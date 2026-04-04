"""
Story Generator API Tests
Tests for Instagram Story video generation feature:
- GET /api/story-generator/presentations - returns list of presentations with round info
- GET /api/story-generator/assets - returns hosts (must be PNG type), locations, backgrounds
- POST /api/story-generator/generate/{presentation_id} - generates MP4 video successfully
- GET /api/story-generator/download/{filename} - downloads generated video
"""

import pytest
import requests
import os
import time

# Get BASE_URL from environment
BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    raise ValueError("REACT_APP_BACKEND_URL environment variable is required")

# Test credentials from review request
TEST_USER = "Nick"
PRESENTATION_ID_5_ROUNDS = "0e6b7efa-4d8d-4b58-85ae-1dc46fd1f220"
PRESENTATION_ID_6_ROUNDS = "96eb1f90-8011-4529-9975-83c75827aa8f"


class TestStoryGeneratorPresentations:
    """Tests for GET /api/story-generator/presentations endpoint"""
    
    def test_get_presentations_with_username(self):
        """Test getting presentations filtered by userName=Nick"""
        response = requests.get(
            f"{BASE_URL}/api/story-generator/presentations",
            params={"userName": TEST_USER}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        
        # Verify presentations have required fields
        if len(data) > 0:
            pres = data[0]
            assert "id" in pres, "Presentation should have 'id' field"
            assert "name" in pres, "Presentation should have 'name' field"
            assert "numRounds" in pres, "Presentation should have 'numRounds' field"
            print(f"✓ Found {len(data)} presentations for user {TEST_USER}")
            for p in data:
                print(f"  - {p['name']} ({p['numRounds']} rounds)")
    
    def test_get_presentations_without_username(self):
        """Test getting all presentations without userName filter"""
        response = requests.get(f"{BASE_URL}/api/story-generator/presentations")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        print(f"✓ Found {len(data)} total presentations")


class TestStoryGeneratorAssets:
    """Tests for GET /api/story-generator/assets endpoint"""
    
    def test_get_assets(self):
        """Test getting available assets (hosts, locations, backgrounds)"""
        response = requests.get(f"{BASE_URL}/api/story-generator/assets")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Verify response structure
        assert "locations" in data, "Response should have 'locations' field"
        assert "hosts" in data, "Response should have 'hosts' field"
        assert "backgrounds" in data, "Response should have 'backgrounds' field"
        assert "sharepoint_enabled" in data, "Response should have 'sharepoint_enabled' field"
        
        print(f"✓ Assets loaded:")
        print(f"  - Locations: {len(data['locations'])}")
        print(f"  - Hosts: {len(data['hosts'])}")
        print(f"  - Backgrounds: {len(data['backgrounds'])}")
        print(f"  - SharePoint enabled: {data['sharepoint_enabled']}")
    
    def test_hosts_are_png_type(self):
        """Test that host images are PNG type (not GIF)"""
        response = requests.get(f"{BASE_URL}/api/story-generator/assets")
        
        assert response.status_code == 200
        
        data = response.json()
        hosts = data.get("hosts", [])
        
        # Verify hosts are PNG images
        for host in hosts:
            path = host.get("path", "")
            # Host images should be PNG (not GIF)
            assert ".png" in path.lower() or ".jpg" in path.lower() or ".jpeg" in path.lower(), \
                f"Host {host.get('name')} should be PNG/JPG, got path: {path}"
            
            # Verify type is 'image' not 'gif'
            assert host.get("type") == "image", \
                f"Host {host.get('name')} type should be 'image', got: {host.get('type')}"
        
        print(f"✓ All {len(hosts)} hosts are static images (PNG/JPG)")
        for h in hosts:
            print(f"  - {h.get('name')}: {h.get('path', '').split('/')[-1]}")


class TestStoryGeneratorPresentation:
    """Tests for GET /api/story-generator/presentation/{id} endpoint"""
    
    def test_get_presentation_details_5_rounds(self):
        """Test getting presentation details for 5-round presentation"""
        response = requests.get(
            f"{BASE_URL}/api/story-generator/presentation/{PRESENTATION_ID_5_ROUNDS}"
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Verify required fields
        assert "id" in data, "Response should have 'id' field"
        assert "name" in data, "Response should have 'name' field"
        assert "location" in data, "Response should have 'location' field"
        assert "host" in data, "Response should have 'host' field"
        assert "rounds" in data, "Response should have 'rounds' field"
        assert "numRounds" in data, "Response should have 'numRounds' field"
        
        # Verify 5 rounds
        assert data["numRounds"] == 5, f"Expected 5 rounds, got {data['numRounds']}"
        assert len(data["rounds"]) == 5, f"Expected 5 rounds in list, got {len(data['rounds'])}"
        
        print(f"✓ Presentation '{data['name']}' has {data['numRounds']} rounds:")
        for r in data["rounds"]:
            print(f"  - {r.get('type')}: {r.get('name')}")
    
    def test_get_presentation_details_6_rounds(self):
        """Test getting presentation details for 6-round presentation"""
        response = requests.get(
            f"{BASE_URL}/api/story-generator/presentation/{PRESENTATION_ID_6_ROUNDS}"
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Verify 6 rounds
        assert data["numRounds"] == 6, f"Expected 6 rounds, got {data['numRounds']}"
        assert len(data["rounds"]) == 6, f"Expected 6 rounds in list, got {len(data['rounds'])}"
        
        print(f"✓ Presentation '{data['name']}' has {data['numRounds']} rounds:")
        for r in data["rounds"]:
            print(f"  - {r.get('type')}: {r.get('name')}")
    
    def test_get_nonexistent_presentation(self):
        """Test getting a non-existent presentation returns 404"""
        response = requests.get(
            f"{BASE_URL}/api/story-generator/presentation/nonexistent-id-12345"
        )
        
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("✓ Non-existent presentation returns 404")


class TestStoryGeneratorPreview:
    """Tests for POST /api/story-generator/preview/{id} endpoint"""
    
    def test_generate_preview_5_rounds(self):
        """Test generating preview for 5-round presentation"""
        response = requests.post(
            f"{BASE_URL}/api/story-generator/preview/{PRESENTATION_ID_5_ROUNDS}"
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Verify response structure
        assert data.get("success") == True, "Response should have success=True"
        assert "preview" in data, "Response should have 'preview' field"
        
        preview = data["preview"]
        assert "location" in preview, "Preview should have 'location' field"
        assert "host" in preview, "Preview should have 'host' field"
        assert "rounds" in preview, "Preview should have 'rounds' field"
        assert "totalDuration" in preview, "Preview should have 'totalDuration' field"
        
        # Verify total duration is 25 seconds
        assert preview["totalDuration"] == 25, f"Expected 25s duration, got {preview['totalDuration']}"
        
        print(f"✓ Preview generated:")
        print(f"  - Location: {preview['location']['name']} (hasAsset: {preview['location']['hasAsset']})")
        print(f"  - Host: {preview['host']['name']} (hasAsset: {preview['host']['hasAsset']})")
        print(f"  - Rounds: {preview['rounds']['numRounds']} (hasBackground: {preview['rounds']['hasBackground']})")
        print(f"  - Total Duration: {preview['totalDuration']}s")


class TestStoryGeneratorVideoGeneration:
    """Tests for POST /api/story-generator/generate/{id} endpoint
    
    New in this iteration: Verify stats object with step timing info
    - step2Time: Location image fetch time
    - step3Time: Host image fetch time
    - step4Time: Background image fetch time
    - step5Time: Overlay generation time
    - step6Time: Video encoding time
    - locationImage, hostImage, backgroundImage: Status (loaded/placeholder)
    - overlay, encoding: Status (created/success)
    """
    
    generated_filename = None
    
    def test_generate_video_5_rounds_with_stats(self):
        """Test generating video for 5-round presentation and verify stats object"""
        print("Starting video generation for 5-round presentation (this may take ~30-60 seconds)...")
        
        response = requests.post(
            f"{BASE_URL}/api/story-generator/generate/{PRESENTATION_ID_5_ROUNDS}",
            timeout=120  # 2 minute timeout
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Verify response structure
        assert data.get("success") == True, f"Response should have success=True, got: {data}"
        assert "filename" in data, "Response should have 'filename' field"
        assert "downloadUrl" in data, "Response should have 'downloadUrl' field"
        assert "stats" in data, "Response should have 'stats' field with timing info"
        
        # Verify filename is MP4
        filename = data["filename"]
        assert filename.endswith(".mp4"), f"Filename should end with .mp4, got: {filename}"
        
        # Verify stats object contains required timing fields
        stats = data["stats"]
        assert "totalTime" in stats, "Stats should have 'totalTime' field"
        assert "step2Time" in stats, "Stats should have 'step2Time' (location fetch time)"
        assert "step3Time" in stats, "Stats should have 'step3Time' (host fetch time)"
        assert "step4Time" in stats, "Stats should have 'step4Time' (background fetch time)"
        assert "step5Time" in stats, "Stats should have 'step5Time' (overlay generation time)"
        assert "step6Time" in stats, "Stats should have 'step6Time' (video encoding time)"
        
        # Verify stats object contains status fields
        assert "locationImage" in stats, "Stats should have 'locationImage' status"
        assert "hostImage" in stats, "Stats should have 'hostImage' status"
        assert "backgroundImage" in stats, "Stats should have 'backgroundImage' status"
        assert "overlay" in stats, "Stats should have 'overlay' status"
        assert "encoding" in stats, "Stats should have 'encoding' status"
        
        # Verify status values are valid
        assert stats["locationImage"] in ["loaded", "placeholder"], f"locationImage should be 'loaded' or 'placeholder', got: {stats['locationImage']}"
        assert stats["hostImage"] in ["loaded", "placeholder"], f"hostImage should be 'loaded' or 'placeholder', got: {stats['hostImage']}"
        assert stats["backgroundImage"] in ["loaded", "placeholder"], f"backgroundImage should be 'loaded' or 'placeholder', got: {stats['backgroundImage']}"
        assert stats["overlay"] == "created", f"overlay should be 'created', got: {stats['overlay']}"
        assert stats["encoding"] == "success", f"encoding should be 'success', got: {stats['encoding']}"
        
        # Store filename for download test
        TestStoryGeneratorVideoGeneration.generated_filename = filename
        
        print(f"✓ Video generated successfully with stats:")
        print(f"  - Filename: {filename}")
        print(f"  - Download URL: {data['downloadUrl']}")
        print(f"  - Total Time: {stats['totalTime']}s")
        print(f"  - Step 2 (Location): {stats['step2Time']}s - {stats['locationImage']}")
        print(f"  - Step 3 (Host): {stats['step3Time']}s - {stats['hostImage']}")
        print(f"  - Step 4 (Background): {stats['step4Time']}s - {stats['backgroundImage']}")
        print(f"  - Step 5 (Overlay): {stats['step5Time']}s - {stats['overlay']}")
        print(f"  - Step 6 (Encoding): {stats['step6Time']}s - {stats['encoding']}")
    
    def test_generate_video_6_rounds_with_stats(self):
        """Test generating video for 6-round presentation and verify stats object"""
        print("Starting video generation for 6-round presentation (this may take ~30-60 seconds)...")
        
        response = requests.post(
            f"{BASE_URL}/api/story-generator/generate/{PRESENTATION_ID_6_ROUNDS}",
            timeout=120  # 2 minute timeout
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Verify response structure
        assert data.get("success") == True, f"Response should have success=True, got: {data}"
        assert "stats" in data, "Response should have 'stats' field with timing info"
        
        # Verify stats object contains required timing fields
        stats = data["stats"]
        assert "step2Time" in stats, "Stats should have 'step2Time' (location fetch time)"
        assert "step3Time" in stats, "Stats should have 'step3Time' (host fetch time)"
        assert "step4Time" in stats, "Stats should have 'step4Time' (background fetch time)"
        assert "step5Time" in stats, "Stats should have 'step5Time' (overlay generation time)"
        assert "step6Time" in stats, "Stats should have 'step6Time' (video encoding time)"
        
        # Verify resolvedRounds is present for 6-round presentation
        assert "resolvedRounds" in stats, "Stats should have 'resolvedRounds' list"
        assert len(stats["resolvedRounds"]) == 6, f"Expected 6 resolved rounds, got {len(stats['resolvedRounds'])}"
        
        print(f"✓ 6-round video generated successfully with stats:")
        print(f"  - Filename: {data['filename']}")
        print(f"  - Total Time: {stats['totalTime']}s")
        print(f"  - Resolved Rounds: {stats['resolvedRounds']}")
        print(f"  - Step timings: 2={stats['step2Time']}s, 3={stats['step3Time']}s, 4={stats['step4Time']}s, 5={stats['step5Time']}s, 6={stats['step6Time']}s")
    
    def test_download_generated_video(self):
        """Test downloading the generated video"""
        filename = TestStoryGeneratorVideoGeneration.generated_filename
        
        if not filename:
            pytest.skip("No video was generated in previous test")
        
        response = requests.get(
            f"{BASE_URL}/api/story-generator/download/{filename}",
            stream=True
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        # Verify content type is video/mp4
        content_type = response.headers.get("content-type", "")
        assert "video/mp4" in content_type, f"Expected video/mp4 content type, got: {content_type}"
        
        # Verify we got some content
        content_length = int(response.headers.get("content-length", 0))
        assert content_length > 0, "Video file should have content"
        
        print(f"✓ Video downloaded successfully:")
        print(f"  - Content-Type: {content_type}")
        print(f"  - Content-Length: {content_length} bytes ({content_length / 1024 / 1024:.2f} MB)")
    
    def test_download_nonexistent_video(self):
        """Test downloading a non-existent video returns 404"""
        response = requests.get(
            f"{BASE_URL}/api/story-generator/download/nonexistent_video.mp4"
        )
        
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("✓ Non-existent video returns 404")


class TestStoryGeneratorRefreshAssets:
    """Tests for POST /api/story-generator/refresh-assets endpoint"""
    
    def test_refresh_assets(self):
        """Test refreshing assets from SharePoint"""
        response = requests.post(f"{BASE_URL}/api/story-generator/refresh-assets")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Verify response structure
        assert data.get("success") == True, "Response should have success=True"
        assert "counts" in data, "Response should have 'counts' field"
        
        counts = data["counts"]
        print(f"✓ Assets refreshed:")
        print(f"  - Locations: {counts.get('locations', 0)}")
        print(f"  - Hosts: {counts.get('hosts', 0)}")
        print(f"  - Backgrounds: {counts.get('backgrounds', 0)}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
