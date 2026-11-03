"""v32.2.10: the Update tool downloads the installer ITSELF, so a click can never end in "success" with nothing on the PC.

Before: the green button asked the OS to open a link (webbrowser.open from the hidden background program). That call returns True when the link was HANDED OFF,
not when a browser opened or a file arrived, so the screen could say "Your browser is downloading" while nothing happened (reported 2026-11-03).

Now: the program downloads this PC's installer from this program's own GitHub release into the Downloads folder, with real progress, and only reports it done
when the file is on disk at the size the server promised.
  * the link comes from the update channel fetched HERE (never from the page) and must pass is_release_url
  * written to <name>.part and renamed only when whole; a damaged/short file is deleted, never offered
  * one download at a time: a second click joins the running one
  * state is kept in memory AND re-found on disk, so closing and reopening the program does not lose a finished download
"""
import asyncio
import logging
import os
import platform
import re
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger("bighat-installer-dl")

IDLE, RUNNING, DONE, FAILED = "idle", "running", "done", "failed"
MAX_BYTES = 1024 * 1024 * 1024                    # 1 GB
_lock = threading.Lock()
_state: Dict[str, Any] = {"state": IDLE}
_thread: Optional[threading.Thread] = None      # the download runs on its OWN thread + event loop, so it can never be cancelled by the
                                                # short-lived loop that handled the click (a download that quietly dies is the bug this fixes)


def _blank() -> Dict[str, Any]:
    return {"state": IDLE, "version": None, "filename": None, "path": None, "bytes": 0, "total": 0, "percent": 0, "error": None, "message": ""}


def snapshot() -> Dict[str, Any]:
    with _lock:
        return dict(_state) if len(_state) > 1 else _blank()


def _set(**kw: Any) -> None:
    with _lock:
        if len(_state) <= 1:
            _state.update(_blank())
        _state.update(kw)
        t = int(_state.get("total") or 0)
        _state["percent"] = int(min(100, (int(_state.get("bytes") or 0) * 100) // t)) if t else 0


def reset() -> None:
    """Tests, and 'Try again'. A running download is never interrupted by this."""
    global _thread
    with _lock:
        if _state.get("state") == RUNNING and _thread is not None and _thread.is_alive():
            return
        _state.clear(); _state["state"] = IDLE
    _thread = None


def _is_running() -> bool:
    with _lock:
        return _state.get("state") == RUNNING and _thread is not None and _thread.is_alive()


def _worker(info: Dict[str, Any]) -> None:
    """Thread body: its own event loop. Whatever happens, the state ends as done or failed, never stuck on 'running'."""
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        loop.run_until_complete(_run(info))
    except BaseException as e:                                          # noqa: BLE001
        logger.error("installer download worker crashed: %s: %s", type(e).__name__, e)
        _set(state=FAILED, error=type(e).__name__, message="The download stopped unexpectedly. Try again.")
    finally:
        with _lock:
            if _state.get("state") == RUNNING:                          # a crash must never leave the screen waiting forever
                _state["state"] = FAILED; _state["message"] = "The download stopped unexpectedly. Try again."
        try:
            loop.close()
        except Exception:                                               # noqa: BLE001
            pass


def _plain_error(e: BaseException) -> str:
    if isinstance(e, httpx.TimeoutException):
        return "The download timed out. Check your internet connection and try again."
    if isinstance(e, httpx.HTTPStatusError):
        return f"The download server answered {e.response.status_code}. Try again in a few minutes."
    if isinstance(e, (httpx.TransportError, OSError)) and not isinstance(e, PermissionError):
        return "The download was interrupted. Check your internet connection and try again."
    if isinstance(e, PermissionError):
        return "The program is not allowed to save into your Downloads folder."
    return f"The download stopped ({type(e).__name__}). Try again."


def find_finished(filename: str, total: int = 0) -> Optional[Path]:
    """A complete copy already in Downloads (same name, same size) so a second visit or a restart does not download again."""
    from .system_router import downloads_dir, safe_filename
    p = downloads_dir() / safe_filename(filename)
    try:
        if p.is_file() and p.stat().st_size > 0 and (not total or p.stat().st_size == total):
            return p
    except OSError:
        pass
    return None


async def _run(info: Dict[str, Any]) -> None:
    from .system_router import downloads_dir, safe_filename, unique_path
    url, name = info["url"], safe_filename(info.get("filename") or "")
    folder = downloads_dir()
    part: Optional[Path] = None
    try:
        folder.mkdir(parents=True, exist_ok=True)
        dest = unique_path(folder, name) if not find_finished(name, int(info.get("size") or 0)) else None
        if dest is None:                                               # already downloaded and the right size
            p = find_finished(name, int(info.get("size") or 0))
            _set(state=DONE, path=str(p), bytes=p.stat().st_size, total=p.stat().st_size, message="Already downloaded.", error=None)
            return
        part = dest.with_name(dest.name + ".part")
        got = 0
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, read=120.0), follow_redirects=True) as client:
            async with client.stream("GET", url) as r:
                r.raise_for_status()
                total = int(r.headers.get("content-length") or 0) or int(info.get("size") or 0)
                if total > MAX_BYTES:
                    raise ValueError("installer_too_large")
                _set(total=total)
                last = 0.0
                with open(part, "wb") as out:
                    async for chunk in r.aiter_bytes(chunk_size=1 << 18):
                        got += len(chunk)
                        if got > MAX_BYTES:
                            raise ValueError("installer_too_large")
                        out.write(chunk)
                        if time.monotonic() - last > 0.25:
                            _set(bytes=got); last = time.monotonic()
                    out.flush(); os.fsync(out.fileno())
        expected = int(info.get("size") or 0) or total
        if got <= 0 or (expected and got != expected):
            raise ValueError(f"size_mismatch got {got} expected {expected}")
        os.replace(part, dest)                                        # only now does a file with the real name exist
        _set(state=DONE, path=str(dest), bytes=got, total=got, message="Downloaded.", error=None)
        logger.info("installer downloaded: %s (%d bytes)", dest, got)
    except Exception as e:                                             # noqa: BLE001
        logger.warning("installer download failed: %s: %s", type(e).__name__, e)
        msg = ("The downloaded file was incomplete, so it was thrown away. Try again." if isinstance(e, ValueError) and "size_mismatch" in str(e)
               else "The installer is larger than expected, so it was not saved." if isinstance(e, ValueError) and "too_large" in str(e)
               else _plain_error(e))
        _set(state=FAILED, error=type(e).__name__, message=msg)
    finally:
        if part is not None:
            try:
                part.unlink(missing_ok=True)                           # a half file is never left behind
            except OSError:
                pass


