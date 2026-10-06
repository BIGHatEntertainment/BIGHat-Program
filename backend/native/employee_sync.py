"""alpha.72: keep Schedule employees and User Management users in step (standalone app).

In the standalone app the real list of users is system_config.json -> users[]. User Management reads it, logins read it,
and on every load anything in db.users that is NOT in that list is purged. The old employee sync wrote only to db.users,
so a new employee never appeared in User Management (and would have been erased if they had).

These helpers write to the config (permanent) and mirror to db.users, the same way Admin > Users does.
The master admin is never created, changed in role, or deleted from here.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import bcrypt

from native import config_manager
from native import admin_router

ROLE_FOR_ADMIN = "admin"
ROLE_FOR_HOST = "host"


def norm_email(email: str) -> str:
    return (email or "").strip().lower()


def role_for(is_admin: bool) -> str:
    return ROLE_FOR_ADMIN if is_admin else ROLE_FOR_HOST


def _split_name(name: str) -> tuple[str, str]:
    parts = (name or "").strip().split(None, 1)
    return (parts[0] if parts else "", parts[1] if len(parts) > 1 else "")


def _hash(pw: str) -> str:
    return bcrypt.hashpw(pw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def find_user(email: str) -> Optional[Dict[str, Any]]:
    return admin_router._find_cfg_user(norm_email(email))


def is_master(user: Optional[Dict[str, Any]]) -> bool:
    return bool(user) and (user.get("is_master") or user.get("role") == "master_admin")


async def upsert_user_for_employee(name: str, email: str, is_admin: bool, phone: Optional[str],
                                   password: Optional[str], default_password: str) -> Dict[str, Any]:
    """Create the user for an employee, or update the existing one. Returns the (config) user."""
    email = norm_email(email)
    first, last = _split_name(name)
    existing = find_user(email)
    if existing:
        if is_master(existing):
            return existing                      # never touch the master admin from the schedule
        existing["first_name"] = first or existing.get("first_name", "")
        existing["last_name"] = last
        existing["display_name"] = (name or "").strip() or existing.get("display_name", "")
        existing["phone"] = phone
        existing["role"] = role_for(is_admin)
        existing["is_admin"] = bool(is_admin)
        if password and not is_master(existing):  # only when a NEW password was typed (never the master's)
            existing["password_hash"] = _hash(password)
        existing["updated_at"] = datetime.now(timezone.utc).isoformat()
        admin_router._save_config()
        await admin_router._mirror_to_db(existing)
        return existing
    user = {
        "id": str(uuid.uuid4()),
        "email": email,
        "password_hash": _hash(password or default_password),
        "first_name": first,
        "last_name": last,
        "display_name": (name or "").strip(),
        "phone": phone,
        "role": role_for(is_admin),
        "is_admin": bool(is_admin),
        "is_master": False,
        "enabled": True,
        "auth_method": "local",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    config_manager.config.setdefault("users", []).append(user)
    admin_router._save_config()
    await admin_router._mirror_to_db(user)
    return user


async def ensure_master_employee(db) -> bool:
    """The master admin is also a Schedule employee (they host events too).
    Creates the employee row if missing. Never touches the master's login or password."""
    cfg_users = config_manager.config.get("users", []) or []
    master = next((u for u in cfg_users if is_master(u)), None)
    if not master or not master.get("email"):
        return False
    email = norm_email(master["email"])
    if await db.employees.find_one({"email": {"$regex": f"^{re.escape(email)}$", "$options": "i"}}):
        return False
    name = (master.get("display_name") or f"{master.get('first_name', '')} {master.get('last_name', '')}").strip() or email
    await db.employees.insert_one({
        "id": str(uuid.uuid4()), "name": name, "email": email, "phone": master.get("phone"),
        "is_admin": True, "password": "",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return True


async def remove_user_for_employee(email: str) -> bool:
    """Remove the user that belongs to a deleted employee (never the master admin)."""
    email = norm_email(email)
    user = find_user(email)
    if not user or is_master(user):
        return False
    config_manager.config["users"] = [u for u in config_manager.config.get("users", []) if norm_email(u.get("email")) != email]
    admin_router._save_config()
    await admin_router._purge_from_db(email)
    return True


async def sync_all(employees: list, default_password: str) -> int:
    """At startup: make sure every employee has a user. Only ADDS missing users; never changes existing ones."""
    made = 0
    for emp in employees:
        email = norm_email(emp.get("email"))
        if not email or find_user(email):
            continue
        await upsert_user_for_employee(emp.get("name", ""), email, bool(emp.get("is_admin")), emp.get("phone"), None, default_password)
        made += 1
    return made


async def set_user_password(email: str, new_password: str) -> bool:
    """Change the login password of the user that belongs to an employee (never the master admin)."""
    user = find_user(email)
    if not user or is_master(user):
        return False
    user["password_hash"] = _hash(new_password)
    user["updated_at"] = datetime.now(timezone.utc).isoformat()
    admin_router._save_config()
    await admin_router._mirror_to_db(user)
    return True


_WORDS_A = ["Swift", "Brave", "Sunny", "Lucky", "Bright", "Happy", "Cosmic", "Silver", "Golden", "Rapid"]
_WORDS_B = ["Otter", "Falcon", "Tiger", "Maple", "River", "Comet", "Harbor", "Willow", "Rocket", "Panda"]


def make_temp_password() -> str:
    """Easy to read out loud and type: Swift-Otter-4821"""
    import secrets
    return f"{secrets.choice(_WORDS_A)}-{secrets.choice(_WORDS_B)}-{secrets.randbelow(9000) + 1000}"
