"""
Test Monthly Expected Income Calculation
Tests the fix for the income calculation bug where:
- User added 2 Karaoke ($160 each), 1 Trivia ($100), 1 Music Bingo ($120) at The Whining Pig Downtown
- Expected $540 (2×$160 + $100 + $120) but app showed $700

Key test scenarios:
1. Regular venue (The Whining Pig Downtown) uses venue_pricing amounts
2. Franchise venue (Monkey Pants) uses fixed $150 per event regardless of type
3. Venue with no pricing is excluded from income total
"""

import pytest
import requests
import os
from datetime import datetime, timedelta

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test venue IDs from the database
WHINING_PIG_DOWNTOWN_ID = "88b01df3-e3f9-4e3a-8e3a-3e3a3e3a3e3a"  # Will be fetched dynamically
MONKEY_PANTS_ID = "6e334fbd"  # Franchise venue

# Expected pricing for The Whining Pig Downtown
WHINING_PIG_PRICING = {
    "trivia_price": 100.0,
    "music_bingo_price": 120.0,
    "karaoke_price": 160.0
}

# Franchise fixed price
FRANCHISE_FIXED_PRICE = 150.0


class TestMonthlyIncomeCalculation:
    """Test the monthly expected income calculation endpoint"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test data - get actual venue IDs"""
        # Get venues
        response = requests.get(f"{BASE_URL}/api/venues")
        assert response.status_code == 200, f"Failed to get venues: {response.text}"
        venues = response.json()
        
        # Find The Whining Pig Downtown
        self.whining_pig = next((v for v in venues if "Whining Pig Downtown" in v['name']), None)
        assert self.whining_pig is not None, "The Whining Pig Downtown venue not found"
        
        # Find Monkey Pants (franchise)
        self.monkey_pants = next((v for v in venues if "Monkey Pants" in v['name']), None)
        assert self.monkey_pants is not None, "Monkey Pants venue not found"
        
        # Find a venue without pricing
        self.venue_without_pricing = next((v for v in venues if "Without Pricing" in v['name']), None)
        
        # Get venue pricing
        pricing_response = requests.get(f"{BASE_URL}/api/venue_pricing")
        assert pricing_response.status_code == 200
        pricing_list = pricing_response.json()
        self.pricing_map = {p['venue_id']: p for p in pricing_list}
        
        # Store created event IDs for cleanup
        self.created_event_ids = []
        
        yield
        
        # Cleanup: Delete all test events
        for event_id in self.created_event_ids:
            try:
                requests.delete(f"{BASE_URL}/api/events/{event_id}")
            except:
                pass
    
    def create_test_event(self, venue_id: str, event_type: str, date: datetime) -> dict:
        """Helper to create a test event"""
        event_data = {
            "title": f"TEST_{event_type}_Income",
            "event_type": event_type,
            "venue_id": venue_id,
            "date": date.isoformat(),
            "duration_hours": 2.0
        }
        response = requests.post(f"{BASE_URL}/api/events", json=event_data)
        assert response.status_code == 200, f"Failed to create event: {response.text}"
        event = response.json()
        self.created_event_ids.append(event['id'])
        return event
    
    def test_venue_pricing_exists(self):
        """Verify The Whining Pig Downtown has correct pricing"""
        pricing = self.pricing_map.get(self.whining_pig['id'])
        assert pricing is not None, "Pricing not found for The Whining Pig Downtown"
        
        print(f"Whining Pig Downtown pricing: Trivia=${pricing['trivia_price']}, Bingo=${pricing['music_bingo_price']}, Karaoke=${pricing['karaoke_price']}")
        
        assert pricing['trivia_price'] == 100.0, f"Expected Trivia=$100, got ${pricing['trivia_price']}"
        assert pricing['music_bingo_price'] == 120.0, f"Expected Music Bingo=$120, got ${pricing['music_bingo_price']}"
        assert pricing['karaoke_price'] == 160.0, f"Expected Karaoke=$160, got ${pricing['karaoke_price']}"
    
    def test_monkey_pants_is_franchise(self):
        """Verify Monkey Pants has venue_pays_host_directly=True"""
        assert self.monkey_pants.get('venue_pays_host_directly') == True, \
            f"Monkey Pants should have venue_pays_host_directly=True, got {self.monkey_pants.get('venue_pays_host_directly')}"
        print(f"Monkey Pants is correctly marked as franchise venue (venue_pays_host_directly=True)")
    
    def test_expected_income_endpoint_exists(self):
        """Test that the expected income endpoint exists and returns data"""
        month = datetime.now().strftime('%Y-%m')
        response = requests.get(f"{BASE_URL}/api/reports/monthly/expected_income?month={month}")
        assert response.status_code == 200, f"Expected income endpoint failed: {response.text}"
        
        data = response.json()
        assert 'total_expected_income' in data
        assert 'events' in data
        assert 'event_count' in data
        print(f"Expected income endpoint working. Total: ${data['total_expected_income']}, Events: {data['event_count']}")
    
    def test_single_trivia_event_income(self):
        """Test income calculation for a single Trivia event at Whining Pig Downtown"""
        # Use April 2026 as the test month (current server month)
        test_date = datetime(2026, 4, 15, 19, 0, 0)
        
        # Create one Trivia event
        event = self.create_test_event(self.whining_pig['id'], 'Trivia', test_date)
        
        # Get expected income for April 2026 filtered by venue
        response = requests.get(
            f"{BASE_URL}/api/reports/monthly/expected_income?month=2026-04&venue_id={self.whining_pig['id']}"
        )
        assert response.status_code == 200
        data = response.json()
        
        # Find our test event in the breakdown
        test_events = [e for e in data['events'] if e['event_id'] == event['id']]
        assert len(test_events) == 1, f"Test event not found in income breakdown"
        
        test_event = test_events[0]
        assert test_event['expected_income'] == 100.0, \
            f"Expected Trivia income $100, got ${test_event['expected_income']}"
        
        print(f"Single Trivia event income: ${test_event['expected_income']} (correct)")
    
    def test_single_music_bingo_event_income(self):
        """Test income calculation for a single Music Bingo event"""
        test_date = datetime(2026, 4, 16, 19, 0, 0)
        
        event = self.create_test_event(self.whining_pig['id'], 'Music Bingo', test_date)
        
        response = requests.get(
            f"{BASE_URL}/api/reports/monthly/expected_income?month=2026-04&venue_id={self.whining_pig['id']}"
        )
        assert response.status_code == 200
        data = response.json()
        
        test_events = [e for e in data['events'] if e['event_id'] == event['id']]
        assert len(test_events) == 1
        
        assert test_events[0]['expected_income'] == 120.0, \
            f"Expected Music Bingo income $120, got ${test_events[0]['expected_income']}"
        
        print(f"Single Music Bingo event income: ${test_events[0]['expected_income']} (correct)")
    
    def test_single_karaoke_event_income(self):
        """Test income calculation for a single Karaoke event"""
        test_date = datetime(2026, 4, 17, 19, 0, 0)
        
        event = self.create_test_event(self.whining_pig['id'], 'Karaoke', test_date)
        
        response = requests.get(
            f"{BASE_URL}/api/reports/monthly/expected_income?month=2026-04&venue_id={self.whining_pig['id']}"
        )
        assert response.status_code == 200
        data = response.json()
        
        test_events = [e for e in data['events'] if e['event_id'] == event['id']]
        assert len(test_events) == 1
        
        assert test_events[0]['expected_income'] == 160.0, \
            f"Expected Karaoke income $160, got ${test_events[0]['expected_income']}"
        
        print(f"Single Karaoke event income: ${test_events[0]['expected_income']} (correct)")
    
    def test_user_scenario_2_karaoke_1_trivia_1_bingo(self):
        """
        THE MAIN BUG TEST:
        User added 2 Karaoke ($160 each), 1 Trivia ($100), 1 Music Bingo ($120)
        Expected: $540 (2×$160 + $100 + $120 = $320 + $100 + $120 = $540)
        
        Note: The original bug report said expected $520 but the math is:
        2×$160 + $100 + $120 = $540
        """
        # Create events on different days in April 2026
        events = []
        events.append(self.create_test_event(self.whining_pig['id'], 'Karaoke', datetime(2026, 4, 20, 19, 0, 0)))
        events.append(self.create_test_event(self.whining_pig['id'], 'Karaoke', datetime(2026, 4, 21, 19, 0, 0)))
        events.append(self.create_test_event(self.whining_pig['id'], 'Trivia', datetime(2026, 4, 22, 19, 0, 0)))
        events.append(self.create_test_event(self.whining_pig['id'], 'Music Bingo', datetime(2026, 4, 23, 19, 0, 0)))
        
        # Get expected income for April 2026 filtered by venue
        response = requests.get(
            f"{BASE_URL}/api/reports/monthly/expected_income?month=2026-04&venue_id={self.whining_pig['id']}"
        )
        assert response.status_code == 200
        data = response.json()
        
        # Find our test events
        test_event_ids = [e['id'] for e in events]
        test_events = [e for e in data['events'] if e['event_id'] in test_event_ids]
        
        assert len(test_events) == 4, f"Expected 4 test events, found {len(test_events)}"
        
        # Calculate total from our test events
        test_total = sum(e['expected_income'] for e in test_events)
        
        # Expected: 2×$160 + $100 + $120 = $540
        expected_total = 2 * 160.0 + 100.0 + 120.0  # = 540
        
        print(f"\n=== USER SCENARIO TEST ===")
        print(f"Events created:")
        for e in test_events:
            print(f"  - {e['event_type']}: ${e['expected_income']}")
        print(f"Total from test events: ${test_total}")
        print(f"Expected total: ${expected_total}")
        
        assert test_total == expected_total, \
            f"INCOME CALCULATION BUG! Expected ${expected_total}, got ${test_total}"
        
        print(f"✓ Income calculation is CORRECT: ${test_total}")
    
    def test_franchise_venue_fixed_price(self):
        """Test that Monkey Pants (franchise) uses fixed $150 per event regardless of type"""
        # Create events at Monkey Pants
        events = []
        events.append(self.create_test_event(self.monkey_pants['id'], 'Trivia', datetime(2026, 4, 24, 19, 0, 0)))
        events.append(self.create_test_event(self.monkey_pants['id'], 'Music Bingo', datetime(2026, 4, 25, 19, 0, 0)))
        events.append(self.create_test_event(self.monkey_pants['id'], 'Karaoke', datetime(2026, 4, 26, 19, 0, 0)))
        
        # Get expected income for April 2026 filtered by Monkey Pants
        response = requests.get(
            f"{BASE_URL}/api/reports/monthly/expected_income?month=2026-04&venue_id={self.monkey_pants['id']}"
        )
        assert response.status_code == 200
        data = response.json()
        
        # Find our test events
        test_event_ids = [e['id'] for e in events]
        test_events = [e for e in data['events'] if e['event_id'] in test_event_ids]
        
        print(f"\n=== FRANCHISE VENUE TEST (Monkey Pants) ===")
        for e in test_events:
            print(f"  - {e['event_type']}: ${e['expected_income']} (venue_pays_host_directly: {e.get('venue_pays_host_directly')})")
            assert e['expected_income'] == FRANCHISE_FIXED_PRICE, \
                f"Franchise venue should use fixed ${FRANCHISE_FIXED_PRICE}, got ${e['expected_income']} for {e['event_type']}"
        
        # Total should be 3 × $150 = $450
        test_total = sum(e['expected_income'] for e in test_events)
        expected_total = 3 * FRANCHISE_FIXED_PRICE
        
        assert test_total == expected_total, \
            f"Franchise total should be ${expected_total}, got ${test_total}"
        
        print(f"✓ Franchise venue uses fixed ${FRANCHISE_FIXED_PRICE} per event (total: ${test_total})")
    
    def test_venue_without_pricing_excluded(self):
        """Test that venues without pricing are excluded from income calculation"""
        if not self.venue_without_pricing:
            pytest.skip("No venue without pricing found for testing")
        
        # Check if this venue has pricing
        pricing = self.pricing_map.get(self.venue_without_pricing['id'])
        
        # Create an event at this venue
        event = self.create_test_event(
            self.venue_without_pricing['id'], 
            'Trivia', 
            datetime(2026, 4, 27, 19, 0, 0)
        )
        
        # Get expected income
        response = requests.get(
            f"{BASE_URL}/api/reports/monthly/expected_income?month=2026-04&venue_id={self.venue_without_pricing['id']}"
        )
        assert response.status_code == 200
        data = response.json()
        
        # If venue has no pricing, event should not appear in breakdown
        test_events = [e for e in data['events'] if e['event_id'] == event['id']]
        
        if pricing is None or (pricing.get('trivia_price', 0) == 0 and 
                               pricing.get('music_bingo_price', 0) == 0 and 
                               pricing.get('karaoke_price', 0) == 0):
            assert len(test_events) == 0, \
                f"Venue without pricing should not contribute to income, but found {len(test_events)} events"
            print(f"✓ Venue without pricing correctly excluded from income calculation")
        else:
            print(f"Note: Venue has pricing set, so it's included in calculation")
    
    def test_income_breakdown_structure(self):
        """Test that the income breakdown includes all required fields"""
        # Create a test event
        event = self.create_test_event(self.whining_pig['id'], 'Trivia', datetime(2026, 4, 28, 19, 0, 0))
        
        response = requests.get(
            f"{BASE_URL}/api/reports/monthly/expected_income?month=2026-04&venue_id={self.whining_pig['id']}"
        )
        assert response.status_code == 200
        data = response.json()
        
        # Check response structure
        assert 'month' in data
        assert 'venue_id' in data
        assert 'total_expected_income' in data
        assert 'event_count' in data
        assert 'events' in data
        
        # Check event breakdown structure
        test_events = [e for e in data['events'] if e['event_id'] == event['id']]
        assert len(test_events) == 1
        
        event_data = test_events[0]
        assert 'event_id' in event_data
        assert 'event_type' in event_data
        assert 'venue_id' in event_data
        assert 'date' in event_data
        assert 'expected_income' in event_data
        assert 'venue_pays_host_directly' in event_data
        
        print(f"✓ Income breakdown structure is correct")
        print(f"  Fields: {list(event_data.keys())}")


