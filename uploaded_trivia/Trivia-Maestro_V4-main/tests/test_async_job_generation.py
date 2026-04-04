"""
Async Job-Based Video Generation Tests
Tests for the new async job pattern to prevent Cloudflare 520 timeout errors:
- POST /api/story-generator/generate/{id} - returns immediately with jobId (< 2 seconds)
- GET /api/story-generator/job-status/{jobId} - returns progress, step, status
- Poll job-status until status='completed' or 'failed'
- Verify completed job has result with filename and downloadUrl
- Verify video file is downloadable after job completes
- Test with invalid presentation ID returns 404
- Test with invalid job ID returns 404
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


class TestAsyncJobGeneration:
    """Tests for async job-based video generation pattern"""
    
    def test_generate_returns_immediately_with_job_id(self):
        """
        Test that POST /api/story-generator/generate/{id} returns immediately (< 2 seconds)
        with a jobId instead of waiting for video completion.
        
        This is the key test for the async pattern - the endpoint should NOT block.
        """
        start_time = time.time()
        
        response = requests.post(
            f"{BASE_URL}/api/story-generator/generate/{PRESENTATION_ID_5_ROUNDS}",
            timeout=10  # Short timeout - should return quickly
        )
        
        elapsed_time = time.time() - start_time
        
        # CRITICAL: Response should be fast (< 2 seconds)
        assert elapsed_time < 2.0, f"Generate endpoint should return in < 2 seconds, took {elapsed_time:.2f}s"
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Verify response structure for async pattern
        assert data.get("success") == True, f"Response should have success=True, got: {data}"
        assert "jobId" in data, "Response should have 'jobId' field"
        assert "statusUrl" in data, "Response should have 'statusUrl' field"
        assert "message" in data, "Response should have 'message' field"
        
        # Verify jobId format (8 character hex)
        job_id = data["jobId"]
        assert len(job_id) == 8, f"jobId should be 8 characters, got: {job_id}"
        
        # Verify statusUrl format
        status_url = data["statusUrl"]
        assert f"/api/story-generator/job-status/{job_id}" in status_url, \
            f"statusUrl should contain job-status endpoint, got: {status_url}"
        
        print(f"✓ Generate endpoint returned in {elapsed_time:.2f}s (< 2s requirement)")
        print(f"  - jobId: {job_id}")
        print(f"  - statusUrl: {status_url}")
        print(f"  - message: {data['message']}")
        
        # Store job_id for subsequent tests
        TestAsyncJobGeneration.job_id = job_id
    
    def test_job_status_returns_progress(self):
        """
        Test that GET /api/story-generator/job-status/{jobId} returns progress info.
        """
        job_id = getattr(TestAsyncJobGeneration, 'job_id', None)
        if not job_id:
            pytest.skip("No job_id from previous test")
        
        response = requests.get(f"{BASE_URL}/api/story-generator/job-status/{job_id}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Verify response structure
        assert "jobId" in data, "Response should have 'jobId' field"
        assert "status" in data, "Response should have 'status' field"
        assert "progress" in data, "Response should have 'progress' field"
        assert "step" in data, "Response should have 'step' field"
        assert "presentationName" in data, "Response should have 'presentationName' field"
        assert "createdAt" in data, "Response should have 'createdAt' field"
        assert "updatedAt" in data, "Response should have 'updatedAt' field"
        
        # Verify status is valid
        assert data["status"] in ["queued", "processing", "completed", "failed"], \
            f"Status should be valid, got: {data['status']}"
        
        # Verify progress is 0-100
        assert 0 <= data["progress"] <= 100, f"Progress should be 0-100, got: {data['progress']}"
        
        print(f"✓ Job status returned:")
        print(f"  - jobId: {data['jobId']}")
        print(f"  - status: {data['status']}")
        print(f"  - progress: {data['progress']}%")
        print(f"  - step: {data['step']}")
    
    def test_poll_until_completion(self):
        """
        Test polling job-status until status='completed' or 'failed'.
        Verify progress increases: 5 -> 20 -> 35 -> 50 -> 65 -> 80 -> 95 -> 100
        """
        job_id = getattr(TestAsyncJobGeneration, 'job_id', None)
        if not job_id:
            pytest.skip("No job_id from previous test")
        
        max_attempts = 120  # 2 minutes with 1 second intervals
        attempt = 0
        last_progress = -1
        progress_history = []
        
        print(f"Polling job {job_id} until completion...")
        
        while attempt < max_attempts:
            response = requests.get(f"{BASE_URL}/api/story-generator/job-status/{job_id}")
            
            assert response.status_code == 200, f"Expected 200, got {response.status_code}"
            
            data = response.json()
            status = data["status"]
            progress = data["progress"]
            step = data["step"]
            
            # Track progress history
            if progress != last_progress:
                progress_history.append(progress)
                print(f"  [{attempt}s] {status}: {progress}% - {step}")
                last_progress = progress
            
            if status == "completed":
                # Verify result is present
                assert "result" in data, "Completed job should have 'result' field"
                result = data["result"]
                assert "filename" in result, "Result should have 'filename' field"
                assert "downloadUrl" in result, "Result should have 'downloadUrl' field"
                
                # Store for download test
                TestAsyncJobGeneration.completed_result = result
                
                print(f"✓ Job completed successfully!")
                print(f"  - filename: {result['filename']}")
                print(f"  - downloadUrl: {result['downloadUrl']}")
                print(f"  - Progress history: {progress_history}")
                
                # Verify progress increased over time
                assert len(progress_history) > 1, "Progress should have increased over time"
                assert progress_history[-1] == 100, "Final progress should be 100"
                
                return
            
            if status == "failed":
                error = data.get("error", "Unknown error")
                pytest.fail(f"Job failed with error: {error}")
            
            time.sleep(1)
            attempt += 1
        
        pytest.fail(f"Job did not complete within {max_attempts} seconds")
    
    def test_completed_job_has_valid_result(self):
        """
        Test that completed job has result with filename and downloadUrl.
        """
        result = getattr(TestAsyncJobGeneration, 'completed_result', None)
        if not result:
            pytest.skip("No completed result from previous test")
        
        # Verify filename is MP4
        filename = result["filename"]
        assert filename.endswith(".mp4"), f"Filename should end with .mp4, got: {filename}"
        
        # Verify downloadUrl format
        download_url = result["downloadUrl"]
        assert "/api/story-generator/download/" in download_url, \
            f"downloadUrl should contain download endpoint, got: {download_url}"
        
        # Verify stats if present
        if "stats" in result:
            stats = result["stats"]
            assert "totalTime" in stats, "Stats should have 'totalTime'"
            print(f"✓ Result has valid stats:")
            print(f"  - totalTime: {stats.get('totalTime')}s")
            print(f"  - videoSize: {stats.get('videoSize', 'N/A')}")
        
        print(f"✓ Completed job has valid result:")
        print(f"  - filename: {filename}")
        print(f"  - downloadUrl: {download_url}")
    
    def test_video_downloadable_after_completion(self):
        """
        Test that video file is downloadable after job completes.
        """
        result = getattr(TestAsyncJobGeneration, 'completed_result', None)
        if not result:
            pytest.skip("No completed result from previous test")
        
        filename = result["filename"]
        
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


class TestAsyncJobErrorHandling:
    """Tests for error handling in async job pattern"""
    
    def test_invalid_presentation_id_returns_404(self):
        """
        Test that POST /generate with invalid presentation ID returns 404.
        """
        response = requests.post(
            f"{BASE_URL}/api/story-generator/generate/invalid-presentation-id-12345",
            timeout=10
        )
        
        assert response.status_code == 404, f"Expected 404, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "detail" in data, "Error response should have 'detail' field"
        
        print(f"✓ Invalid presentation ID returns 404:")
        print(f"  - detail: {data['detail']}")
    
    def test_invalid_job_id_returns_404(self):
        """
        Test that GET /job-status with invalid job ID returns 404.
        """
        response = requests.get(
            f"{BASE_URL}/api/story-generator/job-status/invalid-job-id"
        )
        
        assert response.status_code == 404, f"Expected 404, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "detail" in data, "Error response should have 'detail' field"
        
        print(f"✓ Invalid job ID returns 404:")
        print(f"  - detail: {data['detail']}")


class TestAsyncJobCancellation:
    """Tests for job cancellation endpoint"""
    
    def test_cancel_job(self):
        """
        Test that DELETE /job/{jobId} cancels/removes a job.
        """
        # First create a job
        response = requests.post(
            f"{BASE_URL}/api/story-generator/generate/{PRESENTATION_ID_5_ROUNDS}",
            timeout=10
        )
        
        assert response.status_code == 200
        job_id = response.json()["jobId"]
        
        # Cancel the job
        response = requests.delete(f"{BASE_URL}/api/story-generator/job/{job_id}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("success") == True, "Response should have success=True"
        
        # Verify job is no longer accessible
        response = requests.get(f"{BASE_URL}/api/story-generator/job-status/{job_id}")
        assert response.status_code == 404, "Cancelled job should return 404"
        
        print(f"✓ Job {job_id} cancelled successfully")
    
    def test_cancel_nonexistent_job_returns_404(self):
        """
        Test that DELETE /job with invalid job ID returns 404.
        """
        response = requests.delete(
            f"{BASE_URL}/api/story-generator/job/nonexistent-job-id"
        )
        
        assert response.status_code == 404, f"Expected 404, got {response.status_code}: {response.text}"
        
        print("✓ Cancel nonexistent job returns 404")


class TestAsyncJob6RoundPresentation:
    """Tests for async job generation with 6-round presentation"""
    
    def test_generate_6_round_presentation_async(self):
        """
        Test async generation for 6-round presentation.
        """
        # Start job
        start_time = time.time()
        response = requests.post(
            f"{BASE_URL}/api/story-generator/generate/{PRESENTATION_ID_6_ROUNDS}",
            timeout=10
        )
        elapsed_time = time.time() - start_time
        
        assert elapsed_time < 2.0, f"Generate should return in < 2s, took {elapsed_time:.2f}s"
        assert response.status_code == 200
        
        job_id = response.json()["jobId"]
        print(f"✓ 6-round job started: {job_id} (in {elapsed_time:.2f}s)")
        
        # Poll until completion
        max_attempts = 120
        for attempt in range(max_attempts):
            response = requests.get(f"{BASE_URL}/api/story-generator/job-status/{job_id}")
            assert response.status_code == 200
            
            data = response.json()
            status = data["status"]
            progress = data["progress"]
            
            if attempt % 5 == 0:  # Log every 5 seconds
                print(f"  [{attempt}s] {status}: {progress}% - {data['step']}")
            
            if status == "completed":
                result = data["result"]
                assert "filename" in result
                assert "downloadUrl" in result
                
                # Verify stats has 6 resolved rounds
                if "stats" in result:
                    stats = result["stats"]
                    if "resolvedRounds" in stats:
                        assert len(stats["resolvedRounds"]) == 6, \
                            f"Expected 6 resolved rounds, got {len(stats['resolvedRounds'])}"
                        print(f"✓ 6-round job completed with rounds: {stats['resolvedRounds']}")
                
                return
            
            if status == "failed":
                pytest.fail(f"Job failed: {data.get('error')}")
            
            time.sleep(1)
        
        pytest.fail("Job did not complete in time")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
