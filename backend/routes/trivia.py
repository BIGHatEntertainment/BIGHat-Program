from fastapi import APIRouter, HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase
from typing import List, Dict, Optional
import logging
from datetime import datetime

from sharepoint_service import SharePointService

router = APIRouter(prefix="/trivia", tags=["trivia"])
logger = logging.getLogger(__name__)

# Database will be injected
db: AsyncIOMotorDatabase = None

def set_database(database):
    global db
    db = database


@router.get("/hosts")
async def get_hosts() -> List[Dict[str, str]]:
    """Get list of available hosts from SharePoint"""
    try:
        sp = SharePointService()
        hosts_folder = "01_Trivia/Web App/00_Builder/01_Hosts"
        items = sp.list_folder_contents(hosts_folder)
        
        hosts = []
        for item in items:
            if item.get('file') and item['name'].endswith('.pptx'):
                hosts.append({
                    'id': item['id'],
                    'name': item['name'].replace('.pptx', ''),
                    'path': f"{hosts_folder}/{item['name']}"
                })
        
        return hosts
    except Exception as e:
        logger.error(f"Error fetching hosts: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/locations")
async def get_locations() -> List[Dict[str, str]]:
    """Get list of available locations from SharePoint"""
    try:
        sp = SharePointService()
        locations_folder = "01_Trivia/Web App/00_Builder/02_Locations"
        items = sp.list_folder_contents(locations_folder)
        
        locations = []
        for item in items:
            if item.get('folder'):
                # Each location is a folder containing intro slide and overlay
                locations.append({
                    'id': item['id'],
                    'name': item['name'],
                    'path': f"{locations_folder}/{item['name']}"
                })
        
        return locations
    except Exception as e:
        logger.error(f"Error fetching locations: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/rounds")
async def get_all_rounds() -> List[Dict[str, str]]:
    """Get all available rounds from all types using dedicated folders"""
    try:
        sp = SharePointService()
        
        rounds = []
        
        # Fetch from each dedicated folder
        for round_type, sharing_url in ROUND_FOLDER_URLS.items():
            try:
                items = sp.list_folder_contents_by_sharing_url(sharing_url)
                
                for item in items:
                    parent_ref = item.get('parentReference', {})
                    drive_id = parent_ref.get('driveId', '')
                    
                    if item.get('folder') or (item.get('file') and item['name'].endswith('.pptx')):
                        name = item['name'].replace('.pptx', '') if item.get('file') else item['name']
                        rounds.append({
                            'id': item['id'],
                            'name': name,
                            'path': f"sharepoint://{drive_id}/{item['id']}",
                            'type': round_type.upper(),
                            'driveId': drive_id,
                            'itemId': item['id']
                        })
            except Exception as e:
                logger.warning(f"Could not fetch {round_type} rounds: {str(e)}")
        
        return sorted(rounds, key=lambda x: (x['type'], x['name']))
    except Exception as e:
        logger.error(f"Error fetching all rounds: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/rounds/mc")
async def get_mc_rounds() -> List[Dict[str, str]]:
    """Get Multiple Choice round folders from dedicated folder"""
    try:
        sp = SharePointService()
        sharing_url = ROUND_FOLDER_URLS['mc']
        
        items = sp.list_folder_contents_by_sharing_url(sharing_url)
        
        rounds = []
        for item in items:
            # Get folders (round categories) or pptx files
            if item.get('folder'):
                parent_ref = item.get('parentReference', {})
                drive_id = parent_ref.get('driveId', '')
                rounds.append({
                    'id': item['id'],
                    'name': item['name'],
                    'path': f"sharepoint://{drive_id}/{item['id']}",
                    'driveId': drive_id,
                    'itemId': item['id']
                })
            elif item.get('file') and item['name'].endswith('.pptx'):
                parent_ref = item.get('parentReference', {})
                drive_id = parent_ref.get('driveId', '')
                rounds.append({
                    'id': item['id'],
                    'name': item['name'].replace('.pptx', ''),
                    'path': f"sharepoint://{drive_id}/{item['id']}",
                    'driveId': drive_id,
                    'itemId': item['id']
                })
        
        return sorted(rounds, key=lambda x: x['name'])
    except Exception as e:
        logger.error(f"Error fetching MC rounds: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/rounds/reg")
