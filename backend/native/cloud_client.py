"""Cloud-license HTTP client (Phase 10.2).

Thin async wrapper that the desktop app uses to talk to the cloud license
authority at `https://api.bighat.live`. All methods:

  * Are NETWORK-OPTIONAL — they fail soft. The desktop app honours the
    last-known good validation for `OFFLINE_GRACE_DAYS` so a transient
    outage never locks a paying customer out of features they bought.
  * Use a short connect/read timeout (5s default) — the desktop UI
    cannot afford to hang on a flaky connection.
  * Return tagged dicts (`{"ok": bool, ...}`) instead of raising on
    transport errors, which the caller can render directly.

The base URL is configurable via `BIGHAT_LICENSE_API_BASE_URL` (default
`https://api.bighat.live`). Keep this in `packaging/.env.standalone` so
it ships with installers but never overrides the dev/server value.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Optional

import httpx

logger = logging.getLogger("bighat-cloud-client")


def _api_base_url() -> str:
    return os.environ.get("BIGHAT_LICENSE_API_BASE_URL", "https://api.bighat.live").rstrip("/")


def _machine_label() -> str:
    """Friendly machine name for the cloud server's audit log."""
    import platform
    return f"{platform.node() or 'unknown'} ({platform.system()})"


async def _post(path: str, body: dict, *, timeout: float = 5.0) -> dict:
    url = f"{_api_base_url()}{path}"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.post(url, json=body)
        if r.status_code >= 500:
            return {"ok": False, "error": "server_error", "status_code": r.status_code,
                    "message": "license server unavailable"}
        try:
            data = r.json()
        except Exception:
            return {"ok": False, "error": "invalid_response",
                    "status_code": r.status_code, "message": r.text[:200]}
        if r.status_code >= 400:
            # Server returned a structured 4xx — surface its detail.
            return {"ok": False, "error": data.get("detail") or "client_error",
                    "status_code": r.status_code, "message": data.get("detail") or "",
                    "raw": data}
        # Successful 2xx: pass body through.
        if isinstance(data, dict):
            data.setdefault("ok", True)
            return data
        return {"ok": True, "data": data}
    except httpx.TimeoutException:
        return {"ok": False, "error": "timeout", "message": "license server timeout"}
    except httpx.RequestError as e:
        return {"ok": False, "error": "network_error", "message": str(e)}


async def _get(path: str, *, timeout: float = 5.0) -> dict:
    url = f"{_api_base_url()}{path}"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.get(url)
        try:
            data = r.json()
        except Exception:
            return {"ok": False, "error": "invalid_response",
                    "status_code": r.status_code, "message": r.text[:200]}
        if r.status_code >= 400:
            return {"ok": False, "error": data.get("detail") or "client_error",
                    "status_code": r.status_code}
        if isinstance(data, dict):
            data.setdefault("ok", True)
            return data
        return {"ok": True, "data": data}
    except httpx.TimeoutException:
        return {"ok": False, "error": "timeout"}
    except httpx.RequestError as e:
        return {"ok": False, "error": "network_error", "message": str(e)}


# ---------- public API ----------
async def activate(*, license_key: str, hwid: str,
                   machine_name: Optional[str] = None,
                   email: Optional[str] = None) -> dict:
    """Bind this machine's HWID to a license key.

    On success the cloud returns:
        {ok, message, owns_standalone, cloud_library_active,
         cloud_library_expires_at, max_seats, active_seats, revalidate_after}
    On failure: {ok=False, error, message}.
    """
    return await _post("/api/license/activate", {
        "key": license_key,
        "hwid": hwid,
        "machine_name": machine_name or _machine_label(),
        "email": email,
    })


async def validate(*, license_key: str, hwid: str) -> dict:
    """Periodic re-check (cadence = 7 days). Cloud returns:
        {ok, owns_standalone, cloud_library_active,
         cloud_library_expires_at, revoked, revalidate_after}
    The desktop caches this and falls back to the cached snapshot when
    the request fails (transport errors only — 4xx is authoritative)."""
    return await _post("/api/license/validate", {
        "key": license_key,
        "hwid": hwid,
    })


async def deactivate(*, license_key: str, hwid: str) -> dict:
    """Free this machine's seat so it can be re-bound elsewhere."""
    return await _post("/api/license/deactivate", {
        "key": license_key,
        "hwid": hwid,
    })


async def get_status(*, license_key: str) -> dict:
    """Public status lookup (masked key view) — used by the Settings page."""
    return await _get(f"/api/license/status/{license_key}")


async def get_download_url(*, platform: str) -> dict:
    """Where the auto-updater + UI fetch the latest installer URL."""
    return await _get(f"/api/downloads/{platform}")
