import requests
import sys
import json
from datetime import datetime
from pathlib import Path
import tempfile
import zipfile
from xml.etree import ElementTree as ET

class TriviaAPITester:
    def __init__(self, base_url="https://trivia-generator.preview.emergentagent.com/api"):
        self.base_url = base_url
        self.tests_run = 0
        self.tests_passed = 0
        self.created_rounds = []

    def run_test(self, name, method, endpoint, expected_status, data=None, files=None, response_type="json"):
        """Run a single API test"""
        url = f"{self.base_url}/{endpoint}" if endpoint else self.base_url
        headers = {'Content-Type': 'application/json'} if not files else {}

        self.tests_run += 1
        print(f"\n🔍 Testing {name}...")
        
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

            success = response.status_code == expected_status
            if success:
                self.tests_passed += 1
                print(f"✅ Passed - Status: {response.status_code}")
                
                if response_type == "json" and response.content:
                    return success, response.json()
                elif response_type == "blob":
                    return success, response.content
                else:
                    return success, {}
            else:
                print(f"❌ Failed - Expected {expected_status}, got {response.status_code}")
                if response.content:
                    try:
                        error_data = response.json()
                        print(f"   Error details: {error_data}")
                    except:
                        print(f"   Response: {response.text[:200]}")
                return False, {}

        except Exception as e:
            print(f"❌ Failed - Error: {str(e)}")
            return False, {}

    def test_health_endpoint(self):
        """Test the health endpoint"""
        success, response = self.run_test(
            "Health Check",
            "GET", 
            "",
            200
        )
        return success

    def test_sharepoint_status(self):
        """Test SharePoint status endpoint"""
        success, response = self.run_test(
            "SharePoint Status",
            "GET",
            "sharepoint-status",
            200
        )
        if success:
            print(f"   SharePoint configured: {response.get('configured', False)}")
            print(f"   Token valid: {response.get('token_valid', False)}")
        return success

    def test_reg_title_images(self):
        """Test REG title images endpoint - should return list of 20 categories"""
        success, response = self.run_test(
            "REG Title Images",
            "GET",
            "reg-title-images",
            200
        )
        if success:
            images = response.get('images', [])
            print(f"   Found {len(images)} title images")
            if len(images) >= 15:  # Should have around 20, but allow some flexibility
                print("✅ REG title images loaded successfully")
                # Store first image for testing
                if images:
                    self.test_image = images[0]
                    print(f"   Sample image: {self.test_image.get('name_no_ext')}")
                return True
            else:
                print(f"❌ Expected ~20 images, got {len(images)}")
                return False
        return False

    def test_reg_next_number(self, category="Sports"):
        """Test REG next number endpoint - should return underscore format"""
        success, response = self.run_test(
            f"REG Next Number for {category}",
            "GET",
            f"reg-next-number/{category}",
            200
        )
        if success:
            next_num = response.get('next_number', 0)
            round_name = response.get('round_name', '')
            existing_count = response.get('existing_count', 0)
            
            print(f"   Next number for {category}: {next_num}")
            print(f"   Round name: {round_name}")
            print(f"   Existing count: {existing_count}")
            
            # Verify underscore format: Category_Number
            expected_name = f"{category}_{next_num}"
            if next_num >= 1 and round_name == expected_name:
                print(f"✅ REG next number working correctly with underscore format")
                return True, next_num, round_name
            else:
                print(f"❌ Expected format '{expected_name}', got '{round_name}'")
                return False, 0, ''
        return False, 0, ''

    def test_reg_download_title_image(self):
        """Test downloading a title image from SharePoint"""
        if not hasattr(self, 'test_image') or not self.test_image:
            print("❌ No test image available for download test")
            return False
            
        img = self.test_image
        success, response = self.run_test(
            f"Download Title Image: {img.get('name_no_ext')}",
            "POST",
            f"reg-download-title-image?item_id={img.get('item_id')}&drive_id={img.get('drive_id')}&filename={img.get('name')}",
            200
        )
        if success:
            file_id = response.get('file_id')
            filename = response.get('filename')
            print(f"   Downloaded file_id: {file_id}")
            print(f"   Filename: {filename}")
            if file_id and filename:
                self.downloaded_file_id = file_id
                self.downloaded_filename = filename
                print("✅ Title image download working correctly")
                return True
            else:
                print("❌ Missing file_id or filename in response")
                return False
        return False

    def test_serve_uploaded_image(self):
        """Test serving downloaded images via /uploads endpoint"""
        if not hasattr(self, 'downloaded_filename') or not self.downloaded_filename:
            print("❌ No downloaded file to test serving")
            return False
            
        success, image_data = self.run_test(
            f"Serve Uploaded Image: {self.downloaded_filename}",
            "GET",
            f"uploads/{self.downloaded_filename}",
            200,
            response_type="blob"
        )
        if success and image_data:
            print(f"   Image served successfully, size: {len(image_data)} bytes")
            if len(image_data) > 1000:  # Should be a reasonable image size
                print("✅ Image serving working correctly")
                return True
            else:
                print("❌ Image data seems too small")
                return False
        return False

    def create_mc_round(self):
        """Create a Multiple Choice round for testing"""
        mc_data = {
            "round_type": "MC",
            "name": f"Test MC Round {datetime.now().strftime('%H%M%S')}",
            "questions": [
                {
                    "number": i+1,
                    "question": f"MC Question {i+1}?",
                    "answer": f"A) Option A for Q{i+1}",
                    "options": [f"Option A for Q{i+1}", f"Option B for Q{i+1}", f"Option C for Q{i+1}", f"Option D for Q{i+1}"],
                    "correctOption": 0
                }
                for i in range(10)
            ]
        }
        
        success, response = self.run_test(
            "Create MC Round",
            "POST",
            "rounds",
            200,
            data=mc_data
        )
        
        if success:
            round_id = response.get('id')
            self.created_rounds.append(round_id)
            print(f"   Created MC round ID: {round_id}")
            return round_id
        return None

    def create_reg_round(self, category="Sports", number=None, use_underscore_format=True):
        """Create a REG round for testing with category-based naming"""
        if number is None:
            number = datetime.now().strftime('%H%M%S')
        
        # Use underscore format for new naming convention
        if use_underscore_format:
            round_name = f"{category}_{number}"
        else:
            round_name = f"{category} {number}"
            
        reg_data = {
            "round_type": "REG", 
            "name": round_name,
            "questions": [
                {
                    "number": i+1,
                    "question": f"REG Question {i+1}?",
                    "answer": f"Answer {i+1}"
                }
                for i in range(10)
            ],
            "cover_image_id": getattr(self, 'downloaded_file_id', None)  # Use downloaded image if available
        }
        
        success, response = self.run_test(
            "Create REG Round",
            "POST",
            "rounds",
            200,
            data=reg_data
        )
        
        if success:
            round_id = response.get('id')
            self.created_rounds.append(round_id)
            print(f"   Created REG round ID: {round_id}")
            print(f"   Round name: {response.get('name')}")
            return round_id
        return None

    def test_mc_pptx_generation(self, round_id):
        """Test MC PowerPoint generation and verify slide count"""
        success, pptx_data = self.run_test(
            "Generate MC PPTX",
            "POST",
            f"rounds/{round_id}/generate",
            200,
            response_type="blob"
        )
        
        if success and pptx_data:
            # Save to temporary file and analyze
            with tempfile.NamedTemporaryFile(suffix='.pptx', delete=False) as temp_file:
                temp_file.write(pptx_data)
                temp_path = temp_file.name
            
            slide_count = self.count_pptx_slides(temp_path)
            print(f"   PPTX file size: {len(pptx_data)} bytes")
            print(f"   Slide count: {slide_count}")
            
            # Clean up
            Path(temp_path).unlink()
            
            # Verify MC round has exactly 14 slides
            if slide_count == 14:
                print("✅ MC PPTX has correct slide count (14)")
                return True
            else:
                print(f"❌ MC PPTX has {slide_count} slides, expected 14")
                return False
        return False

    def test_reg_pptx_generation(self, round_id):
        """Test REG PowerPoint generation and verify slide count"""
        success, pptx_data = self.run_test(
            "Generate REG PPTX",
            "POST",
            f"rounds/{round_id}/generate",
            200,
            response_type="blob"
        )
        
        if success and pptx_data:
            # Save to temporary file and analyze
            with tempfile.NamedTemporaryFile(suffix='.pptx', delete=False) as temp_file:
                temp_file.write(pptx_data)
                temp_path = temp_file.name
            
            slide_count = self.count_pptx_slides(temp_path)
            print(f"   PPTX file size: {len(pptx_data)} bytes")
            print(f"   Slide count: {slide_count}")
            
            # Clean up
            Path(temp_path).unlink()
            
            # Verify REG round has exactly 14 slides (same as MC)
            if slide_count == 14:
                print("✅ REG PPTX has correct slide count (14)")
                return True
            else:
                print(f"❌ REG PPTX has {slide_count} slides, expected 14")
                return False
        return False

    def count_pptx_slides(self, pptx_path):
        """Count slides in a PPTX file"""
        try:
            with zipfile.ZipFile(pptx_path, 'r') as zip_file:
                # Count slide XML files
                slide_files = [f for f in zip_file.namelist() if f.startswith('ppt/slides/slide') and f.endswith('.xml')]
                return len(slide_files)
        except Exception as e:
            print(f"Error counting slides: {e}")
            return 0

    def test_duplicate_round(self, round_id):
        """Test round duplication"""
        success, response = self.run_test(
            "Duplicate Round",
            "POST",
            f"rounds/{round_id}/duplicate",
            200
        )
        
        if success:
            new_id = response.get('id')
            self.created_rounds.append(new_id)
            print(f"   Duplicated round ID: {new_id}")
            print(f"   New name: {response.get('name')}")
            return new_id
        return None

    def test_list_rounds(self):
        """Test listing all rounds"""
        success, response = self.run_test(
            "List Rounds",
            "GET",
            "rounds",
            200
        )
        
        if success:
            print(f"   Found {len(response)} rounds")
            return True
        return False

    def test_get_round(self, round_id):
        """Test getting a specific round"""
        success, response = self.run_test(
            "Get Round Details",
            "GET",
            f"rounds/{round_id}",
            200
        )
        
        if success:
            print(f"   Round type: {response.get('round_type')}")
            print(f"   Questions: {len(response.get('questions', []))}")
            return True
        return False

    def test_multiple_categories_naming(self):
        """Test REG next number for multiple categories to verify underscore format"""
        categories_to_test = ["1980s", "Sports", "1970s"]
        results = {}
        
        print("\n🔍 Testing multiple REG categories for underscore naming...")
        
        for category in categories_to_test:
            success, next_num, round_name = self.test_reg_next_number(category)
            results[category] = {
                'success': success,
                'next_number': next_num,
                'round_name': round_name
            }
            
            # Verify the format is Category_Number
            if success:
                expected_format = f"{category}_{next_num}"
                if round_name == expected_format:
                    print(f"✅ {category}: Correct format '{round_name}'")
                else:
                    print(f"❌ {category}: Expected '{expected_format}', got '{round_name}'")
                    results[category]['success'] = False
        
        return results

    def cleanup_rounds(self):
        """Clean up created test rounds"""
        print(f"\n🧹 Cleaning up {len(self.created_rounds)} test rounds...")
        for round_id in self.created_rounds:
            success, _ = self.run_test(
                f"Delete Round {round_id}",
                "DELETE",
                f"rounds/{round_id}",
                200
            )
            if success:
                print(f"   ✅ Deleted {round_id}")