async def get_reg_rounds() -> List[Dict[str, str]]:
    """Get General (REG) round folders from dedicated folder"""
    try:
        sp = SharePointService()
        sharing_url = ROUND_FOLDER_URLS['reg']
        
        items = sp.list_folder_contents_by_sharing_url(sharing_url)
        
        rounds = []
        for item in items:
            if item.get('folder'):
                parent_ref = item.get('parentReference', {})
                drive_id = parent_ref.get('driveId', '')
                rounds.append({
                    'id': item['id'],
                    'name': item['name'],
                    'path': f"sharepoint://{drive_id}/{item['id']}",
                    'driveId': drive_id,
                    'itemId': item['id']
                })
            elif item.get('file') and item['name'].endswith('.pptx'):
                parent_ref = item.get('parentReference', {})
                drive_id = parent_ref.get('driveId', '')
                rounds.append({
                    'id': item['id'],
                    'name': item['name'].replace('.pptx', ''),
                    'path': f"sharepoint://{drive_id}/{item['id']}",
                    'driveId': drive_id,
                    'itemId': item['id']
                })
        
        return sorted(rounds, key=lambda x: x['name'])
    except Exception as e:
        logger.error(f"Error fetching REG rounds: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/rounds/misc")
async def get_misc_rounds() -> List[Dict[str, str]]:
    """Get Specific (MISC) round folders from dedicated folder"""
    try:
        sp = SharePointService()
        sharing_url = ROUND_FOLDER_URLS['misc']
        
        items = sp.list_folder_contents_by_sharing_url(sharing_url)
        
        rounds = []
        for item in items:
            if item.get('folder'):
                parent_ref = item.get('parentReference', {})
                drive_id = parent_ref.get('driveId', '')
                rounds.append({
                    'id': item['id'],
                    'name': item['name'],
                    'path': f"sharepoint://{drive_id}/{item['id']}",
                    'driveId': drive_id,
                    'itemId': item['id']
                })
            elif item.get('file') and item['name'].endswith('.pptx'):
                parent_ref = item.get('parentReference', {})
                drive_id = parent_ref.get('driveId', '')
                rounds.append({
                    'id': item['id'],
                    'name': item['name'].replace('.pptx', ''),
                    'path': f"sharepoint://{drive_id}/{item['id']}",
                    'driveId': drive_id,
                    'itemId': item['id']
                })
        
        return sorted(rounds, key=lambda x: x['name'])
    except Exception as e:
        logger.error(f"Error fetching MISC rounds: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/rounds/mys")
async def get_mys_rounds() -> List[Dict[str, str]]:
    """Get Mystery (MYS) round folders from dedicated folder"""
    try:
        sp = SharePointService()
        sharing_url = ROUND_FOLDER_URLS['mys']
        
        items = sp.list_folder_contents_by_sharing_url(sharing_url)
        
        rounds = []
        for item in items:
            if item.get('folder'):
                parent_ref = item.get('parentReference', {})
                drive_id = parent_ref.get('driveId', '')
                rounds.append({
                    'id': item['id'],
                    'name': item['name'],
                    'path': f"sharepoint://{drive_id}/{item['id']}",
                    'driveId': drive_id,
                    'itemId': item['id']
                })
            elif item.get('file') and item['name'].endswith('.pptx'):
                parent_ref = item.get('parentReference', {})
                drive_id = parent_ref.get('driveId', '')
                rounds.append({
                    'id': item['id'],
                    'name': item['name'].replace('.pptx', ''),
                    'path': f"sharepoint://{drive_id}/{item['id']}",
                    'driveId': drive_id,
                    'itemId': item['id']
                })
        
        return sorted(rounds, key=lambda x: x['name'])
    except Exception as e:
        logger.error(f"Error fetching MYS rounds: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/rounds/big")
async def get_big_rounds() -> List[Dict[str, str]]:
    """Get BIG Question round folders from dedicated folder"""
    try:
        sp = SharePointService()
        sharing_url = ROUND_FOLDER_URLS['big']
        
        items = sp.list_folder_contents_by_sharing_url(sharing_url)
        
        rounds = []
        for item in items:
            if item.get('folder'):
                parent_ref = item.get('parentReference', {})
                drive_id = parent_ref.get('driveId', '')
                rounds.append({
                    'id': item['id'],
                    'name': item['name'],
                    'path': f"sharepoint://{drive_id}/{item['id']}",
                    'driveId': drive_id,
                    'itemId': item['id']
                })
            elif item.get('file') and item['name'].endswith('.pptx'):
                parent_ref = item.get('parentReference', {})
                drive_id = parent_ref.get('driveId', '')
                rounds.append({
                    'id': item['id'],
                    'name': item['name'].replace('.pptx', ''),
                    'path': f"sharepoint://{drive_id}/{item['id']}",
                    'driveId': drive_id,
                    'itemId': item['id']
                })
        
        return sorted(rounds, key=lambda x: x['name'])
    except Exception as e:
        logger.error(f"Error fetching BIG rounds: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sponsors")
