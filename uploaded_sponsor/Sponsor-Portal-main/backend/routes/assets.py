from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from typing import List, Optional
from datetime import datetime, timezone
import logging

from models.schemas import Asset, AssetCreate, AssetUpdate, PendingApproval
from database import db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/assets", tags=["assets"])


@router.get("", response_model=List[Asset])
async def get_assets(
    status: Optional[str] = Query(None, description="Filter by status"),
    sponsor_id: Optional[str] = Query(None, description="Filter by sponsor")
):
    """Get all assets with optional filtering"""
    query = {}
    if status:
        query["status"] = status
    if sponsor_id:
        query["sponsor_id"] = sponsor_id
    
    assets = await db.assets.find(query, {"_id": 0}).to_list(1000)
    return assets


@router.get("/pending", response_model=List[PendingApproval])
async def get_pending_approvals():
    """Get all assets pending approval"""
    assets = await db.assets.find({"status": "pending"}, {"_id": 0}).to_list(1000)
    # Add asset_name field for compatibility
    for asset in assets:
        asset["asset_name"] = asset.get("name", "")
    return assets


@router.get("/user/{user_email}", response_model=List[Asset])
async def get_user_assets(user_email: str):
    """Get all assets for a specific user by email"""
    assets = await db.assets.find(
        {"sponsor_email": user_email.lower()},
        {"_id": 0}
    ).to_list(1000)
    return assets


@router.get("/{asset_id}", response_model=Asset)
async def get_asset(asset_id: str):
    """Get a specific asset by ID"""
    asset = await db.assets.find_one({"id": asset_id}, {"_id": 0})
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    return asset


@router.post("", response_model=Asset)
async def create_asset(asset_data: AssetCreate):
    """Create/upload a new asset"""
    asset = Asset(**asset_data.model_dump())
    asset_dict = asset.model_dump()
    
    await db.assets.insert_one(asset_dict)
    
    # Update sponsor's asset count
    if asset_dict.get("sponsor_id"):
        await db.sponsors.update_one(
            {"id": asset_dict["sponsor_id"]},
            {"$inc": {"assets_count": 1}}
        )
    
    logger.info(f"Created asset: {asset_dict['name']} for {asset_dict.get('sponsor_email', 'unknown')}")
    return asset


