"""Desktop side of the Setup Package cloud calls (alpha.85). Never raises on a network problem."""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import httpx

from . import relay_client
from .hwid import generate_hwid

logger = logging.getLogger("bighat-package-client")


def _auth() -> Optional[Dict[str, str]]:
    return relay_client._auth()


def _fail(error: str, message: str = "") -> Dict[str, Any]:
    return {"ok": False, "error": error, "message": message}


def _nice(detail: str, status: int) -> str:
    d = str(detail or "")
    table = {
        "only_the_master_admin_can_publish": "Only the master admin can publish the setup.",
        "only_the_master_admin_can_transfer": "Only the master admin can move the setup.",
        "no_package": "No setup has been published yet. The master admin needs to publish it first.",
        "package_too_big": "The setup package is too big to upload.",
        "please_wait_a_moment": "Please wait a few seconds and try again.",
        "bad_target_email": "That email address does not look right, or it is the same as the current one.",
        "target_already_has_a_package": "That email already has its own setup package, so it cannot be moved there.",
        "wrong_code": "That code is not right.",
        "code_expired_or_not_requested": "That code has expired. Ask for a new one.",
        "too_many_wrong_codes": "Too many wrong codes. Ask for a new one.",
        "could_not_send_the_confirmation_email": "The confirmation email could not be sent. Try again in a minute.",
    }
    for k, v in table.items():
        if d.startswith(k):
            return v
    if d.startswith("newer_version_exists"):
        return "Another computer published a newer setup. Pull it first, then publish again."
    if d.startswith("package_contains_a_secret"):
        return "The setup contained something private (like a password), so it was not uploaded."
    if status == 401:
        return "This copy of the program is not activated, so the setup service refused it."
    return "The setup service could not do that right now."


async def _call(path: str, **kw) -> Any:
    try:
        async with httpx.AsyncClient(timeout=kw.pop("timeout", 30.0)) as c:
            r = await c.post(f"{relay_client.base_url()}{path}", **kw)
    except httpx.TimeoutException:
        return _fail("timeout", "The setup service did not answer in time.")
    except httpx.RequestError:
        return _fail("offline", "Could not reach the setup service. Check the internet connection, or use the file option.")
    return r


def _detail(r) -> str:
    try:
        d = r.json().get("detail")
        return d if isinstance(d, str) else str(d or "")
    except Exception:
        return ""


async def status() -> Dict[str, Any]:
    a = _auth()
    if not a:
        return _fail("no_license", "Activate the program first.")
    r = await _call("/api/setup-package/status", json=a, timeout=15.0)
    if isinstance(r, dict):
        return r
    if r.status_code >= 400:
        return _fail(_detail(r) or f"http_{r.status_code}", _nice(_detail(r), r.status_code))
    return {"ok": True, **r.json()}


async def publish(raw: bytes, *, expected_version: str = "", machine_label: str = "") -> Dict[str, Any]:
    a = _auth()
    if not a:
        return _fail("no_license", "Activate the program first.")
    r = await _call("/api/setup-package/publish", data={**a, "is_master": "1", "expected_version": expected_version, "machine_label": machine_label},
                    files={"file": ("setup.zip", raw)}, timeout=120.0)
    if isinstance(r, dict):
        return r
    if r.status_code >= 400:
        return _fail(_detail(r) or f"http_{r.status_code}", _nice(_detail(r), r.status_code))
    return {"ok": True, **r.json()}


async def pull() -> Dict[str, Any]:
    a = _auth()
    if not a:
        return _fail("no_license", "Activate the program first.")
    r = await _call("/api/setup-package/pull", json=a, timeout=120.0)
    if isinstance(r, dict):
        return r
    if r.status_code >= 400:
        return _fail(_detail(r) or f"http_{r.status_code}", _nice(_detail(r), r.status_code))
    return {"ok": True, "raw": r.content, "version": r.headers.get("x-package-version"), "hash": r.headers.get("x-package-hash")}


async def transfer_start(to_email: str) -> Dict[str, Any]:
    a = _auth()
    if not a:
        return _fail("no_license")
    r = await _call("/api/setup-package/transfer/start", json={**a, "is_master": True, "to_email": to_email}, timeout=30.0)
    if isinstance(r, dict):
        return r
    if r.status_code >= 400:
        return _fail(_detail(r) or f"http_{r.status_code}", _nice(_detail(r), r.status_code))
    return {"ok": True, **r.json()}


async def transfer_confirm(code: str) -> Dict[str, Any]:
    a = _auth()
    if not a:
        return _fail("no_license")
    r = await _call("/api/setup-package/transfer/confirm", json={**a, "is_master": True, "code": code}, timeout=30.0)
    if isinstance(r, dict):
        return r
    if r.status_code >= 400:
        return _fail(_detail(r) or f"http_{r.status_code}", _nice(_detail(r), r.status_code))
    return {"ok": True, **r.json()}
