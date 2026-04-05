"""
Story Generator Routes - API endpoints for generating Instagram story videos.
"""

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from motor.motor_asyncio import AsyncIOMotorDatabase
from typing import List, Dict, Optional
import logging
import os

from story_generator_service import get_story_service

router = APIRouter(prefix="/story-generator", tags=["story-generator"])
logger = logging.getLogger(__name__)

db: AsyncIOMotorDatabase = None

def set_database(database):
    global db
    db = database


@router.get("/presentations")
async def list_presentations_for_story(userName: Optional[str] = None) -> List[Dict]:
    """
    List all trivia presentations available for story generation.
    Optionally filter by user.
    """
    try:
        query = {}
        if userName:
            query['createdBy'] = userName.lower()
        
        presentations = await db.trivia_presentations.find(query).sort('createdAt', -1).to_list(100)
        
        result = []
        for p in presentations:
            # Extract round info
            round_files = p.get('roundFiles', [])
            rounds_info = []
            for rf in round_files:
                rounds_info.append({
                    'order': rf.get('order', 0),
                    'type': rf.get('type', 'REG'),
                    'name': rf.get('name', rf.get('file', '').split('/')[-1].replace('.pptx', ''))
                })
            
            # Get location name
            location_path = p.get('location', '')
            location_name = location_path.split('/')[-1] if location_path else 'Unknown'
            # Remove numeric prefix
            import re
            location_name = re.sub(r'^\d+_', '', location_name)
            
            # Get host name
            host_path = p.get('hostFile', '')
            host_name = host_path.split('/')[-1].replace('.pptx', '') if host_path else 'Unknown'
            
            result.append({
                'id': p['id'],
                'name': p['name'],
                'createdBy': p.get('createdBy', ''),
                'createdAt': p.get('createdAt'),
                'location': location_name,
                'locationPath': location_path,
                'host': host_name,
                'hostPath': host_path,
                'numRounds': len(rounds_info),
                'rounds': rounds_info,
                'totalSlides': p.get('totalSlides', 0)
            })
        
        return result
    
    except Exception as e:
        logger.error(f"Error listing presentations: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/presentation/{presentation_id}")
