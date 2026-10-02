"""alpha.70: Karaoke Setup - folders, master overlay, venue logos, filler music, settings.

Folders (created for the user, visible in Explorer):
  <Documents>/BIG Hat Entertainment/Files/Karaoke/
      Master Overlay/   the audience-screen template (default = the bundled BIG Hat one)
      Venue Logos/      one image per location, named after the location
      Song Library/     local song lists (reserved)
Settings (filler music folder, YouTube key) live in karaoke_settings.json next to the app config,
not in Documents, so the key is not sitting in a shared folder.

The master overlay is 1920x1080 with four windows the audience screen fills in. Windows are
fractions of the screen, so a replacement overlay must keep the same layout (see WINDOWS).
"""
from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp")
AUDIO_EXTS = (".mp3", ".m4a", ".wav", ".ogg", ".flac", ".aac", ".wma")
AUDIO_MIME = {".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".wav": "audio/wav", ".ogg": "audio/ogg",
              ".flac": "audio/flac", ".aac": "audio/aac", ".wma": "audio/x-ms-wma"}
OVERLAY_SIZE = (1920, 1080)
LOGO_SLOT = (249, 249)            # the logo window on the master overlay, in pixels at 1920x1080
MIN_LOGO = 145                    # the smallest logo we promise to fit (venues use 150)
BUNDLED_OVERLAY = Path(__file__).resolve().parent.parent / "assets" / "karaoke" / "master_overlay.png"

# Where the audience screen puts things (fractions of the 1920x1080 screen). Same as the prototype.
WINDOWS = {
    "video":  {"left": 7.14,  "top": 10.0,  "width": 71.82, "height": 75.93},
    "chyron": {"left": 5.12,  "top": 87.74, "width": 75.79, "height": 10.54},
    "logo":   {"left": 82.66, "top": 10.0,  "width": 12.97, "height": 23.06},
    "qr":     {"left": 82.66, "top": 62.87, "width": 12.97, "height": 23.06},
}


# ---------------------------------------------------------------- folders
def root() -> Path:
    env = os.environ.get("BIGHAT_KARAOKE_DIR")
    if env:
        return Path(env)
    try:
        from native.files_router import _docs_root
        return _docs_root() / "Files" / "Karaoke"
    except Exception:
        return Path.home() / "BIG Hat Entertainment" / "Files" / "Karaoke"


def overlay_dir() -> Path:
    return root() / "Master Overlay"


def logos_dir() -> Path:
    return root() / "Venue Logos"


def songs_dir() -> Path:
    return root() / "Song Library"


def ensure_folders() -> Dict[str, str]:
    """Create the Karaoke folders and put the default master overlay in place."""
    made: Dict[str, str] = {}
    for name, p in (("root", root()), ("overlay", overlay_dir()), ("logos", logos_dir()), ("songs", songs_dir())):
        try:
            p.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        made[name] = str(p)
    return made


# ---------------------------------------------------------------- settings
def settings_path() -> Path:
    env = os.environ.get("BIGHAT_KARAOKE_SETTINGS")
    if env:
        return Path(env)
    try:
        from native.config import DEFAULT_CONFIG_PATH
        return Path(DEFAULT_CONFIG_PATH).with_name("karaoke_settings.json")
    except Exception:
        return Path(__file__).with_name("karaoke_settings.json")


def _default() -> Dict[str, Any]:
    return {"filler_folder": "", "youtube_api_key": ""}


def load_settings() -> Dict[str, Any]:
    try:
        data = json.loads(settings_path().read_text(encoding="utf-8"))
        return {**_default(), **{k: data.get(k, v) for k, v in _default().items()}}
    except (OSError, ValueError):
        return _default()


def save_settings(**changes: Any) -> Dict[str, Any]:
    data = load_settings()
    for k, v in changes.items():
        if k in data and v is not None:
            data[k] = str(v).strip().strip('"') if isinstance(v, str) else v
    p = settings_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, p)
    return data


def youtube_key() -> str:
    """The key saved in Karaoke Setup, else the YOUTUBE_API_KEY environment variable."""
    return load_settings()["youtube_api_key"] or os.environ.get("YOUTUBE_API_KEY", "")


def mask(key: str) -> str:
    return "" if not key else (key[:4] + "..." + key[-4:] if len(key) > 10 else "set")


# ---------------------------------------------------------------- master overlay
def overlay_path() -> Path:
    """The overlay the audience screen uses: the user's upload if there is one, else the bundled one."""
    d = overlay_dir()
    try:
        if d.is_dir():
            for f in sorted(d.iterdir()):
                if f.is_file() and f.suffix.lower() in IMAGE_EXTS and not f.name.startswith("."):
                    return f
    except OSError:
        pass
    return BUNDLED_OVERLAY


def overlay_is_custom() -> bool:
    return overlay_path() != BUNDLED_OVERLAY


def check_overlay(data: bytes) -> Dict[str, Any]:
    """Is this image usable as the master overlay? Must be 1920x1080 (16:9)."""
    from PIL import Image
    import io
    try:
        im = Image.open(io.BytesIO(data))
        im.load()
    except Exception:
        return {"ok": False, "error": "not_an_image"}
    w, h = im.size
    if (w, h) != OVERLAY_SIZE:
        return {"ok": False, "error": "wrong_size", "width": w, "height": h}
    return {"ok": True, "width": w, "height": h, "format": (im.format or "").lower()}


