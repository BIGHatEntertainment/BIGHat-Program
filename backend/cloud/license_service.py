"""Business logic for cloud licensing.

Stateless service class; persists through `LicenseStore`. Email side-effects
live in `email_service` and are injected via the `EmailSender` protocol so
tests can substitute a capturing fake.
"""
from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Protocol

from . import config
from .license_models import (
    HwidBinding,
    LicenseKey,
)
from .license_store import LicenseStore

logger = logging.getLogger("bighat-license")


class EmailSender(Protocol):
    async def send_license_key_email(self, *, to: str, key: str, owns_standalone: bool,
                                     cloud_library_active: bool,
                                     owns_music_bingo: bool = False,
                                     owns_karaoke: bool = False) -> bool: ...
    async def send_subscription_canceled(self, *, to: str, key: str) -> bool: ...


# ---- pure helpers ----
def generate_key() -> str:
    """Return `BHE-XXXX-XXXX-XXXX-XXXX` using an alphabet with no ambiguous chars."""
    groups = []
    for _ in range(config.LICENSE_KEY_GROUP_COUNT):
        groups.append("".join(
            secrets.choice(config.LICENSE_KEY_ALPHABET)
            for _ in range(config.LICENSE_KEY_GROUP_LEN)
        ))
    return f"{config.LICENSE_KEY_PREFIX}-" + "-".join(groups)


def mask_key(key: str) -> str:
    """Return e.g. 'BHE-****-****-****-ABCD' for public status responses."""
    if not key or "-" not in key:
        return "****"
    parts = key.split("-")
    masked = [parts[0]]
    for p in parts[1:-1]:
        masked.append("*" * len(p))
    masked.append(parts[-1])
    return "-".join(masked)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _extend_subscription(current: Optional[datetime], months: int) -> datetime:
    """Add N months (approx 30d each) to the greater of now and `current`."""
    base = current if current and current > now_utc() else now_utc()
    return base + timedelta(days=30 * max(1, months))


