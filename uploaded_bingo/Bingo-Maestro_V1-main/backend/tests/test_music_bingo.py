"""
Music Bingo Backend API Tests
Tests all critical backend endpoints for both Music Bingo and Traditional Bingo modes
"""

import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://music-bingo-host.preview.emergentagent.com').rstrip('/')
API = f"{BASE_URL}/api"


class TestHealthCheck:
    """Health check and basic connectivity tests"""
    
    def test_health_endpoint(self):
        """Test /api/health returns healthy status"""
        response = requests.get(f"{API}/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "service" in data
        print(f"Health check passed: {data}")
    
    def test_root_endpoint(self):
        """Test /api/ root endpoint"""
        response = requests.get(f"{API}/")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        print(f"Root endpoint: {data}")


class TestSharePointIntegration:
    """SharePoint integration tests"""
    
    def test_sharepoint_connection(self):
        """Test SharePoint authentication and connection"""
        response = requests.get(f"{API}/sharepoint/test")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        assert data["has_token"] == True
        assert data["site_id"] is not None
        assert data["drive_id"] is not None
        print(f"SharePoint connected - site_id: {data['site_id'][:50]}...")
    
    def test_songlist_1980s_from_sharepoint(self):
        """Test /api/songlist/1980s returns songs from SharePoint"""
        response = requests.get(f"{API}/songlist/1980s")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        assert data["decade"] == "1980s"
        assert "songs" in data
        assert len(data["songs"]) > 0
        
        # SharePoint returns 76 songs, sample returns 15
        print(f"Source: {data['source']}, Song count: {len(data['songs'])}")
        
        # Verify song structure
        song = data["songs"][0]
        assert "number" in song
        assert "title" in song
        assert "artist" in song
    
    def test_songlist_all_decades(self):
        """Test all decades return song lists"""
        decades = ["1970s", "1980s", "1990s", "2000s"]
        for decade in decades:
            response = requests.get(f"{API}/songlist/{decade}")
            assert response.status_code == 200
            data = response.json()
            assert data["success"] == True
            assert len(data["songs"]) >= 15  # At minimum, sample data
            print(f"Decade {decade}: {len(data['songs'])} songs from {data['source']}")


class TestMusicBingoGameFlow:
    """Music Bingo game creation and flow tests"""
    
    def test_create_music_bingo_game(self):
        """Test creating a Music Bingo game with default call_interval=30"""
        payload = {
            "bingo_type": "music",
            "game_type": "regular",
            "round_type": "traditional",
            "call_interval": 30,
            "music_decade": "1980s",
            "preset_mode": False
        }
        response = requests.post(f"{API}/game/create", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        assert data["game"]["settings"]["bingo_type"] == "music"
        assert data["game"]["settings"]["call_interval"] == 30
        assert data["game"]["settings"]["music_decade"] == "1980s"
        print(f"Music Bingo game created: {data['game']['id']}")
        return data["game"]["id"]
    
    def test_get_game_state(self):
        """Test /api/game/state returns current game state"""
        # First create a game
        payload = {"bingo_type": "music", "game_type": "regular", "call_interval": 30, "music_decade": "1980s"}
        requests.post(f"{API}/game/create", json=payload)
        
        response = requests.get(f"{API}/game/state")
        assert response.status_code == 200
        data = response.json()
        assert "game" in data
        if data["game"]:
            assert "settings" in data["game"]
            assert "is_active" in data["game"]
            print(f"Game state: active={data['game']['is_active']}, bingo_type={data['game']['settings']['bingo_type']}")
    
    def test_music_bingo_start_and_call_song(self):
        """Test starting a music bingo game and calling songs"""
        # Create game
        payload = {"bingo_type": "music", "game_type": "regular", "call_interval": 30, "music_decade": "1980s"}
        create_resp = requests.post(f"{API}/game/create", json=payload)
        assert create_resp.status_code == 200
        
        # Start game
        start_resp = requests.post(f"{API}/game/start")
        assert start_resp.status_code == 200
        assert start_resp.json()["success"] == True
        
        # Call a song
        song_payload = {"number": 1, "title": "Billie Jean", "artist": "Michael Jackson"}
        call_resp = requests.post(f"{API}/game/call-song", json=song_payload)
        assert call_resp.status_code == 200
        data = call_resp.json()
        assert data["success"] == True
        assert data["song"]["number"] == 1
        assert data["song"]["title"] == "Billie Jean"
        print(f"Called song: {data['song']}")
        
        # Verify game state includes called song
        state_resp = requests.get(f"{API}/game/state")
        state_data = state_resp.json()
        assert state_data["game"]["current_song"]["number"] == 1
        assert len(state_data["game"]["called_songs"]) >= 1


class TestTraditionalBingoGameFlow:
    """Traditional Bingo game creation and flow tests"""
    
    def test_create_traditional_bingo_game(self):
        """Test creating a Traditional Bingo game"""
        payload = {
            "bingo_type": "traditional",
            "game_type": "regular",
            "round_type": "traditional",
            "call_interval": 30,
            "music_decade": "1980s",
            "preset_mode": False
        }
        response = requests.post(f"{API}/game/create", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        assert data["game"]["settings"]["bingo_type"] == "traditional"
        print(f"Traditional Bingo game created: {data['game']['id']}")
    
    def test_traditional_bingo_call_number(self):
        """Test calling numbers in traditional bingo"""
        # Create traditional bingo game
        payload = {"bingo_type": "traditional", "game_type": "regular", "call_interval": 30}
        create_resp = requests.post(f"{API}/game/create", json=payload)
        assert create_resp.status_code == 200
        
        # Start game
        start_resp = requests.post(f"{API}/game/start")
        assert start_resp.status_code == 200
        
        # Call a number
        call_resp = requests.post(f"{API}/game/call-number")
        assert call_resp.status_code == 200
        data = call_resp.json()
        assert data["success"] == True
        assert "number" in data
        assert "letter" in data
        assert 1 <= data["number"] <= 75
        assert data["letter"] in ["B", "I", "N", "G", "O"]
        print(f"Called number: {data['letter']}{data['number']}")


class TestGameTimerIntervals:
    """Test timer intervals for Lightning vs Regular mode"""
    
    def test_lightning_mode_interval_10(self):
        """Test Lightning mode with 10 second interval"""
        payload = {
            "bingo_type": "music",
            "game_type": "lightning",
            "call_interval": 10
        }
        response = requests.post(f"{API}/game/create", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["game"]["settings"]["game_type"] == "lightning"
        assert data["game"]["settings"]["call_interval"] == 10
        print("Lightning mode 10s interval: PASS")
    
    def test_lightning_mode_interval_15(self):
        """Test Lightning mode with 15 second interval"""
        payload = {
            "bingo_type": "music",
            "game_type": "lightning",
            "call_interval": 15
        }
        response = requests.post(f"{API}/game/create", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["game"]["settings"]["call_interval"] == 15
        print("Lightning mode 15s interval: PASS")
    
    def test_regular_mode_interval_30(self):
        """Test Regular mode with 30 second interval (default)"""
        payload = {
            "bingo_type": "music",
            "game_type": "regular",
            "call_interval": 30
        }
        response = requests.post(f"{API}/game/create", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["game"]["settings"]["game_type"] == "regular"
        assert data["game"]["settings"]["call_interval"] == 30
        print("Regular mode 30s interval: PASS")
    
    def test_regular_mode_interval_45(self):
        """Test Regular mode with 45 second interval"""
        payload = {
            "bingo_type": "music",
            "game_type": "regular",
            "call_interval": 45
        }
        response = requests.post(f"{API}/game/create", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["game"]["settings"]["call_interval"] == 45
        print("Regular mode 45s interval: PASS")
    
    def test_regular_mode_interval_60(self):
        """Test Regular mode with 60 second interval"""
        payload = {
            "bingo_type": "music",
            "game_type": "regular",
            "call_interval": 60
        }
        response = requests.post(f"{API}/game/create", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["game"]["settings"]["call_interval"] == 60
        print("Regular mode 60s interval: PASS")


class TestBingoClaimVerification:
    """Test Bingo claiming and verification workflow"""
    
    def test_bingo_claim_and_confirm(self):
        """Test claiming bingo and confirming winner"""
        # Setup game
        payload = {"bingo_type": "music", "call_interval": 30}
        requests.post(f"{API}/game/create", json=payload)
        requests.post(f"{API}/game/start")
        
        # Claim bingo
        claim_resp = requests.post(f"{API}/game/bingo")
        assert claim_resp.status_code == 200
        assert claim_resp.json()["success"] == True
        
        # Verify game is paused
        state_resp = requests.get(f"{API}/game/state")
        assert state_resp.json()["game"]["is_paused"] == True
        assert state_resp.json()["game"]["bingo_claimed"] == True
        
        # Confirm bingo
        verify_resp = requests.post(f"{API}/game/verify-bingo", json={
            "winner_name": "Test Winner",
            "confirmed": True
        })
        assert verify_resp.status_code == 200
        
        # Check winner name set
        state_resp = requests.get(f"{API}/game/state")
        assert state_resp.json()["game"]["winner_name"] == "Test Winner"
        print("Bingo claim and confirm: PASS")
    
    def test_bingo_claim_and_reject(self):
        """Test claiming bingo and rejecting (false bingo)"""
        # Setup game
        payload = {"bingo_type": "music", "call_interval": 30}
        requests.post(f"{API}/game/create", json=payload)
        requests.post(f"{API}/game/start")
        
        # Claim bingo
        requests.post(f"{API}/game/bingo")
        
        # Reject bingo
        verify_resp = requests.post(f"{API}/game/verify-bingo", json={
            "winner_name": "Test Player",
            "confirmed": False
        })
        assert verify_resp.status_code == 200
        
        # Check game resumed
        state_resp = requests.get(f"{API}/game/state")
        assert state_resp.json()["game"]["is_paused"] == False
        assert state_resp.json()["game"]["bingo_claimed"] == False
        print("Bingo claim and reject: PASS")


class TestGamePauseResume:
    """Test pause and resume functionality"""
    
    def test_pause_game(self):
        """Test pausing a game"""
        payload = {"bingo_type": "music", "call_interval": 30}
        requests.post(f"{API}/game/create", json=payload)
        requests.post(f"{API}/game/start")
        
        pause_resp = requests.post(f"{API}/game/pause")
        assert pause_resp.status_code == 200
        assert pause_resp.json()["success"] == True
        
        state_resp = requests.get(f"{API}/game/state")
        assert state_resp.json()["game"]["is_paused"] == True
        print("Pause game: PASS")
    
    def test_resume_game(self):
        """Test resuming a paused game"""
        payload = {"bingo_type": "music", "call_interval": 30}
        requests.post(f"{API}/game/create", json=payload)
        requests.post(f"{API}/game/start")
        requests.post(f"{API}/game/pause")
        
        resume_resp = requests.post(f"{API}/game/resume")
        assert resume_resp.status_code == 200
        assert resume_resp.json()["success"] == True
        
        state_resp = requests.get(f"{API}/game/state")
        assert state_resp.json()["game"]["is_paused"] == False
        print("Resume game: PASS")


class TestRoundManagement:
    """Test round management functionality"""
    
    def test_end_round(self):
        """Test ending a round"""
        payload = {"bingo_type": "music", "call_interval": 30}
        requests.post(f"{API}/game/create", json=payload)
        requests.post(f"{API}/game/start")
        
        end_resp = requests.post(f"{API}/game/end-round")
        assert end_resp.status_code == 200
        assert end_resp.json()["success"] == True
        
        state_resp = requests.get(f"{API}/game/state")
        assert state_resp.json()["game"]["is_active"] == False
        print("End round: PASS")
    
    def test_new_round(self):
        """Test starting a new round"""
        payload = {"bingo_type": "music", "call_interval": 30}
        requests.post(f"{API}/game/create", json=payload)
        requests.post(f"{API}/game/start")
        
        # End current round first
        requests.post(f"{API}/game/end-round")
        
        # Start new round
        new_resp = requests.post(f"{API}/game/new-round")
        assert new_resp.status_code == 200
        assert new_resp.json()["success"] == True
        assert new_resp.json()["round_number"] >= 2
        
        state_resp = requests.get(f"{API}/game/state")
        assert state_resp.json()["game"]["called_numbers"] == []
        assert state_resp.json()["game"]["current_number"] is None
        print(f"New round: PASS (round {new_resp.json()['round_number']})")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
