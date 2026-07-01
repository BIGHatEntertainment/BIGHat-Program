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


# ----- Local-mode helpers -----
_LOCAL_ROUND_FOLDER_MAP = {
    'mc':   '01_Trivia/Web App/00_Builder/01_Rounds/01_MC',
    'reg':  '01_Trivia/Web App/00_Builder/01_Rounds/02_REG',
    'misc': '01_Trivia/Web App/00_Builder/01_Rounds/03_MISC',
    'mys':  '01_Trivia/Web App/00_Builder/01_Rounds/04_MYS',
    'big':  '01_Trivia/Web App/00_Builder/01_Rounds/05_BIG',
}


def _is_local_mode() -> bool:
    """True when the asset factory will hand back a LocalAssetService."""
    try:
        from native.asset_factory import can_use_cloud
        return not can_use_cloud()
    except Exception:
        return False


def _list_local_round_files(round_type: str) -> List[Dict[str, str]]:
    """List .pptx files in the conventional local round folder."""
    folder = _LOCAL_ROUND_FOLDER_MAP.get(round_type.lower())
    if not folder:
        return []
    sp = SharePointService()  # transparently swapped to LocalAssetService
    items = sp.list_folder_contents(folder)
    rounds: List[Dict[str, str]] = []
    for item in items:
        if item.get('file') and item['name'].endswith('.pptx'):
            rounds.append({
                'id': item['id'],
                'name': item['name'].replace('.pptx', ''),
                'path': item['id'],
                'type': round_type.upper(),
                'driveId': 'local',
                'itemId': item['id'],
                'displayName': item['name'].replace('.pptx', ''),
                'folder': round_type.upper(),
                'sharingUrl': '',
            })
    return rounds


