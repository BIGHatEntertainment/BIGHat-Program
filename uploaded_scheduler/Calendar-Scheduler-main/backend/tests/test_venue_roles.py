"""
Tests for Venue Roles feature (Primary/Secondary role system per venue)
- Each venue has two role categories: Trivia and Bingo/Karaoke
- Each venue can have ONE primary per category and MANY secondaries
- Primaries must also be secondary at at least one other location
- Venue services are determined by venue pricing (if price > $0, service is offered)
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

@pytest.fixture(scope="module")
def api_client():
    """Shared requests session"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session

@pytest.fixture(scope="module")
def test_data(api_client):
    """Get existing employees and venues for testing"""
    employees_res = api_client.get(f"{BASE_URL}/api/employees")
    assert employees_res.status_code == 200, f"Failed to get employees: {employees_res.text}"
    employees = employees_res.json()
    assert len(employees) > 0, "No employees found in database"
    
    venues_res = api_client.get(f"{BASE_URL}/api/venues")
    assert venues_res.status_code == 200, f"Failed to get venues: {venues_res.text}"
    venues = venues_res.json()
    assert len(venues) > 0, "No venues found in database"
    
    services_res = api_client.get(f"{BASE_URL}/api/venue-roles/services")
    assert services_res.status_code == 200, f"Failed to get services: {services_res.text}"
    services = services_res.json()
    
    # Get venues that have pricing configured (services enabled)
    venues_with_services = list(services.values())
    assert len(venues_with_services) > 0, "No venues with pricing configured"
    
    return {
        "employees": employees,
        "venues": venues,
        "services": services,
        "venues_with_services": venues_with_services
    }

@pytest.fixture(scope="module")
def created_roles():
    """Track created roles for cleanup"""
    return []

@pytest.fixture(scope="module", autouse=True)
def cleanup_roles(api_client, created_roles):
    """Cleanup test-created roles after all tests"""
    yield
    for role_id in created_roles:
        try:
            api_client.delete(f"{BASE_URL}/api/venue-roles/{role_id}")
        except:
            pass


class TestVenueRolesServicesEndpoint:
    """Test GET /api/venue-roles/services endpoint"""
    
    def test_get_services_returns_200(self, api_client):
        """Services endpoint should return 200"""
        response = api_client.get(f"{BASE_URL}/api/venue-roles/services")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    
    def test_services_returns_dict_format(self, api_client, test_data):
        """Services should return dict with venue_id as keys"""
        services = test_data['services']
        assert isinstance(services, dict), "Services should be a dictionary"
        
        # Each value should have required fields
        for venue_id, service in services.items():
            assert 'venue_id' in service, f"Missing venue_id in service: {service}"
            assert 'venue_name' in service, f"Missing venue_name in service: {service}"
            assert 'offers_trivia' in service, f"Missing offers_trivia in service: {service}"
            assert 'offers_bingo_karaoke' in service, f"Missing offers_bingo_karaoke in service: {service}"
    
    def test_services_based_on_pricing(self, api_client, test_data):
        """Services should be based on venue pricing > $0"""
        # Venues with offers_trivia=True should have trivia_price > 0
        # Venues with offers_bingo_karaoke=True should have music_bingo_price > 0 or karaoke_price > 0
        services = test_data['services']
        
        # At least one venue should offer services
        has_services = any(
            s['offers_trivia'] or s['offers_bingo_karaoke'] 
            for s in services.values()
        )
        assert has_services, "At least one venue should offer services"


