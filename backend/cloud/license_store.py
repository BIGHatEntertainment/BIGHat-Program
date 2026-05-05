"""MongoDB CRUD for the cloud licensing service.

Collections:
  * `license_keys`        — one row per customer (unique on `key` and `email`)
  * `license_webhook_events` — idempotency dedupe for Squarespace webhooks

The database handle is passed in from `server.py` at router registration.
All methods work against Motor's async API; they also work transparently
against MontyDB (so the same code is testable under the native SQLite shim).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from .license_models import LicenseKey, WebhookEvent

COLL_LICENSES = "license_keys"
COLL_WEBHOOKS = "license_webhook_events"


class LicenseStore:
    def __init__(self, db):
        self.db = db

    # ---- index setup (idempotent; call once on startup) ----
    async def ensure_indexes(self) -> None:
        # Motor supports create_index; MontyDB shim is a no-op.
        try:
            await self.db[COLL_LICENSES].create_index("key", unique=True)
            await self.db[COLL_LICENSES].create_index("email", unique=True)
            await self.db[COLL_WEBHOOKS].create_index("event_id", unique=True)
        except Exception:
            # Indexes may already exist, or shim may not support them — safe to skip.
            pass

    # ---- LicenseKey CRUD ----
    async def get_by_key(self, key: str) -> Optional[LicenseKey]:
        doc = await self.db[COLL_LICENSES].find_one({"key": key}, {"_id": 0})
        return LicenseKey(**doc) if doc else None

    async def get_by_email(self, email: str) -> Optional[LicenseKey]:
        doc = await self.db[COLL_LICENSES].find_one({"email": email.lower()}, {"_id": 0})
        return LicenseKey(**doc) if doc else None

    async def insert(self, lic: LicenseKey) -> None:
        doc = lic.model_dump(mode="json")
        # Store email always lower-case for case-insensitive uniqueness.
        doc["email"] = doc["email"].lower()
        await self.db[COLL_LICENSES].insert_one(doc)

    async def update(self, key: str, updates: dict[str, Any]) -> Optional[LicenseKey]:
        updates = dict(updates)  # don't mutate caller
        updates["updated_at"] = datetime.now(timezone.utc).isoformat()
        await self.db[COLL_LICENSES].update_one({"key": key}, {"$set": updates})
        return await self.get_by_key(key)

    async def list_all(self, *, limit: int = 100, offset: int = 0) -> list[LicenseKey]:
        cursor = self.db[COLL_LICENSES].find({}, {"_id": 0}).skip(offset).limit(limit)
        docs = await cursor.to_list(length=limit)
        return [LicenseKey(**d) for d in docs]

    async def count(self) -> int:
        return await self.db[COLL_LICENSES].count_documents({})

    # ---- Webhook idempotency ----
    async def already_processed(self, event_id: str) -> bool:
        doc = await self.db[COLL_WEBHOOKS].find_one({"event_id": event_id}, {"_id": 0})
        return bool(doc and doc.get("processed"))

    async def record_event(self, evt: WebhookEvent) -> None:
        doc = evt.model_dump(mode="json")
        try:
            await self.db[COLL_WEBHOOKS].insert_one(doc)
        except Exception:
            # Duplicate event_id (race) — safe to ignore; idempotent.
            pass

    async def mark_processed(self, event_id: str) -> None:
        await self.db[COLL_WEBHOOKS].update_one(
            {"event_id": event_id},
            {"$set": {"processed": True}},
        )
