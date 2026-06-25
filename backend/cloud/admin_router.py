"""Admin routes for the cloud licensing service.

All endpoints require a `Bearer` token signed with `LICENSE_ADMIN_SECRET`
(falls back to `JWT_SECRET`). Obtain a token by POSTing valid admin
credentials to `/api/license/admin/login`. Credentials are reused from
the existing webapp admin (ADMIN_EMAIL / ADMIN_PASSWORD env vars).

Endpoints:
    POST /api/license/admin/login
    GET  /api/license/admin/keys
    GET  /api/license/admin/keys/{key}
    POST /api/license/admin/keys/mint
    POST /api/license/admin/keys/restore     (recover a key after data-wipe)
    POST /api/license/admin/keys/{key}/revoke
    POST /api/license/admin/keys/{key}/resend-email
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt as pyjwt
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request

from . import config
from .license_models import (
    AdminKeyView,
    AdminLoginRequest,
    AdminTokenResponse,
    MintKeyRequest,
)
from .license_service import LicenseService

logger = logging.getLogger("bighat-license-admin")

router = APIRouter(prefix="/api/license/admin", tags=["cloud-licensing-admin"])

_JWT_ALG = "HS256"

_service: Optional[LicenseService] = None


def set_service(service: LicenseService) -> None:
    global _service
    _service = service


def _require_service() -> LicenseService:
    if _service is None:
        raise HTTPException(status_code=503, detail="admin service not initialized")
    return _service


# ---- JWT helpers ----
def _create_token(email: str) -> str:
    secret = config.license_admin_secret()
    if not secret:
        raise HTTPException(status_code=500, detail="admin secret not configured")
    payload = {
        "sub":   email,
        "role":  "license_admin",
        "exp":   datetime.now(timezone.utc) + timedelta(hours=8),
        "type":  "access",
    }
    return pyjwt.encode(payload, secret, algorithm=_JWT_ALG)


async def _require_admin(request: Request) -> str:
    """Returns the admin email if the bearer token is valid."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing_bearer_token")
    token = auth[7:]
    secret = config.license_admin_secret()
    if not secret:
        raise HTTPException(status_code=500, detail="admin secret not configured")
    try:
        decoded = pyjwt.decode(token, secret, algorithms=[_JWT_ALG])
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="token_expired")
    except pyjwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail=f"invalid_token: {e}")
    if decoded.get("role") != "license_admin":
        raise HTTPException(status_code=403, detail="not_a_license_admin")
    return decoded.get("sub", "")


def _to_view(lic) -> AdminKeyView:
    return AdminKeyView(
        key=lic.key,
        email=lic.email,
        owns_standalone=lic.owns_standalone,
        owns_music_bingo=lic.owns_music_bingo,
        owns_karaoke=lic.owns_karaoke,
        cloud_library_status=lic.cloud_library_status,
        cloud_library_expires_at=lic.cloud_library_expires_at,
        max_seats=lic.max_seats,
        active_seats=len(lic.active_hwids),
        revoked=lic.revoked,
        created_at=lic.created_at,
        updated_at=lic.updated_at,
    )


# ---- login ----
@router.post("/login", response_model=AdminTokenResponse)
async def login(req: AdminLoginRequest) -> AdminTokenResponse:
    """Reuse the webapp's ADMIN_EMAIL / ADMIN_PASSWORD for ops simplicity.

    In deployment, set `ADMIN_PASSWORD` to a bcrypt hash (recommended) OR a
    plain string (for dev). We auto-detect the hash by its `$2` prefix.
    """
    expected_email = (os.environ.get("ADMIN_EMAIL") or "").strip().lower()
    expected_password = os.environ.get("ADMIN_PASSWORD") or ""
    if not expected_email or not expected_password:
        raise HTTPException(status_code=500, detail="admin credentials not configured")
    if req.email.strip().lower() != expected_email:
        raise HTTPException(status_code=401, detail="invalid_credentials")

    if expected_password.startswith("$2"):
        ok = bcrypt.checkpw(req.password.encode("utf-8"),
                            expected_password.encode("utf-8"))
    else:
        ok = req.password == expected_password
    if not ok:
        raise HTTPException(status_code=401, detail="invalid_credentials")

    return AdminTokenResponse(access_token=_create_token(expected_email))


