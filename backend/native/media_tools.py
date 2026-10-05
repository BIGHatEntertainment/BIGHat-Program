"""alpha.76: where to find ffmpeg.

The desktop app is installed on a normal Windows PC, which has no ffmpeg. The `imageio-ffmpeg` package carries
its own copy inside the app, so we use that. A system ffmpeg (a server, or a developer PC) is used first if present.
"""
import logging
import os
import shutil
import subprocess
import sys
from typing import Optional

logger = logging.getLogger("bighat-media")
_cache: dict = {}


def ffmpeg_path() -> str:
    """Full path to a working ffmpeg, or the plain name 'ffmpeg' if none was found (so the error names it)."""
    if "ffmpeg" in _cache:
        return _cache["ffmpeg"]
    # BIGHAT_IGNORE_SYSTEM_FFMPEG=1 acts like a PC with no ffmpeg installed (used by the tests)
    system = None if os.environ.get("BIGHAT_IGNORE_SYSTEM_FFMPEG") == "1" else shutil.which("ffmpeg")
    found: Optional[str] = os.environ.get("BIGHAT_FFMPEG") or system
    if not found:
        try:
            import imageio_ffmpeg
            found = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception as e:                                 # noqa: BLE001
            logger.warning("bundled ffmpeg not available: %s", e)
    if found and not os.path.isfile(found):
        found = shutil.which(found)
    _cache["ffmpeg"] = found or "ffmpeg"
    return _cache["ffmpeg"]


def ffmpeg_ok() -> bool:
    try:
        r = subprocess.run([ffmpeg_path(), "-version"], capture_output=True, timeout=10, **_hidden())
        return r.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _hidden() -> dict:
    """On Windows, do not flash a black console window for every ffmpeg call."""
    if sys.platform == "win32":
        return {"creationflags": 0x08000000}                  # CREATE_NO_WINDOW
    return {}


def run(cmd, **kw):
    """subprocess.run, but a leading 'ffmpeg' / 'ffprobe' is swapped for the real program, with no console flash on Windows."""
    cmd = list(cmd)
    if cmd and cmd[0] == "ffmpeg":
        cmd[0] = ffmpeg_path()
    kw = {**_hidden(), **kw}
    return subprocess.run(cmd, **kw)


def probe_size(path: str):
    """(width, height) of the first video stream, or None. Uses ffmpeg itself because ffprobe is not bundled."""
    import re
    try:
        r = subprocess.run([ffmpeg_path(), "-hide_banner", "-i", str(path)], capture_output=True, text=True, timeout=15, **_hidden())
    except (OSError, subprocess.SubprocessError):
        return None
    m = re.search(r"Stream #\d+:\d+.*?Video:.*?,\s*(\d{2,5})x(\d{2,5})", r.stderr or "")
    return (int(m.group(1)), int(m.group(2))) if m else None
