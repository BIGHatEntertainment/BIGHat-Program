from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List
from datetime import datetime
import uuid


# ============ SPONSOR MODELS ============
class SponsorBase(BaseModel):
    business_name: str
    email: str
    contact_name: Optional[str] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    zip_code: Optional[str] = None
    package: Optional[str] = None
    tier: Optional[str] = None  # bronze, silver, gold
    status: str = "inactive"
    notes: Optional[str] = None
    logo: Optional[str] = None
    picture: Optional[str] = None
    is_venue_sponsor: bool = False


class SponsorCreate(SponsorBase):
    pass


class SponsorUpdate(BaseModel):
    business_name: Optional[str] = None
    email: Optional[str] = None
    contact_name: Optional[str] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    zip_code: Optional[str] = None
    package: Optional[str] = None
    tier: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None
    logo: Optional[str] = None
    picture: Optional[str] = None
    is_venue_sponsor: Optional[bool] = None


class Sponsor(SponsorBase):
    model_config = ConfigDict(extra="ignore")
    
    id: str = Field(default_factory=lambda: f"sponsor_{uuid.uuid4().hex[:12]}")
    assets_count: int = 0
    joined_at: str = Field(default_factory=lambda: datetime.utcnow().strftime("%Y-%m-%d"))
    user_id: Optional[str] = None  # Link to registered user account


# ============ LOCATION MODELS ============
class LocationBase(BaseModel):
    name: str
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    capacity_tier: Optional[str] = "> 50"  # '< 50', '> 50', '100+'
    day_of_week: Optional[str] = None
    time: Optional[str] = None
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    notes: Optional[str] = None
    status: str = "active"


class LocationCreate(LocationBase):
    pass


class LocationUpdate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    capacity_tier: Optional[str] = None
    day_of_week: Optional[str] = None
    time: Optional[str] = None
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = None


class Location(LocationBase):
    model_config = ConfigDict(extra="ignore")
    
    id: str = Field(default_factory=lambda: f"loc_{uuid.uuid4().hex[:12]}")


# ============ ASSET MODELS ============
class AssetBase(BaseModel):
    name: str
    type: str  # "16:9" or "1:1"
    file_url: Optional[str] = None
    file_data: Optional[str] = None  # Base64 for now, will migrate to proper storage
    status: str = "pending"  # pending, approved, rejected, revision_requested
    notes: Optional[str] = None
    is_preferred: bool = False  # Whether this is the preferred asset for its type


class AssetCreate(AssetBase):
    sponsor_id: Optional[str] = None
    sponsor_name: Optional[str] = None
    sponsor_email: Optional[str] = None


class AssetUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    file_url: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None
    is_preferred: Optional[bool] = None


class Asset(AssetBase):
    model_config = ConfigDict(extra="ignore")
    
    id: str = Field(default_factory=lambda: f"asset_{uuid.uuid4().hex[:12]}")
    sponsor_id: Optional[str] = None
    sponsor_name: Optional[str] = None
    sponsor_email: Optional[str] = None
    uploaded_at: str = Field(default_factory=lambda: datetime.utcnow().strftime("%Y-%m-%d"))


class PendingApproval(Asset):
    """Asset pending admin approval"""
    asset_name: Optional[str] = None


# ============ SUBSCRIPTION MODELS ============
class SubscriptionBase(BaseModel):
    package_id: str
    package_name: str
    price: float
    status: str = "active"


class SubscriptionCreate(SubscriptionBase):
    user_id: str


class Subscription(SubscriptionBase):
    model_config = ConfigDict(extra="ignore")
    
    id: str = Field(default_factory=lambda: f"sub_{uuid.uuid4().hex[:12]}")
    user_id: str
    purchased_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    start_date: str = Field(default_factory=lambda: datetime.utcnow().strftime("%Y-%m-%d"))
    end_date: Optional[str] = None  # Will be calculated


# ============ REGISTERED ACCOUNT MODELS ============
class RegisteredAccountBase(BaseModel):
    email: str
    business_name: Optional[str] = None
    contact_name: Optional[str] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    zip_code: Optional[str] = None  # Required for local discounts validation


class RegisteredAccountCreate(RegisteredAccountBase):
    password_hash: Optional[str] = None  # For email/password signups
    must_reset_password: bool = False  # True for admin-created accounts
    created_by_admin: bool = False  # Track if admin created this account
    google_linked: bool = False  # True if Google auth is linked


class RegisteredAccountUpdate(BaseModel):
    business_name: Optional[str] = None
    contact_name: Optional[str] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    zip_code: Optional[str] = None


class RegisteredAccount(RegisteredAccountBase):
    model_config = ConfigDict(extra="ignore")
    
    id: str = Field(default_factory=lambda: f"acc_{uuid.uuid4().hex[:12]}")
    registered_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    user_id: Optional[str] = None  # Link to auth user if logged in via Google
    must_reset_password: bool = False  # True if user must reset password on first login
    created_by_admin: bool = False  # True if admin created this account
    google_linked: bool = False  # True if Google auth is linked to this account


# ============ SPONSOR PLACEMENT MODELS ============
# Placement types for the visibility matrix
PLACEMENT_TYPES = [
    {"id": "preshow_16x9", "name": "16:9 Pre-Show", "asset_type": "16:9"},
    {"id": "round1_overlay", "name": "Round 1 Overlay", "asset_type": "1:1"},
    {"id": "round2_overlay", "name": "Round 2 Overlay", "asset_type": "1:1"},
    {"id": "round3_overlay", "name": "Round 3 Overlay", "asset_type": "1:1"},
    {"id": "mystery_overlay", "name": "Mystery Round Overlay", "asset_type": "1:1"},
    {"id": "sponsor_section_16x9", "name": "16:9 Sponsor Section", "asset_type": "16:9"},
    {"id": "sponsor_logo_only", "name": "1:1 Sponsor Section (Logo Only)", "asset_type": "1:1"},
    {"id": "sponsor_logo_detail", "name": "1:1 Sponsor Section (Logo & Detail)", "asset_type": "1:1"},
    {"id": "thank_you", "name": "Thank You Section", "asset_type": "1:1"},
]


class SponsorPlacementBase(BaseModel):
    sponsor_id: str
    location_id: str
    placement_type: str  # One of the PLACEMENT_TYPES ids
    enabled: bool = False


class SponsorPlacementCreate(SponsorPlacementBase):
    pass


class SponsorPlacementUpdate(BaseModel):
    enabled: bool


class SponsorPlacement(SponsorPlacementBase):
    model_config = ConfigDict(extra="ignore")
    
    id: str = Field(default_factory=lambda: f"placement_{uuid.uuid4().hex[:12]}")
    updated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class SponsorPlacementMatrix(BaseModel):
    """Matrix data for a sponsor showing all placements across all locations"""
    sponsor_id: str
    sponsor_name: str
    locations: List[dict]  # List of {id, name}
    placement_types: List[dict]  # List of PLACEMENT_TYPES
    placements: dict  # {location_id: {placement_type: enabled}}

