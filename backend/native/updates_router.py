"""
/api/native/updates/* — Auto-update channel API.

Endpoints
---------
    GET  /api/native/updates/status     — installed + latest_known + staged
    POST /api/native/updates/check      — fetch manifest, persist
    POST /api/native/updates/download   — stream bundle + verify sha256
    POST /api/native/updates/apply      — master-admin only; writes pending_apply.json

`status` is unauthenticated so the React shell can show the "Update
available" pill without needing an admin session. `check` and `download`
are open too (read-mostly + idempotent + no destructive side-effects on
the running install). `apply` requires the master-admin JWT because it
schedules a swap of the install root on next launch.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from .updates_service import UpdatesService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/native/updates", tags=["native-updates"])

_db = None
_service: Optional[UpdatesService] = None


def set_database(database) -> None:
    global _db, _service
    _db = database
    _service = UpdatesService(
        backend_dir=Path(__file__).resolve().parent.parent,
        db=_db,
    )


def _svc() -> UpdatesService:
    if _service is None:
        raise HTTPException(status_code=503, detail="updates_service_unavailable")
    return _service


# ----- Auth: master-admin only on apply -----
async def _require_master_admin(request: Request) -> Dict[str, Any]:
    # Reuse admin_router's resolver — it already supports the
    # set_current_user_resolver setter for tests.
    from .admin_router import _require_master_admin as _gate
    return await _gate(request)


# ----- Endpoints -----
@router.get("/status")
async def updates_status() -> Dict[str, Any]:
    return await _svc().status()


@router.post("/check")
async def updates_check() -> Dict[str, Any]:
    try:
        return await _svc().check()
    except RuntimeError as e:
        # update_channel_not_configured / manifest_http_<code> / fixture path errors
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        logger.error(f"[UPDATES] check failed: {e}")
        raise HTTPException(status_code=500, detail=f"check_failed: {e}")


@router.post("/download")
async def updates_download() -> Dict[str, Any]:
    try:
        return await _svc().download()
    except RuntimeError as e:
        # invalid_manifest_sha256 / sha256_mismatch / no_update / local_bundle_missing
        msg = str(e)
        if msg.startswith("sha256_mismatch") or msg == "invalid_manifest_sha256":
            raise HTTPException(status_code=409, detail=msg)
        if msg == "update_channel_not_configured":
            raise HTTPException(status_code=502, detail=msg)
        raise HTTPException(status_code=502, detail=msg)
    except Exception as e:
        logger.error(f"[UPDATES] download failed: {e}")
        raise HTTPException(status_code=500, detail=f"download_failed: {e}")


@router.post("/open-installer")
async def updates_open_installer() -> Dict[str, Any]:
    """The green "Download update" button. Opens this PC's installer download (or the release page) in the user's own browser.
    v32.2.1: the old button copied the installer into a hidden folder and showed nothing. The link is read from the update channel
    HERE, so a web page cannot choose where the browser goes."""
    import os, webbrowser
    svc = _svc()                                                 # a 503 here is its own clear error
    try:
        info = await svc.installer_link()
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:                                       # noqa: BLE001
        logger.error(f"[UPDATES] installer link failed: {e}")
        raise HTTPException(status_code=500, detail=f"installer_link_failed: {e}")
    if not info.get("update_available"):
        return {**info, "opened": False, "reason": "no_update_available"}
    ok = False
    if os.environ.get("BIGHAT_NO_BROWSER") == "1":              # tests: do not really launch a browser
        ok = True
        info["simulated"] = True
    else:
        try:
            ok = bool(webbrowser.open(info["url"], new=2))
        except Exception as e:                                   # noqa: BLE001
            logger.warning(f"[UPDATES] could not open {info['url']}: {e}")
    return {**info, "opened": ok}


@router.post(
    "/apply",
    dependencies=[Depends(_require_master_admin)],
)
async def updates_apply(force: bool = False) -> Dict[str, Any]:
    try:
        return await _svc().apply(force=force)
    except RuntimeError as e:
        msg = str(e)
        if msg in ("nothing_staged", "staged_bundle_missing"):
            raise HTTPException(status_code=409, detail=msg)
        if msg.startswith("already_scheduled"):
            raise HTTPException(status_code=409, detail=msg)
        raise HTTPException(status_code=500, detail=msg)
    except Exception as e:
        logger.error(f"[UPDATES] apply failed: {e}")
        raise HTTPException(status_code=500, detail=f"apply_failed: {e}")