def main():
    """Main test execution"""
    print("🎯 Starting BIG Hat Trivia API Tests")
    print("=" * 50)
    
    tester = TriviaAPITester()
    
    # Basic health checks
    if not tester.test_health_endpoint():
        print("❌ Health check failed - stopping tests")
        return 1
        
    tester.test_sharepoint_status()
    
    # Test new REG-specific endpoints
    print("\n🔍 Testing REG-specific endpoints...")
    reg_images_success = tester.test_reg_title_images()
    
    if reg_images_success:
        # Test multiple categories for underscore naming format
        category_results = tester.test_multiple_categories_naming()
        
        # Test image download
        download_success = tester.test_reg_download_title_image()
        
        if download_success:
            # Test serving downloaded images
            serve_success = tester.test_serve_uploaded_image()
    
    # Create test rounds
    mc_round_id = tester.create_mc_round()
    
    # Create REG round with downloaded image if available
    if hasattr(tester, 'downloaded_file_id'):
        reg_round_id = tester.create_reg_round("Sports", 1)
    else:
        reg_round_id = tester.create_reg_round()
    
    if not mc_round_id or not reg_round_id:
        print("❌ Failed to create test rounds - stopping tests")
        return 1
    
    # Test round operations
    tester.test_list_rounds()
    tester.test_get_round(mc_round_id)
    tester.test_get_round(reg_round_id)
    
    # Test PowerPoint generation (main feature being tested)
    mc_pptx_success = tester.test_mc_pptx_generation(mc_round_id)
    reg_pptx_success = tester.test_reg_pptx_generation(reg_round_id)
    
    # Test duplication
    duplicated_id = tester.test_duplicate_round(mc_round_id)
    
    # Test that creating another REG round with same category increments number
    if hasattr(tester, 'downloaded_file_id'):
        print("\n🔍 Testing REG auto-numbering with underscore format...")
        next_num_success2, next_num2, round_name2 = tester.test_reg_next_number("Sports")
        if next_num_success2 and next_num2 > 1:
            print(f"✅ REG auto-numbering working: {round_name2}")
        else:
            print(f"❌ REG auto-numbering issue: expected > 1, got {next_num2}")
    
    # Test specific categories mentioned in requirements
    print("\n🔍 Testing specific categories from requirements...")
    test_categories = ["1980s", "Sports", "1970s"]
    for cat in test_categories:
        success, num, name = tester.test_reg_next_number(cat)
        if success:
            print(f"✅ {cat} -> {name} (next number: {num})")
        else:
            print(f"❌ Failed to get next number for {cat}")
    
    # Clean up
    tester.cleanup_rounds()
    
    # Print results
    print("\n" + "=" * 50)
    print(f"📊 Test Results: {tester.tests_passed}/{tester.tests_run} passed")
    
    # Specific checks for the review requirements
    if mc_pptx_success:
        print("✅ MC PowerPoint generation working correctly")
    else:
        print("❌ MC PowerPoint generation has issues")
        
    if reg_pptx_success:
        print("✅ REG PowerPoint generation working correctly") 
    else:
        print("❌ REG PowerPoint generation has issues")
    
    # REG-specific feature checks
    if reg_images_success:
        print("✅ REG title images endpoint working correctly")
    else:
        print("❌ REG title images endpoint has issues")
    
    success_rate = (tester.tests_passed / tester.tests_run) * 100 if tester.tests_run > 0 else 0
    print(f"📈 Success Rate: {success_rate:.1f}%")
    
    return 0 if tester.tests_passed == tester.tests_run else 1

if __name__ == "__main__":
    sys.exit(main())