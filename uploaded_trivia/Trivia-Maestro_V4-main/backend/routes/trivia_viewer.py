from fastapi import APIRouter, HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase
from typing import List, Dict
import logging
import tempfile
import os

from sharepoint_service import SharePointService
from hybrid_pptx_converter import get_hybrid_converter

router = APIRouter(prefix="/trivia-viewer", tags=["trivia-viewer"])
logger = logging.getLogger(__name__)

db: AsyncIOMotorDatabase = None

def set_database(database):
    global db
    db = database


@router.get("/list")
async def list_trivia_presentations(userName: str, viewAll: bool = False) -> List[Dict]:
    """List all trivia presentations for a user (case-insensitive) or all users"""
    try:
        if viewAll:
            # View all trivia presentations regardless of creator
            presentations = await db.trivia_presentations.find({}).sort('createdAt', -1).to_list(100)
            logger.info(f"Found {len(presentations)} total trivia presentations (view all)")
        else:
            # Case-insensitive username match using regex
            presentations = await db.trivia_presentations.find(
                {'createdBy': {'$regex': f'^{userName}$', '$options': 'i'}}
            ).sort('createdAt', -1).to_list(100)
            logger.info(f"Found {len(presentations)} trivia presentations for {userName} (case-insensitive)")
        
        return [{
            'id': p['id'],
            'name': p['name'],
            'createdBy': p['createdBy'],
            'createdAt': p['createdAt'],
            'totalSlides': p.get('totalSlides', 0),
            'location': p.get('location', '').split('/')[-1]  # Just the location name
        } for p in presentations]
    
    except Exception as e:
        logger.error(f"Error listing presentations: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{presentation_id}")
async def get_trivia_presentation(presentation_id: str) -> Dict:
    """
    Get trivia presentation details including location and round configuration.
    Used by the editor to fetch location for overlay functionality and score tracker configuration.
    """
    try:
        presentation = await db.trivia_presentations.find_one({'id': presentation_id})
        if not presentation:
            raise HTTPException(status_code=404, detail="Presentation not found")
        
        # Return presentation with location info AND round configuration
        return {
            "id": presentation['id'],
            "name": presentation['name'],
            "createdBy": presentation['createdBy'],
            "createdAt": presentation['createdAt'],
            "location": presentation.get('location', ''),
            "locationFile": presentation.get('locationFile', ''),
            "locationFolder": presentation.get('locationFolder', ''),
            "totalSlides": presentation.get('totalSlides', 0),
            # Round configuration for Score Tracker
            "numRounds": presentation.get('numRounds'),
            "roundTypes": presentation.get('roundTypes', []),
            "roundNames": presentation.get('roundNames', []),
            "host": presentation.get('host', '')
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching trivia presentation: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{presentation_id}/slides")
async def get_presentation_slides(presentation_id: str) -> Dict:
    """
    Generate slides for a trivia presentation on-demand.
    Downloads files from SharePoint, converts to 16:9 images with overlays.
    """
    try:
        # Get presentation from database
        presentation = await db.trivia_presentations.find_one({'id': presentation_id})
        if not presentation:
            raise HTTPException(status_code=404, detail="Presentation not found")
        
        sp = SharePointService()
        converter = get_hybrid_converter()
        temp_dir = tempfile.mkdtemp(prefix="trivia_view_")
        
        all_slides = []
        slide_order = 0
        
        try:
            # 1. Host slide
            if presentation.get('hostFile'):
                host_local = os.path.join(temp_dir, "host.pptx")
                if sp.download_file(presentation['hostFile'], host_local):
                    host_slides = converter.convert_pptx_to_slides(host_local, slide_order)
                    all_slides.extend(host_slides)
                    slide_order += len(host_slides)
            
            # 2. Location slide
            if presentation.get('locationFile'):
                location_local = os.path.join(temp_dir, "location.pptx")
                if sp.download_file(presentation['locationFile'], location_local):
                    location_slides = converter.convert_pptx_to_slides(location_local, slide_order)
                    all_slides.extend(location_slides)
                    slide_order += len(location_slides)
            
            # 3. Round slides with overlays and sponsors
            round_files = presentation.get('roundFiles', [])
            sponsor_files = presentation.get('sponsorFiles', [])
            sponsor_idx = 0
            
            for round_info in round_files:
                # Download round file
                round_local = os.path.join(temp_dir, f"round_{round_info['order']}.pptx")
                if sp.download_file(round_info['file'], round_local):
                    # Download overlay if specified
                    overlay_local = None
                    if round_info.get('overlayFile'):
                        overlay_local = os.path.join(temp_dir, f"overlay_{round_info['order']}.png")
                        if not sp.download_file(round_info['overlayFile'], overlay_local):
                            logger.warning(f"Could not download overlay: {round_info['overlayFile']}")
                            overlay_local = None
                    
                    # Convert with overlay (enforces 16:9)
                    round_slides = converter.convert_pptx_to_slides(round_local, slide_order, overlay_local)
                    all_slides.extend(round_slides)
                    slide_order += len(round_slides)
                
                # Add sponsor after every other round
                if round_info['order'] % 2 == 0 and sponsor_idx < len(sponsor_files):
                    sponsor_local = os.path.join(temp_dir, f"sponsor_{sponsor_idx}.pptx")
                    if sp.download_file(sponsor_files[sponsor_idx], sponsor_local):
                        sponsor_slides = converter.convert_pptx_to_slides(sponsor_local, slide_order)
                        all_slides.extend(sponsor_slides)
                        slide_order += len(sponsor_slides)
                    sponsor_idx += 1
            
            return {
                "id": presentation['id'],
                "name": presentation['name'],
                "slides": [slide.model_dump() for slide in all_slides],
                "totalSlides": len(all_slides),
                "aspectRatio": "16:9",
                "resolution": "1920x1080"
            }
        
        finally:
            # Cleanup
            converter.cleanup()
            try:
                import shutil
                shutil.rmtree(temp_dir)
            except OSError:
                pass
    
    except Exception as e:
        logger.error(f"Error generating presentation slides: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to generate slides: {str(e)}")


@router.delete("/delete/{presentation_id}")
async def delete_trivia_presentation(presentation_id: str) -> Dict:
    """
    Delete a trivia presentation and its associated entries.
    Deletes both trivia_presentation and the lightweight presentations entry.
    """
    try:
        # Delete from trivia_presentations collection
        trivia_result = await db.trivia_presentations.delete_one({'id': presentation_id})
        
        # Also delete from presentations collection (created for on-demand loading)
        pres_result = await db.presentations.delete_one({'id': presentation_id})
        
        if trivia_result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Trivia presentation not found")
        
        logger.info(f"Deleted trivia presentation {presentation_id} from both collections")
        logger.info(f"  - trivia_presentations: {trivia_result.deleted_count} deleted")
        logger.info(f"  - presentations: {pres_result.deleted_count} deleted")
        
        return {
            "message": "Trivia presentation deleted successfully",
            "id": presentation_id
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting trivia presentation: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
