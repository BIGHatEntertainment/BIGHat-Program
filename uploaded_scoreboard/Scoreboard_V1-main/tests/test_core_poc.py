"""
Phase 1 POC: Test SharePoint Integration
- Authenticate with Azure AD using client credentials
- Resolve SharePoint sharing link to drive item
- List JSON files in the shared folder
- Download and parse JSON file contents
"""

import os
import sys
import json
import base64
import asyncio
import httpx
from dotenv import load_dotenv

# Load env from backend
load_dotenv("/app/backend/.env")

CLIENT_ID = os.environ.get("AZURE_CLIENT_ID")
TENANT_ID = os.environ.get("AZURE_TENANT_ID")
CLIENT_SECRET = os.environ.get("AZURE_CLIENT_SECRET")
SHARING_URL = os.environ.get("SHAREPOINT_SHARING_URL")
GRAPH_API = "https://graph.microsoft.com/v1.0"

def test_env_vars():
    """Test 1: Verify all environment variables are set"""
    print("\n=== TEST 1: Environment Variables ===")
    assert CLIENT_ID, "AZURE_CLIENT_ID not set"
    assert TENANT_ID, "AZURE_TENANT_ID not set"
    assert CLIENT_SECRET, "AZURE_CLIENT_SECRET not set"
    assert SHARING_URL, "SHAREPOINT_SHARING_URL not set"
    print(f"  Client ID: {CLIENT_ID[:8]}...")
    print(f"  Tenant ID: {TENANT_ID[:8]}...")
    print(f"  Sharing URL: {SHARING_URL[:50]}...")
    print("  PASS: All env vars present")
    return True


async def test_get_token():
    """Test 2: Acquire OAuth2 token using client credentials flow"""
    print("\n=== TEST 2: OAuth2 Token Acquisition ===")
    token_url = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token"
    data = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "scope": "https://graph.microsoft.com/.default",
        "grant_type": "client_credentials"
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(token_url, data=data, timeout=30)
        print(f"  Status: {resp.status_code}")
        if resp.status_code != 200:
            print(f"  ERROR: {resp.text}")
            return None
        token_data = resp.json()
        token = token_data.get("access_token")
        print(f"  Token acquired: {token[:20]}...")
        print(f"  Expires in: {token_data.get('expires_in')} seconds")
        print("  PASS: Token acquired successfully")
        return token


async def test_resolve_sharing_link(token):
    """Test 3: Resolve the SharePoint sharing link to a drive item"""
    print("\n=== TEST 3: Resolve Sharing Link ===")
    
    # Encode sharing URL per Microsoft docs:
    # 1. Base64 encode the URL
    # 2. Convert to base64url (replace +/-, replace /_, strip =)
    # 3. Prepend u!
    encoded = base64.b64encode(SHARING_URL.encode()).decode()
    encoded = encoded.rstrip('=').replace('+', '-').replace('/', '_')
    sharing_token = f"u!{encoded}"
    
    print(f"  Encoded token: {sharing_token[:30]}...")
    
    headers = {"Authorization": f"Bearer {token}"}
    
    async with httpx.AsyncClient() as client:
        # First try driveItem
        url = f"{GRAPH_API}/shares/{sharing_token}/driveItem"
        print(f"  Requesting: {url[:80]}...")
        resp = await client.get(url, headers=headers, timeout=30)
        print(f"  Status: {resp.status_code}")
        
        if resp.status_code == 200:
            item = resp.json()
            print(f"  Item name: {item.get('name')}")
            print(f"  Item ID: {item.get('id')}")
            print(f"  Is folder: {'folder' in item}")
            if 'parentReference' in item:
                parent = item['parentReference']
                print(f"  Drive ID: {parent.get('driveId')}")
                print(f"  Site ID: {parent.get('siteId')}")
            print("  PASS: Sharing link resolved")
            return item
        else:
            print(f"  Response: {resp.text[:500]}")
            
            # Try root endpoint
            url2 = f"{GRAPH_API}/shares/{sharing_token}/root"
            resp2 = await client.get(url2, headers=headers, timeout=30)
            print(f"  Root endpoint status: {resp2.status_code}")
            if resp2.status_code == 200:
                item = resp2.json()
                print(f"  Root item: {json.dumps(item, indent=2)[:500]}")
                return item
            else:
                print(f"  Root response: {resp2.text[:500]}")
            return None


