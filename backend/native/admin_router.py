"""
/api/native/admin/* — Master-admin-only UI for user management,
license-seat labels, and sub-admin promotion.

Design notes
------------
*Native mode users live in two places:*

  1.  `system_config.json -> users[]`  — the durable source of truth. The
      setup wizard writes the initial master admin here. Sub-admins and
      hosts created via this router are appended here too.
  2.  `db.users` (MontyDB / SQLite) — populated on first login by the
      "native bridge" in `server.py`. This mirror is what the rest of
      the webapp reads (auth/me, role checks). Updates here apply to
      BOTH stores so a rename / role change / password reset propagates
      correctly.

We require a master-admin JWT on every endpoint — sub-admins cannot add
or promote other users. Deletion of the master admin is explicitly
refused to avoid lockout.

Role vocabulary
---------------
    master_admin  — there's exactly one; cannot be deleted or demoted.
    admin         — full webapp admin; can be promoted from / demoted to host.
    host          — default role for new users.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from .config import config_manager
from .hwid import generate_hwid

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/native/admin", tags=["native-admin"])

# DB injected by server.py after the native swap
_db = None


def set_database(database) -> None:
    global _db
    _db = database


# ----- Auth dependency -----
async def _require_master_admin(request: Request) -> Dict[str, Any]:
    """Only master_admin may call /api/native/admin/*.

    We defer to the existing `get_current_user` helper in server.py so
    token rotation, expiry, and cookie-vs-Bearer handling all match
    the rest of the webapp.
    """
    try:
        # Local import to avoid a circular at module load time.
        from server import get_current_user
    except ImportError as e:
        # Shouldn't happen in a live app; surface it clearly.
        logger.error(f"[NATIVE-ADMIN] get_current_user not importable: {e}")
        raise HTTPException(status_code=500, detail="auth_unavailable")
    user = await get_current_user(request)
    if user.get("role") != "master_admin":
        raise HTTPException(status_code=403, detail="master_admin_required")
    return user


# ----- Helpers -----
_VALID_ROLES = ("admin", "host")  # master_admin is not assignable via API


def _sanitize_user(u: Dict[str, Any]) -> Dict[str, Any]:
    """Strip password hash + return a stable subset for the UI."""
    keys = (
        "id", "email", "first_name", "last_name", "display_name", "phone",
        "role", "is_admin", "is_master", "created_at", "updated_at",
        "auth_method", "enabled",
    )
    return {k: u.get(k) for k in keys if k in u}


def _find_cfg_user(email: str) -> Optional[Dict[str, Any]]:
    users = config_manager.config.get("users", []) or []
    email = (email or "").lower().strip()
    return next((u for u in users if (u.get("email") or "").lower().strip() == email), None)


def _find_cfg_user_by_id(user_id: str) -> Optional[Dict[str, Any]]:
    users = config_manager.config.get("users", []) or []
    return next((u for u in users if u.get("id") == user_id), None)


async def _mirror_to_db(cfg_user: Dict[str, Any]) -> None:
    """Keep `db.users` in sync with `system_config.json -> users[]`.

    Upsert on email (case-insensitive). Idempotent.
    """
    if _db is None:
        return
    email = (cfg_user.get("email") or "").lower().strip()
    if not email:
        return
    display = cfg_user.get("display_name") or (
        f"{cfg_user.get('first_name','')} {cfg_user.get('last_name','')}".strip()
    )
    update = {
        "email": email,
        "name": display,
        "role": cfg_user.get("role", "host"),
        "auth_method": "native",
        "native_user_id": cfg_user.get("id"),
        "enabled": cfg_user.get("enabled", True),
    }
    if cfg_user.get("password_hash"):
        update["password_hash"] = cfg_user["password_hash"]
    existing = await _db.users.find_one({"email": email})
    if existing:
        await _db.users.update_one({"email": email}, {"$set": update})
        return
    # Insert with string UUID to keep Mongo/MontyDB happy
    new_id = cfg_user.get("id") or str(uuid.uuid4())
    doc = {"_id": new_id, **update, "created_at": datetime.now(timezone.utc).isoformat()}
    await _db.users.insert_one(doc)


async def _purge_from_db(email: str) -> None:
    if _db is None:
        return
    await _db.users.delete_one({"email": (email or "").lower().strip()})


def _save_config() -> None:
    config_manager.config["updated_at"] = datetime.now(timezone.utc).isoformat()
    config_manager.save_config()


# ----- Pydantic models -----
class UserCreate(BaseModel):
    email: str = Field(..., min_length=3)
    password: str = Field(..., min_length=6)
    first_name: str = Field(..., min_length=1)
    last_name: str = ""
    display_name: Optional[str] = None
    phone: Optional[str] = None
    role: str = "host"

    @field_validator("email")
    @classmethod
    def _lower_email(cls, v: str) -> str:
        import re as _re
        v = (v or "").strip().lower()
        if not _re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", v):
            raise ValueError("invalid_email")
        return v

    @field_validator("role")
    @classmethod
    def _check_role(cls, v: str) -> str:
        v = (v or "host").strip().lower()
        if v not in _VALID_ROLES:
            raise ValueError("invalid_role")
        return v


class UserUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    display_name: Optional[str] = None
    phone: Optional[str] = None
    role: Optional[str] = None
    password: Optional[str] = Field(default=None, min_length=6)
    enabled: Optional[bool] = None

    @field_validator("role")
    @classmethod
    def _check_role(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip().lower()
        if v not in _VALID_ROLES:
            raise ValueError("invalid_role")
        return v


class SeatLabel(BaseModel):
    label: str = Field(..., min_length=1, max_length=120)


# ----- Endpoints: Users -----
@router.get("/users")
async def list_users(_: Dict[str, Any] = Depends(_require_master_admin)) -> Dict[str, Any]:
    users = config_manager.config.get("users", []) or []
    return {
        "users": [_sanitize_user(u) for u in users],
        "count": len(users),
    }


@router.post("/users")
async def create_user(
    payload: UserCreate,
    _: Dict[str, Any] = Depends(_require_master_admin),
) -> Dict[str, Any]:
    if _find_cfg_user(payload.email) is not None:
        raise HTTPException(status_code=409, detail="email_already_exists")

    pwd_hash = bcrypt.hashpw(payload.password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    display = payload.display_name or f"{payload.first_name} {payload.last_name}".strip()
    new_user = {
        "id": str(uuid.uuid4()),
        "email": payload.email,
        "password_hash": pwd_hash,
        "first_name": payload.first_name,
        "last_name": payload.last_name or "",
        "display_name": display,
        "phone": payload.phone,
        "role": payload.role,
        "is_admin": payload.role == "admin",
        "is_master": False,
        "enabled": True,
        "auth_method": "local",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    users = config_manager.config.setdefault("users", [])
    users.append(new_user)
    _save_config()
    await _mirror_to_db(new_user)
    return {"status": "ok", "user": _sanitize_user(new_user)}


@router.put("/users/{user_id}")
async def update_user(
    user_id: str,
    payload: UserUpdate,
    _: Dict[str, Any] = Depends(_require_master_admin),
) -> Dict[str, Any]:
    user = _find_cfg_user_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user_not_found")
    if user.get("is_master") and payload.role and payload.role != "master_admin":
        raise HTTPException(status_code=400, detail="cannot_demote_master_admin")

    patch = payload.model_dump(exclude_none=True)

    if "password" in patch:
        user["password_hash"] = bcrypt.hashpw(
            patch.pop("password").encode("utf-8"), bcrypt.gensalt()
        ).decode("utf-8")

    for k, v in patch.items():
        user[k] = v

    # Derived fields
    if user.get("role") == "admin":
        user["is_admin"] = True
    elif not user.get("is_master"):
        user["is_admin"] = user.get("role") == "admin"

    if "first_name" in patch or "last_name" in patch or "display_name" in patch:
        user["display_name"] = user.get("display_name") or (
            f"{user.get('first_name','')} {user.get('last_name','')}".strip()
        )
    user["updated_at"] = datetime.now(timezone.utc).isoformat()
    _save_config()
    await _mirror_to_db(user)
    return {"status": "ok", "user": _sanitize_user(user)}


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: str,
    _: Dict[str, Any] = Depends(_require_master_admin),
) -> Dict[str, Any]:
    user = _find_cfg_user_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user_not_found")
    if user.get("is_master"):
        raise HTTPException(status_code=400, detail="cannot_delete_master_admin")
    users = config_manager.config.get("users", []) or []
    config_manager.config["users"] = [u for u in users if u.get("id") != user_id]
    _save_config()
    await _purge_from_db(user.get("email", ""))
    return {"status": "ok", "deleted": user_id}


# ----- Endpoints: License seats -----
@router.get("/license/seats")
async def list_seats(_: Dict[str, Any] = Depends(_require_master_admin)) -> Dict[str, Any]:
    """All registered seats + current HWID flag so the UI can show
    "This device" next to the right row."""
    from .license import get_license_status
    status = get_license_status()
    return {
        "seats": status.get("active_seats", []),
        "total_allowed": status.get("total_seats_allowed", 5),
        "used": status.get("used_seats", 0),
        "remaining": status.get("seats_remaining", 0),
        "current_hwid": status.get("current_hwid"),
    }


@router.put("/license/seats/{hwid}/label")
async def rename_seat(
    hwid: str,
    payload: SeatLabel,
    _: Dict[str, Any] = Depends(_require_master_admin),
) -> Dict[str, Any]:
    """Rename a seat entry. HWID path converter is plain — URL-encode HWID."""
    hwid_lc = (hwid or "").strip()
    cfg = config_manager.config
    lic = cfg.setdefault("license_status", {})
    seats: List[Dict[str, Any]] = lic.setdefault("active_seats", [])
    target = next((s for s in seats if s.get("hwid") == hwid_lc), None)
    if target is None:
        raise HTTPException(status_code=404, detail="seat_not_found")
    target["label"] = payload.label
    target["updated_at"] = datetime.now(timezone.utc).isoformat()
    _save_config()
    return {"status": "ok", "seat": target}


@router.delete("/license/seats/{hwid}")
async def revoke_seat(
    hwid: str,
    _: Dict[str, Any] = Depends(_require_master_admin),
) -> Dict[str, Any]:
    """Master-admin-driven seat revoke (distinct from `/license/seat/release`
    which only releases the current machine). Blocks revoking the current
    device to avoid accidentally locking yourself out.
    """
    from .license import release_seat
    current = generate_hwid()
    if hwid == current:
        raise HTTPException(status_code=400, detail="cannot_revoke_current_device")
    ok, msg = release_seat(hwid)
    if not ok:
        raise HTTPException(status_code=404, detail=msg)
    return {"status": "ok", "message": msg}


# ----- Convenience: current admin snapshot -----
@router.get("/whoami")
async def admin_whoami(me: Dict[str, Any] = Depends(_require_master_admin)) -> Dict[str, Any]:
    return {
        "email": me.get("email"),
        "role": me.get("role"),
        "name": me.get("name"),
        "hwid": generate_hwid(),
    }
