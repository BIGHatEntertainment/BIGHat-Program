"""Pydantic models for the cloud licensing service.

Two kinds of models:
  * Stored records (MongoDB)    — `LicenseKey`, `WebhookEvent`
  * Transport DTOs (HTTP layer) — request/response bodies
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field

CloudLibraryStatus = Literal["inactive", "active", "past_due", "canceled"]


# ---------- Stored records ----------
class HwidBinding(BaseModel):
    """A single (key, machine) activation record."""
    hwid: str
    machine_name: str = ""
    activated_at: datetime
    last_seen_at: Optional[datetime] = None


class LicenseKey(BaseModel):
    """Canonical per-customer license record. ONE key per customer email;
    adding a new purchase extends the existing key rather than minting new."""
    model_config = ConfigDict(populate_by_name=True)

    key: str                                             # BHE-XXXX-XXXX-XXXX-XXXX
    email: EmailStr
    owns_standalone: bool = False
    owns_music_bingo: bool = False
    owns_karaoke: bool = False
    cloud_library_status: CloudLibraryStatus = "inactive"
    cloud_library_expires_at: Optional[datetime] = None
    max_seats: int = 3
    active_hwids: List[HwidBinding] = Field(default_factory=list)
    squarespace_customer_id: Optional[str] = None
    squarespace_standalone_order_id: Optional[str] = None
    squarespace_music_bingo_order_id: Optional[str] = None
    squarespace_karaoke_order_id: Optional[str] = None
    squarespace_subscription_id: Optional[str] = None
    revoked: bool = False
    revocation_reason: str = ""
    created_at: datetime
    updated_at: datetime


class WebhookEvent(BaseModel):
    """Idempotency record for Squarespace webhook dedupe."""
    event_id: str            # Squarespace's own event ID (or a hash fallback)
    topic: str
    received_at: datetime
    processed: bool = False
    raw_payload: dict


# ---------- Transport DTOs ----------
class ActivateRequest(BaseModel):
    key: str
    hwid: str
    machine_name: str = ""
    email: Optional[EmailStr] = None  # optional bonus verification


class ActivateResponse(BaseModel):
    ok: bool
    message: str
    owns_standalone: bool
    owns_music_bingo: bool = False
    owns_karaoke: bool = False
    cloud_library_active: bool
    cloud_library_expires_at: Optional[datetime] = None
    max_seats: int
    active_seats: int
    revalidate_after: datetime        # when the client should next call /validate


class ValidateRequest(BaseModel):
    key: str
    hwid: str


class ValidateResponse(BaseModel):
    ok: bool
    owns_standalone: bool
    owns_music_bingo: bool = False
    owns_karaoke: bool = False
    cloud_library_active: bool
    cloud_library_expires_at: Optional[datetime] = None
    revoked: bool
    revalidate_after: datetime


class DeactivateRequest(BaseModel):
    key: str
    hwid: str


class StatusResponse(BaseModel):
    """Public status lookup — redacts sensitive fields."""
    key_masked: str
    owns_standalone: bool
    owns_music_bingo: bool = False
    owns_karaoke: bool = False
    cloud_library_status: CloudLibraryStatus
    active_seats: int
    max_seats: int


class DownloadInfo(BaseModel):
    platform: Literal["windows", "macos", "macos_apple", "macos_intel"]
    url: str
    version: str
    sha256: Optional[str] = None


class MintKeyRequest(BaseModel):
    """Admin-only: manual key minting for support / comp / gifts."""
    email: EmailStr
    owns_standalone: bool = True
    owns_music_bingo: bool = False
    owns_karaoke: bool = False
    cloud_library_months: int = 0         # grants N months of subscription
    note: str = ""


class AdminKeyView(BaseModel):
    """Admin-only list/detail view of a license key."""
    key: str
    email: EmailStr
    owns_standalone: bool
    owns_music_bingo: bool = False
    owns_karaoke: bool = False
    cloud_library_status: CloudLibraryStatus
    cloud_library_expires_at: Optional[datetime] = None
    max_seats: int
    active_seats: int
    revoked: bool
    created_at: datetime
    updated_at: datetime


class AdminLoginRequest(BaseModel):
    email: EmailStr
    password: str


class AdminTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ---------- Squarespace webhook payload (minimal subset) ----------
class SquarespaceWebhookEnvelope(BaseModel):
    """The envelope structure Squarespace POSTs to our webhook URL.

    Squarespace sends the event metadata; we then usually have to GET
    the full order via their API. We accept both shapes here."""
    model_config = ConfigDict(extra="allow")

    # New-style: {"id": "evt_...", "topic": "order.create", "data": {...}}
    id: Optional[str] = None
    topic: Optional[str] = None
    data: Optional[dict] = None
    # Old-style field alternatives
    websiteId: Optional[str] = None
    storeOrderId: Optional[str] = None
