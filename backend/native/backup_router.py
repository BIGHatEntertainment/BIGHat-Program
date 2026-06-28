"""
/api/native/backup/* — manual trigger + listing for the daily backup
zip. Auto-run on startup is wired separately in `server.py` lifespan.

Auth model:
  • master_admin: full access (trigger backup, list, view path)
  • admin:        no access (these are install-wide secrets)
  • host:         no access
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request

from .backup_service import (
    default_backups_dir, default_source_dir,
    is_running, list_backups, run_backup,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/native/backup", tags=["native-backup"])

_user_resolver = None


def set_current_user_resolver(resolver) -> None:
    global _user_resolver
    _user_resolver = resolver


async def _default_resolver(request: Request) -> Dict[str, Any]:
    try:
        from server import get_current_user  # type: ignore
    except ImportError as e:  # pragma: no cover
        logger.error("backup_router: get_current_user not importable: %s", e)
        raise HTTPException(500, detail="auth_unavailable")
    return await get_current_user(request)


async def _require_master(request: Request) -> Dict[str, Any]:
    resolver = _user_resolver or _default_resolver
    user = await resolver(request)
    if (user or {}).get("role") != "master_admin":
        raise HTTPException(403, detail="master_admin_required")
    return user


@router.get("/status")
async def status(request: Request) -> Dict[str, Any]:
    """Where backups land + a snapshot of what's on disk."""
    await _require_master(request)
    return {
        "running": is_running(),
        "destination": str(default_backups_dir()),
        "source": str(default_source_dir()),
        "backups": list_backups(),
    }


@router.post("/run")
async def trigger(request: Request) -> Dict[str, Any]:
    """Run a backup synchronously and return the result. We run in a
    thread executor so the (potentially seconds-long) zip work doesn't
    block the event loop or starve other requests.
    """
    await _require_master(request)
    if is_running():
        # The startup auto-backup may still be working; surface that
        # cleanly so the UI doesn't double-fire.
        raise HTTPException(409, detail="backup_already_running")
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, run_backup)
    return result.to_dict()
