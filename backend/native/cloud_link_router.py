"""Admin > Integrations > BIG Hat Cloud. Mounted under /api/native/system/cloud-link/*.

Only the code, the link state and timestamps leave the backend. The access key never does.
"""
from __future__ import annotations

from typing import List
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
from . import cloud_files  # noqa: E402


def _db():
    from .db_factory import get_db
    return get_db()


@router.get("/sync-status")
def sync_status():
    return cloud_sync.public_status()


@router.post("/sync-now")
async def sync_now():
    res = await cloud_sync.pull_once(_db())
    # v32.3.0: then the files (venue pictures, overlays, .bighat). They need the venues the line above just brought in.
    try:
        files = await cloud_files.pull_once(_db())
    except Exception as e:                                    # noqa: BLE001  the data pull's answer must never be lost
        files = {"state": "error", "message": f"File sync stopped safely ({type(e).__name__})."}
    return {**res, "files": files}


@router.get("/files-status")
def files_status():
    return cloud_files.public_status()


@router.post("/files-sync-now")
async def files_sync_now():
    return await cloud_files.pull_once(_db())


@router.post("/sync-approve")
async def sync_approve():
    """The host reviewed the first-link preview: apply the Cloud data (a backup is written first)."""
    return await cloud_sync.pull_once(_db(), approve_first_link=True)


# ---- Cloud shows (trivia show bundles built in the Cloud wizard) ----
from fastapi import File, Form, UploadFile  # noqa: E402
from . import cloud_shows  # noqa: E402


@router.get("/shows")
async def cloud_show_list():
    return await cloud_shows.list_shows()


@router.post("/shows/{plan_id}/import")
async def cloud_show_import(plan_id: str, allow_locked: bool = False):
    return await cloud_shows.pull_and_import(_db(), plan_id, allow_locked=allow_locked)


@router.post("/shows/import-files")
async def cloud_show_import_files(files: List[UploadFile] = File(...), allow_locked: bool = Form(False)):
    """ALL the part files of one show downloaded from the Cloud website, sent together."""
    blobs = [await f.read() for f in files]
    return await cloud_shows.import_parts(_db(), blobs, allow_locked=allow_locked)


@router.post("/shows/import-file")
async def cloud_show_import_file(file: UploadFile = File(...), allow_locked: bool = Form(False)):
    """A show file downloaded from the Cloud website and dropped in here."""
    data = await file.read()
    return await cloud_shows.import_bundle(_db(), data, allow_locked=allow_locked)


@router.post("/new-logins")
def new_logins():
    """Temporary passwords for people the sync just created. Shown once, then forgotten."""
    return {"logins": cloud_sync.take_new_logins()}
