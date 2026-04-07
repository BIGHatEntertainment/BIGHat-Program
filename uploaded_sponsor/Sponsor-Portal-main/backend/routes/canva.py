"""Canva Connect API Integration for BIG Hat Sponsor Portal

This module handles:
- OAuth 2.0 authentication with Canva Connect API
- Asset uploads to Canva with organized folder structure
- Manual and scheduled synchronization of sponsor images
"""

from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, List
import httpx
import os
import base64
import secrets
import hashlib
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from database import db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/canva", tags=["canva"])

# Canva API Configuration
CANVA_CLIENT_ID = os.environ.get("CANVA_CLIENT_ID", "")
CANVA_CLIENT_SECRET = os.environ.get("CANVA_CLIENT_SECRET", "")
CANVA_REDIRECT_URI = os.environ.get("CANVA_REDIRECT_URI", "")
CANVA_ROOT_FOLDER_ID = os.environ.get("CANVA_ROOT_FOLDER_ID", "")  # "Sponsor API" folder
CANVA_AUTH_URL = "https://www.canva.com/api/oauth/authorize"
CANVA_TOKEN_URL = "https://api.canva.com/rest/v1/oauth/token"
CANVA_API_BASE = "https://api.canva.com/rest/v1"


# ============ Pydantic Models ============
class CanvaAuthResponse(BaseModel):
    auth_url: str
    state: str


class CanvaTokenExchange(BaseModel):
    code: str
    state: str


class CanvaConnectionStatus(BaseModel):
    connected: bool
    email: Optional[str] = None
    connected_at: Optional[str] = None
    last_sync: Optional[str] = None


class SyncLog(BaseModel):
    id: str
    sync_type: str  # "manual" or "automatic"
    started_at: str
    completed_at: Optional[str] = None
    total_images: int = 0
    successful_uploads: int = 0
    failed_uploads: int = 0
    errors: List[str] = []


class SyncResult(BaseModel):
    success: bool
    message: str
    sync_log: Optional[SyncLog] = None


# ============ Helper Functions ============
def generate_pkce_pair() -> tuple:
    """Generate code verifier and code challenge for PKCE
    
    Per RFC 7636:
    - code_verifier: 43-128 chars, only [A-Za-z0-9-._~]
    - code_challenge: SHA256 hash of verifier, base64url encoded
    """
    # Generate 96 random bytes and encode as base64url (gives ~128 chars)
    code_verifier = secrets.token_urlsafe(96)
    
    # SHA256 hash the verifier and base64url encode
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode('ascii')).digest()
    ).decode('ascii').rstrip('=')
    
    return code_verifier, code_challenge


async def get_valid_token() -> Optional[str]:
    """Get valid Canva access token, refreshing if necessary"""
    token_record = await db.canva_tokens.find_one({}, {"_id": 0})
    
    if not token_record:
        return None
    
    # Check if token is expired (with 5 min buffer)
    expires_at = token_record.get("expires_at")
    if isinstance(expires_at, str):
        expires_at = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    
    if datetime.now(timezone.utc) >= expires_at - timedelta(minutes=5):
        # Token expired or about to expire, refresh it
        refreshed = await refresh_access_token(token_record.get("refresh_token"))
        if not refreshed:
            return None
        token_record = await db.canva_tokens.find_one({}, {"_id": 0})
    
    return token_record.get("access_token")


async def refresh_access_token(refresh_token: str) -> bool:
    """Refresh the access token using refresh token"""
    try:
        auth_string = base64.b64encode(
            f"{CANVA_CLIENT_ID}:{CANVA_CLIENT_SECRET}".encode('utf-8')
        ).decode('utf-8')
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                CANVA_TOKEN_URL,
                headers={
                    "Authorization": f"Basic {auth_string}",
                    "Content-Type": "application/x-www-form-urlencoded"
                },
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token
                }
            )
        
        if response.status_code != 200:
            logger.error(f"Token refresh failed: {response.status_code} - {response.text}")
            return False
        
        token_data = response.json()
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=token_data.get("expires_in", 3600))
        
        await db.canva_tokens.update_one(
            {},
            {"$set": {
                "access_token": token_data["access_token"],
                "refresh_token": token_data.get("refresh_token", refresh_token),
                "expires_at": expires_at.isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat()
            }}
        )
        
        logger.info("Canva access token refreshed successfully")
        return True
        
    except Exception as e:
        logger.error(f"Token refresh error: {str(e)}")
        return False


