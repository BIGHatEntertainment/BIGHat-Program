"""alpha.70: Karaoke Setup routes - folders, master overlay, venue logos, filler music, YouTube key.
Everything comes from folders on this PC (native/karaoke_library.py). No SharePoint."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, UploadFile, File
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

from native import karaoke_library as kl

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/karaoke", tags=["karaoke-setup"])

MAX_IMAGE = 15 * 1024 * 1024


class SettingsBody(BaseModel):
    filler_folder: Optional[str] = None
    youtube_api_key: Optional[str] = None


def _range(header: Optional[str], size: int):
    if not header or not header.startswith("bytes="):
        return None
    try:
        a, _, b = header[6:].split(",")[0].partition("-")
        start = int(a) if a else max(size - int(b), 0)
        end = int(b) if (a and b) else size - 1
    except ValueError:
        return None
    end = min(end, size - 1)
    return (start, end) if 0 <= start <= end else None


def _stream(path: Path, request: Request, mime: str):
    size = path.stat().st_size
    base = {"Accept-Ranges": "bytes", "Content-Type": mime, "Cache-Control": "no-store"}
    if request.method == "HEAD":
        return Response(status_code=200, headers={**base, "Content-Length": str(size)})
    rng = _range(request.headers.get("range"), size)
    start, end = rng if rng else (0, size - 1)
    if request.headers.get("range") and not rng:
        return Response(status_code=416, headers={"Content-Range": f"bytes */{size}"})

    def chunks():
        with open(path, "rb") as fh:
            fh.seek(start)
            left = end - start + 1
            while left > 0:
                data = fh.read(min(1024 * 1024, left))
                if not data:
                    break
                left -= len(data)
                yield data

    headers = {**base, "Content-Length": str(end - start + 1)}
    if rng:
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"
    return StreamingResponse(chunks(), status_code=206 if rng else 200, headers=headers)


def _state():
    s = kl.load_settings()
    key = kl.youtube_key()
    return {
        "folders": kl.ensure_folders(),
        "filler_folder": s["filler_folder"],
        "filler": kl.filler_status(s["filler_folder"]),
        "youtube_key_set": bool(key),
        "youtube_key_hint": kl.mask(key),
        "overlay": {"custom": kl.overlay_is_custom(), "size": list(kl.OVERLAY_SIZE), "windows": kl.WINDOWS,
                    "logo_slot": list(kl.LOGO_SLOT)},
    }


@router.get("/setup")
async def get_setup():
    return _state()


@router.post("/setup")
async def save_setup(body: SettingsBody):
    kl.save_settings(filler_folder=body.filler_folder, youtube_api_key=body.youtube_api_key)
    return _state()


@router.post("/setup/filler-scan")
async def scan_filler(body: SettingsBody):
    """Check a folder without saving it (the Check button)."""
    return kl.filler_status(body.filler_folder or "")


# ---- master overlay ---------------------------------------------------------------------------
@router.api_route("/overlay/master", methods=["GET", "HEAD"])
async def master_overlay(request: Request):
    p = kl.overlay_path()
    if not p.is_file():
        raise HTTPException(404, "overlay_not_found")
    mime = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}.get(p.suffix.lower(), "image/png")
    return Response(content=p.read_bytes(), media_type=mime, headers={"Cache-Control": "no-store"})


@router.post("/overlay/master")
async def upload_master_overlay(file: UploadFile = File(...)):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in kl.IMAGE_EXTS:
        raise HTTPException(400, "bad_type")
    data = await file.read()
    if len(data) > MAX_IMAGE:
        raise HTTPException(413, "too_big")
    res = kl.check_overlay(data)
    if not res["ok"]:
        return {"saved": False, **res}
    kl.save_overlay(data, ext)
    return {"saved": True, **res, "overlay": _state()["overlay"]}


@router.delete("/overlay/master")
async def reset_master_overlay():
    kl.reset_overlay()
    return {"reset": True, "overlay": _state()["overlay"]}


# ---- venue logos ------------------------------------------------------------------------------
@router.api_route("/venue-logo/{location:path}", methods=["GET", "HEAD"])
async def venue_logo(location: str, request: Request):
    p = kl.logo_path(location)
    if p is None:
        raise HTTPException(404, "logo_not_found")
    mime = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}.get(p.suffix.lower(), "image/png")
    return Response(content=p.read_bytes(), media_type=mime, headers={"Cache-Control": "no-store"})


@router.post("/venue-logo/{location:path}")
async def upload_venue_logo(location: str, file: UploadFile = File(...)):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in kl.IMAGE_EXTS or not kl.logo_key(location):
        raise HTTPException(400, "bad_type")
    data = await file.read()
    if len(data) > MAX_IMAGE:
        raise HTTPException(413, "too_big")
    res = kl.check_logo(data)
    if not res["ok"]:
        return {"saved": False, **res}
    kl.save_logo(location, data, ext)
    return {"saved": True, **res}


@router.delete("/venue-logo/{location:path}")
async def remove_venue_logo(location: str):
    if not kl.delete_logo(location):
        raise HTTPException(404, "logo_not_found")
    return {"deleted": True}


# ---- filler music -----------------------------------------------------------------------------
@router.get("/filler/folders")
async def filler_folders():
    s = kl.load_settings()
    return kl.filler_status(s["filler_folder"])


@router.get("/filler/tracks")
async def filler_tracks(folder: str = ""):
    rows = kl.tracks_for(folder)
    if rows is None:
        raise HTTPException(404, "filler_folder_unavailable")
    return {"folder": folder, "tracks": rows}


@router.api_route("/filler/play/{track:path}", methods=["GET", "HEAD"])
async def filler_play(track: str, request: Request):
    p = kl.track_path(track)
    if p is None:
        raise HTTPException(404, "track_not_found")
    return _stream(p, request, kl.AUDIO_MIME.get(p.suffix.lower(), "application/octet-stream"))
