"""
SharePoint upload service using Microsoft Graph API.
Uses client credentials flow (OAuth2) to authenticate and upload files.
"""
import httpx
import base64
import os
import logging
from pathlib import Path
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# SharePoint folder sharing links mapped to round types
SHAREPOINT_SHARE_LINKS = {
    "MC": "https://bhentertainment.sharepoint.com/:f:/g/IgCbqWiBy2MFQ6_SQoGyQNCCAe8uXIVo0wV1gJyKRIFMQbs?e=vb87dq",
    "REG": "https://bhentertainment.sharepoint.com/:f:/g/IgAsoNFIx__sSKd8wqNszKMPAcvTA-6Te9vAmmiKFchoJfo?e=b3QzZ7",
    "MISC": "https://bhentertainment.sharepoint.com/:f:/g/IgA6mWLGMG5RS4mcZ85ijeloAQ0qySX3Ziy9iSX1NkK2fxU?e=Jw1QIs",
    "MYS": "https://bhentertainment.sharepoint.com/:f:/g/IgDxBtJL1z7LRK-1FG7ho1OZAYMs-ClM9qZWi0lyOTUxdt8?e=4omxAo",
    "BIG": "https://bhentertainment.sharepoint.com/:f:/g/IgAInn1huE6eRbwIeKCxwZE9AcTSRIEgDdsAwsc9W2h0ygo?e=W9fPHt",
}

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
TOKEN_URL_TEMPLATE = "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"


async def get_access_token() -> str:
    """Get an access token using client credentials flow."""
    tenant_id = os.environ.get("AZURE_TENANT_ID")
    client_id = os.environ.get("AZURE_CLIENT_ID")
    client_secret = os.environ.get("AZURE_CLIENT_SECRET")

    if not all([tenant_id, client_id, client_secret]):
        raise ValueError("Azure credentials not configured. Set AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET.")

    token_url = TOKEN_URL_TEMPLATE.format(tenant_id=tenant_id)
    data = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": "https://graph.microsoft.com/.default",
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(token_url, data=data)
        if resp.status_code != 200:
            error_detail = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else resp.text
            logger.error(f"Token request failed ({resp.status_code}): {error_detail}")
            raise Exception(f"Failed to get access token: {error_detail}")
        token_data = resp.json()
        return token_data["access_token"]


def _encode_sharing_url(sharing_url: str) -> str:
    """Encode a sharing URL for use with the /shares endpoint.
    
    Microsoft Graph uses a specific encoding: base64url of the URL, prefixed with 'u!'.
    https://learn.microsoft.com/en-us/graph/api/shares-get
    """
    # Remove any query params for cleaner encoding
    clean_url = sharing_url.split("?")[0]
    encoded = base64.urlsafe_b64encode(clean_url.encode("utf-8")).decode("utf-8")
    # Remove trailing padding '='
    encoded = encoded.rstrip("=")
    return f"u!{encoded}"


async def resolve_folder_from_share_link(access_token: str, sharing_url: str) -> dict:
    """Resolve a sharing link to get the drive ID and folder item ID."""
    encoded = _encode_sharing_url(sharing_url)
    url = f"{GRAPH_BASE}/shares/{encoded}/driveItem"
    headers = {"Authorization": f"Bearer {access_token}"}

    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers=headers)
        if resp.status_code != 200:
            error_detail = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else resp.text
            logger.error(f"Failed to resolve share link ({resp.status_code}): {error_detail}")
            raise Exception(f"Failed to resolve SharePoint folder: {error_detail}")
        
        item = resp.json()
        drive_id = item.get("parentReference", {}).get("driveId")
        item_id = item.get("id")
        folder_name = item.get("name", "Unknown")
        
        logger.info(f"Resolved folder '{folder_name}' -> driveId={drive_id}, itemId={item_id}")
        return {"drive_id": drive_id, "item_id": item_id, "folder_name": folder_name}


async def upload_file_to_sharepoint(
    access_token: str,
    drive_id: str,
    folder_item_id: str,
    filename: str,
    file_content: bytes,
) -> dict:
    """Upload a file to a specific SharePoint folder using Microsoft Graph.
    
    Uses the simple upload endpoint (< 4MB) or creates an upload session for larger files.
    For trivia PPTX files, they should be well under 4MB.
    """
    # Simple upload for files < 4MB
    upload_url = f"{GRAPH_BASE}/drives/{drive_id}/items/{folder_item_id}:/{filename}:/content"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.put(upload_url, headers=headers, content=file_content)
        if resp.status_code in (200, 201):
            result = resp.json()
            logger.info(f"Successfully uploaded '{filename}' to SharePoint (id={result.get('id')})")
            return {
                "status": "success",
                "file_id": result.get("id"),
                "filename": filename,
                "web_url": result.get("webUrl"),
                "size": result.get("size"),
                "uploaded_at": datetime.now(timezone.utc).isoformat(),
            }
        else:
            error_detail = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else resp.text
            logger.error(f"Upload failed ({resp.status_code}): {error_detail}")
            raise Exception(f"SharePoint upload failed: {error_detail}")


