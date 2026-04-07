from fastapi import APIRouter, HTTPException, Query, Request

db = None
def set_database(database):
    global db
    db = database

from typing import List
import logging
import uuid
from datetime import datetime
from passlib.context import CryptContext

# Rate limiting
from slowapi import Limiter
from slowapi.util import get_remote_address

from sponsor_models.schemas import RegisteredAccount, RegisteredAccountCreate
# db injected via set_database

logger = logging.getLogger(__name__)

# Initialize rate limiter for account routes
limiter = Limiter(key_func=get_remote_address)

router = APIRouter(prefix="/accounts", tags=["accounts"])

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


@router.get("", response_model=List[RegisteredAccount])
async def get_registered_accounts():
    """Get all registered accounts"""
    accounts = await db.registered_accounts.find({}, {"_id": 0, "password_hash": 0}).to_list(1000)
    return accounts


@router.get("/unlinked", response_model=List[RegisteredAccount])
async def get_unlinked_accounts():
    """Get registered accounts that are not yet linked to sponsors"""
    # Get all sponsor emails
    sponsors = await db.sponsors.find({}, {"email": 1, "_id": 0}).to_list(1000)
    sponsor_emails = [s.get("email", "").lower() for s in sponsors if s.get("email")]
    
    # Get accounts not in sponsors list
    accounts = await db.registered_accounts.find(
        {"email": {"$nin": sponsor_emails}},
        {"_id": 0, "password_hash": 0}
    ).to_list(1000)
    
    return accounts


@router.get("/{account_id}", response_model=RegisteredAccount)
async def get_account(account_id: str):
    """Get a specific registered account by ID"""
    account = await db.registered_accounts.find_one(
        {"id": account_id},
        {"_id": 0, "password_hash": 0}
    )
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    return account


@router.post("", response_model=RegisteredAccount)
@limiter.limit("5/minute")  # Limit account registration to 5 per minute per IP
async def register_account(request: Request, account_data: RegisteredAccountCreate):
    """Register a new account"""
    # Check if account with same email exists
    existing = await db.registered_accounts.find_one(
        {"email": account_data.email.lower()},
        {"_id": 0}
    )
    if existing:
        raise HTTPException(status_code=400, detail="Account with this email already exists")
    
    account = RegisteredAccount(**account_data.model_dump(exclude={"password_hash"}))
    account_dict = account.model_dump()
    account_dict["email"] = account_dict["email"].lower()
    
    # Hash password if provided
    if account_data.password_hash:
        account_dict["password_hash"] = pwd_context.hash(account_data.password_hash)
    
    await db.registered_accounts.insert_one(account_dict)
    
    logger.info(f"Registered account: {account_dict['email']}")
    
    # Auto-create inactive sponsor profile so admin can see all registered users
    existing_sponsor = await db.sponsors.find_one({"email": account_dict["email"]})
    if not existing_sponsor:
        now = datetime.utcnow().isoformat()
        new_sponsor = {
            "id": f"sponsor_{uuid.uuid4().hex[:12]}",
            "email": account_dict["email"],
            "business_name": account_dict.get("business_name") or account_dict["email"].split("@")[0],
            "contact_name": account_dict.get("name"),
            "phone": account_dict.get("phone"),
            "website": account_dict.get("website"),
            "tier": None,
            "package": None,
            "status": "inactive",  # Inactive until they purchase something
            "is_venue_sponsor": False,
            "alacarte_items": [],
            "created_at": now,
            "updated_at": now,
            "notes": "Auto-created on signup"
        }
        await db.sponsors.insert_one(new_sponsor)
        logger.info(f"Auto-created sponsor profile for: {account_dict['email']}")
    
    # Return without password
    if "password_hash" in account_dict:
        del account_dict["password_hash"]
    return account_dict


