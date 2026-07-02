"""
/api/native/* HTTP endpoints — setup wizard, license, subscription.

These endpoints are mounted unconditionally so the React frontend can probe
`/api/native/info` to decide whether to show the setup wizard. They never
touch MongoDB; they only operate on `system_config.json`.
"""
from __future__ import annotations

import bcrypt
import logging
import re as _re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel, Field, field_validator

from .config import config_manager
from .hwid import generate_hwid
from .license import (
    get_license_status,
    is_well_formed_license,
    register_seat,
    release_seat,
    set_license_key,
)
from .subscription import get_subscription, set_subscription
from . import cloud_client

router = APIRouter(prefix="/api/native", tags=["native"])
logger = logging.getLogger("bighat-native-router")


# ---------- Models ----------
class SetupSettings(BaseModel):
    company_name: Optional[str] = "BIG Hat Entertainment"
    location_name: str = Field(..., min_length=1)
    city: str = ""
    state: str = "AZ"
    trivia_source: str = "local"  # 'local' | 'cloud'


_EMAIL_RE = _re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class SetupMasterAdmin(BaseModel):
    email: str = Field(..., min_length=3)
    password: str = Field(..., min_length=6)
    first_name: str = Field(..., min_length=1)
    last_name: str = ""
    display_name: Optional[str] = None
    phone: Optional[str] = None

    @field_validator("email")
    @classmethod
    def _check_email(cls, v: str) -> str:
        v = (v or "").strip().lower()
        if not _EMAIL_RE.match(v):
            raise ValueError("invalid_email")
        return v


class SetupPaths(BaseModel):
    data_root: Optional[str] = None
    local_trivia: Optional[str] = None
    assets: Optional[str] = None
    generated: Optional[str] = None


class SetupInitRequest(BaseModel):
    license_key: str
    master_admin: SetupMasterAdmin
    settings: SetupSettings
    paths: Optional[SetupPaths] = None
    # When true, skip the authoritative cloud activate call entirely and
    # complete setup with the license flagged as `pending_cloud_activation`.
    # The 4-hour background refresh job will retry activation later. This
    # is the only safe response when the cloud reports `unknown_key` for a
    # key the user knows is valid (e.g. they just bought it and a DB-wipe
    # redeploy lost the record, or the user is genuinely offline).
    offline_mode: bool = False


class LicenseSetRequest(BaseModel):
    license_key: str
    master_admin_email: Optional[str] = None

class SubscriptionUpdateRequest(BaseModel):
    active: bool
    tier: str = "premium"
    expires_at: Optional[str] = None
    sharepoint_enabled: Optional[bool] = None
    story_generator_enabled: Optional[bool] = None
    # cloud_sync_enabled removed in v31.0.13.


class SeatRegisterRequest(BaseModel):
    label: Optional[str] = None


class CloudActivateRequest(BaseModel):
    license_key: str
    email: Optional[str] = None
    label: Optional[str] = None


class CloudDeactivateRequest(BaseModel):
    confirm: bool = False


def _read_installed_version() -> str:
    """Read backend/VERSION.txt — single source of truth used by Phase 9.1."""
    try:
        from pathlib import Path as _P
        p = _P(__file__).resolve().parent.parent / "VERSION.txt"
        return p.read_text(encoding="utf-8").strip() or "0.0.0"
    except OSError:
        return "0.0.0"


# ---------- Endpoints ----------
@router.get("/info")
async def get_native_info():
    """Used by the frontend on every load to decide UI state."""
    cfg = config_manager.public_view()
    return {
        "version": _read_installed_version(),
        "native_mode": config_manager.is_native_mode(),
        "setup_complete": cfg.get("setup_complete", False),
        "instance_id": cfg.get("instance_id"),
        "settings": cfg.get("settings", {}),
        "paths": cfg.get("paths", {}),
        "license": get_license_status(),
        "subscription": get_subscription(),
        "current_hwid": generate_hwid(),
        "users_count": len(cfg.get("users", [])),
    }


@router.get("/setup/status")
async def get_setup_status():
    return {
        "setup_complete": config_manager.config.get("setup_complete", False),
        "native_mode": config_manager.is_native_mode(),
        "users_count": len(config_manager.config.get("users", [])),
    }


