"""
Story Builds Routes - API endpoints for managing trivia builds stored in SharePoint.

The builds are JSON files stored in:
01_Trivia/Web App/00_Builder/02_Locations/{location_folder}/00_Built/{filename}.json

Each JSON contains:
- host: Host name
- location: Location name
- numRounds: Number of rounds (5 or 6)
- roundNames: Array of round names
- createdAt: ISO timestamp
- createdBy: User who created it
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Optional
import logging
import json
import re
from datetime import datetime, timezone

router = APIRouter(prefix="/story-builds", tags=["story-builds"])
logger = logging.getLogger(__name__)

# SharePoint folder paths
SHAREPOINT_LOCATIONS_BASE = '01_Trivia/Web App/00_Builder/02_Locations'
BUILT_FOLDER_NAME = '00_Built'


class BuildData(BaseModel):
    """Schema for build data to save"""
    host: str
    location: str
    locationFolder: str  # Full folder name like "01_Monkey Pants"
    numRounds: int
    roundNames: List[str]
    roundTypes: List[str]
    presentationName: str
    createdBy: str


def get_sharepoint_service():
    """Lazy load SharePoint service"""
    try:
        from sharepoint_service import SharePointService
        return SharePointService()
    except Exception as e:
        logger.error(f"Failed to initialize SharePoint service: {e}")
        return None


@router.post("/save")
async def save_build(data: BuildData) -> Dict:
    """
    Save a trivia build as JSON to SharePoint.
    
    The file is saved to:
    01_Trivia/Web App/00_Builder/02_Locations/{locationFolder}/00_Built/{filename}.json
    
    Filename format: {location_name} - {presentation_name}_{timestamp}.json
    """
    try:
        sp = get_sharepoint_service()
        if not sp:
            raise HTTPException(status_code=503, detail="SharePoint service unavailable")
        
        # Create timestamp for filename
        timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
        
        # Clean location name for filename (remove prefix)
        location_clean = re.sub(r'^\d+_', '', data.locationFolder)
        
        # Clean presentation name for filename
        pres_name_clean = re.sub(r'[^\w\s-]', '', data.presentationName).strip()
        pres_name_clean = re.sub(r'\s+', '_', pres_name_clean)
        
        # Build filename
        filename = f"{location_clean} - {pres_name_clean}_{timestamp}.json"
        
        # Build SharePoint path — validate locationFolder matches an existing folder
        # If the folder name doesn't have a numeric prefix, try to find the real folder
        location_folder = data.locationFolder
        if not re.match(r'^\d+_', location_folder):
            # Try to find the prefixed folder in SharePoint
            try:
                items = sp.list_folder_contents(SHAREPOINT_LOCATIONS_BASE)
                for item in items:
                    if item.get('folder'):
                        folder_clean = re.sub(r'^\d+_', '', item['name']).lower()
                        if folder_clean == location_folder.lower() or folder_clean == location_folder.lower().replace(' ', '_'):
                            location_folder = item['name']
                            logger.info(f"Resolved location folder: {data.locationFolder} -> {location_folder}")
                            break
            except Exception as e:
                logger.warning(f"Could not resolve location folder: {e}")
        
        sp_path = f"{SHAREPOINT_LOCATIONS_BASE}/{location_folder}/{BUILT_FOLDER_NAME}/{filename}"
        
        # Prepare JSON content
        build_json = {
            "host": data.host,
            "location": data.location,
            "locationFolder": data.locationFolder,
            "numRounds": data.numRounds,
            "roundNames": data.roundNames,
            "roundTypes": data.roundTypes,
            "presentationName": data.presentationName,
            "createdBy": data.createdBy,
            "createdAt": datetime.now(timezone.utc).isoformat()
        }
        
        # Convert to bytes
        content = json.dumps(build_json, indent=2).encode('utf-8')
        
        # Upload to SharePoint
        success = sp.upload_content(content, sp_path, content_type='application/json')
        
        if success:
            logger.info(f"Saved build to SharePoint: {sp_path}")
            return {
                "success": True,
                "message": "Build saved successfully",
                "path": sp_path,
                "filename": filename
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to save build to SharePoint")
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saving build: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/list")
async def list_builds() -> List[Dict]:
    """
    List all available builds from SharePoint.
    
    Scans all location folders for 00_Built subfolders and returns JSON files.
    """
    try:
        sp = get_sharepoint_service()
        if not sp:
            raise HTTPException(status_code=503, detail="SharePoint service unavailable")
        
        builds = []
        
        # First, get all location folders
        location_folders = sp.list_folder_contents(SHAREPOINT_LOCATIONS_BASE)
        
        for loc_folder in location_folders:
            folder_name = loc_folder.get('name', '')
            
            # Skip if not a folder
            if 'folder' not in loc_folder:
                continue
            
            # Skip the Live Stream Show folder
            if 'Live Stream Show' in folder_name or '99_' in folder_name:
                continue
            
            # Check for 00_Built subfolder
            built_path = f"{SHAREPOINT_LOCATIONS_BASE}/{folder_name}/{BUILT_FOLDER_NAME}"
            
            try:
                built_files = sp.list_folder_contents(built_path)
                
                for file_info in built_files:
                    filename = file_info.get('name', '')
                    
                    # Only include JSON files
                    if not filename.lower().endswith('.json'):
                        continue
                    
                    # Extract info from filename
                    # Format: "{location} - {presentation_name}_{timestamp}.json"
                    name_part = filename[:-5]  # Remove .json
                    
                    # Get location display name (remove prefix)
                    location_display = re.sub(r'^\d+_', '', folder_name)
                    
                    builds.append({
                        'id': filename,
                        'name': name_part,
                        'filename': filename,
                        'location': location_display,
                        'locationFolder': folder_name,
                        'path': f"{built_path}/{filename}",
                        'lastModified': file_info.get('lastModifiedDateTime', '')
                    })
            
            except Exception as e:
                # 00_Built folder might not exist for this location, skip
                logger.debug(f"No 00_Built folder for {folder_name}: {e}")
                continue
        
        # Sort by last modified (newest first)
        builds.sort(key=lambda x: x.get('lastModified', ''), reverse=True)
        
        logger.info(f"Found {len(builds)} builds across all locations")
        return builds
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing builds: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/get/{location_folder}/{filename}")
async def get_build(location_folder: str, filename: str) -> Dict:
    """
    Get a specific build's JSON data from SharePoint.
    """
    try:
        sp = get_sharepoint_service()
        if not sp:
            raise HTTPException(status_code=503, detail="SharePoint service unavailable")
        
        # Build the path
        sp_path = f"{SHAREPOINT_LOCATIONS_BASE}/{location_folder}/{BUILT_FOLDER_NAME}/{filename}"
        
        # Download the file
        content = sp.download_file_to_bytes(sp_path)
        
        if not content:
            raise HTTPException(status_code=404, detail="Build not found")
        
        # Parse JSON
        build_data = json.loads(content.decode('utf-8'))
        
        return {
            "success": True,
            "data": build_data,
            "path": sp_path
        }
    
    except HTTPException:
        raise
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in build file: {e}")
        raise HTTPException(status_code=500, detail="Invalid build file format")
    except Exception as e:
        logger.error(f"Error getting build: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/delete/{location_folder}/{filename}")
async def delete_build(location_folder: str, filename: str) -> Dict:
    """
    Delete a build from SharePoint (optional, for cleanup).
    """
    try:
        sp = get_sharepoint_service()
        if not sp:
            raise HTTPException(status_code=503, detail="SharePoint service unavailable")
        
        # Build the path
        sp_path = f"{SHAREPOINT_LOCATIONS_BASE}/{location_folder}/{BUILT_FOLDER_NAME}/{filename}"
        
        # Delete the file using Graph API
        token = sp.get_access_token()
        headers = {'Authorization': f'Bearer {token}'}
        
        site_id = sp.get_site_id()
        drive_id = sp.get_drive_id(site_id)
        
        import requests
        encoded_path = requests.utils.quote(sp_path)
        url = f'https://graph.microsoft.com/v1.0/sites/{site_id}/drives/{drive_id}/root:/{encoded_path}'
        
        response = requests.delete(url, headers=headers, timeout=(30, 60))
        
        if response.status_code in [200, 204]:
            logger.info(f"Deleted build: {sp_path}")
            return {"success": True, "message": "Build deleted"}
        else:
            logger.error(f"Failed to delete build: {response.text}")
            raise HTTPException(status_code=500, detail="Failed to delete build")
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting build: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
