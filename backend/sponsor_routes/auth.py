from fastapi import APIRouter, HTTPException, Request, Response

db = None
def set_database(database):
    global db
    db = database

from pydantic import BaseModel
from typing import Optional
import httpx
import logging
from datetime import datetime, timezone, timedelta
import uuid

# Rate limiting
from slowapi import Limiter
from slowapi.util import get_remote_address

# db injected via set_database

logger = logging.getLogger(__name__)

# Initialize rate limiter for auth routes (stricter limits)
limiter = Limiter(key_func=get_remote_address)

router = APIRouter(prefix="/auth", tags=["auth"])

# Emergent Auth API endpoint (correct endpoint from playbook)
EMERGENT_AUTH_URL = "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data"

class UserResponse(BaseModel):
    id: str
    email: str
    name: str
    picture: Optional[str] = None
    role: str = "sponsor"
    user_id: Optional[str] = None
    # Sponsor-specific fields
    businessName: Optional[str] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    sponsorTier: Optional[str] = None
    sponsorPackage: Optional[str] = None
    sponsorId: Optional[str] = None
    isVenueSponsor: Optional[bool] = None

class SessionData(BaseModel):
    user_id: str
    session_token: str
    expires_at: datetime

@router.post("/session", response_model=UserResponse)
@limiter.limit("10/minute")  # Limit login attempts to 10 per minute per IP
async def authenticate_session(request: Request, response: Response):
    """
    Exchange session_id from Emergent Auth for user data.
    The session_id comes from the URL hash after Google OAuth redirect.
    """
    try:
        # Get session_id from header
        session_id = request.headers.get("X-Session-ID")
        
        if not session_id:
            raise HTTPException(status_code=400, detail="Session ID required")
        
        logger.info(f"Processing session_id: {session_id[:20]}...")
        
        # Verify session with Emergent Auth API
        async with httpx.AsyncClient(follow_redirects=True) as http_client:
            auth_response = await http_client.get(
                EMERGENT_AUTH_URL,
                headers={"X-Session-ID": session_id}
            )
            
            logger.info(f"Emergent Auth response status: {auth_response.status_code}")
            
            if auth_response.status_code != 200:
                logger.error(f"Emergent Auth error: {auth_response.status_code} - {auth_response.text}")
                raise HTTPException(status_code=401, detail="Invalid or expired session")
            
            auth_data = auth_response.json()
            logger.info(f"Auth data received for: {auth_data.get('email', 'unknown')}")
        
        # Extract user info from Emergent Auth response
        email = auth_data.get("email", "")
        name = auth_data.get("name", email.split("@")[0] if email else "User")
        picture = auth_data.get("picture", f"https://api.dicebear.com/7.x/initials/svg?seed={name}")
        session_token = auth_data.get("session_token", "")
        
        # Check if admin (specific email)
        is_admin = email.lower() == "admin@bighat.live"
        
        # Override name for admin
        if is_admin:
            name = "Nicholas Sellards"
        
        # Generate user_id
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        
        # Check if user exists in database
        existing_user = await db.users.find_one({"email": email}, {"_id": 0})
        
        if existing_user:
            user_id = existing_user.get("user_id", user_id)
            # Update user info if needed
            await db.users.update_one(
                {"email": email},
                {"$set": {
                    "name": name,
                    "picture": picture,
                    "last_login": datetime.now(timezone.utc)
                }}
            )
        else:
            # Create new user
            await db.users.insert_one({
                "user_id": user_id,
                "email": email,
                "name": name,
                "picture": picture,
                "role": "admin" if is_admin else "sponsor",
                "created_at": datetime.now(timezone.utc),
                "last_login": datetime.now(timezone.utc)
            })
        
        # Link Google auth to existing registered account if one exists
        existing_account = await db.registered_accounts.find_one(
            {"email": email.lower()},
            {"_id": 0}
        )
        
        if existing_account:
            # Link Google to existing account
            await db.registered_accounts.update_one(
                {"email": email.lower()},
                {"$set": {
                    "google_linked": True,
                    "user_id": user_id
                }}
            )
            logger.info(f"Linked Google auth to existing account: {email}")
        else:
            # Create a registered account for this Google user
            now = datetime.now(timezone.utc).isoformat()
            new_account = {
                "id": f"account_{uuid.uuid4().hex[:12]}",
                "email": email.lower(),
                "name": name,
                "business_name": None,
                "phone": None,
                "website": None,
                "zip_code": None,
                "google_linked": True,
                "user_id": user_id,
                "registered_at": now
            }
            await db.registered_accounts.insert_one(new_account)
            logger.info(f"Created registered account for Google user: {email}")
        
        # Auto-create inactive sponsor profile if doesn't exist (for admin visibility)
        existing_sponsor = await db.sponsors.find_one({"email": email.lower()})
        if not existing_sponsor and not is_admin:  # Don't create sponsor profile for admin
            now = datetime.now(timezone.utc).isoformat()
            new_sponsor = {
                "id": f"sponsor_{uuid.uuid4().hex[:12]}",
                "email": email.lower(),
                "business_name": name or email.split("@")[0],
                "contact_name": name,
                "phone": None,
                "website": None,
                "tier": None,
                "package": None,
                "status": "inactive",  # Inactive until they purchase something
                "is_venue_sponsor": False,
                "alacarte_items": [],
                "created_at": now,
                "updated_at": now,
                "notes": "Auto-created on Google login"
            }
            await db.sponsors.insert_one(new_sponsor)
            logger.info(f"Auto-created sponsor profile for Google user: {email}")
        
        # Store session in database
        expires_at = datetime.now(timezone.utc) + timedelta(days=7)
        await db.user_sessions.update_one(
            {"user_id": user_id},
            {"$set": {
                "session_token": session_token,
                "expires_at": expires_at,
                "created_at": datetime.now(timezone.utc)
            }},
            upsert=True
        )
        
        # Set session cookie
        response.set_cookie(
            key="session_token",
            value=session_token,
            httponly=True,
            secure=True,
            samesite="none",
            path="/",
            max_age=7 * 24 * 60 * 60  # 7 days
        )
        
        # Fetch sponsor data if user has a linked sponsor profile
        sponsor = await db.sponsors.find_one(
            {"email": email.lower()},
            {"_id": 0}
        )
        
        # Build sponsor-specific fields
        sponsor_tier = None
        sponsor_package = None
        sponsor_id = None
        is_venue_sponsor = False
        business_name = None
        phone = None
        website = None
        
        if sponsor:
            sponsor_tier = sponsor.get("tier")
            sponsor_package = sponsor.get("package")
            sponsor_id = sponsor.get("id")
            # Venue sponsor must be EXPLICITLY set by admin, NOT derived from tier
            is_venue_sponsor = sponsor.get("is_venue_sponsor", False)
            business_name = sponsor.get("business_name")
            phone = sponsor.get("phone")
            website = sponsor.get("website")
        
        # Also check registered account for additional info
        if existing_account:
            if not business_name:
                business_name = existing_account.get("business_name")
            if not phone:
                phone = existing_account.get("phone")
            if not website:
                website = existing_account.get("website")
        
        user_response = UserResponse(
            id=auth_data.get("id", user_id),
            user_id=user_id,
            email=email,
            name=name,
            picture=picture,
            role="admin" if is_admin else "sponsor",
            # Sponsor fields
            businessName=business_name,
            phone=phone,
            website=website,
            sponsorTier=sponsor_tier,
            sponsorPackage=sponsor_package,
            sponsorId=sponsor_id,
            isVenueSponsor=is_venue_sponsor,
        )
        
        logger.info(f"User authenticated: {email}, role: {user_response.role}, tier: {sponsor_tier}, isVenueSponsor: {is_venue_sponsor}")
        
        return user_response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Authentication error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Authentication failed: {str(e)}")

