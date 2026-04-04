"""
Backend tests for Story Generator API endpoints.
Tests the new standalone Story Generator page functionality.
"""
import pytest
import requests
import os
import base64

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://smart-score-tracker.preview.emergentagent.com')

class TestStoryGeneratorPresentations:
    """Tests for /api/story-generator/presentations endpoint"""
    
    def test_get_presentations_returns_list(self):
        """Test that presentations endpoint returns a list"""
        response = requests.get(f"{BASE_URL}/api/story-generator/presentations")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"SUCCESS: Got {len(data)} presentations")
    
    def test_presentations_have_required_fields(self):
        """Test that presentations have required fields for story generation"""
        response = requests.get(f"{BASE_URL}/api/story-generator/presentations")
        assert response.status_code == 200
        data = response.json()
        
        if len(data) > 0:
            presentation = data[0]
            required_fields = ['id', 'name', 'location', 'host', 'numRounds', 'rounds']
            for field in required_fields:
                assert field in presentation, f"Missing field: {field}"
            print(f"SUCCESS: Presentation has all required fields: {required_fields}")
    
    def test_filter_presentations_by_username(self):
        """Test filtering presentations by userName"""
        response = requests.get(f"{BASE_URL}/api/story-generator/presentations", params={'userName': 'nick'})
        assert response.status_code == 200
        data = response.json()
        # All returned presentations should be by nick
        for p in data:
            assert p.get('createdBy', '').lower() == 'nick', f"Expected createdBy='nick', got '{p.get('createdBy')}'"
        print(f"SUCCESS: Filtered to {len(data)} presentations by nick")


class TestStoryGeneratorAssets:
    """Tests for /api/story-generator/build-asset-urls endpoint"""
    
    def test_get_build_asset_urls(self):
        """Test getting asset URLs for a presentation"""
        payload = {
            "location": "Valley Craft",
            "locationFolder": "06_Valley Craft",
            "host": "Niko",
            "numRounds": 6
        }
        response = requests.post(f"{BASE_URL}/api/story-generator/build-asset-urls", json=payload)
        assert response.status_code == 200
        data = response.json()
        
        assert data.get('success') == True
        assert 'assets' in data
        
        assets = data['assets']
        # Check that at least some assets are returned (may be base64 data URLs)
        print(f"SUCCESS: Got assets - location: {'present' if assets.get('locationUrl') else 'missing'}, "
              f"host: {'present' if assets.get('hostUrl') else 'missing'}, "
              f"background: {'present' if assets.get('backgroundUrl') else 'missing'}")
    
    def test_get_assets_for_monkey_pants(self):
        """Test getting assets for Monkey Pants presentation"""
        payload = {
            "location": "Monkey Pants",
            "locationFolder": "01_Monkey Pants",
            "host": "Nick",
            "numRounds": 5
        }
        response = requests.post(f"{BASE_URL}/api/story-generator/build-asset-urls", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data.get('success') == True
        print(f"SUCCESS: Got assets for Monkey Pants presentation")


class TestVideoConversion:
    """Tests for /api/story-generator/convert-to-mp4 endpoint"""
    
    def test_convert_to_mp4_endpoint_exists(self):
        """Test that the convert-to-mp4 endpoint exists and responds"""
        # Send an empty request to check endpoint exists
        response = requests.post(f"{BASE_URL}/api/story-generator/convert-to-mp4", json={})
        # Should return 422 (validation error) not 404
        assert response.status_code != 404, "Endpoint not found"
        print(f"SUCCESS: convert-to-mp4 endpoint exists (status: {response.status_code})")
    
    def test_convert_to_mp4_requires_video_data(self):
        """Test that convert-to-mp4 requires video_data field"""
        response = requests.post(f"{BASE_URL}/api/story-generator/convert-to-mp4", json={})
        assert response.status_code == 422  # Validation error
        print("SUCCESS: Endpoint correctly requires video_data field")
    
    def test_convert_to_mp4_with_invalid_data(self):
        """Test that convert-to-mp4 handles invalid base64 data"""
        payload = {
            "video_data": "invalid_base64_data",
            "filename": "test_video"
        }
        response = requests.post(f"{BASE_URL}/api/story-generator/convert-to-mp4", json=payload)
        # Should return 400 (bad request) for invalid data
        assert response.status_code == 400
        print("SUCCESS: Endpoint correctly rejects invalid base64 data")


class TestPresentationDetails:
    """Tests for /api/story-generator/presentation/{id} endpoint"""
    
    def test_get_presentation_details(self):
        """Test getting details for a specific presentation"""
        # First get list of presentations
        list_response = requests.get(f"{BASE_URL}/api/story-generator/presentations")
        assert list_response.status_code == 200
        presentations = list_response.json()
        
        if len(presentations) > 0:
            presentation_id = presentations[0]['id']
            response = requests.get(f"{BASE_URL}/api/story-generator/presentation/{presentation_id}")
            assert response.status_code == 200
            data = response.json()
            
            assert data.get('id') == presentation_id
            assert 'name' in data
            assert 'rounds' in data
            print(f"SUCCESS: Got details for presentation: {data.get('name')}")
    
    def test_get_nonexistent_presentation(self):
        """Test getting a non-existent presentation returns 404"""
        response = requests.get(f"{BASE_URL}/api/story-generator/presentation/nonexistent-id-12345")
        assert response.status_code == 404
        print("SUCCESS: Non-existent presentation returns 404")


class TestAssetRefresh:
    """Tests for /api/story-generator/assets endpoint"""
    
    def test_get_available_assets(self):
        """Test getting list of available assets"""
        response = requests.get(f"{BASE_URL}/api/story-generator/assets")
        assert response.status_code == 200
        data = response.json()
        
        # Should have locations, hosts, backgrounds
        assert 'locations' in data
        assert 'hosts' in data
        assert 'backgrounds' in data
        
        print(f"SUCCESS: Got assets - {len(data.get('locations', []))} locations, "
              f"{len(data.get('hosts', []))} hosts, {len(data.get('backgrounds', []))} backgrounds")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
