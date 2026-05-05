"""Squarespace Commerce webhook handling.

Squarespace signs every webhook POST with an HMAC-SHA256 header:
    `Squarespace-Signature: t=<unix>,v1=<hex-hmac>`
We verify the signature against our shared secret, then dispatch on the
`topic` field:
    * `order.create`              → standalone purchase (SKU=BH-STANDALONE-*)
                                     or cloud-library start (SKU=BH-CLOUD-LIBRARY-*)
    * `order.update`              → re-fetch & replay mint if not already processed
    * `extensions.order.update`   → some plans emit only this
    * `subscription.cancel`       → cancel_cloud_subscription

The webhook is idempotent: we record every event_id in `license_webhook_events`
and short-circuit replays. We never raise 500 on unknown topics — return 200
so Squarespace doesn't retry forever.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from . import config
from .license_models import WebhookEvent
from .license_service import LicenseService
from .license_store import LicenseStore

logger = logging.getLogger("bighat-license-webhook")


# ---------- signature verification ----------
def verify_signature(*, body: bytes, signature_header: str, secret: Optional[str] = None) -> bool:
    """Compare the provided `Squarespace-Signature` header against a fresh
    HMAC-SHA256 of the raw body. Returns False on any mismatch or on missing
    secret/header.

    We accept two header styles:
        1. Raw hex:           'abcdef…'
        2. Timestamp+sig:     't=1700000000,v1=abcdef…'
    """
    secret = secret if secret is not None else config.squarespace_webhook_secret()
    if not secret or not signature_header:
        return False

    # Parse header. Fall back to raw hex if no '=' present.
    provided_hex = signature_header.strip()
    if "," in provided_hex or "=" in provided_hex:
        parts = dict(
            p.split("=", 1) for p in provided_hex.split(",") if "=" in p
        )
        provided_hex = parts.get("v1") or parts.get("signature") or ""

    expected = hmac.new(
        secret.encode("utf-8"), body, hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(provided_hex.lower(), expected.lower())


# ---------- payload shape probing ----------
def _extract_event_id(payload: dict[str, Any]) -> str:
    """Find a stable id to dedupe on. Prefer Squarespace's `id`; fall back
    to a hash of the payload."""
    eid = payload.get("id") or payload.get("eventId")
    if eid:
        return str(eid)
    # Stable fallback: hash of body. Same payload → same id → dedup.
    raw = repr(sorted(payload.items()))
    return "sha_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _extract_topic(payload: dict[str, Any]) -> str:
    return str(payload.get("topic") or payload.get("type") or "").lower()


def _extract_order(payload: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Squarespace payloads may nest the order under `data.order`, `order`,
    or emit it at the top level. Probe all three."""
    data = payload.get("data")
    if isinstance(data, dict):
        if isinstance(data.get("order"), dict):
            return data["order"]
        # data itself may BE the order
        if "lineItems" in data or "customerEmail" in data:
            return data
    if isinstance(payload.get("order"), dict):
        return payload["order"]
    if "lineItems" in payload or "customerEmail" in payload:
        return payload
    return None


def _iter_skus(order: dict[str, Any]) -> list[str]:
    """Collect all SKUs across the order's line items."""
    skus: list[str] = []
    for li in order.get("lineItems") or []:
        sku = li.get("sku") or li.get("SKU") or ""
        if sku:
            skus.append(str(sku))
    return skus


def _customer_email(order: dict[str, Any]) -> Optional[str]:
    return (
        order.get("customerEmail")
        or order.get("email")
        or (order.get("billingAddress") or {}).get("email")
    )


def _customer_id(order: dict[str, Any]) -> str:
    return str(order.get("customerId") or order.get("customerIdentifier") or "")


def _order_id(order: dict[str, Any]) -> str:
    return str(order.get("id") or order.get("orderNumber") or "")


def _subscription_id(payload: dict[str, Any]) -> str:
    # Subscription topics nest differently; probe a few locations.
    data = payload.get("data") or {}
    return str(
        payload.get("subscriptionId")
        or data.get("subscriptionId")
        or (data.get("subscription") or {}).get("id")
        or ""
    )


def _subscription_customer_email(payload: dict[str, Any]) -> Optional[str]:
    data = payload.get("data") or {}
    sub = data.get("subscription") or {}
    return sub.get("customerEmail") or data.get("customerEmail") or payload.get("customerEmail")


# ---------- handler ----------
class WebhookHandler:
    def __init__(self, service: LicenseService, store: LicenseStore):
        self.service = service
        self.store = store

    async def handle(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Dispatch a parsed payload. Returns a small status dict; caller
        converts to a FastAPI JSONResponse."""
        event_id = _extract_event_id(payload)
        topic = _extract_topic(payload)

        # Idempotency: short-circuit replays.
        if await self.store.already_processed(event_id):
            logger.info("[webhook] replay event_id=%s topic=%s; skip", event_id, topic)
            return {"ok": True, "status": "duplicate", "event_id": event_id}

        await self.store.record_event(WebhookEvent(
            event_id=event_id, topic=topic or "unknown",
            received_at=datetime.now(timezone.utc),
            raw_payload=payload,
        ))

        result: dict[str, Any] = {"ok": True, "event_id": event_id, "topic": topic}

        if topic in ("order.create", "order.update", "extensions.order.update"):
            order = _extract_order(payload)
            if not order:
                result["status"] = "no_order_in_payload"
            else:
                result.update(await self._dispatch_order(order))
        elif topic in ("subscription.cancel", "subscription.canceled"):
            sub_id = _subscription_id(payload)
            if not sub_id:
                result["status"] = "no_subscription_id"
            else:
                lic = await self.service.cancel_cloud_subscription(subscription_id=sub_id)
                result["status"] = "subscription_canceled" if lic else "subscription_unknown"
        else:
            logger.info("[webhook] ignoring topic=%r", topic)
            result["status"] = "ignored"

        await self.store.mark_processed(event_id)
        return result

    async def _dispatch_order(self, order: dict[str, Any]) -> dict[str, Any]:
        email = _customer_email(order)
        order_id = _order_id(order)
        customer_id = _customer_id(order)
        if not email or not order_id:
            return {"status": "missing_email_or_order_id"}

        skus = _iter_skus(order)
        minted: list[str] = []
        # Multiple line items may be in one order — process each.
        for sku in skus:
            if sku == config.SKU_STANDALONE:
                lic = await self.service.mint_standalone_purchase(
                    email=email, order_id=order_id, customer_id=customer_id,
                )
                minted.append(f"standalone:{lic.key}")
            elif sku == config.SKU_CLOUD_LIBRARY:
                # For a subscription start we use order_id as subscription_id
                # when Squarespace didn't surface a separate one.
                lic = await self.service.mint_cloud_subscription(
                    email=email, subscription_id=order_id,
                    months=1, customer_id=customer_id,
                )
                minted.append(f"cloud:{lic.key}")
            else:
                logger.info("[webhook] ignoring unknown sku=%r in order=%s", sku, order_id)

        if not minted:
            return {"status": "no_matching_skus", "skus": skus}
        return {"status": "minted", "results": minted}