@router.post("/login")
@limiter.limit("10/minute")  # Limit login attempts to 10 per minute per IP
async def login(request: Request, email: str = Query(...), password: str = Query(...)):
    """Login with email and password"""
    account = await db.registered_accounts.find_one(
        {"email": email.lower()},
        {"_id": 0}
    )
    
    if not account:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    if not account.get("password_hash"):
        raise HTTPException(status_code=401, detail="Please use Google login for this account")
    
    if not pwd_context.verify(password, account["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    # Also get sponsor info if linked (case-insensitive email match using lowercase)
    sponsor = await db.sponsors.find_one(
        {"email": email.lower()},
        {"_id": 0}
    )
    
    # Sync data from sponsor to account if not already synced
    if sponsor:
        sync_updates = {}
        if not account.get("business_name") or account.get("business_name") == "BIG Hat Entertainment":
            sync_updates["business_name"] = sponsor.get("business_name")
        if not account.get("contact_name") and sponsor.get("contact_name"):
            sync_updates["contact_name"] = sponsor.get("contact_name")
        if not account.get("phone") and sponsor.get("phone"):
            sync_updates["phone"] = sponsor.get("phone")
        if not account.get("website") and sponsor.get("website"):
            sync_updates["website"] = sponsor.get("website")
        
        if sync_updates:
            await db.registered_accounts.update_one(
                {"email": email.lower()},
                {"$set": sync_updates}
            )
            # Update local account dict
            account.update(sync_updates)
            logger.info(f"Synced sponsor data to account: {email}")
    
    # Return account without password but include must_reset_password flag and sponsor info
    response = {k: v for k, v in account.items() if k != "password_hash"}
    response["must_reset_password"] = account.get("must_reset_password", False)
    
    # Include sponsor tier info for frontend to determine upload permissions
    if sponsor:
        response["sponsor_tier"] = sponsor.get("tier")
        response["sponsor_package"] = sponsor.get("package")
        response["sponsor_id"] = sponsor.get("id")
        # CRITICAL: Include is_venue_sponsor flag directly from the sponsor record
        response["is_venue_sponsor"] = sponsor.get("is_venue_sponsor", False)
        # Also include the business name from sponsor if account doesn't have one
        if not response.get("business_name") or response.get("business_name") == "BIG Hat Entertainment":
            response["business_name"] = sponsor.get("business_name")
    
    return response


@router.post("/admin-create")
async def admin_create_account(account_data: RegisteredAccountCreate):
    """Create an account for a sponsor (by admin) with default password"""
    # Check if account with same email exists
    existing = await db.registered_accounts.find_one(
        {"email": account_data.email.lower()},
        {"_id": 0}
    )
    if existing:
        raise HTTPException(status_code=400, detail="Account with this email already exists")
    
    account = RegisteredAccount(**account_data.model_dump(exclude={"password_hash", "must_reset_password", "created_by_admin", "google_linked"}))
    account_dict = account.model_dump()
    account_dict["email"] = account_dict["email"].lower()
    
    # Set default password "B1GHat" and require reset
    default_password = "B1GHat"
    account_dict["password_hash"] = pwd_context.hash(default_password)
    account_dict["must_reset_password"] = True
    account_dict["created_by_admin"] = True
    account_dict["google_linked"] = False
    
    await db.registered_accounts.insert_one(account_dict)
    
    logger.info(f"Admin created account: {account_dict['email']} (password reset required)")
    
    # Auto-create inactive sponsor profile (admin-created accounts also appear in sponsors list)
    existing_sponsor = await db.sponsors.find_one({"email": account_dict["email"]})
    if not existing_sponsor:
        now = datetime.utcnow().isoformat()
        new_sponsor = {
            "id": f"sponsor_{uuid.uuid4().hex[:12]}",
            "email": account_dict["email"],
            "business_name": account_dict.get("business_name") or account_dict["email"].split("@")[0],
            "contact_name": account_dict.get("name"),
            "phone": account_dict.get("phone"),
            "website": account_dict.get("website"),
            "tier": None,
            "package": None,
            "status": "inactive",  # Inactive until they purchase something
            "is_venue_sponsor": False,
            "alacarte_items": [],
            "created_at": now,
            "updated_at": now,
            "notes": "Admin-created account"
        }
        await db.sponsors.insert_one(new_sponsor)
        logger.info(f"Auto-created sponsor profile for admin-created account: {account_dict['email']}")
    
    # Return without password and _id
    if "password_hash" in account_dict:
        del account_dict["password_hash"]
    if "_id" in account_dict:
        del account_dict["_id"]
    return account_dict


@router.post("/reset-password")
async def reset_password(
    email: str = Query(...),
    current_password: str = Query(...),
    new_password: str = Query(...)
):
    """Reset password for a user (used after first login with default password)"""
    account = await db.registered_accounts.find_one(
        {"email": email.lower()},
        {"_id": 0}
    )
    
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    
    # Verify current password
    if not account.get("password_hash"):
        raise HTTPException(status_code=400, detail="Account has no password set")
    
    if not pwd_context.verify(current_password, account["password_hash"]):
        raise HTTPException(status_code=401, detail="Current password is incorrect")
    
    # Check password requirements
    if len(new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    
    # Don't allow same as default password
    if new_password == "B1GHat":
        raise HTTPException(status_code=400, detail="Please choose a different password")
    
    # Update password and clear reset flag
    await db.registered_accounts.update_one(
        {"email": email.lower()},
        {
            "$set": {
                "password_hash": pwd_context.hash(new_password),
                "must_reset_password": False
            }
        }
    )
    
    logger.info(f"Password reset for: {email}")
    return {"message": "Password updated successfully"}


@router.put("/profile/{email}")
async def update_profile(email: str, updates: dict):
    """Update user profile information including zip code. Creates account if it doesn't exist (for OAuth users)."""
    import re
    from datetime import datetime
    
    email_lower = email.lower()
    
    # Allowed fields to update
    allowed_fields = {"business_name", "contact_name", "phone", "website", "zip_code"}
    update_data = {k: v for k, v in updates.items() if k in allowed_fields and v is not None}
    
    if not update_data:
        raise HTTPException(status_code=400, detail="No valid fields to update")
    
    # Validate zip code format if provided
    if "zip_code" in update_data:
        zip_code = update_data["zip_code"].strip()
        if zip_code and not re.match(r'^\d{5}(-\d{4})?$', zip_code):
            raise HTTPException(status_code=400, detail="Invalid zip code format. Use 5 digits (e.g., 85001) or 5+4 format (e.g., 85001-1234)")
        update_data["zip_code"] = zip_code
    
    # Check if account exists
    account = await db.registered_accounts.find_one({"email": email_lower})
    
    if account:
        # Update existing account
        await db.registered_accounts.update_one(
            {"email": email_lower},
            {"$set": update_data}
        )
    else:
        # Create new account (for OAuth users who don't have one yet)
        import uuid
        new_account = {
            "id": f"acc_{uuid.uuid4().hex[:12]}",
            "email": email_lower,
            "registered_at": datetime.utcnow().isoformat(),
            "google_linked": True,  # Assume OAuth if no existing account
            **update_data
        }
        await db.registered_accounts.insert_one(new_account)
        logger.info(f"Created new account for OAuth user: {email}")
    
    # Also update sponsor if linked
    await db.sponsors.update_one(
        {"email": email_lower},
        {"$set": {k: v for k, v in update_data.items() if k != "zip_code"}}
    )
    
    logger.info(f"Updated profile for: {email} - fields: {list(update_data.keys())}")
    
    # Return updated account
    updated_account = await db.registered_accounts.find_one(
        {"email": email_lower},
        {"_id": 0, "password_hash": 0}
    )
    return updated_account


@router.get("/profile/{email}/zip-status")
async def get_zip_code_status(email: str):
    """Check if user has a zip code set and if it's an AZ zip code"""
    account = await db.registered_accounts.find_one(
        {"email": email.lower()},
        {"zip_code": 1, "_id": 0}
    )
    
    # If account doesn't exist, return no zip code (don't throw 404)
    if not account:
        return {
            "has_zip_code": False,
            "is_az_resident": False
        }
    
    zip_code = account.get("zip_code")
    
    if not zip_code:
        return {
            "has_zip_code": False,
            "is_az_resident": False
        }
    
    # Check if AZ zip code (85001-86556)
    try:
        zip_num = int(zip_code.split('-')[0].strip())
        is_az = 85001 <= zip_num <= 86556
    except (ValueError, AttributeError):
        is_az = False
    
    return {
        "has_zip_code": True,
        "zip_code": zip_code,
        "is_az_resident": is_az,
        "eligible_for_az_discount": is_az
    }


@router.post("/link-google")
async def link_google_account(email: str = Query(...), google_id: str = Query(None)):
    """Link Google OAuth to an existing account"""
    account = await db.registered_accounts.find_one(
        {"email": email.lower()},
        {"_id": 0}
    )
    
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    
    # Update account to mark Google as linked
    await db.registered_accounts.update_one(
        {"email": email.lower()},
        {"$set": {"google_linked": True, "user_id": google_id}}
    )
    
    # Also update in users collection if it exists
    await db.users.update_one(
        {"email": email.lower()},
        {"$set": {"linked_account_id": account.get("id")}}
    )
    
    logger.info(f"Linked Google auth to account: {email}")
    return {"message": "Google account linked successfully"}


@router.get("/check-status/{email}")
async def check_account_status(email: str):
    """Check account status (for login flow)"""
    # First check if password exists (separate query to check just that field)
    account_with_pwd = await db.registered_accounts.find_one(
        {"email": email.lower()},
        {"_id": 0, "password_hash": 1, "must_reset_password": 1, "created_by_admin": 1, "google_linked": 1}
    )
    
    if not account_with_pwd:
        return {"exists": False}
    
    return {
        "exists": True,
        "must_reset_password": account_with_pwd.get("must_reset_password", False),
        "created_by_admin": account_with_pwd.get("created_by_admin", False),
        "google_linked": account_with_pwd.get("google_linked", False),
        "has_password": bool(account_with_pwd.get("password_hash"))
    }


@router.delete("/{account_id}")
async def delete_account(account_id: str):
    """Delete a registered account"""
    result = await db.registered_accounts.delete_one({"id": account_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Account not found")
    
    logger.info(f"Deleted account: {account_id}")
    return {"message": "Account deleted successfully"}
