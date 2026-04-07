from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
from datetime import datetime
import logging
import uuid

from models.schemas import Sponsor, SponsorCreate, SponsorUpdate
from database import db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sponsors", tags=["sponsors"])


@router.get("", response_model=List[Sponsor])
async def get_sponsors(
    status: Optional[str] = Query(None, description="Filter by status"),
    package: Optional[str] = Query(None, description="Filter by package")
):
    """Get all sponsors with optional filtering"""
    query = {}
    if status:
        query["status"] = status
    if package:
        query["package"] = package
    
    sponsors = await db.sponsors.find(query, {"_id": 0}).to_list(1000)
    return sponsors


@router.get("/{sponsor_id}", response_model=Sponsor)
async def get_sponsor(sponsor_id: str):
    """Get a specific sponsor by ID"""
    sponsor = await db.sponsors.find_one({"id": sponsor_id}, {"_id": 0})
    if not sponsor:
        raise HTTPException(status_code=404, detail="Sponsor not found")
    return sponsor


@router.post("", response_model=Sponsor)
async def create_sponsor(sponsor_data: SponsorCreate):
    """Create a new sponsor"""
    sponsor = Sponsor(**sponsor_data.model_dump())
    sponsor_dict = sponsor.model_dump()
    
    # Normalize email to lowercase
    if sponsor_dict.get("email"):
        sponsor_dict["email"] = sponsor_dict["email"].lower()
    
    # Auto-set tier based on package (only if package is provided)
    package = sponsor_dict.get("package") or ""
    package_lower = package.lower() if package else ""
    if "star" in package_lower or "gold" in package_lower or "platinum" in package_lower or "premium" in package_lower:
        sponsor_dict["tier"] = "gold"
    elif "silver" in package_lower or "standard" in package_lower:
        sponsor_dict["tier"] = "silver"
    elif "bronze" in package_lower or "basic" in package_lower:
        sponsor_dict["tier"] = "bronze"
    # If no package specified, tier remains None (inactive sponsor)
    
    # Check if sponsor with same email exists
    existing = await db.sponsors.find_one({"email": sponsor_dict["email"]}, {"_id": 0})
    if existing:
        raise HTTPException(status_code=400, detail="Sponsor with this email already exists")
    
    # Try to auto-link to existing registered account
    if sponsor_dict.get("email"):
        account = await db.registered_accounts.find_one(
            {"email": sponsor_dict["email"]},
            {"_id": 0}
        )
        if account:
            sponsor_dict["user_id"] = account.get("id")
            logger.info(f"Auto-linked sponsor to existing account: {account.get('id')}")
    
    await db.sponsors.insert_one(sponsor_dict)
    logger.info(f"Created sponsor: {sponsor_dict['business_name']}")
    return Sponsor(**sponsor_dict)


@router.put("/{sponsor_id}", response_model=Sponsor)
async def update_sponsor(sponsor_id: str, updates: SponsorUpdate):
    """Update an existing sponsor"""
    # Get current sponsor
    existing = await db.sponsors.find_one({"id": sponsor_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Sponsor not found")
    
    # Apply updates (only non-None values)
    update_data = {k: v for k, v in updates.model_dump().items() if v is not None}
    
    # Normalize email to lowercase
    if "email" in update_data:
        update_data["email"] = update_data["email"].lower()
    
    # Auto-set tier based on package
    if "package" in update_data:
        package = (update_data["package"] or "").lower()
        if "star" in package or "gold" in package or "platinum" in package or "premium" in package:
            update_data["tier"] = "gold"
        elif "silver" in package or "standard" in package:
            update_data["tier"] = "silver"
        elif "bronze" in package or "basic" in package:
            update_data["tier"] = "bronze"
    
    if update_data:
        await db.sponsors.update_one(
            {"id": sponsor_id},
            {"$set": update_data}
        )
        
        # Sync info to linked registered account if exists
        sponsor_email = update_data.get("email") or existing.get("email")
        if sponsor_email:
            account_updates = {}
            if "business_name" in update_data:
                account_updates["business_name"] = update_data["business_name"]
            if "contact_name" in update_data:
                account_updates["contact_name"] = update_data["contact_name"]
            if "phone" in update_data:
                account_updates["phone"] = update_data["phone"]
            if "website" in update_data:
                account_updates["website"] = update_data["website"]
            if "zip_code" in update_data:
                account_updates["zip_code"] = update_data["zip_code"]
            
            if account_updates:
                await db.registered_accounts.update_one(
                    {"email": sponsor_email.lower()},
                    {"$set": account_updates}
                )
    
    # Return updated sponsor
    updated = await db.sponsors.find_one({"id": sponsor_id}, {"_id": 0})
    return Sponsor(**updated)


@router.delete("/{sponsor_id}")
async def delete_sponsor(sponsor_id: str):
    """Delete a sponsor"""
    result = await db.sponsors.delete_one({"id": sponsor_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Sponsor not found")
    
    # Also delete their assets
    await db.assets.delete_many({"sponsor_id": sponsor_id})
    
    logger.info(f"Deleted sponsor: {sponsor_id}")
    return {"message": "Sponsor deleted successfully"}


@router.post("/from-account/{email}", response_model=Sponsor)
async def create_sponsor_from_account(email: str):
    """Create a sponsor profile from an existing registered account.
    This is useful for admins to convert existing users into sponsors."""
    
    # Check if sponsor already exists
    existing_sponsor = await db.sponsors.find_one({"email": email.lower()}, {"_id": 0})
    if existing_sponsor:
        raise HTTPException(status_code=400, detail="Sponsor profile already exists for this email")
    
    # Get the registered account
    account = await db.registered_accounts.find_one(
        {"email": email.lower()},
        {"_id": 0, "password_hash": 0}
    )
    
    if not account:
        raise HTTPException(status_code=404, detail="No registered account found with this email")
    
    # Create sponsor from account data
    sponsor_dict = {
        "id": f"sponsor_{uuid.uuid4().hex[:12]}",
        "business_name": account.get("business_name") or account.get("contact_name") or email.split("@")[0],
        "email": email.lower(),
        "contact_name": account.get("contact_name"),
        "phone": account.get("phone"),
        "website": account.get("website"),
        "zip_code": account.get("zip_code"),
        "package": None,
        "tier": None,
        "status": "inactive",  # Admin needs to set package/tier
        "notes": "Auto-created from registered account",
        "logo": None,
        "picture": account.get("picture"),
        "is_venue_sponsor": False,  # Must be explicitly set by admin
        "assets_count": 0,
        "joined_at": datetime.utcnow().strftime("%Y-%m-%d"),
        "user_id": account.get("id")
    }
    
    await db.sponsors.insert_one(sponsor_dict)
    logger.info(f"Created sponsor from account: {email}")
    
    return Sponsor(**sponsor_dict)


@router.get("/by-email/{email}", response_model=Sponsor)
async def get_sponsor_by_email(email: str):
    """Get a sponsor by email"""
    sponsor = await db.sponsors.find_one({"email": email.lower()}, {"_id": 0})
    if not sponsor:
        raise HTTPException(status_code=404, detail="Sponsor not found")
    return sponsor
