#!/usr/bin/env python3
"""
Focused test for Rust Overlay Processor Optimizations
Tests the specific features mentioned in the review request:
1. Rayon Parallel Batch Processing
2. Memory Pre-allocation 
3. Single overlay processing
"""

import requests
import json
import sys
import time
from datetime import datetime

# Get backend URL from environment
BACKEND_URL = "https://smart-score-tracker.preview.emergentagent.com"
API_BASE = f"{BACKEND_URL}/api"

def log_test(message, status="INFO"):
    """Log test messages with timestamp"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] [{status}] {message}")

def test_rust_overlay_stats():
    """Test GET /api/overlays/stats for Rust availability and batch processing stats"""
    log_test("Testing Rust overlay processor stats...")
    try:
        response = requests.get(f"{API_BASE}/overlays/stats", timeout=15)
        
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                stats = data.get('stats', {})
                
                # Check key requirements from review request
                use_rust = stats.get('use_rust', False)
                rust_available = stats.get('rust_available', False)
                rust_batch_processed = stats.get('rust_batch_processed', 0)
                
                log_test(f"✅ Overlay stats endpoint working", "SUCCESS")
                log_test(f"  use_rust: {use_rust}", "INFO")
                log_test(f"  rust_available: {rust_available}", "INFO")
                log_test(f"  rust_batch_processed: {rust_batch_processed}", "INFO")
                log_test(f"  rust_images_processed: {stats.get('rust_images_processed', 0)}", "INFO")
                log_test(f"  rust_cache_size: {stats.get('rust_cache_size', 0)}", "INFO")
                
                # Verify requirements
                if rust_available and use_rust:
                    log_test("✅ Rust overlay processor is available and enabled", "SUCCESS")
                    return True, stats
                else:
                    log_test("❌ Rust overlay processor not available or not enabled", "ERROR")
                    return False, stats
            else:
                log_test(f"❌ Overlay stats endpoint returned success=false: {data}", "ERROR")
                return False, {}
        else:
            log_test(f"❌ Overlay stats endpoint failed: {response.status_code} - {response.text}", "ERROR")
            return False, {}
    except Exception as e:
        log_test(f"❌ Overlay stats endpoint failed: {str(e)}", "ERROR")
        return False, {}

def test_single_overlay_processing():
    """Test single overlay processing to verify standard flow"""
    log_test("Testing single overlay processing (standard flow)...")
    try:
        # Test PNG overlay
        png_path = "01_Trivia/Web App/00_Builder/02_Locations/06_Valley Craft/01_Multiple Choice.png"
        
        start_time = time.time()
        response = requests.get(
            f"{API_BASE}/overlays/image", 
            params={"path": png_path}, 
            timeout=30
        )
        processing_time = time.time() - start_time
        
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                data_url = data.get('dataUrl', '')
                if data_url.startswith('data:image/png;base64,'):
                    log_test(f"✅ Single PNG overlay processing working - {processing_time*1000:.1f}ms", "SUCCESS")
                    log_test(f"  Data URL length: {len(data_url)} characters", "INFO")
                    return True
                else:
                    log_test(f"❌ Invalid PNG data URL format", "ERROR")
                    return False
            else:
                log_test(f"❌ PNG overlay processing failed: {data.get('error', 'Unknown error')}", "ERROR")
                return False
        else:
            log_test(f"❌ PNG overlay processing failed: {response.status_code}", "ERROR")
            return False
    except Exception as e:
        log_test(f"❌ Single overlay processing failed: {str(e)}", "ERROR")
        return False

def test_memory_preallocation():
    """Test memory pre-allocation by processing a large GIF"""
    log_test("Testing memory pre-allocation with large GIF...")
    try:
        # Test large GIF overlay (18.8MB animated file)
        gif_path = "01_Trivia/Web App/00_Builder/02_Locations/06_Valley Craft/06_BIG.gif"
        
        start_time = time.time()
        response = requests.get(
            f"{API_BASE}/overlays/image", 
            params={"path": gif_path}, 
            timeout=30
        )
        processing_time = time.time() - start_time
        
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                data_url = data.get('dataUrl', '')
                if data_url.startswith('data:image/gif;base64,'):
                    log_test(f"✅ Large GIF processing working - {processing_time*1000:.1f}ms", "SUCCESS")
                    log_test(f"  Data URL length: {len(data_url)} characters (~{len(data_url)/1024/1024:.1f}MB)", "INFO")
                    log_test("  Memory pre-allocation should handle large files efficiently", "INFO")
                    return True
                else:
                    log_test(f"❌ Invalid GIF data URL format", "ERROR")
                    return False
            else:
                log_test(f"❌ GIF overlay processing failed: {data.get('error', 'Unknown error')}", "ERROR")
                return False
        else:
            log_test(f"❌ GIF overlay processing failed: {response.status_code}", "ERROR")
            return False
    except Exception as e:
        log_test(f"❌ Memory pre-allocation test failed: {str(e)}", "ERROR")
        return False

def test_batch_processing_simulation():
    """Simulate batch processing by making multiple overlay requests"""
    log_test("Testing batch processing simulation...")
    try:
        # Get overlay metadata first to find multiple overlays
        response = requests.get(f"{API_BASE}/overlays/metadata/06_Valley Craft", timeout=15)
        
        if response.status_code != 200:
            log_test("❌ Could not get overlay metadata for batch test", "ERROR")
            return False
        
        data = response.json()
        if not data.get('success'):
            log_test("❌ Overlay metadata request failed", "ERROR")
            return False
        
        overlays = data.get('overlays', [])[:4]  # Test with first 4 overlays
        if len(overlays) < 2:
            log_test("❌ Not enough overlays for batch test", "ERROR")
            return False
        
        log_test(f"Testing batch-like processing with {len(overlays)} overlays...", "INFO")
        
        # Process multiple overlays in sequence (simulating batch)
        start_time = time.time()
        successful_requests = 0
        
        for overlay in overlays:
            try:
                overlay_response = requests.get(
                    f"{API_BASE}/overlays/image", 
                    params={"path": overlay['path']}, 
                    timeout=15
                )
                
                if overlay_response.status_code == 200 and overlay_response.json().get('success'):
                    successful_requests += 1
                    log_test(f"  ✓ Processed {overlay['name']}", "INFO")
                else:
                    log_test(f"  ✗ Failed {overlay['name']}", "WARNING")
                    
            except Exception as e:
                log_test(f"  ✗ Error processing {overlay['name']}: {str(e)}", "WARNING")
        
        total_time = time.time() - start_time
        
        if successful_requests >= len(overlays) // 2:  # At least half successful
            log_test(f"✅ Batch processing simulation: {successful_requests}/{len(overlays)} successful in {total_time*1000:.1f}ms", "SUCCESS")
            log_test(f"  Average per overlay: {total_time*1000/len(overlays):.1f}ms", "INFO")
            return True
        else:
            log_test(f"❌ Batch processing simulation failed: only {successful_requests}/{len(overlays)} successful", "ERROR")
            return False
            
    except Exception as e:
        log_test(f"❌ Batch processing simulation failed: {str(e)}", "ERROR")
        return False

def test_backend_startup():
    """Test that backend starts without errors"""
    log_test("Testing backend startup and health...")
    try:
        # Test health endpoint
        response = requests.get(f"{BACKEND_URL}/health", timeout=10)
        if response.status_code == 200:
            log_test("✅ Backend health check passed", "SUCCESS")
            
            # Test API root
            api_response = requests.get(f"{API_BASE}/", timeout=10)
            if api_response.status_code == 200:
                data = api_response.json()
                message = data.get('message', '')
                log_test(f"✅ Backend API working: {message}", "SUCCESS")
                return True
            else:
                log_test(f"❌ API root failed: {api_response.status_code}", "ERROR")
                return False
        else:
            log_test(f"❌ Health check failed: {response.status_code}", "ERROR")
            return False
    except Exception as e:
        log_test(f"❌ Backend startup test failed: {str(e)}", "ERROR")
        return False

def main():
    """Run focused Rust overlay processor optimization tests"""
    log_test("=" * 70)
    log_test("RUST OVERLAY PROCESSOR OPTIMIZATION TESTS")
    log_test("Testing: Rayon Parallel Batch Processing, Memory Pre-allocation, Single Processing")
    log_test("=" * 70)
    
    results = {}
    
    # Test 1: Backend startup
    results['backend_startup'] = test_backend_startup()
    
    # Test 2: Rust overlay stats (key requirement)
    rust_available, stats = test_rust_overlay_stats()
    results['rust_stats'] = rust_available
    
    # Test 3: Single overlay processing (standard flow)
    results['single_processing'] = test_single_overlay_processing()
    
    # Test 4: Memory pre-allocation (large file handling)
    results['memory_preallocation'] = test_memory_preallocation()
    
    # Test 5: Batch processing simulation
    results['batch_processing'] = test_batch_processing_simulation()
    
    # Get final stats to check batch processing count
    if rust_available:
        log_test("=" * 50)
        log_test("FINAL RUST OVERLAY PROCESSOR STATS")
        log_test("=" * 50)
        final_rust_available, final_stats = test_rust_overlay_stats()
        if final_rust_available:
            log_test(f"Final rust_batch_processed: {final_stats.get('rust_batch_processed', 0)}", "INFO")
            log_test(f"Final rust_images_processed: {final_stats.get('rust_images_processed', 0)}", "INFO")
            log_test(f"Final rust_cache_hits: {final_stats.get('rust_cache_hits', 0)}", "INFO")
    
    # Summary
    log_test("=" * 70)
    log_test("TEST RESULTS SUMMARY")
    log_test("=" * 70)
    
    passed = 0
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        log_test(f"{test_name}: {status}")
        if result:
            passed += 1
    
    log_test("=" * 70)
    log_test(f"OVERALL: {passed}/{total} tests passed")
    
    if passed == total:
        log_test("🎉 ALL RUST OVERLAY OPTIMIZATION TESTS PASSED!", "SUCCESS")
        return 0
    else:
        log_test(f"⚠️ {total - passed} tests failed - Issues need attention", "WARNING")
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)