"""Legal acceptance record (Terms, Privacy Policy, California addendum).

Stored as a small JSON file in the persistent per-user data dir (next to
system_config.json, i.e. %LOCALAPPDATA%\\BIGHat on Windows), NOT in the webview's
localStorage, so it survives restarts, webview cache clears and in-place updates.

The user is asked again only when:
  * there is no record (fresh install, or after uninstall which wipes the dir)
  * the app version changed (a new update was installed)
  * the legal documents version changed (policies were edited)

Writes are atomic (temp file + os.replace) so a crash can never leave a
half-written or empty record.
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/legal", tags=["native-legal"])  # mounted under /api/native/system
_LOCK = threading.Lock()


def _record_path() -> Path:
    cfg = os.environ.get("BIGHAT_CONFIG_PATH")
    base = Path(cfg).parent if cfg else Path(__file__).resolve().parent
    return base / "legal_acceptance.json"


def _app_version() -> str:
    here = Path(__file__).resolve().parent.parent
    for p in (here / "VERSION.txt", here.parent / "VERSION.txt"):
        try:
            v = p.read_text(encoding="utf-8").strip()
            if v:
                return v
        except OSError:
            continue
    return "unknown"


def _read() -> Optional[dict]:
    try:
        data = json.loads(_record_path().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


class AcceptBody(BaseModel):
    legal_version: str


@router.get("/status")
def status(legal_version: str = ""):
    rec = _read()
    app_version = _app_version()
    accepted = bool(
        rec
        and rec.get("legal_version") == legal_version
        and rec.get("app_version") == app_version
    )
    return {"accepted": accepted, "app_version": app_version, "record": rec}


@router.post("/accept")
def accept(body: AcceptBody):
    rec = {
        "legal_version": body.legal_version,
        "app_version": _app_version(),
        "accepted_at": datetime.now(timezone.utc).isoformat(),
    }
    path = _record_path()
    with _LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".legal_", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(rec, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
    return {"accepted": True, "record": rec}
