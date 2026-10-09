"""alpha.107: Karaoke video fetcher, rebuilt from scratch on yt-dlp.

The audience screen plays every song as a plain video file that THIS module downloads with yt-dlp, so YouTube's embed
rules never apply. Paths are unchanged (mounted inside routes/karaoke.py, so they start with /karaoke):
    GET  /stream/{id}            the video file (HTTP Range supported)
    POST /stream/prepare/{id}    start downloading in the background (next singer)
    GET  /stream/status/{id}     {ready, downloading, error, detail}
    GET  /stream/diagnose        what this PC can do (ffmpeg, yt-dlp version, cookies) - open it in a browser to debug
    POST /stream/update-ytdlp    upgrade yt-dlp in place (YouTube changes break old versions)

What makes it robust (each one fixed a real failure on the way here):
  * No console needed: the installed Windows app has none, and yt-dlp's progress output used to crash with [Errno 22].
  * Uses the program's own ffmpeg (native.media_tools), because a normal PC has none installed.
  * Several download "recipes" are tried in turn (different YouTube clients and formats). One blocked stream no longer ends it.
  * If YouTube asks "sign in to confirm you're not a bot", it retries with the browser's cookies (Edge, Chrome, Firefox, Brave).
  * Every failure is turned into a short plain-English reason that the TV and the host can show.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

logger = logging.getLogger("karaoke.stream")
router = APIRouter()

STREAM_DIR = Path(os.environ.get("KARAOKE_CACHE_DIR") or (Path(tempfile.gettempdir()) / "bighat_karaoke_cache"))
STREAM_MAX_FILES = 30
MIN_FILE_BYTES = 50_000
VIDEO_EXTS = (".mp4", ".m4v", ".webm", ".mkv")
_VID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
BROWSERS = ("edge", "chrome", "firefox", "brave")

_tasks: Dict[str, "asyncio.Future"] = {}
_errors: Dict[str, Tuple[str, str]] = {}            # video_id -> (short reason, technical detail)
_good_recipe: Dict[str, str] = {}                   # remembers what worked last: "recipe" and "cookies"
_last_ok: float = 0.0


# --------------------------------------------------------------------------------------------- files
def _cached_file(video_id: str) -> Optional[Path]:
    try:
        if not STREAM_DIR.exists():
            return None
        for p in STREAM_DIR.glob(f"{video_id}.*"):
            if p.suffix in VIDEO_EXTS and p.stat().st_size > MIN_FILE_BYTES:
                return p
    except OSError:
        pass
    return None


def _clean_partials(video_id: str) -> None:
    """Remove half-finished files from a failed try so the next recipe starts clean."""
    try:
        for p in STREAM_DIR.glob(f"{video_id}*"):
            if p.suffix in (".part", ".ytdl", ".temp") or ".f" in p.stem[11:] or p.stat().st_size <= MIN_FILE_BYTES:
                p.unlink(missing_ok=True)
    except OSError:
        pass


def _prune_cache() -> None:
    try:
        files = sorted([p for p in STREAM_DIR.iterdir() if p.is_file()], key=lambda p: p.stat().st_mtime)
        for p in files[:-STREAM_MAX_FILES]:
            p.unlink(missing_ok=True)
    except OSError:
        pass


# --------------------------------------------------------------------------------------------- tools
def _ffmpeg_path() -> Optional[str]:
    """The program's own finder: system ffmpeg if present, else the copy bundled inside imageio-ffmpeg."""
    try:
        from native import media_tools
        p = media_tools.ffmpeg_path()
        if p and os.path.isfile(p):
            return p
    except Exception as e:  # noqa: BLE001
        logger.warning("media_tools ffmpeg lookup failed: %s", e)
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as e:  # noqa: BLE001
        logger.warning("bundled ffmpeg not available: %s", e)
    import shutil
    return shutil.which("ffmpeg")


def _js_runtime() -> Optional[str]:
    """YouTube needs a JavaScript runtime for some videos. Use one if the PC has it (deno or node)."""
    import shutil
    for name in ("deno", "node"):
        if shutil.which(name):
            return name
    return None


class _SilentLog:
    """yt-dlp logger that never touches the console (a windowed Windows app has a broken stdout/stderr)."""
    def __init__(self):
        self.lines: List[str] = []

    def debug(self, msg):
        pass

    def info(self, msg):
        pass

    def warning(self, msg):
        self.lines.append(str(msg))

    def error(self, msg):
        self.lines.append(str(msg))


