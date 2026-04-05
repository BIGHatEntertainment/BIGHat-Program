#!/usr/bin/env python3
"""
SharePoint Integration Test Suite
Tests specific SharePoint functionality including upload endpoint.
"""

import requests
import sys
import json
import time
from datetime import datetime

class SharePointTester:
    def __init__(self, base_url="https://trivia-generator.preview.emergentagent.com/api"):
        self.base_url = base_url
        self.tests_run = 0
        self.tests_passed = 0
        self.test_round_id = None

    def log(self, message, test_type="INFO"):
        prefix = {
            "PASS": "✅",
            "FAIL": "❌", 
            "INFO": "🔍",
            "WARN": "⚠️"
        }.get(test_type, "ℹ️")
        print(f"{prefix} {message}")

    def run_test(self, name, method, endpoint, expected_status=200, data=None):
        """Run a single test"""
        url = f"{self.base_url}/{endpoint}"
        headers = {'Content-Type': 'application/json'}
        
        self.tests_run += 1
        self.log(f"Testing {name}...", "INFO")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers)
            else:
                raise ValueError(f"Unsupported method: {method}")

            success = response.status_code == expected_status
            if success:
                self.tests_passed += 1
                self.log(f"PASSED - {name} - Status: {response.status_code}", "PASS")
                try:
                    return True, response.json()
                except:
                    return True, response.text
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

    def test_sharepoint_status_detailed(self):
        """Test SharePoint status and verify configured=true and token_valid=true"""
        success, response = self.run_test("SharePoint Status Detailed", "GET", "sharepoint-status")
        
        if success:
            self.log(f"SharePoint Status Response: {json.dumps(response, indent=2)}", "INFO")
            
            # Check specific requirements
            if response.get('configured') == True:
                self.log("✓ SharePoint is configured", "PASS")
            else:
                self.log("✗ SharePoint not configured", "FAIL")
            
            if response.get('token_valid') == True:
                self.log("✓ SharePoint token is valid", "PASS") 
            else:
                self.log("✗ SharePoint token is invalid", "FAIL")
                
            if 'folders' in response:
                self.log(f"Available folders: {list(response['folders'].keys())}", "INFO")
                
        return success, response

    def create_test_round(self):
        """Create a test REG round for SharePoint upload testing"""
        questions = [
            {
                "number": i,
                "question": f"Test REG Question {i} for SharePoint upload?",
                "answer": f"Answer {i}"
            }
            for i in range(1, 11)
        ]
        
        data = {
            "round_type": "REG",
            "name": f"SharePoint_Test_REG_{int(time.time())}",
            "questions": questions
        }
        
        success, response = self.run_test("Create Test REG Round", "POST", "rounds", 200, data)
        if success and 'id' in response:
            self.test_round_id = response['id']
            self.log(f"Created test round with ID: {self.test_round_id}", "INFO")
        return success, response

    def test_sharepoint_upload(self):
        """Test POST /api/rounds/{id}/upload-sharepoint endpoint"""
        if not self.test_round_id:
            self.log("No test round available for SharePoint upload", "WARN")
            return False, {}
            
        success, response = self.run_test(
            f"SharePoint Upload for Round {self.test_round_id}",
            "POST", 
            f"rounds/{self.test_round_id}/upload-sharepoint"
        )
        
        if success:
            self.log(f"SharePoint Upload Response: {json.dumps(response, indent=2)}", "INFO")
            
            # Check expected response fields
            expected_fields = ['status', 'message']
            for field in expected_fields:
                if field in response:
                    self.log(f"✓ Response contains {field}: {response[field]}", "PASS")
                else:
                    self.log(f"✗ Response missing {field}", "FAIL")
                    
        return success, response

    def cleanup_test_round(self):
        """Delete the test round"""
        if self.test_round_id:
            self.run_test(f"Delete Test Round", "DELETE", f"rounds/{self.test_round_id}")

    def run_sharepoint_tests(self):
        """Run all SharePoint-specific tests"""
        self.log("Starting SharePoint Integration Test Suite", "INFO")
        self.log(f"Testing against: {self.base_url}", "INFO")
        
        # Test 1: Detailed SharePoint status check
        self.test_sharepoint_status_detailed()
        
        # Test 2: Create a test round
        self.create_test_round()
        
        # Test 3: Test SharePoint upload endpoint
        self.test_sharepoint_upload()
        
        # Test 4: Cleanup
        self.cleanup_test_round()
        
        # Print summary
        print("\n" + "="*50)
        print(f"📊 SHAREPOINT TEST SUMMARY")
        print(f"Tests Run: {self.tests_run}")
        print(f"Tests Passed: {self.tests_passed}")
        print(f"Tests Failed: {self.tests_run - self.tests_passed}")
        print(f"Success Rate: {(self.tests_passed/self.tests_run)*100:.1f}%")
        print("="*50)
        
        return self.tests_passed == self.tests_run

def main():
    """Main test execution"""
    tester = SharePointTester()
    success = tester.run_sharepoint_tests()
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())