async def get_or_create_folder(access_token: str, folder_name: str, parent_id: str = "root") -> Optional[str]:
    """Get or create a folder in Canva, returning its ID"""
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    
    try:
        # First, list existing folders in parent
        async with httpx.AsyncClient() as client:
            list_response = await client.get(
                f"{CANVA_API_BASE}/folders/{parent_id}/items",
                headers=headers
            )
            
            if list_response.status_code == 200:
                items = list_response.json().get("items", [])
                for item in items:
                    if item.get("type") == "folder":
                        folder_info = item.get("folder", {})
                        if folder_info.get("name") == folder_name:
                            return folder_info.get("id")
            
            # Folder doesn't exist, create it
            create_response = await client.post(
                f"{CANVA_API_BASE}/folders",
                headers=headers,
                json={
                    "name": folder_name,
                    "parent_folder_id": parent_id if parent_id != "root" else None
                }
            )
            
            if create_response.status_code == 200:
                folder_data = create_response.json()
                return folder_data.get("folder", {}).get("id")
            else:
                logger.error(f"Failed to create folder {folder_name}: {create_response.status_code} - {create_response.text}")
                return None
                
    except Exception as e:
        logger.error(f"Error managing folder {folder_name}: {str(e)}")
        return None


async def upload_image_to_canva(access_token: str, image_url: str, asset_name: str, folder_id: str = None) -> Optional[str]:
    """Upload an image to Canva from URL"""
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            # Create URL upload job
            upload_response = await client.post(
                f"{CANVA_API_BASE}/asset-uploads",
                headers=headers,
                json={
                    "url": image_url,
                    "name": asset_name
                }
            )
            
            if upload_response.status_code not in [200, 201]:
                logger.error(f"Upload initiation failed: {upload_response.status_code} - {upload_response.text}")
                return None
            
            job_data = upload_response.json()
            job_id = job_data.get("job", {}).get("id")
            
            if not job_id:
                logger.error("No job ID returned from upload")
                return None
            
            # Poll for completion (max 30 attempts, 2 second intervals)
            for attempt in range(30):
                await asyncio.sleep(2)
                
                status_response = await client.get(
                    f"{CANVA_API_BASE}/asset-uploads/{job_id}",
                    headers=headers
                )
                
                if status_response.status_code != 200:
                    continue
                
                status_data = status_response.json()
                job_status = status_data.get("job", {}).get("status")
                
                if job_status == "success":
                    asset_id = status_data.get("job", {}).get("asset", {}).get("id")
                    logger.info(f"Upload successful: {asset_name} -> {asset_id}")
                    return asset_id
                elif job_status == "failed":
                    error_msg = status_data.get("job", {}).get("error", {}).get("message", "Unknown error")
                    logger.error(f"Upload failed: {error_msg}")
                    return None
            
            logger.error(f"Upload timeout for {asset_name}")
            return None
            
    except Exception as e:
        logger.error(f"Upload error for {asset_name}: {str(e)}")
        return None


