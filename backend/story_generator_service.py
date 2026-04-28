"""
Story Generator Service - Creates MP4 videos for Instagram stories from trivia presentations.

Output: 20-second MP4 video with:
- Location image (3 seconds)
- Host image (3 seconds)  
- Background image with rounds layout (14 seconds)

Encoding: Uses FFmpeg directly for 10x faster generation (~3-5 seconds vs ~30 seconds)

Round colors:
- Green: Multiple Choice (MC) - always first
- Red: REG (General)
- Blue: MISC (Specific)
- Purple: Mystery (MYS)
- Yellow: BIG Question - always last

SharePoint folder structure (01_Socials):
- 01_Locations/{location_folder}/{name}.jpg - Location images
- 02_Hosts/{name}.png - Host images (static PNG)
- 03_Backgrounds/{location_folder}/{N} Rounds.png - Background images by round count
"""

import uuid
import os
import logging
import re
import io
import subprocess
from typing import List, Dict, Optional, Tuple
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import shutil

logger = logging.getLogger(__name__)

# Bundled font path (included in repo, no system install needed)
BUNDLED_FONT_PATH = Path(__file__).parent / 'assets' / 'fonts' / 'Lemonada-Bold.ttf'

# Ensure required system dependencies are installed
def _ensure_dependencies():
    """Install required system dependencies if missing"""
    
    # Check FFmpeg
    if not shutil.which('ffmpeg'):
        logger.warning("FFmpeg not found, attempting to install...")
        try:
            result = subprocess.run(
                ['apt-get', 'update', '-qq'],
                capture_output=True, timeout=60
            )
            result = subprocess.run(
                ['apt-get', 'install', '-y', 'ffmpeg'],
                capture_output=True, timeout=120
            )
            if result.returncode == 0:
                logger.info("FFmpeg installed successfully")
            else:
                logger.error(f"Failed to install FFmpeg: {result.stderr.decode()}")
        except Exception as e:
            logger.error(f"Error installing FFmpeg: {e}")
    
    # Verify bundled font exists
    if BUNDLED_FONT_PATH.exists():
        logger.info(f"Bundled Lemonada font found at {BUNDLED_FONT_PATH}")
    else:
        logger.warning(f"Bundled Lemonada font not found at {BUNDLED_FONT_PATH}")

# Run dependency check at module load
_ensure_dependencies()

# Round type to color mapping
ROUND_COLORS = {
    'MC': '#22C55E',      # Green - Multiple Choice
    'REG': '#EF4444',     # Red - General
    'MISC': '#3B82F6',    # Blue - Specific
    'MYS': '#A855F7',     # Purple - Mystery
    'BIG': '#FFC107'      # Yellow - BIG Question
}

ROUND_DISPLAY_NAMES = {
    'MC': 'Multiple Choice',
    'REG': 'General',
    'MISC': 'Specific',
    'MYS': 'Mystery',
    'BIG': 'BIG Question'
}

# Canvas size for Instagram Stories (9:16 aspect ratio)
STORY_WIDTH = 1080
STORY_HEIGHT = 1920

# Base path for local assets (fallback)
ASSETS_DIR = Path(__file__).parent / 'assets'

# SharePoint folder path for social media assets
SHAREPOINT_SOCIALS_BASE = '01_Trivia/Web App/01_Socials'