class LicenseService:
    def __init__(self, store: LicenseStore, email_sender: Optional[EmailSender] = None):
        self.store = store
        self.email = email_sender

    # ---- minting (webhook-driven) ----
    async def mint_standalone_purchase(
        self,
        *,
        email: str,
        order_id: str,
        customer_id: str = "",
    ) -> LicenseKey:
        """Called from Squarespace `order.create` webhook for the $24.99 SKU.

        Idempotent on (email, order_id): re-posting the same order returns
        the existing key unchanged."""
        existing = await self.store.get_by_email(email)
        if existing and existing.squarespace_standalone_order_id == order_id:
            logger.info("[license] standalone purchase replay for %s; no-op", email)
            return existing

        if existing:
            # Customer already has a key (e.g. from a prior subscription); upgrade it.
            updates = {
                "owns_standalone": True,
                "squarespace_standalone_order_id": order_id,
            }
            if customer_id:
                updates["squarespace_customer_id"] = customer_id
            updated = await self.store.update(existing.key, updates)
            assert updated is not None
            if self.email:
                await self.email.send_license_key_email(
                    to=updated.email, key=updated.key,
                    owns_standalone=True,
                    cloud_library_active=updated.cloud_library_status == "active",
                    owns_music_bingo=updated.owns_music_bingo,
                    owns_karaoke=updated.owns_karaoke,
                )
            return updated

        # Fresh customer: mint a new key.
        now = now_utc()
        lic = LicenseKey(
            key=generate_key(),
            email=email.lower(),
            owns_standalone=True,
            cloud_library_status="inactive",
            max_seats=config.DEFAULT_MAX_SEATS,
            squarespace_standalone_order_id=order_id,
            squarespace_customer_id=customer_id or None,
            created_at=now,
            updated_at=now,
        )
        await self.store.insert(lic)
        if self.email:
            await self.email.send_license_key_email(
                to=lic.email, key=lic.key,
                owns_standalone=True, cloud_library_active=False,
                owns_music_bingo=False, owns_karaoke=False,
            )
        logger.info("[license] minted standalone key for %s", email)
        return lic

    async def mint_cloud_subscription(
        self,
        *,
        email: str,
        subscription_id: str,
        months: int = 1,
        customer_id: str = "",
    ) -> LicenseKey:
        """Called from Squarespace subscription webhook ($5/mo).
        Idempotent on subscription_id."""
        existing = await self.store.get_by_email(email)
        if existing and existing.squarespace_subscription_id == subscription_id \
                and existing.cloud_library_status == "active":
            logger.info("[license] subscription replay for %s; no-op", email)
            return existing

        new_expires = _extend_subscription(
            existing.cloud_library_expires_at if existing else None,
            months,
        )

        if existing:
            updated = await self.store.update(existing.key, {
                "cloud_library_status": "active",
                "cloud_library_expires_at": new_expires.isoformat(),
                "squarespace_subscription_id": subscription_id,
                "max_seats": max(existing.max_seats, config.CLOUD_LIBRARY_MAX_SEATS),
                **({"squarespace_customer_id": customer_id} if customer_id else {}),
            })
            assert updated is not None
            if self.email:
                await self.email.send_license_key_email(
                    to=updated.email, key=updated.key,
                    owns_standalone=updated.owns_standalone,
                    cloud_library_active=True,
                    owns_music_bingo=updated.owns_music_bingo,
                    owns_karaoke=updated.owns_karaoke,
                )
            return updated

        # First interaction with this customer is a subscription; mint a fresh key
        # with owns_standalone=False. They may buy the standalone product later.
        now = now_utc()
        lic = LicenseKey(
            key=generate_key(),
            email=email.lower(),
            owns_standalone=False,
            cloud_library_status="active",
            cloud_library_expires_at=new_expires,
            max_seats=config.CLOUD_LIBRARY_MAX_SEATS,
            squarespace_subscription_id=subscription_id,
            squarespace_customer_id=customer_id or None,
            created_at=now,
            updated_at=now,
        )
        await self.store.insert(lic)
        if self.email:
            await self.email.send_license_key_email(
                to=lic.email, key=lic.key,
                owns_standalone=False, cloud_library_active=True,
                owns_music_bingo=False, owns_karaoke=False,
            )
        logger.info("[license] minted subscription-only key for %s", email)
        return lic

    async def mint_addon_purchase(
        self,
        *,
        addon: str,                # "music_bingo" or "karaoke"
        email: str,
        order_id: str,
        customer_id: str = "",
    ) -> LicenseKey:
        """Webhook-driven add-on purchase (one-time, non-subscription).
        Idempotent on (email, order_id).

        Add-ons require the customer to also own the standalone base to
        actually function — but we accept the purchase even if they haven't
        bought the base yet (cloud just records ownership; desktop gates).
        """
        if addon not in ("music_bingo", "karaoke"):
            raise ValueError(f"unknown addon: {addon!r}")
        owns_field = f"owns_{addon}"
        order_field = f"squarespace_{addon}_order_id"

        existing = await self.store.get_by_email(email)
        if existing and getattr(existing, order_field) == order_id:
            logger.info("[license] %s purchase replay for %s; no-op", addon, email)
            return existing

        if existing:
            updates = {owns_field: True, order_field: order_id}
            if customer_id:
                updates["squarespace_customer_id"] = customer_id
            updated = await self.store.update(existing.key, updates)
            assert updated is not None
            if self.email:
                await self.email.send_license_key_email(
                    to=updated.email, key=updated.key,
                    owns_standalone=updated.owns_standalone,
                    cloud_library_active=updated.cloud_library_status == "active",
                    owns_music_bingo=updated.owns_music_bingo,
                    owns_karaoke=updated.owns_karaoke,
                )
            return updated

        # Fresh customer who's only buying an add-on first (rare but possible).
        now = now_utc()
        lic_kwargs = {
            "key": generate_key(),
            "email": email.lower(),
            "owns_standalone": False,
            "cloud_library_status": "inactive",
            "max_seats": config.DEFAULT_MAX_SEATS,
            "squarespace_customer_id": customer_id or None,
            "created_at": now,
            "updated_at": now,
            owns_field: True,
            order_field: order_id,
        }
        lic = LicenseKey(**lic_kwargs)
        await self.store.insert(lic)
        if self.email:
            await self.email.send_license_key_email(
                to=lic.email, key=lic.key,
                owns_standalone=False, cloud_library_active=False,
                owns_music_bingo=lic.owns_music_bingo,
                owns_karaoke=lic.owns_karaoke,
            )
        logger.info("[license] minted addon-only key for %s (addon=%s)", email, addon)
        return lic

    # ---- minting (webhook-driven) — Cloud Library subscription ----
    async def cancel_cloud_subscription(self, *, subscription_id: str) -> Optional[LicenseKey]:
        # Find the key by subscription_id. Iterate (volume is tiny in early SaaS).
        cursor = self.store.db["license_keys"].find(
            {"squarespace_subscription_id": subscription_id}, {"_id": 0},
        )
        docs = await cursor.to_list(length=1)
        if not docs:
            logger.warning("[license] subscription cancel for unknown sub_id=%s", subscription_id)
            return None
        lic = LicenseKey(**docs[0])
        updated = await self.store.update(lic.key, {"cloud_library_status": "canceled"})
        if self.email and updated:
            await self.email.send_subscription_canceled(to=updated.email, key=updated.key)
        logger.info("[license] canceled subscription for %s", lic.email)
        return updated

    # ---- desktop-app lifecycle ----
    async def activate(self, *, key: str, hwid: str, machine_name: str = "") -> tuple[bool, str, Optional[LicenseKey]]:
        """Bind an HWID to a key (or confirm an existing binding).
        Returns (ok, message, updated_key)."""
        lic = await self.store.get_by_key(key)
        if not lic:
            return False, "unknown_key", None
        if lic.revoked:
            return False, f"revoked: {lic.revocation_reason or 'contact support'}", lic

        now = now_utc()
        existing = next((h for h in lic.active_hwids if h.hwid == hwid), None)
        if existing:
            existing.last_seen_at = now
            new_hwids = [h.model_dump(mode="json") for h in lic.active_hwids]
            await self.store.update(key, {"active_hwids": new_hwids})
            updated = await self.store.get_by_key(key)
            return True, "already_activated", updated

        if len(lic.active_hwids) >= lic.max_seats:
            return False, f"seat_limit_reached ({lic.max_seats})", lic

        binding = HwidBinding(
            hwid=hwid, machine_name=machine_name,
            activated_at=now, last_seen_at=now,
        )
        new_hwids = [h.model_dump(mode="json") for h in lic.active_hwids] + [binding.model_dump(mode="json")]
        updated = await self.store.update(key, {"active_hwids": new_hwids})
        return True, "activated", updated

    async def deactivate(self, *, key: str, hwid: str) -> tuple[bool, str]:
        lic = await self.store.get_by_key(key)
        if not lic:
            return False, "unknown_key"
        new_hwids = [h for h in lic.active_hwids if h.hwid != hwid]
        if len(new_hwids) == len(lic.active_hwids):
            return False, "hwid_not_found"
        await self.store.update(key, {
            "active_hwids": [h.model_dump(mode="json") for h in new_hwids],
        })
        return True, "deactivated"

    async def validate(self, *, key: str, hwid: str) -> tuple[bool, str, Optional[LicenseKey]]:
        lic = await self.store.get_by_key(key)
        if not lic:
            return False, "unknown_key", None
        if lic.revoked:
            return False, "revoked", lic
        if not any(h.hwid == hwid for h in lic.active_hwids):
            return False, "hwid_not_activated", lic

        # Touch last_seen_at on the matching binding.
        now = now_utc()
        for h in lic.active_hwids:
            if h.hwid == hwid:
                h.last_seen_at = now
        await self.store.update(key, {
            "active_hwids": [h.model_dump(mode="json") for h in lic.active_hwids],
        })
        return True, "ok", lic

    # ---- admin ops ----
    async def mint_manual(
        self,
        *,
        email: str,
        owns_standalone: bool,
        cloud_library_months: int,
        owns_music_bingo: bool = False,
        owns_karaoke: bool = False,
        note: str = "",
        send_email: bool = True,
        key: Optional[str] = None,
    ) -> LicenseKey:
        """Support/comp/restore path — create a key outside any purchase flow.

        When `key` is provided, that exact value is used (used by the
        `/api/license/admin/keys/restore` endpoint to put a lost license back
        in the DB after a data-wipe, preserving the customer's existing
        email-with-key on file). When omitted, a fresh key is generated.

        When `send_email=True` (default), the customer receives a license-key
        email identical to the one generated by the Squarespace poller. Pass
        `send_email=False` for restores where the customer already has the
        key in hand and a duplicate email would be confusing.
        """
        existing = await self.store.get_by_email(email)
        now = now_utc()
        if existing:
            updates: dict = {
                "owns_standalone":   existing.owns_standalone or owns_standalone,
                "owns_music_bingo":  existing.owns_music_bingo or owns_music_bingo,
                "owns_karaoke":      existing.owns_karaoke or owns_karaoke,
            }
            if cloud_library_months > 0:
                updates["cloud_library_expires_at"] = _extend_subscription(
                    existing.cloud_library_expires_at, cloud_library_months,
                ).isoformat()
                updates["cloud_library_status"] = "active"
            if note:
                updates["revocation_reason"] = ""  # reusing; leave note in logs only
            updated = await self.store.update(existing.key, updates)
            assert updated is not None
            logger.info("[license] admin updated key for %s (note=%s)", email, note)
            if send_email and self.email:
                await self.email.send_license_key_email(
                    to=updated.email, key=updated.key,
                    owns_standalone=updated.owns_standalone,
                    cloud_library_active=updated.cloud_library_status == "active",
                    owns_music_bingo=updated.owns_music_bingo,
                    owns_karaoke=updated.owns_karaoke,
                )
            return updated

        lic = LicenseKey(
            key=key or generate_key(),
            email=email.lower(),
            owns_standalone=owns_standalone,
            owns_music_bingo=owns_music_bingo,
            owns_karaoke=owns_karaoke,
            cloud_library_status="active" if cloud_library_months > 0 else "inactive",
            cloud_library_expires_at=(
                _extend_subscription(None, cloud_library_months) if cloud_library_months > 0 else None
            ),
            max_seats=(
                config.CLOUD_LIBRARY_MAX_SEATS if cloud_library_months > 0
                else config.DEFAULT_MAX_SEATS
            ),
            created_at=now,
            updated_at=now,
        )
        await self.store.insert(lic)
        logger.info("[license] admin minted key for %s (note=%s)", email, note)
        if send_email and self.email:
            await self.email.send_license_key_email(
                to=lic.email, key=lic.key,
                owns_standalone=lic.owns_standalone,
                cloud_library_active=lic.cloud_library_status == "active",
                owns_music_bingo=lic.owns_music_bingo,
                owns_karaoke=lic.owns_karaoke,
            )
        return lic

    async def resend_license_email(self, *, key: str) -> tuple[bool, str]:
        """Look up a license by key and re-send its purchase email. Used by
        the support tooling when a customer reports they didn't receive (or
        lost) the original email. Returns (ok, message)."""
        lic = await self.store.get_by_key(key)
        if not lic:
            return False, "unknown_key"
        if not self.email:
            return False, "email_service_not_configured"
        await self.email.send_license_key_email(
            to=lic.email, key=lic.key,
            owns_standalone=lic.owns_standalone,
            cloud_library_active=lic.cloud_library_status == "active",
            owns_music_bingo=lic.owns_music_bingo,
            owns_karaoke=lic.owns_karaoke,
        )
        logger.info("[license] resent key email for %s", lic.email)
        return True, "sent"

    async def revoke(self, *, key: str, reason: str = "") -> Optional[LicenseKey]:
        lic = await self.store.get_by_key(key)
        if not lic:
            return None
        return await self.store.update(key, {"revoked": True, "revocation_reason": reason})