@router.put("/{asset_id}", response_model=Asset)
async def update_asset(asset_id: str, updates: AssetUpdate):
    """Update an existing asset"""
    existing = await db.assets.find_one({"id": asset_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    update_data = {k: v for k, v in updates.model_dump().items() if v is not None}
    
    if update_data:
        await db.assets.update_one(
            {"id": asset_id},
            {"$set": update_data}
        )
    
    updated = await db.assets.find_one({"id": asset_id}, {"_id": 0})
    return updated


@router.post("/{asset_id}/approve")
async def approve_asset(asset_id: str, background_tasks: BackgroundTasks):
    """Approve an asset and upload 16:9 images to SharePoint"""
    # Get asset first to check type
    asset = await db.assets.find_one({"id": asset_id}, {"_id": 0})
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    result = await db.assets.update_one(
        {"id": asset_id},
        {"$set": {"status": "approved"}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    logger.info(f"Approved asset: {asset_id}")
    
    # If it's a 16:9 image, upload to SharePoint in background
    if asset.get("type") == "16:9":
        async def upload_to_sharepoint():
            try:
                from routes.sharepoint import sharepoint_service
                
                # Get sponsor info
                sponsor_email = asset.get("sponsor_email")
                sponsor = await db.sponsors.find_one(
                    {"email": sponsor_email.lower()},
                    {"_id": 0}
                )
                
                if not sponsor:
                    logger.warning(f"Sponsor not found for asset {asset_id}")
                    return
                
                is_venue_sponsor = sponsor.get("is_venue_sponsor", False)
                sponsor_name = sponsor.get("business_name", "Unknown")
                
                # For venue sponsors, get their location
                location_name = None
                if is_venue_sponsor:
                    location = await db.locations.find_one(
                        {"$or": [
                            {"sponsor_email": sponsor_email.lower()},
                            {"name": {"$regex": sponsor_name, "$options": "i"}}
                        ]},
                        {"_id": 0}
                    )
                    if location:
                        location_name = location.get("name")
                
                # Generate filename
                filename = f"{sponsor_name.replace(' ', '_')}_{asset.get('name', 'image')}"
                if not filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif')):
                    filename += ".png"
                
                # Upload to SharePoint
                image_data = asset.get("file_data")
                if image_data:
                    result = await sharepoint_service.upload_sponsor_image(
                        sponsor_name=sponsor_name,
                        image_data=image_data,
                        filename=filename,
                        is_venue_sponsor=is_venue_sponsor,
                        location_name=location_name
                    )
                    
                    if result["success"]:
                        await db.assets.update_one(
                            {"id": asset_id},
                            {"$set": {
                                "sharepoint_path": result.get("file_path"),
                                "sharepoint_uploaded_at": datetime.now(timezone.utc).isoformat()
                            }}
                        )
                        logger.info(f"Auto-uploaded approved 16:9 asset {asset_id} to SharePoint: {result.get('file_path')}")
                    else:
                        logger.error(f"Failed to auto-upload asset {asset_id} to SharePoint: {result.get('message')}")
            except Exception as e:
                logger.error(f"Error in background SharePoint upload for asset {asset_id}: {str(e)}")
        
        background_tasks.add_task(upload_to_sharepoint)
        return {"message": "Asset approved successfully. 16:9 image will be uploaded to SharePoint."}
    
    return {"message": "Asset approved successfully"}


@router.post("/{asset_id}/reject")
async def reject_asset(asset_id: str):
    """Reject an asset"""
    result = await db.assets.update_one(
        {"id": asset_id},
        {"$set": {"status": "rejected"}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    logger.info(f"Rejected asset: {asset_id}")
    return {"message": "Asset rejected successfully"}


@router.post("/{asset_id}/revision")
async def request_revision(asset_id: str, notes: str = Query(..., description="Revision notes")):
    """Request revision for an asset"""
    result = await db.assets.update_one(
        {"id": asset_id},
        {"$set": {"status": "revision_requested", "notes": notes}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    logger.info(f"Requested revision for asset: {asset_id}")
    return {"message": "Revision requested successfully"}


@router.post("/{asset_id}/set-preferred")
async def set_preferred_asset(asset_id: str):
    """Set an asset as preferred for its type (16:9 or 1:1)
    This will unset any other preferred asset of the same type for this sponsor
    """
    # Get the asset to find its type and sponsor
    asset = await db.assets.find_one({"id": asset_id}, {"_id": 0})
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    asset_type = asset.get("type")
    sponsor_email = asset.get("sponsor_email")
    
    if not asset_type or not sponsor_email:
        raise HTTPException(status_code=400, detail="Asset missing type or sponsor information")
    
    # First, unset preferred for all other assets of the same type for this sponsor
    await db.assets.update_many(
        {
            "sponsor_email": sponsor_email,
            "type": asset_type,
            "id": {"$ne": asset_id}
        },
        {"$set": {"is_preferred": False}}
    )
    
    # Then set this asset as preferred
    await db.assets.update_one(
        {"id": asset_id},
        {"$set": {"is_preferred": True}}
    )
    
    logger.info(f"Set asset {asset_id} as preferred {asset_type} for {sponsor_email}")
    return {"message": f"Asset set as preferred {asset_type}", "asset_id": asset_id, "type": asset_type}


@router.post("/{asset_id}/unset-preferred")
async def unset_preferred_asset(asset_id: str):
    """Remove preferred status from an asset"""
    result = await db.assets.update_one(
        {"id": asset_id},
        {"$set": {"is_preferred": False}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    logger.info(f"Removed preferred status from asset: {asset_id}")
    return {"message": "Preferred status removed"}


@router.get("/preferred/{sponsor_email}")
async def get_preferred_assets(sponsor_email: str):
    """Get preferred assets for a sponsor (one for each type)"""
    preferred_assets = await db.assets.find(
        {"sponsor_email": sponsor_email.lower(), "is_preferred": True},
        {"_id": 0}
    ).to_list(10)
    
    result = {
        "16:9": None,
        "1:1": None
    }
    
    for asset in preferred_assets:
        asset_type = asset.get("type")
        if asset_type in result:
            result[asset_type] = asset
    
    return result


@router.delete("/{asset_id}")
async def delete_asset(asset_id: str):
    """Delete an asset"""
    # Get asset first to update sponsor count
    asset = await db.assets.find_one({"id": asset_id}, {"_id": 0})
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    await db.assets.delete_one({"id": asset_id})
    
    # Update sponsor's asset count
    if asset.get("sponsor_id"):
        await db.sponsors.update_one(
            {"id": asset["sponsor_id"]},
            {"$inc": {"assets_count": -1}}
        )
    
    logger.info(f"Deleted asset: {asset_id}")
    return {"message": "Asset deleted successfully"}
