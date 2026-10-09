"""alpha.105: Karaoke songs play as a plain video file downloaded by yt-dlp (never through YouTube's embed).

Why: the TV is a desktop window at http://127.0.0.1. YouTube refuses to embed videos for that origin
("owner does not allow it to be played outside YouTube"), so every YT.Player / iframe build failed.
The BACKEND downloads the song with yt-dlp (same library the prototype's search uses) and the TV plays
the file in a normal <video> tag. Embedding rules do not apply.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import tempfile
from pathlib import Path
from typing import Dict

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response, StreamingResponse

logger = logging.getLogger(__name__)
router = APIRouter()      # mounted inside routes/karaoke.py, so every path starts with /karaoke

STREAM_DIR = Path(os.environ.get("KARAOKE_CACHE_DIR") or (Path(tempfile.gettempdir()) / "bighat_karaoke_cache"))
STREAM_MAX_FILES = 30
_VID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
_dl_tasks: Dict[str, "asyncio.Future"] = {}
_dl_errors: Dict[str, str] = {}


def _cached_file(video_id: str):
    if not STREAM_DIR.exists():
        return None
    for p in STREAM_DIR.glob(f"{video_id}.*"):
        if p.suffix in (".mp4", ".webm", ".m4v", ".mkv") and p.stat().st_size > 50_000:
            return p
    return None


def _prune_cache() -> None:
    try:
        files = sorted([p for p in STREAM_DIR.iterdir() if p.is_file()], key=lambda p: p.stat().st_mtime)
        for p in files[:-STREAM_MAX_FILES]:
            p.unlink(missing_ok=True)
    except Exception:
        pass


def _ffmpeg_path():
    """ffmpeg is needed to join YouTube's separate video and audio streams. Use the system one, else the bundled imageio-ffmpeg."""
    import shutil
    p = shutil.which("ffmpeg")
    if p:
        return p
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_exe()
    except Exception:
        return None


class _YtLog:
    """yt-dlp logger that never touches the console (a console-less Windows app has a broken stdout/stderr)."""
    def debug(self, msg):
        pass

    def info(self, msg):
        pass

    def warning(self, msg):
        logger.warning(f"[yt-dlp] {msg}")

    def error(self, msg):
        logger.error(f"[yt-dlp] {msg}")


def _ytdlp_download(video_id: str) -> str:
    """Blocking. Download the song as ONE mp4 (H.264 video + AAC audio, joined with ffmpeg) that any <video> tag can play."""
    import yt_dlp
    STREAM_DIR.mkdir(parents=True, exist_ok=True)
    base = {
        "quiet": True, "no_warnings": True, "noplaylist": True,
        # alpha.106: the installed Windows app has no console. yt-dlp writes progress to it and crashes with
        # [Errno 22] Invalid argument (every format then "fails"). Stay silent, and send its log to our logger.
        "noprogress": True, "consoletitle": False, "color": "never", "logger": _YtLog(),
        "outtmpl": str(STREAM_DIR / f"{video_id}.%(ext)s"),
        "retries": 5, "fragment_retries": 5, "socket_timeout": 20,
        "overwrites": False, "merge_output_format": "mp4",
    }
    ff = _ffmpeg_path()
    if ff:
        base["ffmpeg_location"] = ff
    # best first: H.264 <=720p + AAC joined; then any <=720p pair; then a single combined file; then whatever exists
    formats = [
        "bv*[ext=mp4][height<=720][vcodec^=avc1]+ba[ext=m4a]/b[ext=mp4][height<=720]",
        "bv*[height<=720]+ba/b[height<=720]",
        "18/22/b",
        "bv*+ba/best",
    ]
    last = None
    for fmt in formats:
        try:
            with yt_dlp.YoutubeDL({**base, "format": fmt}) as ydl:
                ydl.download([f"https://www.youtube.com/watch?v={video_id}"])
            f = _cached_file(video_id)
            if f:
                return str(f)
        except Exception as e:  # try the next format
            last = e
            logger.warning(f"[Karaoke stream] {video_id} format '{fmt}' failed: {e}")
    raise RuntimeError(str(last or "download produced no file")[:200])


