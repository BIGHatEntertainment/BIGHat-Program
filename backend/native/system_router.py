"""alpha.78: two things a web page inside the desktop app cannot do by itself.

  POST /api/native/system/open-url       open a bighat.live link in the PC's default browser
  POST /api/native/system/save-download  save a file the app generated into the user's Downloads folder

The desktop window blocks window.open() and <a download>, so the page asks this backend (which runs on the PC) to do it.
"""
import logging
import os
import platform
import re
import subprocess
import sys
import webbrowser
from pathlib import Path
from typing import Any, Dict
from urllib.parse import urlparse

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

logger = logging.getLogger("bighat-native-system")
router = APIRouter(prefix="/api/native/system", tags=["native-system"])

# Where each "Buy" button sends the customer: the real software store pages on bighat.live (checked 2026-10-05).
# Story Generator, Scoreboard, Round creator etc. come WITH the main program, so they use the program's page.
# Change a link WITHOUT a new release by creating  <AppData>/store_links.json  like:
#   {"karaoke": "https://www.bighat.live/...", "standalone": "https://www.bighat.live/..."}
STORE_PAGE = "https://www.bighat.live/bh-franchise"
STORE_DEFAULTS = {
    "default": STORE_PAGE,                                                   # all software downloads / purchases
    "standalone": f"{STORE_PAGE}/p/big-hat-entertainment",                   # BIG Hat Entertainment (Windows/Mac) $49.99
    "karaoke": f"{STORE_PAGE}/p/bingo-player-add-on-tn5sg",                  # Karaoke Player Add-on $24.99 (yes, the address says "bingo")
    "bingo": f"{STORE_PAGE}/p/bingo-player-add-on",                          # Bingo Player Add-on $24.99
    "story": f"{STORE_PAGE}/p/big-hat-entertainment",                        # part of the main program
    "trivia": f"{STORE_PAGE}/p/big-hat-entertainment",
}

ALLOWED_HOSTS = ("bighat.live",)              # + any subdomain, e.g. www.bighat.live, api.bighat.live
MAX_DOWNLOAD_BYTES = 1024 * 1024 * 1024        # 1 GB
_BAD_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')
_WINDOWS_RESERVED = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}


def is_allowed_url(url: str) -> bool:
    try:
        u = urlparse(str(url).strip())
    except ValueError:
        return False
    host = (u.hostname or "").lower()
    return u.scheme == "https" and any(host == h or host.endswith("." + h) for h in ALLOWED_HOSTS) and not u.username


def downloads_dir() -> Path:
    """The user's Downloads folder. BIGHAT_DOWNLOADS_DIR overrides it (tests)."""
    env = os.environ.get("BIGHAT_DOWNLOADS_DIR")
    if env:
        return Path(env)
    return Path.home() / "Downloads"


def safe_filename(name: str, fallback: str = "download") -> str:
    base = _BAD_CHARS.sub("", os.path.basename((name or "").replace("\\", "/"))).strip(" .")
    if not base:
        base = fallback
    stem, dot, ext = base.rpartition(".")
    if not dot:
        stem, ext = base, ""
    if stem.lower() in _WINDOWS_RESERVED:
        stem = "_" + stem
    stem = stem[:120] or fallback
    return f"{stem}.{ext[:10]}" if ext else stem


def unique_path(folder: Path, filename: str) -> Path:
    p = folder / filename
    if not p.exists():
        return p
    stem, dot, ext = filename.rpartition(".")
    if not dot:
        stem, ext = filename, ""
    n = 2
    while True:
        cand = folder / (f"{stem} ({n}).{ext}" if ext else f"{stem} ({n})")
        if not cand.exists():
            return cand
        n += 1


def _show_in_folder(path: Path) -> bool:
    """Open the file manager with the file selected. Best effort, never raises."""
    try:
        system = platform.system()
        if system == "Windows":
            subprocess.Popen(["explorer", "/select,", str(path)])
        elif system == "Darwin":
            subprocess.Popen(["open", "-R", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path.parent)])
        return True
    except (OSError, ValueError):
        return False


def store_links() -> Dict[str, str]:
    """Defaults, overridden by <AppData>/store_links.json.  A bad or non-bighat.live entry is ignored."""
    links = dict(STORE_DEFAULTS)
    try:
        from native import data_map
        f = data_map.appdata_root() / "store_links.json"
        if f.is_file():
            import json
            for k, v in (json.loads(f.read_text("utf-8-sig")) or {}).items():
                if isinstance(v, str) and is_allowed_url(v):
                    links[str(k)] = v
    except Exception as e:                                        # noqa: BLE001
        logger.warning("store_links.json ignored: %s", e)
    return links


@router.get("/store-links")
async def get_store_links() -> Dict[str, str]:
    return store_links()


@router.post("/open-url")
async def open_url(payload: Dict[str, Any]) -> Dict[str, Any]:
    url = str(payload.get("url") or "")
    if not is_allowed_url(url):
        raise HTTPException(status_code=400, detail="Only https://bighat.live links can be opened")
    if os.environ.get("BIGHAT_NO_BROWSER") == "1":                 # tests: do not really launch a browser
        return {"ok": True, "opened": url, "simulated": True}
    try:
        ok = webbrowser.open(url, new=2)
    except Exception as e:                                        # noqa: BLE001
        logger.warning("could not open %s: %s", url, e)
        ok = False
    return {"ok": bool(ok), "opened": url}


@router.post("/save-download")
async def save_download(file: UploadFile = File(...), filename: str = Form(""), reveal: str = Form("1")) -> Dict[str, Any]:
    """Save a file into Downloads and (by default) show it in the file manager."""
    name = safe_filename(filename or file.filename or "")
    folder = downloads_dir()
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Could not use the Downloads folder: {e}")
    dest = unique_path(folder, name)
    tmp = dest.with_name(dest.name + ".part")
    total = 0
    try:
        with open(tmp, "wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_DOWNLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="File is larger than 1 GB")
                out.write(chunk)
        if total == 0:
            raise HTTPException(status_code=400, detail="The file is empty")
        os.replace(tmp, dest)
    except HTTPException:
        tmp.unlink(missing_ok=True)
        raise
    except OSError as e:
        tmp.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Could not save the file: {e}")
    shown = False
    if reveal != "0" and os.environ.get("BIGHAT_NO_BROWSER") != "1":
        shown = _show_in_folder(dest)
    return {"ok": True, "path": str(dest), "filename": dest.name, "folder": str(folder), "size": total, "shown": shown}