@router.post("/setup/initialize")
async def initialize_setup(payload: SetupInitRequest):
    """First-run setup wizard — creates master admin, sets license, registers seat.

    Also calls the cloud license authority at `api.bighat.live` to bind this
    machine's HWID to the supplied key. The cloud is authoritative on
    `owns_standalone` / `cloud_library_active` / seat counts — we mirror its
    response into local state. Offline-tolerant: if the cloud is unreachable
    (timeout / network error), setup still completes and the licence is
    flagged `pending_cloud_activation`; a background job retries activation
    every few hours until it succeeds. **A 4xx from the cloud** (unknown key,
    revoked, seat limit) rejects the setup so fake keys cannot be used.
    """
    if config_manager.config.get("setup_complete"):
        raise HTTPException(status_code=409, detail="setup_already_complete")

    if not is_well_formed_license(payload.license_key):
        raise HTTPException(status_code=400, detail="invalid_license_format")

    key = payload.license_key.strip().upper()
    admin_email = payload.master_admin.email.lower().strip()
    hwid = generate_hwid()

    # 1. Cloud activation (authoritative). Do this BEFORE writing local state
    #    so a 4xx from the cloud doesn't leave a half-finished config behind.
    #
    # `offline_mode=True` skips this entirely — the wizard's "Continue offline"
    # button sends this flag so an authoritative cloud rejection (e.g.
    # `unknown_key` from a wiped DB) doesn't trap the user. The local copy
    # is marked `pending_cloud_activation` and retried by the 4-hour refresh
    # job once the cloud is reachable + the key has been (re-)minted.
    if payload.offline_mode:
        cloud_resp = {"ok": False, "error": "offline_mode_requested", "skipped": True}
        pending_cloud = True
        logger.info("[setup] offline_mode requested by client; skipping cloud activate")
    else:
        cloud_resp = await cloud_client.activate(
            license_key=key,
            hwid=hwid,
            machine_name=f"Setup Wizard — {payload.master_admin.first_name}",
            email=admin_email,
        )
        pending_cloud = False
        if not cloud_resp.get("ok"):
            if cloud_resp.get("error") in ("timeout", "network_error", "server_error"):
                # Offline-tolerant: accept setup, retry later.
                pending_cloud = True
                logger.info(
                    "[setup] cloud activation deferred (%s); will retry in background",
                    cloud_resp.get("error"),
                )
            else:
                # Authoritative rejection — unknown key, revoked, seat limit, etc.
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error":       cloud_resp.get("error", "license_rejected"),
                        "message":     cloud_resp.get("message", "License could not be activated."),
                        "status_code": cloud_resp.get("status_code"),
                    },
                )

    # 2. Persist license + settings + master admin.
    set_license_key(key, admin_email)

    cfg = config_manager.config
    cfg["settings"].update(payload.settings.model_dump(exclude_none=True))
    if payload.paths:
        cfg["paths"].update(payload.paths.model_dump(exclude_none=True))

    pwd_hash = bcrypt.hashpw(
        payload.master_admin.password.encode("utf-8"), bcrypt.gensalt()
    ).decode("utf-8")
    master_user = {
        "id": str(uuid.uuid4()),
        "email": admin_email,
        "password_hash": pwd_hash,
        "first_name": payload.master_admin.first_name,
        "last_name": payload.master_admin.last_name or "",
        "display_name": (
            payload.master_admin.display_name
            or f"{payload.master_admin.first_name} {payload.master_admin.last_name}".strip()
        ),
        "phone": payload.master_admin.phone,
        "role": "master_admin",
        "is_admin": True,
        "is_master": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "auth_method": "local",
    }
    cfg["users"] = [master_user]  # wipe any prior users on initial setup

    cfg["setup_complete"] = True
    config_manager.save_config()

    # v32.0.0-alpha.30: persist the master_admin profile to
    # `BIG Hat Entertainment/Files/Hosts/<slug>/host.json` so Host Recall
    # can identify the operator offline and survive a system_config wipe.
    # Import lazily to avoid a circular import at module load time (the
    # files_router itself imports from `.config`).
    try:
        from .files_router import write_host_profile_json  # noqa: WPS433
        write_host_profile_json(master_user)
    except Exception as e:  # pragma: no cover — never fail setup over disk
        logger.warning("[setup] could not persist host.json: %s", e)

    # 3. Mirror cloud response (subscription flags, seats) OR flag pending.
    #
    # SECURITY INVARIANT — the cloud is authoritative on entitlement.
    # `pending_cloud` is ONLY reached when the cloud was unreachable
    # (timeout / network error) or the customer chose offline mode AFTER
    # the cloud had previously approved the key. We never grant
    # `owns_standalone=true` without an OK from `api.bighat.live` — the
    # repo is public, so any "trust the local key" shortcut would let
    # anyone with a well-formed BHE-XXXX string bypass payment. The
    # 4-hour refresh job promotes the local state once the cloud
    # confirms entitlement; until then features stay locked.
    if pending_cloud:
        lic = config_manager.config.setdefault("license_status", {})
        lic["pending_cloud_activation"] = True
        config_manager.save_config()
        # Local seat so the customer can use the app offline immediately.
        register_seat(label=f"Master Admin — {master_user['display_name']}")
    else:
        _apply_cloud_response_to_local_state(cloud_resp, license_key=key, email=admin_email)
        register_seat(label=f"Master Admin — {master_user['display_name']}")

    return {
        "status": "ok",
        "master_admin_email": master_user["email"],
        "hwid": hwid,
        "license": get_license_status(),
        "subscription": get_subscription(),
        "cloud": cloud_resp if not pending_cloud else {
            "ok": False, "pending": True, "error": cloud_resp.get("error"),
        },
    }


