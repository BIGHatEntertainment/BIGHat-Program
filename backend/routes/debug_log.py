"""v32.0.0-alpha.42 — rotating debug log for the desktop app.

Merchant install feedback: DevTools aren't available in the frozen
Tauri build (Ctrl+Shift+I is a no-op), so when the Trivia Presenter
mystery-empties there's no way to see what the frontend axios call is
actually doing on the merchant's Windows machine.

This module wires a two-file rotating log at
  <Documents>/BIG Hat Entertainment/Files/Logs/app.log
  <Documents>/BIG Hat Entertainment/Files/Logs/app.log.1
Each capped at 1MB (per merchant spec). Rotation is handled by Python's
stdlib `RotatingFileHandler`, so when `app.log` fills, it's moved to
`app.log.1` (overwriting the previous `app.log.1`) and `app.log` is
truncated. Two files, always. Predictable disk usage.

The frontend POSTs structured events here — every click (data-testid +
text + route), every axios request+response (URL, status, ms), and
every route change. When the merchant reports a bug we can `GET
/api/debug/logs/download` to pull the whole thing.
"""
from __future__ import annotations
import json
import logging
import os
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

router = APIRouter(prefix="/debug", tags=["debug"])
logger = logging.getLogger("routes.debug_log")

_MAX_BYTES = 1024 * 1024        # 1 MB per merchant spec
_BACKUP_COUNT = 1               # → two files total (`app.log` + `app.log.1`)
_LOG_FILE_NAME = "app.log"

_captured_logger: Optional[logging.Logger] = None


def _docs_root() -> Path:
    """Inline resolver — same as trivia_viewer._native_docs_root.
    Frozen build must not depend on cross-module imports."""
    override = os.environ.get("BIGHAT_FILES_DIR")
    if override:
        return Path(override).expanduser()
    home = Path.home()
    base = home / "Documents"
    if not base.exists():
        base = home
    return base / "BIG Hat Entertainment"


def _logs_dir() -> Path:
    return _docs_root() / "Files" / "Logs"


def _get_capture_logger() -> logging.Logger:
    """Lazy-init a dedicated logger that writes ONLY to the rotating
    log files — never mixed with backend stdout/stderr streams."""
    global _captured_logger
    if _captured_logger is not None:
        return _captured_logger

    lg = logging.getLogger("bighat.capture")
    lg.setLevel(logging.INFO)
    lg.propagate = False  # don't spam supervisor logs

    if not lg.handlers:
        try:
            _logs_dir().mkdir(parents=True, exist_ok=True)
            handler = RotatingFileHandler(
                filename=str(_logs_dir() / _LOG_FILE_NAME),
                maxBytes=_MAX_BYTES,
                backupCount=_BACKUP_COUNT,
                encoding="utf-8",
            )
            # Newline-delimited JSON — makes tail/grep trivial and
            # keeps parsing dead-simple.
            handler.setFormatter(logging.Formatter("%(message)s"))
            lg.addHandler(handler)
        except OSError as e:
            logger.warning("[debug-log] could not initialise capture: %s", e)

    _captured_logger = lg
    return lg


class LogEvent(BaseModel):
    """Frontend-emitted event. Wire format is intentionally loose — the
    merchant may add fields ad-hoc from any React component. Only `type`
    and `at` are required; everything else is opaque metadata."""
    type: str                    # "click" | "axios" | "route" | "error" | ...
    at: Optional[str] = None     # ISO timestamp; server backfills if missing
    session: Optional[str] = None
    data: Optional[dict] = None


class LogBatch(BaseModel):
    events: List[LogEvent]


@router.post("/log")
async def push_log(batch: LogBatch):
    """Frontend POSTs a batch of events here every 2-3 seconds."""
    lg = _get_capture_logger()
    now_iso = datetime.now(timezone.utc).isoformat()
    written = 0
    for e in batch.events:
        rec = {
            "at": e.at or now_iso,
            "type": e.type,
            "session": e.session or "",
            "data": e.data or {},
        }
        try:
            lg.info(json.dumps(rec, default=str, ensure_ascii=False))
            written += 1
        except Exception as exc:
            logger.warning("[debug-log] serialise failed: %s", exc)
    return {"written": written}


@router.get("/logs")
async def read_logs(limit: int = Query(200, ge=1, le=5000)):
    """Return the last `limit` events as parsed JSON. Used for in-app
    diagnostics view."""
    entries: List[dict] = []
    for name in (_LOG_FILE_NAME + ".1", _LOG_FILE_NAME):
        # Older file first so overall order is chronological.
        p = _logs_dir() / name
        if not p.exists():
            continue
        try:
            with p.open("r", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        entries.append({"type": "raw", "line": line})
        except OSError as e:
            entries.append({"type": "error", "error": f"read {p}: {e}"})
    # Return the tail
    return {"count": len(entries), "entries": entries[-limit:]}


@router.get("/logs/download")
async def download_logs():
    """Download `app.log` + `app.log.1` concatenated into a single file
    so the merchant can email/upload the whole thing."""
    lg = _logs_dir()
    if not lg.exists():
        raise HTTPException(status_code=404, detail="No logs yet")
    combined = lg / "app-combined.log"
    try:
        with combined.open("w", encoding="utf-8") as out:
            out.write(f"# BIG Hat combined debug log — exported {datetime.now(timezone.utc).isoformat()}\n")
            for name in (_LOG_FILE_NAME + ".1", _LOG_FILE_NAME):
                p = lg / name
                if not p.exists():
                    continue
                out.write(f"\n\n# ─── {p.name} ({p.stat().st_size} bytes) ───\n")
                with p.open("r", encoding="utf-8", errors="replace") as fh:
                    out.write(fh.read())
            # v32.0.0-alpha.57: append the BACKEND log tails so exported
            # debug logs finally show server-side behaviour (title-card
            # resolution, boot migrations, exceptions) from the frozen app.
            for name in ("backend.log.1", "backend.log"):
                p = lg / name
                if not p.exists():
                    continue
                data = p.read_bytes()
                tail = data[-400_000:].decode("utf-8", errors="replace")
                out.write(f"\n\n# ─── {p.name} ({p.stat().st_size} bytes, last {len(tail)} chars) ───\n")
                out.write(tail)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"combine failed: {e}")
    return FileResponse(str(combined), media_type="text/plain", filename="bighat-debug.log")


@router.delete("/logs")
async def clear_logs():
    """Wipe both log files. Handy right before reproducing a bug so the
    subsequent capture is clean."""
    wiped = []
    for name in (_LOG_FILE_NAME, _LOG_FILE_NAME + ".1", "app-combined.log"):
        p = _logs_dir() / name
        try:
            if p.exists():
                p.unlink()
                wiped.append(str(p))
        except OSError as e:
            logger.warning("[debug-log] wipe %s failed: %s", p, e)
    # Rebuild the handler so writes resume cleanly.
    global _captured_logger
    _captured_logger = None
    return {"wiped": wiped}


@router.get("/logs/status")
async def logs_status():
    """Compact status: file sizes + docs root, so the merchant can
    confirm log capture is working without downloading."""
    lg = _logs_dir()
    files = {}
    for name in (_LOG_FILE_NAME, _LOG_FILE_NAME + ".1"):
        p = lg / name
        files[name] = {
            "exists": p.exists(),
            "size_bytes": p.stat().st_size if p.exists() else 0,
        }
    return {
        "logs_dir": str(lg),
        "logs_dir_exists": lg.exists(),
        "max_bytes_per_file": _MAX_BYTES,
        "files": files,
    }