async def sync_sponsor_images(sync_type: str = "manual") -> SyncLog:
    """Sync all approved sponsor images to Canva
    
    Folder structure (inside 'Sponsor API' root folder):
    - Sponsors/{CompanyName}/16x9/ and /1x1/ - for regular sponsors
    - Venues/{VenueName}/16x9/ and /1x1/ - for venue sponsors
    """
    import uuid
    
    sync_log = SyncLog(
        id=f"sync_{uuid.uuid4().hex[:12]}",
        sync_type=sync_type,
        started_at=datetime.now(timezone.utc).isoformat(),
        total_images=0,
        successful_uploads=0,
        failed_uploads=0,
        errors=[]
    )
    
    try:
        # Get valid token
        access_token = await get_valid_token()
        if not access_token:
            sync_log.errors.append("No valid Canva access token. Please reconnect Canva.")
            sync_log.completed_at = datetime.now(timezone.utc).isoformat()
            await db.canva_sync_logs.insert_one(sync_log.model_dump())
            return sync_log
        
        # Get all approved assets that haven't been synced to Canva
        assets = await db.assets.find(
            {
                "status": "approved",
                "$or": [
                    {"canva_synced": {"$ne": True}},
                    {"canva_synced": {"$exists": False}}
                ]
            },
            {"_id": 0}
        ).to_list(1000)
        
        sync_log.total_images = len(assets)
        logger.info(f"Starting Canva sync: {len(assets)} images to process")
        
        if len(assets) == 0:
            sync_log.completed_at = datetime.now(timezone.utc).isoformat()
            await db.canva_sync_logs.insert_one(sync_log.model_dump())
            return sync_log
        
        # Use configured root folder (Sponsor API) or create one
        root_folder_id = CANVA_ROOT_FOLDER_ID
        if not root_folder_id:
            root_folder_id = await get_or_create_folder(access_token, "Sponsor API")
            if not root_folder_id:
                sync_log.errors.append("Failed to find/create root folder")
                sync_log.completed_at = datetime.now(timezone.utc).isoformat()
                await db.canva_sync_logs.insert_one(sync_log.model_dump())
                return sync_log
        
        # Get or create Sponsors and Venues folders inside root
        sponsors_folder_id = await get_or_create_folder(access_token, "Sponsors", root_folder_id)
        venues_folder_id = await get_or_create_folder(access_token, "Venues", root_folder_id)
        
        if not sponsors_folder_id or not venues_folder_id:
            sync_log.errors.append("Failed to create/find Sponsors or Venues folder")
            sync_log.completed_at = datetime.now(timezone.utc).isoformat()
            await db.canva_sync_logs.insert_one(sync_log.model_dump())
            return sync_log
        
        # Get sponsor info to determine if venue sponsor
        sponsors_cache = {}
        sponsors_list = await db.sponsors.find({}, {"_id": 0}).to_list(1000)
        for s in sponsors_list:
            sponsors_cache[s.get("id")] = s
        
        # Group assets by sponsor
        sponsors_assets = {}
        for asset in assets:
            sponsor_id = asset.get("sponsor_id")
            sponsor_name = asset.get("sponsor_name", "Unknown")
            if sponsor_name not in sponsors_assets:
                sponsors_assets[sponsor_name] = {
                    "sponsor_id": sponsor_id,
                    "assets": []
                }
            sponsors_assets[sponsor_name]["assets"].append(asset)
        
        # Process each sponsor
        for sponsor_name, sponsor_data in sponsors_assets.items():
            sponsor_id = sponsor_data.get("sponsor_id")
            sponsor_info = sponsors_cache.get(sponsor_id, {})
            is_venue_sponsor = sponsor_info.get("is_venue_sponsor", False)
            
            # Choose parent folder based on sponsor type
            parent_folder_id = venues_folder_id if is_venue_sponsor else sponsors_folder_id
            
            # Create sponsor folder (sanitize name for folder)
            safe_name = sponsor_name.replace("/", "-").replace("\\", "-").strip()
            sponsor_folder_id = await get_or_create_folder(
                access_token, 
                safe_name,
                parent_folder_id
            )
            if not sponsor_folder_id:
                for asset in sponsor_data["assets"]:
                    sync_log.failed_uploads += 1
                    sync_log.errors.append(f"Failed to create folder for {sponsor_name}")
                continue
            
            # Create format subfolders and upload assets
            for asset in sponsor_data["assets"]:
                asset_type = asset.get("type", "1:1")  # "16:9" or "1:1"
                folder_name = "16x9" if asset_type == "16:9" else "1x1"
                
                # Create format subfolder
                format_folder_id = await get_or_create_folder(
                    access_token,
                    folder_name,
                    sponsor_folder_id
                )
                
                # Get image URL
                image_url = asset.get("file_url")
                if not image_url and asset.get("file_data"):
                    # Handle base64 encoded images - skip for now as Canva needs URL
                    sync_log.failed_uploads += 1
                    sync_log.errors.append(f"Asset {asset.get('name')} uses base64 data, not URL")
                    continue
                
                if not image_url:
                    sync_log.failed_uploads += 1
                    sync_log.errors.append(f"Asset {asset.get('name')} has no valid URL")
                    continue
                
                # Build asset name with preferred indicator
                is_preferred = asset.get("is_preferred", False)
                asset_name = asset.get("name", "asset")
                if is_preferred:
                    asset_name = f"[PREFERRED] {asset_name}"
                
                # Upload to Canva
                canva_asset_id = await upload_image_to_canva(
                    access_token,
                    image_url,
                    asset_name,
                    format_folder_id
                )
                
                if canva_asset_id:
                    # Mark as synced in database
                    await db.assets.update_one(
                        {"id": asset.get("id")},
                        {"$set": {
                            "canva_synced": True,
                            "canva_asset_id": canva_asset_id,
                            "canva_synced_at": datetime.now(timezone.utc).isoformat()
                        }}
                    )
                    sync_log.successful_uploads += 1
                else:
                    sync_log.failed_uploads += 1
                    sync_log.errors.append(f"Failed to upload: {asset.get('name')}")
                
                # Rate limiting - don't overwhelm Canva API
                await asyncio.sleep(0.5)
        
        sync_log.completed_at = datetime.now(timezone.utc).isoformat()
        await db.canva_sync_logs.insert_one(sync_log.model_dump())
        
        # Update last sync time
        await db.canva_tokens.update_one(
            {},
            {"$set": {"last_sync": datetime.now(timezone.utc).isoformat()}}
        )
        
        logger.info(f"Canva sync completed: {sync_log.successful_uploads}/{sync_log.total_images} successful")
        return sync_log
        
    except Exception as e:
        logger.error(f"Sync error: {str(e)}")
        sync_log.errors.append(str(e))
        sync_log.completed_at = datetime.now(timezone.utc).isoformat()
        await db.canva_sync_logs.insert_one(sync_log.model_dump())
        return sync_log