async def upload_round_to_sharepoint(round_type: str, filename: str, file_path: str) -> dict:
    """High-level function: upload a generated PPTX to the correct SharePoint folder by round type."""
    sharing_url = SHAREPOINT_SHARE_LINKS.get(round_type)
    if not sharing_url:
        raise ValueError(f"No SharePoint folder configured for round type: {round_type}")

    # Read the file
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"Generated file not found: {file_path}")
    
    file_content = file_path.read_bytes()
    
    # Get access token
    access_token = await get_access_token()
    
    # Resolve the sharing link to get folder location
    folder_info = await resolve_folder_from_share_link(access_token, sharing_url)
    
    # Upload the file
    result = await upload_file_to_sharepoint(
        access_token=access_token,
        drive_id=folder_info["drive_id"],
        folder_item_id=folder_info["item_id"],
        filename=filename,
        file_content=file_content,
    )
    
    result["folder"] = folder_info["folder_name"]
    result["round_type"] = round_type
    return result


# ── REG Title Images folder (separate from round output folders) ──

REG_TITLE_IMAGES_SHARE_LINK = "https://bhentertainment.sharepoint.com/:f:/g/IgBVBXOD3X6LT5nIGFf9kaJfAaxD0s8zTRFJz7_h-cnpOjg?e=QUI5rG"

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff"}


async def list_reg_title_images() -> list:
    """List all image files in the REG title images SharePoint folder.
    Returns a list of dicts: [{name, name_no_ext, item_id, drive_id, download_url}, ...]
    """
    access_token = await get_access_token()
    folder_info = await resolve_folder_from_share_link(access_token, REG_TITLE_IMAGES_SHARE_LINK)
    drive_id = folder_info["drive_id"]
    item_id = folder_info["item_id"]

    url = f"{GRAPH_BASE}/drives/{drive_id}/items/{item_id}/children?$select=id,name,file,@microsoft.graph.downloadUrl&$top=200"
    headers = {"Authorization": f"Bearer {access_token}"}

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url, headers=headers)
        if resp.status_code != 200:
            error_detail = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else resp.text
            logger.error(f"Failed to list folder children ({resp.status_code}): {error_detail}")
            raise Exception(f"Failed to list SharePoint folder: {error_detail}")

        data = resp.json()
        items = data.get("value", [])

    images = []
    for item in items:
        name = item.get("name", "")
        ext = Path(name).suffix.lower()
        if ext in IMAGE_EXTENSIONS:
            name_no_ext = Path(name).stem
            images.append({
                "name": name,
                "name_no_ext": name_no_ext,
                "item_id": item.get("id"),
                "drive_id": drive_id,
                "download_url": item.get("@microsoft.graph.downloadUrl", ""),
            })

    # Sort alphabetically by name
    images.sort(key=lambda x: x["name_no_ext"].lower())
    logger.info(f"Found {len(images)} title images in REG folder")
    return images


async def download_reg_title_image(item_id: str, drive_id: str, filename: str, save_dir: str) -> str:
    """Download a specific image from the REG title images folder to local disk."""
    access_token = await get_access_token()
    url = f"{GRAPH_BASE}/drives/{drive_id}/items/{item_id}/content"
    headers = {"Authorization": f"Bearer {access_token}"}

    save_path = Path(save_dir) / filename
    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
        resp = await client.get(url, headers=headers)
        if resp.status_code != 200:
            logger.error(f"Failed to download image ({resp.status_code})")
            raise Exception(f"Failed to download image from SharePoint")
        save_path.write_bytes(resp.content)

    logger.info(f"Downloaded title image '{filename}' -> {save_path}")
    return str(save_path)



async def list_sharepoint_folder_files(share_link: str) -> list:
    """List all files in a SharePoint folder by sharing link.
    Returns a list of filenames (without extension).
    """
    access_token = await get_access_token()
    folder_info = await resolve_folder_from_share_link(access_token, share_link)
    drive_id = folder_info["drive_id"]
    item_id = folder_info["item_id"]

    url = f"{GRAPH_BASE}/drives/{drive_id}/items/{item_id}/children?$select=name&$top=500"
    headers = {"Authorization": f"Bearer {access_token}"}

    all_files = []
    async with httpx.AsyncClient(timeout=30.0) as client:
        while url:
            resp = await client.get(url, headers=headers)
            if resp.status_code != 200:
                error_detail = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else resp.text
                logger.error(f"Failed to list folder ({resp.status_code}): {error_detail}")
                raise Exception(f"Failed to list SharePoint folder: {error_detail}")
            data = resp.json()
            for item in data.get("value", []):
                all_files.append(item.get("name", ""))
            url = data.get("@odata.nextLink")

    logger.info(f"Found {len(all_files)} files in SharePoint folder")
    return all_files