async def start(svc) -> Dict[str, Any]:
    """Begin (or join) the download of this PC's installer. Returns the current snapshot at once; the work runs in the background."""
    global _thread
    if _is_running():
        return {**snapshot(), "joined": True}
    info = await svc.installer_link()
    if not info.get("update_available"):
        return {**_blank(), "state": IDLE, "reason": "no_update_available", "installed_version": info.get("installed_version")}
    if not info.get("direct"):                                         # the channel has no installer for this PC: the release page is the honest answer
        return {**_blank(), "state": FAILED, "version": info.get("latest_version"), "url": info.get("url"), "no_direct_link": True,
                "message": "The update server has no installer for this computer yet.", "error": "no_direct_link"}
    from .system_router import is_release_url
    if not is_release_url(info["url"]):
        return {**_blank(), "state": FAILED, "error": "bad_link", "message": "The update link was not recognised, so nothing was downloaded."}
    _set(state=RUNNING, version=info.get("latest_version"), filename=info.get("filename") or Path(info["url"]).name, path=None,
         bytes=0, total=int(info.get("size") or 0), error=None, message="Downloading...")
    _thread = threading.Thread(target=_worker, args=(info,), name="bighat-installer-download", daemon=True)
    _thread.start()
    return {**snapshot(), "url": info["url"], "joined": False}


def open_installer(path: str) -> Dict[str, Any]:
    """Show the finished installer in its folder (and, on Windows, offer to run it). Only a file that is in the Downloads folder and was
    downloaded by this module can be opened."""
    from .system_router import downloads_dir, _show_in_folder
    snap = snapshot()
    p = Path(path or snap.get("path") or "")
    try:
        inside = p.resolve().parent == downloads_dir().resolve()
    except OSError:
        inside = False
    if not (inside and p.is_file() and p.suffix.lower() in (".exe", ".dmg", ".msi", ".pkg")):
        return {"ok": False, "message": "That file is not in your Downloads folder any more. Download the update again."}
    if os.environ.get("BIGHAT_NO_BROWSER") == "1":
        return {"ok": True, "shown": str(p), "simulated": True}
    return {"ok": bool(_show_in_folder(p)), "shown": str(p)}
