"""
/api/native/sync/* — SharePoint Hybrid Sync router.

All mutating endpoints are premium-gated by `cloud_sync_enabled`. The
`/status` endpoint is always free so the frontend can show an upgrade
banner pointing at exactly which subscription flag is needed.

Endpoints:
    GET  /api/native/sync/status   — sync state + last runs + availability
    POST /api/native/sync/plan     — dry-run, returns add/update/delete lists
    POST /api/native/sync/pull     — cloud → local
    POST /api/native/sync/push     — local → cloud
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .asset_factory import can_use_cloud, get_asset_service
from .config import config_manager
from .feature_gate import require_native_premium
from .subscription import get_subscription
from .sync_service import SyncService, get_sync_state, record_sync_run

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/native/sync", tags=["native-sync"])

# Database injected from server.py after the native DB swap
_db = None


def set_database(database) -> None:
    global _db
    _db = database


# Dev-mode override: if `BIGHAT_SYNC_REMOTE_FIXTURE` is set to a local
# directory, the sync engine will treat that directory as "the cloud".
# Lets us exercise the full pull/push flow without real SharePoint creds.
def _remote_service():
    fixture = os.environ.get("BIGHAT_SYNC_REMOTE_FIXTURE", "").strip()
    if fixture:
        from .local_asset_service import LocalAssetService
        return LocalAssetService(root=Path(fixture))
    return get_asset_service()


def _local_root() -> Path:
    assets = config_manager.config.get("paths", {}).get("assets")
    if assets:
        return Path(assets)
    return Path(__file__).parent / "data" / "assets"


class SyncOptions(BaseModel):
    """Body shape for /plan, /pull, /push."""
    sync_root: str = Field(
        default="",
        description="Relative folder under the managed root; empty = whole tree. "
        "Typical value: '01_Trivia/Web App/00_Builder'.",
    )
    delete_missing: bool = Field(
        default=False,
        description="When true, delete target-side files that no longer exist on source.",
    )


def _build_service(opts: SyncOptions) -> SyncService:
    return SyncService(
        remote_service=_remote_service(),
        local_root=_local_root(),
        sync_root_rel=opts.sync_root,
        db=_db,
        delete_on_pull=opts.delete_missing,
        delete_on_push=opts.delete_missing,
    )


# ----- Status -----
@router.get("/status")
async def sync_status() -> Dict[str, Any]:
    """Availability + last pull/push summaries. Always free."""
    sub = get_subscription()
    native_mode = os.environ.get("BIGHAT_NATIVE_MODE", "0") in ("1", "true", "True", "yes")
    cloud_available = can_use_cloud()
    cloud_sync_enabled = bool(sub.get("active") and sub.get("cloud_sync_enabled"))
    fixture = os.environ.get("BIGHAT_SYNC_REMOTE_FIXTURE", "").strip() or None

    state = await get_sync_state(_db)
    return {
        "native_mode": native_mode,
        "subscription": sub,
        "cloud_available": cloud_available,
        "cloud_sync_enabled": cloud_sync_enabled,
        "available": (not native_mode) or cloud_sync_enabled,
        "remote_mode": (
            "fixture" if fixture else ("sharepoint" if cloud_available else "disabled")
        ),
        "remote_fixture": fixture,
        "local_root": str(_local_root()),
        "last_pull": state.get("last_pull"),
        "last_push": state.get("last_push"),
    }


# ----- Plan (dry run) -----
@router.post(
    "/plan",
    dependencies=[Depends(require_native_premium("cloud_sync_enabled"))],
)
async def sync_plan(body: Optional[SyncOptions] = None) -> Dict[str, Any]:
    opts = body or SyncOptions()
    svc = _build_service(opts)
    try:
        pull_plan = svc.plan("pull").as_dict()
        push_plan = svc.plan("push").as_dict()
    except Exception as e:
        logger.error(f"[SYNC] plan failed: {e}")
        raise HTTPException(status_code=500, detail=f"sync plan failed: {e}")
    return {"sync_root": opts.sync_root, "pull": pull_plan, "push": push_plan}


# ----- Pull (cloud → local) -----
@router.post(
    "/pull",
    dependencies=[Depends(require_native_premium("cloud_sync_enabled"))],
)
async def sync_pull(body: Optional[SyncOptions] = None) -> Dict[str, Any]:
    opts = body or SyncOptions()
    svc = _build_service(opts)
    try:
        result = svc.pull()
    except Exception as e:
        logger.error(f"[SYNC] pull failed: {e}")
        raise HTTPException(status_code=500, detail=f"sync pull failed: {e}")
    await record_sync_run(_db, "pull", result)
    result["sync_root"] = opts.sync_root
    return result


# ----- Push (local → cloud) -----
@router.post(
    "/push",
    dependencies=[Depends(require_native_premium("cloud_sync_enabled"))],
)
async def sync_push(body: Optional[SyncOptions] = None) -> Dict[str, Any]:
    opts = body or SyncOptions()
    svc = _build_service(opts)
    try:
        result = svc.push()
    except Exception as e:
        logger.error(f"[SYNC] push failed: {e}")
        raise HTTPException(status_code=500, detail=f"sync push failed: {e}")
    await record_sync_run(_db, "push", result)
    result["sync_root"] = opts.sync_root
    return result
