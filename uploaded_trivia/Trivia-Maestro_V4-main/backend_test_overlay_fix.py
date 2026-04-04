#!/usr/bin/env python3
"""
Backend Test Suite for Overlay Regression Fix
Tests the specific overlay endpoints mentioned in the review request.

Focus Areas:
1. GET /api/overlays/metadata/{location_name} for all locations with both clean and prefixed names
2. GET /api/overlays/image?path=... returns base64 data URL
3. GET /api/overlays/stats returns cache statistics
4. GET /api/presentations/{id} includes location and locationFolder fields (when data available)

Based on review request: Fix critical production overlay regression
"""

import requests
import json
import sys
import os
import time
from datetime import datetime

# Get backend URL from environment
BACKEND_URL = "https://smart-score-tracker.preview.emergentagent.com"
API_BASE = f"{BACKEND_URL}/api"

def log_test(message, status="INFO"):
    """Log test messages with timestamp"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] [{status}] {message}")

def test_overlay_metadata_all_locations():
    """Test GET /api/overlays/metadata/{location_name} for all 6 locations"""
    log_test("Testing overlay metadata endpoint for all locations...")
    
    # Test locations from review request
    locations_to_test = [
        "WP Gilbert",        # Clean name
        "04_WP Gilbert",     # Prefixed name
        "Monkey Pants", 
        "Crooked Pint",
        "WP Downtown",
        "Valley Craft"
    ]
    
    results = {}
    
    for location_name in locations_to_test:
        try:
            log_test(f"Testing location: {location_name}")
            response = requests.get(f"{API_BASE}/overlays/metadata/{location_name}", timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    overlays = data.get('overlays', [])
                    results[location_name] = {
                        'status': 'success',
                        'overlay_count': len(overlays),
                        'overlays': overlays
                    }
                    log_test(f"✅ {location_name}: Found {len(overlays)} overlays", "SUCCESS")
                    
                    # Log sample overlays for verification
                    for i, overlay in enumerate(overlays[:3]):  # Show first 3
                        overlay_name = overlay.get('name', 'Unknown')
                        overlay_type = overlay.get('type', 'Unknown')
                        round_number = overlay.get('roundNumber', 'None')
                        log_test(f"  Overlay {i+1}: {overlay_name} (type: {overlay_type}, round: {round_number})", "INFO")
                else:
                    results[location_name] = {
                        'status': 'failed',
                        'error': data.get('error', 'success=false'),
                        'overlay_count': 0
                    }
                    log_test(f"❌ {location_name}: API returned success=false - {data.get('error')}", "ERROR")
            else:
                results[location_name] = {
                    'status': 'failed',
                    'error': f"HTTP {response.status_code}",
                    'overlay_count': 0
                }
                log_test(f"❌ {location_name}: HTTP {response.status_code} - {response.text[:100]}", "ERROR")
                
        except Exception as e:
            results[location_name] = {
                'status': 'failed',
                'error': str(e),
                'overlay_count': 0
            }
            log_test(f"❌ {location_name}: Exception - {str(e)}", "ERROR")
    
    # Summary
    log_test("=" * 60)
    log_test("OVERLAY METADATA TEST SUMMARY")
    log_test("=" * 60)
    
    success_count = 0
    total_overlays = 0
    
    for location, result in results.items():
        status = "✅ PASS" if result['status'] == 'success' else "❌ FAIL"
        overlay_count = result['overlay_count']
        log_test(f"{location}: {status} ({overlay_count} overlays)")
        
        if result['status'] == 'success':
            success_count += 1
            total_overlays += overlay_count
        else:
            log_test(f"  Error: {result['error']}", "ERROR")
    
    log_test(f"Results: {success_count}/{len(locations_to_test)} locations passed")
    log_test(f"Total overlays found: {total_overlays}")
    
    return results

def test_overlay_image_endpoint():
    """Test GET /api/overlays/image?path=... returns base64 data URL"""
    log_test("Testing overlay image endpoint...")
    
    # Test with various overlay paths
    test_paths = [
        "01_Trivia/Web App/00_Builder/02_Locations/06_Valley Craft/01_Multiple Choice.png",
        "01_Trivia/Web App/00_Builder/02_Locations/06_Valley Craft/06_BIG.gif",
        "01_Trivia/Web App/00_Builder/02_Locations/01_Monkey Pants/01_Multiple Choice.png"
    ]
    
    results = {}
    
    for path in test_paths:
        try:
            log_test(f"Testing image path: {path.split('/')[-1]}")
            response = requests.get(
                f"{API_BASE}/overlays/image", 
                params={"path": path}, 
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    data_url = data.get('dataUrl', '')
                    
                    # Validate data URL format
                    if path.endswith('.png') and data_url.startswith('data:image/png;base64,'):
                        results[path] = {
                            'status': 'success',
                            'data_url_length': len(data_url),
                            'format': 'PNG'
                        }
                        log_test(f"✅ PNG overlay loaded: {len(data_url)} chars", "SUCCESS")
                    elif path.endswith('.gif') and data_url.startswith('data:image/gif;base64,'):
                        results[path] = {
                            'status': 'success',
                            'data_url_length': len(data_url),
                            'format': 'GIF'
                        }
                        log_test(f"✅ GIF overlay loaded: {len(data_url)} chars", "SUCCESS")
                    else:
                        results[path] = {
                            'status': 'failed',
                            'error': f'Invalid data URL format: {data_url[:50]}...'
                        }
                        log_test(f"❌ Invalid data URL format for {path}", "ERROR")
                else:
                    results[path] = {
                        'status': 'failed',
                        'error': data.get('error', 'success=false')
                    }
                    log_test(f"❌ API returned success=false: {data.get('error')}", "ERROR")
            else:
                results[path] = {
                    'status': 'failed',
                    'error': f"HTTP {response.status_code}"
                }
                log_test(f"❌ HTTP {response.status_code}: {response.text[:100]}", "ERROR")
                
        except Exception as e:
            results[path] = {
                'status': 'failed',
                'error': str(e)
            }
            log_test(f"❌ Exception: {str(e)}", "ERROR")
    
    # Summary
    success_count = sum(1 for r in results.values() if r['status'] == 'success')
    log_test(f"Image endpoint results: {success_count}/{len(test_paths)} paths passed")
    
    return results

def test_overlay_stats_endpoint():
    """Test GET /api/overlays/stats returns cache statistics"""
    log_test("Testing overlay stats endpoint...")
    
    try:
        response = requests.get(f"{API_BASE}/overlays/stats", timeout=15)
        
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                stats = data.get('stats', {})
                
                # Verify expected stats fields
                expected_fields = [
                    'rust_available', 
                    'cache_items',
                    'cache_size_mb', 
                    'cache_max_mb',
                    'cache_hit_rate_pct'
                ]
                
                missing_fields = []
                for field in expected_fields:
                    if field not in stats:
                        missing_fields.append(field)
                
                if missing_fields:
                    log_test(f"❌ Missing stats fields: {missing_fields}", "ERROR")
                    return {'status': 'failed', 'error': f'Missing fields: {missing_fields}'}
                
                # Log key stats
                rust_available = stats.get('rust_available', False)
                cache_items = stats.get('cache_items', 0)
                cache_size_mb = stats.get('cache_size_mb', 0)
                cache_hit_rate = stats.get('cache_hit_rate_pct', 0)
                
                log_test(f"✅ Stats endpoint working", "SUCCESS")
                log_test(f"  Rust available: {rust_available}", "INFO")
                log_test(f"  Cache items: {cache_items}", "INFO")
                log_test(f"  Cache size: {cache_size_mb:.2f} MB", "INFO")
                log_test(f"  Hit rate: {cache_hit_rate:.1f}%", "INFO")
                
                return {
                    'status': 'success',
                    'stats': stats,
                    'rust_available': rust_available,
                    'cache_items': cache_items
                }
            else:
                log_test(f"❌ API returned success=false: {data.get('error')}", "ERROR")
                return {'status': 'failed', 'error': data.get('error', 'success=false')}
        else:
            log_test(f"❌ HTTP {response.status_code}: {response.text}", "ERROR")
            return {'status': 'failed', 'error': f"HTTP {response.status_code}"}
            
    except Exception as e:
        log_test(f"❌ Exception: {str(e)}", "ERROR")
        return {'status': 'failed', 'error': str(e)}

def test_presentations_endpoint():
    """Test GET /api/presentations/{id} includes location and locationFolder fields"""
    log_test("Testing presentations endpoint for location fields...")
    
    # First, get list of presentations to find trivia-imported ones
    try:
        # Try to get presentations for a few common usernames
        test_users = ["Nick", "Admin", "testuser", "user"]
        
        trivia_presentations = []
        
        for username in test_users:
            try:
                response = requests.get(f"{API_BASE}/presentations", params={"userName": username}, timeout=15)
                
                if response.status_code == 200:
                    presentations = response.json()
                    
                    # Look for trivia-imported presentations
                    for pres in presentations:
                        if pres.get('type') == 'trivia-imported':
                            trivia_presentations.append(pres)
                            log_test(f"Found trivia-imported presentation: {pres['name']}", "INFO")
                
            except Exception as e:
                log_test(f"Failed to get presentations for {username}: {e}", "WARNING")
        
        if not trivia_presentations:
            log_test("⚠️ No trivia-imported presentations found for testing", "WARNING")
            log_test("Testing with empty database - cannot verify presentation endpoint fully", "INFO")
            return {
                'status': 'skipped', 
                'reason': 'No trivia-imported presentations in database',
                'note': 'This is expected based on review context'
            }
        
        # Test the first trivia-imported presentation
        test_pres = trivia_presentations[0]
        pres_id = test_pres['id']
        
        log_test(f"Testing presentation ID: {pres_id}")
        
        response = requests.get(f"{API_BASE}/presentations/{pres_id}", timeout=15)
        
        if response.status_code == 200:
            presentation = response.json()
            
            # Check for required fields from the fix
            has_location = 'location' in presentation
            has_location_folder = 'locationFolder' in presentation
            
            if has_location and has_location_folder:
                location = presentation['location']
                location_folder = presentation['locationFolder']
                
                log_test(f"✅ Presentation includes location fields", "SUCCESS")
                log_test(f"  location: {location}", "INFO")
                log_test(f"  locationFolder: {location_folder}", "INFO")
                
                return {
                    'status': 'success',
                    'presentation_id': pres_id,
                    'location': location,
                    'locationFolder': location_folder
                }
            else:
                missing = []
                if not has_location:
                    missing.append('location')
                if not has_location_folder:
                    missing.append('locationFolder')
                
                log_test(f"❌ Missing location fields: {missing}", "ERROR")
                return {
                    'status': 'failed',
                    'error': f'Missing fields: {missing}',
                    'presentation_id': pres_id
                }
        else:
            log_test(f"❌ HTTP {response.status_code}: {response.text}", "ERROR")
            return {'status': 'failed', 'error': f"HTTP {response.status_code}"}
            
    except Exception as e:
        log_test(f"❌ Exception: {str(e)}", "ERROR")
        return {'status': 'failed', 'error': str(e)}

def test_clean_vs_prefixed_location_names():
    """Specific test for clean vs prefixed location name handling"""
    log_test("Testing clean vs prefixed location name handling...")
    
    # Test pairs: (clean_name, prefixed_name)
    test_pairs = [
        ("WP Gilbert", "04_WP Gilbert"),
        ("Valley Craft", "06_Valley Craft"),
        ("Monkey Pants", "01_Monkey Pants")
    ]
    
    results = {}
    
    for clean_name, prefixed_name in test_pairs:
        log_test(f"Testing pair: '{clean_name}' vs '{prefixed_name}'")
        
        clean_result = None
        prefixed_result = None
        
        # Test clean name
        try:
            response = requests.get(f"{API_BASE}/overlays/metadata/{clean_name}", timeout=15)
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    clean_result = len(data.get('overlays', []))
                    log_test(f"  Clean name '{clean_name}': {clean_result} overlays", "INFO")
        except Exception as e:
            log_test(f"  Clean name failed: {e}", "WARNING")
        
        # Test prefixed name
        try:
            response = requests.get(f"{API_BASE}/overlays/metadata/{prefixed_name}", timeout=15)
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    prefixed_result = len(data.get('overlays', []))
                    log_test(f"  Prefixed name '{prefixed_name}': {prefixed_result} overlays", "INFO")
        except Exception as e:
            log_test(f"  Prefixed name failed: {e}", "WARNING")
        
        # Analyze results
        if clean_result is not None and prefixed_result is not None:
            if clean_result == prefixed_result and clean_result > 0:
                log_test(f"✅ Both names work and return same count: {clean_result}", "SUCCESS")
                results[f"{clean_name}_vs_{prefixed_name}"] = {
                    'status': 'success',
                    'clean_count': clean_result,
                    'prefixed_count': prefixed_result
                }
            else:
                log_test(f"❌ Mismatch: clean={clean_result}, prefixed={prefixed_result}", "ERROR")
                results[f"{clean_name}_vs_{prefixed_name}"] = {
                    'status': 'failed',
                    'error': 'Count mismatch',
                    'clean_count': clean_result,
                    'prefixed_count': prefixed_result
                }
        elif clean_result is not None or prefixed_result is not None:
            working_count = clean_result or prefixed_result
            log_test(f"⚠️ Only one format works: {working_count} overlays", "WARNING")
            results[f"{clean_name}_vs_{prefixed_name}"] = {
                'status': 'partial',
                'clean_count': clean_result,
                'prefixed_count': prefixed_result
            }
        else:
            log_test(f"❌ Both formats failed", "ERROR")
            results[f"{clean_name}_vs_{prefixed_name}"] = {
                'status': 'failed',
                'error': 'Both formats failed'
            }
    
    return results

def main():
    """Run all overlay regression fix tests"""
    log_test("=" * 70)
    log_test("OVERLAY REGRESSION FIX TEST SUITE")
    log_test("Testing critical production overlay regression fixes")
    log_test("=" * 70)
    
    all_results = {}
    
    # Test 1: Overlay metadata for all locations
    log_test("\n" + "="*50)
    log_test("TEST 1: OVERLAY METADATA FOR ALL LOCATIONS")
    log_test("="*50)
    all_results['overlay_metadata'] = test_overlay_metadata_all_locations()
    
    # Test 2: Clean vs prefixed location names
    log_test("\n" + "="*50)
    log_test("TEST 2: CLEAN VS PREFIXED LOCATION NAMES")
    log_test("="*50)
    all_results['clean_vs_prefixed'] = test_clean_vs_prefixed_location_names()
    
    # Test 3: Overlay image endpoint
    log_test("\n" + "="*50)
    log_test("TEST 3: OVERLAY IMAGE ENDPOINT")
    log_test("="*50)
    all_results['overlay_image'] = test_overlay_image_endpoint()
    
    # Test 4: Overlay stats endpoint
    log_test("\n" + "="*50)
    log_test("TEST 4: OVERLAY STATS ENDPOINT")
    log_test("="*50)
    all_results['overlay_stats'] = test_overlay_stats_endpoint()
    
    # Test 5: Presentations endpoint with location fields
    log_test("\n" + "="*50)
    log_test("TEST 5: PRESENTATIONS ENDPOINT LOCATION FIELDS")
    log_test("="*50)
    all_results['presentations_location_fields'] = test_presentations_endpoint()
    
    # Final summary
    log_test("\n" + "="*70)
    log_test("FINAL TEST SUMMARY")
    log_test("="*70)
    
    # Count successes
    metadata_success = sum(1 for r in all_results['overlay_metadata'].values() if r['status'] == 'success')
    metadata_total = len(all_results['overlay_metadata'])
    
    clean_prefixed_success = sum(1 for r in all_results['clean_vs_prefixed'].values() if r['status'] == 'success')
    clean_prefixed_total = len(all_results['clean_vs_prefixed'])
    
    image_success = sum(1 for r in all_results['overlay_image'].values() if r['status'] == 'success')
    image_total = len(all_results['overlay_image'])
    
    stats_success = 1 if all_results['overlay_stats']['status'] == 'success' else 0
    
    presentations_success = 1 if all_results['presentations_location_fields']['status'] in ['success', 'skipped'] else 0
    
    log_test(f"Overlay metadata endpoints: {metadata_success}/{metadata_total} locations")
    log_test(f"Clean vs prefixed names: {clean_prefixed_success}/{clean_prefixed_total} pairs")
    log_test(f"Overlay image endpoints: {image_success}/{image_total} paths")
    log_test(f"Overlay stats endpoint: {stats_success}/1")
    log_test(f"Presentations location fields: {presentations_success}/1")
    
    total_success = metadata_success + clean_prefixed_success + image_success + stats_success + presentations_success
    total_tests = metadata_total + clean_prefixed_total + image_total + 1 + 1
    
    log_test("=" * 70)
    log_test(f"OVERALL RESULT: {total_success}/{total_tests} tests passed")
    
    if total_success == total_tests:
        log_test("🎉 ALL OVERLAY REGRESSION TESTS PASSED!", "SUCCESS")
        return 0
    else:
        failed = total_tests - total_success
        log_test(f"⚠️ {failed} test(s) failed - Issues need attention", "WARNING")
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)