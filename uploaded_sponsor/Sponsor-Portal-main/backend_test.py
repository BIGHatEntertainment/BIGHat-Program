#!/usr/bin/env python3
"""
Comprehensive Backend API Testing for BIG Hat Sponsor Portal
Tests all API endpoints: sponsors, locations, accounts, assets, subscriptions, init
"""

import requests
import json
import sys
from typing import Dict, Any, Optional

# API Base URL from frontend/.env
API_BASE_URL = "https://sponsor-hub-9.preview.emergentagent.com/api"

class APITester:
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.session = requests.Session()
        self.test_data = {}  # Store created test data for cleanup
        
    def log(self, message: str, level: str = "INFO"):
        """Log test messages"""
        print(f"[{level}] {message}")
        
    def make_request(self, method: str, endpoint: str, data: Optional[Dict] = None, params: Optional[Dict] = None) -> Dict[str, Any]:
        """Make HTTP request and return response data"""
        url = f"{self.base_url}{endpoint}"
        
        try:
            if method.upper() == "GET":
                response = self.session.get(url, params=params)
            elif method.upper() == "POST":
                response = self.session.post(url, json=data, params=params)
            elif method.upper() == "PUT":
                response = self.session.put(url, json=data)
            elif method.upper() == "DELETE":
                response = self.session.delete(url)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
                
            return {
                "status_code": response.status_code,
                "data": response.json() if response.content else {},
                "success": 200 <= response.status_code < 300
            }
        except requests.exceptions.RequestException as e:
            return {
                "status_code": 0,
                "data": {"error": str(e)},
                "success": False
            }
        except json.JSONDecodeError:
            return {
                "status_code": response.status_code,
                "data": {"error": "Invalid JSON response"},
                "success": False
            }

    def test_init_api(self):
        """Test /api/init endpoint - Initialize database"""
        self.log("=== Testing Init API ===")
        
        # Test database initialization
        result = self.make_request("POST", "/init")
        
        if result["success"]:
            self.log("✅ Database initialization successful")
            self.log(f"   Response: {result['data']}")
        else:
            self.log(f"❌ Database initialization failed: {result['status_code']} - {result['data']}")
            
        return result["success"]

    def test_sponsors_api(self):
        """Test /api/sponsors endpoints"""
        self.log("=== Testing Sponsors API ===")
        success_count = 0
        
        # 1. GET /api/sponsors - Should return list of sponsors (expect 4+)
        result = self.make_request("GET", "/sponsors")
        if result["success"]:
            sponsors = result["data"]
            if len(sponsors) >= 3:  # At least 3 from seed data
                self.log(f"✅ GET /sponsors successful - Found {len(sponsors)} sponsors")
                success_count += 1
            else:
                self.log(f"❌ GET /sponsors - Expected 3+ sponsors, got {len(sponsors)}")
        else:
            self.log(f"❌ GET /sponsors failed: {result['status_code']} - {result['data']}")
            
        # 2. POST /api/sponsors - Create new sponsor
        test_sponsor_data = {
            "business_name": "API Test Sponsor",
            "email": "apitest@sponsor.com",
            "contact_name": "API Tester",
            "phone": "(602) 555-0000",
            "package": "Bronze Sponsor",
            "status": "active"
        }
        
        result = self.make_request("POST", "/sponsors", test_sponsor_data)
        if result["success"]:
            created_sponsor = result["data"]
            self.test_data["sponsor_id"] = created_sponsor["id"]
            self.log(f"✅ POST /sponsors successful - Created sponsor ID: {created_sponsor['id']}")
            success_count += 1
        else:
            self.log(f"❌ POST /sponsors failed: {result['status_code']} - {result['data']}")
            
        # 3. GET /api/sponsors/{id} - Get specific sponsor
        if "sponsor_id" in self.test_data:
            result = self.make_request("GET", f"/sponsors/{self.test_data['sponsor_id']}")
            if result["success"]:
                sponsor = result["data"]
                if sponsor["business_name"] == "API Test Sponsor":
                    self.log(f"✅ GET /sponsors/{{id}} successful - Retrieved correct sponsor")
                    success_count += 1
                else:
                    self.log(f"❌ GET /sponsors/{{id}} - Wrong sponsor data returned")
            else:
                self.log(f"❌ GET /sponsors/{{id}} failed: {result['status_code']} - {result['data']}")
                
        # 4. PUT /api/sponsors/{id} - Update sponsor status
        if "sponsor_id" in self.test_data:
            update_data = {"status": "inactive"}
            result = self.make_request("PUT", f"/sponsors/{self.test_data['sponsor_id']}", update_data)
            if result["success"]:
                updated_sponsor = result["data"]
                if updated_sponsor["status"] == "inactive":
                    self.log(f"✅ PUT /sponsors/{{id}} successful - Status updated to inactive")
                    success_count += 1
                else:
                    self.log(f"❌ PUT /sponsors/{{id}} - Status not updated correctly")
            else:
                self.log(f"❌ PUT /sponsors/{{id}} failed: {result['status_code']} - {result['data']}")
                
        # 5. DELETE /api/sponsors/{id} - Delete the test sponsor (cleanup)
        if "sponsor_id" in self.test_data:
            result = self.make_request("DELETE", f"/sponsors/{self.test_data['sponsor_id']}")
            if result["success"]:
                self.log(f"✅ DELETE /sponsors/{{id}} successful - Test sponsor deleted")
                success_count += 1
                del self.test_data["sponsor_id"]
            else:
                self.log(f"❌ DELETE /sponsors/{{id}} failed: {result['status_code']} - {result['data']}")
                
        return success_count == 5

    def test_locations_api(self):
        """Test /api/locations endpoints"""
        self.log("=== Testing Locations API ===")
        success_count = 0
        
        # 1. GET /api/locations - Should return 6 locations
        result = self.make_request("GET", "/locations")
        if result["success"]:
            locations = result["data"]
            if len(locations) >= 6:
                self.log(f"✅ GET /locations successful - Found {len(locations)} locations")
                success_count += 1
            else:
                self.log(f"❌ GET /locations - Expected 6+ locations, got {len(locations)}")
        else:
            self.log(f"❌ GET /locations failed: {result['status_code']} - {result['data']}")
            
        # 2. POST /api/locations - Create new location
        test_location_data = {
            "name": "Test Venue API",
            "address": "999 Test St",
            "city": "Phoenix",
            "state": "AZ",
            "status": "active"
        }
        
        result = self.make_request("POST", "/locations", test_location_data)
        if result["success"]:
            created_location = result["data"]
            self.test_data["location_id"] = created_location["id"]
            self.log(f"✅ POST /locations successful - Created location ID: {created_location['id']}")
            success_count += 1
        else:
            self.log(f"❌ POST /locations failed: {result['status_code']} - {result['data']}")
            
        # 3. PUT /api/locations/{id} - Update location
        if "location_id" in self.test_data:
            update_data = {"status": "inactive"}
            result = self.make_request("PUT", f"/locations/{self.test_data['location_id']}", update_data)
            if result["success"]:
                updated_location = result["data"]
                if updated_location["status"] == "inactive":
                    self.log(f"✅ PUT /locations/{{id}} successful - Status updated")
                    success_count += 1
                else:
                    self.log(f"❌ PUT /locations/{{id}} - Status not updated correctly")
            else:
                self.log(f"❌ PUT /locations/{{id}} failed: {result['status_code']} - {result['data']}")
                
        # 4. DELETE /api/locations/{id} - Delete test location (cleanup)
        if "location_id" in self.test_data:
            result = self.make_request("DELETE", f"/locations/{self.test_data['location_id']}")
            if result["success"]:
                self.log(f"✅ DELETE /locations/{{id}} successful - Test location deleted")
                success_count += 1
                del self.test_data["location_id"]
            else:
                self.log(f"❌ DELETE /locations/{{id}} failed: {result['status_code']} - {result['data']}")
                
        return success_count == 4

    def test_accounts_api(self):
        """Test /api/accounts endpoints"""
        self.log("=== Testing Accounts API ===")
        success_count = 0
        
        # 1. GET /api/accounts - Should return registered accounts (2+)
        result = self.make_request("GET", "/accounts")
        if result["success"]:
            accounts = result["data"]
            self.log(f"✅ GET /accounts successful - Found {len(accounts)} accounts")
            success_count += 1
        else:
            self.log(f"❌ GET /accounts failed: {result['status_code']} - {result['data']}")
            
        # 2. GET /api/accounts/unlinked - Should return accounts not yet linked to sponsors
        result = self.make_request("GET", "/accounts/unlinked")
        if result["success"]:
            unlinked_accounts = result["data"]
            self.log(f"✅ GET /accounts/unlinked successful - Found {len(unlinked_accounts)} unlinked accounts")
            success_count += 1
        else:
            self.log(f"❌ GET /accounts/unlinked failed: {result['status_code']} - {result['data']}")
            
        # 3. POST /api/accounts - Register new account
        test_account_data = {
            "email": "apitest@account.com",
            "business_name": "API Test Account",
            "contact_name": "Account Tester"
        }
        
        result = self.make_request("POST", "/accounts", test_account_data)
        if result["success"]:
            created_account = result["data"]
            self.test_data["account_id"] = created_account["id"]
            self.log(f"✅ POST /accounts successful - Created account ID: {created_account['id']}")
            success_count += 1
        else:
            self.log(f"❌ POST /accounts failed: {result['status_code']} - {result['data']}")
            
        return success_count == 3

    def test_assets_api(self):
        """Test /api/assets endpoints"""
        self.log("=== Testing Assets API ===")
        success_count = 0
        
        # 1. GET /api/assets - Should return list of assets
        result = self.make_request("GET", "/assets")
        if result["success"]:
            assets = result["data"]
            self.log(f"✅ GET /assets successful - Found {len(assets)} assets")
            success_count += 1
        else:
            self.log(f"❌ GET /assets failed: {result['status_code']} - {result['data']}")
            
        # 2. GET /api/assets/pending - Should return pending assets
        result = self.make_request("GET", "/assets/pending")
        if result["success"]:
            pending_assets = result["data"]
            self.log(f"✅ GET /assets/pending successful - Found {len(pending_assets)} pending assets")
            success_count += 1
        else:
            self.log(f"❌ GET /assets/pending failed: {result['status_code']} - {result['data']}")
            
        # 3. POST /api/assets - Create test asset
        test_asset_data = {
            "name": "API Test Asset",
            "type": "16:9",
            "sponsor_email": "apitest@sponsor.com",
            "sponsor_name": "API Test Sponsor",
            "status": "pending"
        }
        
        result = self.make_request("POST", "/assets", test_asset_data)
        if result["success"]:
            created_asset = result["data"]
            self.test_data["asset_id"] = created_asset["id"]
            self.log(f"✅ POST /assets successful - Created asset ID: {created_asset['id']}")
            success_count += 1
        else:
            self.log(f"❌ POST /assets failed: {result['status_code']} - {result['data']}")
            
        # 4. POST /api/assets/{id}/approve - Approve asset
        if "asset_id" in self.test_data:
            result = self.make_request("POST", f"/assets/{self.test_data['asset_id']}/approve")
            if result["success"]:
                self.log(f"✅ POST /assets/{{id}}/approve successful - Asset approved")
                success_count += 1
            else:
                self.log(f"❌ POST /assets/{{id}}/approve failed: {result['status_code']} - {result['data']}")
                
        # 5. DELETE /api/assets/{id} - Delete test asset (cleanup)
        if "asset_id" in self.test_data:
            result = self.make_request("DELETE", f"/assets/{self.test_data['asset_id']}")
            if result["success"]:
                self.log(f"✅ DELETE /assets/{{id}} successful - Test asset deleted")
                success_count += 1
                del self.test_data["asset_id"]
            else:
                self.log(f"❌ DELETE /assets/{{id}} failed: {result['status_code']} - {result['data']}")
                
        return success_count == 5

    def test_subscriptions_api(self):
        """Test /api/subscriptions endpoints"""
        self.log("=== Testing Subscriptions API ===")
        success_count = 0
        
        # 1. GET /api/subscriptions - Should return list of subscriptions
        result = self.make_request("GET", "/subscriptions")
        if result["success"]:
            subscriptions = result["data"]
            self.log(f"✅ GET /subscriptions successful - Found {len(subscriptions)} subscriptions")
            success_count += 1
        else:
            self.log(f"❌ GET /subscriptions failed: {result['status_code']} - {result['data']}")
            
        # 2. POST /api/subscriptions - Create test subscription
        test_subscription_data = {
            "user_id": "apitest@subscription.com",
            "package_id": "bronze",
            "package_name": "Bronze Sponsor",
            "price": 375.0
        }
        
        result = self.make_request("POST", "/subscriptions", test_subscription_data)
        if result["success"]:
            created_subscription = result["data"]
            self.test_data["subscription_id"] = created_subscription["id"]
            self.log(f"✅ POST /subscriptions successful - Created subscription ID: {created_subscription['id']}")
            success_count += 1
        else:
            self.log(f"❌ POST /subscriptions failed: {result['status_code']} - {result['data']}")
            
        return success_count == 2

    def test_canva_api(self):
        """Test /api/canva endpoints for Canva Connect integration"""
        self.log("=== Testing Canva API ===")
        success_count = 0
        
        # 1. GET /api/canva/status - Check Canva connection status
        result = self.make_request("GET", "/canva/status")
        if result["success"]:
            status_data = result["data"]
            # Should return connected: false when not connected
            if "connected" in status_data and status_data["connected"] == False:
                self.log(f"✅ GET /canva/status successful - Not connected as expected: {status_data}")
                success_count += 1
            else:
                self.log(f"❌ GET /canva/status - Unexpected response format: {status_data}")
        else:
            self.log(f"❌ GET /canva/status failed: {result['status_code']} - {result['data']}")
            
        # 2. GET /api/canva/auth - Initiate OAuth flow
        result = self.make_request("GET", "/canva/auth")
        if result["success"]:
            auth_data = result["data"]
            # Should return auth_url and state
            if "auth_url" in auth_data and "state" in auth_data:
                auth_url = auth_data["auth_url"]
                # Verify auth_url contains required PKCE parameters
                if ("client_id=OC-AZsygO_WYiIo" in auth_url and 
                    "code_challenge=" in auth_url and 
                    "code_challenge_method=S256" in auth_url):
                    self.log(f"✅ GET /canva/auth successful - OAuth URL with PKCE parameters generated")
                    success_count += 1
                else:
                    self.log(f"❌ GET /canva/auth - Missing required PKCE parameters in auth_url: {auth_url}")
            else:
                self.log(f"❌ GET /canva/auth - Missing auth_url or state: {auth_data}")
        else:
            self.log(f"❌ GET /canva/auth failed: {result['status_code']} - {result['data']}")
            
        # 3. GET /api/canva/pending-sync-count - Get count of assets pending sync
        result = self.make_request("GET", "/canva/pending-sync-count")
        if result["success"]:
            count_data = result["data"]
            if "pending_count" in count_data and isinstance(count_data["pending_count"], int):
                self.log(f"✅ GET /canva/pending-sync-count successful - Pending count: {count_data['pending_count']}")
                success_count += 1
            else:
                self.log(f"❌ GET /canva/pending-sync-count - Invalid response format: {count_data}")
        else:
            self.log(f"❌ GET /canva/pending-sync-count failed: {result['status_code']} - {result['data']}")
            
        # 4. GET /api/canva/sync-logs - Get recent sync history
        result = self.make_request("GET", "/canva/sync-logs")
        if result["success"]:
            logs_data = result["data"]
            if isinstance(logs_data, list):
                self.log(f"✅ GET /canva/sync-logs successful - Found {len(logs_data)} sync logs")
                success_count += 1
            else:
                self.log(f"❌ GET /canva/sync-logs - Expected array, got: {type(logs_data)}")
        else:
            self.log(f"❌ GET /canva/sync-logs failed: {result['status_code']} - {result['data']}")
            
        # 5. POST /api/canva/sync - Trigger manual sync (should fail when not connected)
        result = self.make_request("POST", "/canva/sync")
        if result["status_code"] == 400:
            # Should return 400 error when not connected
            error_data = result["data"]
            if "detail" in error_data and "not connected" in error_data["detail"].lower():
                self.log(f"✅ POST /canva/sync correctly failed - Canva not connected: {error_data['detail']}")
                success_count += 1
            else:
                self.log(f"❌ POST /canva/sync - Wrong error message: {error_data}")
        else:
            self.log(f"❌ POST /canva/sync - Expected 400 error, got {result['status_code']}: {result['data']}")
            
        # 6. POST /api/canva/disconnect - Disconnect Canva (safe to call when not connected)
        result = self.make_request("POST", "/canva/disconnect")
        if result["success"]:
            disconnect_data = result["data"]
            if "success" in disconnect_data and disconnect_data["success"] == True:
                self.log(f"✅ POST /canva/disconnect successful - {disconnect_data.get('message', 'Disconnected')}")
                success_count += 1
            else:
                self.log(f"❌ POST /canva/disconnect - Unexpected response: {disconnect_data}")
        else:
            self.log(f"❌ POST /canva/disconnect failed: {result['status_code']} - {result['data']}")
            
        return success_count == 6

    def test_placements_api(self):
        """Test /api/placements endpoints for Sponsor Placement Matrix"""
        self.log("=== Testing Sponsor Placement Matrix API ===")
        success_count = 0
        
        # Use existing sponsor from the review request
        test_sponsor_id = "sponsor_3c44d2bd1c12"  # Monkey Pants Bar & Grill
        
        # 1. GET /api/placements/placement-types - Should return 9 placement types
        result = self.make_request("GET", "/placements/placement-types")
        if result["success"]:
            placement_types = result["data"]
            expected_types = [
                "preshow_16x9", "round1_overlay", "round2_overlay", "round3_overlay", 
                "mystery_overlay", "sponsor_section_16x9", "sponsor_logo_only", 
                "sponsor_logo_detail", "thank_you"
            ]
            
            if len(placement_types) == 9:
                type_ids = [pt["id"] for pt in placement_types]
                if all(expected_type in type_ids for expected_type in expected_types):
                    self.log(f"✅ GET /placements/placement-types successful - Found all 9 expected placement types")
                    success_count += 1
                else:
                    self.log(f"❌ GET /placements/placement-types - Missing expected placement types")
            else:
                self.log(f"❌ GET /placements/placement-types - Expected 9 types, got {len(placement_types)}")
        else:
            self.log(f"❌ GET /placements/placement-types failed: {result['status_code']} - {result['data']}")
            
        # 2. GET /api/placements/matrix/{sponsor_id} - Get full placement matrix
        result = self.make_request("GET", f"/placements/matrix/{test_sponsor_id}")
        if result["success"]:
            matrix_data = result["data"]
            required_fields = ["sponsor_id", "sponsor_name", "locations", "placement_types", "placements"]
            
            if all(field in matrix_data for field in required_fields):
                self.log(f"✅ GET /placements/matrix/{{sponsor_id}} successful - Matrix contains all required fields")
                self.log(f"   Sponsor: {matrix_data['sponsor_name']}")
                self.log(f"   Locations: {len(matrix_data['locations'])}")
                self.log(f"   Placement Types: {len(matrix_data['placement_types'])}")
                success_count += 1
                
                # Store first location for testing
                if matrix_data["locations"]:
                    self.test_data["test_location_id"] = matrix_data["locations"][0]["id"]
            else:
                self.log(f"❌ GET /placements/matrix/{{sponsor_id}} - Missing required fields: {matrix_data}")
        else:
            self.log(f"❌ GET /placements/matrix/{{sponsor_id}} failed: {result['status_code']} - {result['data']}")
            
        # 3. PUT /api/placements/matrix/{sponsor_id} - Update single placement
        if "test_location_id" in self.test_data:
            # Use query parameters for PUT request
            endpoint = f"/placements/matrix/{test_sponsor_id}?location_id={self.test_data['test_location_id']}&placement_type=preshow_16x9&enabled=true"
            result = self.make_request("PUT", endpoint)
            if result["success"]:
                update_data = result["data"]
                if update_data.get("success") == True and update_data.get("enabled") == True:
                    self.log(f"✅ PUT /placements/matrix/{{sponsor_id}} successful - Placement enabled")
                    success_count += 1
                else:
                    self.log(f"❌ PUT /placements/matrix/{{sponsor_id}} - Unexpected response: {update_data}")
            else:
                self.log(f"❌ PUT /placements/matrix/{{sponsor_id}} failed: {result['status_code']} - {result['data']}")
                
        # 4. GET /api/placements/sponsor/{sponsor_id}/enabled - Get enabled placements
        result = self.make_request("GET", f"/placements/sponsor/{test_sponsor_id}/enabled")
        if result["success"]:
            enabled_data = result["data"]
            required_fields = ["sponsor_id", "enabled_placements", "by_location"]
            
            if all(field in enabled_data for field in required_fields):
                enabled_count = len(enabled_data["enabled_placements"])
                self.log(f"✅ GET /placements/sponsor/{{sponsor_id}}/enabled successful - Found {enabled_count} enabled placements")
                success_count += 1
            else:
                self.log(f"❌ GET /placements/sponsor/{{sponsor_id}}/enabled - Missing required fields: {enabled_data}")
        else:
            self.log(f"❌ GET /placements/sponsor/{{sponsor_id}}/enabled failed: {result['status_code']} - {result['data']}")
            
        # 5. POST /api/placements/matrix/{sponsor_id}/select-all-location/{location_id} - Select all for location
        if "test_location_id" in self.test_data:
            endpoint = f"/placements/matrix/{test_sponsor_id}/select-all-location/{self.test_data['test_location_id']}?enabled=true"
            result = self.make_request("POST", endpoint)
            if result["success"]:
                select_data = result["data"]
                if (select_data.get("success") == True and 
                    select_data.get("location_id") == self.test_data["test_location_id"] and
                    select_data.get("all_enabled") == True):
                    self.log(f"✅ POST /placements/matrix/{{sponsor_id}}/select-all-location/{{location_id}} successful")
                    success_count += 1
                else:
                    self.log(f"❌ POST /placements/matrix/{{sponsor_id}}/select-all-location/{{location_id}} - Unexpected response: {select_data}")
            else:
                self.log(f"❌ POST /placements/matrix/{{sponsor_id}}/select-all-location/{{location_id}} failed: {result['status_code']} - {result['data']}")
                
        # 6. POST /api/placements/matrix/{sponsor_id}/select-all-placement/{placement_type} - Select all for placement type
        endpoint = f"/placements/matrix/{test_sponsor_id}/select-all-placement/preshow_16x9?enabled=false"  # Disable to clean up
        result = self.make_request("POST", endpoint)
        if result["success"]:
            select_data = result["data"]
            if (select_data.get("success") == True and 
                select_data.get("placement_type") == "preshow_16x9" and
                select_data.get("all_enabled") == False):
                self.log(f"✅ POST /placements/matrix/{{sponsor_id}}/select-all-placement/{{placement_type}} successful")
                success_count += 1
            else:
                self.log(f"❌ POST /placements/matrix/{{sponsor_id}}/select-all-placement/{{placement_type}} - Unexpected response: {select_data}")
        else:
            self.log(f"❌ POST /placements/matrix/{{sponsor_id}}/select-all-placement/{{placement_type}} failed: {result['status_code']} - {result['data']}")
            
        return success_count == 6

    def cleanup_test_data(self):
        """Clean up any remaining test data"""
        self.log("=== Cleaning up test data ===")
        
        # Clean up account if exists
        if "account_id" in self.test_data:
            result = self.make_request("DELETE", f"/accounts/{self.test_data['account_id']}")
            if result["success"]:
                self.log("✅ Test account cleaned up")
            else:
                self.log(f"❌ Failed to clean up test account: {result['data']}")
                
        # Clean up subscription if exists (cancel it)
        if "subscription_id" in self.test_data:
            result = self.make_request("POST", f"/subscriptions/{self.test_data['subscription_id']}/cancel")
            if result["success"]:
                self.log("✅ Test subscription cancelled")
            else:
                self.log(f"❌ Failed to cancel test subscription: {result['data']}")

    def test_login_and_profile_sync(self):
        """Test login and profile sync for BIG Hat Sponsor Portal"""
        self.log("=== Testing Login and Profile Sync ===")
        success_count = 0
        
        # Test 1: Account status check for nicholas.sellards@gmail.com
        self.log("Test 1: Account status check for nicholas.sellards@gmail.com")
        result = self.make_request("GET", "/accounts/check-status/nicholas.sellards@gmail.com")
        if result["success"]:
            status_data = result["data"]
            expected_exists = True
            expected_has_password = True
            expected_must_reset = True
            
            if (status_data.get("exists") == expected_exists and 
                status_data.get("has_password") == expected_has_password and
                status_data.get("must_reset_password") == expected_must_reset):
                self.log(f"✅ Account status check PASSED - exists={status_data.get('exists')}, has_password={status_data.get('has_password')}, must_reset_password={status_data.get('must_reset_password')}")
                success_count += 1
            else:
                self.log(f"❌ Account status check FAILED - Expected: exists={expected_exists}, has_password={expected_has_password}, must_reset_password={expected_must_reset}")
                self.log(f"   Got: exists={status_data.get('exists')}, has_password={status_data.get('has_password')}, must_reset_password={status_data.get('must_reset_password')}")
        else:
            self.log(f"❌ Account status check FAILED: {result['status_code']} - {result['data']}")
            
        # Test 2: Login with correct credentials
        self.log("Test 2: Login with nicholas.sellards@gmail.com and password B1GHat")
        login_params = {
            "email": "nicholas.sellards@gmail.com",
            "password": "B1GHat"
        }
        result = self.make_request("POST", "/accounts/login", params=login_params)
        if result["success"]:
            login_data = result["data"]
            expected_business_name = "Live Stream Show"
            expected_sponsor_tier = "gold"
            expected_sponsor_package = "Top Tier Presenter"
            
            # Check if all expected fields are present
            if (login_data.get("business_name") == expected_business_name and
                login_data.get("sponsor_tier") == expected_sponsor_tier and
                login_data.get("sponsor_package") == expected_sponsor_package and
                login_data.get("sponsor_id")):
                self.log(f"✅ Login PASSED - business_name='{login_data.get('business_name')}', sponsor_tier='{login_data.get('sponsor_tier')}', sponsor_package='{login_data.get('sponsor_package')}', sponsor_id='{login_data.get('sponsor_id')}'")
                success_count += 1
                
                # Store sponsor_id for Test 3
                self.test_data["login_sponsor_id"] = login_data.get("sponsor_id")
            else:
                self.log(f"❌ Login FAILED - Expected: business_name='{expected_business_name}', sponsor_tier='{expected_sponsor_tier}', sponsor_package='{expected_sponsor_package}'")
                self.log(f"   Got: business_name='{login_data.get('business_name')}', sponsor_tier='{login_data.get('sponsor_tier')}', sponsor_package='{login_data.get('sponsor_package')}', sponsor_id='{login_data.get('sponsor_id')}'")
        else:
            self.log(f"❌ Login FAILED: {result['status_code']} - {result['data']}")
            
        # Test 3: Verify sponsor has correct tier
        self.log("Test 3: Verify sponsor 'Live Stream Show' has tier='gold'")
        if "login_sponsor_id" in self.test_data:
            result = self.make_request("GET", f"/sponsors/{self.test_data['login_sponsor_id']}")
            if result["success"]:
                sponsor_data = result["data"]
                expected_business_name = "Live Stream Show"
                expected_tier = "gold"
                
                if (sponsor_data.get("business_name") == expected_business_name and
                    sponsor_data.get("tier") == expected_tier and
                    sponsor_data.get("user_id")):  # Check that sponsor is linked to user account
                    self.log(f"✅ Sponsor verification PASSED - business_name='{sponsor_data.get('business_name')}', tier='{sponsor_data.get('tier')}', user_id='{sponsor_data.get('user_id')}'")
                    success_count += 1
                else:
                    self.log(f"❌ Sponsor verification FAILED - Expected: business_name='{expected_business_name}', tier='{expected_tier}', user_id should exist")
                    self.log(f"   Got: business_name='{sponsor_data.get('business_name')}', tier='{sponsor_data.get('tier')}', user_id='{sponsor_data.get('user_id')}'")
            else:
                self.log(f"❌ Sponsor verification FAILED: {result['status_code']} - {result['data']}")
        else:
            self.log("❌ Sponsor verification SKIPPED - No sponsor_id from login test")
            
        return success_count == 3

    def test_stripe_checkout_session(self):
        """Test Stripe checkout session creation for BIG Hat Sponsor Portal"""
        self.log("=== Testing Stripe Checkout Session Creation ===")
        success_count = 0
        
        # Test data from the review request
        test_request = {
            "package_id": "silver",
            "origin_url": "http://localhost:3000",
            "user_email": "test@sponsor.com"
        }
        
        # 1. Test POST /api/payments/checkout/session
        self.log("Test 1: Creating Stripe checkout session for Silver package")
        result = self.make_request("POST", "/payments/checkout/session", test_request)
        
        if result["success"]:
            response_data = result["data"]
            
            # Verify response contains required fields
            if "url" in response_data and "session_id" in response_data:
                session_id = response_data["session_id"]
                checkout_url = response_data["url"]
                
                # Verify session_id format (should start with "cs_")
                if session_id.startswith("cs_"):
                    self.log(f"✅ Checkout session created successfully")
                    self.log(f"   Session ID: {session_id}")
                    self.log(f"   Checkout URL: {checkout_url}")
                    success_count += 1
                    
                    # Store session_id for further verification
                    self.test_data["stripe_session_id"] = session_id
                else:
                    self.log(f"❌ Invalid session ID format: {session_id} (should start with 'cs_')")
            else:
                self.log(f"❌ Missing required fields in response: {response_data}")
        else:
            self.log(f"❌ Failed to create checkout session: {result['status_code']} - {result['data']}")
            
        # 2. Test GET /api/payments/checkout/status/{session_id} - Check session status
        if "stripe_session_id" in self.test_data:
            self.log("Test 2: Checking checkout session status")
            result = self.make_request("GET", f"/payments/checkout/status/{self.test_data['stripe_session_id']}")
            
            if result["success"]:
                status_data = result["data"]
                required_fields = ["status", "payment_status", "amount_total", "currency"]
                
                if all(field in status_data for field in required_fields):
                    self.log(f"✅ Session status retrieved successfully")
                    self.log(f"   Status: {status_data.get('status')}")
                    self.log(f"   Payment Status: {status_data.get('payment_status')}")
                    self.log(f"   Amount: ${status_data.get('amount_total')} {status_data.get('currency', 'USD').upper()}")
                    success_count += 1
                else:
                    self.log(f"❌ Missing required fields in status response: {status_data}")
            else:
                self.log(f"❌ Failed to get session status: {result['status_code']} - {result['data']}")
                
        # 3. Test package validation - Invalid package
        self.log("Test 3: Testing invalid package validation")
        invalid_request = {
            "package_id": "invalid-package",
            "origin_url": "http://localhost:3000", 
            "user_email": "test@sponsor.com"
        }
        
        result = self.make_request("POST", "/payments/checkout/session", invalid_request)
        
        if result["status_code"] == 400:
            error_data = result["data"]
            if "detail" in error_data and "Invalid package" in error_data["detail"]:
                self.log(f"✅ Invalid package validation working correctly")
                success_count += 1
            else:
                self.log(f"❌ Wrong error message for invalid package: {error_data}")
        else:
            self.log(f"❌ Expected 400 error for invalid package, got {result['status_code']}: {result['data']}")
            
        # 4. Test GET /api/payments/packages - Verify Silver package exists
        self.log("Test 4: Verifying Silver package configuration")
        result = self.make_request("GET", "/payments/packages")
        
        if result["success"]:
            packages = result["data"]
            silver_package = None
            
            for pkg in packages:
                if pkg.get("id") == "silver":
                    silver_package = pkg
                    break
                    
            if silver_package:
                expected_price = 850.00
                if silver_package.get("price") == expected_price:
                    self.log(f"✅ Silver package found with correct price: ${silver_package.get('price')}")
                    self.log(f"   Name: {silver_package.get('name')}")
                    self.log(f"   Tier: {silver_package.get('tier')}")
                    success_count += 1
                else:
                    self.log(f"❌ Silver package price mismatch: expected ${expected_price}, got ${silver_package.get('price')}")
            else:
                self.log(f"❌ Silver package not found in packages list")
        else:
            self.log(f"❌ Failed to get packages: {result['status_code']} - {result['data']}")
            
        # 5. Test discount code validation
        self.log("Test 5: Testing discount code validation")
        result = self.make_request("GET", "/payments/discount/validate", params={"code": "AZLOCAL25"})
        
        if result["success"]:
            discount_data = result["data"]
            
            if (discount_data.get("valid") == True and 
                discount_data.get("code") == "AZLOCAL25" and
                discount_data.get("value") == 25):
                self.log(f"✅ Discount code validation working correctly")
                self.log(f"   Code: {discount_data.get('code')}")
                self.log(f"   Type: {discount_data.get('type')}")
                self.log(f"   Value: {discount_data.get('value')}%")
                success_count += 1
            else:
                self.log(f"❌ Discount validation failed: {discount_data}")
        else:
            self.log(f"❌ Failed to validate discount code: {result['status_code']} - {result['data']}")
            
        return success_count == 5

    def test_sponsor_zip_code_management(self):
        """Test sponsor management API with the new zip_code field"""
        self.log("=== Testing Sponsor Zip Code Management ===")
        success_count = 0
        
        # Test 1: Create Sponsor with Zip Code
        self.log("Test 1: Create Sponsor with Zip Code")
        test_sponsor_data = {
            "business_name": "Test Company",
            "email": "test123@example.com",
            "contact_name": "Test Contact",
            "phone": "480-555-1234",
            "website": "https://test.com",
            "zip_code": "85001",
            "package": "Silver Sponsor",
            "status": "active"
        }
        
        result = self.make_request("POST", "/sponsors", test_sponsor_data)
        if result["success"]:
            created_sponsor = result["data"]
            if created_sponsor.get("zip_code") == "85001":
                self.log(f"✅ POST /sponsors with zip_code successful - Created sponsor with zip_code: {created_sponsor.get('zip_code')}")
                self.test_data["zip_sponsor_id"] = created_sponsor["id"]
                success_count += 1
            else:
                self.log(f"❌ POST /sponsors - zip_code not saved correctly. Expected: 85001, Got: {created_sponsor.get('zip_code')}")
        else:
            self.log(f"❌ POST /sponsors with zip_code failed: {result['status_code']} - {result['data']}")
            
        # Test 2: Update Sponsor with Zip Code
        if "zip_sponsor_id" in self.test_data:
            self.log("Test 2: Update Sponsor with Zip Code")
            update_data = {"zip_code": "85701"}
            result = self.make_request("PUT", f"/sponsors/{self.test_data['zip_sponsor_id']}", update_data)
            if result["success"]:
                updated_sponsor = result["data"]
                if updated_sponsor.get("zip_code") == "85701":
                    self.log(f"✅ PUT /sponsors with zip_code successful - Updated zip_code to: {updated_sponsor.get('zip_code')}")
                    success_count += 1
                else:
                    self.log(f"❌ PUT /sponsors - zip_code not updated correctly. Expected: 85701, Got: {updated_sponsor.get('zip_code')}")
            else:
                self.log(f"❌ PUT /sponsors with zip_code failed: {result['status_code']} - {result['data']}")
                
        # Test 3: Get Sponsors - Verify zip_code field is included
        self.log("Test 3: Get Sponsors - Verify zip_code field")
        result = self.make_request("GET", "/sponsors")
        if result["success"]:
            sponsors = result["data"]
            zip_sponsor = None
            for sponsor in sponsors:
                if sponsor.get("id") == self.test_data.get("zip_sponsor_id"):
                    zip_sponsor = sponsor
                    break
            
            if zip_sponsor and zip_sponsor.get("zip_code") == "85701":
                self.log(f"✅ GET /sponsors includes zip_code field - Found zip_code: {zip_sponsor.get('zip_code')}")
                success_count += 1
            else:
                self.log(f"❌ GET /sponsors - zip_code field missing or incorrect in response")
        else:
            self.log(f"❌ GET /sponsors failed: {result['status_code']} - {result['data']}")
            
        # Test 4: Discount Validation (AZ Resident Flow)
        self.log("Test 4: Discount Validation (AZ Resident Flow)")
        
        # 4a: Create/Update registered account with zip code
        profile_data = {
            "business_name": "Test Company",
            "zip_code": "85001"
        }
        result = self.make_request("PUT", "/accounts/profile/test123@example.com", profile_data)
        if result["success"]:
            self.log(f"✅ PUT /accounts/profile with zip_code successful")
            
            # 4b: Validate discount code for AZ resident
            result = self.make_request("GET", "/payments/discount/validate", params={"code": "AZLOCAL25", "user_email": "test123@example.com"})
            if result["success"]:
                discount_data = result["data"]
                if discount_data.get("valid") == True:
                    self.log(f"✅ Discount validation successful for AZ zip code - valid={discount_data.get('valid')}")
                    success_count += 1
                else:
                    self.log(f"❌ Discount validation failed for AZ zip code: {discount_data}")
            else:
                self.log(f"❌ Discount validation failed: {result['status_code']} - {result['data']}")
        else:
            self.log(f"❌ Profile update with zip_code failed: {result['status_code']} - {result['data']}")
            
        # Test 5: View Profile functionality
        self.log("Test 5: View Profile zip status functionality")
        result = self.make_request("GET", "/accounts/profile/test123@example.com/zip-status")
        if result["success"]:
            zip_status = result["data"]
            expected_has_zip = True
            expected_is_az = True
            
            if (zip_status.get("has_zip_code") == expected_has_zip and 
                zip_status.get("is_az_resident") == expected_is_az):
                self.log(f"✅ Zip status check successful - has_zip_code={zip_status.get('has_zip_code')}, is_az_resident={zip_status.get('is_az_resident')}")
                success_count += 1
            else:
                self.log(f"❌ Zip status check failed - Expected: has_zip_code={expected_has_zip}, is_az_resident={expected_is_az}")
                self.log(f"   Got: has_zip_code={zip_status.get('has_zip_code')}, is_az_resident={zip_status.get('is_az_resident')}")
        else:
            self.log(f"❌ Zip status check failed: {result['status_code']} - {result['data']}")
            
        # Cleanup: Delete test sponsor
        if "zip_sponsor_id" in self.test_data:
            result = self.make_request("DELETE", f"/sponsors/{self.test_data['zip_sponsor_id']}")
            if result["success"]:
                self.log(f"✅ Test sponsor cleanup successful")
                del self.test_data["zip_sponsor_id"]
            else:
                self.log(f"❌ Test sponsor cleanup failed: {result['status_code']} - {result['data']}")
                
        return success_count == 5

    def run_all_tests(self):
        """Run all API tests"""
        self.log("🚀 Starting BIG Hat Sponsor Portal Backend API Tests")
        self.log(f"   API Base URL: {self.base_url}")
        
        test_results = {}
        
        # Test each API group
        test_results["init"] = self.test_init_api()
        test_results["sponsors"] = self.test_sponsors_api()
        test_results["sponsor_zip_code"] = self.test_sponsor_zip_code_management()
        test_results["locations"] = self.test_locations_api()
        test_results["accounts"] = self.test_accounts_api()
        test_results["assets"] = self.test_assets_api()
        test_results["subscriptions"] = self.test_subscriptions_api()
        test_results["canva"] = self.test_canva_api()
        test_results["placements"] = self.test_placements_api()
        test_results["stripe_checkout"] = self.test_stripe_checkout_session()
        
        # Cleanup
        self.cleanup_test_data()
        
        # Summary
        self.log("\n=== TEST SUMMARY ===")
        passed = sum(1 for result in test_results.values() if result)
        total = len(test_results)
        
        for api_name, result in test_results.items():
            status = "✅ PASSED" if result else "❌ FAILED"
            self.log(f"{api_name.upper()} API: {status}")
            
        self.log(f"\nOverall: {passed}/{total} API groups passed")
        
        if passed == total:
            self.log("🎉 ALL BACKEND API TESTS PASSED!")
            return True
        else:
            self.log("❌ SOME BACKEND API TESTS FAILED!")
            return False

    def run_login_profile_sync_tests(self):
        """Run only the login and profile sync tests"""
        self.log("🚀 Starting Login and Profile Sync Tests for BIG Hat Sponsor Portal")
        self.log(f"   API Base URL: {self.base_url}")
        
        # Initialize database first
        init_result = self.test_init_api()
        if not init_result:
            self.log("❌ Database initialization failed - cannot proceed with tests")
            return False
            
        # Run login and profile sync tests
        login_result = self.test_login_and_profile_sync()
        
        # Summary
        self.log("\n=== LOGIN AND PROFILE SYNC TEST SUMMARY ===")
        if login_result:
            self.log("🎉 ALL LOGIN AND PROFILE SYNC TESTS PASSED!")
            return True
        else:
            self.log("❌ LOGIN AND PROFILE SYNC TESTS FAILED!")
            return False


    def run_stripe_checkout_tests(self):
        """Run only the Stripe checkout session tests"""
        self.log("🚀 Starting Stripe Checkout Session Tests for BIG Hat Sponsor Portal")
        self.log(f"   API Base URL: {self.base_url}")
        
        # Initialize database first
        init_result = self.test_init_api()
        if not init_result:
            self.log("❌ Database initialization failed - cannot proceed with tests")
            return False
            
        # Run Stripe checkout tests
        stripe_result = self.test_stripe_checkout_session()
        
        # Summary
        self.log("\n=== STRIPE CHECKOUT SESSION TEST SUMMARY ===")
        if stripe_result:
            self.log("🎉 ALL STRIPE CHECKOUT SESSION TESTS PASSED!")
            return True
        else:
            self.log("❌ STRIPE CHECKOUT SESSION TESTS FAILED!")
            return False


    def run_zip_code_tests(self):
        """Run only the sponsor zip code management tests"""
        self.log("🚀 Starting Sponsor Zip Code Management Tests")
        self.log(f"   API Base URL: {self.base_url}")
        
        # Initialize database first
        init_result = self.test_init_api()
        if not init_result:
            self.log("❌ Database initialization failed - cannot proceed with tests")
            return False
            
        # Run zip code tests
        zip_result = self.test_sponsor_zip_code_management()
        
        # Summary
        self.log("\n=== SPONSOR ZIP CODE MANAGEMENT TEST SUMMARY ===")
        if zip_result:
            self.log("🎉 ALL SPONSOR ZIP CODE MANAGEMENT TESTS PASSED!")
            return True
        else:
            self.log("❌ SPONSOR ZIP CODE MANAGEMENT TESTS FAILED!")
            return False

    def test_alacarte_discount_validation(self):
        """Test discount code validation for à la carte items - specifically the 99-SPONSOR-99 code"""
        self.log("=== Testing À La Carte Discount Code Validation ===")
        success_count = 0
        
        # Test 1: Test the "99-SPONSOR-99" code for Prize Sponsor (should work)
        self.log("Test 1: Testing '99-SPONSOR-99' code for Prize Sponsor")
        result = self.make_request("GET", "/payments/discount/validate", params={
            "code": "99-SPONSOR-99",
            "package_id": "alacarte-prize-sponsor"
        })
        
        if result["success"]:
            discount_data = result["data"]
            expected_valid = True
            expected_type = "fixed_price"
            expected_value = 1.0
            expected_restricted_to = ["alacarte-prize-sponsor"]
            expected_description = "Test Purchase - Prize Sponsor $1"
            
            if (discount_data.get("valid") == expected_valid and
                discount_data.get("type") == expected_type and
                discount_data.get("value") == expected_value and
                discount_data.get("restricted_to") == expected_restricted_to and
                discount_data.get("description") == expected_description):
                self.log(f"✅ '99-SPONSOR-99' code validation for Prize Sponsor PASSED")
                self.log(f"   valid={discount_data.get('valid')}, type={discount_data.get('type')}, value={discount_data.get('value')}")
                self.log(f"   restricted_to={discount_data.get('restricted_to')}, description='{discount_data.get('description')}'")
                success_count += 1
            else:
                self.log(f"❌ '99-SPONSOR-99' code validation for Prize Sponsor FAILED")
                self.log(f"   Expected: valid={expected_valid}, type={expected_type}, value={expected_value}")
                self.log(f"   Got: valid={discount_data.get('valid')}, type={discount_data.get('type')}, value={discount_data.get('value')}")
        else:
            self.log(f"❌ '99-SPONSOR-99' code validation for Prize Sponsor FAILED: {result['status_code']} - {result['data']}")
            
        # Test 2: Test the "99-SPONSOR-99" code WITHOUT Prize Sponsor (should fail)
        self.log("Test 2: Testing '99-SPONSOR-99' code for Gold package (should fail)")
        result = self.make_request("GET", "/payments/discount/validate", params={
            "code": "99-SPONSOR-99",
            "package_id": "gold"
        })
        
        if result["success"]:
            discount_data = result["data"]
            expected_valid = False
            expected_message = "This discount code is only valid for Prize Sponsor purchases."
            
            if (discount_data.get("valid") == expected_valid and
                expected_message in discount_data.get("message", "")):
                self.log(f"✅ '99-SPONSOR-99' code validation for Gold package correctly FAILED")
                self.log(f"   valid={discount_data.get('valid')}, message='{discount_data.get('message')}'")
                success_count += 1
            else:
                self.log(f"❌ '99-SPONSOR-99' code validation for Gold package should have failed but didn't")
                self.log(f"   Expected: valid={expected_valid}, message containing '{expected_message}'")
                self.log(f"   Got: valid={discount_data.get('valid')}, message='{discount_data.get('message')}'")
        else:
            self.log(f"❌ '99-SPONSOR-99' code validation for Gold package request failed: {result['status_code']} - {result['data']}")
            
        # Test 3: Test a regular package discount code for à la carte (should work for general codes)
        self.log("Test 3: Testing 'WELCOME10' code (general discount)")
        result = self.make_request("GET", "/payments/discount/validate", params={
            "code": "WELCOME10"
        })
        
        if result["success"]:
            discount_data = result["data"]
            expected_valid = True
            expected_type = "percent"
            expected_value = 10
            
            if (discount_data.get("valid") == expected_valid and
                discount_data.get("type") == expected_type and
                discount_data.get("value") == expected_value):
                self.log(f"✅ 'WELCOME10' code validation PASSED")
                self.log(f"   valid={discount_data.get('valid')}, type={discount_data.get('type')}, value={discount_data.get('value')}%")
                success_count += 1
            else:
                self.log(f"❌ 'WELCOME10' code validation FAILED")
                self.log(f"   Expected: valid={expected_valid}, type={expected_type}, value={expected_value}")
                self.log(f"   Got: valid={discount_data.get('valid')}, type={discount_data.get('type')}, value={discount_data.get('value')}")
        else:
            self.log(f"❌ 'WELCOME10' code validation FAILED: {result['status_code']} - {result['data']}")
            
        return success_count == 3

    def run_alacarte_discount_tests(self):
        """Run only the à la carte discount validation tests"""
        self.log("🚀 Starting À La Carte Discount Code Validation Tests")
        self.log(f"   API Base URL: {self.base_url}")
        
        # Initialize database first
        init_result = self.test_init_api()
        if not init_result:
            self.log("❌ Database initialization failed - cannot proceed with tests")
            return False
            
        # Run discount validation tests
        discount_result = self.test_alacarte_discount_validation()
        
        # Summary
        self.log("\n=== À LA CARTE DISCOUNT CODE VALIDATION TEST SUMMARY ===")
        if discount_result:
            self.log("🎉 ALL À LA CARTE DISCOUNT CODE VALIDATION TESTS PASSED!")
            return True
        else:
            self.log("❌ À LA CARTE DISCOUNT CODE VALIDATION TESTS FAILED!")
            return False

    def test_checkout_flow_scenarios(self):
        """Test the complete checkout flow for sponsorship purchases as specified in review request"""
        self.log("=== Testing Complete Checkout Flow Scenarios ===")
        success_count = 0
        
        # SCENARIO 1: Gold Package Purchase (No Discount)
        self.log("SCENARIO 1: Gold Package Purchase (No Discount)")
        scenario1_data = {
            "package_id": "gold",
            "origin_url": "https://sponsor.bighat.live",
            "user_email": "nicksellards@yahoo.com"
        }
        
        result = self.make_request("POST", "/payments/checkout/session", scenario1_data)
        if result["success"]:
            response_data = result["data"]
            if "url" in response_data and "session_id" in response_data:
                session_id = response_data["session_id"]
                checkout_url = response_data["url"]
                
                # Verify session_id format (should start with "cs_")
                if session_id.startswith("cs_") and "checkout.stripe.com" in checkout_url:
                    self.log(f"✅ SCENARIO 1 PASSED - Gold package checkout session created")
                    self.log(f"   Session ID: {session_id}")
                    self.log(f"   Checkout URL: {checkout_url}")
                    success_count += 1
                else:
                    self.log(f"❌ SCENARIO 1 FAILED - Invalid session format or URL")
            else:
                self.log(f"❌ SCENARIO 1 FAILED - Missing required fields: {response_data}")
        else:
            self.log(f"❌ SCENARIO 1 FAILED: {result['status_code']} - {result['data']}")
        
        # SCENARIO 2: À La Carte Prize Sponsor with 99-SPONSOR-99 Discount
        self.log("SCENARIO 2: À La Carte Prize Sponsor with 99-SPONSOR-99 Discount")
        scenario2_data = {
            "package_id": "alacarte-prize-sponsor",
            "origin_url": "https://sponsor.bighat.live",
            "user_email": "nicksellards@yahoo.com",
            "discount_code": "99-SPONSOR-99"
        }
        
        result = self.make_request("POST", "/payments/checkout/session", scenario2_data)
        if result["success"]:
            response_data = result["data"]
            if "url" in response_data and "session_id" in response_data:
                session_id = response_data["session_id"]
                checkout_url = response_data["url"]
                
                # Verify session_id format and URL
                if session_id.startswith("cs_") and "checkout.stripe.com" in checkout_url:
                    self.log(f"✅ SCENARIO 2 PASSED - Prize Sponsor with discount checkout session created")
                    self.log(f"   Session ID: {session_id}")
                    self.log(f"   Checkout URL: {checkout_url}")
                    success_count += 1
                else:
                    self.log(f"❌ SCENARIO 2 FAILED - Invalid session format or URL")
            else:
                self.log(f"❌ SCENARIO 2 FAILED - Missing required fields: {response_data}")
        else:
            self.log(f"❌ SCENARIO 2 FAILED: {result['status_code']} - {result['data']}")
        
        # SCENARIO 3: Invalid Discount Code Usage (99-SPONSOR-99 with Gold package)
        self.log("SCENARIO 3: Invalid Discount Code Usage (99-SPONSOR-99 with Gold package)")
        scenario3_data = {
            "package_id": "gold",
            "origin_url": "https://sponsor.bighat.live",
            "user_email": "nicksellards@yahoo.com",
            "discount_code": "99-SPONSOR-99"
        }
        
        result = self.make_request("POST", "/payments/checkout/session", scenario3_data)
        if result["status_code"] == 400:
            error_data = result["data"]
            expected_error_msg = "Discount code '99-SPONSOR-99' is only valid for: alacarte-prize-sponsor"
            
            if "detail" in error_data and expected_error_msg in error_data["detail"]:
                self.log(f"✅ SCENARIO 3 PASSED - Correctly rejected invalid discount code usage")
                self.log(f"   Error message: {error_data['detail']}")
                success_count += 1
            else:
                self.log(f"❌ SCENARIO 3 FAILED - Wrong error message: {error_data}")
        else:
            self.log(f"❌ SCENARIO 3 FAILED - Expected 400 error, got {result['status_code']}: {result['data']}")
        
        return success_count == 3

    def run_checkout_flow_tests(self):
        """Run only the checkout flow scenario tests"""
        self.log("🚀 Starting Complete Checkout Flow Tests")
        self.log(f"   API Base URL: {self.base_url}")
        
        # Initialize database first
        init_result = self.test_init_api()
        if not init_result:
            self.log("❌ Database initialization failed - cannot proceed with tests")
            return False
            
        # Run checkout flow tests
        checkout_result = self.test_checkout_flow_scenarios()
        
        # Summary
        self.log("\n=== COMPLETE CHECKOUT FLOW TEST SUMMARY ===")
        if checkout_result:
            self.log("🎉 ALL CHECKOUT FLOW SCENARIO TESTS PASSED!")
            return True
        else:
            self.log("❌ CHECKOUT FLOW SCENARIO TESTS FAILED!")
            return False

    def test_high_traffic_protection(self):
        """Test high-traffic protection features: health check, timeout middleware, and normal flow"""
        self.log("=== Testing High-Traffic Protection Features ===")
        success_count = 0
        
        # Test 1: Health Check Endpoint
        self.log("Test 1: Health Check Endpoint (GET /api/health)")
        result = self.make_request("GET", "/health")
        
        if result["success"]:
            health_data = result["data"]
            required_fields = ["status", "api", "database", "timestamp"]
            
            if all(field in health_data for field in required_fields):
                expected_status = "healthy"
                expected_api = "up"
                expected_database = "connected"
                
                if (health_data.get("status") == expected_status and
                    health_data.get("api") == expected_api and
                    health_data.get("database") == expected_database):
                    self.log(f"✅ Health check PASSED")
                    self.log(f"   Status: {health_data.get('status')}")
                    self.log(f"   API: {health_data.get('api')}")
                    self.log(f"   Database: {health_data.get('database')}")
                    self.log(f"   Timestamp: {health_data.get('timestamp')}")
                    success_count += 1
                else:
                    self.log(f"❌ Health check FAILED - Unexpected values")
                    self.log(f"   Expected: status={expected_status}, api={expected_api}, database={expected_database}")
                    self.log(f"   Got: status={health_data.get('status')}, api={health_data.get('api')}, database={health_data.get('database')}")
            else:
                self.log(f"❌ Health check FAILED - Missing required fields")
                self.log(f"   Required: {required_fields}")
                self.log(f"   Got: {list(health_data.keys())}")
        else:
            self.log(f"❌ Health check FAILED: {result['status_code']} - {result['data']}")
        
        # Test 2: Request Timeout Test (verify normal requests complete within timeout)
        self.log("Test 2: Request Timeout Test - Normal request should complete within timeout")
        import time
        start_time = time.time()
        
        # Make a normal request that should complete quickly
        result = self.make_request("GET", "/")
        end_time = time.time()
        request_duration = end_time - start_time
        
        if result["success"]:
            # Verify request completed within reasonable time (much less than 30s timeout)
            if request_duration < 10.0:  # Should complete in under 10 seconds
                self.log(f"✅ Request timeout test PASSED - Request completed in {request_duration:.2f}s")
                success_count += 1
            else:
                self.log(f"❌ Request timeout test FAILED - Request took too long: {request_duration:.2f}s")
        else:
            self.log(f"❌ Request timeout test FAILED: {result['status_code']} - {result['data']}")
        
        # Test 3: Normal Flow Test - Create account, login, verify login returns user data
        self.log("Test 3: Normal Flow Test - Create account, login, verify user data")
        
        # 3a: Create a test account
        test_email = f"hightraffic_test_{int(time.time())}@test.com"
        test_password = "TestPass123!"
        test_account_data = {
            "email": test_email,
            "name": "High Traffic Test User",
            "business_name": "High Traffic Test Business",
            "phone": "480-555-9999",
            "password_hash": test_password  # Will be hashed by the API
        }
        
        result = self.make_request("POST", "/accounts", test_account_data)
        if result["success"]:
            created_account = result["data"]
            self.log(f"✅ Account creation PASSED - Created account: {created_account.get('email')}")
            self.test_data["high_traffic_account_id"] = created_account.get("id")
            
            # 3b: Login with the created account
            result = self.make_request("POST", "/accounts/login", params={
                "email": test_email,
                "password": test_password
            })
            
            if result["success"]:
                login_data = result["data"]
                required_login_fields = ["email", "business_name"]
                
                if all(field in login_data for field in required_login_fields):
                    if login_data.get("email") == test_email.lower():
                        self.log(f"✅ Login PASSED - User data returned correctly")
                        self.log(f"   Email: {login_data.get('email')}")
                        self.log(f"   Business Name: {login_data.get('business_name')}")
                        self.log(f"   Sponsor ID: {login_data.get('sponsor_id', 'None')}")
                        success_count += 1
                    else:
                        self.log(f"❌ Login FAILED - Wrong email returned: {login_data.get('email')}")
                else:
                    self.log(f"❌ Login FAILED - Missing required fields: {required_login_fields}")
                    self.log(f"   Got fields: {list(login_data.keys())}")
            else:
                self.log(f"❌ Login FAILED: {result['status_code']} - {result['data']}")
        else:
            self.log(f"❌ Account creation FAILED: {result['status_code']} - {result['data']}")
        
        # Cleanup: Delete test account if created
        if "high_traffic_account_id" in self.test_data:
            # Note: There's no DELETE endpoint for accounts in the current API
            # So we'll just log that cleanup would be needed
            self.log(f"Note: Test account {test_email} created - manual cleanup may be needed")
            del self.test_data["high_traffic_account_id"]
        
        return success_count == 3

    def run_high_traffic_protection_tests(self):
        """Run only the high-traffic protection tests"""
        self.log("🚀 Starting High-Traffic Protection Tests")
        self.log(f"   API Base URL: {self.base_url}")
        
        # Initialize database first
        init_result = self.test_init_api()
        if not init_result:
            self.log("❌ Database initialization failed - cannot proceed with tests")
            return False
            
        # Run high-traffic protection tests
        protection_result = self.test_high_traffic_protection()
        
        # Summary
        self.log("\n=== HIGH-TRAFFIC PROTECTION TEST SUMMARY ===")
        if protection_result:
            self.log("🎉 ALL HIGH-TRAFFIC PROTECTION TESTS PASSED!")
            return True
        else:
            self.log("❌ HIGH-TRAFFIC PROTECTION TESTS FAILED!")
            return False


def main():
    """Main test execution"""
    tester = APITester(API_BASE_URL)
    
    # Check if we should run specific tests
    if len(sys.argv) > 1:
        if sys.argv[1] == "--login-only":
            success = tester.run_login_profile_sync_tests()
        elif sys.argv[1] == "--stripe-only":
            success = tester.run_stripe_checkout_tests()
        elif sys.argv[1] == "--zip-only":
            success = tester.run_zip_code_tests()
        elif sys.argv[1] == "--discount-only":
            success = tester.run_alacarte_discount_tests()
        elif sys.argv[1] == "--high-traffic-only":
            success = tester.run_high_traffic_protection_tests()
        else:
            success = tester.run_all_tests()
    else:
        success = tester.run_all_tests()
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()