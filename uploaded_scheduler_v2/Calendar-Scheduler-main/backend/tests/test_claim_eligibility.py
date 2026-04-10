"""
Tests for Primary/Secondary venue role claiming rules:
1. Primaries get early access to claim events at their venue+category immediately when events are added
2. If a primary has blackout dates overlapping an event, that event auto-opens to all
3. If a primary hasn't claimed by the Sunday prior to the event, it opens to all
4. Events are typically added a month in advance

Test data context:
- Venue: Whining Pig Downtown (88b01df3-8f99-41b1-a839-4676aff9b5ef)
  - Trivia primary: Chloe R. (3b3566d6-e530-4d34-85e0-bad35e82e9af)
  - Bingo/Karaoke primary: Chase B. (8e1389db-3b0c-4dbf-b377-e763ac18fdfb)
- Non-primary employee: Nick S. (2d3a5242-1d4a-4379-bda9-ba824228afbc)
"""
import pytest
import requests
import os
from datetime import datetime, timedelta
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test data constants
WHINING_PIG_DOWNTOWN_ID = "88b01df3-8f99-41b1-a839-4676aff9b5ef"
CHLOE_ID = "3b3566d6-e530-4d34-85e0-bad35e82e9af"  # Primary for trivia at Whining Pig Downtown
CHASE_ID = "8e1389db-3b0c-4dbf-b377-e763ac18fdfb"  # Primary for bingo_karaoke at Whining Pig Downtown
NICK_ID = "2d3a5242-1d4a-4379-bda9-ba824228afbc"   # Non-primary at Whining Pig Downtown