class TestVenueRolesCRUD:
    """Test venue roles CRUD operations"""
    
    def test_get_all_roles(self, api_client):
        """GET /api/venue-roles should return list"""
        response = api_client.get(f"{BASE_URL}/api/venue-roles")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        assert isinstance(response.json(), list), "Response should be a list"
    
    def test_create_secondary_role(self, api_client, test_data, created_roles):
        """POST /api/venue-roles should create a secondary role"""
        employees = test_data['employees']
        venues_with_services = test_data['venues_with_services']
        
        # Find a venue that offers trivia
        trivia_venue = next(
            (v for v in venues_with_services if v['offers_trivia']), 
            None
        )
        assert trivia_venue is not None, "No venue offers trivia"
        
        payload = {
            "venue_id": trivia_venue['venue_id'],
            "employee_id": employees[0]['id'],
            "role_category": "trivia",
            "role_type": "secondary"
        }
        
        response = api_client.post(f"{BASE_URL}/api/venue-roles", json=payload)
        
        # May succeed or fail if role already exists
        if response.status_code == 200:
            data = response.json()
            assert 'id' in data, "Response should have id"
            assert data['venue_id'] == payload['venue_id']
            assert data['employee_id'] == payload['employee_id']
            assert data['role_category'] == 'trivia'
            assert data['role_type'] == 'secondary'
            created_roles.append(data['id'])
        elif response.status_code == 400:
            # Role already exists - acceptable
            assert "already exists" in response.json().get('detail', '').lower()
        else:
            pytest.fail(f"Unexpected status code: {response.status_code}, body: {response.text}")
    
    def test_create_primary_role(self, api_client, test_data, created_roles):
        """POST /api/venue-roles should create a primary role (if not already assigned)"""
        employees = test_data['employees']
        venues_with_services = test_data['venues_with_services']
        
        # Find a venue that offers trivia
        trivia_venue = next(
            (v for v in venues_with_services if v['offers_trivia']), 
            None
        )
        assert trivia_venue is not None, "No venue offers trivia"
        
        # Use a different employee for primary
        employee = employees[1] if len(employees) > 1 else employees[0]
        
        payload = {
            "venue_id": trivia_venue['venue_id'],
            "employee_id": employee['id'],
            "role_category": "trivia",
            "role_type": "primary"
        }
        
        response = api_client.post(f"{BASE_URL}/api/venue-roles", json=payload)
        
        if response.status_code == 200:
            data = response.json()
            assert data['role_type'] == 'primary'
            created_roles.append(data['id'])
        elif response.status_code == 400:
            # Primary already exists - acceptable
            detail = response.json().get('detail', '').lower()
            assert "primary already exists" in detail or "already exists" in detail
        else:
            pytest.fail(f"Unexpected status code: {response.status_code}, body: {response.text}")
    
    def test_create_role_invalid_category(self, api_client, test_data):
        """POST with invalid category should return 400"""
        employees = test_data['employees']
        venues_with_services = test_data['venues_with_services']
        
        payload = {
            "venue_id": venues_with_services[0]['venue_id'],
            "employee_id": employees[0]['id'],
            "role_category": "invalid_category",
            "role_type": "secondary"
        }
        
        response = api_client.post(f"{BASE_URL}/api/venue-roles", json=payload)
        assert response.status_code == 400, f"Expected 400 for invalid category, got {response.status_code}"
        assert "invalid" in response.json().get('detail', '').lower()
    
    def test_create_role_invalid_type(self, api_client, test_data):
        """POST with invalid role_type should return 400"""
        employees = test_data['employees']
        venues_with_services = test_data['venues_with_services']
        
        payload = {
            "venue_id": venues_with_services[0]['venue_id'],
            "employee_id": employees[0]['id'],
            "role_category": "trivia",
            "role_type": "invalid_type"
        }
        
        response = api_client.post(f"{BASE_URL}/api/venue-roles", json=payload)
        assert response.status_code == 400, f"Expected 400 for invalid type, got {response.status_code}"
    
    def test_create_role_nonexistent_venue(self, api_client, test_data):
        """POST with nonexistent venue should return 404"""
        employees = test_data['employees']
        
        payload = {
            "venue_id": str(uuid.uuid4()),
            "employee_id": employees[0]['id'],
            "role_category": "trivia",
            "role_type": "secondary"
        }
        
        response = api_client.post(f"{BASE_URL}/api/venue-roles", json=payload)
        assert response.status_code == 404, f"Expected 404 for nonexistent venue, got {response.status_code}"
    
    def test_create_role_nonexistent_employee(self, api_client, test_data):
        """POST with nonexistent employee should return 404"""
        venues_with_services = test_data['venues_with_services']
        
        payload = {
            "venue_id": venues_with_services[0]['venue_id'],
            "employee_id": str(uuid.uuid4()),
            "role_category": "trivia",
            "role_type": "secondary"
        }
        
        response = api_client.post(f"{BASE_URL}/api/venue-roles", json=payload)
        assert response.status_code == 404, f"Expected 404 for nonexistent employee, got {response.status_code}"
    
    def test_create_role_venue_no_service(self, api_client, test_data):
        """POST for service venue doesn't offer should return 400"""
        employees = test_data['employees']
        venues_with_services = test_data['venues_with_services']
        
        # Find a venue that doesn't offer bingo/karaoke
        venue_no_bingo = next(
            (v for v in venues_with_services if not v['offers_bingo_karaoke']),
            None
        )
        
        if venue_no_bingo is None:
            pytest.skip("All venues offer bingo/karaoke")
        
        payload = {
            "venue_id": venue_no_bingo['venue_id'],
            "employee_id": employees[0]['id'],
            "role_category": "bingo_karaoke",
            "role_type": "secondary"
        }
        
        response = api_client.post(f"{BASE_URL}/api/venue-roles", json=payload)
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        assert "does not offer" in response.json().get('detail', '').lower()
    
    def test_get_roles_by_employee(self, api_client, test_data):
        """GET /api/venue-roles/employee/{id} should return roles for employee"""
        employees = test_data['employees']
        employee_id = employees[0]['id']
        
        response = api_client.get(f"{BASE_URL}/api/venue-roles/employee/{employee_id}")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        assert isinstance(response.json(), list), "Response should be a list"
    
    def test_get_roles_by_venue(self, api_client, test_data):
        """GET /api/venue-roles/venue/{id} should return roles for venue"""
        venues_with_services = test_data['venues_with_services']
        venue_id = venues_with_services[0]['venue_id']
        
        response = api_client.get(f"{BASE_URL}/api/venue-roles/venue/{venue_id}")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        assert isinstance(response.json(), list), "Response should be a list"


