"""Admin endpoints for the Squarespace Orders poller.

Lets the merchant trigger a run on demand and inspect the poll state
without shelling into the pod. All endpoints are JWT-gated on the same
admin secret as the rest of /api/license/admin/*.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException

from .admin_router import _require_admin as require_admin           # reuse the existing JWT guard
from .license_service import LicenseService
from .license_store import LicenseStore
from . import squarespace_poller

logger = logging.getLogger("bighat-poller-router")

router = APIRouter(prefix="/api/license/admin/poller", tags=["cloud-licensing-poller"])

_service: Optional[LicenseService] = None
_store: Optional[LicenseStore] = None


def set_runtime(*, service: LicenseService, store: LicenseStore) -> None:
    global _service, _store
    _service, _store = service, store


def _require_runtime() -> tuple[LicenseService, LicenseStore]:
    if _service is None or _store is None:
        raise HTTPException(status_code=503, detail="poller not initialised")
    return _service, _store


@router.get("/status", dependencies=[Depends(require_admin)])
async def poller_status() -> dict[str, Any]:
    """Current high-water mark + lifetime counters. Safe to poll from a
    monitoring dashboard."""
    _, store = _require_runtime()
    state = await squarespace_poller.load_state(store)
    return {
        "last_modified_at": state.get("last_modified_at"),
        "last_run_at": state.get("last_run_at"),
        "last_error": state.get("last_error", ""),
        "total_fetched_lifetime": state.get("total_fetched_lifetime", 0),
        "total_minted_lifetime": state.get("total_minted_lifetime", 0),
    }


@router.post("/run", dependencies=[Depends(require_admin)])
async def poller_run_once() -> dict[str, Any]:
    """Trigger a single poll cycle immediately and return the summary.
    Use this to retroactively mint orders that arrived while the service
    was misconfigured."""
    service, store = _require_runtime()
    summary = await squarespace_poller.run_once(service=service, store=store)
    return summary


@router.post("/replay/{order_id}", dependencies=[Depends(require_admin)])
async def poller_replay(order_id: str) -> dict[str, Any]:
    """Force-replay a single Squarespace order by id. Clears the
    idempotency row first, then fetches just that one order and processes
    it. Useful when a customer reports they didn't get their license email.
    """
    from . import config as cloud_config
    import httpx
    service, store = _require_runtime()
    api_key = cloud_config.squarespace_api_key()
    if not api_key:
        raise HTTPException(status_code=503, detail="SQUARESPACE_API_KEY not set")

    # Drop any prior idempotency marker so the order is re-processed.
    event_id = f"{squarespace_poller.EVENT_ID_PREFIX}{order_id}"
    await store.db["license_webhook_events"].delete_one({"event_id": event_id})

    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(
            f"{cloud_config.squarespace_api_base()}/commerce/orders/{order_id}",
            headers={
                "Authorization": f"Bearer {api_key}",
                "User-Agent": "BIGHat-Entertainment-Poller/1.0",
            },
        )
    if r.status_code != 200:
        raise HTTPException(status_code=r.status_code, detail=r.text)
    order = r.json()

    result = await squarespace_poller.process_order(
        order=order, service=service, store=store,
    )
    return {"ok": True, "result": result}
