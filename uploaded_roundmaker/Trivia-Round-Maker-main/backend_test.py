#!/usr/bin/env python3
"""
Backend API Test Suite for BIG Hat Presenter Trivia Round Creator
Tests all CRUD operations, file upload, and PowerPoint generation endpoints.
"""

import requests
import sys
import json
import time
import io
from datetime import datetime
from pathlib import Path

class TriviaAPITester:
    def __init__(self, base_url="https://trivia-generator.preview.emergentagent.com/api"):
        self.base_url = base_url
        self.tests_run = 0
        self.tests_passed = 0
        self.created_rounds = []  # Track created rounds for cleanup
        self.cover_file_id = None

    def log(self, message, test_type="INFO"):
        prefix = {
            "PASS": "✅",
            "FAIL": "❌", 
            "INFO": "🔍",
            "WARN": "⚠️"
        }.get(test_type, "ℹ️")
        print(f"{prefix} {message}")

    def run_test(self, name, method, endpoint, expected_status=200, data=None, files=None, response_type='json'):
        """Run a single API test"""
        url = f"{self.base_url}/{endpoint}" if endpoint else self.base_url
        headers = {'Content-Type': 'application/json'} if not files else {}
        
        self.tests_run += 1
        self.log(f"Testing {name}...", "INFO")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers)
            elif method == 'POST':
                if files:
                    response = requests.post(url, files=files)
                else:
                    response = requests.post(url, json=data, headers=headers)
            elif method == 'DELETE':
                response = requests.delete(url, headers=headers)
            else:
                raise ValueError(f"Unsupported method: {method}")

            success = response.status_code == expected_status
            if success:
                self.tests_passed += 1
                self.log(f"PASSED - {name} - Status: {response.status_code}", "PASS")
                
                if response_type == 'json':
                    try:
                        return True, response.json()
                    except:
                        return True, response.text
                else:
                    return True, response.content
            else:
                self.log(f"FAILED - {name} - Expected {expected_status}, got {response.status_code}", "FAIL")
                try:
                    error_data = response.json()
                    self.log(f"Error details: {error_data}", "FAIL")
                except:
                    self.log(f"Error text: {response.text[:200]}", "FAIL")
                
                return False, {}

        except Exception as e:
            self.log(f"FAILED - {name} - Error: {str(e)}", "FAIL")
            return False, {}

    def test_health_check(self):
        """Test basic API health"""
        return self.run_test("API Health Check", "GET", "")

    def test_cover_upload(self):
        """Test cover image upload"""
        # Create a simple test image file
        test_image = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x01\x00\x00\x00\x007n\xf9$\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xdb\x00\x00\x00\x00IEND\xaeB`\x82'
        files = {'file': ('test_cover.png', io.BytesIO(test_image), 'image/png')}
        
        success, response = self.run_test("Cover Image Upload", "POST", "upload-cover", 200, files=files)
        if success and 'file_id' in response:
            self.cover_file_id = response['file_id']
            self.log(f"Cover uploaded with ID: {self.cover_file_id}", "INFO")
        return success, response

    def create_mc_round(self):
        """Create a Multiple Choice round"""
        questions = []
        for i in range(1, 11):
            questions.append({
                "number": i,
                "question": f"MC Question {i}?",
                "answer": f"A) Answer {i}",
                "options": [f"Answer {i}", f"Wrong {i}A", f"Wrong {i}B", f"Wrong {i}C"]
            })
        
        data = {
            "round_type": "MC",
            "name": f"Test_MC_Round_{int(time.time())}",
            "questions": questions,
            "cover_image_id": self.cover_file_id
        }
        
        success, response = self.run_test("Create MC Round", "POST", "rounds", 200, data)
        if success and 'id' in response:
            self.created_rounds.append(response['id'])
        return success, response

    def create_reg_round(self):
        """Create a General Round"""
        questions = []
        for i in range(1, 11):
            questions.append({
                "number": i,
                "question": f"REG Question {i}?",
                "answer": f"Answer {i}"
            })
        
        data = {
            "round_type": "REG", 
            "name": f"Test_REG_Round_{int(time.time())}",
            "questions": questions,
            "cover_image_id": self.cover_file_id
        }
        
        success, response = self.run_test("Create REG Round", "POST", "rounds", 200, data)
        if success and 'id' in response:
            self.created_rounds.append(response['id'])
        return success, response

    def create_misc_round(self):
        """Create a Specific/Misc Round"""
        questions = []
        for i in range(1, 11):
            questions.append({
                "number": i,
                "question": f"MISC Question {i}?",
                "answer": f"Answer {i}"
            })
        
        data = {
            "round_type": "MISC",
            "name": f"Test_MISC_Round_{int(time.time())}",
            "questions": questions,
            "cover_image_id": self.cover_file_id
        }
        
        success, response = self.run_test("Create MISC Round", "POST", "rounds", 200, data)
        if success and 'id' in response:
            self.created_rounds.append(response['id'])
        return success, response

    def create_mys_round(self):
        """Create a Mystery Round (9 clues + 1 theme)"""
        questions = []
        for i in range(1, 10):
            questions.append({
                "number": i,
                "question": f"MYS Clue {i}?",
                "answer": f"Answer {i}"
            })
        # Q10 is locked as "Theme?"
        questions.append({
            "number": 10,
            "question": "Theme?",
            "answer": "The theme is Animals"
        })
        
        data = {
            "round_type": "MYS",
            "name": f"Test_MYS_Round_{int(time.time())}",
            "questions": questions,
            "cover_image_id": self.cover_file_id
        }
        
        success, response = self.run_test("Create MYS Round", "POST", "rounds", 200, data)
        if success and 'id' in response:
            self.created_rounds.append(response['id'])
        return success, response

    def create_big_round(self):
        """Create a BIG Round (1 question, multiple answers, tiebreaker)"""
        # BIG round has 1 question with multiple answer lines (8-15)
        questions = []
        for i in range(1, 11):  # 10 answers
            questions.append({
                "number": i,
                "question": "Name countries in Europe",
                "answer": f"European Country {i}"
            })
        
        tiebreaker = {
            "question": "What is the population of Germany?",
            "answer": "83 million"
        }
        
        data = {
            "round_type": "BIG",
            "name": f"Test_BIG_Round_{int(time.time())}",
            "questions": questions,
            "tiebreaker": tiebreaker,
            "cover_image_id": self.cover_file_id
        }
        
        success, response = self.run_test("Create BIG Round", "POST", "rounds", 200, data)
        if success and 'id' in response:
            self.created_rounds.append(response['id'])
        return success, response

    def test_list_rounds(self):
        """Test listing all rounds"""
        return self.run_test("List All Rounds", "GET", "rounds")

    def test_get_round(self, round_id):
        """Test getting a specific round"""
        return self.run_test(f"Get Round {round_id}", "GET", f"rounds/{round_id}")

    def test_generate_pptx(self, round_id):
        """Test PowerPoint generation"""
        success, response = self.run_test(
            f"Generate PPTX for Round {round_id}", 
            "POST", 
            f"rounds/{round_id}/generate", 
            200,
            response_type='blob'
        )
        if success:
            self.log(f"PPTX generated successfully, size: {len(response)} bytes", "INFO")
        return success, response

    def test_delete_round(self, round_id):
        """Test deleting a round"""
        return self.run_test(f"Delete Round {round_id}", "DELETE", f"rounds/{round_id}")

    def test_sharepoint_status(self):
        """Test SharePoint status endpoint"""
        return self.run_test("SharePoint Status", "GET", "sharepoint-status")

    def test_reg_title_images(self):
        """Test REG title images endpoint"""
        return self.run_test("REG Title Images", "GET", "reg-title-images")

    def test_reg_next_number(self, category="Sports"):
        """Test REG next number endpoint"""
        return self.run_test(f"REG Next Number for {category}", "GET", f"reg-next-number/{category}")

    def test_mc_next_name(self):
        """Test MC next name endpoint - should return MC_19_D with 72 existing files"""
        success, response = self.run_test("MC Next Name", "GET", "mc-next-name")
        if success:
            round_name = response.get('round_name', '')
            existing_count = response.get('existing_count', 0)
            next_number = response.get('next_number', 0)
            next_letter = response.get('next_letter', '')
            
            self.log(f"MC Next Name: {round_name}", "INFO")
            self.log(f"Existing MC files: {existing_count}", "INFO")
            self.log(f"Next number: {next_number}, Next letter: {next_letter}", "INFO")
            
            # Verify the expected format MC_NN_X
            if round_name and '_' in round_name:
                parts = round_name.split('_')
                if len(parts) == 3 and parts[0] == 'MC':
                    self.log("MC naming format is correct", "PASS")
                else:
                    self.log(f"MC naming format incorrect: {round_name}", "FAIL")
            else:
                self.log(f"MC naming format invalid: {round_name}", "FAIL")
                
        return success, response

    def test_reg_download_title_image(self, item_id="test", drive_id="test", filename="test.jpg"):
        """Test REG download title image endpoint"""
        endpoint = f"reg-download-title-image?item_id={item_id}&drive_id={drive_id}&filename={filename}"
        return self.run_test("REG Download Title Image", "POST", endpoint, 200)

    def test_serve_upload(self, filename="test.jpg"):
        """Test serving uploaded files"""
        return self.run_test(f"Serve Upload {filename}", "GET", f"uploads/{filename}")

    def test_duplicate_round(self, round_id):
        """Test the new duplicate/clone endpoint"""
        return self.run_test(f"Duplicate Round {round_id}", "POST", f"rounds/{round_id}/duplicate", 200)

    def cleanup_created_rounds(self):
        """Clean up all rounds created during testing"""
        self.log("Cleaning up created rounds...", "INFO")
        for round_id in self.created_rounds:
            self.test_delete_round(round_id)

    def run_all_tests(self):
        """Run the complete test suite"""
        self.log("Starting BIG Hat Presenter API Test Suite", "INFO")
        self.log(f"Testing against: {self.base_url}", "INFO")
        
        # 1. Basic health check
        self.test_health_check()
        
        # 2. Cover image upload
        self.test_cover_upload()
        
        # 3. Create rounds for each type
        mc_success, mc_response = self.create_mc_round()
        reg_success, reg_response = self.create_reg_round()
        misc_success, misc_response = self.create_misc_round()
        mys_success, mys_response = self.create_mys_round()
        big_success, big_response = self.create_big_round()
        
        # 4. Test listing rounds
        self.test_list_rounds()
        
        # 5. Test getting specific rounds
        if self.created_rounds:
            for round_id in self.created_rounds[:2]:  # Test first 2 rounds
                self.test_get_round(round_id)
        
        # 6. Test PowerPoint generation
        if self.created_rounds:
            # Test with first created round
            self.test_generate_pptx(self.created_rounds[0])
        
        # 7. Test duplicate functionality
        if self.created_rounds:
            # Test duplicating the first round
            duplicate_success, duplicate_response = self.test_duplicate_round(self.created_rounds[0])
            if duplicate_success and 'id' in duplicate_response:
                self.created_rounds.append(duplicate_response['id'])
                self.log(f"Duplicated round created with name: {duplicate_response.get('name')}", "INFO")
                # Verify the duplicate has '(Copy)' in name
                original_name = mc_response.get('name', '') if mc_success else ''
                duplicate_name = duplicate_response.get('name', '')
                if '(Copy)' in duplicate_name:
                    self.log("Duplicate naming convention correct", "PASS")
                else:
                    self.log(f"Duplicate naming issue - got '{duplicate_name}'", "FAIL")
        
        # 8. Test SharePoint status  
        self.test_sharepoint_status()
        
        # 9. Test MC-specific endpoints
        self.log("Testing MC-specific SharePoint endpoints...", "INFO")
        self.test_mc_next_name()
        
        # 10. Test REG-specific endpoints
        self.log("Testing REG-specific SharePoint endpoints...", "INFO")
        reg_images_success, reg_images_response = self.test_reg_title_images()
        
        if reg_images_success and reg_images_response.get('images'):
            images = reg_images_response['images']
            self.log(f"Found {len(images)} REG title images", "INFO")
            
            # Test next number for first category
            if images:
                first_category = images[0].get('name_no_ext', 'Sports')
                self.test_reg_next_number(first_category)
                
                # Test download (this might fail without valid SharePoint data)
                first_img = images[0]
                item_id = first_img.get('item_id', 'test')
                drive_id = first_img.get('drive_id', 'test')
                filename = first_img.get('name', 'test.jpg')
                
                download_success, download_response = self.test_reg_download_title_image(item_id, drive_id, filename)
                if download_success and download_response.get('filename'):
                    # Test serving the downloaded file
                    self.test_serve_upload(download_response['filename'])
        else:
            self.log("No REG images found or endpoint failed", "WARN")
        
        # 11. Cleanup (delete created rounds)
        self.cleanup_created_rounds()
        
        # Print summary
        print("\n" + "="*50)
        print(f"📊 TEST SUMMARY")
        print(f"Tests Run: {self.tests_run}")
        print(f"Tests Passed: {self.tests_passed}")
        print(f"Tests Failed: {self.tests_run - self.tests_passed}")
        print(f"Success Rate: {(self.tests_passed/self.tests_run)*100:.1f}%")
        print("="*50)
        
        return self.tests_passed == self.tests_run

def main():
    """Main test execution"""
    tester = TriviaAPITester()
    success = tester.run_all_tests()
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())