class TestIncomeBreakdownByType:
    """Test the per-event-type breakdown in the income calculation"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test data"""
        response = requests.get(f"{BASE_URL}/api/venues")
        assert response.status_code == 200
        venues = response.json()
        
        self.whining_pig = next((v for v in venues if "Whining Pig Downtown" in v['name']), None)
        assert self.whining_pig is not None
        
        self.created_event_ids = []
        yield
        
        for event_id in self.created_event_ids:
            try:
                requests.delete(f"{BASE_URL}/api/events/{event_id}")
            except:
                pass
    
    def create_test_event(self, venue_id: str, event_type: str, date: datetime) -> dict:
        event_data = {
            "title": f"TEST_{event_type}_Breakdown",
            "event_type": event_type,
            "venue_id": venue_id,
            "date": date.isoformat(),
            "duration_hours": 2.0
        }
        response = requests.post(f"{BASE_URL}/api/events", json=event_data)
        assert response.status_code == 200
        event = response.json()
        self.created_event_ids.append(event['id'])
        return event
    
    def test_breakdown_groups_by_event_type(self):
        """Test that the breakdown can be grouped by event type for UI display"""
        # Create multiple events of different types
        events = []
        events.append(self.create_test_event(self.whining_pig['id'], 'Trivia', datetime(2026, 4, 10, 19, 0, 0)))
        events.append(self.create_test_event(self.whining_pig['id'], 'Trivia', datetime(2026, 4, 11, 19, 0, 0)))
        events.append(self.create_test_event(self.whining_pig['id'], 'Karaoke', datetime(2026, 4, 12, 19, 0, 0)))
        events.append(self.create_test_event(self.whining_pig['id'], 'Music Bingo', datetime(2026, 4, 13, 19, 0, 0)))
        
        response = requests.get(
            f"{BASE_URL}/api/reports/monthly/expected_income?month=2026-04&venue_id={self.whining_pig['id']}"
        )
        assert response.status_code == 200
        data = response.json()
        
        # Group by event type (simulating what frontend does)
        test_event_ids = [e['id'] for e in events]
        test_events = [e for e in data['events'] if e['event_id'] in test_event_ids]
        
        by_type = {}
        for e in test_events:
            event_type = e['event_type']
            if event_type not in by_type:
                by_type[event_type] = {'count': 0, 'total': 0, 'per_event': e['expected_income']}
            by_type[event_type]['count'] += 1
            by_type[event_type]['total'] += e['expected_income']
        
        print(f"\n=== BREAKDOWN BY EVENT TYPE ===")
        for event_type, data in by_type.items():
            print(f"  {data['count']}x {event_type} @ ${data['per_event']}/event = ${data['total']}")
        
        # Verify counts
        assert by_type.get('Trivia', {}).get('count', 0) == 2, "Should have 2 Trivia events"
        assert by_type.get('Karaoke', {}).get('count', 0) == 1, "Should have 1 Karaoke event"
        assert by_type.get('Music Bingo', {}).get('count', 0) == 1, "Should have 1 Music Bingo event"
        
        # Verify totals
        assert by_type.get('Trivia', {}).get('total', 0) == 200.0, "Trivia total should be $200"
        assert by_type.get('Karaoke', {}).get('total', 0) == 160.0, "Karaoke total should be $160"
        assert by_type.get('Music Bingo', {}).get('total', 0) == 120.0, "Music Bingo total should be $120"
        
        # Verify grand total
        grand_total = sum(d['total'] for d in by_type.values())
        assert grand_total == 480.0, f"Grand total should be $480, got ${grand_total}"
        
        print(f"✓ Breakdown totals correct: ${grand_total}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