def save_overlay(data: bytes, ext: str) -> Path:
    ensure_folders()
    d = overlay_dir()
    for old in d.iterdir():
        if old.is_file() and old.suffix.lower() in IMAGE_EXTS:
            old.unlink()
    target = d / ("master_overlay" + ext.lower())
    target.write_bytes(data)
    return target


def reset_overlay() -> None:
    d = overlay_dir()
    if d.is_dir():
        for old in d.iterdir():
            if old.is_file() and old.suffix.lower() in IMAGE_EXTS:
                old.unlink()


# ---------------------------------------------------------------- venue logos
def logo_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (name or "").lower().replace("&", "and"))


def logo_path(location: str) -> Optional[Path]:
    k = logo_key(location)
    if not k:
        return None
    d = logos_dir()
    try:
        if d.is_dir():
            for f in sorted(d.iterdir()):
                if f.is_file() and f.suffix.lower() in IMAGE_EXTS and logo_key(f.stem) == k:
                    return f
    except OSError:
        pass
    return None


def check_logo(data: bytes) -> Dict[str, Any]:
    """A venue logo must be an image at least 145x145 and roughly square (it is shown in a ~249px window)."""
    from PIL import Image
    import io
    try:
        im = Image.open(io.BytesIO(data))
        im.load()
    except Exception:
        return {"ok": False, "error": "not_an_image"}
    w, h = im.size
    if w < MIN_LOGO or h < MIN_LOGO:
        return {"ok": False, "error": "too_small", "width": w, "height": h}
    if max(w, h) / min(w, h) > 1.25:
        return {"ok": False, "error": "not_square", "width": w, "height": h}
    return {"ok": True, "width": w, "height": h}


def save_logo(location: str, data: bytes, ext: str) -> Path:
    ensure_folders()
    old = logo_path(location)
    if old:
        old.unlink()
    safe = re.sub(r'[\\/:*?"<>|]', "", location).strip() or "venue"
    target = logos_dir() / (safe + ext.lower())
    target.write_bytes(data)
    return target


def delete_logo(location: str) -> bool:
    p = logo_path(location)
    if p:
        p.unlink()
        return True
    return False


# ---------------------------------------------------------------- filler music (external drive friendly)
def filler_status(folder: str) -> Dict[str, Any]:
    """Look at the filler folder. A missing drive is reported, never raised."""
    folder = (folder or "").strip().strip('"')
    if not folder:
        return {"ok": False, "error": "no_folder", "folders": [], "tracks": 0}
    p = Path(folder)
    try:
        if not p.exists():
            return {"ok": False, "error": "drive_missing", "folders": [], "tracks": 0}
        if not p.is_dir():
            return {"ok": False, "error": "folder_not_found", "folders": [], "tracks": 0}
        subs = sorted([d for d in p.iterdir() if d.is_dir() and not d.name.startswith((".", "$", "_"))],
                      key=lambda d: d.name.lower())
    except OSError:
        return {"ok": False, "error": "folder_not_readable", "folders": [], "tracks": 0}
    out: List[Dict[str, Any]] = []
    for d in subs:
        n = len(scan_tracks(d))
        if n:
            out.append({"name": d.name, "tracks": n})
    loose = len(scan_tracks(p, recurse=False))
    return {"ok": True, "error": None, "folders": out, "loose_tracks": loose,
            "tracks": sum(f["tracks"] for f in out) + loose}


def scan_tracks(folder: Path, recurse: bool = True) -> List[Path]:
    found: List[Path] = []
    try:
        it = folder.rglob("*") if recurse else folder.iterdir()
        for f in it:
            if f.is_file() and f.suffix.lower() in AUDIO_EXTS and not f.name.startswith("."):
                found.append(f)
    except OSError:
        pass
    return sorted(found, key=lambda f: str(f).lower())


def tracks_for(folder_name: str) -> Optional[List[Dict[str, Any]]]:
    """Tracks in one sub folder of the saved filler folder (or all of them when folder_name is '')."""
    s = load_settings()
    base = Path(s["filler_folder"]) if s["filler_folder"] else None
    if not base or not base.is_dir():
        return None
    if folder_name and (re.search(r"[\\/]", folder_name) or folder_name in (".", "..")):
        return None
    target = (base / folder_name).resolve() if folder_name else base.resolve()
    if folder_name and target.parent != base.resolve():
        return None
    if not target.is_dir():
        return None
    rows = []
    for i, f in enumerate(scan_tracks(target)):
        rel = f.relative_to(base.resolve()) if str(f).startswith(str(base.resolve())) else f.name
        parts = Path(rel).parts
        artist = parts[1] if len(parts) >= 3 else (parts[0] if len(parts) == 2 else "Unknown")
        rows.append({"id": str(Path(rel).as_posix()), "name": f.name, "artist": artist})
    return rows


def track_path(rel: str) -> Optional[Path]:
    """Safe path to one filler track (no escaping the saved filler folder)."""
    s = load_settings()
    if not s["filler_folder"] or not rel:
        return None
    base = Path(s["filler_folder"]).resolve()
    try:
        p = (base / rel).resolve()
    except OSError:
        return None
    if base not in p.parents or not p.is_file() or p.suffix.lower() not in AUDIO_EXTS:
        return None
    return p
