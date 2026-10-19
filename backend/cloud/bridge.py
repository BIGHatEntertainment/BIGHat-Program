"""One-way writer to the separate "bridge" Atlas cluster.

The (yet-to-launch) BIG Hat Cloud app reads `cloud_entitlements` from the
bridge cluster to decide who may enter. api.bighat.live only ever WRITES
here — licensing data stays in the main DB (never store license keys,
payment data or customer ids in bridge docs).

A bridge outage must NEVER break order processing: callers get False and
the poller retries on its next cycle. Missing env vars = skip quietly.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger("bighat-bridge")

_client = None


def _cfg() -> tuple[str, str]:
    return (
        os.environ.get("BRIDGE_MONGO_URL", "").strip(),
        os.environ.get("BRIDGE_DB_NAME", "").strip(),
    )


def is_configured() -> bool:
    url, name = _cfg()
    return bool(url and name)


def _db():
    global _client
    from motor.motor_asyncio import AsyncIOMotorClient
    url, name = _cfg()
    if _client is None:
        _client = AsyncIOMotorClient(url, serverSelectionTimeoutMS=8000)
    return _client[name]


def reset_client() -> None:
    """Test hook — drop the cached client so env changes take effect."""
    global _client
    _client = None


async def sync_entitlement(lic) -> bool:
    """Upsert one `cloud_entitlements` doc keyed by lowercase email.

    Returns True on success OR when the bridge is unconfigured / the
    license has no subscription (nothing to sync). Returns False only on
    a real write failure, so the poller knows to retry next cycle.
    """
    if not is_configured():
        return True
    from .license_service import cloud_subscription_state
    state = cloud_subscription_state(lic)
    if state["paid_through"] is None:
        return True
    doc = {
        "status": state["status"],
        "paid_through": state["paid_through"].isoformat(),
        "grace_until": state["grace_until"].isoformat(),
        "plan": "cloud_subscription",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "last_order_id": lic.cloud_subscription_last_order_id,
    }
    try:
        await _db()["cloud_entitlements"].update_one(
            {"_id": lic.email.lower()}, {"$set": doc}, upsert=True,
        )
        return True
    except Exception as e:
        logger.error("[CLOUD-SUB][BRIDGE] upsert failed for %s: %s — will retry next poll",
                     lic.email, e)
        return False
