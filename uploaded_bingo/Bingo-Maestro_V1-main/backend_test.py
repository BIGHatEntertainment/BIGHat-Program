import requests
import sys
import json
from datetime import datetime

class MusicBingoAPITester:
    def __init__(self, base_url="https://music-bingo-host.preview.emergentagent.com"):
        self.base_url = base_url
        self.api_url = f"{base_url}/api"
        self.tests_run = 0
        self.tests_passed = 0
        self.game_id = None

    def run_test(self, name, method, endpoint, expected_status, data=None, headers=None):
        """Run a single API test"""
        url = f"{self.api_url}/{endpoint}"
        if headers is None:
            headers = {'Content-Type': 'application/json'}

        self.tests_run += 1
        print(f"\n🔍 Testing {name}...")
        print(f"   URL: {url}")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, timeout=10)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers, timeout=10)
            elif method == 'PUT':
                response = requests.put(url, json=data, headers=headers, timeout=10)

            success = response.status_code == expected_status
            if success:
                self.tests_passed += 1
                print(f"✅ Passed - Status: {response.status_code}")
                try:
                    response_data = response.json()
                    print(f"   Response: {json.dumps(response_data, indent=2)[:200]}...")
                    return True, response_data
                except:
                    return True, {}
            else:
                print(f"❌ Failed - Expected {expected_status}, got {response.status_code}")
                try:
                    error_data = response.json()
                    print(f"   Error: {error_data}")
                except:
                    print(f"   Error: {response.text}")
                return False, {}

        except Exception as e:
            print(f"❌ Failed - Error: {str(e)}")
            return False, {}

    def test_health_check(self):
        """Test basic health endpoint"""
        return self.run_test("Health Check", "GET", "health", 200)

    def test_root_endpoint(self):
        """Test root API endpoint"""
        return self.run_test("Root Endpoint", "GET", "", 200)

    def test_create_game_preset(self):
        """Test creating a game in preset mode"""
        game_data = {
            "game_type": "regular",
            "round_type": "traditional", 
            "call_interval": 20,
            "music_decade": "mixed",
            "preset_mode": True
        }
        success, response = self.run_test(
            "Create Game (Preset Mode)",
            "POST", 
            "game/create",
            200,
            data=game_data
        )
        if success and response.get('success') and response.get('game'):
            self.game_id = response['game']['id']
            print(f"   Game ID: {self.game_id}")
        return success

    def test_create_game_custom(self):
        """Test creating a game in custom mode"""
        game_data = {
            "game_type": "lightning",
            "round_type": "4-corners", 
            "call_interval": 10,
            "music_decade": "1980s",
            "preset_mode": False
        }
        success, response = self.run_test(
            "Create Game (Custom Mode)",
            "POST", 
            "game/create",
            200,
            data=game_data
        )
        if success and response.get('success') and response.get('game'):
            self.game_id = response['game']['id']
            print(f"   Game ID: {self.game_id}")
        return success

    def test_get_game_state(self):
        """Test getting current game state"""
        success, response = self.run_test(
            "Get Game State",
            "GET",
            "game/state", 
            200
        )
        if success and response.get('game'):
            print(f"   Game found: {response['game']['id']}")
            return True
        return success

    def test_start_game(self):
        """Test starting the game"""
        return self.run_test(
            "Start Game",
            "POST",
            "game/start",
            200
        )

    def test_call_number(self):
        """Test calling a bingo number"""
        success, response = self.run_test(
            "Call Number",
            "POST",
            "game/call-number",
            200
        )
        if success and response.get('success'):
            print(f"   Called: {response.get('letter', '')}{response.get('number', '')}")
        return success

    def test_pause_game(self):
        """Test pausing the game"""
        return self.run_test(
            "Pause Game",
            "POST",
            "game/pause",
            200
        )

    def test_resume_game(self):
        """Test resuming the game"""
        return self.run_test(
            "Resume Game", 
            "POST",
            "game/resume",
            200
        )

    def test_claim_bingo(self):
        """Test claiming bingo"""
        return self.run_test(
            "Claim Bingo",
            "POST",
            "game/bingo",
            200
        )

    def test_verify_bingo_confirm(self):
        """Test confirming a bingo"""
        verification_data = {
            "winner_name": "Test Winner",
            "confirmed": True
        }
        return self.run_test(
            "Verify Bingo (Confirm)",
            "POST",
            "game/verify-bingo",
            200,
            data=verification_data
        )

    def test_verify_bingo_reject(self):
        """Test rejecting a bingo"""
        verification_data = {
            "winner_name": "Test Player",
            "confirmed": False
        }
        return self.run_test(
            "Verify Bingo (Reject)",
            "POST", 
            "game/verify-bingo",
            200,
            data=verification_data
        )

    def test_new_round(self):
        """Test starting a new round"""
        return self.run_test(
            "New Round",
            "POST",
            "game/new-round",
            200
        )

    def test_end_round(self):
        """Test ending current round"""
        return self.run_test(
            "End Round",
            "POST",
            "game/end-round", 
            200
        )

    def test_set_volume(self):
        """Test setting game volume"""
        return self.run_test(
            "Set Volume",
            "POST",
            "game/volume",
            200,
            data=0.5
        )

    def test_sharepoint_test(self):
        """Test SharePoint integration"""
        return self.run_test(
            "SharePoint Test",
            "GET",
            "sharepoint/test",
            200
        )

    def test_sharepoint_folders(self):
        """Test SharePoint folder listing"""
        return self.run_test(
            "SharePoint Folders",
            "GET", 
            "sharepoint/folders",
            200
        )

def main():
    print("🎵 Music Bingo API Testing Suite")
    print("=" * 50)
    
    tester = MusicBingoAPITester()
    
    # Basic connectivity tests
    print("\n📡 CONNECTIVITY TESTS")
    tester.test_health_check()
    tester.test_root_endpoint()
    
    # Game creation tests
    print("\n🎮 GAME CREATION TESTS")
    tester.test_create_game_preset()
    tester.test_get_game_state()
    
    # Game flow tests
    print("\n🎯 GAME FLOW TESTS")
    tester.test_start_game()
    tester.test_call_number()
    tester.test_call_number()  # Call another number
    tester.test_pause_game()
    tester.test_resume_game()
    
    # Bingo verification tests
    print("\n🏆 BINGO TESTS")
    tester.test_claim_bingo()
    tester.test_verify_bingo_reject()  # Test rejection first
    tester.test_claim_bingo()  # Claim again
    tester.test_verify_bingo_confirm()  # Then confirm
    
    # Round management tests
    print("\n🔄 ROUND MANAGEMENT TESTS")
    tester.test_new_round()
    tester.test_create_game_custom()  # Test custom game creation
    tester.test_end_round()
    
    # Additional features
    print("\n⚙️ ADDITIONAL FEATURES")
    tester.test_set_volume()
    tester.test_sharepoint_test()
    tester.test_sharepoint_folders()
    
    # Print results
    print("\n" + "=" * 50)
    print(f"📊 FINAL RESULTS")
    print(f"Tests Run: {tester.tests_run}")
    print(f"Tests Passed: {tester.tests_passed}")
    print(f"Success Rate: {(tester.tests_passed/tester.tests_run*100):.1f}%")
    
    if tester.tests_passed == tester.tests_run:
        print("🎉 All tests passed!")
        return 0
    else:
        print(f"⚠️  {tester.tests_run - tester.tests_passed} tests failed")
        return 1

if __name__ == "__main__":
    sys.exit(main())