"""FastAPI routes for the cloud licensing service.

Mount via `server.py` only when `BIGHAT_CLOUD_MODE=1`. All endpoints are
rate-limited at the app level (see server.py); the handlers here assume
the request has already cleared CORS/rate-limiting.

Public endpoints (consumed by the desktop app + by Squarespace):
    POST /api/license/activate
    POST /api/license/validate
    POST /api/license/deactivate
    GET  /api/license/status/{key}
    GET  /api/downloads/{platform}          (platform = 'windows'|'macos')
    POST /api/squarespace/webhook
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Path, Request

from . import config
from .license_models import (
    ActivateRequest, ActivateResponse,
    DeactivateRequest,
    DownloadInfo,
    StatusResponse,
    ValidateRequest, ValidateResponse,
)
from .license_service import LicenseService, mask_key, now_utc
from .license_store import LicenseStore
from .squarespace_webhook import WebhookHandler, verify_signature

logger = logging.getLogger("bighat-license-router")

router = APIRouter(prefix="/api", tags=["cloud-licensing"])

# ---- Injected from server.py at startup ----
_store: Optional[LicenseStore] = None
_service: Optional[LicenseService] = None
_webhook: Optional[WebhookHandler] = None


def set_runtime(*, store: LicenseStore, service: LicenseService, webhook: WebhookHandler) -> None:
    global _store, _service, _webhook
    _store, _service, _webhook = store, service, webhook


def _require_service() -> LicenseService:
    if _service is None:
        raise HTTPException(status_code=503, detail="license service not initialized")
    return _service


def _require_webhook() -> WebhookHandler:
    if _webhook is None:
        raise HTTPException(status_code=503, detail="webhook handler not initialized")
    return _webhook


# ---------- /api/license/activate ----------
@router.post("/license/activate", response_model=ActivateResponse)
async def activate(req: ActivateRequest) -> ActivateResponse:
    svc = _require_service()
    ok, msg, lic = await svc.activate(
        key=req.key, hwid=req.hwid, machine_name=req.machine_name,
    )
    if not ok or lic is None:
        raise HTTPException(status_code=400, detail=msg)
    revalidate_after = now_utc() + timedelta(days=config.VALIDATION_INTERVAL_DAYS)
    return ActivateResponse(
        ok=True, message=msg,
        owns_standalone=lic.owns_standalone,
        owns_music_bingo=lic.owns_music_bingo,
        owns_karaoke=lic.owns_karaoke,
        cloud_library_active=lic.cloud_library_status == "active"
                             and not lic.revoked,
        cloud_library_expires_at=lic.cloud_library_expires_at,
        max_seats=lic.max_seats,
        active_seats=len(lic.active_hwids),
        revalidate_after=revalidate_after,
    )


# ---------- /api/license/validate ----------
@router.post("/license/validate", response_model=ValidateResponse)
async def validate(req: ValidateRequest) -> ValidateResponse:
    svc = _require_service()
    ok, msg, lic = await svc.validate(key=req.key, hwid=req.hwid)
    revalidate_after = now_utc() + timedelta(days=config.VALIDATION_INTERVAL_DAYS)
    if not ok or lic is None:
        # Return a well-formed negative response (not 4xx) so the desktop
        # client can still parse and gate features without branching on HTTP.
        return ValidateResponse(
            ok=False,
            owns_standalone=False,
            cloud_library_active=False,
            cloud_library_expires_at=None,
            revoked=(msg == "revoked"),
            revalidate_after=revalidate_after,
        )
    return ValidateResponse(
        ok=True,
        owns_standalone=lic.owns_standalone,
        owns_music_bingo=lic.owns_music_bingo,
        owns_karaoke=lic.owns_karaoke,
        cloud_library_active=lic.cloud_library_status == "active" and not lic.revoked,
        cloud_library_expires_at=lic.cloud_library_expires_at,
        revoked=lic.revoked,
        revalidate_after=revalidate_after,
    )


# ---------- /api/license/deactivate ----------
@router.post("/license/deactivate")
async def deactivate(req: DeactivateRequest) -> dict:
    svc = _require_service()
    ok, msg = await svc.deactivate(key=req.key, hwid=req.hwid)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"ok": True, "message": msg}


# ---------- /api/license/status/{key} ----------
@router.get("/license/status/{key}", response_model=StatusResponse)
async def status(key: str = Path(..., min_length=8, max_length=64)) -> StatusResponse:
    svc = _require_service()
    lic = await svc.store.get_by_key(key)
    if not lic or lic.revoked:
        raise HTTPException(status_code=404, detail="not_found")
    return StatusResponse(
        key_masked=mask_key(lic.key),
        owns_standalone=lic.owns_standalone,
        owns_music_bingo=lic.owns_music_bingo,
        owns_karaoke=lic.owns_karaoke,
        cloud_library_status=lic.cloud_library_status,
        active_seats=len(lic.active_hwids),
        max_seats=lic.max_seats,
    )


# ---------- /api/downloads/{platform} ----------
@router.get("/downloads/{platform}", response_model=DownloadInfo)
async def download(platform: str = Path(..., pattern="^(windows|macos)$")) -> DownloadInfo:
    url = (config.download_url_windows() if platform == "windows"
           else config.download_url_macos())
    if not url:
        raise HTTPException(status_code=404, detail=f"no download configured for {platform}")
    return DownloadInfo(platform=platform, url=url, version=config.current_release_version())


# ---------- /api/squarespace/webhook ----------
@router.post("/squarespace/webhook")
async def squarespace_webhook(request: Request) -> dict:
    """Signed webhook from Squarespace Commerce.

    In production, `SQUARESPACE_WEBHOOK_SECRET` must be set; missing/invalid
    signatures are rejected with 401. In dev (no secret configured) we log
    a warning and accept the request so you can curl-test the endpoint.
    """
    body = await request.body()
    signature = (
        request.headers.get("Squarespace-Signature")
        or request.headers.get("X-Squarespace-Signature")
        or ""
    )
    secret = config.squarespace_webhook_secret()
    if secret:
        if not verify_signature(body=body, signature_header=signature, secret=secret):
            logger.warning("[webhook] signature mismatch; rejecting")
            raise HTTPException(status_code=401, detail="invalid_signature")
    else:
        logger.warning("[webhook] SQUARESPACE_WEBHOOK_SECRET not set — accepting unsigned request")

    try:
        payload = await request.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"invalid_json: {e}")
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="payload must be a JSON object")

    handler = _require_webhook()
    result = await handler.handle(payload)
    return result
