#!/usr/bin/env python3
"""
BIG Hat Standalone — Native Mode Backend Testing
Tests all 27 scenarios for Phases 0, 0.5, 1 as specified in the review request.
"""

import requests
import sys
import json
from datetime import datetime
from pathlib import Path

class NativeBackendTester:
    def __init__(self, base_url="https://standalone-tools.preview.emergentagent.com"):
        self.base_url = base_url
        self.token = None
        self.cookies = None
        self.tests_run = 0
        self.tests_passed = 0
        self.failed_tests = []
        self.test_results = {}
        
    def log(self, message, level="INFO"):
        """Log a message with timestamp"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {level}: {message}")
    
    def run_test(self, test_num, name, method, endpoint, expected_status, data=None, 
                 auth_required=False, params=None, validate_response=None):
        """Run a single API test with detailed logging"""
        url = f"{self.base_url}/api/{endpoint}"
        headers = {'Content-Type': 'application/json'}
        
        if auth_required and self.token:
            headers['Authorization'] = f'Bearer {self.token}'

        self.tests_run += 1
        self.log(f"Test #{test_num}: {name}")
        self.log(f"  → {method} {url}", "DEBUG")
        
        try:
            kwargs = {'headers': headers, 'cookies': self.cookies}
            if data:
                kwargs['json'] = data
            if params:
                kwargs['params'] = params
                
            if method == 'GET':
                response = requests.get(url, **kwargs)
            elif method == 'POST':
                response = requests.post(url, **kwargs)
            elif method == 'PUT':
                response = requests.put(url, **kwargs)
            elif method == 'DELETE':
                response = requests.delete(url, **kwargs)
            else:
                raise ValueError(f"Unsupported method: {method}")

            # Check status code
            status_match = response.status_code == expected_status
            
            # Parse response
            try:
                response_data = response.json() if response.content else {}
            except:
                response_data = {"raw": response.text}
            
            # Custom validation
            validation_passed = True
            validation_msg = ""
            if validate_response and status_match:
                validation_passed, validation_msg = validate_response(response_data)
            
            success = status_match and validation_passed
            
            if success:
                self.tests_passed += 1
                self.log(f"  ✅ PASSED (status={response.status_code})", "PASS")
                if validation_msg:
                    self.log(f"     {validation_msg}", "INFO")
            else:
                if not status_match:
                    self.log(f"  ❌ FAILED: Expected status {expected_status}, got {response.status_code}", "FAIL")
                else:
                    self.log(f"  ❌ FAILED: {validation_msg}", "FAIL")
                    
                self.log(f"     Response: {json.dumps(response_data, indent=2)[:500]}", "DEBUG")
                
                self.failed_tests.append({
                    "test_num": test_num,
                    "name": name,
                    "expected_status": expected_status,
                    "actual_status": response.status_code,
                    "endpoint": endpoint,
                    "validation_msg": validation_msg if not status_match else None,
                    "response": response_data
                })
            
            self.test_results[test_num] = {
                "name": name,
                "passed": success,
                "status": response.status_code,
                "response": response_data
            }
            
            return success, response_data

        except Exception as e:
            self.log(f"  ❌ EXCEPTION: {str(e)}", "ERROR")
            self.failed_tests.append({
                "test_num": test_num,
                "name": name,
                "error": str(e),
                "endpoint": endpoint
            })
            self.test_results[test_num] = {
                "name": name,
                "passed": False,
                "error": str(e)
            }
            return False, {}

    # ========== A. Native Module Endpoints ==========
    
    def test_01_native_info(self):
        """Test #1: GET /api/native/info"""
        def validate(data):
            checks = []
            checks.append(("native_mode", data.get("native_mode") == True))
            checks.append(("setup_complete", data.get("setup_complete") == True))
            checks.append(("license.is_active", data.get("license", {}).get("is_active") == True))
            checks.append(("license.used_seats >= 1", data.get("license", {}).get("used_seats", 0) >= 1))
            checks.append(("license.total_seats_allowed", data.get("license", {}).get("total_seats_allowed") == 5))
            checks.append(("current_hwid exists", len(data.get("current_hwid", "")) == 64))
            checks.append(("instance_id exists", len(data.get("instance_id", "")) > 0))
            
            failed = [name for name, result in checks if not result]
            if failed:
                return False, f"Validation failed: {', '.join(failed)}"
            return True, f"All fields validated: native_mode=true, setup_complete=true, license active, {data.get('license', {}).get('used_seats')} seats used"
        
        return self.run_test(1, "GET /api/native/info", "GET", "native/info", 200, 
                            auth_required=False, validate_response=validate)
    
    def test_02_native_hwid(self):
        """Test #2: GET /api/native/hwid"""
        def validate(data):
            hwid = data.get("hwid", "")
            if len(hwid) != 64:
                return False, f"HWID length is {len(hwid)}, expected 64"
            return True, f"HWID: {hwid[:16]}...{hwid[-16:]}"
        
        return self.run_test(2, "GET /api/native/hwid", "GET", "native/hwid", 200,
                            auth_required=False, validate_response=validate)
    
    def test_03_setup_status(self):
        """Test #3: GET /api/native/setup/status"""
        def validate(data):
            if data.get("setup_complete") != True:
                return False, "setup_complete should be true"
            return True, "Setup is complete"
        
        return self.run_test(3, "GET /api/native/setup/status", "GET", "native/setup/status", 200,
                            auth_required=False, validate_response=validate)
    
    def test_04_setup_initialize_409(self):
        """Test #4: POST /api/native/setup/initialize (should return 409 when already complete)"""
        payload = {
            "license_key": "BHE-TEST-1234-ABCD-WXYZ",
            "master_admin": {
                "email": "test@bighat.local",
                "password": "TestPass123",
                "first_name": "Test",
                "last_name": "User"
            },
            "settings": {
                "location_name": "Test Location",
                "city": "Phoenix",
                "state": "AZ",
                "trivia_source": "local"
            }
        }
        
        def validate(data):
            detail = data.get("detail", "")
            if "setup_already_complete" in detail:
                return True, "Correctly returned setup_already_complete"
            return False, f"Expected 'setup_already_complete', got: {detail}"
        
        return self.run_test(4, "POST /api/native/setup/initialize (409 when complete)", 
                            "POST", "native/setup/initialize", 409, data=payload,
                            auth_required=False, validate_response=validate)
    
    def test_05_get_license(self):
        """Test #5: GET /api/native/license"""
        def validate(data):
            checks = []
            checks.append(("is_active", data.get("is_active") == True))
            checks.append(("used_seats", data.get("used_seats", 0) >= 1))
            checks.append(("total_seats_allowed", data.get("total_seats_allowed") == 5))
            checks.append(("current_hwid_registered", data.get("current_hwid_registered") == True))
            
            failed = [name for name, result in checks if not result]
            if failed:
                return False, f"Validation failed: {', '.join(failed)}"
            
            key_masked = data.get("key_masked", "")
            return True, f"License active, {data.get('used_seats')}/{data.get('total_seats_allowed')} seats, key={key_masked}"
        
        return self.run_test(5, "GET /api/native/license", "GET", "native/license", 200,
                            auth_required=False, validate_response=validate)
    
    def test_06_register_seat(self):
        """Test #6: POST /api/native/license/seat/register (idempotent)"""
        payload = {"label": "test seat"}
        
        def validate(data):
            msg = data.get("message", "")
            if "seat_already_registered" in msg or "seat_registered" in msg:
                return True, f"Seat registration: {msg}"
            return False, f"Unexpected message: {msg}"
        
        return self.run_test(6, "POST /api/native/license/seat/register (idempotent)",
                            "POST", "native/license/seat/register", 200, data=payload,
                            auth_required=False, validate_response=validate)
    
    def test_07_get_subscription(self):
        """Test #7: GET /api/native/subscription"""
        def validate(data):
            # Just check it returns subscription data
            if "active" not in data or "tier" not in data:
                return False, "Missing subscription fields"
            return True, f"Subscription: active={data.get('active')}, tier={data.get('tier')}"
        
        return self.run_test(7, "GET /api/native/subscription", "GET", "native/subscription", 200,
                            auth_required=False, validate_response=validate)
    
    def test_08_activate_subscription(self):
        """Test #8: POST /api/native/subscription (activate premium)"""
        payload = {
            "active": True,
            "tier": "premium",
            "expires_at": "2027-01-01T00:00:00Z"
        }
        
        def validate(data):
            sub = data.get("subscription", {})
            checks = []
            checks.append(("active", sub.get("active") == True))
            checks.append(("tier", sub.get("tier") == "premium"))
            checks.append(("sharepoint_enabled", sub.get("sharepoint_enabled") == True))
            checks.append(("story_generator_enabled", sub.get("story_generator_enabled") == True))
            checks.append(("cloud_sync_enabled", sub.get("cloud_sync_enabled") == True))
            
            failed = [name for name, result in checks if not result]
            if failed:
                return False, f"Premium flags not set: {', '.join(failed)}"
            return True, "All 3 premium flags enabled"
        
        return self.run_test(8, "POST /api/native/subscription (activate premium)",
                            "POST", "native/subscription", 200, data=payload,
                            auth_required=False, validate_response=validate)
    
    def test_09_deactivate_subscription(self):
        """Test #9: POST /api/native/subscription (deactivate)"""
        payload = {
            "active": False,
            "tier": "free"
        }
        
        def validate(data):
            sub = data.get("subscription", {})
            checks = []
            checks.append(("active", sub.get("active") == False))
            checks.append(("sharepoint_enabled", sub.get("sharepoint_enabled") == False))
            checks.append(("story_generator_enabled", sub.get("story_generator_enabled") == False))
            checks.append(("cloud_sync_enabled", sub.get("cloud_sync_enabled") == False))
            
            failed = [name for name, result in checks if not result]
            if failed:
                return False, f"Premium flags not cleared: {', '.join(failed)}"
            return True, "All 3 premium flags disabled"
        
        return self.run_test(9, "POST /api/native/subscription (deactivate)",
                            "POST", "native/subscription", 200, data=payload,
                            auth_required=False, validate_response=validate)
    
    def test_10_setup_initialize_bad_license(self):
        """Test #10: POST /api/native/setup/initialize with bad license format"""
        payload = {
            "license_key": "NOT-VALID",
            "master_admin": {
                "email": "test@bighat.local",
                "password": "TestPass123",
                "first_name": "Test",
                "last_name": "User"
            },
            "settings": {
                "location_name": "Test Location"
            }
        }
        
        # Should return 409 (setup already complete) OR 400 (bad license)
        # Since setup is complete, we expect 409
        def validate(data):
            detail = data.get("detail", "")
            if "setup_already_complete" in detail:
                return True, "Correctly blocked (setup already complete)"
            elif "invalid_license" in detail:
                return True, "Correctly rejected bad license format"
            return False, f"Unexpected error: {detail}"
        
        # Accept either 400 or 409
        success_400, data_400 = self.run_test(10, "POST /api/native/setup/initialize (bad license)",
                            "POST", "native/setup/initialize", 400, data=payload,
                            auth_required=False, validate_response=validate)
        
        if not success_400:
            # Try 409
            success_409, data_409 = self.run_test(10, "POST /api/native/setup/initialize (bad license, expect 409)",
                                "POST", "native/setup/initialize", 409, data=payload,
                                auth_required=False, validate_response=validate)
            return success_409, data_409
        
        return success_400, data_400
    
    def test_11_setup_reset_wrong_confirm(self):
        """Test #11: POST /api/native/setup/reset with wrong confirm"""
        def validate(data):
            detail = data.get("detail", "")
            if "confirmation_required" in detail:
                return True, "Correctly rejected wrong confirmation"
            return False, f"Unexpected error: {detail}"
        
        return self.run_test(11, "POST /api/native/setup/reset (wrong confirm)",
                            "POST", "native/setup/reset", 400, params={"confirm": "WRONG"},
                            auth_required=False, validate_response=validate)
    
    # ========== B. Native Auth Bridge ==========
    
    def test_12_login_master_admin(self):
        """Test #12: POST /api/auth/login (master admin)"""
        payload = {
            "email": "master@bighat.local",
            "password": "BigHat2024!"
        }
        
        def validate(data):
            checks = []
            checks.append(("id exists", "id" in data))
            checks.append(("email", data.get("email") == "master@bighat.local"))
            checks.append(("role", data.get("role") == "master_admin"))
            checks.append(("token exists", "token" in data and len(data.get("token", "")) > 0))
            
            failed = [name for name, result in checks if not result]
            if failed:
                return False, f"Validation failed: {', '.join(failed)}"
            
            # Store token for subsequent tests
            self.token = data.get("token")
            return True, f"Logged in as {data.get('name')} (role={data.get('role')})"
        
        return self.run_test(12, "POST /api/auth/login (master admin)",
                            "POST", "auth/login", 200, data=payload,
                            auth_required=False, validate_response=validate)
    
    def test_13_login_wrong_password(self):
        """Test #13: POST /api/auth/login (wrong password)"""
        payload = {
            "email": "master@bighat.local",
            "password": "WrongPassword123"
        }
        
        def validate(data):
            detail = data.get("detail", "")
            if "Invalid email or password" in detail:
                return True, "Correctly rejected wrong password"
            return False, f"Unexpected error: {detail}"
        
        return self.run_test(13, "POST /api/auth/login (wrong password)",
                            "POST", "auth/login", 401, data=payload,
                            auth_required=False, validate_response=validate)
    
    def test_14_login_unknown_email(self):
        """Test #14: POST /api/auth/login (unknown email)"""
        payload = {
            "email": "nobody@nowhere.local",
            "password": "SomePassword123"
        }
        
        def validate(data):
            detail = data.get("detail", "")
            if "Invalid email or password" in detail:
                return True, "Correctly rejected unknown email"
            return False, f"Unexpected error: {detail}"
        
        return self.run_test(14, "POST /api/auth/login (unknown email)",
                            "POST", "auth/login", 401, data=payload,
                            auth_required=False, validate_response=validate)
    
    def test_15_auth_me_with_token(self):
        """Test #15: GET /api/auth/me (with token)"""
        def validate(data):
            checks = []
            checks.append(("id exists", "id" in data))
            checks.append(("email", data.get("email") == "master@bighat.local"))
            checks.append(("role", data.get("role") == "master_admin"))
            checks.append(("name", data.get("name") == "Master Admin"))
            
            failed = [name for name, result in checks if not result]
            if failed:
                return False, f"Validation failed: {', '.join(failed)}"
            return True, f"User: {data.get('name')} ({data.get('role')})"
        
        return self.run_test(15, "GET /api/auth/me (with token)",
                            "GET", "auth/me", 200, auth_required=True,
                            validate_response=validate)
    
    def test_16_auth_me_no_token(self):
        """Test #16: GET /api/auth/me (no token)"""
        # Temporarily remove token
        temp_token = self.token
        self.token = None
        
        def validate(data):
            detail = data.get("detail", "")
            if "Not authenticated" in detail or "authenticated" in detail.lower():
                return True, "Correctly rejected request without token"
            return False, f"Unexpected error: {detail}"
        
        success, data = self.run_test(16, "GET /api/auth/me (no token)",
                            "GET", "auth/me", 401, auth_required=False,
                            validate_response=validate)
        
        # Restore token
        self.token = temp_token
        return success, data
    
    # ========== C. SQLite-backed Schedule CRUD ==========
    
    def test_17_get_venues(self):
        """Test #17: GET /api/venues (should return ≥6)"""
        def validate(data):
            if not isinstance(data, list):
                return False, "Response is not a list"
            if len(data) < 6:
                return False, f"Expected ≥6 venues, got {len(data)}"
            return True, f"Found {len(data)} venues (auto-seeded)"
        
        return self.run_test(17, "GET /api/venues (≥6 venues)",
                            "GET", "venues", 200, auth_required=False,
                            validate_response=validate)
    
    def test_18_get_events(self):
        """Test #18: GET /api/events (should return ≥20)"""
        def validate(data):
            if not isinstance(data, list):
                return False, "Response is not a list"
            if len(data) < 20:
                return False, f"Expected ≥20 events, got {len(data)}"
            return True, f"Found {len(data)} events (auto-seeded)"
        
        return self.run_test(18, "GET /api/events (≥20 events)",
                            "GET", "events", 200, auth_required=False,
                            validate_response=validate)
    
    def test_19_create_event(self):
        """Test #19: POST /api/events (create new event)"""
        payload = {
            "title": "Phase1 SQLite Verify",
            "event_type": "trivia",
            "venue_id": "venue-taphouse",
            "date": "2026-09-15T19:00:00Z",
            "duration_hours": 2.0
        }
        
        def validate(data):
            checks = []
            checks.append(("id exists", "id" in data and len(data.get("id", "")) > 0))
            checks.append(("title", data.get("title") == "Phase1 SQLite Verify"))
            checks.append(("event_type", data.get("event_type") == "trivia"))
            checks.append(("venue_id", data.get("venue_id") == "venue-taphouse"))
            
            # Check that id is a string UUID, not ObjectId hex
            event_id = data.get("id", "")
            if len(event_id) == 24 and all(c in "0123456789abcdef" for c in event_id.lower()):
                return False, "Event ID looks like ObjectId hex (should be UUID string)"
            
            failed = [name for name, result in checks if not result]
            if failed:
                return False, f"Validation failed: {', '.join(failed)}"
            
            # Store event ID for subsequent tests
            self.created_event_id = data.get("id")
            return True, f"Created event with ID: {event_id}"
        
        return self.run_test(19, "POST /api/events (create event)",
                            "POST", "events", 200, data=payload, auth_required=True,
                            validate_response=validate)
    
    def test_20_get_events_by_date(self):
        """Test #20: GET /api/events?event_date=2026-09-15 (find created event)"""
        # Note: The API uses 'include_past' param, not 'event_date'
        # Let's just get all events and check if our created event is there
        def validate(data):
            if not isinstance(data, list):
                return False, "Response is not a list"
            
            # Look for our created event
            created_id = getattr(self, 'created_event_id', None)
            if not created_id:
                return False, "No created event ID stored from test #19"
            
            found = any(e.get("id") == created_id for e in data)
            if not found:
                return False, f"Created event {created_id} not found in events list"
            
            return True, f"Found created event {created_id} in events list"
        
        return self.run_test(20, "GET /api/events (verify created event exists)",
                            "GET", "events", 200, params={"include_past": "true"},
                            auth_required=False, validate_response=validate)
    
    def test_21_update_event(self):
        """Test #21: PUT /api/events/<id> (update status to confirmed)"""
        created_id = getattr(self, 'created_event_id', None)
        if not created_id:
            self.log("  ⚠️  Skipping: No created event ID from test #19", "WARN")
            return False, {}
        
        payload = {"status": "confirmed"}
        
        def validate(data):
            if data.get("status") != "confirmed":
                return False, f"Status is {data.get('status')}, expected 'confirmed'"
            return True, f"Event status updated to 'confirmed'"
        
        return self.run_test(21, f"PUT /api/events/{created_id} (update status)",
                            "PUT", f"events/{created_id}", 200, data=payload,
                            auth_required=True, validate_response=validate)
    
    def test_22_delete_event(self):
        """Test #22: DELETE /api/events/<id>"""
        created_id = getattr(self, 'created_event_id', None)
        if not created_id:
            self.log("  ⚠️  Skipping: No created event ID from test #19", "WARN")
            return False, {}
        
        def validate(data):
            if data.get("success") != True:
                return False, f"Delete failed: {data}"
            return True, "Event deleted successfully"
        
        return self.run_test(22, f"DELETE /api/events/{created_id}",
                            "DELETE", f"events/{created_id}", 200,
                            auth_required=True, validate_response=validate)
    
    def test_23_verify_event_deleted(self):
        """Test #23: GET /api/events (verify event is gone)"""
        created_id = getattr(self, 'created_event_id', None)
        if not created_id:
            self.log("  ⚠️  Skipping: No created event ID from test #19", "WARN")
            return False, {}
        
        def validate(data):
            if not isinstance(data, list):
                return False, "Response is not a list"
            
            found = any(e.get("id") == created_id for e in data)
            if found:
                return False, f"Deleted event {created_id} still exists in events list"
            
            return True, f"Confirmed event {created_id} was deleted"
        
        return self.run_test(23, "GET /api/events (verify deletion)",
                            "GET", "events", 200, params={"include_past": "true"},
                            auth_required=False, validate_response=validate)
    
    # ========== D. Regression Tests ==========
    
    def test_24_health_check(self):
        """Test #24: GET /health"""
        return self.run_test(24, "GET /health (regression check)",
                            "GET", "../health", 200, auth_required=False)
    
    def test_25_sqlite_files_exist(self):
        """Test #25: Verify SQLite files exist on disk"""
        self.tests_run += 1
        self.log("Test #25: Verify SQLite files on disk")
        
        sqlite_dir = Path("/app/backend/native/data/bighat_db/test_database")
        
        if not sqlite_dir.exists():
            self.log(f"  ❌ FAILED: SQLite directory does not exist: {sqlite_dir}", "FAIL")
            self.failed_tests.append({
                "test_num": 25,
                "name": "SQLite files exist",
                "error": f"Directory not found: {sqlite_dir}"
            })
            self.test_results[25] = {"name": "SQLite files exist", "passed": False}
            return False, {}
        
        # Look for .collection files
        collection_files = list(sqlite_dir.glob("*.collection"))
        
        if not collection_files:
            self.log(f"  ❌ FAILED: No .collection files found in {sqlite_dir}", "FAIL")
            self.failed_tests.append({
                "test_num": 25,
                "name": "SQLite files exist",
                "error": "No .collection files found"
            })
            self.test_results[25] = {"name": "SQLite files exist", "passed": False}
            return False, {}
        
        self.tests_passed += 1
        self.log(f"  ✅ PASSED: Found {len(collection_files)} SQLite collection files", "PASS")
        self.log(f"     Files: {', '.join(f.name for f in collection_files[:5])}", "INFO")
        self.test_results[25] = {
            "name": "SQLite files exist",
            "passed": True,
            "files": [f.name for f in collection_files]
        }
        return True, {"files": [f.name for f in collection_files]}
    
    # ========== E. Subscription Gate (Smoke) ==========
    
    def test_26_subscription_active_flags(self):
        """Test #26: Verify subscription flags after activation (from test #8)"""
        def validate(data):
            checks = []
            checks.append(("active", data.get("active") == True))
            checks.append(("cloud_sync_enabled", data.get("cloud_sync_enabled") == True))
            
            failed = [name for name, result in checks if not result]
            if failed:
                return False, f"Flags not set after activation: {', '.join(failed)}"
            return True, "Subscription flags correctly set to true"
        
        return self.run_test(26, "GET /api/native/subscription (verify active flags)",
                            "GET", "native/subscription", 200, auth_required=False,
                            validate_response=validate)
    
    def test_27_subscription_inactive_flags(self):
        """Test #27: Verify subscription flags after deactivation (from test #9)"""
        def validate(data):
            checks = []
            checks.append(("active", data.get("active") == False))
            checks.append(("cloud_sync_enabled", data.get("cloud_sync_enabled") == False))
            
            failed = [name for name, result in checks if not result]
            if failed:
                return False, f"Flags not cleared after deactivation: {', '.join(failed)}"
            return True, "Subscription flags correctly set to false"
        
        return self.run_test(27, "GET /api/native/subscription (verify inactive flags)",
                            "GET", "native/subscription", 200, auth_required=False,
                            validate_response=validate)
    
    # ========== Test Runner ==========
    
    def run_all_tests(self):
        """Run all 27 tests in sequence"""
        self.log("=" * 80)
        self.log("BIG Hat Standalone — Native Mode Backend Testing")
        self.log("Testing Phases 0, 0.5, 1 (27 test scenarios)")
        self.log("=" * 80)
        
        # A. Native Module Endpoints (11 tests)
        self.log("\n" + "=" * 80)
        self.log("A. NATIVE MODULE ENDPOINTS (/api/native/*)")
        self.log("=" * 80)
        self.test_01_native_info()
        self.test_02_native_hwid()
        self.test_03_setup_status()
        self.test_04_setup_initialize_409()
        self.test_05_get_license()
        self.test_06_register_seat()
        self.test_07_get_subscription()
        self.test_08_activate_subscription()
        self.test_09_deactivate_subscription()
        self.test_10_setup_initialize_bad_license()
        self.test_11_setup_reset_wrong_confirm()
        
        # B. Native Auth Bridge (5 tests)
        self.log("\n" + "=" * 80)
        self.log("B. NATIVE AUTH BRIDGE (/api/auth/login)")
        self.log("=" * 80)
        self.test_12_login_master_admin()
        self.test_13_login_wrong_password()
        self.test_14_login_unknown_email()
        self.test_15_auth_me_with_token()
        self.test_16_auth_me_no_token()
        
        # C. SQLite-backed Schedule CRUD (7 tests)
        self.log("\n" + "=" * 80)
        self.log("C. SQLITE-BACKED SCHEDULE CRUD (/api/events, /api/venues)")
        self.log("=" * 80)
        self.test_17_get_venues()
        self.test_18_get_events()
        self.test_19_create_event()
        self.test_20_get_events_by_date()
        self.test_21_update_event()
        self.test_22_delete_event()
        self.test_23_verify_event_deleted()
        
        # D. Regression Tests (2 tests)
        self.log("\n" + "=" * 80)
        self.log("D. REGRESSION TESTS")
        self.log("=" * 80)
        self.test_24_health_check()
        self.test_25_sqlite_files_exist()
        
        # E. Subscription Gate (2 tests)
        self.log("\n" + "=" * 80)
        self.log("E. SUBSCRIPTION GATE (SMOKE)")
        self.log("=" * 80)
        # Re-activate for test 26
        self.test_08_activate_subscription()
        self.test_26_subscription_active_flags()
        # Re-deactivate for test 27
        self.test_09_deactivate_subscription()
        self.test_27_subscription_inactive_flags()
        
        # Print summary
        self.print_summary()
    
    def print_summary(self):
        """Print test results summary"""
        self.log("\n" + "=" * 80)
        self.log("TEST RESULTS SUMMARY")
        self.log("=" * 80)
        
        success_rate = (self.tests_passed / self.tests_run * 100) if self.tests_run > 0 else 0
        
        self.log(f"Tests Run:    {self.tests_run}")
        self.log(f"Tests Passed: {self.tests_passed}")
        self.log(f"Tests Failed: {len(self.failed_tests)}")
        self.log(f"Success Rate: {success_rate:.1f}%")
        
        if self.failed_tests:
            self.log("\n" + "=" * 80)
            self.log("FAILED TESTS DETAILS")
            self.log("=" * 80)
            for failure in self.failed_tests:
                self.log(f"\nTest #{failure.get('test_num')}: {failure.get('name')}")
                if 'error' in failure:
                    self.log(f"  Error: {failure['error']}")
                else:
                    self.log(f"  Expected: {failure.get('expected_status')}")
                    self.log(f"  Actual:   {failure.get('actual_status')}")
                    if failure.get('validation_msg'):
                        self.log(f"  Validation: {failure['validation_msg']}")
                    self.log(f"  Endpoint: {failure.get('endpoint')}")
        
        self.log("\n" + "=" * 80)
        if self.tests_passed == self.tests_run:
            self.log("✅ ALL TESTS PASSED!")
        else:
            self.log(f"❌ {len(self.failed_tests)} TEST(S) FAILED")
        self.log("=" * 80)
        
        return self.tests_passed == self.tests_run

def main():
    """Main entry point"""
    tester = NativeBackendTester()
    tester.run_all_tests()
    
    # Return exit code
    return 0 if tester.tests_passed == tester.tests_run else 1

if __name__ == "__main__":
    sys.exit(main())
