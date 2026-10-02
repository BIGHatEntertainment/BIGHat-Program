"""alpha.67: Bingo Setup routes - main folder, theme toggles, songs, video streaming.
No SharePoint. Everything comes from the folder the user picked (native/bingo_library.py)."""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Dict, Optional

from fastapi import APIRouter, HTTPException, Request, UploadFile, File
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

from native import bingo_library as bl
from native import winner_videos as wv

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/bingo", tags=["bingo-setup"])


class SetupBody(BaseModel):
    main_folder: str = ""
    themes: Dict[str, dict] = {}          # { "<folder name>": {"enabled": true} }


@router.get("/setup")
async def get_setup():
    """Saved settings + what the folder currently contains."""
    s = bl.load_settings()
    res = bl.scan(s["main_folder"]) if s["main_folder"] else {"ok": False, "error": "no_folder", "themes": []}
    return {"main_folder": s["main_folder"], "ok": res["ok"], "error": res["error"], "themes": res["themes"]}


@router.post("/setup")
async def save_setup(body: SetupBody):
    folder = (body.main_folder or "").strip().strip('"')
    if folder and not Path(folder).is_dir():
        raise HTTPException(status_code=400, detail="folder_not_found")
    bl.save_settings(folder, body.themes)
    return await get_setup()


@router.post("/setup/scan")
async def scan_folder(body: SetupBody):
    """Preview a folder BEFORE saving it (used by the Browse button)."""
    folder = (body.main_folder or "").strip().strip('"')
    res = bl.scan(folder)
    return {"main_folder": folder, "ok": res["ok"], "error": res["error"], "themes": res["themes"]}


@router.get("/available-themes")
async def available_themes():
    """The tiles on the Music Bingo step: ready AND switched on in Bingo Setup."""
    s = bl.load_settings()
    return {"success": True, "configured": bool(s["main_folder"]), "themes": bl.available_themes()}


@router.get("/theme-songs/{theme}")
async def theme_songs(theme: str):
    res = bl.theme_songs(theme)
    if res is None:
        raise HTTPException(status_code=404, detail="theme_not_found")
    if res.get("error"):
        raise HTTPException(status_code=404, detail=res["error"])
    return {"success": True, **res}


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


@router.api_route("/media/{theme}/{number}", methods=["GET", "HEAD"])
async def stream_video(theme: str, number: int, request: Request):
    """Stream one song's video from the saved folder (supports seeking / Range)."""
    path = bl.video_path(theme, number)
    if path is None or not path.is_file():
        raise HTTPException(status_code=404, detail="video_not_found")
    size = path.stat().st_size
    mime = bl.MIME.get(path.suffix.lower(), "application/octet-stream")
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


# ---- alpha.69: winner videos (kept in app data so they never get lost) ----------
def _stream_file(path: Path, request: Request):
    size = path.stat().st_size
    mime = wv.MIME.get(path.suffix.lower(), "application/octet-stream")
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


@router.api_route("/winner-video/{theme:path}", methods=["GET", "HEAD"])
async def winner_video(theme: str, request: Request):
    """The winner video for a theme (or the generic one). Streams with Range."""
    path = wv.find(theme)
    if path is None or not path.is_file():
        raise HTTPException(status_code=404, detail="winner_video_not_found")
    return _stream_file(path, request)


@router.get("/winner-videos")
async def list_winner_videos():
    return {"folder": str(wv.user_dir()), "videos": wv.listing()}


@router.post("/winner-videos")
async def add_winner_videos(files: list[UploadFile] = File(...)):
    saved, rejected = [], []
    for f in files:
        try:
            wv.save_upload_file(f.filename or "", f.file)
            saved.append(Path(f.filename).name)
        except ValueError as e:
            rejected.append({"name": f.filename, "reason": str(e)})
        except OSError:
            rejected.append({"name": f.filename, "reason": "could_not_save"})
    return {"saved": saved, "rejected": rejected, "folder": str(wv.user_dir()), "videos": wv.listing()}


@router.delete("/winner-videos/{name}")
async def delete_winner_video(name: str):
    target = wv.user_dir() / Path(name).name
    if not target.is_file() or target.suffix.lower() not in wv.EXTS:
        raise HTTPException(status_code=404, detail="not_found")
    target.unlink()
    return {"deleted": target.name, "videos": wv.listing()}


# ---- the two routes the existing Lobby + Host pages already call --------------
# Registered BEFORE routes/bingo.py, so these win. Theme ids are folder names.
@router.get("/available-decades")
async def available_decades_compat():
    themes = bl.available_themes()
    return {"success": True, "source": "local-folder",
            "decades": [{"id": t["id"], "name": t["name"], "subtitle": f'{t["videos"]} songs'} for t in themes]}


@router.get("/songlist/{decade}")
async def songlist_compat(decade: str):
    res = bl.theme_songs(decade)
    if res is None or res.get("error"):
        raise HTTPException(status_code=404, detail=(res or {}).get("error") or "theme_not_found")
    return {"success": True, "decade": decade, "source": "local-folder",
            "songs": [{"number": s["number"], "title": s["title"], "artist": s["artist"], "has_video": s["has_video"]} for s in res["songs"]]}