# --------------------------------------------------------------------------------------------- error words
def explain(text: str) -> Tuple[str, str]:
    """(short reason code, plain-English sentence) for a yt-dlp failure."""
    t = (text or "").lower()
    if "sign in to confirm" in t or "not a bot" in t or "cookies" in t and "sign in" in t:
        return "signin", "YouTube wants a sign-in before it will hand over this video."
    if "ffmpeg" in t and ("not installed" in t or "not found" in t or "no such file" in t):
        return "ffmpeg", "The video tool ffmpeg is missing from this install."
    if "private video" in t or "this video is private" in t:
        return "private", "This video is private."
    if "unavailable" in t or "has been removed" in t or "no longer available" in t:
        return "unavailable", "This video is not available any more."
    if "not available in your country" in t or "blocked it in your country" in t or "geo" in t:
        return "region", "This video is blocked in this country."
    if "age" in t and ("confirm" in t or "restrict" in t):
        return "age", "This video is age-restricted."
    if "403" in t or "forbidden" in t:
        return "blocked", "YouTube refused the download (403)."
    if "429" in t or "too many requests" in t:
        return "ratelimit", "YouTube is limiting downloads from this connection. Wait a few minutes."
    if any(k in t for k in ("getaddrinfo", "name or service", "network is unreachable", "timed out", "timeout", "connection", "urlopen")):
        return "network", "No internet connection to YouTube."
    if "errno 22" in t or "invalid argument" in t:
        return "console", "The app's console is broken (Errno 22)."
    if "empty" in t:
        return "empty", "YouTube returned an empty file."
    return "unknown", "The song could not be downloaded."


# --------------------------------------------------------------------------------------------- recipes
def _recipes() -> List[Tuple[str, dict]]:
    """Ways to ask for a video, best first. Each is a name plus yt-dlp options. The last one that worked is tried first."""
    fmt_best = "bv*[height<=720][vcodec^=avc1]+ba[ext=m4a]/bv*[height<=720]+ba/b[height<=720]/b"
    fmt_any = "bv*[height<=480]+ba/b[height<=480]/bv*+ba/b"
    recipes = [
        ("default", {"format": fmt_best}),
        ("tv", {"format": fmt_any, "extractor_args": {"youtube": {"player_client": ["tv"]}}}),
        ("mweb", {"format": fmt_any, "extractor_args": {"youtube": {"player_client": ["mweb"]}}}),
        ("ios", {"format": fmt_any, "extractor_args": {"youtube": {"player_client": ["ios"]}}}),
        ("android_vr", {"format": fmt_any, "extractor_args": {"youtube": {"player_client": ["android_vr"]}}}),
        ("web_safari", {"format": fmt_any, "extractor_args": {"youtube": {"player_client": ["web_safari"]}}}),
        ("hls", {"format": "b/bv*+ba", "extractor_args": {"youtube": {"skip": ["dash"]}}}),
    ]
    good = _good_recipe.get("recipe")
    recipes.sort(key=lambda r: 0 if r[0] == good else 1)
    return recipes


def _base_opts(video_id: str, log: _SilentLog) -> dict:
    opts = {
        "quiet": True, "no_warnings": True, "noplaylist": True, "logger": log,
        "noprogress": True, "consoletitle": False, "color": "never",
        "outtmpl": str(STREAM_DIR / f"{video_id}.%(ext)s"),
        "merge_output_format": "mp4", "overwrites": False,
        "retries": 3, "fragment_retries": 3, "socket_timeout": 20,
        "concurrent_fragment_downloads": 4,
    }
    ff = _ffmpeg_path()
    if ff:
        opts["ffmpeg_location"] = ff
    rt = _js_runtime()
    if rt:
        opts["js_runtimes"] = {rt: {}}
    return opts


def _try_download(video_id: str, recipe_opts: dict, cookies: Optional[str]) -> Tuple[bool, str]:
    """One attempt. Returns (ok, error text)."""
    import yt_dlp
    log = _SilentLog()
    opts = {**_base_opts(video_id, log), **recipe_opts}
    if cookies:
        opts["cookiesfrombrowser"] = (cookies,)
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([f"https://www.youtube.com/watch?v={video_id}"])
        return (_cached_file(video_id) is not None), ("" if _cached_file(video_id) else "empty file")
    except BaseException as e:  # noqa: BLE001  (yt-dlp raises SystemExit-like errors too)
        detail = " ".join([str(e)] + log.lines[-3:])
        return False, detail