# ---- key management ----
@router.get("/keys", response_model=list[AdminKeyView])
async def list_keys(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    _admin: str = Depends(_require_admin),
) -> list[AdminKeyView]:
    svc = _require_service()
    rows = await svc.store.list_all(limit=limit, offset=offset)
    return [_to_view(r) for r in rows]


@router.get("/keys/{key}", response_model=AdminKeyView)
async def get_key(
    key: str = Path(..., min_length=8, max_length=64),
    _admin: str = Depends(_require_admin),
) -> AdminKeyView:
    svc = _require_service()
    lic = await svc.store.get_by_key(key)
    if not lic:
        raise HTTPException(status_code=404, detail="not_found")
    return _to_view(lic)


@router.post("/keys/mint", response_model=AdminKeyView)
async def mint_key(
    req: MintKeyRequest,
    _admin: str = Depends(_require_admin),
) -> AdminKeyView:
    svc = _require_service()
    lic = await svc.mint_manual(
        email=str(req.email),
        owns_standalone=req.owns_standalone,
        owns_music_bingo=req.owns_music_bingo,
        owns_karaoke=req.owns_karaoke,
        cloud_library_months=req.cloud_library_months,
        note=req.note,
        send_email=req.send_email,
    )
    return _to_view(lic)


# ---- restore (put a wiped license back with its ORIGINAL key) ----
class _RestoreKeyRequest(MintKeyRequest):
    """Same fields as MintKeyRequest plus `key` — the exact license string
    the customer already has in their original purchase email. Used after a
    cloud DB wipe so customers don't get a brand-new key (which would
    invalidate the one they were emailed at purchase time)."""
    key: str


@router.post("/keys/restore", response_model=AdminKeyView)
async def restore_key(
    req: _RestoreKeyRequest,
    _admin: str = Depends(_require_admin),
) -> AdminKeyView:
    """Recovery endpoint for a license that was lost from the DB (e.g. a
    cloud-side data wipe). Re-inserts the license with the customer's
    ORIGINAL key value — the one already in their purchase email — so they
    don't need a new email and the email-key contract is preserved.

    Idempotent on the key: if a row already exists for this key, returns it
    unchanged. If a row exists for the email but with a DIFFERENT key, the
    request is rejected (use `/keys/mint` for a fresh purchase, or revoke
    the old row first).
    """
    svc = _require_service()
    # If the key already exists, treat as idempotent success.
    existing_by_key = await svc.store.get_by_key(req.key)
    if existing_by_key:
        return _to_view(existing_by_key)
    # If a row exists for the email under a different key, refuse — the
    # caller probably wants /keys/mint instead.
    existing_by_email = await svc.store.get_by_email(str(req.email))
    if existing_by_email and existing_by_email.key != req.key:
        raise HTTPException(
            status_code=409,
            detail=(
                f"email already has a different key: {existing_by_email.key}. "
                "Use /keys/mint, or revoke the existing row first."
            ),
        )
    lic = await svc.mint_manual(
        email=str(req.email),
        owns_standalone=req.owns_standalone,
        owns_music_bingo=req.owns_music_bingo,
        owns_karaoke=req.owns_karaoke,
        cloud_library_months=req.cloud_library_months,
        note=(req.note or "restored after data-wipe"),
        send_email=False,   # don't double-email — customer already has the key
        key=req.key,
    )
    logger.info("[license] admin restored key %s for %s", req.key, req.email)
    return _to_view(lic)


@router.post("/keys/{key}/resend-email")
async def resend_email(
    key: str = Path(..., min_length=8, max_length=64),
    _admin: str = Depends(_require_admin),
) -> dict:
    """Re-send the standard license-key email for an existing key.
    Used by support when a customer reports they didn't receive (or lost)
    the original email — turns a 30-second ticket into a single curl /
    button click."""
    svc = _require_service()
    ok, message = await svc.resend_license_email(key=key)
    if not ok:
        raise HTTPException(status_code=404 if message == "unknown_key" else 500,
                            detail=message)
    return {"ok": True, "key": key, "message": message}


@router.post("/keys/{key}/revoke", response_model=AdminKeyView)
async def revoke_key(
    key: str = Path(..., min_length=8, max_length=64),
    reason: str = Query("revoked_by_admin", max_length=200),
    _admin: str = Depends(_require_admin),
) -> AdminKeyView:
    svc = _require_service()
    lic = await svc.revoke(key=key, reason=reason)
    if not lic:
        raise HTTPException(status_code=404, detail="not_found")
    return _to_view(lic)
