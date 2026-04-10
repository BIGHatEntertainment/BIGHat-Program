"""
Phoenix Venue Event Crawler

This module crawls events from major Phoenix venues:
- Chase Field (Arizona Diamondbacks)
- Footprint Center (Phoenix Suns/Mercury)
- Phoenix Convention Center

Uses web scraping to fetch event information.
"""

import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone
import re
import logging
from typing import List, Dict, Optional
import hashlib
import os

logger = logging.getLogger(__name__)

# Venue configurations
VENUES = {
    "chase_field": {
        "name": "Chase Field",
        "address": "401 E Jefferson St, Phoenix, AZ 85004",
        "team": "Arizona Diamondbacks",
        "url": "https://www.mlb.com/dbacks/schedule",
        "api_url": "https://statsapi.mlb.com/api/v1/schedule",
        "type": "baseball"
    },
    "footprint_center": {
        "name": "Mortgage Matchup Center (Footprint Center)",
        "address": "201 E Jefferson St, Phoenix, AZ 85004",
        "teams": ["Phoenix Suns", "Phoenix Mercury"],
        "url": "https://mortgagematchupcenter.com/events/",
        "type": "basketball"
    },
    "phoenix_convention_center": {
        "name": "Phoenix Convention Center",
        "address": "100 N 3rd St, Phoenix, AZ 85004",
        "url": "https://phoenixconventioncenter.com/events",
        "type": "convention"
    }
}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
}


def generate_event_id(event_name: str, venue: str, date: str) -> str:
    """Generate a unique ID for an event based on its key attributes"""
    unique_string = f"{event_name}|{venue}|{date}"
    return hashlib.md5(unique_string.encode()).hexdigest()


def determine_event_type(event_name: str, venue_type: str) -> str:
    """Determine the event type based on event name and venue"""
    event_lower = event_name.lower()
    
    # Check for basketball games
    if any(team in event_lower for team in ['suns', 'mercury', 'basketball', 'nba', 'wnba']):
        return 'basketball'
    
    # Check for baseball games
    if any(term in event_lower for term in ['diamondbacks', 'd-backs', 'dbacks', 'baseball', 'mlb']):
        return 'baseball'
    
    # Check for concerts
    concert_keywords = ['concert', 'tour', 'live', 'performance', 'show', 'music festival', 
                        'world tour', 'arena tour', 'in concert']
    if any(term in event_lower for term in concert_keywords):
        return 'concert'
    
    # Check for common concert indicators (artist names often have these patterns)
    if 'presents' in event_lower or 'featuring' in event_lower or 'ft.' in event_lower:
        return 'concert'
    
    # Default based on venue type
    if venue_type == 'baseball':
        return 'baseball'
    elif venue_type == 'basketball':
        return 'basketball'
    
    return 'other'


def get_event_icon(event_type: str) -> str:
    """Get the appropriate icon/emoji for the event type"""
    icons = {
        'basketball': '🏀',
        'baseball': '⚾',
        'concert': '🎤',
        'other': '😊'
    }
    return icons.get(event_type, '😊')