# ============ API Endpoints ============
@router.get("/status", response_model=CanvaConnectionStatus)
async def get_canva_status():
    """Check if Canva is connected and get connection details"""
    token_record = await db.canva_tokens.find_one({}, {"_id": 0})
    
    if not token_record:
        return CanvaConnectionStatus(connected=False)
    
    # Check if token is valid
    access_token = await get_valid_token()
    
    return CanvaConnectionStatus(
        connected=access_token is not None,
        email=token_record.get("email"),
        connected_at=token_record.get("connected_at"),
        last_sync=token_record.get("last_sync")
    )


@router.get("/auth", response_model=CanvaAuthResponse)
async def initiate_canva_auth():
    """Generate Canva OAuth authorization URL"""
    if not CANVA_CLIENT_ID or not CANVA_REDIRECT_URI:
        raise HTTPException(status_code=500, detail="Canva credentials not configured")
    
    code_verifier, code_challenge = generate_pkce_pair()
    state = secrets.token_urlsafe(32)
    
    # Store PKCE data for callback
    await db.canva_auth_sessions.update_one(
        {"state": state},
        {"$set": {
            "state": state,
            "code_verifier": code_verifier,
            "created_at": datetime.now(timezone.utc).isoformat()
        }},
        upsert=True
    )
    
    # Build authorization URL
    # Only request scopes that are enabled in Canva Developer Portal
    # Based on user's config: asset:write, folder:read, folder:write, design:meta:read
    params = {
        "response_type": "code",
        "client_id": CANVA_CLIENT_ID,
        "redirect_uri": CANVA_REDIRECT_URI,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "state": state,
        "scope": "asset:write folder:read folder:write design:meta:read"
    }
    
    auth_url = f"{CANVA_AUTH_URL}?{'&'.join(f'{k}={v}' for k, v in params.items())}"
    
    return CanvaAuthResponse(auth_url=auth_url, state=state)


