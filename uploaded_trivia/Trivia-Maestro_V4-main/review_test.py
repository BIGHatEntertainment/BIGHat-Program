#!/usr/bin/env python3
"""
Review Test Suite for BIG Hat Presenter - Overlay Fix Verification
Tests the specific endpoints mentioned in the review request.
"""

import requests
import json
import sys
import os
from datetime import datetime

# Get backend URL from environment
BACKEND_URL = "https://smart-score-tracker.preview.emergentagent.com"
API_BASE = f"{BACKEND_URL}/api"

def log_test(message, status="INFO"):
    """Log test messages with timestamp"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] [{status}] {message}")

def test_health_check():
    """Test the health check endpoint: GET /api/"""
    log_test("Testing health check endpoint: GET /api/")
    try:
        response = requests.get(f"{API_BASE}/", timeout=10)
        if response.status_code == 200:
            data = response.json()
            message = data.get('message', '')
            log_test(f"✅ Health check passed: {message}", "SUCCESS")
            return True
        else:
            log_test(f"❌ Health check failed: {response.status_code} - {response.text}", "ERROR")
            return False
    except Exception as e:
        log_test(f"❌ Health check failed: {str(e)}", "ERROR")
        return False

def test_overlay_metadata():
    """Test overlay metadata: GET /api/overlays/metadata/01_Monkey%20Pants"""
    log_test("Testing overlay metadata endpoint...")
    try:
        location_name = "01_Monkey Pants"
        response = requests.get(f"{API_BASE}/overlays/metadata/{location_name}", timeout=15)
        
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                overlays = data.get('overlays', [])
                log_test(f"✅ Overlay metadata working - found {len(overlays)} overlays for {location_name}", "SUCCESS")
                
                # Show overlay details
                for overlay in overlays[:3]:  # Show first 3 overlays
                    name = overlay.get('name', 'Unknown')
                    overlay_type = overlay.get('type', 'Unknown')
                    round_number = overlay.get('roundNumber', 'None')
                    log_test(f"  Overlay: {name} (type: {overlay_type}, round: {round_number})", "INFO")
                
                return True
            else:
                log_test(f"❌ Overlay metadata returned success=false: {data}", "ERROR")
                return False
        else:
            log_test(f"❌ Overlay metadata failed: {response.status_code} - {response.text}", "ERROR")
            return False
    except Exception as e:
        log_test(f"❌ Overlay metadata failed: {str(e)}", "ERROR")
        return False

def test_overlay_image():
    """Test overlay image: GET /api/overlays/image?path=..."""
    log_test("Testing overlay image endpoint...")
    try:
        image_path = "01_Trivia/Web App/00_Builder/02_Locations/01_Monkey Pants/01_Multiple Choice.png"
        response = requests.get(
            f"{API_BASE}/overlays/image", 
            params={"path": image_path}, 
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                data_url = data.get('dataUrl', '')
                if data_url.startswith('data:image/png;base64,'):
                    log_test("✅ Overlay image working - valid base64 data URL returned", "SUCCESS")
                    log_test(f"  Data URL length: {len(data_url)} characters", "INFO")
                    return True
                else:
                    log_test(f"❌ Overlay image failed - invalid data URL format: {data_url[:100]}...", "ERROR")
                    return False
            else:
                log_test(f"❌ Overlay image failed: {data.get('error', 'Unknown error')}", "ERROR")
                return False
        else:
            log_test(f"❌ Overlay image failed: {response.status_code} - {response.text}", "ERROR")
            return False
    except Exception as e:
        log_test(f"❌ Overlay image failed: {str(e)}", "ERROR")
        return False

def test_presentations_list():
    """Test presentations list: GET /api/presentations?userName=Nick"""
    log_test("Testing presentations list endpoint with userName=Nick...")
    try:
        response = requests.get(f"{API_BASE}/presentations", params={"userName": "Nick"}, timeout=15)
        
        if response.status_code == 200:
            presentations = response.json()
            log_test(f"✅ Presentations endpoint working - found {len(presentations)} presentations", "SUCCESS")
            
            # Look for specific presentations
            for presentation in presentations:
                name = presentation.get('name', 'Unknown')
                pres_type = presentation.get('type', 'Unknown')
                pres_id = presentation.get('id', 'Unknown')
                log_test(f"  Presentation: {name} (type: {pres_type}, id: {pres_id})", "INFO")
            
            # Look for the specific presentation mentioned in the review
            monkey_pants_presentation = None
            for p in presentations:
                if "Monkey Pants" in p.get('name', '') or "01_Monkey Pants" in p.get('name', ''):
                    monkey_pants_presentation = p
                    break
            
            if monkey_pants_presentation:
                log_test(f"✅ Found Monkey Pants presentation: {monkey_pants_presentation.get('name')}", "SUCCESS")
            else:
                log_test("⚠️ Monkey Pants presentation not found in list", "WARNING")
            
            return True
        else:
            log_test(f"❌ Presentations endpoint failed: {response.status_code} - {response.text}", "ERROR")
            return False
    except Exception as e:
        log_test(f"❌ Presentations endpoint failed: {str(e)}", "ERROR")
        return False

def check_backend_logs():
    """Check backend logs for any errors"""
    log_test("Checking backend logs for errors...")
    try:
        log_files = [
            "/var/log/supervisor/backend.out.log",
            "/var/log/supervisor/backend.err.log"
        ]
        
        recent_errors = []
        
        for log_file in log_files:
            if os.path.exists(log_file):
                with open(log_file, 'r') as f:
                    lines = f.readlines()
                    # Check last 50 lines for recent errors
                    for line in lines[-50:]:
                        if "ERROR" in line or "Exception" in line or "Traceback" in line:
                            recent_errors.append(line.strip())
        
        if recent_errors:
            log_test(f"⚠️ Found {len(recent_errors)} recent errors in logs", "WARNING")
            for error in recent_errors[:5]:  # Show first 5 errors
                log_test(f"  {error}", "WARNING")
        else:
            log_test("✅ No recent errors found in backend logs", "SUCCESS")
        
        return len(recent_errors) == 0
        
    except Exception as e:
        log_test(f"⚠️ Could not check backend logs: {str(e)}", "WARNING")
        return True  # Don't fail if we can't read logs

def main():
    """Run the review-specific tests"""
    log_test("=" * 60)
    log_test("BIG HAT PRESENTER - OVERLAY FIX VERIFICATION")
    log_test("Testing specific endpoints from review request")
    log_test("=" * 60)
    
    results = {}
    
    # Test 1: Health check
    results['health_check'] = test_health_check()
    
    # Test 2: Overlay metadata
    results['overlay_metadata'] = test_overlay_metadata()
    
    # Test 3: Overlay image
    results['overlay_image'] = test_overlay_image()
    
    # Test 4: Presentations list
    results['presentations_list'] = test_presentations_list()
    
    # Test 5: Backend logs check
    results['backend_logs'] = check_backend_logs()
    
    # Summary
    log_test("=" * 60)
    log_test("TEST RESULTS SUMMARY")
    log_test("=" * 60)
    
    passed = 0
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        log_test(f"{test_name}: {status}")
        if result:
            passed += 1
    
    log_test("=" * 60)
    log_test(f"OVERALL: {passed}/{total} tests passed")
    
    if passed == total:
        log_test("🎉 ALL TESTS PASSED - Overlay fix is working correctly!", "SUCCESS")
        return 0
    else:
        log_test(f"⚠️ {total - passed} tests failed - Issues need attention", "WARNING")
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)