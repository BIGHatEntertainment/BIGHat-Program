from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import logging

from database import db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/profile", tags=["profile"])


class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    business_name: Optional[str] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    picture: Optional[str] = None  # Base64 encoded image


class ProfilePictureUpdate(BaseModel):
    picture: Optional[str] = None  # Base64 encoded image or URL


class ProfileResponse(BaseModel):
    id: str
    email: str
    name: Optional[str] = None
    business_name: Optional[str] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    picture: Optional[str] = None
    joined_at: Optional[str] = None


@router.get("/{email}", response_model=ProfileResponse)
async def get_profile(email: str):
    """Get user profile by email"""
    # Check in registered_accounts first
    account = await db.registered_accounts.find_one(
        {"email": email.lower()},
        {"_id": 0, "password_hash": 0}
    )
    
    if account:
        return ProfileResponse(
            id=account.get("id", ""),
            email=account.get("email", ""),
            name=account.get("contact_name", ""),
            business_name=account.get("business_name", ""),
            phone=account.get("phone", ""),
            website=account.get("website", ""),
            picture=account.get("picture"),
            joined_at=account.get("registered_at", "")
        )
    
    # Also check users collection (for Google OAuth users)
    user = await db.users.find_one(
        {"email": email.lower()},
        {"_id": 0}
    )
    
    if user:
        return ProfileResponse(
            id=user.get("user_id", ""),
            email=user.get("email", ""),
            name=user.get("name", ""),
            business_name=user.get("business_name", ""),
            phone=user.get("phone", ""),
            website=user.get("website", ""),
            picture=user.get("picture"),
            joined_at=str(user.get("created_at", ""))
        )
    
    raise HTTPException(status_code=404, detail="Profile not found")


@router.put("/{email}", response_model=ProfileResponse)
async def update_profile(email: str, updates: ProfileUpdate):
    """Update user profile"""
    update_data = {k: v for k, v in updates.model_dump().items() if v is not None}
    
    if not update_data:
        raise HTTPException(status_code=400, detail="No updates provided")
    
    # Map frontend field names to backend
    if "business_name" in update_data:
        update_data["business_name"] = update_data["business_name"]
    if "name" in update_data:
        update_data["contact_name"] = update_data.pop("name")
    
    # Update in registered_accounts
    await db.registered_accounts.update_one(
        {"email": email.lower()},
        {"$set": update_data}
    )
    
    # Also update in users collection if exists
    await db.users.update_one(
        {"email": email.lower()},
        {"$set": {
            "name": updates.name,
            "picture": updates.picture
        }}
    )
    
    # Also update sponsor if exists (case-insensitive email match)
    sponsor_updates = {}
    if updates.business_name:
        sponsor_updates["business_name"] = updates.business_name
    if updates.name:
        sponsor_updates["contact_name"] = updates.name
    if updates.phone:
        sponsor_updates["phone"] = updates.phone
    if updates.website:
        sponsor_updates["website"] = updates.website
    if updates.picture:
        sponsor_updates["picture"] = updates.picture
    
    if sponsor_updates:
        # Use case-insensitive regex for email matching
        await db.sponsors.update_one(
            {"email": {"$regex": f"^{email}$", "$options": "i"}},
            {"$set": sponsor_updates}
        )
    
    logger.info(f"Updated profile for: {email}")
    
    return await get_profile(email)


@router.put("/{email}/picture")
async def update_profile_picture(email: str, data: ProfilePictureUpdate):
    """Update only the profile picture"""
    picture = data.picture
    
    # Update in registered_accounts
    await db.registered_accounts.update_one(
        {"email": email.lower()},
        {"$set": {"picture": picture}}
    )
    
    # Update in users collection
    await db.users.update_one(
        {"email": email.lower()},
        {"$set": {"picture": picture}}
    )
    
    # Update in sponsors collection
    await db.sponsors.update_one(
        {"email": email.lower()},
        {"$set": {"picture": picture}}
    )
    
    logger.info(f"Updated profile picture for: {email}")
    
    return {"message": "Profile picture updated successfully", "picture": picture}


@router.delete("/{email}/picture")
async def remove_profile_picture(email: str):
    """Remove profile picture"""
    # Set picture to null in all collections
    await db.registered_accounts.update_one(
        {"email": email.lower()},
        {"$set": {"picture": None}}
    )
    
    await db.users.update_one(
        {"email": email.lower()},
        {"$set": {"picture": None}}
    )
    
    await db.sponsors.update_one(
        {"email": email.lower()},
        {"$set": {"picture": None}}
    )
    
    logger.info(f"Removed profile picture for: {email}")
    
    return {"message": "Profile picture removed successfully"}
