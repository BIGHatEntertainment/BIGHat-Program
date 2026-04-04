#!/usr/bin/env python3
"""
BIG Hat Hub Backend API Testing
Tests all API endpoints with master admin credentials
"""

import requests
import sys
import json
from datetime import datetime

class BigHatAPITester:
    def __init__(self, base_url="https://show-command.preview.emergentagent.com"):
        self.base_url = base_url
        self.token = None
        self.cookies = None
        self.tests_run = 0
        self.tests_passed = 0
        self.failed_tests = []

    def run_test(self, name, method, endpoint, expected_status, data=None, auth_required=True):
        """Run a single API test"""
        url = f"{self.base_url}/api/{endpoint}"
        headers = {'Content-Type': 'application/json'}
        
        if auth_required and self.token:
            headers['Authorization'] = f'Bearer {self.token}'

        self.tests_run += 1
        print(f"\n🔍 Testing {name}...")
        print(f"   URL: {url}")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, cookies=self.cookies)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers, cookies=self.cookies)
            elif method == 'PUT':
                response = requests.put(url, json=data, headers=headers, cookies=self.cookies)
            elif method == 'DELETE':
                response = requests.delete(url, headers=headers, cookies=self.cookies)

            success = response.status_code == expected_status
            if success:
                self.tests_passed += 1
                print(f"✅ Passed - Status: {response.status_code}")
                try:
                    response_data = response.json()
                    if isinstance(response_data, dict) and len(str(response_data)) < 200:
                        print(f"   Response: {response_data}")
                except:
                    pass
            else:
                print(f"❌ Failed - Expected {expected_status}, got {response.status_code}")
                try:
                    error_detail = response.json()
                    print(f"   Error: {error_detail}")
                except:
                    print(f"   Error: {response.text}")
                self.failed_tests.append({
                    "test": name,
                    "expected": expected_status,
                    "actual": response.status_code,
                    "endpoint": endpoint
                })

            return success, response.json() if response.content else {}

        except Exception as e:
            print(f"❌ Failed - Error: {str(e)}")
            self.failed_tests.append({
                "test": name,
                "error": str(e),
                "endpoint": endpoint
            })
            return False, {}

    def test_health_check(self):
        """Test API health endpoint"""
        success, response = self.run_test(
            "Health Check",
            "GET",
            "health",
            200,
            auth_required=False
        )
        return success

    def test_login(self, email, password):
        """Test login and get token"""
        success, response = self.run_test(
            "Master Admin Login",
            "POST",
            "auth/login",
            200,
            data={"email": email, "password": password},
            auth_required=False
        )
        if success and 'token' in response:
            self.token = response['token']
            print(f"   Token received: {self.token[:20]}...")
            return True
        return False

    def test_auth_me(self):
        """Test getting current user info"""
        success, response = self.run_test(
            "Get Current User (/auth/me)",
            "GET",
            "auth/me",
            200
        )
        if success:
            print(f"   User: {response.get('name')} ({response.get('role')})")
        return success

    def test_get_users(self):
        """Test getting all users (admin only)"""
        success, response = self.run_test(
            "Get All Users",
            "GET",
            "users",
            200
        )
        if success:
            print(f"   Found {len(response)} users")
        return success

    def test_create_user(self):
        """Test creating a new user"""
        test_user_data = {
            "email": f"test_host_{datetime.now().strftime('%H%M%S')}@bighat.live",
            "password": "TestPass123!",
            "name": "Test Host",
            "role": "host"
        }
        success, response = self.run_test(
            "Create New User",
            "POST",
            "auth/register",
            200,
            data=test_user_data
        )
        if success:
            return response.get('id')
        return None

    def test_get_events(self):
        """Test getting all events"""
        success, response = self.run_test(
            "Get All Events",
            "GET",
            "events",
            200
        )
        if success:
            print(f"   Found {len(response)} events")
        return success, response

    def test_get_unclaimed_events(self):
        """Test getting unclaimed events"""
        success, response = self.run_test(
            "Get Unclaimed Events",
            "GET",
            "events/unclaimed",
            200
        )
        if success:
            print(f"   Found {len(response)} unclaimed events")
        return success, response

    def test_create_event(self):
        """Test creating a new event"""
        # First get a venue ID
        venues_success, venues = self.run_test(
            "Get Venues for Event Creation",
            "GET", 
            "venues",
            200
        )
        if not venues_success or not venues:
            print("   No venues available for event creation")
            return None
            
        venue_id = venues[0]['id']
        event_data = {
            "title": f"Test Event {datetime.now().strftime('%H:%M:%S')}",
            "event_type": "Trivia",
            "venue_id": venue_id,
            "date": "2026-02-01T19:00:00Z",
            "duration_hours": 2.0
        }
        success, response = self.run_test(
            "Create New Event",
            "POST",
            "events",
            200,
            data=event_data
        )
        if success:
            return response.get('id')
        return None

    def test_claim_event(self, event_id):
        """Test claiming an event"""
        if not event_id:
            return False
        
        # Get an employee ID to claim the event
        employees_success, employees = self.run_test(
            "Get Employees for Event Claim",
            "GET",
            "employees", 
            200
        )
        if not employees_success or not employees:
            print("   No employees available for event claim")
            return False
            
        employee_id = employees[0]['id']
        claim_data = {"employee_id": employee_id}
        
        success, response = self.run_test(
            "Claim Event",
            "POST",
            f"events/{event_id}/claim",
            200,
            data=claim_data
        )
        return success

    def test_protected_route_without_auth(self):
        """Test accessing protected route without authentication"""
        # Temporarily remove token
        temp_token = self.token
        self.token = None
        success, response = self.run_test(
            "Protected Route Without Auth",
            "GET",
            "users",
            401
        )
        # Restore token
        self.token = temp_token
        return success

    def test_get_employees(self):
        """Test getting all employees (should return 5)"""
        success, response = self.run_test(
            "Get All Employees",
            "GET",
            "employees",
            200
        )
        if success:
            print(f"   Found {len(response)} employees")
            if len(response) != 5:
                print(f"   ⚠️  Expected 5 employees, found {len(response)}")
        return success

    def test_get_venues(self):
        """Test getting all venues (should return 6)"""
        success, response = self.run_test(
            "Get All Venues",
            "GET",
            "venues",
            200
        )
        if success:
            print(f"   Found {len(response)} venues")
            if len(response) != 6:
                print(f"   ⚠️  Expected 6 venues, found {len(response)}")
        return success

    def test_get_venue_pricing(self):
        """Test getting venue pricing data"""
        success, response = self.run_test(
            "Get Venue Pricing",
            "GET",
            "venue_pricing",
            200
        )
        if success:
            print(f"   Found pricing for {len(response)} venues")
        return success

    def test_host_login(self):
        """Test schedule host login"""
        host_data = {
            "name": "Nick Sellards",
            "password": "B1GHat"
        }
        success, response = self.run_test(
            "Schedule Host Login",
            "POST",
            "host/login",
            200,
            data=host_data,
            auth_required=False
        )
        if success:
            print(f"   Host logged in: {response.get('employee', {}).get('name')}")
        return success

    def test_admin_verify(self):
        """Test schedule admin passcode verification"""
        admin_data = {
            "passcode": "121589"
        }
        success, response = self.run_test(
            "Schedule Admin Verify",
            "POST",
            "admin/verify",
            200,
            data=admin_data,
            auth_required=False
        )
        if success:
            print(f"   Admin verified: {response.get('message')}")
        return success

    def test_logout(self):
        """Test logout"""
        success, response = self.run_test(
            "Logout",
            "POST",
            "auth/logout",
            200
        )
        return success

