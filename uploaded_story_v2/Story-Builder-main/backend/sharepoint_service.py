import msal
import requests
import os
from typing import Optional, List, Dict
import logging

logger = logging.getLogger(__name__)

# Timeout configuration for SharePoint API requests
# (connection_timeout, read_timeout) in seconds
# Connection timeout: time to establish connection
# Read timeout: time to wait for data after connection is established
SHAREPOINT_TIMEOUT = (30, 120)  # 30s connect, 120s read

class SharePointService:
    def __init__(self):
        # Require environment variables - no hardcoded fallbacks for security
        self.tenant_id = os.environ['AZURE_TENANT_ID']
        self.client_id = os.environ['AZURE_CLIENT_ID']
        self.client_secret = os.environ['AZURE_CLIENT_SECRET']
        self.site_url = 'https://bhentertainment.sharepoint.com'
        self.site_name = 'bhentertainment.sharepoint.com'
        # The base folder path in SharePoint
        self.base_folder = '01_Trivia/Web App/00_Builder'
        self.access_token = None
        self._site_id_cache = None
        self._drive_id_cache = None
    
    def get_access_token(self) -> str:
        """Get access token for Microsoft Graph API"""
        if self.access_token:
            return self.access_token
            
        authority = f"https://login.microsoftonline.com/{self.tenant_id}"
        scope = ['https://graph.microsoft.com/.default']
        
        app = msal.ConfidentialClientApplication(
            self.client_id,
            authority=authority,
            client_credential=self.client_secret
        )
        
        result = app.acquire_token_for_client(scopes=scope)
        
        if 'access_token' in result:
            self.access_token = result['access_token']
            return self.access_token
        else:
            logger.error(f"Failed to get access token: {result.get('error_description')}")
            raise Exception(f"Failed to authenticate: {result.get('error_description')}")
    
    def get_site_id(self) -> str:
        """Get SharePoint site ID"""
        if self._site_id_cache:
            return self._site_id_cache
            
        token = self.get_access_token()
        headers = {'Authorization': f'Bearer {token}'}
        
        # Try to get the root site first
        url = f'https://graph.microsoft.com/v1.0/sites/bhentertainment.sharepoint.com'
        response = requests.get(url, headers=headers, timeout=SHAREPOINT_TIMEOUT)
        
        if response.status_code == 200:
            self._site_id_cache = response.json()['id']
            return self._site_id_cache
        else:
            logger.error(f"Failed to get site ID: {response.text}")
            raise Exception(f"Failed to get site ID: {response.text}")
    
    def get_drive_id(self, site_id: str) -> str:
        """Get drive ID for the site"""
        if self._drive_id_cache:
            return self._drive_id_cache
            
        token = self.get_access_token()
        headers = {'Authorization': f'Bearer {token}'}
        
        url = f'https://graph.microsoft.com/v1.0/sites/{site_id}/drives'
        response = requests.get(url, headers=headers, timeout=SHAREPOINT_TIMEOUT)
        
        if response.status_code == 200:
            drives = response.json()['value']
            # Look for "Documents" drive (not IntranetDocuments)
            for drive in drives:
                drive_name = drive.get('name', '')
                if drive_name == 'Documents':
                    self._drive_id_cache = drive['id']
                    logger.info(f"Using drive: {drive_name} ({drive['id']})")
                    return drive['id']
            # Fallback: look for Shared Documents or any Documents
            for drive in drives:
                if 'Documents' in drive.get('name', ''):
                    self._drive_id_cache = drive['id']
                    return drive['id']
            # Final fallback to first drive
            if drives:
                self._drive_id_cache = drives[0]['id']
                return drives[0]['id']
        
        logger.error(f"Failed to get drive ID: {response.text}")
        raise Exception(f"Failed to get drive ID: {response.text}")
    
    def list_folder_contents(self, folder_path: str) -> List[Dict]:
        """List contents of a folder"""
        token = self.get_access_token()
        headers = {'Authorization': f'Bearer {token}'}
        
        site_id = self.get_site_id()
        drive_id = self.get_drive_id(site_id)
        
        # Encode the path
        encoded_path = requests.utils.quote(folder_path)
        url = f'https://graph.microsoft.com/v1.0/sites/{site_id}/drives/{drive_id}/root:/{encoded_path}:/children'
        
        response = requests.get(url, headers=headers, timeout=SHAREPOINT_TIMEOUT)
        
        if response.status_code == 200:
            return response.json().get('value', [])
        else:
            logger.error(f"Failed to list folder: {response.text}")
            return []
    
    def download_file(self, file_path: str, local_path: str) -> bool:
        """Download a file from SharePoint"""
        try:
            token = self.get_access_token()
            headers = {'Authorization': f'Bearer {token}'}
            
            site_id = self.get_site_id()
            drive_id = self.get_drive_id(site_id)
            
            encoded_path = requests.utils.quote(file_path)
            url = f'https://graph.microsoft.com/v1.0/sites/{site_id}/drives/{drive_id}/root:/{encoded_path}:/content'
            
            response = requests.get(url, headers=headers, stream=True, timeout=SHAREPOINT_TIMEOUT)
            
            if response.status_code == 200:
                os.makedirs(os.path.dirname(local_path), exist_ok=True)
                with open(local_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                return True
            else:
                logger.error(f"Failed to download file {file_path}: {response.text}")
                return False
        except Exception as e:
            logger.error(f"Error downloading file {file_path}: {str(e)}")
            return False

    def download_file_to_bytes(self, file_path: str) -> bytes:
        """Download a file from SharePoint and return as bytes"""
        try:
            token = self.get_access_token()
            headers = {'Authorization': f'Bearer {token}'}
            
            site_id = self.get_site_id()
            drive_id = self.get_drive_id(site_id)
            
            encoded_path = requests.utils.quote(file_path)
            url = f'https://graph.microsoft.com/v1.0/sites/{site_id}/drives/{drive_id}/root:/{encoded_path}:/content'
            
            response = requests.get(url, headers=headers, timeout=SHAREPOINT_TIMEOUT)
            
            if response.status_code == 200:
                return response.content
            else:
                logger.error(f"Failed to download file {file_path}: {response.text}")
                return None
        except Exception as e:
            logger.error(f"Error downloading file {file_path}: {str(e)}")
            return None

    def get_file_url(self, file_path: str) -> str:
        """Get direct SharePoint URL for a file"""
        try:
            token = self.get_access_token()
            headers = {'Authorization': f'Bearer {token}'}
            
            site_id = self.get_site_id()
            drive_id = self.get_drive_id(site_id)
            
            encoded_path = requests.utils.quote(file_path)
            url = f'https://graph.microsoft.com/v1.0/sites/{site_id}/drives/{drive_id}/root:/{encoded_path}'
            
            response = requests.get(url, headers=headers, timeout=SHAREPOINT_TIMEOUT)
            
            if response.status_code == 200:
                file_info = response.json()
                # Return the web URL for direct access
                web_url = file_info.get('webUrl', '')
                if web_url:
                    return web_url
                else:
                    # Fallback: construct direct download URL
                    return f'https://graph.microsoft.com/v1.0/sites/{site_id}/drives/{drive_id}/root:/{encoded_path}:/content'
            else:
                logger.error(f"Failed to get file URL for {file_path}: {response.text}")
                return ""
        except Exception as e:
            logger.error(f"Error getting file URL for {file_path}: {str(e)}")
            return ""

    
    def upload_file(self, local_path: str, sharepoint_path: str) -> bool:
        """Upload a file to SharePoint"""
        try:
            token = self.get_access_token()
            headers = {
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/octet-stream'
            }
            
            site_id = self.get_site_id()
            drive_id = self.get_drive_id(site_id)
            
            encoded_path = requests.utils.quote(sharepoint_path)
            url = f'https://graph.microsoft.com/v1.0/sites/{site_id}/drives/{drive_id}/root:/{encoded_path}:/content'
            
            with open(local_path, 'rb') as f:
                response = requests.put(url, headers=headers, data=f, timeout=SHAREPOINT_TIMEOUT)
            
            if response.status_code in [200, 201]:
                return True
            else:
                logger.error(f"Failed to upload file to {sharepoint_path}: {response.text}")
                return False
        except Exception as e:
            logger.error(f"Error uploading file to {sharepoint_path}: {str(e)}")
            return False

    def encode_sharing_url(self, sharing_url: str) -> str:
        """
        Encode a SharePoint sharing URL for use with the Microsoft Graph Shares API.
        Uses URL-safe base64 encoding with 'u!' prefix.
        """
        import base64
        # Encode the URL to bytes, then base64
        encoded = base64.urlsafe_b64encode(sharing_url.encode('utf-8')).decode('utf-8')
        # Remove padding and add 'u!' prefix
        encoded = encoded.rstrip('=')
        return f"u!{encoded}"

    def list_folder_contents_by_sharing_url(self, sharing_url: str) -> List[Dict]:
        """
        List contents of a folder using a SharePoint sharing URL.
        This is used for the new round folder structure.
        """
        try:
            token = self.get_access_token()
            headers = {'Authorization': f'Bearer {token}'}
            
            # Encode the sharing URL
            encoded_url = self.encode_sharing_url(sharing_url)
            
            # Get the driveItem from the sharing URL
            url = f'https://graph.microsoft.com/v1.0/shares/{encoded_url}/driveItem/children'
            
            response = requests.get(url, headers=headers, timeout=SHAREPOINT_TIMEOUT)
            
            if response.status_code == 200:
                return response.json().get('value', [])
            else:
                logger.error(f"Failed to list folder from sharing URL: {response.text}")
                return []
        except Exception as e:
            logger.error(f"Error listing folder from sharing URL: {str(e)}")
            return []

    def get_driveitem_info_from_sharing_url(self, sharing_url: str) -> Dict:
        """
        Get driveItem info (driveId, itemId, path) from a SharePoint sharing URL.
        """
        try:
            token = self.get_access_token()
            headers = {'Authorization': f'Bearer {token}'}
            
            encoded_url = self.encode_sharing_url(sharing_url)
            url = f'https://graph.microsoft.com/v1.0/shares/{encoded_url}/driveItem'
            
            response = requests.get(url, headers=headers, timeout=SHAREPOINT_TIMEOUT)
            
            if response.status_code == 200:
                data = response.json()
                return {
                    'id': data.get('id'),
                    'name': data.get('name'),
                    'driveId': data.get('parentReference', {}).get('driveId'),
                    'path': data.get('parentReference', {}).get('path', ''),
                    'webUrl': data.get('webUrl')
                }
            else:
                logger.error(f"Failed to get driveItem info: {response.text}")
                return {}
        except Exception as e:
            logger.error(f"Error getting driveItem info: {str(e)}")
            return {}

    def download_file_from_sharing_folder(self, sharing_url: str, filename: str) -> bytes:
        """
        Download a file from a folder accessed via sharing URL.
        """
        try:
            token = self.get_access_token()
            headers = {'Authorization': f'Bearer {token}'}
            
            # First get the folder's driveId and itemId
            encoded_url = self.encode_sharing_url(sharing_url)
            folder_url = f'https://graph.microsoft.com/v1.0/shares/{encoded_url}/driveItem'
            
            folder_response = requests.get(folder_url, headers=headers, timeout=SHAREPOINT_TIMEOUT)
            if folder_response.status_code != 200:
                logger.error(f"Failed to get folder info: {folder_response.text}")
                return None
            
            folder_data = folder_response.json()
            drive_id = folder_data.get('parentReference', {}).get('driveId')
            folder_id = folder_data.get('id')
            
            if not drive_id or not folder_id:
                logger.error("Could not get drive_id or folder_id from sharing URL")
                return None
            
            # List children to find the file
            children_url = f'https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{folder_id}/children'
            children_response = requests.get(children_url, headers=headers, timeout=SHAREPOINT_TIMEOUT)
            
            if children_response.status_code != 200:
                logger.error(f"Failed to list folder children: {children_response.text}")
                return None
            
            children = children_response.json().get('value', [])
            target_file = None
            for child in children:
                if child.get('name') == filename:
                    target_file = child
                    break
            
            if not target_file:
                logger.error(f"File {filename} not found in folder")
                return None
            
            # Download the file
            file_id = target_file.get('id')
            download_url = f'https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{file_id}/content'
            
            download_response = requests.get(download_url, headers=headers, timeout=SHAREPOINT_TIMEOUT)
            
            if download_response.status_code == 200:
                return download_response.content
            else:
                logger.error(f"Failed to download file: {download_response.text}")
                return None
                
        except Exception as e:
            logger.error(f"Error downloading file from sharing folder: {str(e)}")
            return None

    def download_file_by_item_id(self, drive_id: str, item_id: str, local_path: str) -> bool:
        """
        Download a file using driveId and itemId (for new sharepoint:// path format).
        """
        try:
            token = self.get_access_token()
            headers = {'Authorization': f'Bearer {token}'}
            
            url = f'https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}/content'
            
            response = requests.get(url, headers=headers, stream=True, timeout=SHAREPOINT_TIMEOUT)
            
            if response.status_code == 200:
                os.makedirs(os.path.dirname(local_path), exist_ok=True)
                with open(local_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                return True
            else:
                logger.error(f"Failed to download file by item ID {item_id}: {response.text}")
                return False
        except Exception as e:
            logger.error(f"Error downloading file by item ID {item_id}: {str(e)}")
            return False

    def download_file_to_bytes_by_item_id(self, drive_id: str, item_id: str) -> bytes:
        """
        Download a file to bytes using driveId and itemId.
        """
        try:
            token = self.get_access_token()
            headers = {'Authorization': f'Bearer {token}'}
            
            url = f'https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}/content'
            
            response = requests.get(url, headers=headers, timeout=SHAREPOINT_TIMEOUT)
            
            if response.status_code == 200:
                return response.content
            else:
                logger.error(f"Failed to download file by item ID {item_id}: {response.text}")
                return None
        except Exception as e:
            logger.error(f"Error downloading file by item ID {item_id}: {str(e)}")
            return None

    def download_file_by_sharing_url(self, sharing_url: str, local_path: str) -> bool:
        """
        Download a file directly from a SharePoint sharing URL.
        Works for single file sharing links (e.g., /:p:/g/ for PowerPoint files).
        """
        try:
            token = self.get_access_token()
            headers = {'Authorization': f'Bearer {token}'}
            
            # Get the driveItem info from the sharing URL
            encoded_url = self.encode_sharing_url(sharing_url)
            driveitem_url = f'https://graph.microsoft.com/v1.0/shares/{encoded_url}/driveItem'
            
            driveitem_response = requests.get(driveitem_url, headers=headers, timeout=SHAREPOINT_TIMEOUT)
            
            if driveitem_response.status_code != 200:
                logger.error(f"Failed to get driveItem info from sharing URL: {driveitem_response.text}")
                return False
            
            driveitem_data = driveitem_response.json()
            drive_id = driveitem_data.get('parentReference', {}).get('driveId')
            item_id = driveitem_data.get('id')
            file_name = driveitem_data.get('name', 'unknown')
            
            if not drive_id or not item_id:
                logger.error("Could not get drive_id or item_id from sharing URL driveItem")
                return False
            
            logger.info(f"Downloading '{file_name}' via sharing URL (driveId={drive_id[:8]}..., itemId={item_id[:8]}...)")
            
            # Download the file content
            download_url = f'https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}/content'
            
            download_response = requests.get(download_url, headers=headers, stream=True, timeout=SHAREPOINT_TIMEOUT)
            
            if download_response.status_code == 200:
                os.makedirs(os.path.dirname(local_path) if os.path.dirname(local_path) else '.', exist_ok=True)
                with open(local_path, 'wb') as f:
                    for chunk in download_response.iter_content(chunk_size=8192):
                        f.write(chunk)
                logger.info(f"✓ Downloaded '{file_name}' to {local_path}")
                return True
            else:
                logger.error(f"Failed to download file content: {download_response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Error downloading file from sharing URL: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    def get_item_children(self, drive_id: str, item_id: str) -> List[Dict]:
        """
        Get children of a driveItem (for folder navigation).
        """
        try:
            token = self.get_access_token()
            headers = {'Authorization': f'Bearer {token}'}
            
            url = f'https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}/children'
            
            response = requests.get(url, headers=headers, timeout=SHAREPOINT_TIMEOUT)
            
            if response.status_code == 200:
                return response.json().get('value', [])
            else:
                logger.error(f"Failed to get item children: {response.text}")
                return []
        except Exception as e:
            logger.error(f"Error getting item children: {str(e)}")
            return []

    def parse_sharepoint_path(self, path: str) -> tuple:
        """
        Parse a sharepoint:// path into (drive_id, item_id).
        Returns (None, None) if not a sharepoint:// path.
        """
        if path.startswith('sharepoint://'):
            parts = path.replace('sharepoint://', '').split('/')
            if len(parts) >= 2:
                return parts[0], parts[1]
        return None, None

