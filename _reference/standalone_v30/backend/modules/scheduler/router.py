from fastapi import APIRouter, HTTPException
from core.database import get_db_conn
from typing import List, Optional
import uuid
from datetime import datetime, timezone

router = APIRouter(prefix="/api/scheduler", tags=["scheduler"])

@router.get("/events")
async def get_events():
    conn = get_db_conn()
    events = conn.execute('SELECT e.*, v.name as venue_name FROM events e LEFT JOIN venues v ON e.venue_id = v.id').fetchall()
    conn.close()
    return [dict(row) for row in events]

@router.get("/venues")
async def get_venues():
    conn = get_db_conn()
    venues = conn.execute('SELECT * FROM venues').fetchall()
    conn.close()
    return [dict(row) for row in venues]

@router.post("/events/create")
async def create_event(data: dict):
    conn = get_db_conn()
    event_id = str(uuid.uuid4())
    conn.execute('''INSERT INTO events 
        (id, title, event_type, venue_id, date, duration_hours, status) 
        VALUES (?, ?, ?, ?, ?, ?, ?)''',
        (event_id, data['title'], data['event_type'], data['venue_id'], data['date'], data.get('duration_hours', 2.0), 'available'))
    conn.commit()
    conn.close()
    return {"id": event_id, "status": "created"}

@router.post("/venues/create")
async def create_venue(data: dict):
    conn = get_db_conn()
    venue_id = str(uuid.uuid4())
    conn.execute('''INSERT INTO venues 
        (id, name, address, city, state, venue_pays_host_directly, created_at) 
        VALUES (?, ?, ?, ?, ?, ?, ?)''',
        (venue_id, data['name'], data['address'], data['city'], data.get('state', 'AZ'), 0, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    return {"id": venue_id, "status": "created"}

@router.get("/hosts")
async def get_hosts():
    conn = get_db_conn()
    hosts = conn.execute('SELECT id, name, email, is_admin FROM employees').fetchall()
    conn.close()
    return [dict(row) for row in hosts]