async def get_sponsors() -> List[Dict[str, str]]:
    """Get list of sponsor slides from SharePoint"""
    try:
        sp = SharePointService()
        sponsors_folder = "01_Trivia/Web App/00_Builder/03_Sponsors"
        items = sp.list_folder_contents(sponsors_folder)
        
        sponsors = []
        for item in items:
            if item.get('file') and item['name'].endswith('.pptx'):
                sponsors.append({
                    'id': item['id'],
                    'name': item['name'].replace('.pptx', ''),
                    'path': f"{sponsors_folder}/{item['name']}"
                })
        
        return sponsors
    except Exception as e:
        logger.error(f"Error fetching sponsors: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cleanup-expired-usage")
async def cleanup_expired_usage() -> Dict:
    """
    Clean up expired round usage records (older than 6 months).
    This makes old rounds available again for selection.
    """
    try:
        cutoff_date = datetime.utcnow()
        
        # Delete all usage records that have expired
        result = await db.round_usage.delete_many({
            'expiresDate': {'$lt': cutoff_date}
        })
        
        logger.info(f"Cleaned up {result.deleted_count} expired usage records")
        
        return {
            "message": f"Successfully cleaned up {result.deleted_count} expired records",
            "deletedCount": result.deleted_count
        }
    except Exception as e:
        logger.error(f"Error cleaning up expired usage: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/usage-stats")
