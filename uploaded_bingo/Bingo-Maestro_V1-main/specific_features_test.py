import requests
import sys
import json
from datetime import datetime

class SpecificFeaturesTester:
    def __init__(self, base_url="https://music-bingo-host.preview.emergentagent.com/api"):
        self.base_url = base_url
        self.tests_run = 0
        self.tests_passed = 0
        self.results = []

    def log_result(self, test_name, success, details=""):
        """Log test result"""
        self.tests_run += 1
        if success:
            self.tests_passed += 1
        
        result = {
            "test": test_name,
            "success": success,
            "details": details,
            "timestamp": datetime.now().isoformat()
        }
        self.results.append(result)
        
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} - {test_name}")
        if details:
            print(f"    {details}")

    def test_music_bingo_creation(self):
        """Test /api/game/create with bingo_type='music'"""
        data = {
            "bingo_type": "music",
            "game_type": "regular",
            "round_type": "traditional",
            "call_interval": 20,
            "music_decade": "1980s",
            "preset_mode": False
        }
        
        try:
            response = requests.post(f"{self.base_url}/game/create", json=data, timeout=10)
            success = response.status_code == 200
            
            if success:
                response_data = response.json()
                game = response_data.get('game', {})
                settings = game.get('settings', {})
                
                if settings.get('bingo_type') == 'music':
                    self.log_result("Music Bingo Game Creation", True, f"Game ID: {game.get('id')}, Type: {settings.get('bingo_type')}")
                    return True, response_data
                else:
                    self.log_result("Music Bingo Game Creation", False, f"Wrong bingo type: {settings.get('bingo_type')}")
                    return False, {}
            else:
                self.log_result("Music Bingo Game Creation", False, f"Status: {response.status_code}, Error: {response.text}")
                return False, {}
                
        except Exception as e:
            self.log_result("Music Bingo Game Creation", False, f"Exception: {str(e)}")
            return False, {}

    def test_traditional_bingo_creation(self):
        """Test /api/game/create with bingo_type='traditional'"""
        data = {
            "bingo_type": "traditional",
            "game_type": "regular",
            "round_type": "traditional",
            "call_interval": 20,
            "music_decade": "1980s",
            "preset_mode": False
        }
        
        try:
            response = requests.post(f"{self.base_url}/game/create", json=data, timeout=10)
            success = response.status_code == 200
            
            if success:
                response_data = response.json()
                game = response_data.get('game', {})
                settings = game.get('settings', {})
                
                if settings.get('bingo_type') == 'traditional':
                    self.log_result("Traditional Bingo Game Creation", True, f"Game ID: {game.get('id')}, Type: {settings.get('bingo_type')}")
                    return True, response_data
                else:
                    self.log_result("Traditional Bingo Game Creation", False, f"Wrong bingo type: {settings.get('bingo_type')}")
                    return False, {}
            else:
                self.log_result("Traditional Bingo Game Creation", False, f"Status: {response.status_code}, Error: {response.text}")
                return False, {}
                
        except Exception as e:
            self.log_result("Traditional Bingo Game Creation", False, f"Exception: {str(e)}")
            return False, {}

    def test_songlist_1980s(self):
        """Test /api/songlist/1980s returns sample song list with 15 songs"""
        try:
            response = requests.get(f"{self.base_url}/songlist/1980s", timeout=10)
            success = response.status_code == 200
            
            if success:
                response_data = response.json()
                songs = response_data.get('songs', [])
                
                if len(songs) >= 15:
                    # Check if songs have required fields
                    sample_song = songs[0] if songs else {}
                    has_required_fields = all(field in sample_song for field in ['number', 'title', 'artist'])
                    
                    if has_required_fields:
                        self.log_result("1980s Song List", True, f"Found {len(songs)} songs with required fields (number, title, artist)")
                        return True, response_data
                    else:
                        self.log_result("1980s Song List", False, f"Songs missing required fields. Sample: {sample_song}")
                        return False, {}
                else:
                    self.log_result("1980s Song List", False, f"Expected at least 15 songs, got {len(songs)}")
                    return False, {}
            else:
                self.log_result("1980s Song List", False, f"Status: {response.status_code}, Error: {response.text}")
                return False, {}
                
        except Exception as e:
            self.log_result("1980s Song List", False, f"Exception: {str(e)}")
            return False, {}

    def test_call_song_endpoint(self):
        """Test /api/game/call-song endpoint accepts song data"""
        # First create a music bingo game
        music_game_success, _ = self.test_music_bingo_creation()
        if not music_game_success:
            self.log_result("Call Song Endpoint", False, "Failed to create music bingo game first")
            return False, {}
        
        # Start the game
        try:
            start_response = requests.post(f"{self.base_url}/game/start", timeout=10)
            if start_response.status_code != 200:
                self.log_result("Call Song Endpoint", False, "Failed to start game")
                return False, {}
        except Exception as e:
            self.log_result("Call Song Endpoint", False, f"Failed to start game: {str(e)}")
            return False, {}
        
        # Now test call-song
        song_data = {
            "number": 1,
            "title": "Billie Jean",
            "artist": "Michael Jackson"
        }
        
        try:
            response = requests.post(f"{self.base_url}/game/call-song", json=song_data, timeout=10)
            success = response.status_code == 200
            
            if success:
                response_data = response.json()
                if response_data.get('success') and 'song' in response_data:
                    self.log_result("Call Song Endpoint", True, f"Song called successfully: {response_data.get('song')}")
                    return True, response_data
                else:
                    self.log_result("Call Song Endpoint", False, f"Unexpected response format: {response_data}")
                    return False, {}
            else:
                self.log_result("Call Song Endpoint", False, f"Status: {response.status_code}, Error: {response.text}")
                return False, {}
                
        except Exception as e:
            self.log_result("Call Song Endpoint", False, f"Exception: {str(e)}")
            return False, {}

    def run_specific_tests(self):
        """Run tests for specific features mentioned in review request"""
        print("🎯 Testing Specific Music Bingo Features")
        print("=" * 60)
        
        # Test the specific features from review request
        print("\n🎮 Game Creation Tests...")
        self.test_music_bingo_creation()
        self.test_traditional_bingo_creation()
        
        print("\n🎵 Song List Tests...")
        self.test_songlist_1980s()
        
        print("\n📞 Song Calling Tests...")
        self.test_call_song_endpoint()
        
        # Print summary
        print("\n" + "=" * 60)
        print(f"📊 Specific Features Test Summary: {self.tests_passed}/{self.tests_run} tests passed")
        
        if self.tests_passed == self.tests_run:
            print("🎉 All specific feature tests passed!")
            return 0
        else:
            print(f"⚠️  {self.tests_run - self.tests_passed} specific feature tests failed")
            return 1

def main():
    tester = SpecificFeaturesTester()
    return tester.run_specific_tests()

if __name__ == "__main__":
    sys.exit(main())