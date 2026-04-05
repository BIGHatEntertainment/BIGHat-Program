#!/usr/bin/env python3
"""
Backend API Testing for BIG Hat Trivia Scoreboard
Tests all endpoints: root, SharePoint, scores, presets, tournaments
"""
import requests
import sys
import json
from datetime import datetime
from typing import Dict, Any

class TriviaAPITester:
    def __init__(self, base_url="https://trivia-scoreboard.preview.emergentagent.com"):
        self.base_url = base_url
        self.api_url = f"{base_url}/api"
        self.tests_run = 0
        self.tests_passed = 0
        self.test_results = []

    def log_test(self, name: str, success: bool, details: str = ""):
        """Log test result"""
        self.tests_run += 1
        if success:
            self.tests_passed += 1
        
        result = {
            "test": name,
            "success": success,
            "details": details,
            "timestamp": datetime.now().isoformat()
        }
        self.test_results.append(result)
        
        status = "✅ PASSED" if success else "❌ FAILED"
        print(f"{status} - {name}")
        if details:
            print(f"   Details: {details}")

    def run_test(self, name: str, method: str, endpoint: str, expected_status: int, data=None, timeout=30):
        """Run a single API test"""
        url = f"{self.api_url}/{endpoint}" if endpoint else self.api_url
        headers = {'Content-Type': 'application/json'}
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, timeout=timeout)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers, timeout=timeout)
            elif method == 'PUT':
                response = requests.put(url, json=data, headers=headers, timeout=timeout)
            elif method == 'DELETE':
                response = requests.delete(url, headers=headers, timeout=timeout)
            
            success = response.status_code == expected_status
            
            if success:
                try:
                    resp_data = response.json()
                    details = f"Status: {response.status_code}, Response keys: {list(resp_data.keys()) if isinstance(resp_data, dict) else 'Non-dict response'}"
                except:
                    details = f"Status: {response.status_code}, Response length: {len(response.text)}"
            else:
                try:
                    error_data = response.json()
                    details = f"Expected {expected_status}, got {response.status_code}. Error: {error_data.get('detail', 'No detail')}"
                except:
                    details = f"Expected {expected_status}, got {response.status_code}. Raw: {response.text[:200]}"
            
            self.log_test(name, success, details)
            return success, response.json() if success and response.text else {}
            
        except Exception as e:
            self.log_test(name, False, f"Exception: {str(e)}")
            return False, {}

    def test_root_endpoint(self):
        """Test the root API endpoint"""
        return self.run_test("Root API Endpoint", "GET", "", 200)

    def test_sharepoint_files(self):
        """Test SharePoint files endpoint - may take longer due to API calls"""
        return self.run_test("SharePoint Files Fetch", "GET", "sharepoint/files", 200, timeout=60)

    def test_sharepoint_sync(self):
        """Test SharePoint sync endpoint - may take longer"""
        return self.run_test("SharePoint Sync", "POST", "sharepoint/sync", 200, timeout=60)

    def test_get_scores(self):
        """Test get scores endpoint"""
        return self.run_test("Get Synced Scores", "GET", "scores", 200)

    def test_presets_crud(self):
        """Test preset CRUD operations"""
        # Create preset
        preset_data = {
            "name": f"Test Preset {datetime.now().strftime('%H%M%S')}",
            "mode": "leaderboard",
            "aspect_ratio": "landscape",
            "animation_speed": 1.5,
            "config": {"test": True}
        }
        
        success, create_response = self.run_test("Create Preset", "POST", "presets", 200, preset_data)
        if not success:
            return False
        
        preset_id = create_response.get("id")
        if not preset_id:
            self.log_test("Create Preset - Get ID", False, "No ID in create response")
            return False

        # Get all presets
        success, _ = self.run_test("Get All Presets", "GET", "presets", 200)
        if not success:
            return False

        # Get specific preset
        success, _ = self.run_test("Get Specific Preset", "GET", f"presets/{preset_id}", 200)
        if not success:
            return False

        # Update preset
        update_data = {
            "name": "Updated Test Preset",
            "mode": "tournament",
            "aspect_ratio": "portrait",
            "animation_speed": 2.0
        }
        success, _ = self.run_test("Update Preset", "PUT", f"presets/{preset_id}", 200, update_data)
        if not success:
            return False

        # Delete preset
        success, _ = self.run_test("Delete Preset", "DELETE", f"presets/{preset_id}", 200)
        return success

    def test_tournaments_crud(self):
        """Test tournament CRUD operations"""
        # Create tournament
        tournament_data = {
            "name": f"Test Tournament {datetime.now().strftime('%H%M%S')}",
            "total_teams": 8,
            "bye_count": 0,
            "teams": [
                {"seed": 1, "name": "Team Alpha"},
                {"seed": 2, "name": "Team Beta"},
                {"seed": 3, "name": "Team Gamma"},
                {"seed": 4, "name": "Team Delta"}
            ],
            "bracket_state": {}
        }
        
        success, create_response = self.run_test("Create Tournament", "POST", "tournaments", 200, tournament_data)
        if not success:
            return False
        
        tournament_id = create_response.get("id")
        if not tournament_id:
            self.log_test("Create Tournament - Get ID", False, "No ID in create response")
            return False

        # Get all tournaments
        success, _ = self.run_test("Get All Tournaments", "GET", "tournaments", 200)
        if not success:
            return False

        # Get specific tournament
        success, _ = self.run_test("Get Specific Tournament", "GET", f"tournaments/{tournament_id}", 200)
        if not success:
            return False

        # Update tournament
        update_data = {
            "name": "Updated Test Tournament",
            "teams": [
                {"seed": 1, "name": "Team Alpha Updated"},
                {"seed": 2, "name": "Team Beta Updated"}
            ]
        }
        success, _ = self.run_test("Update Tournament", "PUT", f"tournaments/{tournament_id}", 200, update_data)
        if not success:
            return False

        # Test advance tournament (record match result)
        advance_data = {
            "match_id": "test_match_1",
            "winner_seed": 1,
            "score_a": 3,
            "score_b": 1
        }
        success, _ = self.run_test("Advance Tournament", "POST", f"tournaments/{tournament_id}/advance", 200, advance_data)
        if not success:
            return False

        # Delete tournament
        success, _ = self.run_test("Delete Tournament", "DELETE", f"tournaments/{tournament_id}", 200)
        return success

    def test_venue_specific_scores(self):
        """Test venue-specific scores endpoint"""
        return self.run_test("Get Venue Scores", "GET", "scores/test_venue", 200)

    def run_all_tests(self):
        """Run all backend tests"""
        print(f"🚀 Starting BIG Hat Trivia Scoreboard Backend Tests")
        print(f"   Base URL: {self.base_url}")
        print(f"   API URL: {self.api_url}")
        print("=" * 60)

        # Basic connectivity
        self.test_root_endpoint()
        
        # SharePoint integration (these may fail if credentials are invalid)
        print("\n📁 Testing SharePoint Integration...")
        self.test_sharepoint_files()
        self.test_sharepoint_sync()
        
        # Scores
        print("\n📊 Testing Scores API...")
        self.test_get_scores()
        self.test_venue_specific_scores()
        
        # Presets CRUD
        print("\n⚙️ Testing Presets CRUD...")
        self.test_presets_crud()
        
        # Tournaments CRUD
        print("\n🏆 Testing Tournaments CRUD...")
        self.test_tournaments_crud()
        
        # Results summary
        print("\n" + "=" * 60)
        print(f"📈 Test Results: {self.tests_passed}/{self.tests_run} passed ({self.tests_passed/self.tests_run*100:.1f}%)")
        
        # Show failed tests
        failed_tests = [t for t in self.test_results if not t['success']]
        if failed_tests:
            print(f"\n❌ Failed Tests ({len(failed_tests)}):")
            for test in failed_tests:
                print(f"   • {test['test']}: {test['details']}")
        else:
            print("\n🎉 All tests passed!")
        
        return self.tests_passed == self.tests_run

def main():
    """Main test execution"""
    tester = TriviaAPITester()
    
    try:
        all_passed = tester.run_all_tests()
        
        # Save detailed results
        with open('/app/backend_test_results.json', 'w') as f:
            json.dump({
                'summary': {
                    'total_tests': tester.tests_run,
                    'passed_tests': tester.tests_passed,
                    'failed_tests': tester.tests_run - tester.tests_passed,
                    'success_rate': f"{tester.tests_passed/tester.tests_run*100:.1f}%" if tester.tests_run > 0 else "0%",
                    'timestamp': datetime.now().isoformat()
                },
                'detailed_results': tester.test_results
            }, f, indent=2)
        
        return 0 if all_passed else 1
        
    except KeyboardInterrupt:
        print("\n⚠️ Tests interrupted by user")
        return 1
    except Exception as e:
        print(f"\n💥 Unexpected error: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())