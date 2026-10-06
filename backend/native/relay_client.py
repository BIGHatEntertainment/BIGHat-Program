"""Desktop side of the QR relay (alpha.82). Talks to api.bighat.live over plain outbound HTTPS.

Never raises on a network problem: every call returns {"ok": False, "error": ...} so a bad connection
only means "no QR right now", never a crash. The license key + machine id are read from the local config."""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from .config import config_manager
from .hwid import generate_hwid

logger = logging.getLogger("bighat-relay-client")


def base_url() -> str:
    return os.environ.get("BIGHAT_LICENSE_API_BASE_URL", "https://api.bighat.live").rstrip("/")


def _auth() -> Optional[Dict[str, str]]:
    key = ((config_manager.config.get("license_status") or {}).get("key") or "").strip().upper()
    return {"license_key": key, "hwid": generate_hwid()} if key else None


def public_url(path: str) -> str:
    """Full link for a QR. On api.bighat.live only /api/... reaches the relay (other paths show the website),
    so the short /d/... and /k/... forms are always turned into /api/relay/d/... and /api/relay/k/...."""
    if path.startswith("/d/") or path.startswith("/k/"):
        path = "/api/relay" + path
    return f"{base_url()}{path}"


def _fail(error: str, message: str = "") -> Dict[str, Any]:
    return {"ok": False, "error": error, "message": message}


async def _call(method: str, path: str, *, timeout: float = 15.0, **kw) -> Dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=timeout) as c:
            r = await c.request(method, f"{base_url()}{path}", **kw)
    except httpx.TimeoutException:
        return _fail("timeout", "The QR service did not answer in time.")
    except httpx.RequestError as e:
        return _fail("offline", "Could not reach the QR service. Check the internet connection.")
    try:
        data = r.json()
    except Exception:
        data = {}
    if r.status_code >= 400:
        detail = data.get("detail") if isinstance(data, dict) else None
        return _fail(str(detail or f"http_{r.status_code}"), _nice(detail, r.status_code))
    out = dict(data) if isinstance(data, dict) else {"data": data}
    out["ok"] = True
    return out


def _nice(detail: Any, status: int) -> str:
    d = str(detail or "")
    if status == 401:
        return "This copy of the program is not activated, so the QR service refused it."
    if d == "too_many_files":
        return "Too many QR files are stored. They clear on their own after two days."
    if d == "file_too_big":
        return "That file is too big to share by QR."
    return "The QR service could not do that right now."


async def publish_file(path: str, *, label: str = "") -> Dict[str, Any]:
    """Upload a file the PC already has; return {"ok", "url" (full https link), "expires_at"}."""
    a = _auth()
    if not a:
        return _fail("no_license", "Activate the program first.")
    p = Path(path)
    if not p.exists():
        return _fail("missing_file", "The file is not on this computer any more.")
    with open(p, "rb") as f:
        res = await _call("POST", "/api/relay/files", timeout=180.0, data={**a, "label": label},
                          files={"file": (p.name, f)})
    if res.get("ok"):
        res["url"] = public_url(res["url"])
    return res


async def open_night(venue: str) -> Dict[str, Any]:
    a = _auth()
    if not a:
        return _fail("no_license", "Activate the program first.")
    res = await _call("POST", "/api/relay/karaoke/sessions", json={**a, "venue": venue})
    if res.get("ok"):
        res["url"] = public_url(res["url"])
    return res


async def pull(session: str, answers: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    a = _auth()
    if not a:
        return _fail("no_license")
    return await _call("POST", f"/api/relay/karaoke/sessions/{session}/pull", json={**a, "answers": answers or []}, timeout=10.0)


async def close_night(session: str) -> Dict[str, Any]:
    a = _auth()
    if not a:
        return _fail("no_license")
    return await _call("POST", f"/api/relay/karaoke/sessions/{session}/close", json=a, timeout=10.0)
