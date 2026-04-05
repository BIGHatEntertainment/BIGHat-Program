"""
Phase 1 POC - Part 2: Explore SharePoint subfolders for JSON files
"""
import os, json, base64, asyncio, httpx
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")

CLIENT_ID = os.environ.get("AZURE_CLIENT_ID")
TENANT_ID = os.environ.get("AZURE_TENANT_ID")
CLIENT_SECRET = os.environ.get("AZURE_CLIENT_SECRET")
SHARING_URL = os.environ.get("SHAREPOINT_SHARING_URL")
GRAPH_API = "https://graph.microsoft.com/v1.0"


async def get_token():
    token_url = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token"
    data = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "scope": "https://graph.microsoft.com/.default",
        "grant_type": "client_credentials"
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(token_url, data=data, timeout=30)
        return resp.json().get("access_token")


async def explore_folder(token, drive_id, item_id, path="", depth=0):
    """Recursively explore folder structure"""
    headers = {"Authorization": f"Bearer {token}"}
    indent = "  " * depth
    
    async with httpx.AsyncClient() as client:
        url = f"{GRAPH_API}/drives/{drive_id}/items/{item_id}/children"
        resp = await client.get(url, headers=headers, timeout=30)
        
        if resp.status_code != 200:
            print(f"{indent}Error: {resp.status_code} - {resp.text[:200]}")
            return []
        
        data = resp.json()
        children = data.get('value', [])
        json_files = []
        
        for child in children:
            name = child.get('name', 'unknown')
            full_path = f"{path}/{name}"
            
            if 'folder' in child:
                print(f"{indent}[FOLDER] {full_path} ({child['folder'].get('childCount')} items)")
                # Recurse into subfolder
                sub_files = await explore_folder(token, drive_id, child['id'], full_path, depth + 1)
                json_files.extend(sub_files)
            elif 'file' in child:
                size = child.get('size', 0)
                mime = child['file'].get('mimeType', 'unknown')
                print(f"{indent}[FILE] {full_path} ({size} bytes, {mime})")
                
                if name.endswith('.json'):
                    json_files.append({
                        'name': name,
                        'path': full_path,
                        'id': child['id'],
                        'drive_id': drive_id,
                        'size': size,
                        'download_url': child.get('@microsoft.graph.downloadUrl')
                    })
                elif name.endswith(('.xlsx', '.csv', '.txt')):
                    # Also note other data files
                    json_files.append({
                        'name': name,
                        'path': full_path,
                        'id': child['id'],
                        'drive_id': drive_id,
                        'size': size,
                        'download_url': child.get('@microsoft.graph.downloadUrl'),
                        'type': 'other'
                    })
        
        return json_files


async def download_and_preview(token, file_info):
    """Download a file and preview its contents"""
    headers = {"Authorization": f"Bearer {token}"}
    
    async with httpx.AsyncClient() as client:
        # Try download URL first (no auth needed), then Graph API
        if file_info.get('download_url'):
            resp = await client.get(file_info['download_url'], timeout=30, follow_redirects=True)
        else:
            url = f"{GRAPH_API}/drives/{file_info['drive_id']}/items/{file_info['id']}/content"
            resp = await client.get(url, headers=headers, timeout=30, follow_redirects=True)
        
        if resp.status_code == 200:
            content = resp.text
            print(f"\n--- Content of {file_info['name']} ---")
            print(content[:2000])
            if len(content) > 2000:
                print(f"... ({len(content)} total chars)")
            
            # Try to parse as JSON
            if file_info['name'].endswith('.json'):
                try:
                    data = json.loads(content)
                    print(f"\nParsed JSON structure: {type(data)}")
                    if isinstance(data, dict):
                        print(f"Keys: {list(data.keys())}")
                    elif isinstance(data, list):
                        print(f"List length: {len(data)}")
                        if data:
                            print(f"First item keys: {list(data[0].keys()) if isinstance(data[0], dict) else 'not a dict'}")
                    return data
                except json.JSONDecodeError as e:
                    print(f"JSON parse error: {e}")
            return content
        else:
            print(f"Download failed: {resp.status_code}")
            return None


async def main():
    print("=" * 60)
    print("Exploring SharePoint Folder Structure")
    print("=" * 60)
    
    token = await get_token()
    if not token:
        print("Failed to get token")
        return
    
    # Resolve sharing link
    encoded = base64.b64encode(SHARING_URL.encode()).decode()
    encoded = encoded.rstrip('=').replace('+', '-').replace('/', '_')
    sharing_token = f"u!{encoded}"
    
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{GRAPH_API}/shares/{sharing_token}/driveItem", headers=headers, timeout=30)
        drive_item = resp.json()
    
    drive_id = drive_item['parentReference']['driveId']
    item_id = drive_item['id']
    
    print(f"\nRoot folder: {drive_item['name']}")
    print(f"Drive ID: {drive_id}")
    print(f"Item ID: {item_id}")
    print()
    
    # Explore recursively
    all_files = await explore_folder(token, drive_id, item_id)
    
    print(f"\n{'='*60}")
    print(f"Found {len(all_files)} data files total")
    print(f"{'='*60}")
    
    # Download and preview each file
    for f in all_files:
        print(f"\n>>> Downloading: {f['path']} ({f['size']} bytes)")
        await download_and_preview(token, f)


if __name__ == "__main__":
    asyncio.run(main())
