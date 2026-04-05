#!/usr/bin/env python3
"""
Backend API Testing for Story Generator Feature
Tests all Story Generator endpoints and functionality
"""

import requests
import sys
import json
import time
from datetime import datetime
from pathlib import Path

class StoryGeneratorAPITester:
    def __init__(self, base_url="https://trivia-poster-gen.preview.emergentagent.com"):
        self.base_url = base_url
        self.api_url = f"{base_url}/api"
        self.tests_run = 0
        self.tests_passed = 0
        self.failed_tests = []
        self.test_results = []

    def log_test(self, name, success, status_code=None, error=None, response_data=None):
        """Log test result"""
        self.tests_run += 1
        if success:
            self.tests_passed += 1
            print(f"✅ {name} - PASSED (Status: {status_code})")
        else:
            print(f"❌ {name} - FAILED (Status: {status_code}, Error: {error})")
            self.failed_tests.append({
                'test': name,
                'status_code': status_code,
                'error': str(error),
                'response': response_data
            })
        
        self.test_results.append({
            'name': name,
            'success': success,
            'status_code': status_code,
            'error': str(error) if error else None,
            'timestamp': datetime.now().isoformat()
        })

    def test_api_endpoint(self, method, endpoint, expected_status=200, data=None, params=None, timeout=30):
        """Generic API test method"""
        url = f"{self.api_url}/{endpoint}"
        headers = {'Content-Type': 'application/json'}
        
        try:
            if method.upper() == 'GET':
                response = requests.get(url, headers=headers, params=params, timeout=timeout)
            elif method.upper() == 'POST':
                response = requests.post(url, json=data, headers=headers, params=params, timeout=timeout)
            elif method.upper() == 'DELETE':
                response = requests.delete(url, headers=headers, params=params, timeout=timeout)
            else:
                raise ValueError(f"Unsupported method: {method}")

            success = response.status_code == expected_status
            response_data = None
            
            try:
                response_data = response.json()
            except:
                response_data = response.text[:200] if response.text else None

            return success, response.status_code, response_data

        except requests.exceptions.Timeout:
            return False, None, "Request timeout"
        except requests.exceptions.ConnectionError:
            return False, None, "Connection error"
        except Exception as e:
            return False, None, str(e)

    def test_get_presentations(self):
        """Test GET /api/story-generator/presentations"""
        print("\n🔍 Testing Story Generator Presentations API...")
        
        # Test without userName parameter
        success, status, data = self.test_api_endpoint('GET', 'story-generator/presentations')
        self.log_test("GET presentations (no filter)", success, status, 
                     None if success else data, data)
        
        # Test with userName parameter
        success, status, data = self.test_api_endpoint('GET', 'story-generator/presentations', 
                                                      params={'userName': 'testuser'})
        self.log_test("GET presentations (with userName)", success, status, 
                     None if success else data, data)
        
        return data if success else []

    def test_get_assets(self):
        """Test GET /api/story-generator/assets"""
        print("\n🔍 Testing Story Generator Assets API...")
        
        success, status, data = self.test_api_endpoint('GET', 'story-generator/assets')
        self.log_test("GET assets", success, status, 
                     None if success else data, data)
        
        if success and data:
            # Validate assets structure
            expected_keys = ['locations', 'hosts', 'backgrounds']
            has_all_keys = all(key in data for key in expected_keys)
            self.log_test("Assets structure validation", has_all_keys, status,
                         None if has_all_keys else f"Missing keys: {set(expected_keys) - set(data.keys())}")
        
        return data if success else {}

    def test_presentation_details(self, presentation_id):
        """Test GET /api/story-generator/presentation/{id}"""
        print(f"\n🔍 Testing Presentation Details API for ID: {presentation_id}...")
        
        success, status, data = self.test_api_endpoint('GET', f'story-generator/presentation/{presentation_id}')
        self.log_test(f"GET presentation details ({presentation_id})", success, status,
                     None if success else data, data)
        
        if success and data:
            # Validate presentation structure
            required_fields = ['id', 'name', 'location', 'host', 'rounds']
            has_required = all(field in data for field in required_fields)
            self.log_test("Presentation details structure", has_required, status,
                         None if has_required else f"Missing fields: {set(required_fields) - set(data.keys())}")
        
        return data if success else None

    def test_generate_preview(self, presentation_id):
        """Test POST /api/story-generator/preview/{id}"""
        print(f"\n🔍 Testing Preview Generation for ID: {presentation_id}...")
        
        success, status, data = self.test_api_endpoint('POST', f'story-generator/preview/{presentation_id}')
        self.log_test(f"POST generate preview ({presentation_id})", success, status,
                     None if success else data, data)
        
        if success and data:
            # Validate preview structure
            if 'preview' in data:
                preview = data['preview']
                required_sections = ['location', 'host', 'rounds', 'totalDuration']
                has_sections = all(section in preview for section in required_sections)
                self.log_test("Preview structure validation", has_sections, status,
                             None if has_sections else f"Missing sections: {set(required_sections) - set(preview.keys())}")
        
        return data if success else None

    def test_round_layout_validation(self, presentation_data):
        """Test if the presentation has the correct round layout"""
        if not presentation_data:
            return False
            
        rounds = presentation_data.get('rounds', [])
        if not rounds:
            return False
            
        print(f"\n🔍 Validating Round Layout for {presentation_data.get('name', 'Unknown')}...")
        print(f"   Total rounds: {len(rounds)}")
        
        # Count rounds by type
        round_counts = {}
        for round_info in rounds:
            round_type = round_info.get('type', 'UNKNOWN')
            round_counts[round_type] = round_counts.get(round_type, 0) + 1
            print(f"   - {round_info.get('name', 'Unnamed')}: {round_type}")
        
        print(f"   Round type counts: {round_counts}")
        
        # Validate expected layouts
        total_rounds = len(rounds)
        has_mc = round_counts.get('MC', 0) >= 1
        has_mystery = round_counts.get('MYS', 0) >= 1  
        has_big = round_counts.get('BIG', 0) >= 1
        
        layout_valid = False
        layout_description = ""
        
        if total_rounds == 5:
            # 5-round layout: Green MC, 1 Red REG, 1 Blue MISC, Purple Mystery, Yellow BIG
            expected_layout = has_mc and round_counts.get('REG', 0) == 1 and round_counts.get('MISC', 0) == 1 and has_mystery and has_big
            layout_description = "5-round layout (MC + 1 REG + 1 MISC + Mystery + BIG)"
            layout_valid = expected_layout
        elif total_rounds == 6:
            # Could be either 2 REG or 2 MISC layout
            if round_counts.get('REG', 0) == 2:
                # 6-round with 2 REGs: Green MC, 2 Red REGs, 1 Blue MISC, Purple Mystery, Yellow BIG
                expected_layout = has_mc and round_counts.get('REG', 0) == 2 and round_counts.get('MISC', 0) == 1 and has_mystery and has_big
                layout_description = "6-round layout with 2 REGs (MC + 2 REG + 1 MISC + Mystery + BIG)"
                layout_valid = expected_layout
            elif round_counts.get('MISC', 0) == 2:
                # 6-round with 2 MISCs: Green MC, 1 Red REG, 2 Blue MISCs, Purple Mystery, Yellow BIG
                expected_layout = has_mc and round_counts.get('REG', 0) == 1 and round_counts.get('MISC', 0) == 2 and has_mystery and has_big
                layout_description = "6-round layout with 2 MISCs (MC + 1 REG + 2 MISC + Mystery + BIG)"
                layout_valid = expected_layout
        
        self.log_test(f"Round layout validation: {layout_description}", layout_valid, 200,
                     None if layout_valid else f"Layout doesn't match expected pattern. Counts: {round_counts}")
        
        return layout_valid
    def test_generate_video(self, presentation_id):
        """Test POST /api/story-generator/generate/{id}"""
        print(f"\n🔍 Testing Video Generation for ID: {presentation_id}...")
        print("⚠️  This test may take 1-2 minutes to complete...")
        
        success, status, data = self.test_api_endpoint('POST', f'story-generator/generate/{presentation_id}', 
                                                      timeout=120)  # 2 minute timeout
        self.log_test(f"POST generate video ({presentation_id})", success, status,
                     None if success else data, data)
        
        if success and data:
            # Validate video generation response
            required_fields = ['success', 'filename', 'downloadUrl']
            has_required = all(field in data for field in required_fields)
            self.log_test("Video generation response structure", has_required, status,
                         None if has_required else f"Missing fields: {set(required_fields) - set(data.keys())}")
            
            return data.get('filename') if has_required else None
        
        return None

    def test_download_video(self, filename):
        """Test GET /api/story-generator/download/{filename}"""
        if not filename:
            print("\n⚠️  Skipping video download test - no filename available")
            return
            
        print(f"\n🔍 Testing Video Download for file: {filename}...")
        
        url = f"{self.api_url}/story-generator/download/{filename}"
        try:
            response = requests.get(url, timeout=30, stream=True)  # Use GET with stream
            success = response.status_code == 200
            self.log_test(f"GET download video ({filename})", success, response.status_code,
                         None if success else "File not accessible")
            
            if success:
                # Check if it's actually a video file
                content_type = response.headers.get('content-type', '')
                is_video = 'video' in content_type.lower() or 'mp4' in content_type.lower()
                self.log_test("Video file content-type check", is_video, response.status_code,
                             None if is_video else f"Content-Type: {content_type}")
                
        except Exception as e:
            self.log_test(f"GET download video ({filename})", False, None, str(e))

    def test_specific_presentations_exist(self):
        """Test if the specific test presentations exist in database"""
        print("\n🔍 Testing Specific Test Presentations Existence...")
        
        # Test presentations mentioned in the review request
        test_presentations = {
            "b1b7943a-1fb9-4304-94c9-612636b161b1": "5 rounds layout",
            "6de0675c-7499-439f-a4c9-a7139414151f": "6 rounds with 2 REG",
        }
        
        existing_presentations = []
        
        for pres_id, description in test_presentations.items():
            success, status, data = self.test_api_endpoint('GET', f'story-generator/presentation/{pres_id}')
            self.log_test(f"Test presentation exists ({description}: {pres_id})", success, status,
                         None if success else data, data)
            
            if success and data:
                existing_presentations.append({
                    'id': pres_id,
                    'description': description,
                    'data': data
                })
        
        # Also search for Denver presentation with 2 MISC rounds
        print("\n🔍 Searching for Denver presentation with 2 MISC rounds...")
        success, status, all_presentations = self.test_api_endpoint('GET', 'story-generator/presentations')
        
        if success and all_presentations:
            for pres in all_presentations:
                if 'denver' in pres.get('name', '').lower() or 'denver' in pres.get('location', '').lower():
                    # Get detailed info to check rounds
                    pres_id = pres.get('id')
                    success, status, data = self.test_api_endpoint('GET', f'story-generator/presentation/{pres_id}')
                    
                    if success and data:
                        rounds = data.get('rounds', [])
                        misc_count = sum(1 for r in rounds if r.get('type') == 'MISC')
                        
                        if misc_count == 2:
                            self.log_test(f"Denver presentation with 2 MISC found ({pres_id})", True, status)
                            existing_presentations.append({
                                'id': pres_id,
                                'description': "Denver presentation with 2 MISC",
                                'data': data
                            })
                            break
        
        return existing_presentations

    def run_comprehensive_test(self):
        """Run all Story Generator API tests"""
        print("🚀 Starting Story Generator API Testing...")
        print(f"Backend URL: {self.base_url}")
        print("=" * 60)
        
        # Test 1: Get presentations list
        presentations = self.test_get_presentations()
        
        # Test 2: Get assets
        assets = self.test_get_assets()
        
        # Test 3: Check if specific test presentations exist
        specific_presentations = self.test_specific_presentations_exist()
        
        # Test 4: Test each specific presentation
        for pres_info in specific_presentations:
            pres_id = pres_info['id']
            description = pres_info['description']
            
            print(f"\n{'='*60}")
            print(f"🎯 Testing {description} (ID: {pres_id})")
            print(f"{'='*60}")
            
            # Get presentation details
            presentation_details = self.test_presentation_details(pres_id)
            
            # Validate round layout
            if presentation_details:
                self.test_round_layout_validation(presentation_details)
            
            # Generate preview
            preview_data = self.test_generate_preview(pres_id)
            
            # Generate video (this is the most intensive test)
            generated_filename = self.test_generate_video(pres_id)
            
            # Test video download
            self.test_download_video(generated_filename)
        
        # If no specific presentations found, test with any available presentation
        if not specific_presentations:
            print("\n⚠️  No specific test presentations found, testing with available presentations...")
            
            if presentations and len(presentations) > 0:
                test_presentation_id = presentations[0].get('id')
                
                # Test with first available presentation
                presentation_details = self.test_presentation_details(test_presentation_id)
                if presentation_details:
                    self.test_round_layout_validation(presentation_details)
                preview_data = self.test_generate_preview(test_presentation_id)
                generated_filename = self.test_generate_video(test_presentation_id)
                self.test_download_video(generated_filename)
            else:
                print("\n⚠️  No presentations available for testing video generation")
                self.log_test("Video generation tests", False, None, "No presentations available")
        
        # Print summary
        self.print_summary()
        
        return self.tests_passed == self.tests_run

    def print_summary(self):
        """Print test summary"""
        print("\n" + "=" * 60)
        print("📊 TEST SUMMARY")
        print("=" * 60)
        print(f"Total Tests: {self.tests_run}")
        print(f"Passed: {self.tests_passed}")
        print(f"Failed: {len(self.failed_tests)}")
        print(f"Success Rate: {(self.tests_passed/self.tests_run*100):.1f}%" if self.tests_run > 0 else "0%")
        
        if self.failed_tests:
            print("\n❌ FAILED TESTS:")
            for test in self.failed_tests:
                print(f"  • {test['test']}: {test['error']}")
        
        print("\n" + "=" * 60)

def main():
    """Main test execution"""
    tester = StoryGeneratorAPITester()
    
    try:
        success = tester.run_comprehensive_test()
        
        # Save test results to file
        results_file = Path("/app/test_reports/backend_test_results.json")
        results_file.parent.mkdir(exist_ok=True)
        
        with open(results_file, 'w') as f:
            json.dump({
                'timestamp': datetime.now().isoformat(),
                'total_tests': tester.tests_run,
                'passed_tests': tester.tests_passed,
                'failed_tests': len(tester.failed_tests),
                'success_rate': (tester.tests_passed/tester.tests_run*100) if tester.tests_run > 0 else 0,
                'test_results': tester.test_results,
                'failed_details': tester.failed_tests
            }, f, indent=2)
        
        print(f"\n📄 Test results saved to: {results_file}")
        
        return 0 if success else 1
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Tests interrupted by user")
        return 1
    except Exception as e:
        print(f"\n\n💥 Test execution failed: {str(e)}")
        return 1

if __name__ == "__main__":
    sys.exit(main())