class StoryGeneratorService:
    def __init__(self):
        self.locations_dir = ASSETS_DIR / 'locations'
        self.hosts_dir = ASSETS_DIR / 'hosts'
        self.backgrounds_dir = ASSETS_DIR / 'backgrounds'
        self.generated_dir = ASSETS_DIR / 'generated'
        self._sharepoint_service = None
        
        # SharePoint folder paths for Story Generator assets
        # Primary: 01_Socials folder (dedicated story assets)
        self.sp_locations_folder = f'{SHAREPOINT_SOCIALS_BASE}/01_Locations'
        self.sp_hosts_folder = f'{SHAREPOINT_SOCIALS_BASE}/02_Hosts'
        self.sp_backgrounds_folder = f'{SHAREPOINT_SOCIALS_BASE}/03_Backgrounds'
        
        # Alternative: Builder's location folders (may contain location images)
        self.sp_builder_locations_base = '01_Trivia/Web App/00_Builder/02_Locations'
        
        # Cache for SharePoint assets
        self._sp_assets_cache = {
            'locations': None,
            'hosts': None,
            'backgrounds': None
        }
        
        # Ensure local directories exist (for fallback and generated files)
        for directory in [self.locations_dir, self.hosts_dir, self.backgrounds_dir, self.generated_dir]:
            directory.mkdir(parents=True, exist_ok=True)
        
        # Direct Graph API config for SharePoint asset folders
        self._graph_drive_id = "b!vFnSKrOPL02dj2-MZU_EHmAti4Py2yROjNNkPjQrBjDvfYp5Cu28QIG93vJSp4xs"
        self._graph_folders = {
            "locations": "01Z4PLCYUCPKMVK5JXCZC2PRXULQ5FNUTH",
            "hosts": "01Z4PLCYSUGLYAMDEBLFDZR3BRN6EPPJI7",
            "backgrounds": "01Z4PLCYWP7NFIQ4Q4HBA3R6HF2OQGIEI7"
        }
        self._graph_token_cache = {"token": None, "expires": 0}
        
        # Event story SharePoint sharing URLs (Bingo & Karaoke)
        self._event_sharing_urls = {
            'bingo': {
                'locations': 'https://bhentertainment.sharepoint.com/:f:/g/IgA2wHK1vZxNQKNaT9W89dX8AU8uVh0VoHvLzk7XmVFBbBM?e=aY5tfm',
                'hosts': 'https://bhentertainment.sharepoint.com/:f:/g/IgAVO16gi-VJS5kxcKIYKg6rAY7XsRxJCFYYXAEHMjjwxY8?e=zV2Zhe',
            },
            'karaoke': {
                'locations': 'https://bhentertainment.sharepoint.com/:f:/g/IgCNzRVqSjgLT6lSdBhDe_-_AdO31SsuEN6QIje7B2Xmsq0?e=Jl0zca',
                'hosts': 'https://bhentertainment.sharepoint.com/:f:/g/IgDoLqzdH5CSQJmjnfW-RjalAV9PdWce-PjExTMclVYlckA?e=Ejr2ZA',
            }
        }
        # Cache for resolved sharing URLs → (drive_id, item_id)
        self._event_folder_cache = {}
        # Cache for event folder listings
        self._event_assets_cache = {}
    
    def _get_graph_token(self):
        """Get Microsoft Graph API token"""
        import time, requests as sync_requests
        now = time.time()
        if self._graph_token_cache["token"] and now < self._graph_token_cache["expires"]:
            return self._graph_token_cache["token"]
        tenant = os.environ.get("ROUNDMAKER_TENANT_ID", os.environ.get("AZURE_TENANT_ID", ""))
        cid = os.environ.get("ROUNDMAKER_CLIENT_ID", os.environ.get("AZURE_CLIENT_ID", ""))
        csec = os.environ.get("ROUNDMAKER_CLIENT_SECRET", os.environ.get("AZURE_CLIENT_SECRET", ""))
        if not all([tenant, cid, csec]):
            return None
        r = sync_requests.post(f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token", data={
            "grant_type": "client_credentials", "client_id": cid, "client_secret": csec,
            "scope": "https://graph.microsoft.com/.default"
        }, timeout=10)
        if r.status_code == 200:
            self._graph_token_cache["token"] = r.json()["access_token"]
            self._graph_token_cache["expires"] = now + 3500
            return self._graph_token_cache["token"]
        return None
    
    def _graph_list_folder(self, folder_id):
        """List items in a SharePoint folder via Graph API"""
        import requests as sync_requests
        token = self._get_graph_token()
        if not token: return []
        r = sync_requests.get(f"https://graph.microsoft.com/v1.0/drives/{self._graph_drive_id}/items/{folder_id}/children?$top=200",
            headers={"Authorization": f"Bearer {token}"}, timeout=15)
        return r.json().get("value", []) if r.status_code == 200 else []
    
    def _graph_download_file(self, item_id):
        """Download a file from SharePoint via Graph API"""
        import requests as sync_requests
        token = self._get_graph_token()
        if not token: return None
        r = sync_requests.get(f"https://graph.microsoft.com/v1.0/drives/{self._graph_drive_id}/items/{item_id}/content",
            headers={"Authorization": f"Bearer {token}"}, timeout=30, allow_redirects=True)
        return r.content if r.status_code == 200 else None
    
    def _graph_find_and_download(self, folder_type, name_match, extensions=None):
        """Find and download a file from a SharePoint folder.
        Searches in the folder and its subfolders for a matching file.
        """
        folder_id = self._graph_folders.get(folder_type)
        if not folder_id: return None
        
        items = self._graph_list_folder(folder_id)
        clean_name = name_match.lower().replace('_', ' ').strip()
        
        # Check if any items are subfolders matching the name
        for item in items:
            item_name = item.get("name", "").lower()
            if item.get("folder") and (clean_name in item_name or item_name in clean_name):
                # It's a matching subfolder - list its contents
                sub_items = self._graph_list_folder(item["id"])
                for sub in sub_items:
                    sub_name = sub.get("name", "").lower()
                    if extensions:
                        if any(sub_name.endswith(ext.lower()) for ext in extensions):
                            content = self._graph_download_file(sub["id"])
                            if content:
                                logger.info(f"Graph: Downloaded {sub['name']} from {item['name']}/")
                                return content
                    else:
                        content = self._graph_download_file(sub["id"])
                        if content:
                            return content
        
        # Check direct files in the folder
        for item in items:
            if item.get("folder"): continue
            item_name = item.get("name", "").lower()
            name_no_ext = item_name.rsplit('.', 1)[0] if '.' in item_name else item_name
            if clean_name in name_no_ext or name_no_ext in clean_name:
                if extensions:
                    if any(item_name.endswith(ext.lower()) for ext in extensions):
                        content = self._graph_download_file(item["id"])
                        if content:
                            logger.info(f"Graph: Downloaded {item['name']}")
                            return content
                else:
                    content = self._graph_download_file(item["id"])
                    if content:
                        return content
        
        return None

    def _resolve_sharing_url(self, sharing_url):
        """Resolve a SharePoint sharing URL to (drive_id, item_id) via Graph API."""
        import base64
        import requests as sync_requests
        
        cache_key = sharing_url.split('?')[0]  # Strip query params for cache key
        if cache_key in self._event_folder_cache:
            return self._event_folder_cache[cache_key]
        
        token = self._get_graph_token()
        if not token:
            logger.error("Cannot resolve sharing URL - no Graph token")
            return None, None
        
        # Encode the sharing URL for the shares API
        encoded = base64.urlsafe_b64encode(sharing_url.encode()).decode().rstrip('=')
        share_token = f"u!{encoded}"
        
        r = sync_requests.get(
            f"https://graph.microsoft.com/v1.0/shares/{share_token}/driveItem",
            headers={"Authorization": f"Bearer {token}"}, timeout=15
        )
        
        if r.status_code == 200:
            data = r.json()
            drive_id = data.get("parentReference", {}).get("driveId")
            item_id = data.get("id")
            logger.info(f"Resolved sharing URL → drive={drive_id[:20]}..., item={item_id}")
            self._event_folder_cache[cache_key] = (drive_id, item_id)
            return drive_id, item_id
        else:
            logger.error(f"Failed to resolve sharing URL: {r.status_code} - {r.text[:200]}")
            return None, None
    
    def _list_event_folder(self, drive_id, item_id):
        """List children of a folder using drive_id and item_id."""
        import requests as sync_requests
        token = self._get_graph_token()
        if not token:
            return []
        r = sync_requests.get(
            f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}/children?$top=200",
            headers={"Authorization": f"Bearer {token}"}, timeout=15
        )
        return r.json().get("value", []) if r.status_code == 200 else []
    
    def _download_event_file(self, drive_id, item_id):
        """Download a file from SharePoint using drive_id and item_id."""
        import requests as sync_requests
        token = self._get_graph_token()
        if not token:
            return None
        r = sync_requests.get(
            f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}/content",
            headers={"Authorization": f"Bearer {token}"}, timeout=60, allow_redirects=True
        )
        return r.content if r.status_code == 200 else None
    
    def get_event_assets(self, event_type):
        """Get available locations and hosts for an event type (bingo/karaoke).
        Returns: { locations: [{name, id}], hosts: [{name, id}] }
        """
        cache_key = f"{event_type}"
        if cache_key in self._event_assets_cache:
            return self._event_assets_cache[cache_key]
        
        urls = self._event_sharing_urls.get(event_type)
        if not urls:
            return {"locations": [], "hosts": []}
        
        result = {"locations": [], "hosts": []}
        
        # Resolve and list locations folder
        drive_id, item_id = self._resolve_sharing_url(urls['locations'])
        if drive_id and item_id:
            items = self._list_event_folder(drive_id, item_id)
            for item in items:
                name = item.get("name", "")
                if item.get("folder"):
                    continue  # Skip subfolders
                ext = name.rsplit('.', 1)[-1].lower() if '.' in name else ''
                if ext in ['jpg', 'jpeg', 'png', 'webp']:
                    clean_name = name.rsplit('.', 1)[0]
                    result["locations"].append({
                        "name": clean_name,
                        "id": item["id"],
                        "drive_id": drive_id,
                        "filename": name
                    })
            logger.info(f"[EventAssets] {event_type} locations: {len(result['locations'])}")
        
        # Resolve and list hosts folder
        drive_id, item_id = self._resolve_sharing_url(urls['hosts'])
        if drive_id and item_id:
            items = self._list_event_folder(drive_id, item_id)
            for item in items:
                name = item.get("name", "")
                if item.get("folder"):
                    continue
                ext = name.rsplit('.', 1)[-1].lower() if '.' in name else ''
                if ext in ['gif', 'jpg', 'jpeg', 'png', 'webp']:
                    clean_name = name.rsplit('.', 1)[0]
                    result["hosts"].append({
                        "name": clean_name,
                        "id": item["id"],
                        "drive_id": drive_id,
                        "filename": name,
                        "is_gif": ext == 'gif'
                    })
            logger.info(f"[EventAssets] {event_type} hosts: {len(result['hosts'])}")
        
        self._event_assets_cache[cache_key] = result
        return result
    
    def download_event_asset(self, drive_id, item_id):
        """Download an event asset by drive_id and item_id."""
        return self._download_event_file(drive_id, item_id)


    
    @property
    def sharepoint_service(self):
        """Lazy load SharePoint service"""
        if self._sharepoint_service is None:
            try:
                from sharepoint_service import SharePointService
                self._sharepoint_service = SharePointService()
                logger.info("SharePoint service initialized successfully")
            except Exception as e:
                logger.warning(f"Could not initialize SharePoint service: {e}. Using local assets only.")
                self._sharepoint_service = False  # Mark as unavailable
        return self._sharepoint_service if self._sharepoint_service else None
    
    def _list_sharepoint_folder(self, folder_path: str, files_only: bool = True) -> List[Dict]:
        """List contents of a SharePoint folder
        
        Args:
            folder_path: Path to the folder in SharePoint
            files_only: If True, return only files. If False, return all items (including folders)
        """
        if not self.sharepoint_service:
            return []
        try:
            items = self.sharepoint_service.list_folder_contents(folder_path)
            if files_only:
                return [item for item in items if 'file' in item]  # Filter to files only
            else:
                return items  # Return all items including folders
        except Exception as e:
            logger.error(f"Error listing SharePoint folder {folder_path}: {e}")
            return []
    
    def _download_sharepoint_file(self, file_path: str) -> Optional[bytes]:
        """Download a file from SharePoint as bytes"""
        if not self.sharepoint_service:
            return None
        try:
            return self.sharepoint_service.download_file_to_bytes(file_path)
        except Exception as e:
            logger.error(f"Error downloading SharePoint file {file_path}: {e}")
            return None
    
    def resolve_round_name(self, round_file: str) -> str:
        """Resolve the actual round name from a SharePoint file reference.
        
        The round file is stored as 'sharepoint://{drive_id}/{item_id}'.
        This method queries SharePoint to get the actual filename/name.
        
        Args:
            round_file: The SharePoint file reference (e.g., 'sharepoint://b!.../01Z4PLCYWELSHNUKQYOBFJUJKNMUR67DFV')
            
        Returns:
            The actual round name (e.g., 'Geography', 'Music', 'The Office') or a fallback.
        """
        if not self.sharepoint_service:
            return "Unknown"
        
        try:
            # Extract item ID from sharepoint:// URL
            if round_file.startswith('sharepoint://'):
                parts = round_file.split('/')
                if len(parts) >= 2:
                    item_id = parts[-1]
                    
                    # Query SharePoint for item info
                    item_info = self.sharepoint_service.get_item_by_id(item_id)
                    if item_info:
                        name = item_info.get('name', '')
                        # Remove .pptx extension
                        if name.endswith('.pptx'):
                            name = name[:-5]
                        # Remove numeric prefix if present (e.g., "01_Geography" -> "Geography")
                        name = re.sub(r'^\d+_', '', name)
                        # Remove "BIG_" prefix for BIG rounds
                        name = re.sub(r'^BIG_', '', name, flags=re.IGNORECASE)
                        # Remove trailing underscore and numbers (e.g., "TV Shows_1" -> "TV Shows")
                        name = re.sub(r'_\d+$', '', name)
                        # Replace underscores with spaces for nicer display
                        name = name.replace('_', ' ')
                        return name.strip() if name else "Unknown"
            
            return "Unknown"
        except Exception as e:
            logger.error(f"Error resolving round name from {round_file}: {e}")
            return "Unknown"
    
    def _get_sharepoint_assets(self, asset_type: str) -> List[Dict]:
        """Get assets from SharePoint folder
        
        Structure:
        - Hosts: 01_Socials/02_Hosts/{name}.png (PNG files at top level)
        - Locations: 01_Socials/01_Locations/{location_folder}/{name}.jpg (nested in subfolders)
        - Backgrounds: 01_Socials/03_Backgrounds/{location_folder}/{N} Rounds.png (nested in subfolders)
        """
        folder_map = {
            'locations': self.sp_locations_folder,
            'hosts': self.sp_hosts_folder,
            'backgrounds': self.sp_backgrounds_folder
        }
        
        folder_path = folder_map.get(asset_type)
        if not folder_path:
            return []
        
        # Check cache first (cache is cleared on refresh or after timeout)
        if self._sp_assets_cache.get(asset_type) is not None:
            return self._sp_assets_cache[asset_type]
        
        assets = []
        
        if asset_type == 'hosts':
            # Hosts are PNG files directly in the folder (Nick.png, Al.png, etc.)
            files = self._list_sharepoint_folder(folder_path, files_only=True)
            for file_info in files:
                filename = file_info.get('name', '')
                file_ext = Path(filename).suffix.lower()
                
                # Include .gif files for hosts (animated host images)
                if file_ext in ['.png', '.jpg', '.jpeg', '.webp', '.gif']:
                    stem = Path(filename).stem
                    clean_name = re.sub(r'^\d+_', '', stem)
                    
                    assets.append({
                        'id': stem,
                        'name': clean_name.replace('_', ' ').title(),
                        'path': f"{folder_path}/{filename}",
                        'type': 'image',
                        'source': 'sharepoint'
                    })
        
        elif asset_type == 'locations':
            # Locations are nested: 01_Locations/{location_folder}/{name}.jpg
            # First list all items (including folders) in the locations folder
            location_folders = self._list_sharepoint_folder(folder_path, files_only=False)
            logger.info(f"Found {len(location_folders)} items in locations folder")
            
            for folder_info in location_folders:
                folder_name = folder_info.get('name', '')
                # Check if this is a folder (has 'folder' key in response)
                if not folder_name or 'folder' not in folder_info:
                    continue
                
                logger.info(f"Scanning location folder: {folder_name}")
                subfolder_path = f"{folder_path}/{folder_name}"
                files = self._list_sharepoint_folder(subfolder_path, files_only=True)
                
                for file_info in files:
                    filename = file_info.get('name', '')
                    file_ext = Path(filename).suffix.lower()
                    
                    # Look for .jpg files (location images)
                    if file_ext in ['.jpg', '.jpeg', '.png', '.webp']:
                        stem = Path(filename).stem
                        clean_folder_name = re.sub(r'^\d+_', '', folder_name)
                        
                        assets.append({
                            'id': folder_name,  # Use folder name as ID for matching
                            'name': clean_folder_name.replace('_', ' ').title(),
                            'path': f"{subfolder_path}/{filename}",
                            'type': 'image',
                            'source': 'sharepoint',
                            'folder': folder_name
                        })
                        logger.info(f"Found location image: {filename} in {folder_name}")
                        break  # Only take first image per location folder
        
        elif asset_type == 'backgrounds':
            # Backgrounds are nested: 03_Backgrounds/{location_folder}/{location_name}.jpg or {N} Rounds.png
            # First list all items (including folders) in the backgrounds folder
            location_folders = self._list_sharepoint_folder(folder_path, files_only=False)
            logger.info(f"Found {len(location_folders)} items in backgrounds folder")
            
            for folder_info in location_folders:
                folder_name = folder_info.get('name', '')
                # Check if this is a folder (has 'folder' key in response)
                if not folder_name or 'folder' not in folder_info:
                    continue
                
                logger.info(f"Scanning background folder: {folder_name}")
                subfolder_path = f"{folder_path}/{folder_name}"
                files = self._list_sharepoint_folder(subfolder_path, files_only=True)
                
                for file_info in files:
                    filename = file_info.get('name', '')
                    file_ext = Path(filename).suffix.lower()
                    
                    # Accept image files (.png, .jpg, .jpeg, .webp)
                    if file_ext in ['.png', '.jpg', '.jpeg', '.webp']:
                        stem = Path(filename).stem
                        clean_folder_name = re.sub(r'^\d+_', '', folder_name)
                        
                        # Check if it's the old "{N} Rounds.png" format
                        rounds_match = re.match(r'(\d+)\s*[Rr]ounds?', stem)
                        if rounds_match:
                            num_rounds = int(rounds_match.group(1))
                            assets.append({
                                'id': f"{folder_name}_{num_rounds}",
                                'name': f"{clean_folder_name.replace('_', ' ').title()} - {num_rounds} Rounds",
                                'path': f"{subfolder_path}/{filename}",
                                'type': 'image',
                                'source': 'sharepoint',
                                'folder': folder_name,
                                'numRounds': num_rounds
                            })
                        else:
                            # New format: file named after location (e.g., "Bristol's Mesa.jpg")
                            assets.append({
                                'id': f"{folder_name}_{stem}",
                                'name': f"{clean_folder_name.replace('_', ' ').title()} - {stem}",
                                'path': f"{subfolder_path}/{filename}",
                                'type': 'image',
                                'source': 'sharepoint',
                                'folder': folder_name,
                                'filename': stem,  # Store filename for matching
                                'numRounds': 0  # Not round-based naming
                            })
                            logger.info(f"Found background with location name: {stem} in folder {folder_name}")
        
        # Cache the results
        self._sp_assets_cache[asset_type] = assets
        logger.info(f"Loaded {len(assets)} {asset_type} assets from SharePoint")
        return assets
    
    def refresh_sharepoint_cache(self):
        """Clear SharePoint asset cache to fetch fresh data"""
        self._sp_assets_cache = {
            'locations': None,
            'hosts': None,
            'backgrounds': None
        }
        logger.info("SharePoint asset cache cleared")
    
    def get_available_assets(self) -> Dict:
        """Get list of available assets from SharePoint and local storage"""
        locations = []
        hosts = []
        backgrounds = []
        
        # First, get SharePoint assets
        sp_locations = self._get_sharepoint_assets('locations')
        sp_hosts = self._get_sharepoint_assets('hosts')
        sp_backgrounds = self._get_sharepoint_assets('backgrounds')
        
        locations.extend(sp_locations)
        hosts.extend(sp_hosts)
        backgrounds.extend(sp_backgrounds)
        
        # Then, scan local directories (as fallback/additional)
        if self.locations_dir.exists():
            for f in self.locations_dir.iterdir():
                if f.suffix.lower() in ['.png', '.jpg', '.jpeg', '.webp']:
                    name = f.stem.replace('_', ' ').title()
                    # Only add if not already from SharePoint
                    if not any(a['id'].lower() == f.stem.lower() for a in locations):
                        locations.append({
                            'id': f.stem,
                            'name': name,
                            'path': str(f),
                            'type': 'image',
                            'source': 'local'
                        })
        
        if self.hosts_dir.exists():
            for f in self.hosts_dir.iterdir():
                # Prioritize PNG for hosts (current standard)
                if f.suffix.lower() in ['.png', '.jpg', '.jpeg', '.webp']:
                    name = f.stem.replace('_', ' ').title()
                    if not any(a['id'].lower() == f.stem.lower() for a in hosts):
                        hosts.append({
                            'id': f.stem,
                            'name': name,
                            'path': str(f),
                            'type': 'image',
                            'source': 'local'
                        })
        
        if self.backgrounds_dir.exists():
            for f in self.backgrounds_dir.iterdir():
                if f.suffix.lower() in ['.png', '.jpg', '.jpeg', '.webp']:
                    name = f.stem.replace('_', ' ').title()
                    if not any(a['id'].lower() == f.stem.lower() for a in backgrounds):
                        backgrounds.append({
                            'id': f.stem,
                            'name': name,
                            'path': str(f),
                            'type': 'image',
                            'source': 'local'
                        })
        
        return {
            'locations': locations,
            'hosts': hosts,
            'backgrounds': backgrounds,
            'sharepoint_enabled': self.sharepoint_service is not None
        }
    
    def _normalize_location_name(self, location_path: str) -> str:
        """Extract clean location name from SharePoint path"""
        # Path like: 01_Trivia/Web App/00_Builder/02_Locations/01_Monkey Pants
        parts = location_path.split('/')
        if parts:
            # Get last part and remove numeric prefix
            name = parts[-1]
            # Remove prefix like "01_", "02_", etc.
            clean_name = re.sub(r'^\d+_', '', name)
            return clean_name.replace(' ', '_').lower()
        return 'unknown'
    
    def _normalize_host_name(self, host_path: str) -> str:
        """Extract clean host name from SharePoint path"""
        # Path like: 01_Trivia/Web App/00_Builder/01_Hosts/John Smith.pptx
        parts = host_path.split('/')
        if parts:
            name = parts[-1]
            # Remove .pptx extension
            name = name.replace('.pptx', '')
            # Remove numeric prefix
            clean_name = re.sub(r'^\d+_', '', name)
            return clean_name.replace(' ', '_').lower()
        return 'unknown'
    
    def _find_asset_local(self, asset_dir: Path, name: str, extensions: List[str]) -> Optional[Path]:
        """Find an asset file locally by name (case-insensitive)"""
        name_lower = name.lower()
        for ext in extensions:
            # Try exact match
            candidate = asset_dir / f"{name}{ext}"
            if candidate.exists():
                return candidate
            
            # Try case-insensitive match
            if asset_dir.exists():
                for f in asset_dir.iterdir():
                    if f.stem.lower() == name_lower and f.suffix.lower() == ext.lower():
                        return f
                    # Also try partial match (e.g., "monkey_pants" matches "01_Monkey_Pants")
                    clean_stem = re.sub(r'^\d+_', '', f.stem).lower().replace(' ', '_')
                    if clean_stem == name_lower and f.suffix.lower() == ext.lower():
                        return f
        
        return None
    
    def _find_sharepoint_asset(self, asset_type: str, name: str, extensions: List[str], num_rounds: int = 0) -> Optional[str]:
        """Find an asset in SharePoint by name — normalizes spaces, underscores, and hyphens for matching"""
        assets = self._get_sharepoint_assets(asset_type)
        # Normalize: lowercase, replace spaces/hyphens with underscores
        name_lower = name.lower().replace(' ', '_').replace('-', '_')
        
        for asset in assets:
            # For nested assets (locations, backgrounds), use folder name for matching
            if asset_type in ['locations', 'backgrounds']:
                folder_name = asset.get('folder', '')
                folder_name_clean = re.sub(r'^\d+_', '', folder_name).lower().replace(' ', '_').replace('-', '_')
                
                # Check if location matches
                if name_lower in folder_name_clean or folder_name_clean in name_lower:
                    # For backgrounds, look for file named after the location
                    if asset_type == 'backgrounds':
                        # Get the filename without extension
                        asset_filename = Path(asset['path']).stem.lower().replace(' ', '_').replace('-', '_')
                        
                        # Check if filename matches location name (new naming convention)
                        if name_lower in asset_filename or asset_filename in name_lower or folder_name_clean in asset_filename:
                            logger.info(f"Found background for {name}: {asset['path']}")
                            return asset['path']
                        
                        # Fallback: Also check for old naming convention (numRounds)
                        asset_rounds = asset.get('numRounds', 0)
                        if num_rounds > 0 and asset_rounds == num_rounds:
                            logger.info(f"Found background for {name} with {num_rounds} rounds (old naming): {asset['path']}")
                            return asset['path']
                    else:
                        # For locations, just return the match
                        return asset['path']
            else:
                # For hosts, match by asset ID/name
                asset_name_clean = re.sub(r'^\d+_', '', asset['id']).lower().replace(' ', '_').replace('-', '_')
                asset_ext = Path(asset['path']).suffix.lower()
                
                if asset_name_clean == name_lower and asset_ext in extensions:
                    return asset['path']
                
                # Also try partial/fuzzy match
                if name_lower in asset_name_clean or asset_name_clean in name_lower:
                    if asset_ext in extensions:
                        return asset['path']
        
        return None
    
    def _load_image_from_sharepoint(self, sp_path: str) -> Optional[Image.Image]:
        """Download and load an image from SharePoint"""
        content = self._download_sharepoint_file(sp_path)
        if content:
            try:
                return Image.open(io.BytesIO(content))
            except Exception as e:
                logger.error(f"Error opening SharePoint image {sp_path}: {e}")
        return None
    
    def _get_location_image(self, location_name: str) -> Optional[Image.Image]:
        """Get location image from SharePoint via Graph API"""
        extensions = ['.jpg', '.jpeg', '.png', '.webp']
        
        # Try Graph API direct download first
        content = self._graph_find_and_download('locations', location_name, extensions)
        if content:
            try:
                img = Image.open(io.BytesIO(content))
                logger.info(f"Loaded location image from SharePoint: {location_name}")
                return img
            except Exception as e:
                logger.error(f"Failed to open location image: {e}")
        
        # Fall back to local
        local_path = self._find_asset_local(self.locations_dir, location_name, extensions)
        if local_path:
            return Image.open(local_path)
        
        logger.warning(f"No location image found for: {location_name}")
        return None
    
    def _get_host_image(self, host_name: str) -> Tuple[Optional[Image.Image], bool]:
        """Get host image from SharePoint via Graph API. Tries .gif first (animated), then static."""
        
        # Try GIF first from Graph API
        content = self._graph_find_and_download('hosts', host_name, ['.gif'])
        if content:
            try:
                img = Image.open(io.BytesIO(content))
                logger.info(f"Loaded host GIF from SharePoint: {host_name}")
                return img, True
            except Exception as e:
                logger.error(f"Failed to open host GIF: {e}")
        
        # Try static images
        content = self._graph_find_and_download('hosts', host_name, ['.png', '.jpg', '.jpeg'])
        if content:
            try:
                img = Image.open(io.BytesIO(content))
                logger.info(f"Loaded host image from SharePoint: {host_name}")
                return img, False
            except Exception as e:
                logger.error(f"Failed to open host image: {e}")
        
        # Fall back to local
        all_extensions = ['.gif', '.png', '.jpg', '.jpeg', '.webp']
        local_path = self._find_asset_local(self.hosts_dir, host_name, all_extensions)
        if local_path:
            is_gif = local_path.lower().endswith('.gif')
            return Image.open(local_path), is_gif
        
        return None, False
    
    def _get_background_image(self, location_name: str, num_rounds: int = 5) -> Optional[Image.Image]:
        """Get background image from SharePoint via Graph API"""
        extensions = ['.png', '.jpg', '.jpeg', '.webp']
        
        # Try Graph API - look in backgrounds folder for matching location subfolder
        content = self._graph_find_and_download('backgrounds', location_name, extensions)
        if content:
            try:
                img = Image.open(io.BytesIO(content))
                logger.info(f"Loaded background from SharePoint: {location_name}")
                return img
            except Exception as e:
                logger.error(f"Failed to open background: {e}")
        
        # Fall back to local
        local_path = self._find_asset_local(self.backgrounds_dir, location_name, extensions)
        if local_path:
            return Image.open(local_path)
        
        logger.warning(f"No background image found for: {location_name}")
        return None
    
    def _create_placeholder_image(self, width: int, height: int, text: str, bg_color: str = '#333333') -> Image.Image:
        """Create a placeholder image with text"""
        img = Image.new('RGB', (width, height), bg_color)
        draw = ImageDraw.Draw(img)
        
        # Try to use a nice font, fall back to default
        try:
            font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 48)
        except (IOError, OSError):
            font = ImageFont.load_default()
        
        # Calculate text position
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        x = (width - text_width) // 2
        y = (height - text_height) // 2
        
        draw.text((x, y), text, fill='white', font=font)
        return img
    
    def _resize_to_story(self, img: Image.Image) -> Image.Image:
        """Resize and crop image to fit story dimensions (9:16)"""
        # Calculate aspect ratios
        img_ratio = img.width / img.height
        story_ratio = STORY_WIDTH / STORY_HEIGHT
        
        if img_ratio > story_ratio:
            # Image is wider - crop width
            new_height = STORY_HEIGHT
            new_width = int(new_height * img_ratio)
            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            # Crop center
            left = (new_width - STORY_WIDTH) // 2
            img = img.crop((left, 0, left + STORY_WIDTH, STORY_HEIGHT))
        else:
            # Image is taller - crop height
            new_width = STORY_WIDTH
            new_height = int(new_width / img_ratio)
            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            # Crop center
            top = (new_height - STORY_HEIGHT) // 2
            img = img.crop((0, top, STORY_WIDTH, top + STORY_HEIGHT))
        
        return img
    
    def _create_rounds_overlay(self, rounds_info: List[Dict], location_name: str, num_rounds: int = 5) -> Image.Image:
        """
        Create a text overlay for ALL round names with colored boxes behind each.
        Draws every round's colored box + text (nothing is pre-drawn on the background).
        """
        overlay = Image.new('RGBA', (STORY_WIDTH, STORY_HEIGHT), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        
        # Load font
        try:
            lemonada_font = ImageFont.truetype(str(BUNDLED_FONT_PATH), 44)
            big_font = ImageFont.truetype(str(BUNDLED_FONT_PATH), 48)
        except (IOError, OSError):
            try:
                lemonada_font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 44)
                big_font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 48)
            except (IOError, OSError):
                lemonada_font = ImageFont.load_default()
                big_font = ImageFont.load_default()
        
        # Color map for each round type (RGBA)
        COLOR_MAP = {
            'MC':   (34, 197, 94, 230),    # Green
            'REG':  (239, 68, 68, 230),     # Red
            'MISC': (59, 130, 246, 230),    # Blue
            'MYS':  (168, 85, 247, 230),    # Purple
            'BIG':  (255, 193, 7, 230),     # Yellow/Gold
        }
        
        # Calculate Y positions for all rounds evenly spaced
        # Leave space at top (400px for logo area) and bottom (200px margin)
        top_start = 420
        bottom_end = 1750
        available_height = bottom_end - top_start
        
        if num_rounds <= 0:
            return overlay
        
        spacing = available_height // (num_rounds + 1)
        box_height = min(95, int((spacing - 20) * 1.1))  # 10% taller boxes
        
        def draw_text_with_outline(text, x, y, font, fill_color='white', outline_color='black', outline_width=3):
            for dx in range(-outline_width, outline_width + 1):
                for dy in range(-outline_width, outline_width + 1):
                    if dx != 0 or dy != 0:
                        draw.text((x + dx, y + dy), text, font=font, fill=outline_color)
            draw.text((x, y), text, font=font, fill=fill_color)
        
        for i, round_info in enumerate(rounds_info):
            round_type = round_info.get('type', 'REG')
            round_name = round_info.get('name', f'Round {i+1}')
            
            y_center = top_start + spacing * (i + 1)
            color = COLOR_MAP.get(round_type, (128, 128, 128, 230))
            
            # Draw the colored box — 5% narrower on each side (margin 80 -> 134)
            margin = 134  # ~12.4% margin each side (was ~7.4%), effectively 5% narrower total
            x1, x2 = margin, STORY_WIDTH - margin
            y1 = y_center - box_height // 2
            y2 = y_center + box_height // 2
            draw.rounded_rectangle([(x1, y1), (x2, y2)], radius=20, fill=color)
            
            # Choose font and text color
            use_font = big_font if round_type == 'BIG' else lemonada_font
            text_color = 'black' if round_type == 'BIG' else 'white'
            outline_color = 'white' if round_type == 'BIG' else 'black'
            outline_w = 2 if round_type == 'BIG' else 3
            
            # Draw round name text centered in the box
            bbox = draw.textbbox((0, 0), round_name, font=use_font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            x = (STORY_WIDTH - text_width) // 2
            y = y_center - text_height // 2
            draw_text_with_outline(round_name, x, y, use_font, fill_color=text_color, outline_color=outline_color, outline_width=outline_w)
            
            logger.info(f"  Drew round {i+1}: [{round_type}] {round_name} at y={y_center} color={color[:3]}")
        
        return overlay
    
    def generate_story_frames(self, presentation_data: Dict) -> Tuple[List[Image.Image], List[float]]:
        """
        Generate story frames from presentation data.
        Returns list of frames and their durations.
        
        Fetches assets from SharePoint first, falls back to local storage.
        """
        frames = []
        durations = []
        
        location_name = self._normalize_location_name(presentation_data.get('location', ''))
        host_name = self._normalize_host_name(presentation_data.get('hostFile', ''))
        rounds_info = presentation_data.get('roundFiles', [])
        
        logger.info(f"Generating story for location: {location_name}, host: {host_name}")
        
        # 1. Location image (5 seconds) - from SharePoint or local
        location_img = self._get_location_image(location_name)
        if location_img:
            location_img = location_img.convert('RGB')
        else:
            # Create placeholder
            logger.warning(f"No location image found for {location_name}, using placeholder")
            location_img = self._create_placeholder_image(
                STORY_WIDTH, STORY_HEIGHT, 
                f"Location:\n{location_name.replace('_', ' ').title()}",
                '#1a1a2e'
            )
        location_img = self._resize_to_story(location_img)
        frames.append(location_img)
        durations.append(5.0)
        
        # 2. Host image (5 seconds) - from SharePoint or local
        host_img, is_animated = self._get_host_image(host_name)
        
        if host_img:
            # Static image
            host_img = host_img.convert('RGB')
            host_img = self._resize_to_story(host_img)
            frames.append(host_img)
            durations.append(5.0)
        else:
            # Create placeholder
            logger.warning(f"No host image found for {host_name}, using placeholder")
            host_img = self._create_placeholder_image(
                STORY_WIDTH, STORY_HEIGHT,
                f"Host:\n{host_name.replace('_', ' ').title()}",
                '#16213e'
            )
            frames.append(host_img)
            durations.append(5.0)
        
        # 3. Background with rounds (15 seconds) - from SharePoint or local
        # Select background based on location AND number of rounds
        num_rounds = len(rounds_info)
        bg_img = self._get_background_image(location_name, num_rounds=num_rounds)
        if bg_img:
            bg_img = bg_img.convert('RGBA')
        else:
            # Use a default dark background
            logger.warning(f"No background image found for {location_name}, using default")
            bg_img = Image.new('RGBA', (STORY_WIDTH, STORY_HEIGHT), (26, 26, 46, 255))
        
        bg_img = self._resize_to_story(bg_img.convert('RGB')).convert('RGBA')
        
        # Resolve actual round names - use roundNames from presentation data first
        resolved_rounds = []
        round_names_list = presentation_data.get('roundNames', [])
        
        for i, rf in enumerate(rounds_info):
            round_type = rf.get('type', 'REG')
            
            # For MC and MYS, use fixed display names
            if round_type == 'MC':
                round_name = 'Multiple Choice'
            elif round_type == 'MYS':
                round_name = 'Mystery'
            else:
                # Get the actual name from roundNames array
                raw_name = round_names_list[i] if i < len(round_names_list) else rf.get('name', '')
                
                if raw_name:
                    # Clean up the name for display
                    import re as name_re
                    # Remove .pptx extension
                    clean = raw_name.replace('.pptx', '')
                    # Remove "BIG_" prefix
                    clean = name_re.sub(r'^BIG_', '', clean, flags=name_re.IGNORECASE)
                    # Remove trailing "_N" number suffixes (e.g., "1970s_1" -> "1970s")
                    clean = name_re.sub(r'_\d+$', '', clean)
                    # Replace underscores with spaces
                    clean = clean.replace('_', ' ')
                    round_name = clean.strip()
                else:
                    round_name = f'{round_type} Round'
            
            resolved_rounds.append({
                'order': rf.get('order', 0),
                'type': round_type,
                'name': round_name
            })
        
        logger.info(f"Resolved round names: {[r['name'] for r in resolved_rounds]}")
        
        # Create rounds overlay with resolved names
        rounds_overlay = self._create_rounds_overlay(resolved_rounds, location_name, num_rounds=num_rounds)
        
        # Composite
        final_bg = Image.alpha_composite(bg_img, rounds_overlay)
        frames.append(final_bg.convert('RGB'))
        durations.append(15.0)
        
        return frames, durations
    
    def generate_video(self, presentation_data: Dict, output_filename: Optional[str] = None) -> str:
        """
        Generate an MP4 video from presentation data.
        Returns path to the generated video.
        """
        try:
            # Try moviepy 2.x import first
            try:
                from moviepy import ImageClip, concatenate_videoclips
            except ImportError:
                # Fall back to moviepy 1.x import
                from moviepy.editor import ImageClip, concatenate_videoclips
        except ImportError:
            logger.error("moviepy not installed. Please install it with: pip install moviepy")
            raise ImportError("moviepy is required for video generation")
        
        # Generate frames
        frames, durations = self.generate_story_frames(presentation_data)
        
        if not frames:
            raise ValueError("No frames generated")
        
        # Create video clips
        clips = []
        temp_files = []
        
        try:
            for i, (frame, duration) in enumerate(zip(frames, durations)):
                # Save frame to temp file
                temp_path = self.generated_dir / f"temp_frame_{i}.png"
                frame.save(temp_path)
                temp_files.append(temp_path)
                
                # Create clip
                clip = ImageClip(str(temp_path)).with_duration(duration)
                clips.append(clip)
            
            # Concatenate clips
            final_clip = concatenate_videoclips(clips, method="compose")
            
            # Generate output filename
            if not output_filename:
                output_filename = f"story_{uuid.uuid4().hex[:8]}.mp4"
            
            output_path = self.generated_dir / output_filename
            
            # Write video with audio codec set (even though no audio)
            final_clip.write_videofile(
                str(output_path),
                fps=24,
                codec='libx264',
                audio=False,
                preset='ultrafast',
                threads=4
            )
            
            final_clip.close()
            
            return str(output_path)
        
        finally:
            # Cleanup temp files
            for temp_file in temp_files:
                try:
                    temp_file.unlink()
                except (IOError, OSError):
                    pass
    
    def generate_video_with_progress(self, presentation_data: Dict, output_filename: Optional[str] = None, progress_callback: Optional[callable] = None) -> Tuple[str, Dict]:
        """
        Generate an MP4 video from presentation data with detailed progress tracking.
        Returns tuple of (output_path, stats_dict).
        
        Args:
            presentation_data: Dict with location, hostFile, roundFiles
            output_filename: Optional custom filename for output
            progress_callback: Optional callback(step_num, step_name) for progress updates
        
        Progress Steps:
        - Step 2: Fetch location image
        - Step 3: Fetch host image
        - Step 4: Fetch background image
        - Step 5: Generate frames with overlays
        - Step 6: Encode video
        """
        import time
        stats = {}
        
        def report_progress(step_num: int, step_name: str):
            """Report progress to callback if provided"""
            if progress_callback:
                try:
                    progress_callback(step_num, step_name)
                except Exception as e:
                    logger.warning(f"Progress callback error: {e}")
        
        # Check ffmpeg is available
        try:
            result = subprocess.run(['ffmpeg', '-version'], capture_output=True, timeout=5)
            if result.returncode != 0:
                raise RuntimeError("FFmpeg not available")
            logger.info("[INIT] FFmpeg available for fast encoding")
        except Exception as e:
            logger.error(f"[INIT] FFmpeg check failed: {e}")
            raise RuntimeError("FFmpeg is required for video generation. Install with: apt-get install ffmpeg")
        
        location_name = self._normalize_location_name(presentation_data.get('location', ''))
        host_name = self._normalize_host_name(presentation_data.get('hostFile', ''))
        rounds_info = presentation_data.get('roundFiles', [])
        num_rounds = len(rounds_info)
        
        logger.info("[STEP 2] Starting asset fetch pipeline")
        logger.info(f"[STEP 2] Normalized location: '{location_name}'")
        logger.info(f"[STEP 2] Normalized host: '{host_name}'")
        logger.info(f"[STEP 2] Number of rounds: {num_rounds}")
        
        frames = []
        durations = []
        
        # STEP 2: Fetch location image
        report_progress(2, 'Fetching location image')
        step_start = time.time()
        logger.info(f"[STEP 2/6] Fetching location image for: {location_name}")
        
        try:
            location_img = self._get_location_image(location_name)
            if location_img:
                location_img = location_img.convert('RGB')
                location_img = self._resize_to_story(location_img)
                logger.info(f"[STEP 2/6] SUCCESS - Location image loaded ({location_img.size})")
                stats['locationImage'] = 'loaded'
            else:
                logger.warning("[STEP 2/6] WARNING - No location image found, using placeholder")
                location_img = self._create_placeholder_image(
                    STORY_WIDTH, STORY_HEIGHT, 
                    f"Location:\n{location_name.replace('_', ' ').title()}",
                    '#1a1a2e'
                )
                location_img = self._resize_to_story(location_img)
                stats['locationImage'] = 'placeholder'
        except Exception as e:
            logger.error(f"[STEP 2/6] ERROR fetching location image: {str(e)}")
            import traceback
            logger.error(f"[STEP 2/6] Traceback:\n{traceback.format_exc()}")
            # Use placeholder instead of failing
            location_img = self._create_placeholder_image(
                STORY_WIDTH, STORY_HEIGHT, 
                f"Location:\n{location_name.replace('_', ' ').title()}",
                '#1a1a2e'
            )
            location_img = self._resize_to_story(location_img)
            stats['locationImage'] = 'error_placeholder'
        
        frames.append(location_img)
        durations.append(5.0)
        stats['step2Time'] = round(time.time() - step_start, 2)
        logger.info(f"[STEP 2/6] Completed in {stats['step2Time']}s")
        
        # STEP 3: Fetch host image
        report_progress(3, 'Fetching host image')
        step_start = time.time()
        logger.info(f"[STEP 3/6] Fetching host image for: {host_name}")
        
        try:
            host_img, is_animated = self._get_host_image(host_name)
            if host_img:
                host_img = host_img.convert('RGB')
                host_img = self._resize_to_story(host_img)
                logger.info(f"[STEP 3/6] SUCCESS - Host image loaded ({host_img.size})")
                stats['hostImage'] = 'loaded'
            else:
                logger.warning("[STEP 3/6] WARNING - No host image found, using placeholder")
                host_img = self._create_placeholder_image(
                    STORY_WIDTH, STORY_HEIGHT,
                    f"Host:\n{host_name.replace('_', ' ').title()}",
                    '#16213e'
                )
                stats['hostImage'] = 'placeholder'
        except Exception as e:
            logger.error(f"[STEP 3/6] ERROR fetching host image: {str(e)}")
            import traceback
            logger.error(f"[STEP 3/6] Traceback:\n{traceback.format_exc()}")
            host_img = self._create_placeholder_image(
                STORY_WIDTH, STORY_HEIGHT,
                f"Host:\n{host_name.replace('_', ' ').title()}",
                '#16213e'
            )
            stats['hostImage'] = 'error_placeholder'
        
        frames.append(host_img)
        durations.append(5.0)
        stats['step3Time'] = round(time.time() - step_start, 2)
        logger.info(f"[STEP 3/6] Completed in {stats['step3Time']}s")
        
        # STEP 4: Fetch background image
        report_progress(4, 'Fetching background image')
        step_start = time.time()
        logger.info(f"[STEP 4/6] Fetching background image for: {location_name} ({num_rounds} rounds)")
        
        try:
            bg_img = self._get_background_image(location_name, num_rounds=num_rounds)
            if bg_img:
                bg_img = bg_img.convert('RGBA')
                bg_img = self._resize_to_story(bg_img.convert('RGB')).convert('RGBA')
                logger.info(f"[STEP 4/6] SUCCESS - Background image loaded ({bg_img.size})")
                stats['backgroundImage'] = 'loaded'
            else:
                logger.warning("[STEP 4/6] WARNING - No background image found, using default")
                bg_img = Image.new('RGBA', (STORY_WIDTH, STORY_HEIGHT), (26, 26, 46, 255))
                stats['backgroundImage'] = 'default'
        except Exception as e:
            logger.error(f"[STEP 4/6] ERROR fetching background image: {str(e)}")
            import traceback
            logger.error(f"[STEP 4/6] Traceback:\n{traceback.format_exc()}")
            bg_img = Image.new('RGBA', (STORY_WIDTH, STORY_HEIGHT), (26, 26, 46, 255))
            stats['backgroundImage'] = 'error_default'
        
        stats['step4Time'] = round(time.time() - step_start, 2)
        logger.info(f"[STEP 4/6] Completed in {stats['step4Time']}s")
        
        # STEP 5: Generate frames with overlays
        report_progress(5, 'Creating text overlays')
        step_start = time.time()
        logger.info("[STEP 5/6] Generating overlay frames with round names")
        
        try:
            # Resolve round names from presentation data
            resolved_rounds = []
            round_names_list = presentation_data.get('roundNames', [])
            
            for i, rf in enumerate(rounds_info):
                round_type = rf.get('type', 'REG')
                
                if round_type == 'MC':
                    round_name = 'Multiple Choice'
                elif round_type == 'MYS':
                    round_name = 'Mystery'
                else:
                    raw_name = round_names_list[i] if i < len(round_names_list) else rf.get('name', '')
                    if raw_name:
                        import re as name_re
                        clean = raw_name.replace('.pptx', '')
                        clean = name_re.sub(r'^BIG_', '', clean, flags=name_re.IGNORECASE)
                        clean = name_re.sub(r'_\d+$', '', clean)
                        clean = clean.replace('_', ' ')
                        round_name = clean.strip()
                    else:
                        round_name = f'{round_type} Round'
                
                resolved_rounds.append({
                    'order': rf.get('order', 0),
                    'type': round_type,
                    'name': round_name
                })
                logger.info(f"[STEP 5/6] Round {i+1}: {round_type} -> '{round_name}'")
            
            stats['resolvedRounds'] = [r['name'] for r in resolved_rounds]
            
            # Create overlay
            logger.info("[STEP 5/6] Creating text overlay with bundled Lemonada font")
            rounds_overlay = self._create_rounds_overlay(resolved_rounds, location_name, num_rounds=num_rounds)
            
            # Composite
            final_bg = Image.alpha_composite(bg_img, rounds_overlay)
            frames.append(final_bg.convert('RGB'))
            durations.append(15.0)
            
            logger.info("[STEP 5/6] SUCCESS - Overlay created and composited")
            stats['overlay'] = 'created'
        except Exception as e:
            logger.error(f"[STEP 5/6] ERROR creating overlay: {str(e)}")
            import traceback
            logger.error(f"[STEP 5/6] Traceback:\n{traceback.format_exc()}")
            # Add plain background without overlay
            frames.append(bg_img.convert('RGB'))
            durations.append(15.0)
            stats['overlay'] = 'error_skipped'
        
        stats['step5Time'] = round(time.time() - step_start, 2)
        logger.info(f"[STEP 5/6] Completed in {stats['step5Time']}s")
        
        # STEP 6: Fast video encoding using FFmpeg
        report_progress(6, 'Encoding video (fast mode)')
        step_start = time.time()
        
        # Updated durations: 3s location, 3s host, 14s background = 20s total
        fast_durations = [3.0, 3.0, 14.0]
        total_duration = sum(fast_durations)
        logger.info(f"[STEP 6/6] Fast encoding with FFmpeg (frames: {len(frames)}, duration: {total_duration}s)")
        
        temp_files = []
        segment_files = []
        
        try:
            # Save frames as temp PNG files
            for i, frame in enumerate(frames):
                temp_path = self.generated_dir / f"temp_frame_{uuid.uuid4().hex[:8]}_{i}.png"
                frame.save(temp_path, 'PNG')
                temp_files.append(temp_path)
                logger.info(f"[STEP 6/6] Saved frame {i+1}: {temp_path.name}")
            
            # Create individual video segments using FFmpeg in PARALLEL (3x faster)
            from concurrent.futures import ThreadPoolExecutor, as_completed
            
            def encode_segment(args):
                """Encode a single segment - runs in thread pool"""
                idx, temp_path, duration, segment_path = args
                ffmpeg_cmd = [
                    'ffmpeg', '-y',
                    '-loop', '1',
                    '-i', str(temp_path),
                    '-t', str(duration),
                    '-r', '1',  # 1fps — still images don't need more
                    '-c:v', 'libx264',
                    '-preset', 'ultrafast',
                    '-tune', 'stillimage',
                    '-crf', '35',  # Lower quality = much faster
                    '-threads', '1',
                    '-pix_fmt', 'yuv420p',
                    '-vf', 'scale=540:960',  # 540x960 — small enough for fast encode
                    '-movflags', '+faststart',
                    str(segment_path)
                ]
                
                result = subprocess.run(
                    ffmpeg_cmd, 
                    capture_output=True, 
                    text=True,
                    timeout=180
                )
                
                if result.returncode != 0:
                    raise RuntimeError(f"FFmpeg failed for segment {idx+1}: {result.stderr[:200]}")
                
                return idx, segment_path
            
            # Prepare segment tasks
            segment_tasks = []
            for i, (temp_path, duration) in enumerate(zip(temp_files, fast_durations)):
                segment_path = self.generated_dir / f"segment_{uuid.uuid4().hex[:8]}_{i}.mp4"
                segment_files.append(segment_path)
                segment_tasks.append((i, temp_path, duration, segment_path))
            
            # Run segment encodings sequentially to avoid overwhelming production container
            logger.info(f"[STEP 6/6] Encoding {len(segment_tasks)} segments (720x1280, 15fps)...")
            with ThreadPoolExecutor(max_workers=1) as executor:
                futures = {executor.submit(encode_segment, task): task for task in segment_tasks}
                for future in as_completed(futures):
                    idx, seg_path = future.result()
                    logger.info(f"[STEP 6/6] Segment {idx+1} complete: {seg_path.name}")
            
            # Generate output filename
            if not output_filename:
                output_filename = f"story_{uuid.uuid4().hex[:8]}.mp4"
            
            output_path = self.generated_dir / output_filename
            
            # Create concat file for FFmpeg
            concat_file = self.generated_dir / f"concat_{uuid.uuid4().hex[:8]}.txt"
            with open(concat_file, 'w') as f:
                for seg in segment_files:
                    f.write(f"file '{seg}'\n")
            temp_files.append(concat_file)
            
            # Concatenate segments without re-encoding (super fast)
            logger.info(f"[STEP 6/6] Concatenating {len(segment_files)} segments...")
            concat_cmd = [
                'ffmpeg', '-y',
                '-f', 'concat',
                '-safe', '0',
                '-i', str(concat_file),
                '-c', 'copy',  # No re-encoding = instant concat
                str(output_path)
            ]
            
            result = subprocess.run(
                concat_cmd,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode != 0:
                logger.error(f"[STEP 6/6] FFmpeg concat error: {result.stderr}")
                raise RuntimeError(f"FFmpeg concat failed: {result.stderr[:200]}")
            
            # Verify output
            if output_path.exists():
                file_size = output_path.stat().st_size
                logger.info(f"[STEP 6/6] SUCCESS - Video created: {output_path.name} ({file_size / 1024 / 1024:.2f} MB)")
                stats['videoSize'] = f"{file_size / 1024 / 1024:.2f} MB"
                stats['encoding'] = 'ffmpeg_fast'
                stats['videoDuration'] = f"{total_duration}s"
            else:
                logger.error("[STEP 6/6] ERROR - Output file not found!")
                stats['encoding'] = 'file_missing'
                raise RuntimeError("Video file was not created")
            
            stats['step6Time'] = round(time.time() - step_start, 2)
            logger.info(f"[STEP 6/6] Completed in {stats['step6Time']}s (FFmpeg fast mode)")
            
            return str(output_path), stats
        
        except Exception as e:
            logger.error(f"[STEP 6/6] ERROR encoding video: {str(e)}")
            import traceback
            logger.error(f"[STEP 6/6] Traceback:\n{traceback.format_exc()}")
            stats['encoding'] = f'error: {str(e)}'
            raise
        
        finally:
            # Cleanup temp files and segment files
            all_temp_files = temp_files + segment_files
            for temp_file in all_temp_files:
                try:
                    if temp_file.exists():
                        temp_file.unlink()
                        logger.info(f"[CLEANUP] Deleted: {temp_file.name}")
                except (IOError, OSError) as e:
                    logger.warning(f"[CLEANUP] Failed to delete {temp_file}: {e}")
    
    def upload_asset(self, file_content: bytes, filename: str, asset_type: str) -> Dict:
        """
        Upload an asset (location image, host gif, or background).
        
        Args:
            file_content: Raw file bytes
            filename: Original filename
            asset_type: 'location', 'host', or 'background'
        """
        # Determine target directory
        if asset_type == 'location':
            target_dir = self.locations_dir
        elif asset_type == 'host':
            target_dir = self.hosts_dir
        elif asset_type == 'background':
            target_dir = self.backgrounds_dir
        else:
            raise ValueError(f"Invalid asset type: {asset_type}")
        
        # Clean filename
        safe_filename = filename.replace(' ', '_').lower()
        target_path = target_dir / safe_filename
        
        # Write file
        with open(target_path, 'wb') as f:
            f.write(file_content)
        
        return {
            'id': target_path.stem,
            'name': target_path.stem.replace('_', ' ').title(),
            'path': str(target_path),
            'type': 'image'
        }
    
    def delete_asset(self, asset_id: str, asset_type: str) -> bool:
        """
        Delete an asset.
        
        Args:
            asset_id: Asset ID (filename without extension)
            asset_type: 'location', 'host', or 'background'
        """
        if asset_type == 'location':
            target_dir = self.locations_dir
        elif asset_type == 'host':
            target_dir = self.hosts_dir
        elif asset_type == 'background':
            target_dir = self.backgrounds_dir
        else:
            raise ValueError(f"Invalid asset type: {asset_type}")
        
        # Find and delete file
        for f in target_dir.iterdir():
            if f.stem.lower() == asset_id.lower():
                f.unlink()
                return True
        
        return False


# Singleton instance
_story_service = None

def get_story_service() -> StoryGeneratorService:
    global _story_service
    if _story_service is None:
        _story_service = StoryGeneratorService()
    return _story_service