async def get_presentation_details(presentation_id: str) -> Dict:
    """
    Get detailed information about a presentation for story generation preview.
    """
    try:
        presentation = await db.trivia_presentations.find_one({'id': presentation_id})
        if not presentation:
            raise HTTPException(status_code=404, detail="Presentation not found")
        
        # Extract round info
        round_files = presentation.get('roundFiles', [])
        rounds_info = []
        for rf in round_files:
            rounds_info.append({
                'order': rf.get('order', 0),
                'type': rf.get('type', 'REG'),
                'name': rf.get('name', rf.get('file', '').split('/')[-1].replace('.pptx', '')),
                'file': rf.get('file', '')
            })
        
        # Get location name
        location_path = presentation.get('location', '')
        location_name = location_path.split('/')[-1] if location_path else 'Unknown'
        import re
        location_name = re.sub(r'^\d+_', '', location_name)
        
        # Get host name
        host_path = presentation.get('hostFile', '')
        host_name = host_path.split('/')[-1].replace('.pptx', '') if host_path else 'Unknown'
        
        return {
            'id': presentation['id'],
            'name': presentation['name'],
            'createdBy': presentation.get('createdBy', ''),
            'createdAt': presentation.get('createdAt'),
            'location': location_name,
            'locationPath': location_path,
            'host': host_name,
            'hostPath': host_path,
            'numRounds': len(rounds_info),
            'rounds': rounds_info,
            'totalSlides': presentation.get('totalSlides', 0),
            # Include raw data for story generation
            'rawData': {
                'location': location_path,
                'hostFile': host_path,
                'roundFiles': round_files
            }
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting presentation: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/assets")
async def get_available_assets(refresh: bool = False) -> Dict:
    """
    Get list of available assets (location images, host GIFs, backgrounds).
    
    Args:
        refresh: If true, clears the SharePoint cache and fetches fresh data
    """
    try:
        service = get_story_service()
        if refresh:
            service.refresh_sharepoint_cache()
        return service.get_available_assets()
    
    except Exception as e:
        logger.error(f"Error getting assets: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/refresh-assets")
async def refresh_assets_cache() -> Dict:
    """
    Clear the SharePoint asset cache and reload assets.
    Call this when new locations, hosts, or backgrounds are added to SharePoint.
    """
    try:
        service = get_story_service()
        service.refresh_sharepoint_cache()
        assets = service.get_available_assets()
        return {
            'success': True,
            'message': 'Asset cache refreshed successfully',
            'counts': {
                'locations': len(assets.get('locations', [])),
                'hosts': len(assets.get('hosts', [])),
                'backgrounds': len(assets.get('backgrounds', []))
            },
            'sharepoint_enabled': assets.get('sharepoint_enabled', False)
        }
    except Exception as e:
        logger.error(f"Error refreshing assets: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/generate/{presentation_id}")
async def generate_story_video(presentation_id: str) -> Dict:
    """
    Generate an Instagram story video from a presentation.
    Returns the path to download the generated video.
    """
    try:
        # Get presentation data
        presentation = await db.trivia_presentations.find_one({'id': presentation_id})
        if not presentation:
            raise HTTPException(status_code=404, detail="Presentation not found")
        
        logger.info(f"Generating story video for presentation: {presentation['name']}")
        
        # Prepare data for story generation
        story_data = {
            'location': presentation.get('location', ''),
            'hostFile': presentation.get('hostFile', ''),
            'roundFiles': presentation.get('roundFiles', [])
        }
        
        # Generate video
        service = get_story_service()
        output_path = service.generate_video(story_data)
        
        # Get filename from path
        filename = os.path.basename(output_path)
        
        logger.info(f"Story video generated: {output_path}")
        
        return {
            'success': True,
            'message': 'Video generated successfully',
            'filename': filename,
            'downloadUrl': f'/api/story-generator/download/{filename}'
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating video: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to generate video: {str(e)}")


@router.get("/download/{filename}")
async def download_video(filename: str):
    """
    Download a generated story video.
    """
    try:
        service = get_story_service()
        file_path = service.generated_dir / filename
        
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="Video not found")
        
        return FileResponse(
            path=str(file_path),
            filename=filename,
            media_type='video/mp4'
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading video: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/upload-asset")
async def upload_asset(
    file: UploadFile = File(...),
    asset_type: str = Form(...),
    name: Optional[str] = Form(None)
) -> Dict:
    """
    Upload an asset (location image, host GIF, or background).
    
    Args:
        file: The image/GIF file
        asset_type: 'location', 'host', or 'background'
        name: Optional custom name (will use filename if not provided)
    """
    try:
        # Validate asset type
        if asset_type not in ['location', 'host', 'background']:
            raise HTTPException(status_code=400, detail="Invalid asset type")
        
        # Read file content
        content = await file.read()
        
        # Use custom name if provided
        filename = name or file.filename
        if not filename:
            raise HTTPException(status_code=400, detail="Filename required")
        
        # Ensure proper extension
        if not any(filename.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp']):
            # Add extension from content type
            ext_map = {
                'image/png': '.png',
                'image/jpeg': '.jpg',
                'image/gif': '.gif',
                'image/webp': '.webp'
            }
            ext = ext_map.get(file.content_type, '.png')
            filename = filename + ext
        
        # Upload asset
        service = get_story_service()
        result = service.upload_asset(content, filename, asset_type)
        
        return {
            'success': True,
            'message': f'{asset_type.title()} asset uploaded successfully',
            'asset': result
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading asset: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/asset/{asset_type}/{asset_id}")
async def delete_asset(asset_type: str, asset_id: str) -> Dict:
    """
    Delete an asset.
    
    Args:
        asset_type: 'location', 'host', or 'background'
        asset_id: Asset ID (filename without extension)
    """
    try:
        if asset_type not in ['location', 'host', 'background']:
            raise HTTPException(status_code=400, detail="Invalid asset type")
        
        service = get_story_service()
        deleted = service.delete_asset(asset_id, asset_type)
        
        if not deleted:
            raise HTTPException(status_code=404, detail="Asset not found")
        
        return {
            'success': True,
            'message': f'{asset_type.title()} asset deleted successfully'
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting asset: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/preview/{presentation_id}")
async def generate_preview(presentation_id: str) -> Dict:
    """
    Generate a preview of the story (returns frame data without creating video).
    Useful for showing a preview before generating the full video.
    """
    try:
        # Get presentation data
        presentation = await db.trivia_presentations.find_one({'id': presentation_id})
        if not presentation:
            raise HTTPException(status_code=404, detail="Presentation not found")
        
        # Prepare data for preview
        round_files = presentation.get('roundFiles', [])
        rounds_info = []
        for rf in round_files:
            rounds_info.append({
                'order': rf.get('order', 0),
                'type': rf.get('type', 'REG'),
                'name': rf.get('name', rf.get('file', '').split('/')[-1].replace('.pptx', ''))
            })
        
        # Get location name
        location_path = presentation.get('location', '')
        location_name = location_path.split('/')[-1] if location_path else 'Unknown'
        import re
        location_name = re.sub(r'^\d+_', '', location_name)
        
        # Get host name
        host_path = presentation.get('hostFile', '')
        host_name = host_path.split('/')[-1].replace('.pptx', '') if host_path else 'Unknown'
        
        # Check which assets are available
        service = get_story_service()
        assets = service.get_available_assets()
        
        # Normalize names for matching
        location_key = location_name.replace(' ', '_').lower()
        host_key = host_name.replace(' ', '_').lower()
        
        has_location_asset = any(a['id'].lower() == location_key for a in assets['locations'])
        has_host_asset = any(a['id'].lower() == host_key for a in assets['hosts'])
        has_background_asset = any(a['id'].lower() == location_key for a in assets['backgrounds'])
        
        return {
            'success': True,
            'preview': {
                'location': {
                    'name': location_name,
                    'hasAsset': has_location_asset,
                    'duration': 5
                },
                'host': {
                    'name': host_name,
                    'hasAsset': has_host_asset,
                    'duration': 5
                },
                'rounds': {
                    'items': rounds_info,
                    'hasBackground': has_background_asset,
                    'duration': 15
                },
                'totalDuration': 25
            },
            'assetsNeeded': {
                'locationImage': not has_location_asset,
                'hostImage': not has_host_asset,
                'backgroundImage': not has_background_asset
            }
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating preview: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