def _usable_browsers() -> List[str]:
    """Browsers on this PC whose saved sign-in yt-dlp can actually read. Probing is cheap (no network)."""
    found: List[str] = []
    try:
        from yt_dlp.cookies import extract_cookies_from_browser
    except Exception:  # noqa: BLE001
        return found
    for b in BROWSERS:
        try:
            jar = extract_cookies_from_browser(b)
            if any("youtube" in (c.domain or "") or "google" in (c.domain or "") for c in jar):
                found.append(b)
        except BaseException:  # noqa: BLE001  (not installed, locked, or no profile)
            continue
    return found


def _download(video_id: str) -> str:
    """Blocking. Tries recipes, then browser cookies. Returns the file path or raises RuntimeError('code|sentence|detail')."""
    global _last_ok
    STREAM_DIR.mkdir(parents=True, exist_ok=True)
    attempts: List[Tuple[str, str]] = []
    need_cookies = False
    # Round 1: no cookies, every recipe. Round 2 (only if YouTube asked for a sign-in): the same recipes with browser cookies.
    cookie_options: List[Optional[str]] = [None]
    for round_no in range(2):
        for cookies in cookie_options:
            for name, ropts in _recipes():
                ok, err = _try_download(video_id, ropts, cookies)
                label = f"{name}{'+' + cookies if cookies else ''}"
                if ok:
                    _good_recipe["recipe"] = name
                    _last_ok = time.time()
                    logger.info("[Karaoke stream] %s downloaded with %s", video_id, label)
                    return str(_cached_file(video_id))
                _clean_partials(video_id)
                attempts.append((label, err))
                code, _ = explain(err)
                if code == "signin":
                    need_cookies = True
                if code in ("private", "unavailable", "region", "age", "network", "ffmpeg"):
                    break                         # another recipe will not change this
            else:
                continue
            break
        if round_no == 0 and need_cookies:
            cookie_options = _usable_browsers()   # now try the PC's own browsers' sign-in (only ones that exist)
            if not cookie_options:
                break
            continue
        break
    # pick the most useful error to show: a sign-in problem beats a generic 403
    chosen = next((e for _, e in attempts if explain(e)[0] == "signin"), None) or (attempts[-1][1] if attempts else "")
    code, sentence = explain(chosen)
    if code == "signin":
        sentence += " Sign in to YouTube once in Edge or Chrome on this PC, then try again."
    real = [(l, e) for l, e in attempts if "cookies database" not in e and "cookie" not in e.lower()[:60]] or attempts
    detail = " | ".join(f"{l}: {e[:110]}" for l, e in real[-3:])
    raise RuntimeError(f"{code}|{sentence}|{detail}")


# --------------------------------------------------------------------------------------------- task plumbing
async def _ensure_video(video_id: str) -> Path:
    f = _cached_file(video_id)
    if f:
        f.touch()
        return f
    task = _tasks.get(video_id)
    if task is None or task.done():
        _errors.pop(video_id, None)
        task = asyncio.get_running_loop().run_in_executor(None, _download, video_id)
        _tasks[video_id] = task

        def _done(t, vid=video_id):
            try:
                t.result()
            except BaseException as e:  # noqa: BLE001
                parts = str(e).split("|", 2)
                _errors[vid] = (parts[0] if len(parts) == 3 else "unknown", str(e) if len(parts) != 3 else parts[1] + "  [" + parts[2] + "]")
                logger.error("[Karaoke stream] %s failed: %s", vid, _errors[vid][1])
            finally:
                _tasks.pop(vid, None)
                _prune_cache()
        task.add_done_callback(_done)
    try:
        await asyncio.shield(task)
    except BaseException:  # noqa: BLE001  (the done-callback already recorded why)
        pass
    f = _cached_file(video_id)
    if not f:
        raise RuntimeError(_errors.get(video_id, ("unknown", "download failed"))[1])
    return f


def _check_id(video_id: str) -> None:
    if not _VID_RE.match(video_id):
        raise HTTPException(status_code=400, detail="bad video id")