async def _ensure_video(video_id: str):
    f = _cached_file(video_id)
    if f:
        f.touch()
        return f
    task = _dl_tasks.get(video_id)
    if task is None or task.done():
        _dl_errors.pop(video_id, None)
        loop = asyncio.get_running_loop()
        task = loop.run_in_executor(None, _ytdlp_download, video_id)
        _dl_tasks[video_id] = task

        def _done(t, vid=video_id):
            try:
                t.result()
            except Exception as e:
                _dl_errors[vid] = str(e)[:200]
            finally:
                _dl_tasks.pop(vid, None)
                _prune_cache()
        task.add_done_callback(_done)
    await asyncio.shield(task)
    f = _cached_file(video_id)
    if not f:
        raise RuntimeError(_dl_errors.get(video_id, "download failed"))
    return f


@router.post("/stream/prepare/{video_id}")
async def stream_prepare(video_id: str):
    """Start downloading a song in the background (used for the NEXT singer). Returns at once."""
    if not _VID_RE.match(video_id):
        raise HTTPException(status_code=400, detail="bad video id")
    if _cached_file(video_id):
        return {"ready": True}
    if video_id not in _dl_tasks:
        asyncio.create_task(_prepare_quiet(video_id))
    return {"ready": False}


async def _prepare_quiet(video_id: str):
    try:
        await _ensure_video(video_id)
    except Exception as e:
        logger.warning(f"[Karaoke stream] prepare {video_id} failed: {e}")


@router.get("/stream/status/{video_id}")
async def stream_status(video_id: str):
    if not _VID_RE.match(video_id):
        raise HTTPException(status_code=400, detail="bad video id")
    if _cached_file(video_id):
        return {"ready": True, "error": ""}
    return {"ready": False, "downloading": video_id in _dl_tasks, "error": _dl_errors.get(video_id, "")}


def _iter_file(path: str, start: int, end: int, chunk: int = 512 * 1024):
    with open(path, "rb") as fh:
        fh.seek(start)
        left = end - start + 1
        while left > 0:
            data = fh.read(min(chunk, left))
            if not data:
                break
            left -= len(data)
            yield data


@router.get("/stream/{video_id}")
async def stream_video(video_id: str, request: Request):
    """The song as a real video file, with HTTP Range support (206) so the <video> tag can buffer and seek.
    (Done by hand: the starlette version pinned by this program has no Range support in FileResponse.)"""
    if not _VID_RE.match(video_id):
        raise HTTPException(status_code=400, detail="bad video id")
    try:
        f = await asyncio.wait_for(_ensure_video(video_id), timeout=180)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="video is still downloading")
    except Exception as e:
        logger.error(f"[Karaoke stream] {video_id} failed: {e}")
        raise HTTPException(status_code=502, detail=f"could not fetch video: {e}")
    size = f.stat().st_size
    mt = {".mp4": "video/mp4", ".m4v": "video/mp4", ".webm": "video/webm", ".mkv": "video/x-matroska"}.get(f.suffix, "video/mp4")
    headers = {"Accept-Ranges": "bytes", "Cache-Control": "no-store"}
    rng = request.headers.get("range", "")
    m = re.match(r"bytes=(\d*)-(\d*)$", rng.strip()) if rng else None
    if m and (m.group(1) or m.group(2)):
        if m.group(1):
            start = int(m.group(1))
            end = int(m.group(2)) if m.group(2) else size - 1
        else:                                   # "bytes=-500" = the last 500 bytes
            start = max(0, size - int(m.group(2)))
            end = size - 1
        end = min(end, size - 1)
        if start >= size or start > end:
            return Response(status_code=416, headers={**headers, "Content-Range": f"bytes */{size}"})
        headers.update({"Content-Range": f"bytes {start}-{end}/{size}", "Content-Length": str(end - start + 1)})
        return StreamingResponse(_iter_file(str(f), start, end), status_code=206, media_type=mt, headers=headers)
    headers["Content-Length"] = str(size)
    return StreamingResponse(_iter_file(str(f), 0, size - 1), status_code=200, media_type=mt, headers=headers)