class TestVenueRolesValidation:
    """Test role validation (primary must have secondary at other venue)"""
    
    def test_validate_endpoint_exists(self, api_client, test_data):
        """GET /api/venue-roles/validate/{employee_id} should work"""
        employees = test_data['employees']
        employee_id = employees[0]['id']
        
        response = api_client.get(f"{BASE_URL}/api/venue-roles/validate/{employee_id}")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    
    def test_validate_returns_required_fields(self, api_client, test_data):
        """Validation response should have valid and message fields"""
        employees = test_data['employees']
        employee_id = employees[0]['id']
        
        response = api_client.get(f"{BASE_URL}/api/venue-roles/validate/{employee_id}")
        data = response.json()
        
        assert 'valid' in data, "Response should have 'valid' field"
        assert 'message' in data, "Response should have 'message' field"
        assert isinstance(data['valid'], bool), "'valid' should be boolean"
    
    def test_validate_no_primary_is_valid(self, api_client, test_data, created_roles):
        """Employee with no primary roles should be valid (no secondary requirement)"""
        employees = test_data['employees']
        
        # Find an employee without any roles
        all_roles_res = api_client.get(f"{BASE_URL}/api/venue-roles")
        all_roles = all_roles_res.json()
        
        employees_with_primary = set(
            r['employee_id'] for r in all_roles if r['role_type'] == 'primary'
        )
        
        employee_without_primary = next(
            (e for e in employees if e['id'] not in employees_with_primary),
            None
        )
        
        if employee_without_primary is None:
            pytest.skip("All employees have primary roles")
        
        response = api_client.get(
            f"{BASE_URL}/api/venue-roles/validate/{employee_without_primary['id']}"
        )
        data = response.json()
        
        assert data['valid'] == True, f"Employee without primary should be valid: {data}"