@router.get("/callback")
async def canva_oauth_callback(
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    error_description: Optional[str] = Query(None)
):
    """Handle OAuth callback from Canva - exchanges authorization code for access token"""
    from fastapi.responses import RedirectResponse
    import urllib.parse
    
    # Handle error response from Canva
    if error:
        logger.error(f"Canva OAuth error: {error} - {error_description}")
        error_msg = urllib.parse.quote(error_description or error)
        return RedirectResponse(
            url=f"/admin/settings?canva_error={error_msg}",
            status_code=302
        )
    
    # Validate required params
    if not code or not state:
        return RedirectResponse(
            url="/admin/settings?canva_error=missing_code_or_state",
            status_code=302
        )
    
    # Retrieve stored PKCE data
    auth_session = await db.canva_auth_sessions.find_one({"state": state}, {"_id": 0})
    
    if not auth_session:
        logger.error(f"No auth session found for state: {state}")
        # Redirect to frontend with error
        return RedirectResponse(
            url="/admin/settings?canva_error=invalid_state",
            status_code=302
        )
    
    code_verifier = auth_session.get("code_verifier")
    
    try:
        auth_string = base64.b64encode(
            f"{CANVA_CLIENT_ID}:{CANVA_CLIENT_SECRET}".encode('utf-8')
        ).decode('utf-8')
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                CANVA_TOKEN_URL,
                headers={
                    "Authorization": f"Basic {auth_string}",
                    "Content-Type": "application/x-www-form-urlencoded"
                },
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "code_verifier": code_verifier,
                    "redirect_uri": CANVA_REDIRECT_URI
                }
            )
        
        if response.status_code != 200:
            logger.error(f"Token exchange failed: {response.status_code} - {response.text}")
            return RedirectResponse(
                url="/admin/settings?canva_error=token_exchange_failed",
                status_code=302
            )
        
        token_data = response.json()
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=token_data.get("expires_in", 3600))
        
        # Store tokens
        await db.canva_tokens.delete_many({})  # Only one connection allowed
        await db.canva_tokens.insert_one({
            "access_token": token_data["access_token"],
            "refresh_token": token_data["refresh_token"],
            "expires_at": expires_at.isoformat(),
            "connected_at": datetime.now(timezone.utc).isoformat(),
            "email": "Canva Teams Account"  # Will be updated with actual user info if available
        })
        
        # Cleanup auth session
        await db.canva_auth_sessions.delete_one({"state": state})
        
        logger.info("Canva OAuth completed successfully")
        
        # Redirect to frontend with success
        return RedirectResponse(
            url="/admin/settings?canva_connected=true",
            status_code=302
        )
        
    except Exception as e:
        logger.error(f"OAuth callback error: {str(e)}")
        return RedirectResponse(
            url=f"/admin/settings?canva_error={str(e)[:50]}",
            status_code=302
        )


@router.post("/disconnect")
async def disconnect_canva():
    """Disconnect Canva integration"""
    await db.canva_tokens.delete_many({})
    await db.canva_auth_sessions.delete_many({})
    
    logger.info("Canva disconnected")
    return {"success": True, "message": "Canva disconnected"}


@router.post("/sync", response_model=SyncResult)
async def trigger_manual_sync(background_tasks: BackgroundTasks):
    """Trigger manual sync of sponsor images to Canva"""
    # Check if Canva is connected
    access_token = await get_valid_token()
    if not access_token:
        raise HTTPException(status_code=400, detail="Canva not connected. Please connect first.")
    
    # Run sync in background
    background_tasks.add_task(sync_sponsor_images, "manual")
    
    return SyncResult(
        success=True,
        message="Sync started. Check status for progress."
    )


@router.get("/sync-logs", response_model=List[SyncLog])
async def get_sync_logs(limit: int = Query(10, le=50)):
    """Get recent sync logs"""
    logs = await db.canva_sync_logs.find(
        {},
        {"_id": 0}
    ).sort("started_at", -1).to_list(limit)
    
    return logs


@router.get("/pending-sync-count")
async def get_pending_sync_count():
    """Get count of assets pending sync to Canva"""
    count = await db.assets.count_documents({
        "status": "approved",
        "$or": [
            {"canva_synced": {"$ne": True}},
            {"canva_synced": {"$exists": False}}
        ]
    })
    
    return {"pending_count": count}