async def test_list_folder_children(token, drive_item):
    """Test 4: List children (files) in the resolved folder"""
    print("\n=== TEST 4: List Folder Contents ===")
    
    if not drive_item:
        print("  SKIP: No drive item from previous test")
        return None
    
    headers = {"Authorization": f"Bearer {token}"}
    drive_id = drive_item.get('parentReference', {}).get('driveId')
    item_id = drive_item.get('id')
    
    if not drive_id:
        # Try using the shares endpoint to list children
        print("  No driveId in parentReference, trying shares endpoint...")
        encoded = base64.b64encode(SHARING_URL.encode()).decode()
        encoded = encoded.rstrip('=').replace('+', '-').replace('/', '_')
        sharing_token = f"u!{encoded}"
        
        async with httpx.AsyncClient() as client:
            url = f"{GRAPH_API}/shares/{sharing_token}/driveItem/children"
            resp = await client.get(url, headers=headers, timeout=30)
            print(f"  Status: {resp.status_code}")
            if resp.status_code == 200:
                data = resp.json()
                children = data.get('value', [])
                print(f"  Found {len(children)} items:")
                for child in children:
                    print(f"    - {child.get('name')} (size: {child.get('size', 'N/A')})")
                    if 'file' in child:
                        print(f"      Type: file, MIME: {child['file'].get('mimeType')}")
                    elif 'folder' in child:
                        print(f"      Type: folder, Count: {child['folder'].get('childCount')}")
                print("  PASS: Children listed")
                return children
            else:
                print(f"  Response: {resp.text[:500]}")
                return None
    
    async with httpx.AsyncClient() as client:
        url = f"{GRAPH_API}/drives/{drive_id}/items/{item_id}/children"
        resp = await client.get(url, headers=headers, timeout=30)
        print(f"  Status: {resp.status_code}")
        
        if resp.status_code == 200:
            data = resp.json()
            children = data.get('value', [])
            print(f"  Found {len(children)} items:")
            for child in children:
                print(f"    - {child.get('name')} (size: {child.get('size', 'N/A')})")
                if 'file' in child:
                    print(f"      Type: file, MIME: {child['file'].get('mimeType')}")
                elif 'folder' in child:
                    print(f"      Type: folder, Count: {child['folder'].get('childCount')}")
            print("  PASS: Children listed")
            return children
        else:
            print(f"  Response: {resp.text[:500]}")
            return None


async def test_download_json_file(token, drive_item, children):
    """Test 5: Download and parse a JSON file"""
    print("\n=== TEST 5: Download JSON File ===")
    
    if not children:
        print("  SKIP: No children from previous test")
        return None
    
    # Find first JSON file
    json_files = [c for c in children if c.get('name', '').endswith('.json')]
    if not json_files:
        print("  No JSON files found in folder")
        # Try to download any file to see what's there
        if children:
            print(f"  Available files: {[c.get('name') for c in children]}")
        return None
    
    target = json_files[0]
    print(f"  Target file: {target.get('name')}")
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # Get the download URL
    drive_id = target.get('parentReference', {}).get('driveId') or drive_item.get('parentReference', {}).get('driveId')
    item_id = target.get('id')
    
    async with httpx.AsyncClient() as client:
        if drive_id:
            url = f"{GRAPH_API}/drives/{drive_id}/items/{item_id}/content"
        else:
            # Try using @microsoft.graph.downloadUrl if available
            download_url = target.get('@microsoft.graph.downloadUrl')
            if download_url:
                url = download_url
                headers = {}  # Download URL doesn't need auth
            else:
                print("  No drive_id or downloadUrl available")
                return None
        
        print(f"  Downloading from: {url[:80]}...")
        resp = await client.get(url, headers=headers, timeout=30, follow_redirects=True)
        print(f"  Status: {resp.status_code}")
        
        if resp.status_code == 200:
            try:
                content = resp.json()
                print(f"  JSON parsed successfully!")
                print(f"  Content preview: {json.dumps(content, indent=2)[:500]}")
                print("  PASS: JSON file downloaded and parsed")
                return content
            except json.JSONDecodeError:
                content_text = resp.text[:500]
                print(f"  Content is not JSON: {content_text}")
                return None
        else:
            print(f"  Response: {resp.text[:500]}")
            return None


async def run_all_tests():
    """Run all POC tests sequentially"""
    print("=" * 60)
    print("BIG Hat Trivia - SharePoint Integration POC")
    print("=" * 60)
    
    # Test 1: Env vars
    test_env_vars()
    
    # Test 2: Token
    token = await test_get_token()
    if not token:
        print("\nFAILED: Could not acquire token. Stopping.")
        return False
    
    # Test 3: Resolve sharing link
    drive_item = await test_resolve_sharing_link(token)
    
    # Test 4: List folder contents
    children = await test_list_folder_children(token, drive_item)
    
    # Test 5: Download JSON
    json_data = await test_download_json_file(token, drive_item, children)
    
    print("\n" + "=" * 60)
    print("POC SUMMARY")
    print("=" * 60)
    print(f"  Token:         {'PASS' if token else 'FAIL'}")
    print(f"  Sharing Link:  {'PASS' if drive_item else 'FAIL'}")
    print(f"  Folder List:   {'PASS' if children else 'FAIL'}")
    print(f"  JSON Download: {'PASS' if json_data else 'FAIL'}")
    
    all_pass = all([token, drive_item, children is not None])
    print(f"\n  Overall: {'ALL PASS' if all_pass else 'SOME FAILURES'}")
    return all_pass


if __name__ == "__main__":
    result = asyncio.run(run_all_tests())
    sys.exit(0 if result else 1)
