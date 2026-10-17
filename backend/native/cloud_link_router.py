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