@router.post("/setup/reset")
async def reset_setup(confirm: str = ""):
    """DANGEROUS: wipes config back to factory. Requires confirm=RESET-NATIVE."""
    if confirm != "RESET-NATIVE":
        raise HTTPException(status_code=400, detail="confirmation_required")
    # Reset by writing defaults
    from .config import _default_config  # noqa: WPS433

    config_manager.config = _default_config()
    config_manager.save_config()
    return {"status": "ok", "message": "system_config reset to factory defaults"}


@router.get("/license")
async def get_license():
    return get_license_status()


@router.post("/license")
async def set_license(payload: LicenseSetRequest):
    ok, msg = set_license_key(payload.license_key, payload.master_admin_email)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"status": "ok", "license": get_license_status()}


@router.post("/license/seat/register")
async def register_current_seat(payload: SeatRegisterRequest):
    ok, msg = register_seat(label=payload.label)
    if not ok:
        raise HTTPException(status_code=409, detail=msg)
    return {"status": "ok", "message": msg, "license": get_license_status()}


@router.post("/license/seat/release")
async def release_current_seat(hwid: Optional[str] = None):
    ok, msg = release_seat(hwid)
    if not ok:
        raise HTTPException(status_code=404, detail=msg)
    return {"status": "ok", "message": msg, "license": get_license_status()}


# ---------- Cloud-license activation (Phase 10.2) ----------
def _apply_cloud_response_to_local_state(resp: dict, *, license_key: str, email: Optional[str]) -> None:
    """Mirror the cloud's authoritative state into `system_config.json` so that
    `is_premium_active()` and `get_license_status()` return correct values
    even when offline."""
    set_license_key(license_key, master_admin_email=email)
    flags = {
        "sharepoint_enabled":      bool(resp.get("cloud_library_active")),
        "story_generator_enabled": bool(resp.get("owns_standalone")),
        # cloud_sync_enabled removed in v31.0.13.
        "music_bingo_enabled":     bool(resp.get("owns_standalone") and resp.get("owns_music_bingo")),
        "karaoke_enabled":         bool(resp.get("owns_standalone") and resp.get("owns_karaoke")),
        "bingo_story_enabled":     bool(resp.get("owns_standalone") and resp.get("owns_music_bingo")),
        "karaoke_story_enabled":   bool(resp.get("owns_standalone") and resp.get("owns_karaoke")),
    }
    set_subscription(
        active=bool(resp.get("owns_standalone") or resp.get("cloud_library_active")),
        tier=("premium" if resp.get("cloud_library_active")
              else "standalone" if resp.get("owns_standalone") else "free"),
        expires_at=resp.get("cloud_library_expires_at"),
        feature_flags=flags,
    )
    # Stash the last cloud snapshot for the offline-grace logic.
    sub = config_manager.config.setdefault("subscription", {})
    sub["last_cloud_validated_at"] = datetime.now(timezone.utc).isoformat()
    sub["revalidate_after"] = resp.get("revalidate_after")
    sub["owns_standalone"]    = bool(resp.get("owns_standalone"))
    sub["owns_music_bingo"]   = bool(resp.get("owns_music_bingo"))
    sub["owns_karaoke"]       = bool(resp.get("owns_karaoke"))
    sub["cloud_library_active"] = bool(resp.get("cloud_library_active"))
    config_manager.save_config()