# --------------------------------------------------------------------------------------------- routes
@router.post("/stream/prepare/{video_id}")
async def stream_prepare(video_id: str):
    """Start downloading a song in the background (the NEXT singer). Returns at once."""
    _check_id(video_id)
    if _cached_file(video_id):
        return {"ready": True}
    if video_id not in _tasks:
        asyncio.create_task(_quiet(video_id))
    return {"ready": False}


async def _quiet(video_id: str):
    try:
        await _ensure_video(video_id)
    except Exception:  # noqa: BLE001
        pass


@router.get("/stream/status/{video_id}")
async def stream_status(video_id: str):
    _check_id(video_id)
    if _cached_file(video_id):
        return {"ready": True, "downloading": False, "error": "", "detail": ""}
    code, detail = _errors.get(video_id, ("", ""))
    return {"ready": False, "downloading": video_id in _tasks, "error": code, "detail": detail}


@router.get("/stream/diagnose")
async def stream_diagnose():
    """Open this address in a browser to see what the app can do on this PC."""
    ff = _ffmpeg_path()
    ff_ok = False
    if ff:
        try:
            ff_ok = subprocess.run([ff, "-version"], capture_output=True, timeout=10).returncode == 0
        except Exception:  # noqa: BLE001
            ff_ok = False
    try:
        import yt_dlp
        ver = yt_dlp.version.__version__
    except Exception as e:  # noqa: BLE001
        ver = f"NOT AVAILABLE: {e}"
    cached = sorted(p.name for p in STREAM_DIR.glob("*") if p.suffix in VIDEO_EXTS) if STREAM_DIR.exists() else []
    return {
        "yt_dlp_version": ver, "ffmpeg": ff, "ffmpeg_runs": ff_ok, "js_runtime": _js_runtime(),
        "cache_dir": str(STREAM_DIR), "cached_songs": cached, "downloading_now": sorted(_tasks),
        "last_working_recipe": _good_recipe.get("recipe"), "last_success_seconds_ago": (round(time.time() - _last_ok) if _last_ok else None),
        "recent_errors": {k: v[1][:300] for k, v in list(_errors.items())[-5:]},
        "python": sys.version.split()[0], "frozen": bool(getattr(sys, "frozen", False)),
    }


@router.post("/stream/update-ytdlp")
async def stream_update_ytdlp():
    """Upgrade yt-dlp (YouTube changes break old versions). Works when running from Python; the frozen app needs a new build."""
    if getattr(sys, "frozen", False):
        return JSONResponse(status_code=200, content={"updated": False, "reason": "This installed app has yt-dlp built in. Release a new build to update it."})
    try:
        r = await asyncio.to_thread(lambda: subprocess.run([sys.executable, "-m", "pip", "install", "-U", "yt-dlp"], capture_output=True, text=True, timeout=180))
        return {"updated": r.returncode == 0, "output": (r.stdout + r.stderr)[-400:]}
    except Exception as e:  # noqa: BLE001
        return {"updated": False, "reason": str(e)[:200]}


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
    """The song as a real video file, with HTTP Range support (206) so the <video> tag can buffer and seek."""
    _check_id(video_id)
    try:
        f = await asyncio.wait_for(_ensure_video(video_id), timeout=240)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="still downloading")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"could not fetch video: {e}")
    size = f.stat().st_size
    mt = {".mp4": "video/mp4", ".m4v": "video/mp4", ".webm": "video/webm", ".mkv": "video/x-matroska"}.get(f.suffix, "video/mp4")
    headers = {"Accept-Ranges": "bytes", "Cache-Control": "no-store"}
    m = re.match(r"bytes=(\d*)-(\d*)$", request.headers.get("range", "").strip())
    if m and (m.group(1) or m.group(2)):
        if m.group(1):
            start = int(m.group(1))
            end = int(m.group(2)) if m.group(2) else size - 1
        else:
            start, end = max(0, size - int(m.group(2))), size - 1
        end = min(end, size - 1)
        if start >= size or start > end:
            return Response(status_code=416, headers={**headers, "Content-Range": f"bytes */{size}"})
        headers.update({"Content-Range": f"bytes {start}-{end}/{size}", "Content-Length": str(end - start + 1)})
        return StreamingResponse(_iter_file(str(f), start, end), status_code=206, media_type=mt, headers=headers)
    headers["Content-Length"] = str(size)
    return StreamingResponse(_iter_file(str(f), 0, size - 1), status_code=200, media_type=mt, headers=headers)
