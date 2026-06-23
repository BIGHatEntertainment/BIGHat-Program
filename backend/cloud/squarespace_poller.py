"""Squarespace Orders poller — the production replacement for webhooks.

Squarespace's webhook subscriptions API requires building a full OAuth
Extension (see https://developers.squarespace.com/commerce-apis/webhook-
subscriptions-overview). For a single-merchant setup that's pure
overhead; the simpler and more reliable design is to poll the public
Commerce Orders REST API every 2 minutes with the static API key the
merchant already has.

Architecture
------------
* Background asyncio task started at app boot when BIGHAT_CLOUD_MODE=1.
* Persisted high-water mark (`modifiedOn` of the most recent order we
  processed) lives in the `license_poll_state` collection so restarts
  don't re-process the entire backlog.
* Per-order idempotency reuses the existing `license_webhook_events`
  collection keyed by `sqsp:order:<orderId>`, mirroring the contract
  the webhook handler used. A single order is therefore minted exactly
  once across the whole lifetime of the deployment, regardless of how
  many times it appears in poll responses.
* Tier routing has two layers:
    1. Exact `LICENSE_PRODUCT_MAP` (productId → tier) from env.
    2. Fallback substring match against `productName` using the rules
       in `config.license_product_name_rules()`.
  This means new products can be wired up by either adding to the env
  map OR just naming the product something reasonable in Squarespace.

The poller is intentionally idempotent, restart-safe, rate-limit-aware,
and silent on failure (logs at WARN; never crashes the FastAPI app).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional

import httpx

from . import config
from .license_service import LicenseService
from .license_store import LicenseStore

logger = logging.getLogger("bighat-license-poller")

POLL_STATE_ID = "squarespace_orders"
EVENT_ID_PREFIX = "sqsp:order:"


# ---------------------------------------------------------------------------
# Tier resolution
# ---------------------------------------------------------------------------
def resolve_tier(*, product_id: str, product_name: str) -> Optional[str]:
    """Map a Squarespace line item to one of our four license tiers.

    Returns one of: standalone | music_bingo | karaoke | cloud_library
    or None if the item shouldn't trigger a mint (e.g. merch t-shirts).
    """
    mapping = config.license_product_map()
    if product_id and product_id in mapping:
        return mapping[product_id]

    if product_name:
        needle = product_name.lower()
        for substring, tier in config.license_product_name_rules():
            if substring in needle:
                return tier
    return None


# ---------------------------------------------------------------------------
# Order processing
# ---------------------------------------------------------------------------
async def process_order(
    *,
    order: dict[str, Any],
    service: LicenseService,
    store: LicenseStore,
) -> dict[str, Any]:
    """Mint all license rows implied by a single Squarespace order.

    Returns a result dict so the poll loop can log a summary. Always
    safe to call repeatedly — idempotency lives in `webhook_events`
    and in each `mint_*` method.
    """
    order_id = str(order.get("id") or "")
    if not order_id:
        return {"order_id": "", "status": "skipped", "reason": "no_order_id"}

    event_id = f"{EVENT_ID_PREFIX}{order_id}"
    if await store.already_processed(event_id):
        return {"order_id": order_id, "status": "duplicate"}

    email = (order.get("customerEmail") or "").strip().lower()
    if not email:
        from .license_models import WebhookEvent
        await store.record_event(WebhookEvent(
            event_id=event_id, topic="poll.order", processed=False,
            received_at=datetime.now(timezone.utc), raw_payload=order,
        ))
        return {"order_id": order_id, "status": "skipped", "reason": "no_email"}

    customer_id = str(order.get("customerId") or "")
    line_items = order.get("lineItems") or []

    minted: list[str] = []
    skipped: list[str] = []

    for item in line_items:
        product_id = str(item.get("productId") or "")
        product_name = str(item.get("productName") or "")
        tier = resolve_tier(product_id=product_id, product_name=product_name)
        if tier is None:
            skipped.append(f"{product_name or product_id} (no tier match)")
            continue

        try:
            if tier == "standalone":
                lic = await service.mint_standalone_purchase(
                    email=email, order_id=order_id, customer_id=customer_id,
                )
                minted.append(f"standalone:{lic.key}")
            elif tier == "cloud_library":
                lic = await service.mint_cloud_subscription(
                    email=email,
                    subscription_id=order_id,         # one-shot order acts as sub id
                    customer_id=customer_id,
                    months=12,                         # annual; tune via product config later
                )
                minted.append(f"cloud_library:{lic.key}")
            elif tier in ("music_bingo", "karaoke"):
                lic = await service.mint_addon_purchase(
                    addon=tier, email=email, order_id=order_id,
                    customer_id=customer_id,
                )
                minted.append(f"{tier}:{lic.key}")
            else:
                skipped.append(f"{product_name} (unknown tier '{tier}')")
        except Exception as e:
            logger.exception("[poller] mint failed for order=%s tier=%s: %s",
                             order_id, tier, e)
            skipped.append(f"{tier} ({type(e).__name__})")

    from .license_models import WebhookEvent
    await store.record_event(WebhookEvent(
        event_id=event_id, topic="poll.order", processed=bool(minted),
        received_at=datetime.now(timezone.utc), raw_payload=order,
    ))
    if minted:
        await store.mark_processed(event_id)
    return {
        "order_id": order_id,
        "email": email,
        "status": "minted" if minted else "skipped",
        "minted": minted,
        "skipped": skipped,
    }


# ---------------------------------------------------------------------------
# HTTP fetch
# ---------------------------------------------------------------------------
async def fetch_orders(
    *,
    modified_after: datetime,
    modified_before: datetime,
    api_key: str,
    base: Optional[str] = None,
    client: Optional[httpx.AsyncClient] = None,
) -> list[dict[str, Any]]:
    """Page through Squarespace's Orders API. Returns ALL orders in window.

    Squarespace returns max 50 per page; cursor in `pagination.nextPageCursor`.
    """
    base = base or config.squarespace_api_base()
    url = f"{base}/commerce/orders"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "User-Agent": "BIGHat-Entertainment-Poller/1.0",
    }
    params = {
        "modifiedAfter": modified_after.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "modifiedBefore": modified_before.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
    }

    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=30.0)
    try:
        out: list[dict[str, Any]] = []
        cursor: Optional[str] = None
        for _page in range(50):       # hard cap: 50 pages = 2500 orders/poll
            q = dict(params)
            if cursor:
                q["cursor"] = cursor
            r = await client.get(url, headers=headers, params=q)
            r.raise_for_status()
            data = r.json()
            out.extend(data.get("result") or [])
            pagination = data.get("pagination") or {}
            if not pagination.get("hasNextPage"):
                break
            cursor = pagination.get("nextPageCursor")
            if not cursor:
                break
        return out
    finally:
        if owns_client:
            await client.aclose()


# ---------------------------------------------------------------------------
# State persistence
# ---------------------------------------------------------------------------
async def load_state(store: LicenseStore) -> dict[str, Any]:
    raw = await store.db["license_poll_state"].find_one({"_id": POLL_STATE_ID})
    return raw or {}


async def save_state(store: LicenseStore, state: dict[str, Any]) -> None:
    # Exclude _id from the $set payload — MontyDB rejects ANY update that
    # touches the immutable _id field. The upsert filter already sets _id
    # on insert, so we don't need to specify it in the update doc.
    payload = {k: v for k, v in state.items() if k != "_id"}
    await store.db["license_poll_state"].update_one(
        {"_id": POLL_STATE_ID},
        {"$set": payload},
        upsert=True,
    )


# ---------------------------------------------------------------------------
# Single-shot poll (callable directly from admin endpoint or tests)
# ---------------------------------------------------------------------------
async def run_once(
    *,
    service: LicenseService,
    store: LicenseStore,
    api_key: Optional[str] = None,
    now: Optional[datetime] = None,
    client: Optional[httpx.AsyncClient] = None,
) -> dict[str, Any]:
    """One iteration. Returns a summary suitable for logs or admin response."""
    api_key = api_key if api_key is not None else config.squarespace_api_key()
    if not api_key:
        return {"ok": False, "error": "SQUARESPACE_API_KEY not configured"}

    now = now or datetime.now(timezone.utc)
    state = await load_state(store)

    last_iso = state.get("last_modified_at")
    if last_iso:
        try:
            modified_after = datetime.fromisoformat(last_iso.replace("Z", "+00:00"))
        except ValueError:
            modified_after = now - timedelta(hours=config.squarespace_poll_lookback_hours())
    else:
        modified_after = now - timedelta(hours=config.squarespace_poll_lookback_hours())

    # Subtract 1ms so the boundary order isn't filtered out (Squarespace
    # uses exclusive lower bound on `modifiedAfter`).
    modified_after = modified_after - timedelta(milliseconds=1)

    try:
        orders = await fetch_orders(
            modified_after=modified_after,
            modified_before=now,
            api_key=api_key,
            client=client,
        )
    except httpx.HTTPError as e:
        logger.warning("[poller] fetch failed: %s", e)
        await save_state(store, {
            **state,
            "last_run_at": now.isoformat(),
            "last_error": f"{type(e).__name__}: {e}",
        })
        return {"ok": False, "error": str(e), "fetched": 0}

    results = []
    new_high_water = modified_after
    for order in orders:
        results.append(await process_order(order=order, service=service, store=store))
        # Advance high-water mark per-order so a mid-batch crash doesn't
        # lose progress.
        m = order.get("modifiedOn")
        if m:
            try:
                dt = datetime.fromisoformat(str(m).replace("Z", "+00:00"))
                if dt > new_high_water:
                    new_high_water = dt
            except ValueError:
                pass

    n_minted = sum(1 for r in results if r["status"] == "minted")
    n_duplicate = sum(1 for r in results if r["status"] == "duplicate")
    n_skipped = sum(1 for r in results if r["status"] == "skipped")

    await save_state(store, {
        "last_modified_at": new_high_water.isoformat(),
        "last_run_at": now.isoformat(),
        "last_error": "",
        "total_fetched_lifetime": int(state.get("total_fetched_lifetime", 0)) + len(orders),
        "total_minted_lifetime": int(state.get("total_minted_lifetime", 0)) + n_minted,
    })

    summary = {
        "ok": True,
        "fetched": len(orders),
        "minted": n_minted,
        "duplicate": n_duplicate,
        "skipped": n_skipped,
        "high_water": new_high_water.isoformat(),
        "results": results,
    }
    if orders:
        logger.info("[poller] %s", {k: v for k, v in summary.items() if k != "results"})
    return summary


# ---------------------------------------------------------------------------
# Background loop (started at app boot when cloud mode is on)
# ---------------------------------------------------------------------------
async def poll_forever(
    *,
    service: LicenseService,
    store: LicenseStore,
    interval_seconds: Optional[int] = None,
    shutdown: Optional[asyncio.Event] = None,
) -> None:
    """Run `run_once` on a schedule until `shutdown` is set. Errors are
    swallowed (logged, never raised) so the FastAPI process keeps serving."""
    interval = interval_seconds or config.squarespace_poll_interval_seconds()
    shutdown = shutdown or asyncio.Event()
    logger.info("[poller] starting Squarespace orders poll every %ss", interval)

    # Small jitter delay before the first run so multiple replicas don't
    # all hit the API at the same instant.
    try:
        await asyncio.wait_for(shutdown.wait(), timeout=5)
        return
    except asyncio.TimeoutError:
        pass

    while not shutdown.is_set():
        try:
            await run_once(service=service, store=store)
        except Exception as e:
            logger.exception("[poller] iteration crashed: %s", e)
        try:
            await asyncio.wait_for(shutdown.wait(), timeout=interval)
        except asyncio.TimeoutError:
            continue
