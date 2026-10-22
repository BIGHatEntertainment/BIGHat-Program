"""Admin > Integrations > BIG Hat Cloud. Mounted under /api/native/system/cloud-link/*.

Only the code, the link state and timestamps leave the backend. The access key never does.
"""
from __future__ import annotations

from fastapi import APIRouter

from . import cloud_link

router = APIRouter(prefix="/cloud-link", tags=["cloud-link"])


@router.get("/status")
def status():
    return cloud_link.public_view()


@router.post("/check")
async def check():
    return await cloud_link.check()


# ---- Phase 3: ongoing pull from the Cloud (native/cloud_sync.py) ----
from . import cloud_sync  # noqa: E402


def _db():
    from .db_factory import get_db
    return get_db()


@router.get("/sync-status")
def sync_status():
    return cloud_sync.public_status()


@router.post("/sync-now")
async def sync_now():
    return await cloud_sync.pull_once(_db())


@router.post("/sync-approve")
async def sync_approve():
    """The host reviewed the first-link preview: apply the Cloud data (a backup is written first)."""
    return await cloud_sync.pull_once(_db(), approve_first_link=True)


@router.post("/new-logins")
def new_logins():
    """Temporary passwords for people the sync just created. Shown once, then forgotten."""
    return {"logins": cloud_sync.take_new_logins()}