def main():
    print("🎩 BIG Hat Hub Backend API Testing")
    print("=" * 50)
    
    # Setup
    tester = BigHatAPITester()
    
    # Master admin credentials from test_credentials.md
    admin_email = "Sellards@bighat.live"
    admin_password = "BigHat2024!"

    # Run tests in sequence
    print("\n📋 Running Backend API Tests...")
    
    # 1. Health check
    if not tester.test_health_check():
        print("❌ Health check failed, stopping tests")
        return 1

    # 2. Login
    if not tester.test_login(admin_email, admin_password):
        print("❌ Login failed, stopping tests")
        return 1

    # 3. Auth verification
    tester.test_auth_me()

    # 4. Schedule-specific tests
    tester.test_get_employees()
    tester.test_get_venues()
    tester.test_get_venue_pricing()
    tester.test_host_login()
    tester.test_admin_verify()

    # 5. User management tests
    tester.test_get_users()
    new_user_id = tester.test_create_user()

    # 6. Event management tests
    events_success, events = tester.test_get_events()
    unclaimed_success, unclaimed_events = tester.test_get_unclaimed_events()
    
    # Create and claim event
    new_event_id = tester.test_create_event()
    if new_event_id:
        tester.test_claim_event(new_event_id)

    # 7. Security tests
    tester.test_protected_route_without_auth()

    # 8. Logout
    tester.test_logout()

    # Print results
    print(f"\n📊 Test Results:")
    print(f"   Tests passed: {tester.tests_passed}/{tester.tests_run}")
    print(f"   Success rate: {(tester.tests_passed/tester.tests_run)*100:.1f}%")
    
    if tester.failed_tests:
        print(f"\n❌ Failed Tests:")
        for failure in tester.failed_tests:
            error_msg = failure.get('error', f"Expected {failure.get('expected')}, got {failure.get('actual')}")
            print(f"   - {failure['test']}: {error_msg}")
    
    return 0 if tester.tests_passed == tester.tests_run else 1

if __name__ == "__main__":
    sys.exit(main())