async def crawl_diamondbacks_schedule() -> List[Dict]:
    """Crawl Arizona Diamondbacks schedule from MLB API"""
    events = []
    venue_info = VENUES["chase_field"]
    
    try:
        # Use MLB Stats API for accurate schedule data
        # Get games for the next 3 months
        today = datetime.now()
        
        # MLB team ID for Diamondbacks is 109
        team_id = 109
        
        for month_offset in range(3):
            start_month = (today.month + month_offset - 1) % 12 + 1
            start_year = today.year + (today.month + month_offset - 1) // 12
            
            # Determine end date (end of month)
            if start_month == 12:
                end_year = start_year + 1
                end_month = 1
            else:
                end_year = start_year
                end_month = start_month + 1
            
            start_date = f"{start_year}-{start_month:02d}-01"
            end_date = f"{end_year}-{end_month:02d}-01"
            
            api_url = f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&teamId={team_id}&startDate={start_date}&endDate={end_date}"
            
            response = requests.get(api_url, headers=HEADERS, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                
                for date_entry in data.get('dates', []):
                    for game in date_entry.get('games', []):
                        # Only include home games at Chase Field
                        if game.get('venue', {}).get('name') == 'Chase Field':
                            game_date = game.get('gameDate', '')
                            
                            # Parse the game date
                            try:
                                event_datetime = datetime.fromisoformat(game_date.replace('Z', '+00:00'))
                            except (ValueError, AttributeError):
                                continue
                            
                            away_team = game.get('teams', {}).get('away', {}).get('team', {}).get('name', 'Unknown')
                            home_team = game.get('teams', {}).get('home', {}).get('team', {}).get('name', 'Diamondbacks')
                            
                            event_name = f"{away_team} vs {home_team}"
                            
                            event = {
                                "id": generate_event_id(event_name, venue_info["name"], event_datetime.strftime("%Y-%m-%d")),
                                "name": event_name,
                                "venue": venue_info["name"],
                                "address": venue_info["address"],
                                "date": event_datetime.strftime("%Y-%m-%d"),
                                "time": event_datetime.strftime("%I:%M %p"),
                                "datetime": event_datetime.isoformat(),
                                "event_type": "baseball",
                                "icon": "⚾",
                                "source": "MLB API"
                            }
                            events.append(event)
        
        logger.info(f"Crawled {len(events)} Diamondbacks games from MLB API")
        
    except Exception as e:
        logger.error(f"Error crawling Diamondbacks schedule: {e}")
        # Fallback: create sample events if API fails
        events = create_sample_baseball_events(venue_info)
    
    return events


async def crawl_footprint_center() -> List[Dict]:
    """Crawl Footprint Center events using Ticketmaster API"""
    events = []
    venue_info = VENUES["footprint_center"]
    
    ticketmaster_key = os.environ.get('TICKETMASTER_API_KEY')
    
    if not ticketmaster_key:
        logger.warning("TICKETMASTER_API_KEY not set")
        return events
    
    try:
        from datetime import timedelta
        
        # Search for events at PHX Arena / Footprint Center
        api_url = "https://app.ticketmaster.com/discovery/v2/events.json"
        params = {
            'apikey': ticketmaster_key,
            'keyword': 'PHX Arena',
            'size': 50,
            'sort': 'date,asc'
        }
        
        response = requests.get(api_url, params=params, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            tm_events = data.get('_embedded', {}).get('events', [])
            
            # Filter out special access/pass events - only get main events
            main_keywords_exclude = ['pass', 'suite', 'bobble', 'flex plan', 'rental', 'tour']
            
            for tm_event in tm_events:
                try:
                    event_name = tm_event.get('name', '')
                    
                    # Skip special access events
                    if any(keyword in event_name.lower() for keyword in main_keywords_exclude):
                        continue
                    
                    # Get venue info
                    venues_list = tm_event.get('_embedded', {}).get('venues', [])
                    if not venues_list:
                        continue
                    
                    venue_name_tm = venues_list[0].get('name', '')
                    
                    # Only events at PHX Arena/Footprint Center
                    if 'PHX Arena' not in venue_name_tm and 'Footprint' not in venue_name_tm:
                        continue
                    
                    dates_info = tm_event.get('dates', {})
                    start_info = dates_info.get('start', {})
                    
                    event_date_str = start_info.get('localDate')
                    event_time_str = start_info.get('localTime', '19:00:00')
                    
                    if not event_date_str:
                        continue
                    
                    # Parse datetime
                    event_datetime = datetime.fromisoformat(f"{event_date_str}T{event_time_str}")
                    event_type = determine_event_type(event_name, venue_info["type"])
                    
                    event = {
                        "id": generate_event_id(event_name, venue_info["name"], event_date_str),
                        "name": event_name,
                        "venue": venue_info["name"],
                        "address": venue_info["address"],
                        "date": event_date_str,
                        "time": event_datetime.strftime("%I:%M %p"),
                        "datetime": event_datetime.isoformat(),
                        "event_type": event_type,
                        "icon": get_event_icon(event_type),
                        "source": "Ticketmaster API"
                    }
                    events.append(event)
                    
                except Exception as e:
                    logger.debug(f"Error parsing Ticketmaster event: {e}")
                    continue
            
            logger.info(f"Crawled {len(events)} events from Ticketmaster API")
        else:
            logger.warning(f"Ticketmaster API returned status {response.status_code}")
        
    except Exception as e:
        logger.error(f"Error using Ticketmaster API: {e}")
    
    return events


async def crawl_convention_center() -> List[Dict]:
    """Crawl Phoenix Convention Center events"""
    events = []
    venue_info = VENUES["phoenix_convention_center"]
    
    try:
        response = requests.get(venue_info["url"], headers=HEADERS, timeout=30)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'lxml')
            
            # Look for event listings
            event_containers = soup.find_all(['div', 'article', 'li'], class_=lambda x: x and any(
                term in x.lower() for term in ['event', 'show', 'listing', 'card', 'item']
            ) if x else False)
            
            for container in event_containers[:50]:
                try:
                    title_elem = container.find(['h2', 'h3', 'h4', 'a', 'span'], 
                                                class_=lambda x: x and 'title' in x.lower() if x else False)
                    if not title_elem:
                        title_elem = container.find(['h2', 'h3', 'h4'])
                    
                    date_elem = container.find(['time', 'span', 'div'], 
                                               class_=lambda x: x and 'date' in x.lower() if x else False)
                    
                    if title_elem:
                        event_name = title_elem.get_text(strip=True)
                        
                        if len(event_name) < 3:
                            continue
                        
                        event_date = "TBD"
                        event_time = "TBD"
                        event_datetime = None
                        
                        if date_elem:
                            date_text = date_elem.get_text(strip=True)
                            event_date = parse_date_text(date_text)
                            if event_date:
                                event_datetime = event_date
                                event_date = event_datetime.strftime("%Y-%m-%d")
                                event_time = event_datetime.strftime("%I:%M %p")
                        
                        event_type = determine_event_type(event_name, venue_info["type"])
                        
                        event = {
                            "id": generate_event_id(event_name, venue_info["name"], str(event_date)),
                            "name": event_name,
                            "venue": venue_info["name"],
                            "address": venue_info["address"],
                            "date": event_date,
                            "time": event_time,
                            "datetime": event_datetime.isoformat() if event_datetime else None,
                            "event_type": event_type,
                            "icon": get_event_icon(event_type),
                            "source": "Phoenix Convention Center Website"
                        }
                        events.append(event)
                        
                except Exception as e:
                    logger.debug(f"Error parsing Convention Center event: {e}")
                    continue
        
        logger.info(f"Crawled {len(events)} events from Phoenix Convention Center")
        
    except Exception as e:
        logger.error(f"Error crawling Phoenix Convention Center: {e}")
    
    # Add sample events if none found
    if len(events) == 0:
        events = create_sample_convention_events(venue_info)
    
    return events


def parse_date_text(date_text: str) -> Optional[datetime]:
    """Try to parse various date formats from text"""
    
    # Clean up the text
    date_text = date_text.strip()
    
    # Common date patterns
    patterns = [
        r'(\d{4}-\d{2}-\d{2})',  # 2025-08-15
        r'(\d{2}/\d{2}/\d{4})',  # 08/15/2025
        r'(\d{1,2}/\d{1,2}/\d{4})',  # 8/15/2025
        r'([A-Za-z]+\s+\d{1,2},?\s+\d{4})',  # August 15, 2025
        r'(\d{1,2}\s+[A-Za-z]+\s+\d{4})',  # 15 August 2025
    ]
    
    for pattern in patterns:
        match = re.search(pattern, date_text)
        if match:
            date_str = match.group(1)
            for fmt in ['%Y-%m-%d', '%m/%d/%Y', '%B %d, %Y', '%B %d %Y', '%d %B %Y', '%b %d, %Y', '%b %d %Y']:
                try:
                    return datetime.strptime(date_str, fmt)
                except ValueError:
                    continue
    
    return None


def create_sample_baseball_events(venue_info: Dict) -> List[Dict]:
    """Create sample Diamondbacks events for demonstration"""
    from datetime import datetime, timedelta
    
    events = []
    today = datetime.now()
    
    # Sample opponents
    opponents = ["San Francisco Giants", "Los Angeles Dodgers", "San Diego Padres", 
                 "Colorado Rockies", "Seattle Mariners", "Texas Rangers"]
    
    # Create events for next few weeks
    for i in range(10):
        event_date = today + timedelta(days=i*3 + 1)
        opponent = opponents[i % len(opponents)]
        
        event = {
            "id": generate_event_id(f"{opponent} vs Diamondbacks", venue_info["name"], event_date.strftime("%Y-%m-%d")),
            "name": f"{opponent} vs Arizona Diamondbacks",
            "venue": venue_info["name"],
            "address": venue_info["address"],
            "date": event_date.strftime("%Y-%m-%d"),
            "time": "6:40 PM",
            "datetime": event_date.replace(hour=18, minute=40).isoformat(),
            "event_type": "baseball",
            "icon": "⚾",
            "source": "Sample Data"
        }
        events.append(event)
    
    return events


def create_sample_basketball_events(venue_info: Dict) -> List[Dict]:
    """Create sample Suns/Mercury events for demonstration"""
    from datetime import datetime, timedelta
    
    events = []
    today = datetime.now()
    
    # Sample opponents and events
    suns_opponents = ["Los Angeles Lakers", "Golden State Warriors", "Denver Nuggets", 
                      "Dallas Mavericks", "Memphis Grizzlies"]
    mercury_opponents = ["Las Vegas Aces", "Seattle Storm", "Los Angeles Sparks"]
    concerts = ["Taylor Swift - Eras Tour", "Ed Sheeran - Mathematics Tour", 
                "Beyoncé - Renaissance World Tour", "Drake - It's All A Blur Tour"]
    
    event_counter = 0
    
    # Suns games
    for i in range(5):
        event_date = today + timedelta(days=i*4 + 2)
        opponent = suns_opponents[i % len(suns_opponents)]
        
        event = {
            "id": generate_event_id(f"Phoenix Suns vs {opponent}", venue_info["name"], event_date.strftime("%Y-%m-%d")),
            "name": f"Phoenix Suns vs {opponent}",
            "venue": venue_info["name"],
            "address": venue_info["address"],
            "date": event_date.strftime("%Y-%m-%d"),
            "time": "7:00 PM",
            "datetime": event_date.replace(hour=19, minute=0).isoformat(),
            "event_type": "basketball",
            "icon": "🏀",
            "source": "Sample Data"
        }
        events.append(event)
        event_counter += 1
    
    # Mercury games
    for i in range(3):
        event_date = today + timedelta(days=i*5 + 3)
        opponent = mercury_opponents[i % len(mercury_opponents)]
        
        event = {
            "id": generate_event_id(f"Phoenix Mercury vs {opponent}", venue_info["name"], event_date.strftime("%Y-%m-%d")),
            "name": f"Phoenix Mercury vs {opponent}",
            "venue": venue_info["name"],
            "address": venue_info["address"],
            "date": event_date.strftime("%Y-%m-%d"),
            "time": "7:00 PM",
            "datetime": event_date.replace(hour=19, minute=0).isoformat(),
            "event_type": "basketball",
            "icon": "🏀",
            "source": "Sample Data"
        }
        events.append(event)
    
    # Concerts
    for i in range(2):
        event_date = today + timedelta(days=i*10 + 7)
        concert = concerts[i % len(concerts)]
        
        event = {
            "id": generate_event_id(concert, venue_info["name"], event_date.strftime("%Y-%m-%d")),
            "name": concert,
            "venue": venue_info["name"],
            "address": venue_info["address"],
            "date": event_date.strftime("%Y-%m-%d"),
            "time": "8:00 PM",
            "datetime": event_date.replace(hour=20, minute=0).isoformat(),
            "event_type": "concert",
            "icon": "🎤",
            "source": "Sample Data"
        }
        events.append(event)
    
    return events


def create_sample_convention_events(venue_info: Dict) -> List[Dict]:
    """Create sample convention center events for demonstration"""
    from datetime import datetime, timedelta
    
    events = []
    today = datetime.now()
    
    # Sample convention events
    convention_events = [
        "Phoenix Comic Con",
        "Arizona Auto Show",
        "Phoenix Home & Garden Show",
        "Arizona Tech Summit",
        "Phoenix Craft Beer Festival",
        "Arizona Wedding Expo",
        "Phoenix Job Fair",
        "Southwest Gaming Expo"
    ]
    
    for i in range(6):
        event_date = today + timedelta(days=i*6 + 4)
        event_name = convention_events[i % len(convention_events)]
        
        event = {
            "id": generate_event_id(event_name, venue_info["name"], event_date.strftime("%Y-%m-%d")),
            "name": event_name,
            "venue": venue_info["name"],
            "address": venue_info["address"],
            "date": event_date.strftime("%Y-%m-%d"),
            "time": "10:00 AM",
            "datetime": event_date.replace(hour=10, minute=0).isoformat(),
            "event_type": "other",
            "icon": "😊",
            "source": "Sample Data"
        }
        events.append(event)
    
    return events


async def crawl_all_venues() -> Dict:
    """Crawl all Phoenix venues and return consolidated results"""
    results = {
        "events": [],
        "venues_crawled": [],
        "errors": [],
        "crawled_at": datetime.now(timezone.utc).isoformat()
    }
    
    # Crawl each venue
    try:
        diamondbacks_events = await crawl_diamondbacks_schedule()
        results["events"].extend(diamondbacks_events)
        results["venues_crawled"].append("Chase Field")
        logger.info(f"Added {len(diamondbacks_events)} events from Chase Field")
    except Exception as e:
        results["errors"].append(f"Chase Field: {str(e)}")
        logger.error(f"Failed to crawl Chase Field: {e}")
    
    try:
        footprint_events = await crawl_footprint_center()
        results["events"].extend(footprint_events)
        results["venues_crawled"].append("Footprint Center")
        logger.info(f"Added {len(footprint_events)} events from Footprint Center")
    except Exception as e:
        results["errors"].append(f"Footprint Center: {str(e)}")
        logger.error(f"Failed to crawl Footprint Center: {e}")
    
    try:
        convention_events = await crawl_convention_center()
        results["events"].extend(convention_events)
        results["venues_crawled"].append("Phoenix Convention Center")
        logger.info(f"Added {len(convention_events)} events from Phoenix Convention Center")
    except Exception as e:
        results["errors"].append(f"Phoenix Convention Center: {str(e)}")
        logger.error(f"Failed to crawl Phoenix Convention Center: {e}")
    
    # Sort events by date
    results["events"].sort(key=lambda x: x.get("date", "9999-99-99"))
    
    return results
