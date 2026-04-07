"""Sponsor Placement Management Routes

Manages the visibility matrix for sponsors across venues and placement types.
Controls where sponsor images appear at each location.
"""

from fastapi import APIRouter, HTTPException

db = None
def set_database(database):
    global db
    db = database

from datetime import datetime, timezone
# db injected via set_database
from sponsor_models.schemas import (
    SponsorPlacementMatrix,
    PLACEMENT_TYPES
)

router = APIRouter(prefix="/placements", tags=["placements"])


@router.get("/placement-types")
async def get_placement_types():
    """Get all available placement types for the matrix"""
    return PLACEMENT_TYPES


@router.get("/matrix/{sponsor_id}", response_model=SponsorPlacementMatrix)
async def get_sponsor_placement_matrix(sponsor_id: str):
    """Get the full placement matrix for a sponsor"""
    
    # Get sponsor info
    sponsor = await db.sponsors.find_one({"id": sponsor_id}, {"_id": 0})
    if not sponsor:
        raise HTTPException(status_code=404, detail="Sponsor not found")
    
    # Get all active locations
    locations = await db.locations.find(
        {"status": "active"},
        {"_id": 0, "id": 1, "name": 1}
    ).to_list(100)
    
    # Get all placements for this sponsor
    existing_placements = await db.sponsor_placements.find(
        {"sponsor_id": sponsor_id},
        {"_id": 0}
    ).to_list(1000)
    
    # Build placements dict: {location_id: {placement_type: enabled}}
    placements = {}
    for loc in locations:
        placements[loc["id"]] = {}
        for pt in PLACEMENT_TYPES:
            # Default to False if no placement exists
            placements[loc["id"]][pt["id"]] = False
    
    # Fill in existing placements
    for p in existing_placements:
        loc_id = p.get("location_id")
        pt_id = p.get("placement_type")
        if loc_id in placements and pt_id in placements[loc_id]:
            placements[loc_id][pt_id] = p.get("enabled", False)
    
    return SponsorPlacementMatrix(
        sponsor_id=sponsor_id,
        sponsor_name=sponsor.get("business_name", "Unknown"),
        locations=[{"id": loc["id"], "name": loc["name"]} for loc in locations],
        placement_types=PLACEMENT_TYPES,
        placements=placements
    )


@router.put("/matrix/{sponsor_id}")
async def update_sponsor_placement(
    sponsor_id: str,
    location_id: str,
    placement_type: str,
    enabled: bool
):
    """Update a single placement cell in the matrix"""
    
    # Verify sponsor exists
    sponsor = await db.sponsors.find_one({"id": sponsor_id}, {"_id": 0})
    if not sponsor:
        raise HTTPException(status_code=404, detail="Sponsor not found")
    
    # Verify location exists
    location = await db.locations.find_one({"id": location_id}, {"_id": 0})
    if not location:
        raise HTTPException(status_code=404, detail="Location not found")
    
    # Verify placement type is valid
    valid_types = [pt["id"] for pt in PLACEMENT_TYPES]
    if placement_type not in valid_types:
        raise HTTPException(status_code=400, detail=f"Invalid placement type. Must be one of: {valid_types}")
    
    # Upsert the placement
    await db.sponsor_placements.update_one(
        {
            "sponsor_id": sponsor_id,
            "location_id": location_id,
            "placement_type": placement_type
        },
        {
            "$set": {
                "sponsor_id": sponsor_id,
                "location_id": location_id,
                "placement_type": placement_type,
                "enabled": enabled,
                "updated_at": datetime.now(timezone.utc).isoformat()
            },
            "$setOnInsert": {
                "id": f"placement_{sponsor_id[:8]}_{location_id[:8]}_{placement_type}"
            }
        },
        upsert=True
    )
    
    return {"success": True, "enabled": enabled}


