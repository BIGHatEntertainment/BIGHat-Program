from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
import logging

from models.schemas import Location, LocationCreate, LocationUpdate
from database import db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/locations", tags=["locations"])


@router.get("", response_model=List[Location])
async def get_locations(
    status: Optional[str] = Query(None, description="Filter by status")
):
    """Get all locations with optional filtering"""
    query = {}
    if status:
        query["status"] = status
    
    locations = await db.locations.find(query, {"_id": 0}).to_list(1000)
    return locations


@router.get("/{location_id}", response_model=Location)
async def get_location(location_id: str):
    """Get a specific location by ID"""
    location = await db.locations.find_one({"id": location_id}, {"_id": 0})
    if not location:
        raise HTTPException(status_code=404, detail="Location not found")
    return location


@router.post("", response_model=Location)
async def create_location(location_data: LocationCreate):
    """Create a new location"""
    location = Location(**location_data.model_dump())
    location_dict = location.model_dump()
    
    await db.locations.insert_one(location_dict)
    logger.info(f"Created location: {location_dict['name']}")
    return location


@router.put("/{location_id}", response_model=Location)
async def update_location(location_id: str, updates: LocationUpdate):
    """Update an existing location"""
    existing = await db.locations.find_one({"id": location_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Location not found")
    
    update_data = {k: v for k, v in updates.model_dump().items() if v is not None}
    
    if update_data:
        await db.locations.update_one(
            {"id": location_id},
            {"$set": update_data}
        )
    
    updated = await db.locations.find_one({"id": location_id}, {"_id": 0})
    return updated


@router.delete("/{location_id}")
async def delete_location(location_id: str):
    """Delete a location"""
    result = await db.locations.delete_one({"id": location_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Location not found")
    
    logger.info(f"Deleted location: {location_id}")
    return {"message": "Location deleted successfully"}