@router.get("/me", response_model=UserResponse)
async def get_current_user(request: Request):
    """
    Get current user info from session cookie or Authorization header.
    """
    # Try cookie first, then Authorization header
    session_token = request.cookies.get("session_token")
    
    if not session_token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            session_token = auth_header[7:]
    
    if not session_token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    try:
        # Find session in database
        session_doc = await db.user_sessions.find_one(
            {"session_token": session_token},
            {"_id": 0}
        )
        
        if not session_doc:
            raise HTTPException(status_code=401, detail="Invalid session")
        
        # Check expiry
        expires_at = session_doc.get("expires_at")
        if isinstance(expires_at, str):
            expires_at = datetime.fromisoformat(expires_at)
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at < datetime.now(timezone.utc):
            raise HTTPException(status_code=401, detail="Session expired")
        
        # Get user data
        user_doc = await db.users.find_one(
            {"user_id": session_doc["user_id"]},
            {"_id": 0}
        )
        
        if not user_doc:
            raise HTTPException(status_code=401, detail="User not found")
        
        return UserResponse(
            id=user_doc.get("user_id"),
            user_id=user_doc.get("user_id"),
            email=user_doc.get("email"),
            name=user_doc.get("name"),
            picture=user_doc.get("picture"),
            role=user_doc.get("role", "sponsor")
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get user error: {str(e)}")
        raise HTTPException(status_code=401, detail="Session invalid")

@router.post("/logout")
async def logout(request: Request, response: Response):
    """
    Clear session cookie and delete session from database.
    """
    session_token = request.cookies.get("session_token")
    
    if session_token:
        await db.user_sessions.delete_one({"session_token": session_token})
    
    response.delete_cookie(
        key="session_token",
        path="/",
        secure=True,
        samesite="none"
    )
    
    return {"message": "Logged out successfully"}