@pytest.fixture(scope="module")
def api_client():
    """Shared requests session"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture(scope="module")
def created_events():
    """Track created events for cleanup"""
    return []


@pytest.fixture(scope="module")
def created_blackouts():
    """Track created blackouts for cleanup"""
    return []


@pytest.fixture(scope="module", autouse=True)
def cleanup(api_client, created_events, created_blackouts):
    """Cleanup test-created data after all tests"""
    yield
    for event_id in created_events:
        try:
            api_client.delete(f"{BASE_URL}/api/events/{event_id}")
        except:
            pass
    for blackout_id in created_blackouts:
        try:
            api_client.delete(f"{BASE_URL}/api/blackouts/{blackout_id}")
        except:
            pass


class TestClaimEligibilityEndpoint:
    """Test GET /api/events/claim-eligibility endpoint"""
    
    def test_claim_eligibility_returns_200(self, api_client):
        """Endpoint should return 200"""
        response = api_client.get(f"{BASE_URL}/api/events/claim-eligibility")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
    def test_claim_eligibility_returns_dict(self, api_client):
        """Response should be a dictionary with event_id keys"""
        response = api_client.get(f"{BASE_URL}/api/events/claim-eligibility")
        data = response.json()
        assert isinstance(data, dict), f"Expected dict, got {type(data)}"


class TestPrimaryLockedEvent:
    """Test that events at venues with primaries are initially locked for the primary"""
    
    def test_create_event_at_venue_with_primary_returns_primary_only(self, api_client, created_events):
        """Creating an event at a venue with primary should mark it as primary_only in eligibility"""
        # Create a trivia event at Whining Pig Downtown (has Chloe as trivia primary)
        # Event should be far enough in the future that Sunday deadline hasn't passed
        future_date = datetime.utcnow() + timedelta(days=30)  # 30 days from now
        
        payload = {
            "title": "TEST_Primary_Lock_Trivia",
            "event_type": "Trivia",
            "venue_id": WHINING_PIG_DOWNTOWN_ID,
            "date": future_date.isoformat(),
            "duration_hours": 2.0
        }
        
        response = api_client.post(f"{BASE_URL}/api/events", json=payload)
        assert response.status_code == 200, f"Failed to create event: {response.text}"
        
        event_data = response.json()
        event_id = event_data["id"]
        created_events.append(event_id)
        
        # Check eligibility
        elig_response = api_client.get(f"{BASE_URL}/api/events/claim-eligibility")
        assert elig_response.status_code == 200
        eligibility = elig_response.json()
        
        assert event_id in eligibility, f"Event {event_id} not found in eligibility response"
        assert eligibility[event_id]["status"] == "primary_only", \
            f"Expected 'primary_only', got '{eligibility[event_id]['status']}'"
        assert eligibility[event_id]["primary_employee_id"] == CHLOE_ID, \
            f"Expected primary to be Chloe ({CHLOE_ID}), got {eligibility[event_id]['primary_employee_id']}"
        assert "opens_at" in eligibility[event_id], "Missing 'opens_at' field"
        
        print(f"SUCCESS: Event created with primary_only status, primary={CHLOE_ID}")
    
    def test_music_bingo_locked_for_chase(self, api_client, created_events):
        """Music Bingo event at Whining Pig Downtown should be locked for Chase (bingo_karaoke primary)"""
        future_date = datetime.utcnow() + timedelta(days=28)
        
        payload = {
            "title": "TEST_Primary_Lock_MusicBingo",
            "event_type": "Music Bingo",
            "venue_id": WHINING_PIG_DOWNTOWN_ID,
            "date": future_date.isoformat(),
            "duration_hours": 2.0
        }
        
        response = api_client.post(f"{BASE_URL}/api/events", json=payload)
        assert response.status_code == 200, f"Failed to create event: {response.text}"
        
        event_data = response.json()
        event_id = event_data["id"]
        created_events.append(event_id)
        
        # Check eligibility
        elig_response = api_client.get(f"{BASE_URL}/api/events/claim-eligibility")
        eligibility = elig_response.json()
        
        assert event_id in eligibility
        assert eligibility[event_id]["status"] == "primary_only"
        assert eligibility[event_id]["primary_employee_id"] == CHASE_ID
        
        print(f"SUCCESS: Music Bingo event locked for Chase ({CHASE_ID})")


class TestNonPrimaryCannotClaim:
    """Test that non-primary users get 403 when trying to claim primary-locked events"""
    
    def test_non_primary_cannot_claim_locked_event(self, api_client, created_events):
        """Non-primary user should get 403 when trying to claim a locked event"""
        # First create a trivia event at Whining Pig Downtown
        future_date = datetime.utcnow() + timedelta(days=25)
        
        payload = {
            "title": "TEST_NonPrimary_Reject_Trivia",
            "event_type": "Trivia",
            "venue_id": WHINING_PIG_DOWNTOWN_ID,
            "date": future_date.isoformat(),
            "duration_hours": 2.0
        }
        
        response = api_client.post(f"{BASE_URL}/api/events", json=payload)
        assert response.status_code == 200
        event_id = response.json()["id"]
        created_events.append(event_id)
        
        # Try to claim as Nick (non-primary)
        claim_response = api_client.post(f"{BASE_URL}/api/events/{event_id}/claim", json={
            "employee_id": NICK_ID
        })
        
        assert claim_response.status_code == 403, \
            f"Expected 403 for non-primary claim, got {claim_response.status_code}: {claim_response.text}"
        
        detail = claim_response.json().get("detail", "")
        assert "reserved" in detail.lower() or "primary" in detail.lower(), \
            f"Error message should mention reservation/primary: {detail}"
        
        print(f"SUCCESS: Non-primary user correctly rejected with 403")


class TestPrimaryCanClaim:
    """Test that primary users CAN claim their locked events"""
    
    def test_primary_can_claim_locked_event(self, api_client, created_events):
        """Primary user should be able to claim their locked event"""
        future_date = datetime.utcnow() + timedelta(days=22)
        
        payload = {
            "title": "TEST_Primary_Claim_Trivia",
            "event_type": "Trivia",
            "venue_id": WHINING_PIG_DOWNTOWN_ID,
            "date": future_date.isoformat(),
            "duration_hours": 2.0
        }
        
        response = api_client.post(f"{BASE_URL}/api/events", json=payload)
        assert response.status_code == 200
        event_id = response.json()["id"]
        created_events.append(event_id)
        
        # Verify it's locked for primary first
        elig_response = api_client.get(f"{BASE_URL}/api/events/claim-eligibility")
        eligibility = elig_response.json()
        assert event_id in eligibility
        assert eligibility[event_id]["status"] == "primary_only"
        
        # Claim as Chloe (the primary for trivia)
        claim_response = api_client.post(f"{BASE_URL}/api/events/{event_id}/claim", json={
            "employee_id": CHLOE_ID
        })
        
        assert claim_response.status_code == 200, \
            f"Expected 200 for primary claim, got {claim_response.status_code}: {claim_response.text}"
        
        # Verify the claim
        event_response = api_client.get(f"{BASE_URL}/api/events/{event_id}")
        event_data = event_response.json()
        assert event_data["claimed_by"] == CHLOE_ID
        assert event_data["status"] == "claimed"
        
        print(f"SUCCESS: Primary user (Chloe) successfully claimed their locked event")


class TestBlackoutDateOpensEvent:
    """Test that events open to all when primary has blackout dates on event date"""
    
    def test_event_opens_when_primary_has_blackout(self, api_client, created_events, created_blackouts):
        """Event should become 'open' when primary has a blackout on that date"""
        # Choose a date far in the future
        event_date = datetime.utcnow() + timedelta(days=45)
        event_date_str = event_date.strftime("%Y-%m-%d")
        
        # First create a blackout for Chloe (trivia primary) on that date
        blackout_payload = {
            "employee_id": CHLOE_ID,
            "start_date": event_date_str,
            "end_date": event_date_str
        }
        
        blackout_response = api_client.post(f"{BASE_URL}/api/blackouts", json=blackout_payload)
        assert blackout_response.status_code == 200, f"Failed to create blackout: {blackout_response.text}"
        blackout_id = blackout_response.json()["id"]
        created_blackouts.append(blackout_id)
        
        # Now create an event on the same date
        event_payload = {
            "title": "TEST_Blackout_Opens_Trivia",
            "event_type": "Trivia",
            "venue_id": WHINING_PIG_DOWNTOWN_ID,
            "date": event_date.isoformat(),
            "duration_hours": 2.0
        }
        
        event_response = api_client.post(f"{BASE_URL}/api/events", json=event_payload)
        assert event_response.status_code == 200
        event_id = event_response.json()["id"]
        created_events.append(event_id)
        
        # Check eligibility - should be open
        elig_response = api_client.get(f"{BASE_URL}/api/events/claim-eligibility")
        eligibility = elig_response.json()
        
        assert event_id in eligibility, f"Event {event_id} not in eligibility"
        assert eligibility[event_id]["status"] == "open", \
            f"Expected 'open' due to blackout, got '{eligibility[event_id]['status']}'"
        
        print(f"SUCCESS: Event correctly opens to all when primary has blackout")
    
    def test_anyone_can_claim_event_with_primary_blackout(self, api_client, created_events, created_blackouts):
        """Non-primary should be able to claim event when primary has blackout"""
        event_date = datetime.utcnow() + timedelta(days=50)
        event_date_str = event_date.strftime("%Y-%m-%d")
        
        # Create blackout for Chloe
        blackout_payload = {
            "employee_id": CHLOE_ID,
            "start_date": event_date_str,
            "end_date": event_date_str
        }
        blackout_response = api_client.post(f"{BASE_URL}/api/blackouts", json=blackout_payload)
        assert blackout_response.status_code == 200
        created_blackouts.append(blackout_response.json()["id"])
        
        # Create trivia event
        event_payload = {
            "title": "TEST_Blackout_AllowClaim_Trivia",
            "event_type": "Trivia",
            "venue_id": WHINING_PIG_DOWNTOWN_ID,
            "date": event_date.isoformat(),
            "duration_hours": 2.0
        }
        event_response = api_client.post(f"{BASE_URL}/api/events", json=event_payload)
        assert event_response.status_code == 200
        event_id = event_response.json()["id"]
        created_events.append(event_id)
        
        # Nick (non-primary) should be able to claim
        claim_response = api_client.post(f"{BASE_URL}/api/events/{event_id}/claim", json={
            "employee_id": NICK_ID
        })
        
        assert claim_response.status_code == 200, \
            f"Expected 200 for claim when primary has blackout, got {claim_response.status_code}: {claim_response.text}"
        
        print(f"SUCCESS: Non-primary can claim event when primary has blackout")


class TestSundayDeadlineOpensEvent:
    """Test that events open to all when Sunday prior to event has passed"""
    
    def test_event_opens_after_sunday_deadline(self, api_client, created_events):
        """Event in current week (Sunday deadline passed) should be 'open'"""
        # Create an event for this week (within 6 days from today)
        # This should be past the "Sunday prior" deadline
        today = datetime.utcnow()
        
        # Find a date within this week but in the future
        days_until_sunday = (6 - today.weekday()) % 7
        if days_until_sunday == 0:
            days_until_sunday = 7  # If today is Sunday, go to next Sunday
        
        # Event for tomorrow or day after
        event_date = today + timedelta(days=2)
        
        event_payload = {
            "title": "TEST_Sunday_Deadline_Trivia",
            "event_type": "Trivia",
            "venue_id": WHINING_PIG_DOWNTOWN_ID,
            "date": event_date.isoformat(),
            "duration_hours": 2.0
        }
        
        event_response = api_client.post(f"{BASE_URL}/api/events", json=event_payload)
        assert event_response.status_code == 200
        event_id = event_response.json()["id"]
        created_events.append(event_id)
        
        # Check eligibility - should be open since we're past the prior Sunday
        elig_response = api_client.get(f"{BASE_URL}/api/events/claim-eligibility")
        eligibility = elig_response.json()
        
        assert event_id in eligibility
        # If today is past the Sunday before the event, it should be open
        assert eligibility[event_id]["status"] == "open", \
            f"Expected 'open' for event this week, got '{eligibility[event_id]['status']}'"
        
        print(f"SUCCESS: Event correctly opens after Sunday deadline passes")


class TestNoPrimaryAssignedOpens:
    """Test that events with no primary assigned are open to all"""
    
    def test_event_at_venue_without_primary_is_open(self, api_client, created_events):
        """Event at venue without primary for that category should be 'open'"""
        # Valley Craft (bda8a6dd...) doesn't have any primary assigned
        VALLEY_CRAFT_ID = "bda8a6dd-4df6-4790-9cc5-6e2b93397a18"
        
        future_date = datetime.utcnow() + timedelta(days=35)
        
        event_payload = {
            "title": "TEST_NoPrimary_Trivia",
            "event_type": "Trivia",
            "venue_id": VALLEY_CRAFT_ID,
            "date": future_date.isoformat(),
            "duration_hours": 2.0
        }
        
        event_response = api_client.post(f"{BASE_URL}/api/events", json=event_payload)
        assert event_response.status_code == 200
        event_id = event_response.json()["id"]
        created_events.append(event_id)
        
        # Check eligibility
        elig_response = api_client.get(f"{BASE_URL}/api/events/claim-eligibility")
        eligibility = elig_response.json()
        
        assert event_id in eligibility
        assert eligibility[event_id]["status"] == "open", \
            f"Expected 'open' for venue without primary, got '{eligibility[event_id]['status']}'"
        
        print(f"SUCCESS: Event at venue without primary is correctly open to all")
    
    def test_special_event_type_is_open(self, api_client, created_events):
        """Special event type (not trivia/bingo/karaoke) should be open"""
        future_date = datetime.utcnow() + timedelta(days=32)
        
        event_payload = {
            "title": "TEST_Special_Event",
            "event_type": "Special",
            "venue_id": WHINING_PIG_DOWNTOWN_ID,
            "date": future_date.isoformat(),
            "duration_hours": 2.0
        }
        
        event_response = api_client.post(f"{BASE_URL}/api/events", json=event_payload)
        assert event_response.status_code == 200
        event_id = event_response.json()["id"]
        created_events.append(event_id)
        
        # Check eligibility
        elig_response = api_client.get(f"{BASE_URL}/api/events/claim-eligibility")
        eligibility = elig_response.json()
        
        assert event_id in eligibility
        assert eligibility[event_id]["status"] == "open", \
            f"Expected 'open' for Special event type, got '{eligibility[event_id]['status']}'"
        
        print(f"SUCCESS: Special event type is correctly open to all")


class TestClaimEndpointValidation:
    """Test claim endpoint error handling"""
    
    def test_claim_nonexistent_event(self, api_client):
        """Claiming nonexistent event should return 404"""
        fake_id = str(uuid.uuid4())
        response = api_client.post(f"{BASE_URL}/api/events/{fake_id}/claim", json={
            "employee_id": NICK_ID
        })
        assert response.status_code == 404
        
    def test_claim_with_nonexistent_employee(self, api_client, created_events):
        """Claiming with nonexistent employee should return 404"""
        future_date = datetime.utcnow() + timedelta(days=40)
        
        # Create event first
        event_payload = {
            "title": "TEST_Invalid_Employee_Claim",
            "event_type": "Trivia",
            "venue_id": WHINING_PIG_DOWNTOWN_ID,
            "date": future_date.isoformat(),
            "duration_hours": 2.0
        }
        event_response = api_client.post(f"{BASE_URL}/api/events", json=event_payload)
        event_id = event_response.json()["id"]
        created_events.append(event_id)
        
        # Try to claim with fake employee
        fake_employee_id = str(uuid.uuid4())
        response = api_client.post(f"{BASE_URL}/api/events/{event_id}/claim", json={
            "employee_id": fake_employee_id
        })
        assert response.status_code == 404
    
    def test_cannot_claim_already_claimed_event(self, api_client, created_events):
        """Claiming already claimed event should return 400"""
        # Create an event that's open (this week)
        event_date = datetime.utcnow() + timedelta(days=1)
        
        event_payload = {
            "title": "TEST_Double_Claim_Check",
            "event_type": "Trivia",
            "venue_id": WHINING_PIG_DOWNTOWN_ID,
            "date": event_date.isoformat(),
            "duration_hours": 2.0
        }
        event_response = api_client.post(f"{BASE_URL}/api/events", json=event_payload)
        event_id = event_response.json()["id"]
        created_events.append(event_id)
        
        # First claim should succeed (event is open)
        claim1_response = api_client.post(f"{BASE_URL}/api/events/{event_id}/claim", json={
            "employee_id": NICK_ID
        })
        assert claim1_response.status_code == 200
        
        # Second claim should fail
        claim2_response = api_client.post(f"{BASE_URL}/api/events/{event_id}/claim", json={
            "employee_id": CHLOE_ID
        })
        assert claim2_response.status_code == 400
        assert "already claimed" in claim2_response.json().get("detail", "").lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