@router.post("/matrix/{sponsor_id}/bulk")
async def bulk_update_placements(sponsor_id: str, placements: dict):
    """Bulk update multiple placements for a sponsor
    
    placements format: {location_id: {placement_type: enabled, ...}, ...}
    """
    
    # Verify sponsor exists
    sponsor = await db.sponsors.find_one({"id": sponsor_id}, {"_id": 0})
    if not sponsor:
        raise HTTPException(status_code=404, detail="Sponsor not found")
    
    valid_types = [pt["id"] for pt in PLACEMENT_TYPES]
    updates_count = 0
    
    for location_id, placement_data in placements.items():
        for placement_type, enabled in placement_data.items():
            if placement_type not in valid_types:
                continue
            
            await db.sponsor_placements.update_one(
                {
                    "sponsor_id": sponsor_id,
                    "location_id": location_id,
                    "placement_type": placement_type
                },
                {
                    "$set": {
                        "sponsor_id": sponsor_id,
                        "location_id": location_id,
                        "placement_type": placement_type,
                        "enabled": enabled,
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    },
                    "$setOnInsert": {
                        "id": f"placement_{sponsor_id[:8]}_{location_id[:8]}_{placement_type}"
                    }
                },
                upsert=True
            )
            updates_count += 1
    
    return {"success": True, "updates_count": updates_count}


@router.get("/sponsor/{sponsor_id}/enabled")
async def get_enabled_placements(sponsor_id: str):
    """Get all enabled placements for a sponsor (for Canva/SharePoint sync)"""
    
    placements = await db.sponsor_placements.find(
        {"sponsor_id": sponsor_id, "enabled": True},
        {"_id": 0}
    ).to_list(1000)
    
    # Group by location
    by_location = {}
    for p in placements:
        loc_id = p.get("location_id")
        if loc_id not in by_location:
            by_location[loc_id] = []
        by_location[loc_id].append(p.get("placement_type"))
    
    return {
        "sponsor_id": sponsor_id,
        "enabled_placements": placements,
        "by_location": by_location
    }


@router.post("/matrix/{sponsor_id}/select-all-location/{location_id}")
async def select_all_for_location(sponsor_id: str, location_id: str, enabled: bool = True):
    """Select or deselect all placements for a sponsor at a specific location"""
    
    valid_types = [pt["id"] for pt in PLACEMENT_TYPES]
    
    for placement_type in valid_types:
        await db.sponsor_placements.update_one(
            {
                "sponsor_id": sponsor_id,
                "location_id": location_id,
                "placement_type": placement_type
            },
            {
                "$set": {
                    "sponsor_id": sponsor_id,
                    "location_id": location_id,
                    "placement_type": placement_type,
                    "enabled": enabled,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                },
                "$setOnInsert": {
                    "id": f"placement_{sponsor_id[:8]}_{location_id[:8]}_{placement_type}"
                }
            },
            upsert=True
        )
    
    return {"success": True, "location_id": location_id, "all_enabled": enabled}


@router.post("/matrix/{sponsor_id}/select-all-placement/{placement_type}")
async def select_all_for_placement_type(sponsor_id: str, placement_type: str, enabled: bool = True):
    """Select or deselect a placement type for all locations"""
    
    valid_types = [pt["id"] for pt in PLACEMENT_TYPES]
    if placement_type not in valid_types:
        raise HTTPException(status_code=400, detail="Invalid placement type")
    
    # Get all active locations
    locations = await db.locations.find({"status": "active"}, {"_id": 0, "id": 1}).to_list(100)
    
    for loc in locations:
        await db.sponsor_placements.update_one(
            {
                "sponsor_id": sponsor_id,
                "location_id": loc["id"],
                "placement_type": placement_type
            },
            {
                "$set": {
                    "sponsor_id": sponsor_id,
                    "location_id": loc["id"],
                    "placement_type": placement_type,
                    "enabled": enabled,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                },
                "$setOnInsert": {
                    "id": f"placement_{sponsor_id[:8]}_{loc['id'][:8]}_{placement_type}"
                }
            },
            upsert=True
        )
    
    return {"success": True, "placement_type": placement_type, "all_enabled": enabled}
