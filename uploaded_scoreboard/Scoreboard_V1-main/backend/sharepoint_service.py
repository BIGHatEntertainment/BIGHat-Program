"""
SharePoint integration via Microsoft Graph API
Client credentials flow for daemon/service authentication
"""
import os
import json
import base64
import logging
import time
import httpx
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)

GRAPH_API = "https://graph.microsoft.com/v1.0"


class TokenCache:
    """Simple in-memory token cache with expiry"""
    def __init__(self):
        self._token = None
        self._expires_at = 0

    def get(self):
        if self._token and time.time() < self._expires_at - 60:
            return self._token
        return None

    def set(self, token: str, expires_in: int):
        self._token = token
        self._expires_at = time.time() + expires_in


_token_cache = TokenCache()


async def get_access_token() -> str:
    """Acquire OAuth2 token using client credentials flow"""
    cached = _token_cache.get()
    if cached:
        return cached

    tenant_id = os.environ.get("AZURE_TENANT_ID")
    client_id = os.environ.get("AZURE_CLIENT_ID")
    client_secret = os.environ.get("AZURE_CLIENT_SECRET")

    if not all([tenant_id, client_id, client_secret]):
        raise ValueError("Azure credentials not configured. Set AZURE_CLIENT_ID, AZURE_TENANT_ID, AZURE_CLIENT_SECRET in .env")

    token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": "https://graph.microsoft.com/.default",
        "grant_type": "client_credentials"
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(token_url, data=data, timeout=30)
        if resp.status_code != 200:
            logger.error(f"Token acquisition failed: {resp.status_code} - {resp.text}")
            raise Exception(f"Failed to acquire token: {resp.text}")
        token_data = resp.json()
        token = token_data["access_token"]
        _token_cache.set(token, token_data.get("expires_in", 3600))
        logger.info("Access token acquired successfully")
        return token


def encode_sharing_url(sharing_url: str) -> str:
    """Encode a sharing URL to the format Microsoft Graph expects"""
    encoded = base64.b64encode(sharing_url.encode()).decode()
    encoded = encoded.rstrip('=').replace('+', '-').replace('/', '_')
    return f"u!{encoded}"


async def resolve_sharing_link(sharing_url: str) -> Dict[str, Any]:
    """Resolve a SharePoint sharing link to drive item info"""
    token = await get_access_token()
    sharing_token = encode_sharing_url(sharing_url)
    headers = {"Authorization": f"Bearer {token}"}

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GRAPH_API}/shares/{sharing_token}/driveItem",
            headers=headers,
            timeout=30
        )
        if resp.status_code != 200:
            logger.error(f"Failed to resolve sharing link: {resp.status_code} - {resp.text}")
            raise Exception(f"Failed to resolve sharing link: {resp.text}")
        return resp.json()


async def list_folder_children(drive_id: str, item_id: str) -> List[Dict[str, Any]]:
    """List all children in a folder"""
    token = await get_access_token()
    headers = {"Authorization": f"Bearer {token}"}

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GRAPH_API}/drives/{drive_id}/items/{item_id}/children",
            headers=headers,
            timeout=30
        )
        if resp.status_code != 200:
            logger.error(f"Failed to list children: {resp.status_code} - {resp.text}")
            raise Exception(f"Failed to list folder children: {resp.text}")
        return resp.json().get('value', [])


async def download_file_content(drive_id: str, item_id: str) -> bytes:
    """Download file content from SharePoint"""
    token = await get_access_token()
    headers = {"Authorization": f"Bearer {token}"}

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GRAPH_API}/drives/{drive_id}/items/{item_id}/content",
            headers=headers,
            timeout=30,
            follow_redirects=True
        )
        if resp.status_code != 200:
            logger.error(f"Failed to download file: {resp.status_code}")
            raise Exception(f"Failed to download file")
        return resp.content


async def get_all_score_files(sharing_url: str) -> List[Dict[str, Any]]:
    """
    Get all score JSON files from the SharePoint shared folder.
    Explores subfolders recursively.
    Returns list of file metadata with parsed JSON content.
    """
    # Resolve the sharing link to get root folder
    root_item = await resolve_sharing_link(sharing_url)
    drive_id = root_item['parentReference']['driveId']
    root_id = root_item['id']

    all_files = []

    # List root children (venue folders)
    root_children = await list_folder_children(drive_id, root_id)

    for child in root_children:
        if 'folder' in child:
            # It's a venue subfolder, explore it
            venue_name = child.get('name', 'Unknown')
            try:
                subfolder_children = await list_folder_children(drive_id, child['id'])
                for file_item in subfolder_children:
                    if file_item.get('name', '').endswith('.json') and 'file' in file_item:
                        # Download and parse the JSON
                        try:
                            content = await download_file_content(drive_id, file_item['id'])
                            data = json.loads(content.decode('utf-8'))
                            all_files.append({
                                'file_name': file_item['name'],
                                'venue': venue_name,
                                'drive_id': drive_id,
                                'item_id': file_item['id'],
                                'size': file_item.get('size', 0),
                                'last_modified': file_item.get('lastModifiedDateTime', ''),
                                'data': data
                            })
                        except Exception as e:
                            logger.warning(f"Failed to parse {file_item['name']}: {e}")
            except Exception as e:
                logger.warning(f"Failed to explore folder {venue_name}: {e}")
        elif child.get('name', '').endswith('.json') and 'file' in child:
            # Direct JSON file in root
            try:
                content = await download_file_content(drive_id, child['id'])
                data = json.loads(content.decode('utf-8'))
                all_files.append({
                    'file_name': child['name'],
                    'venue': 'Root',
                    'drive_id': drive_id,
                    'item_id': child['id'],
                    'size': child.get('size', 0),
                    'last_modified': child.get('lastModifiedDateTime', ''),
                    'data': data
                })
            except Exception as e:
                logger.warning(f"Failed to parse {child['name']}: {e}")

    return all_files