async def get_usage_stats(location: str = None) -> Dict:
    """
    Get statistics about round usage.
    Optionally filter by location.
    """
    try:
        query = {}
        if location:
            query['location'] = location
        
        total_records = await db.round_usage.count_documents(query)
        
        cutoff_date = datetime.utcnow()
        active_records = await db.round_usage.count_documents({
            **query,
            'expiresDate': {'$gt': cutoff_date}
        })
        
        expired_records = total_records - active_records
        
        # Get most recently used rounds
        recent_usage = await db.round_usage.find(
            query
        ).sort('usedDate', -1).limit(10).to_list(10)
        
        return {
            "totalRecords": total_records,
            "activeRecords": active_records,
            "expiredRecords": expired_records,
            "recentUsage": [{
                "roundFile": r['roundFile'].split('/')[-1],
                "location": r['location'].split('/')[-1],
                "usedDate": r['usedDate'],
                "expiresDate": r['expiresDate'],
                "usedBy": r['usedBy']
            } for r in recent_usage]
        }
    except Exception as e:
        logger.error(f"Error getting usage stats: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# SharePoint sharing URLs for each round type folder
# These are the dedicated folders for organized round storage
ROUND_FOLDER_URLS = {
    'mc': 'https://bhentertainment.sharepoint.com/:f:/g/IgCbqWiBy2MFQ6_SQoGyQNCCAe8uXIVo0wV1gJyKRIFMQbs?e=KDPjsc',
    'reg': 'https://bhentertainment.sharepoint.com/:f:/g/IgAsoNFIx__sSKd8wqNszKMPAcvTA-6Te9vAmmiKFchoJfo?e=sgrIRB',
    'misc': 'https://bhentertainment.sharepoint.com/:f:/g/IgA6mWLGMG5RS4mcZ85ijeloAQ0qySX3Ziy9iSX1NkK2fxU?e=Si5xCL',
    'mys': 'https://bhentertainment.sharepoint.com/:f:/g/IgDxBtJL1z7LRK-1FG7ho1OZAYMs-ClM9qZWi0lyOTUxdt8?e=pqclm7',
    'big': 'https://bhentertainment.sharepoint.com/:f:/g/IgAInn1huE6eRbwIeKCxwZE9AcTSRIEgDdsAwsc9W2h0ygo?e=Qmdu7X'
}


@router.get("/round-files/{round_type}")
async def get_round_files_by_type(round_type: str, location: Optional[str] = None) -> List[Dict[str, str]]:
    """
    Get all .pptx files for a specific round type, filtered by location usage.
    Files used in the last 6 months for the specified location are excluded.
    
    Args:
        round_type: One of 'mc', 'reg', 'misc', 'mys', 'big'
        location: Optional location path to filter out recently used files
    """
    try:
        sp = SharePointService()
        
        # Get the sharing URL for this round type
        if round_type not in ROUND_FOLDER_URLS:
            raise HTTPException(status_code=400, detail="Invalid round type")
        
        sharing_url = ROUND_FOLDER_URLS[round_type]
        
        # Use the new method to list folder contents from sharing URL
        logger.info(f"Fetching {round_type} rounds from SharePoint sharing URL...")
        items = sp.list_folder_contents_by_sharing_url(sharing_url)
        
        # Collect all .pptx files (these are now directly in the folder, not in subfolders)
        all_files = []
        for item in items:
            # Check if it's a .pptx file
            if item.get('file') and item['name'].endswith('.pptx') and not item['name'].startswith('00_'):
                # Build a path reference using the sharing URL approach
                # Store the item ID for later retrieval
                file_id = item.get('id')
                parent_ref = item.get('parentReference', {})
                drive_id = parent_ref.get('driveId', '')
                
                all_files.append({
                    'id': file_id,
                    'name': item['name'].replace('.pptx', ''),
                    'folder': round_type.upper(),
                    'path': f"sharepoint://{drive_id}/{file_id}",  # New path format for sharing URL items
                    'driveId': drive_id,
                    'itemId': file_id,
                    'displayName': item['name'].replace('.pptx', ''),
                    'sharingUrl': sharing_url
                })
            # Also check if it's a subfolder (in case rounds are organized in subfolders)
            elif item.get('folder'):
                # List contents of subfolder
                subfolder_id = item.get('id')
                parent_ref = item.get('parentReference', {})
                drive_id = parent_ref.get('driveId', '')
                
                if drive_id and subfolder_id:
                    try:
                        token = sp.get_access_token()
                        headers = {'Authorization': f'Bearer {token}'}
                        subfolder_url = f'https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{subfolder_id}/children'
                        
                        import requests as req
                        subfolder_response = req.get(subfolder_url, headers=headers)
                        
                        if subfolder_response.status_code == 200:
                            subfolder_items = subfolder_response.json().get('value', [])
                            for subitem in subfolder_items:
                                if subitem.get('file') and subitem['name'].endswith('.pptx') and not subitem['name'].startswith('00_'):
                                    sub_file_id = subitem.get('id')
                                    all_files.append({
                                        'id': sub_file_id,
                                        'name': subitem['name'].replace('.pptx', ''),
                                        'folder': f"{round_type.upper()}/{item['name']}",
                                        'path': f"sharepoint://{drive_id}/{sub_file_id}",
                                        'driveId': drive_id,
                                        'itemId': sub_file_id,
                                        'displayName': f"{item['name']} - {subitem['name'].replace('.pptx', '')}",
                                        'sharingUrl': sharing_url
                                    })
                    except Exception as e:
                        logger.warning(f"Could not list subfolder {item['name']}: {str(e)}")
        
        logger.info(f"Found {len(all_files)} {round_type} round files")
        
        # Filter out recently used files for this location (180-day lockout)
        if location and db is not None:
            from datetime import timedelta
            now_iso = datetime.utcnow().isoformat()
            cutoff_iso = (datetime.utcnow() - timedelta(days=180)).isoformat()
            
            # Extract the location name from the path for flexible matching
            # e.g. "01_Trivia/Web App/00_Builder/02_Locations/04_WP Gilbert" -> "WP Gilbert"
            import re as re_mod
            loc_name = location.split('/')[-1] if '/' in location else location
            loc_name_clean = re_mod.sub(r'^\d+_', '', loc_name)  # Remove leading numbers like "04_"
            
            # Match any round_usage where the location contains this venue name
            location_regex = f'({re_mod.escape(loc_name)}|{re_mod.escape(loc_name_clean)})'
            
            used_records = await db.round_usage.find({
                'location': {'$regex': location_regex, '$options': 'i'},
                'usedDate': {'$gte': cutoff_iso}
            }).to_list(5000)
            
            # Build set of used round names (normalized) and paths
            used_names = set()
            used_paths_set = set()
            for usage in used_records:
                if usage.get('roundFileName'):
                    used_names.add(usage['roundFileName'].lower().strip())
                if usage.get('roundFile'):
                    used_paths_set.add(usage['roundFile'])
                # Also match by the display name from the round
                name = usage.get('roundFileName', '')
                if name:
                    # Normalize: "BIG_Cactus League (Hard)" matches "BIG_Cactus League (Hard)"
                    used_names.add(name.lower().strip())
            
            before_count = len(all_files)
            all_files = [f for f in all_files if 
                f['name'].lower().strip() not in used_names and 
                f.get('displayName', '').lower().strip() not in used_names and
                f['path'] not in used_paths_set]
            
            filtered_count = before_count - len(all_files)
            if filtered_count > 0:
                logger.info(f"Filtered out {filtered_count} used rounds for '{loc_name_clean}' (180-day lockout, {len(used_names)} unique names blocked)")
        
        return sorted(all_files, key=lambda x: x['displayName'])
        
    except Exception as e:
        logger.error(f"Error fetching round files: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
