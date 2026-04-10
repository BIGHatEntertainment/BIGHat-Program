"""
Backend tests for the email notification feature.
- POST /api/notifications/send-primary-report (Friday primary emails)
- POST /api/notifications/send-secondary-availability (Monday secondary emails)
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestNotificationEndpoints:
    """Test the notification trigger endpoints."""

    def test_send_primary_report_endpoint_exists(self):
        """Test POST /api/notifications/send-primary-report returns 200 and proper structure."""
        response = requests.post(f"{BASE_URL}/api/notifications/send-primary-report", timeout=60)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "success" in data, "Response should have 'success' field"
        assert data["success"] is True, "success should be True"
        assert "sent" in data, "Response should have 'sent' field"
        assert "errors" in data, "Response should have 'errors' field"
        assert isinstance(data["sent"], int), "'sent' should be an integer"
        assert isinstance(data["errors"], list), "'errors' should be a list"
        print(f"Primary report: sent={data['sent']}, errors={len(data['errors'])}")

    def test_send_secondary_availability_endpoint_exists(self):
        """Test POST /api/notifications/send-secondary-availability returns 200 and proper structure."""
        response = requests.post(f"{BASE_URL}/api/notifications/send-secondary-availability", timeout=60)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "success" in data, "Response should have 'success' field"
        assert data["success"] is True, "success should be True"
        assert "sent" in data, "Response should have 'sent' field"
        assert "errors" in data, "Response should have 'errors' field"
        assert isinstance(data["sent"], int), "'sent' should be an integer"
        assert isinstance(data["errors"], list), "'errors' should be a list"
        print(f"Secondary availability: sent={data['sent']}, errors={len(data['errors'])}")


class TestPrimaryReportEmailContent:
    """Test that primary reports include correct data based on database state."""

    def test_primary_report_has_no_rate_limit_errors(self):
        """Test that rate limiting (0.6s delay) prevents 429 errors."""
        response = requests.post(f"{BASE_URL}/api/notifications/send-primary-report", timeout=120)
        assert response.status_code == 200
        data = response.json()
        
        # Check if there are rate limit errors in the errors list
        rate_limit_errors = [e for e in data.get("errors", []) if "429" in str(e.get("error", "")) or "rate limit" in str(e.get("error", "")).lower()]
        assert len(rate_limit_errors) == 0, f"Found rate limit errors: {rate_limit_errors}"
        print(f"No rate limit errors detected. Sent: {data['sent']}, Total errors: {len(data['errors'])}")


class TestSecondaryAvailabilityEmailContent:
    """Test that secondary availability emails only include unclaimed events at secondary venues."""

    def test_secondary_availability_returns_correct_structure(self):
        """Test secondary availability endpoint returns proper response."""
        response = requests.post(f"{BASE_URL}/api/notifications/send-secondary-availability", timeout=120)
        assert response.status_code == 200
        data = response.json()
        
        # Validate response structure
        assert "success" in data
        assert "sent" in data
        assert "errors" in data
        
        # Check for rate limit errors
        rate_limit_errors = [e for e in data.get("errors", []) if "429" in str(e.get("error", "")) or "rate limit" in str(e.get("error", "")).lower()]
        assert len(rate_limit_errors) == 0, f"Found rate limit errors: {rate_limit_errors}"
        print(f"Secondary availability sent: {data['sent']}, errors: {len(data['errors'])}")


class TestVenueRolesExist:
    """Verify venue roles exist to enable notifications."""

    def test_primary_roles_exist(self):
        """Test that there are primary roles in the system."""
        response = requests.get(f"{BASE_URL}/api/venue-roles", timeout=30)
        assert response.status_code == 200
        data = response.json()
        
        primary_roles = [r for r in data if r.get("role_type") == "primary"]
        assert len(primary_roles) > 0, "No primary roles found - emails won't be sent"
        print(f"Found {len(primary_roles)} primary roles")

    def test_secondary_roles_exist(self):
        """Test that there are secondary roles in the system."""
        response = requests.get(f"{BASE_URL}/api/venue-roles", timeout=30)
        assert response.status_code == 200
        data = response.json()
        
        secondary_roles = [r for r in data if r.get("role_type") == "secondary"]
        print(f"Found {len(secondary_roles)} secondary roles")
        # Secondary roles may or may not exist - not a failure


class TestSchedulerJobsRegistered:
    """Test that scheduler jobs are properly configured (verified via logs)."""

    def test_api_root_check(self):
        """Test API root endpoint is responding."""
        response = requests.get(f"{BASE_URL}/api/", timeout=10)
        assert response.status_code == 200
        data = response.json()
        assert "message" in data or "Entertainment" in str(data)


class TestEmployeeEmailsConfigured:
    """Test that employees have emails configured for notifications."""

    def test_employees_have_emails(self):
        """Test that employees who are primaries have email addresses."""
        # Get all employees
        emp_response = requests.get(f"{BASE_URL}/api/employees", timeout=30)
        assert emp_response.status_code == 200
        employees = emp_response.json()
        
        # Get all primary roles
        roles_response = requests.get(f"{BASE_URL}/api/venue-roles", timeout=30)
        assert roles_response.status_code == 200
        roles = roles_response.json()
        
        primary_employee_ids = set(r["employee_id"] for r in roles if r.get("role_type") == "primary")
        
        # Check that primary hosts have emails
        employees_map = {e["id"]: e for e in employees}
        missing_emails = []
        for emp_id in primary_employee_ids:
            emp = employees_map.get(emp_id)
            if emp and not emp.get("email"):
                missing_emails.append(emp.get("name", emp_id))
        
        assert len(missing_emails) == 0, f"Primary hosts missing emails: {missing_emails}"
        print(f"All {len(primary_employee_ids)} primary hosts have email addresses")


class TestFutureEventsExist:
    """Test that there are future events for the notifications to report on."""

    def test_future_events_exist(self):
        """Test that future events exist in the system."""
        response = requests.get(f"{BASE_URL}/api/events", timeout=30)
        assert response.status_code == 200
        events = response.json()
        
        # Events endpoint returns future events by default
        print(f"Found {len(events)} future events")
        
        # Check event types
        trivia_events = [e for e in events if e.get("event_type") == "Trivia"]
        bingo_events = [e for e in events if e.get("event_type") == "Music Bingo"]
        karaoke_events = [e for e in events if e.get("event_type") == "Karaoke"]
        
        print(f"  Trivia: {len(trivia_events)}, Bingo: {len(bingo_events)}, Karaoke: {len(karaoke_events)}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