@router.get("/hosts")
async def get_hosts() -> List[Dict[str, str]]:
    """List all hosts available for the Trivia Presenter host-picker.

    v32.0.0-alpha.31: SharePoint fully decommissioned. In native mode
    we source hosts from `system_config.json → users[]` (merged with
    `db.users` when present) so the merchant's Master Admin + any
    added sub-admins/hosts show up immediately after setup — no
    intermittent empty dropdown.

    Response shape kept identical to the pre-alpha.31 SharePoint payload
    so `TriviaBuilderWizard.jsx` (and SlotMachineRandomizer) don't need
    a matching frontend edit:
        [{ id, name, path, host_image_16x9?, host_image_9x16?,
           profile_picture?, home_city? }]
    where `path` = the 16:9 slide GIF URL the presenter loads as slide 1.
    """
    hosts: List[Dict[str, str]] = []
    seen_emails: set[str] = set()

    # Native config users (source of truth on standalone installs)
    try:
        from native.db_factory import is_native as _is_native
        if _is_native():
            from native import config_manager
            for u in (config_manager.config.get("users", []) or []):
                email = (u.get("email") or "").lower().strip()
                if not email or email in seen_emails:
                    continue
                display = u.get("display_name") or (
                    f"{u.get('first_name','')} {u.get('last_name','')}".strip()
                ) or email
                hosts.append({
                    "id": u.get("id") or email,
                    "name": display,
                    "path": u.get("host_image_16x9") or "",
                    "host_image_16x9": u.get("host_image_16x9") or "",
                    "host_image_9x16": u.get("host_image_9x16") or "",
                    "profile_picture": u.get("profile_picture") or "",
                    "home_city": u.get("home_city") or "",
                    "role": u.get("role") or "host",
                })
                seen_emails.add(email)
    except Exception as e:
        logger.warning(f"[trivia/hosts] native config source failed: {e}")

    # Merge in db.users (covers cloud mode + any users created via the
    # native admin router that haven't rehydrated config yet).
    try:
        if db is not None:
            docs = await db.users.find(
                {"role": {"$in": ["master_admin", "admin", "host"]}},
                {"password_hash": 0},
            ).to_list(1000)
            for u in docs:
                email = (u.get("email") or "").lower().strip()
                if not email or email in seen_emails:
                    continue
                hosts.append({
                    "id": u.get("native_user_id") or str(u.get("_id") or u.get("id") or email),
                    "name": u.get("name") or email,
                    "path": u.get("host_image_16x9") or "",
                    "host_image_16x9": u.get("host_image_16x9") or "",
                    "host_image_9x16": u.get("host_image_9x16") or "",
                    "profile_picture": u.get("profile_picture") or "",
                    "home_city": u.get("home_city") or "",
                    "role": u.get("role") or "host",
                })
                seen_emails.add(email)
    except Exception as e:
        logger.warning(f"[trivia/hosts] db.users merge failed: {e}")

    # Sort master_admin first, then admin, then host, alpha-by-name inside each tier
    _tier = {"master_admin": 0, "admin": 1, "host": 2}
    hosts.sort(key=lambda h: (_tier.get(h.get("role", "host"), 3), (h.get("name") or "").lower()))
    return hosts


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
    if _is_local_mode():
        out: List[Dict[str, str]] = []
        for rt in _LOCAL_ROUND_FOLDER_MAP.keys():
            out.extend(_list_local_round_files(rt))
        return sorted(out, key=lambda x: (x['type'], x['name']))
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
    if _is_local_mode():
        return _list_local_round_files('mc')
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
    if _is_local_mode():
        return _list_local_round_files('reg')
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
    if _is_local_mode():
        return _list_local_round_files('misc')
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
    if _is_local_mode():
        return _list_local_round_files('mys')
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
    if _is_local_mode():
        return _list_local_round_files('big')
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
    if _is_local_mode():
        # Local-mode short-circuit — list from disk and apply 180-day lockout
        all_files = _list_local_round_files(round_type)
        if location and db is not None and all_files:
            from datetime import timedelta
            import re as re_mod
            now = datetime.utcnow()
            cutoff_dt = now - timedelta(days=180)
            cutoff_iso = cutoff_dt.isoformat()
            loc_name = location.split('/')[-1] if '/' in location else location
            loc_name_clean = re_mod.sub(r'^\d+_', '', loc_name)
            location_regex = f'({re_mod.escape(loc_name)}|{re_mod.escape(loc_name_clean)})'
            try:
                used_records = await db.round_usage.find({
                    'location': {'$regex': location_regex, '$options': 'i'},
                    '$or': [
                        {'usedDate': {'$gte': cutoff_dt}},
                        {'usedDate': {'$gte': cutoff_iso}},
                    ]
                }).to_list(5000)
            except Exception:
                used_records = []
            used_names = {(u.get('roundFileName') or '').lower().strip() for u in used_records}
            all_files = [f for f in all_files if f['name'].lower().strip() not in used_names]
        return sorted(all_files, key=lambda x: x['displayName'])
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
            now = datetime.utcnow()
            cutoff_dt = now - timedelta(days=180)
            cutoff_iso = cutoff_dt.isoformat()
            
            import re as re_mod
            loc_name = location.split('/')[-1] if '/' in location else location
            loc_name_clean = re_mod.sub(r'^\d+_', '', loc_name)
            location_regex = f'({re_mod.escape(loc_name)}|{re_mod.escape(loc_name_clean)})'
            
            # Query with both datetime and string comparison for usedDate
            used_records = await db.round_usage.find({
                'location': {'$regex': location_regex, '$options': 'i'},
                '$or': [
                    {'usedDate': {'$gte': cutoff_dt}},      # datetime objects
                    {'usedDate': {'$gte': cutoff_iso}},      # ISO strings
                ]
            }).to_list(5000)
            
            # Build set of used round names and paths
            used_names = set()
            used_paths_set = set()
            for usage in used_records:
                rn = usage.get('roundFileName', '')
                if rn:
                    used_names.add(rn.lower().strip())
                rf = usage.get('roundFile', '')
                if rf:
                    used_paths_set.add(rf)
            
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