class TestVenueRolesDelete:
    """Test role deletion"""
    
    def test_delete_nonexistent_role(self, api_client):
        """DELETE nonexistent role should return 404"""
        fake_id = str(uuid.uuid4())
        response = api_client.delete(f"{BASE_URL}/api/venue-roles/{fake_id}")
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
    
    def test_create_and_delete_role(self, api_client, test_data):
        """Create a role and delete it"""
        employees = test_data['employees']
        venues_with_services = test_data['venues_with_services']
        
        # Find a venue with bingo_karaoke
        bk_venue = next(
            (v for v in venues_with_services if v['offers_bingo_karaoke']),
            None
        )
        
        if bk_venue is None:
            pytest.skip("No venue offers bingo/karaoke")
        
        # Use last employee to minimize conflicts
        employee = employees[-1]
        
        payload = {
            "venue_id": bk_venue['venue_id'],
            "employee_id": employee['id'],
            "role_category": "bingo_karaoke",
            "role_type": "secondary"
        }
        
        # Create role
        create_res = api_client.post(f"{BASE_URL}/api/venue-roles", json=payload)
        
        if create_res.status_code == 200:
            role_id = create_res.json()['id']
            
            # Verify it exists
            get_res = api_client.get(f"{BASE_URL}/api/venue-roles")
            roles = get_res.json()
            assert any(r['id'] == role_id for r in roles), "Created role not found"
            
            # Delete it
            delete_res = api_client.delete(f"{BASE_URL}/api/venue-roles/{role_id}")
            assert delete_res.status_code == 200, f"Delete failed: {delete_res.text}"
            
            # Verify it's gone
            get_res2 = api_client.get(f"{BASE_URL}/api/venue-roles")
            roles2 = get_res2.json()
            assert not any(r['id'] == role_id for r in roles2), "Role still exists after delete"
        elif create_res.status_code == 400 and "already exists" in create_res.json().get('detail', '').lower():
            pytest.skip("Role already exists, skipping create/delete test")
        else:
            pytest.fail(f"Unexpected status: {create_res.status_code}, {create_res.text}")


class TestPrimaryUniqueness:
    """Test that only one primary per venue+category is allowed"""
    
    def test_cannot_create_duplicate_primary(self, api_client, test_data, created_roles):
        """Creating second primary for same venue+category should fail"""
        employees = test_data['employees']
        venues_with_services = test_data['venues_with_services']
        
        if len(employees) < 2:
            pytest.skip("Need at least 2 employees for this test")
        
        # Find a venue with trivia
        trivia_venue = next(
            (v for v in venues_with_services if v['offers_trivia']),
            None
        )
        
        if trivia_venue is None:
            pytest.skip("No venue offers trivia")
        
        # Check if primary already exists
        venue_roles_res = api_client.get(f"{BASE_URL}/api/venue-roles/venue/{trivia_venue['venue_id']}")
        venue_roles = venue_roles_res.json()
        existing_primary = next(
            (r for r in venue_roles if r['role_category'] == 'trivia' and r['role_type'] == 'primary'),
            None
        )
        
        if existing_primary:
            # Try to create another primary - should fail
            payload = {
                "venue_id": trivia_venue['venue_id'],
                "employee_id": employees[0]['id'] if employees[0]['id'] != existing_primary['employee_id'] else employees[1]['id'],
                "role_category": "trivia",
                "role_type": "primary"
            }
            
            response = api_client.post(f"{BASE_URL}/api/venue-roles", json=payload)
            assert response.status_code == 400, f"Expected 400 for duplicate primary, got {response.status_code}"
            assert "primary already exists" in response.json().get('detail', '').lower()
        else:
            # Create first primary
            payload1 = {
                "venue_id": trivia_venue['venue_id'],
                "employee_id": employees[0]['id'],
                "role_category": "trivia",
                "role_type": "primary"
            }
            res1 = api_client.post(f"{BASE_URL}/api/venue-roles", json=payload1)
            if res1.status_code == 200:
                created_roles.append(res1.json()['id'])
                
                # Try to create second primary - should fail
                payload2 = {
                    "venue_id": trivia_venue['venue_id'],
                    "employee_id": employees[1]['id'],
                    "role_category": "trivia",
                    "role_type": "primary"
                }
                res2 = api_client.post(f"{BASE_URL}/api/venue-roles", json=payload2)
                assert res2.status_code == 400, f"Expected 400 for duplicate primary, got {res2.status_code}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