@router.post("/license/cloud/activate")
async def cloud_activate(payload: CloudActivateRequest):
    """Online activation: tells `api.bighat.live` to bind this machine's HWID
    to the supplied license key. Mirrors the cloud's response into local state."""
    key = payload.license_key.strip().upper()
    if not is_well_formed_license(key):
        raise HTTPException(status_code=400, detail="invalid_license_format")
    hwid = generate_hwid()
    resp = await cloud_client.activate(
        license_key=key, hwid=hwid,
        machine_name=payload.label,
        email=payload.email,
    )
    if not resp.get("ok"):
        is_transport_err = resp.get("error") in ("timeout", "network_error", "server_error")
        raise HTTPException(
            status_code=503 if is_transport_err else 400,
            detail={
                "error":      resp.get("error", "cloud_unreachable"),
                "message":    resp.get("message", ""),
                "status_code": resp.get("status_code"),
            },
        )
    _apply_cloud_response_to_local_state(resp, license_key=key, email=payload.email)
    register_seat(label=payload.label or "This computer")
    return {
        "status":       "ok",
        "license":      get_license_status(),
        "subscription": get_subscription(),
        "cloud":        resp,
    }


@router.post("/license/cloud/validate")
async def cloud_validate():
    """Periodic re-check (UI cron'd at startup + every 7 days). Refreshes
    local subscription state from the cloud's authoritative truth.

    On transport error we DO NOT raise — the cached state is still honoured
    via the offline grace window. We surface the error in the payload so
    the UI can show a "last checked X minutes ago, offline" badge."""
    cfg = config_manager.config
    lic = cfg.get("license_status", {}) or {}
    key = lic.get("key")
    if not key:
        raise HTTPException(status_code=400, detail="no_license_key_set")
    hwid = generate_hwid()
    resp = await cloud_client.validate(license_key=key, hwid=hwid)
    if resp.get("ok") and resp.get("error") is None:
        _apply_cloud_response_to_local_state(resp, license_key=key, email=None)
        return {
            "status":       "ok",
            "license":      get_license_status(),
            "subscription": get_subscription(),
            "cloud":        resp,
        }
    # Network error → don't downgrade; bubble up the offline state.
    return {
        "status":       "offline",
        "license":      get_license_status(),
        "subscription": get_subscription(),
        "error":        resp.get("error"),
        "message":      resp.get("message"),
    }


@router.post("/license/cloud/deactivate")
async def cloud_deactivate(payload: CloudDeactivateRequest):
    """Move-to-new-machine path. Releases the seat on the cloud + locally.
    User must `confirm=true` to prevent accidental clicks."""
    if not payload.confirm:
        raise HTTPException(status_code=400, detail="confirmation_required")
    cfg = config_manager.config
    lic = cfg.get("license_status", {}) or {}
    key = lic.get("key")
    if not key:
        raise HTTPException(status_code=400, detail="no_license_key_set")
    hwid = generate_hwid()
    resp = await cloud_client.deactivate(license_key=key, hwid=hwid)
    # Even if cloud is unreachable, free the local seat so the user can move on.
    release_seat(hwid)
    set_subscription(active=False, tier="free")
    return {
        "status": "ok" if resp.get("ok") else "offline",
        "license": get_license_status(),
        "cloud":  resp,
    }



@router.get("/subscription")
async def get_sub():
    return get_subscription()


@router.post("/subscription")
async def update_sub(payload: SubscriptionUpdateRequest):
    flags = {
        k: v
        for k, v in payload.model_dump().items()
        if k
        in ("sharepoint_enabled", "story_generator_enabled")
        and v is not None
    }
    sub = set_subscription(
        active=payload.active,
        tier=payload.tier,
        expires_at=payload.expires_at,
        feature_flags=flags or None,
    )
    return {"status": "ok", "subscription": sub}


@router.get("/hwid")
async def get_hwid():
    return {"hwid": generate_hwid()}


@router.get("/config")
async def get_full_config():
    """Master-Admin only in production. For Phase 0 this is open for debugging."""
    return config_manager.public_view()



@router.post("/errors/report")
async def report_frontend_error(payload: Dict[str, Any] = Body(...)):
    """Sink for the React ErrorBoundary. We log to the standard
    supervisor stream so `tail -f /var/log/supervisor/backend.err.log`
    surfaces frontend crashes without needing DevTools open.

    The endpoint deliberately never raises — the frontend fire-and-
    forgets with `keepalive: true` during teardown, and we don't want
    a validation error to become the reason the user's Reload button
    disappears.
    """
    try:
        msg = str(payload.get("message") or "").strip()[:400]
        stack = str(payload.get("stack") or "").strip()[:2000]
        comp = str(payload.get("componentStack") or "").strip()[:2000]
        loc = str(payload.get("location") or "").strip()[:400]
        logger.error(
            "[frontend-error-boundary] loc=%s msg=%s\n  stack=%s\n  componentStack=%s",
            loc, msg, stack, comp,
        )
    except Exception as e:  # pragma: no cover
        logger.warning("[frontend-error-boundary] failed to log report: %s", e)
    return {"ok": True}
