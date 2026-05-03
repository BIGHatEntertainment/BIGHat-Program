from fastapi import FastAPI, APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional
import uuid
from datetime import datetime, timezone, timedelta
from contextlib import asynccontextmanager

# Configure logging FIRST
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("server")

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Scheduler reference
scheduler = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    global scheduler
    try:
        from scheduler import start_scheduler
        scheduler = start_scheduler()
        logger.info("Scheduler initialized successfully")
    except Exception as e:
        logger.error(f"Failed to start scheduler: {e}")
    
    # Run data migration for existing payment records without venue_id
    try:
        await migrate_payment_records()
    except Exception as e:
        logger.error(f"Failed to migrate payment records: {e}")
    
    yield
    
    # Shutdown
    if scheduler:
        scheduler.shutdown()
        logger.info("Scheduler shut down")


async def migrate_payment_records():
    """Add venue_id and employee_email to existing payment records that don't have them"""
    # Get all employees for lookup
    all_employees = await db.employees.find({}, {"_id": 0}).to_list(1000)
    employee_id_to_email = {e['id']: e.get('email', '') for e in all_employees}
    
    # Get all venues for lookup by name
    venues = await db.venues.find({}, {"_id": 0}).to_list(100)
    venue_name_to_id = {v['name']: v['id'] for v in venues}
    
    # Find all payment acknowledgments that need migration
    payments_to_migrate = await db.payment_acknowledgments.find({
        "$or": [
            {"venue_id": {"$exists": False}},
            {"employee_email": {"$exists": False}}
        ]
    }).to_list(1000)
    
    if not payments_to_migrate:
        logger.info("No payment records to migrate")
        return
    
    logger.info(f"Migrating {len(payments_to_migrate)} payment records...")
    
    for payment in payments_to_migrate:
        update_fields = {}
        
        # Add venue_id if missing
        if 'venue_id' not in payment:
            venue_name = payment.get('venue_name', '')
            venue_id = venue_name_to_id.get(venue_name)
            if venue_id:
                update_fields['venue_id'] = venue_id
            else:
                # Try to find venue_id from the event
                event = await db.events.find_one({"id": payment.get('event_id')})
                if event and event.get('venue_id'):
                    update_fields['venue_id'] = event['venue_id']
        
        # Add employee_email if missing
        if 'employee_email' not in payment:
            employee_id = payment.get('employee_id')
            if employee_id and employee_id in employee_id_to_email:
                update_fields['employee_email'] = employee_id_to_email[employee_id]
        
        if update_fields:
            await db.payment_acknowledgments.update_one(
                {"_id": payment["_id"]},
                {"$set": update_fields}
            )
            logger.info(f"Migrated payment {payment.get('event_title')}: {list(update_fields.keys())}")
    
    logger.info("Payment record migration complete")

# Create the main app without a prefix
app = FastAPI(lifespan=lifespan)

# Custom CORS middleware that handles all cases properly
class CustomCORSMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        origin = request.headers.get("origin", "*")
        
        # Handle preflight OPTIONS requests
        if request.method == "OPTIONS":
            response = JSONResponse(content={}, status_code=200)
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS, PATCH"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Session-ID, X-Requested-With, Accept"
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Access-Control-Max-Age"] = "600"
            return response
        
        # Process the actual request
        response = await call_next(request)
        
        # Add CORS headers to all responses
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS, PATCH"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Session-ID, X-Requested-With, Accept"
        
        return response

# Add custom CORS middleware
app.add_middleware(CustomCORSMiddleware)

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")


# Define Models
class Employee(BaseModel):
    model_config = ConfigDict(extra="ignore")
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    email: str
    phone: Optional[str] = None
    is_admin: bool = False
    password: str = "B1GHat"  # Default password for all hosts
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class EmployeeCreate(BaseModel):
    name: str
    email: str
    phone: Optional[str] = None
    is_admin: bool = False
    password: Optional[str] = "B1GHat"  # Default password

class Venue(BaseModel):
    model_config = ConfigDict(extra="ignore")
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    address: str
    city: str = "Phoenix"
    state: str = "AZ"
    notes: Optional[str] = None
    venue_pays_host_directly: bool = False  # For franchise locations like Monkey Pants
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class VenueCreate(BaseModel):
    name: str
    address: str
    city: str = "Phoenix"
    state: str = "AZ"
    notes: Optional[str] = None
    venue_pays_host_directly: bool = False

class Event(BaseModel):
    model_config = ConfigDict(extra="ignore")
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    event_type: str  # Trivia, Karaoke, Music Bingo, Special
    venue_id: str
    date: datetime
    duration_hours: float = 2.0
    pay_rate: Optional[float] = None
    notes: Optional[str] = None
    claimed_by: Optional[str] = None  # employee_id
    claimed_at: Optional[datetime] = None
    status: str = "available"  # available, claimed, completed
    # Payment bonuses for Trivia events
    wore_big_hat: bool = False
    social_media_posts: bool = False
    winners_post: bool = False
    is_special_event: bool = False  # Yellow star indicator for giveaways/promotions
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class EventCreate(BaseModel):
    title: str
    event_type: str
    venue_id: str
    date: datetime
    duration_hours: float = 2.0
    pay_rate: Optional[float] = None
    notes: Optional[str] = None

class EventUpdate(BaseModel):
    title: Optional[str] = None
    event_type: Optional[str] = None
    venue_id: Optional[str] = None
    date: Optional[datetime] = None
    duration_hours: Optional[float] = None
    pay_rate: Optional[float] = None
    notes: Optional[str] = None
    status: Optional[str] = None
    wore_big_hat: Optional[bool] = None
    social_media_posts: Optional[bool] = None
    winners_post: Optional[bool] = None
    is_special_event: Optional[bool] = None

class ClaimEvent(BaseModel):
    employee_id: str

class AdminAuth(BaseModel):
    passcode: str

class HostLogin(BaseModel):
    name: str
    password: str

class PasswordChange(BaseModel):
    employee_id: str
    current_password: str
    new_password: str

class PasswordVerify(BaseModel):
    employee_id: str
    password: str

class PasswordReset(BaseModel):
    new_password: str

class PaymentReport(BaseModel):
    employee_name: str
    venue_name: str
    event_type: str
    date: datetime
    duration_hours: float
    pay_rate: Optional[float]
    total_pay: Optional[float]

class PaymentAcknowledgment(BaseModel):
    model_config = ConfigDict(extra="ignore")
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event_id: str
    event_title: str
    event_type: str
    venue_name: str
    employee_id: str
    employee_name: str
    employee_email: str = ""  # Added for owner filtering (Nick Sellards exclusion)
    event_date: datetime
    base_pay: float
    bonuses: float
    bonus_details: List[str] = []
    wore_big_hat: bool = False
    social_media_posts: bool = False
    winners_post: bool = False
    total_pay: float
    venue_id: str  # Added for venue filtering
    venue_pays_host_directly: bool = False  # For franchise locations
    acknowledged_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    acknowledged_month: str  # Format: "2025-12"

class AcknowledgePayment(BaseModel):
    event_id: str
    wore_big_hat: bool = False
    social_media_posts: bool = False
    winners_post: bool = False

class VenuePricing(BaseModel):
    model_config = ConfigDict(extra="ignore")
    
    venue_id: str
    trivia_price: float = 0.0
    music_bingo_price: float = 0.0
    karaoke_price: float = 0.0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class VenuePricingCreate(BaseModel):
    venue_id: str
    trivia_price: float = 0.0
    music_bingo_price: float = 0.0
    karaoke_price: float = 0.0

class MonthlyArchive(BaseModel):
    model_config = ConfigDict(extra="ignore")
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    month: str  # Format: "2025-12"
    archived_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Income breakdown
    total_income: float = 0.0
    income_by_location: dict = {}  # {venue_id: {venue_name: str, amount: float}}
    income_by_event: List[dict] = []  # [{event_id, event_type, venue_name, amount}]
    
    # Payments breakdown
    total_outgoing: float = 0.0
    payments_by_event: List[dict] = []  # [{event_id, employee_name, venue_name, amount}]
    
    # Summary
    net_revenue: float = 0.0
    event_count: int = 0
    payment_count: int = 0


# OAuth Models
class UserSession(BaseModel):
    model_config = ConfigDict(extra="ignore")
    
    user_id: str
    session_token: str
    expires_at: datetime
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class OAuthUser(BaseModel):
    model_config = ConfigDict(extra="ignore")
    
    user_id: str
    email: str
    name: str
    picture: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# Blackout Dates Models
class BlackoutDate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    employee_id: str
    start_date: str  # Format: "2026-01-15"
    end_date: str    # Format: "2026-01-20"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class BlackoutDateCreate(BaseModel):
    employee_id: str
    start_date: str
    end_date: str


# Venue Role Models
class VenueRole(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    venue_id: str
    employee_id: str
    role_category: str  # "trivia" or "bingo_karaoke"
    role_type: str  # "primary" or "secondary"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class VenueRoleCreate(BaseModel):
    venue_id: str
    employee_id: str
    role_category: str  # "trivia" or "bingo_karaoke"
    role_type: str  # "primary" or "secondary"


# Root endpoint
@api_router.get("/")
async def root():
    return {"message": "Entertainment Scheduling API"}


# Admin Authentication
@api_router.post("/admin/verify")
async def verify_admin(auth: AdminAuth):
    """
    Verify admin access. Accepts:
    1. The universal admin passcode (121589)
    2. The personal password of any user marked as is_admin=True
    
    Note: The generic password "B1GHat" does NOT work for admin access.
    """
    # First, check if it's the universal admin passcode
    if auth.passcode == "121589":
        return {"success": True, "message": "Admin authenticated"}
    
    # Second, check if it's a personal password of an admin user
    # Find any admin employee whose password matches
    admin_employees = await db.employees.find({"is_admin": True}, {"_id": 0}).to_list(100)
    
    for admin in admin_employees:
        admin_password = admin.get('password', '')
        # Only accept non-default passwords for admin access
        # The generic "B1GHat" password should NOT grant admin access
        if admin_password and admin_password != 'B1GHat' and auth.passcode == admin_password:
            logger.info(f"Admin authenticated via personal password: {admin.get('name')}")
            return {"success": True, "message": f"Admin authenticated as {admin.get('name')}"}
    
    raise HTTPException(status_code=401, detail="Invalid passcode")

# Host Authentication
@api_router.post("/host/login")
async def host_login(login: HostLogin):
    # Find employee by name
    employee = await db.employees.find_one({"name": login.name}, {"_id": 0})
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    
    # Check password (plain text comparison)
    # Accept master password OR employee's password
    if login.password == "121589" or login.password == employee.get('password', 'B1GHat'):
        return {
            "success": True,
            "employee": {
                "id": employee['id'],
                "name": employee['name'],
                "email": employee['email'],
                "is_admin": employee.get('is_admin', False)
            }
        }
    
    raise HTTPException(status_code=401, detail="Invalid password")

@api_router.post("/host/password/change")
async def change_password(change: PasswordChange):
    employee = await db.employees.find_one({"id": change.employee_id})
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    
    # Verify current password
    current_pwd = employee.get('password', 'B1GHat')
    if change.current_password != current_pwd and change.current_password != "121589":
        raise HTTPException(status_code=401, detail="Current password is incorrect")
    
    # Update password
    await db.employees.update_one(
        {"id": change.employee_id},
        {"$set": {"password": change.new_password}}
    )
    
    return {"success": True, "message": "Password changed successfully"}

@api_router.get("/host/password/is-default/{employee_id}")
async def check_default_password(employee_id: str):
    """Check if employee is using the default password"""
    employee = await db.employees.find_one({"id": employee_id}, {"_id": 0})
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    
    # Check if password is the default
    employee_pwd = employee.get('password', 'B1GHat')
    is_default = employee_pwd == 'B1GHat'
    
    return {"is_default": is_default, "default_password": "B1GHat" if is_default else None}

@api_router.post("/host/password/verify")
async def verify_password(verify: PasswordVerify):
    employee = await db.employees.find_one({"id": verify.employee_id})
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    
    # Check password - accept master password OR employee's password
    employee_pwd = employee.get('password', 'B1GHat')
    if verify.password == "121589" or verify.password == employee_pwd:
        return {"success": True}
    
    raise HTTPException(status_code=401, detail="Invalid password")

@api_router.post("/employees/{employee_id}/password/reset")
async def reset_employee_password(employee_id: str, reset: PasswordReset):
    employee = await db.employees.find_one({"id": employee_id})
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    
    # Update password
    await db.employees.update_one(
        {"id": employee_id},
        {"$set": {"password": reset.new_password}}
    )
    
    return {"success": True, "message": "Password reset successfully"}


# Employee endpoints
@api_router.post("/employees", response_model=Employee)
async def create_employee(employee: EmployeeCreate):
    employee_obj = Employee(**employee.model_dump())
    doc = employee_obj.model_dump()
    doc['created_at'] = doc['created_at'].isoformat()
    await db.employees.insert_one(doc)
    return employee_obj

@api_router.get("/employees", response_model=List[Employee])
async def get_employees():
    employees = await db.employees.find({}, {"_id": 0}).to_list(1000)
    for emp in employees:
        if isinstance(emp['created_at'], str):
            emp['created_at'] = datetime.fromisoformat(emp['created_at'])
    return employees

@api_router.get("/employees/{employee_id}", response_model=Employee)
async def get_employee(employee_id: str):
    employee = await db.employees.find_one({"id": employee_id}, {"_id": 0})
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    if isinstance(employee['created_at'], str):
        employee['created_at'] = datetime.fromisoformat(employee['created_at'])
    return employee

@api_router.put("/employees/{employee_id}", response_model=Employee)
async def update_employee(employee_id: str, employee: EmployeeCreate):
    existing = await db.employees.find_one({"id": employee_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Employee not found")
    
    update_data = employee.model_dump()
    await db.employees.update_one({"id": employee_id}, {"$set": update_data})
    
    updated = await db.employees.find_one({"id": employee_id}, {"_id": 0})
    if isinstance(updated['created_at'], str):
        updated['created_at'] = datetime.fromisoformat(updated['created_at'])
    return updated

@api_router.delete("/employees/{employee_id}")
async def delete_employee(employee_id: str):
    result = await db.employees.delete_one({"id": employee_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Employee not found")
    return {"success": True, "message": "Employee deleted"}


# Venue endpoints
@api_router.post("/venues", response_model=Venue)
async def create_venue(venue: VenueCreate):
    venue_obj = Venue(**venue.model_dump())
    doc = venue_obj.model_dump()
    doc['created_at'] = doc['created_at'].isoformat()
    await db.venues.insert_one(doc)
    return venue_obj

@api_router.get("/venues", response_model=List[Venue])
async def get_venues():
    venues = await db.venues.find({}, {"_id": 0}).to_list(1000)
    for venue in venues:
        if isinstance(venue['created_at'], str):
            venue['created_at'] = datetime.fromisoformat(venue['created_at'])
    return venues

@api_router.get("/venues/{venue_id}", response_model=Venue)
async def get_venue(venue_id: str):
    venue = await db.venues.find_one({"id": venue_id}, {"_id": 0})
    if not venue:
        raise HTTPException(status_code=404, detail="Venue not found")
    if isinstance(venue['created_at'], str):
        venue['created_at'] = datetime.fromisoformat(venue['created_at'])
    return venue

@api_router.put("/venues/{venue_id}", response_model=Venue)
async def update_venue(venue_id: str, venue: VenueCreate):
    existing = await db.venues.find_one({"id": venue_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Venue not found")
    
    update_data = venue.model_dump()
    await db.venues.update_one({"id": venue_id}, {"$set": update_data})
    
    updated = await db.venues.find_one({"id": venue_id}, {"_id": 0})
    if isinstance(updated['created_at'], str):
        updated['created_at'] = datetime.fromisoformat(updated['created_at'])
    return updated

@api_router.delete("/venues/{venue_id}")
async def delete_venue(venue_id: str):
    result = await db.venues.delete_one({"id": venue_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Venue not found")
    return {"success": True, "message": "Venue deleted"}


# Event endpoints
@api_router.post("/events", response_model=Event)
async def create_event(event: EventCreate):
    # Verify venue exists
    venue = await db.venues.find_one({"id": event.venue_id})
    if not venue:
        raise HTTPException(status_code=404, detail="Venue not found")
    
    event_obj = Event(**event.model_dump())
    doc = event_obj.model_dump()
    doc['date'] = doc['date'].isoformat()
    doc['created_at'] = doc['created_at'].isoformat()
    if doc['claimed_at']:
        doc['claimed_at'] = doc['claimed_at'].isoformat()
    await db.events.insert_one(doc)
    return event_obj

@api_router.get("/events", response_model=List[Event])
async def get_events(include_past: bool = False):
    query = {}
    if not include_past:
        # Only show future events + events from the last 10 days (non-archived)
        cutoff = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        query['date'] = {'$gte': cutoff}
    # Always exclude archived events unless explicitly including past
    if not include_past:
        query['archived'] = {'$ne': True}
    
    events = await db.events.find(query, {"_id": 0}).sort("date", 1).to_list(1000)
    for event in events:
        if isinstance(event['date'], str):
            event['date'] = datetime.fromisoformat(event['date'])
        if isinstance(event['created_at'], str):
            event['created_at'] = datetime.fromisoformat(event['created_at'])
        if event.get('claimed_at') and isinstance(event['claimed_at'], str):
            event['claimed_at'] = datetime.fromisoformat(event['claimed_at'])
    return events


@api_router.get("/events/claim-eligibility")
async def get_claim_eligibility():
    """Batch endpoint: return claim status for all unclaimed future events."""
    now_iso = datetime.now(timezone.utc).isoformat()
    elig_events = await db.events.find({
        "date": {"$gte": now_iso},
        "claimed_by": None
    }, {"_id": 0}).to_list(2000)

    # Pre-load all venue roles and blackouts for efficiency
    all_roles = await db.venue_roles.find({"role_type": "primary"}, {"_id": 0}).to_list(500)
    all_blackouts = await db.blackout_dates.find({}, {"_id": 0}).to_list(1000)

    today = datetime.now(timezone.utc).date()
    result = {}

    for event in elig_events:
        role_category = _map_event_type_to_category(event.get('event_type', ''))
        if not role_category:
            result[event['id']] = {"status": "open"}
            continue

        primary_role = next(
            (r for r in all_roles
             if r['venue_id'] == event['venue_id'] and r['role_category'] == role_category),
            None
        )
        if not primary_role:
            result[event['id']] = {"status": "open"}
            continue

        primary_id = primary_role['employee_id']

        ed = event['date']
        if isinstance(ed, str):
            event_date = datetime.fromisoformat(ed)
        else:
            event_date = ed
        if event_date.tzinfo is None:
            event_date = event_date.replace(tzinfo=timezone.utc)
        event_date_str = event_date.strftime('%Y-%m-%d')

        has_blackout = any(
            b['employee_id'] == primary_id
            and b['start_date'] <= event_date_str <= b['end_date']
            for b in all_blackouts
        )
        if has_blackout:
            result[event['id']] = {"status": "open"}
            continue

        event_date_only = event_date.date()
        weekday = event_date_only.weekday()
        days_back = (weekday + 1) % 7
        if days_back == 0:
            days_back = 7
        prior_sunday = event_date_only - timedelta(days=days_back)

        if today > prior_sunday:
            result[event['id']] = {"status": "open"}
        else:
            opens_at = (prior_sunday + timedelta(days=1)).isoformat()
            result[event['id']] = {
                "status": "primary_only",
                "primary_employee_id": primary_id,
                "opens_at": opens_at
            }

    return result


@api_router.get("/events/{event_id}", response_model=Event)
async def get_event(event_id: str):
    event = await db.events.find_one({"id": event_id}, {"_id": 0})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    if isinstance(event['date'], str):
        event['date'] = datetime.fromisoformat(event['date'])
    if isinstance(event['created_at'], str):
        event['created_at'] = datetime.fromisoformat(event['created_at'])
    if event.get('claimed_at') and isinstance(event['claimed_at'], str):
        event['claimed_at'] = datetime.fromisoformat(event['claimed_at'])
    return event

@api_router.put("/events/{event_id}", response_model=Event)
async def update_event(event_id: str, event: EventUpdate):
    existing = await db.events.find_one({"id": event_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Event not found")
    
    update_data = event.model_dump(exclude_unset=True)
    if 'date' in update_data and update_data['date']:
        update_data['date'] = update_data['date'].isoformat()
    
    await db.events.update_one({"id": event_id}, {"$set": update_data})
    
    updated = await db.events.find_one({"id": event_id}, {"_id": 0})
    if isinstance(updated['date'], str):
        updated['date'] = datetime.fromisoformat(updated['date'])
    if isinstance(updated['created_at'], str):
        updated['created_at'] = datetime.fromisoformat(updated['created_at'])
    if updated.get('claimed_at') and isinstance(updated['claimed_at'], str):
        updated['claimed_at'] = datetime.fromisoformat(updated['claimed_at'])
    return updated

@api_router.delete("/events/{event_id}")
async def delete_event(event_id: str):
    result = await db.events.delete_one({"id": event_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Event not found")
    return {"success": True, "message": "Event deleted"}


# --- Claim eligibility helper ---
def _map_event_type_to_category(event_type: str) -> str:
    """Map an event type to a role category."""
    if event_type == 'Trivia':
        return 'trivia'
    if event_type in ('Music Bingo', 'Karaoke'):
        return 'bingo_karaoke'
    return ''


async def compute_event_eligibility(event: dict) -> dict:
    """
    Determine if an event is open to all or reserved for a primary.
    Rules:
    1. Primaries get early access to claim events at their venue+category.
    2. If the primary has a blackout date overlapping the event, it's open to all.
    3. If the Sunday prior to the event has passed, it's open to all.
    """
    role_category = _map_event_type_to_category(event.get('event_type', ''))
    if not role_category:
        return {"status": "open"}

    venue_id = event['venue_id']

    # Find primary for this venue+category
    primary_role = await db.venue_roles.find_one({
        "venue_id": venue_id,
        "role_category": role_category,
        "role_type": "primary"
    }, {"_id": 0})

    if not primary_role:
        return {"status": "open"}

    primary_id = primary_role['employee_id']

    # Parse event date
    event_date_raw = event['date']
    if isinstance(event_date_raw, str):
        event_date = datetime.fromisoformat(event_date_raw)
    else:
        event_date = event_date_raw
    if event_date.tzinfo is None:
        event_date = event_date.replace(tzinfo=timezone.utc)
    event_date_str = event_date.strftime('%Y-%m-%d')

    # Check if primary has blackout dates overlapping this event
    blackout_overlap = await db.blackout_dates.find_one({
        "employee_id": primary_id,
        "start_date": {"$lte": event_date_str},
        "end_date": {"$gte": event_date_str}
    })
    if blackout_overlap:
        return {"status": "open"}

    # Check if we're past the Sunday prior to the event
    event_date_only = event_date.date()
    weekday = event_date_only.weekday()  # 0=Mon, 6=Sun
    days_back = (weekday + 1) % 7
    if days_back == 0:
        days_back = 7  # Event is on Sunday → prior Sunday is 7 days back
    prior_sunday = event_date_only - timedelta(days=days_back)

    today = datetime.now(timezone.utc).date()
    if today > prior_sunday:
        return {"status": "open"}

    opens_at = (prior_sunday + timedelta(days=1)).isoformat()  # Monday after the deadline
    return {
        "status": "primary_only",
        "primary_employee_id": primary_id,
        "opens_at": opens_at
    }


@api_router.post("/events/{event_id}/claim")
async def claim_event(event_id: str, claim: ClaimEvent):
    event = await db.events.find_one({"id": event_id})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    
    if event.get('claimed_by'):
        raise HTTPException(status_code=400, detail="Event already claimed")
    
    # Verify employee exists
    employee = await db.employees.find_one({"id": claim.employee_id})
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    
    # --- Primary/Secondary claim rules ---
    eligibility = await compute_event_eligibility(event)
    if eligibility["status"] == "primary_only" and claim.employee_id != eligibility["primary_employee_id"]:
        primary_emp = await db.employees.find_one({"id": eligibility["primary_employee_id"]}, {"_id": 0, "name": 1})
        primary_name = primary_emp["name"] if primary_emp else "the primary host"
        raise HTTPException(
            status_code=403,
            detail=f"This event is currently reserved for {primary_name} (primary). It opens to all on {eligibility['opens_at']}."
        )
    
    await db.events.update_one(
        {"id": event_id},
        {
            "$set": {
                "claimed_by": claim.employee_id,
                "claimed_at": datetime.now(timezone.utc).isoformat(),
                "status": "claimed"
            }
        }
    )
    
    return {"success": True, "message": "Event claimed successfully"}

@api_router.post("/events/{event_id}/unclaim")
async def unclaim_event(event_id: str):
    event = await db.events.find_one({"id": event_id})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    
    await db.events.update_one(
        {"id": event_id},
        {
            "$set": {
                "claimed_by": None,
                "claimed_at": None,
                "status": "available",
                "wore_big_hat": False,
                "social_media_posts": False,
                "winners_post": False
            }
        }
    )
    
    return {"success": True, "message": "Event unclaimed successfully"}


class AdminAssign(BaseModel):
    employee_id: str


@api_router.post("/events/{event_id}/admin-assign")
async def admin_assign_event(event_id: str, assign: AdminAssign):
    """Admin endpoint to assign a host to an event (bypasses password verification)"""
    # Verify event exists
    event = await db.events.find_one({"id": event_id})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    
    # Verify employee exists
    employee = await db.employees.find_one({"id": assign.employee_id})
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    
    # Assign the host
    await db.events.update_one(
        {"id": event_id},
        {
            "$set": {
                "claimed_by": assign.employee_id,
                "claimed_at": datetime.now(timezone.utc).isoformat(),
                "status": "claimed"
            }
        }
    )
    
    logger.info(f"Admin assigned {employee.get('name')} to event {event.get('title')}")
    return {"success": True, "message": f"Host {employee.get('name')} assigned successfully"}

class UpdateBonuses(BaseModel):
    wore_big_hat: bool
    social_media_posts: bool
    winners_post: bool

@api_router.post("/events/{event_id}/bonuses")
async def update_event_bonuses(event_id: str, bonuses: UpdateBonuses):
    event = await db.events.find_one({"id": event_id})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    
    await db.events.update_one(
        {"id": event_id},
        {
            "$set": {
                "wore_big_hat": bonuses.wore_big_hat,
                "social_media_posts": bonuses.social_media_posts,
                "winners_post": bonuses.winners_post
            }
        }
    )
    
    return {"success": True, "message": "Bonuses updated successfully"}


# Reports endpoint
@api_router.get("/reports/weekly")
async def get_weekly_report(week_start: Optional[str] = None):
    # Get events from the past week for payment reporting
    if week_start:
        start_date = datetime.fromisoformat(week_start)
    else:
        # Get last Friday
        today = datetime.now(timezone.utc)
        days_since_friday = (today.weekday() - 4) % 7
        last_friday = today - timedelta(days=days_since_friday)
        start_date = last_friday.replace(hour=0, minute=0, second=0, microsecond=0)
    
    end_date = start_date + timedelta(days=7)
    
    # Get list of acknowledged event IDs
    acknowledged_events = await db.payment_acknowledgments.find({}, {"_id": 0, "event_id": 1}).to_list(1000)
    acknowledged_event_ids = [ack['event_id'] for ack in acknowledged_events]
    
    # Get completed events in this range, excluding acknowledged ones
    events = await db.events.find({
        "date": {
            "$gte": start_date.isoformat(),
            "$lt": end_date.isoformat()
        },
        "claimed_by": {"$ne": None},
        "id": {"$nin": acknowledged_event_ids}
    }, {"_id": 0}).to_list(1000)
    
    report_items = []
    for event in events:
        # Get employee and venue details
        employee = await db.employees.find_one({"id": event['claimed_by']}, {"_id": 0})
        venue = await db.venues.find_one({"id": event['venue_id']}, {"_id": 0})
        
        if employee and venue:
            # Check if venue pays host directly (franchise locations like Monkey Pants)
            venue_pays_directly = venue.get('venue_pays_host_directly', False)
            
            # Calculate base pay based on event type
            if venue_pays_directly:
                # Franchise venues pay hosts a fixed $150 directly
                base_pay = 150
            elif event['event_type'] == 'Trivia':
                base_pay = 60
            elif event['event_type'] == 'Music Bingo':
                base_pay = 70
            elif event['event_type'] == 'Karaoke':
                # Karaoke is hourly with no bonuses
                base_pay = 25 * event.get('duration_hours', 2)
            else:
                base_pay = event.get('pay_rate', 0) * event.get('duration_hours', 0) if event.get('pay_rate') else 0
            
            # Calculate bonuses for Trivia and Music Bingo events
            # Franchise venues don't have bonuses - they pay flat $150
            bonuses = 0
            bonus_details = []
            if not venue_pays_directly and event['event_type'] in ['Trivia', 'Music Bingo']:
                if event.get('wore_big_hat', False):
                    bonuses += 20
                    bonus_details.append('BIG Hat (+$20)')
                if event.get('social_media_posts', False):
                    bonuses += 5
                    bonus_details.append('Social Media (+$5)')
                if event.get('winners_post', False):
                    bonuses += 5
                    bonus_details.append('Winners Post (+$5)')
            
            total_pay = base_pay + bonuses
            
            report_items.append({
                "event_id": event['id'],
                "event_title": event['title'],
                "employee_id": event['claimed_by'],
                "employee_name": employee['name'],
                "venue_id": venue['id'],
                "venue_name": venue['name'],
                "event_type": event['event_type'],
                "date": event['date'],
                "duration_hours": event['duration_hours'],
                "pay_rate": event.get('pay_rate'),
                "base_pay": base_pay,
                "bonuses": bonuses,
                "bonus_details": bonus_details,
                "wore_big_hat": event.get('wore_big_hat', False),
                "social_media_posts": event.get('social_media_posts', False),
                "winners_post": event.get('winners_post', False),
                "total_pay": total_pay,
                "venue_pays_host_directly": venue_pays_directly
            })
    
    return {
        "week_start": start_date.isoformat(),
        "week_end": end_date.isoformat(),
        "events": report_items
    }

@api_router.post("/reports/payment/acknowledge")
async def acknowledge_payment(ack: AcknowledgePayment):
    # Get event details
    event = await db.events.find_one({"id": ack.event_id})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    
    # Update event with final bonus states
    await db.events.update_one(
        {"id": ack.event_id},
        {
            "$set": {
                "wore_big_hat": ack.wore_big_hat,
                "social_media_posts": ack.social_media_posts,
                "winners_post": ack.winners_post
            }
        }
    )
    
    # Get employee and venue details
    employee = await db.employees.find_one({"id": event['claimed_by']})
    venue = await db.venues.find_one({"id": event['venue_id']})
    
    if not employee or not venue:
        raise HTTPException(status_code=404, detail="Employee or venue not found")
    
    # Check if venue pays host directly (franchise locations like Monkey Pants)
    venue_pays_directly = venue.get('venue_pays_host_directly', False)
    
    # Calculate payment details
    if venue_pays_directly:
        # Franchise venues pay hosts a fixed $150 directly
        base_pay = 150
    elif event['event_type'] == 'Trivia':
        base_pay = 60
    elif event['event_type'] == 'Music Bingo':
        base_pay = 70
    elif event['event_type'] == 'Karaoke':
        base_pay = 25 * event.get('duration_hours', 2)
    else:
        base_pay = event.get('pay_rate', 0) * event.get('duration_hours', 0)
    
    # Calculate bonuses - franchise venues don't have bonuses
    bonuses = 0
    bonus_details = []
    if not venue_pays_directly and event['event_type'] in ['Trivia', 'Music Bingo']:
        if ack.wore_big_hat:
            bonuses += 20
            bonus_details.append('BIG Hat (+$20)')
        if ack.social_media_posts:
            bonuses += 5
            bonus_details.append('Social Media (+$5)')
        if ack.winners_post:
            bonuses += 5
            bonus_details.append('Winners Post (+$5)')
    
    total_pay = base_pay + bonuses
    
    # Get month for organization (e.g., "2025-12")
    event_date = datetime.fromisoformat(event['date'])
    acknowledged_month = event_date.strftime('%Y-%m')
    
    # Create acknowledgment record using the provided bonus states
    acknowledgment = PaymentAcknowledgment(
        event_id=event['id'],
        event_title=event['title'],
        event_type=event['event_type'],
        venue_id=venue['id'],  # Added venue_id for filtering
        venue_name=venue['name'],
        employee_id=employee['id'],
        employee_name=employee['name'],
        employee_email=employee.get('email', ''),  # For owner filtering
        event_date=event_date,
        base_pay=base_pay,
        bonuses=bonuses,
        bonus_details=bonus_details,
        wore_big_hat=ack.wore_big_hat,
        social_media_posts=ack.social_media_posts,
        winners_post=ack.winners_post,
        total_pay=total_pay,
        venue_pays_host_directly=venue.get('venue_pays_host_directly', False),
        acknowledged_month=acknowledged_month
    )
    
    # Save to database
    doc = acknowledgment.model_dump()
    doc['event_date'] = doc['event_date'].isoformat()
    doc['acknowledged_at'] = doc['acknowledged_at'].isoformat()
    await db.payment_acknowledgments.insert_one(doc)
    
    return {"success": True, "message": "Payment acknowledged successfully"}

@api_router.get("/reports/payment/history")
async def get_payment_history(month: Optional[str] = None):
    # Get payment history, optionally filtered by month
    query = {}
    if month:
        query['acknowledged_month'] = month
    
    acknowledgments = await db.payment_acknowledgments.find(query, {"_id": 0}).sort("acknowledged_at", -1).to_list(1000)
    
    # Convert datetime strings back to datetime objects
    for ack in acknowledgments:
        if isinstance(ack['event_date'], str):
            ack['event_date'] = datetime.fromisoformat(ack['event_date'])
        if isinstance(ack['acknowledged_at'], str):
            ack['acknowledged_at'] = datetime.fromisoformat(ack['acknowledged_at'])
    
    return acknowledgments


# Monthly Archive endpoints
@api_router.post("/reports/monthly/archive")
async def create_monthly_archive(month: str):
    """Create a monthly archive snapshot for record keeping"""
    # Check if archive already exists
    existing = await db.monthly_archives.find_one({"month": month})
    if existing:
        raise HTTPException(status_code=400, detail="Archive already exists for this month")
    
    # Get expected income data
    expected_income_res = await get_monthly_expected_income(month, None)
    
    # Get acknowledged payments for this month
    payments = await db.payment_acknowledgments.find({"acknowledged_month": month}, {"_id": 0}).to_list(1000)
    
    # Get all venues and pricing
    all_venues = await db.venues.find({}, {"_id": 0}).to_list(1000)
    venue_map = {v['id']: v for v in all_venues}
    
    # Calculate income by location
    income_by_location = {}
    for event_data in expected_income_res['events']:
        venue_id = event_data['venue_id']
        venue_name = venue_map.get(venue_id, {}).get('name', 'Unknown')
        
        if venue_id not in income_by_location:
            income_by_location[venue_id] = {
                'venue_name': venue_name,
                'amount': 0
            }
        income_by_location[venue_id]['amount'] += event_data['expected_income']
    
    # Build income by event list
    income_by_event = []
    for event_data in expected_income_res['events']:
        venue_name = venue_map.get(event_data['venue_id'], {}).get('name', 'Unknown')
        income_by_event.append({
            'event_id': event_data['event_id'],
            'event_type': event_data['event_type'],
            'venue_name': venue_name,
            'date': event_data['date'],
            'amount': event_data['expected_income']
        })
    
    # Build payments by event list and calculate total
    payments_by_event = []
    total_outgoing = 0
    for payment in payments:
        # Exclude franchise venue payments from outgoing total
        if not payment.get('venue_pays_host_directly', False):
            total_outgoing += payment['total_pay']
        
        payments_by_event.append({
            'event_id': payment['event_id'],
            'event_title': payment['event_title'],
            'employee_name': payment['employee_name'],
            'venue_name': payment['venue_name'],
            'event_date': payment['event_date'] if isinstance(payment['event_date'], str) else payment['event_date'].isoformat(),
            'amount': payment['total_pay'],
            'venue_pays_host_directly': payment.get('venue_pays_host_directly', False)
        })
    
    # Create archive document
    archive = MonthlyArchive(
        month=month,
        total_income=expected_income_res['total_expected_income'],
        income_by_location=income_by_location,
        income_by_event=income_by_event,
        total_outgoing=total_outgoing,
        payments_by_event=payments_by_event,
        net_revenue=expected_income_res['total_expected_income'] - total_outgoing,
        event_count=len(income_by_event),
        payment_count=len(payments)
    )
    
    # Save to database
    doc = archive.model_dump()
    doc['archived_at'] = doc['archived_at'].isoformat()
    await db.monthly_archives.insert_one(doc)
    
    # Upload to SharePoint Financial Records folder
    sp_upload_status = "not_attempted"
    try:
        from sharepoint_service import SharePointService
        import json as json_mod
        import base64
        import requests as sp_requests
        
        sp = SharePointService()
        token = sp.get_access_token()
        
        # Resolve the Financial Records sharing URL to get drive_id and item_id
        sharing_url = "https://bhentertainment.sharepoint.com/:f:/g/IgCNsqgWmBgXQbSpKnp-IEdWAUqZzHgub7Wwk6GhOTW2oCc?e=s12lta"
        encoded = base64.urlsafe_b64encode(sharing_url.encode()).decode().rstrip('=')
        share_token = f"u!{encoded}"
        
        resolve_resp = sp_requests.get(
            f"https://graph.microsoft.com/v1.0/shares/{share_token}/driveItem",
            headers={"Authorization": f"Bearer {token}"}, timeout=15
        )
        
        if resolve_resp.status_code == 200:
            folder_data = resolve_resp.json()
            drive_id = folder_data.get("parentReference", {}).get("driveId")
            folder_id = folder_data.get("id")
            
            # Prepare JSON — exclude _id, convert datetimes
            upload_doc = {k: v for k, v in doc.items() if k != '_id'}
            json_content = json_mod.dumps(upload_doc, indent=2, default=str).encode('utf-8')
            filename = f"{month}_Financial_Report.json"
            
            # Upload to SharePoint
            upload_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{folder_id}:/{filename}:/content"
            upload_resp = sp_requests.put(
                upload_url,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                data=json_content, timeout=30
            )
            
            if upload_resp.status_code in [200, 201]:
                sp_upload_status = "uploaded"
                logger.info(f"[Archive] Uploaded {filename} to SharePoint Financial Records")
            else:
                sp_upload_status = f"failed: {upload_resp.status_code}"
                logger.error(f"[Archive] SharePoint upload failed: {upload_resp.status_code} - {upload_resp.text[:200]}")
        else:
            sp_upload_status = f"resolve_failed: {resolve_resp.status_code}"
            logger.error(f"[Archive] Could not resolve SharePoint folder: {resolve_resp.status_code}")
    except Exception as e:
        sp_upload_status = f"error: {str(e)[:80]}"
        logger.error(f"[Archive] SharePoint upload error: {e}")
    
    return {
        "success": True,
        "message": f"Monthly archive created for {month}",
        "archive": archive,
        "sharepoint_upload": sp_upload_status
    }

@api_router.get("/reports/monthly/archive/{month}")
async def get_monthly_archive(month: str):
    """Retrieve a monthly archive"""
    archive = await db.monthly_archives.find_one({"month": month}, {"_id": 0})
    if not archive:
        raise HTTPException(status_code=404, detail="Archive not found")
    
    if isinstance(archive['archived_at'], str):
        archive['archived_at'] = datetime.fromisoformat(archive['archived_at'])
    
    return archive

@api_router.get("/reports/monthly/archives")
async def get_all_monthly_archives():
    """Retrieve all monthly archives"""
    archives = await db.monthly_archives.find({}, {"_id": 0}).sort("month", -1).to_list(1000)
    
    for archive in archives:
        if isinstance(archive['archived_at'], str):
            archive['archived_at'] = datetime.fromisoformat(archive['archived_at'])
    
    return archives


# Event Crawler endpoints
@api_router.get("/events/crawler/phoenix")
async def crawl_phoenix_events():
    """Crawl events from major Phoenix venues (concerts, sports, etc.)"""
    try:
        from event_crawler import crawl_all_venues
        
        results = await crawl_all_venues()
        
        return {
            "success": True,
            "events": results["events"],
            "venues_crawled": results["venues_crawled"],
            "errors": results["errors"],
            "crawled_at": results["crawled_at"],
            "total_events": len(results["events"])
        }
    except Exception as e:
        logger.error(f"Error crawling Phoenix events: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to crawl events: {str(e)}")


# OAuth Authentication endpoints
@api_router.post("/auth/session")
async def create_session(request: Request):
    """Process OAuth session_id and create user session"""
    logger.info("=== OAuth Session Request Started ===")
    logger.info(f"Request headers: {dict(request.headers)}")
    
    try:
        # Get session_id from header
        session_id = request.headers.get("X-Session-ID")
        logger.info(f"Session ID present: {bool(session_id)}")
        
        if not session_id:
            logger.error("Missing session_id in request headers")
            raise HTTPException(status_code=400, detail="Missing session_id")
        
        # Call Emergent OAuth API to get user data
        import httpx
        import re
        logger.info("Calling Emergent OAuth API...")
        
        async with httpx.AsyncClient() as http_client:
            response = await http_client.get(
                "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data",
                headers={"X-Session-ID": session_id},
                timeout=30.0
            )
            
            logger.info(f"OAuth API response status: {response.status_code}")
            
            if response.status_code != 200:
                logger.error(f"OAuth API returned status {response.status_code}: {response.text}")
                raise HTTPException(status_code=401, detail="Invalid session_id")
            
            oauth_data = response.json()
            logger.info(f"OAuth data received for email: {oauth_data.get('email')}")
        
        # Check if user exists in our employee database by email (case-insensitive)
        oauth_email = oauth_data["email"].lower()
        # Escape special regex characters in email
        escaped_email = re.escape(oauth_email)
        
        logger.info(f"Looking up employee with email pattern: {escaped_email}")
        employee = await db.employees.find_one(
            {"email": {"$regex": f"^{escaped_email}$", "$options": "i"}}, 
            {"_id": 0}
        )
        
        if not employee:
            logger.warning(f"OAuth login attempted with unregistered email: {oauth_data['email']}")
            raise HTTPException(status_code=403, detail="Email not authorized. Contact admin to add your account.")
        
        logger.info(f"Employee found: {employee.get('name')} (ID: {employee.get('id')})")
        
        # Create or update OAuth user record
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        
        existing_user = await db.oauth_users.find_one(
            {"email": {"$regex": f"^{escaped_email}$", "$options": "i"}}, 
            {"_id": 0}
        )
        if existing_user:
            user_id = existing_user["user_id"]
            logger.info(f"Existing OAuth user found: {user_id}")
            # Update existing user
            await db.oauth_users.update_one(
                {"user_id": user_id},
                {"$set": {
                    "name": oauth_data["name"],
                    "picture": oauth_data.get("picture")
                }}
            )
        else:
            logger.info(f"Creating new OAuth user: {user_id}")
            # Create new OAuth user linked to employee
            await db.oauth_users.insert_one({
                "user_id": user_id,
                "email": oauth_data["email"],
                "name": oauth_data["name"],
                "picture": oauth_data.get("picture"),
                "employee_id": employee["id"],
                "created_at": datetime.now(timezone.utc).isoformat()
            })
        
        # Create session with 7-day expiry
        session_token = oauth_data["session_token"]
        expires_at = datetime.now(timezone.utc) + timedelta(days=7)
        
        await db.user_sessions.insert_one({
            "user_id": user_id,
            "session_token": session_token,
            "expires_at": expires_at.isoformat(),
            "created_at": datetime.now(timezone.utc).isoformat()
        })
        
        # Return user data with employee info
        response_data = {
            "user_id": user_id,
            "email": oauth_data["email"],
            "name": oauth_data["name"],
            "picture": oauth_data.get("picture"),
            "session_token": session_token,
            "employee_id": employee["id"],
            "is_admin": employee.get("is_admin", False)
        }
        
        logger.info("=== OAuth Session Success ===")
        logger.info(f"User logged in: {oauth_data['email']} -> employee_id: {employee['id']}")
        
        return response_data
    
    except HTTPException as he:
        logger.error(f"HTTPException in create_session: {he.status_code} - {he.detail}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error creating session: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail="Failed to create session")


@api_router.get("/auth/me")
async def get_current_user(request: Request):
    """Get current authenticated user from session token"""
    try:
        # Get session token from cookie or Authorization header
        session_token = request.cookies.get("session_token")
        if not session_token:
            auth_header = request.headers.get("Authorization")
            if auth_header and auth_header.startswith("Bearer "):
                session_token = auth_header.split(" ")[1]
        
        if not session_token:
            raise HTTPException(status_code=401, detail="Not authenticated")
        
        # Find session
        session = await db.user_sessions.find_one({"session_token": session_token}, {"_id": 0})
        if not session:
            raise HTTPException(status_code=401, detail="Invalid session")
        
        # Check expiry
        expires_at = session["expires_at"]
        if isinstance(expires_at, str):
            expires_at = datetime.fromisoformat(expires_at)
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        
        if expires_at < datetime.now(timezone.utc):
            raise HTTPException(status_code=401, detail="Session expired")
        
        # Get user
        user = await db.oauth_users.find_one({"user_id": session["user_id"]}, {"_id": 0})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Get employee info
        employee = await db.employees.find_one({"id": user["employee_id"]}, {"_id": 0})
        
        return {
            "user_id": user["user_id"],
            "email": user["email"],
            "name": user["name"],
            "picture": user.get("picture"),
            "employee_id": user["employee_id"],
            "is_admin": employee.get("is_admin", False) if employee else False
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting current user: {e}")
        raise HTTPException(status_code=401, detail="Authentication failed")


@api_router.post("/auth/logout")
async def logout(request: Request):
    """Logout user and delete session"""
    try:
        session_token = request.cookies.get("session_token")
        if session_token:
            await db.user_sessions.delete_one({"session_token": session_token})
        
        return {"success": True, "message": "Logged out successfully"}
    except Exception as e:
        logger.error(f"Error logging out: {e}")
        return {"success": False, "message": "Logout failed"}


# Venue Pricing endpoints
@api_router.post("/venue_pricing", response_model=VenuePricing)
async def create_venue_pricing(pricing: VenuePricingCreate):
    # Check if venue exists
    venue = await db.venues.find_one({"id": pricing.venue_id})
    if not venue:
        raise HTTPException(status_code=404, detail="Venue not found")
    
    # Check if pricing already exists for this venue
    existing = await db.venue_pricing.find_one({"venue_id": pricing.venue_id})
    if existing:
        # Update existing
        update_data = pricing.model_dump()
        update_data['updated_at'] = datetime.now(timezone.utc).isoformat()
        await db.venue_pricing.update_one(
            {"venue_id": pricing.venue_id},
            {"$set": update_data}
        )
        updated = await db.venue_pricing.find_one({"venue_id": pricing.venue_id}, {"_id": 0})
        if isinstance(updated['created_at'], str):
            updated['created_at'] = datetime.fromisoformat(updated['created_at'])
        if isinstance(updated['updated_at'], str):
            updated['updated_at'] = datetime.fromisoformat(updated['updated_at'])
        return updated
    else:
        # Create new
        pricing_obj = VenuePricing(**pricing.model_dump())
        doc = pricing_obj.model_dump()
        doc['created_at'] = doc['created_at'].isoformat()
        doc['updated_at'] = doc['updated_at'].isoformat()
        await db.venue_pricing.insert_one(doc)
        return pricing_obj

@api_router.get("/venue_pricing", response_model=List[VenuePricing])
async def get_all_venue_pricing():
    pricing_list = await db.venue_pricing.find({}, {"_id": 0}).to_list(1000)
    for pricing in pricing_list:
        if isinstance(pricing['created_at'], str):
            pricing['created_at'] = datetime.fromisoformat(pricing['created_at'])
        if isinstance(pricing['updated_at'], str):
            pricing['updated_at'] = datetime.fromisoformat(pricing['updated_at'])
    return pricing_list

@api_router.get("/venue_pricing/{venue_id}", response_model=VenuePricing)
async def get_venue_pricing(venue_id: str):
    pricing = await db.venue_pricing.find_one({"venue_id": venue_id}, {"_id": 0})
    if not pricing:
        # Return default pricing if not set
        return VenuePricing(
            venue_id=venue_id,
            trivia_price=0.0,
            music_bingo_price=0.0,
            karaoke_price=0.0
        )
    if isinstance(pricing['created_at'], str):
        pricing['created_at'] = datetime.fromisoformat(pricing['created_at'])
    if isinstance(pricing['updated_at'], str):
        pricing['updated_at'] = datetime.fromisoformat(pricing['updated_at'])
    return pricing

@api_router.get("/reports/monthly/expected_income")
async def get_monthly_expected_income(month: str, venue_id: Optional[str] = None):
    """Calculate expected income based on scheduled events and venue pricing"""
    # Parse month (format: "2025-12")
    year, month_num = map(int, month.split('-'))
    
    # Use Arizona/MST boundaries (UTC-7, no DST) to match the frontend calendar display.
    # The frontend creates dates in local time and uses isSameDay() in local time,
    # so the backend must align: April 1 00:00 MST = April 1 07:00 UTC.
    MST_OFFSET_HOURS = 7
    month_start = datetime(year, month_num, 1, MST_OFFSET_HOURS, 0, 0, tzinfo=timezone.utc)
    if month_num == 12:
        month_end = datetime(year + 1, 1, 1, MST_OFFSET_HOURS, 0, 0, tzinfo=timezone.utc)
    else:
        month_end = datetime(year, month_num + 1, 1, MST_OFFSET_HOURS, 0, 0, tzinfo=timezone.utc)
    
    # Build query
    query = {
        "date": {
            "$gte": month_start.isoformat(),
            "$lt": month_end.isoformat()
        }
    }
    if venue_id:
        query["venue_id"] = venue_id
    
    # Get events for the month
    events = await db.events.find(query, {"_id": 0}).to_list(1000)
    
    # Get all venue pricing and venue data
    all_pricing = await db.venue_pricing.find({}, {"_id": 0}).to_list(1000)
    pricing_map = {p['venue_id']: p for p in all_pricing}
    all_venues = await db.venues.find({}, {"_id": 0}).to_list(1000)
    venue_map = {v['id']: v for v in all_venues}
    
    # Calculate expected income
    total_expected = 0
    event_breakdown = []
    
    # Special fixed price for franchise venues like Monkey Pants
    FRANCHISE_FIXED_PRICE = 150.0
    
    for event in events:
        venue = venue_map.get(event['venue_id'])
        
        # Determine the event price
        if venue and venue.get('venue_pays_host_directly', False):
            # Franchise venues (like Monkey Pants) always pay $150 per event
            # This counts as INCOME for every event
            event_price = FRANCHISE_FIXED_PRICE
        else:
            # Regular venues use venue pricing
            venue_pricing = pricing_map.get(event['venue_id'])
            if not venue_pricing:
                continue
            
            event_price = 0
            if event['event_type'] == 'Trivia':
                event_price = venue_pricing.get('trivia_price', 0)
            elif event['event_type'] == 'Music Bingo':
                event_price = venue_pricing.get('music_bingo_price', 0)
            elif event['event_type'] == 'Karaoke':
                event_price = venue_pricing.get('karaoke_price', 0)
        
        if event_price > 0:
            total_expected += event_price
            event_breakdown.append({
                "event_id": event['id'],
                "event_type": event['event_type'],
                "venue_id": event['venue_id'],
                "date": event['date'],
                "expected_income": event_price,
                "venue_pays_host_directly": venue.get('venue_pays_host_directly', False) if venue else False
            })
    
    return {
        "month": month,
        "venue_id": venue_id,
        "total_expected_income": total_expected,
        "event_count": len(event_breakdown),
        "events": event_breakdown
    }


# ============= BLACKOUT DATES ENDPOINTS =============

@api_router.get("/blackouts")
async def get_all_blackouts():
    """Get all blackout dates"""
    blackouts = await db.blackout_dates.find({}, {"_id": 0}).to_list(1000)
    return blackouts

@api_router.get("/blackouts/employee/{employee_id}")
async def get_employee_blackouts(employee_id: str):
    """Get blackout dates for a specific employee"""
    blackouts = await db.blackout_dates.find(
        {"employee_id": employee_id}, 
        {"_id": 0}
    ).to_list(100)
    return blackouts

@api_router.get("/blackouts/month/{month}")
async def get_blackouts_by_month(month: str):
    """Get all blackouts that overlap with a specific month (format: 2026-01)"""
    try:
        # Parse the month to get the date range
        year, month_num = map(int, month.split('-'))
        month_start = f"{year}-{month_num:02d}-01"
        
        # Calculate last day of month
        if month_num == 12:
            next_month_start = f"{year + 1}-01-01"
        else:
            next_month_start = f"{year}-{month_num + 1:02d}-01"
        
        from datetime import datetime as dt
        last_day = (dt.strptime(next_month_start, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
        month_end = last_day
        
        logger.info(f"Fetching blackouts for month {month}: {month_start} to {month_end}")
        
        # Find blackouts that overlap with this month
        # A blackout overlaps if: start_date <= month_end AND end_date >= month_start
        blackouts = await db.blackout_dates.find({
            "$and": [
                {"start_date": {"$lte": month_end}},
                {"end_date": {"$gte": month_start}}
            ]
        }, {"_id": 0}).to_list(1000)
        
        # Get employee names for each blackout
        result = []
        for blackout in blackouts:
            employee = await db.employees.find_one(
                {"id": blackout["employee_id"]}, 
                {"_id": 0, "name": 1}
            )
            result.append({
                **blackout,
                "employee_name": employee["name"] if employee else "Unknown"
            })
        
        return result
        
    except Exception as e:
        logger.error(f"Error fetching blackouts by month: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch blackouts")

@api_router.post("/blackouts", response_model=BlackoutDate)
async def create_blackout(blackout: BlackoutDateCreate):
    """Create a new blackout date range"""
    try:
        # Validate employee exists
        employee = await db.employees.find_one({"id": blackout.employee_id})
        if not employee:
            raise HTTPException(status_code=404, detail="Employee not found")
        
        # Validate dates
        from datetime import datetime as dt
        try:
            start = dt.strptime(blackout.start_date, "%Y-%m-%d")
            end = dt.strptime(blackout.end_date, "%Y-%m-%d")
            if end < start:
                raise HTTPException(status_code=400, detail="End date must be after start date")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
        
        # Create the blackout
        new_blackout = BlackoutDate(
            employee_id=blackout.employee_id,
            start_date=blackout.start_date,
            end_date=blackout.end_date
        )
        
        await db.blackout_dates.insert_one(new_blackout.model_dump())
        logger.info(f"Created blackout for employee {blackout.employee_id}: {blackout.start_date} to {blackout.end_date}")
        
        return new_blackout
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating blackout: {e}")
        raise HTTPException(status_code=500, detail="Failed to create blackout")

@api_router.delete("/blackouts/{blackout_id}")
async def delete_blackout(blackout_id: str):
    """Delete a blackout date range"""
    result = await db.blackout_dates.delete_one({"id": blackout_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Blackout not found")
    
    logger.info(f"Deleted blackout: {blackout_id}")
    return {"success": True, "message": "Blackout deleted"}


# ============= VENUE ROLES ENDPOINTS =============

@api_router.get("/venue-roles")
async def get_all_venue_roles():
    """Get all venue roles"""
    roles = await db.venue_roles.find({}, {"_id": 0}).to_list(1000)
    return roles

@api_router.get("/venue-roles/venue/{venue_id}")
async def get_venue_roles(venue_id: str):
    """Get all roles for a specific venue"""
    roles = await db.venue_roles.find({"venue_id": venue_id}, {"_id": 0}).to_list(100)
    return roles

@api_router.get("/venue-roles/employee/{employee_id}")
async def get_employee_roles(employee_id: str):
    """Get all roles for a specific employee"""
    roles = await db.venue_roles.find({"employee_id": employee_id}, {"_id": 0}).to_list(100)
    return roles

@api_router.post("/venue-roles")
async def create_venue_role(role: VenueRoleCreate):
    """Create or assign a venue role"""
    # Validate inputs
    if role.role_category not in ("trivia", "bingo_karaoke"):
        raise HTTPException(status_code=400, detail="Invalid role_category. Must be 'trivia' or 'bingo_karaoke'")
    if role.role_type not in ("primary", "secondary"):
        raise HTTPException(status_code=400, detail="Invalid role_type. Must be 'primary' or 'secondary'")

    # Verify venue and employee exist
    venue = await db.venues.find_one({"id": role.venue_id})
    if not venue:
        raise HTTPException(status_code=404, detail="Venue not found")
    employee = await db.employees.find_one({"id": role.employee_id})
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    # Check venue pricing to see if the service is offered
    pricing = await db.venue_pricing.find_one({"venue_id": role.venue_id}, {"_id": 0})
    if role.role_category == "trivia":
        if not pricing or pricing.get("trivia_price", 0) <= 0:
            raise HTTPException(status_code=400, detail="This venue does not offer Trivia events")
    elif role.role_category == "bingo_karaoke":
        if not pricing or (pricing.get("music_bingo_price", 0) <= 0 and pricing.get("karaoke_price", 0) <= 0):
            raise HTTPException(status_code=400, detail="This venue does not offer Bingo/Karaoke events")

    # If primary, check that no other primary exists for this venue+category
    if role.role_type == "primary":
        existing_primary = await db.venue_roles.find_one({
            "venue_id": role.venue_id,
            "role_category": role.role_category,
            "role_type": "primary"
        })
        if existing_primary:
            raise HTTPException(status_code=400, detail="A primary already exists for this venue and category. Remove the existing primary first.")

    # Check for duplicate role (same employee, venue, category, type)
    existing = await db.venue_roles.find_one({
        "venue_id": role.venue_id,
        "employee_id": role.employee_id,
        "role_category": role.role_category,
        "role_type": role.role_type
    })
    if existing:
        raise HTTPException(status_code=400, detail="This role already exists")

    new_role = VenueRole(**role.model_dump())
    doc = new_role.model_dump()
    doc['created_at'] = doc['created_at'].isoformat()
    await db.venue_roles.insert_one(doc)

    logger.info(f"Created venue role: {employee.get('name')} as {role.role_type} {role.role_category} at {venue.get('name')}")
    return {k: v for k, v in doc.items() if k != '_id'}

@api_router.delete("/venue-roles/{role_id}")
async def delete_venue_role(role_id: str):
    """Remove a venue role"""
    result = await db.venue_roles.delete_one({"id": role_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Role not found")
    logger.info(f"Deleted venue role: {role_id}")
    return {"success": True, "message": "Role removed"}

@api_router.get("/venue-roles/validate/{employee_id}")
async def validate_employee_roles(employee_id: str):
    """Check if an employee who is a primary somewhere is also a secondary at another venue"""
    all_roles = await db.venue_roles.find({"employee_id": employee_id}, {"_id": 0}).to_list(100)

    primary_roles = [r for r in all_roles if r["role_type"] == "primary"]
    secondary_roles = [r for r in all_roles if r["role_type"] == "secondary"]

    if not primary_roles:
        return {"valid": True, "message": "No primary roles, no secondary requirement", "needs_secondary": False}

    # Get unique venue_ids where they are primary
    primary_venue_ids = set(r["venue_id"] for r in primary_roles)
    # Get unique venue_ids where they are secondary (must be at a DIFFERENT venue)
    secondary_venue_ids = set(r["venue_id"] for r in secondary_roles)
    other_secondary_venues = secondary_venue_ids - primary_venue_ids

    if other_secondary_venues:
        return {"valid": True, "message": "Employee has secondary role at another venue", "needs_secondary": False}
    else:
        return {
            "valid": False,
            "message": "Primary hosts must also be a secondary at least one other location",
            "needs_secondary": True,
            "primary_venue_ids": list(primary_venue_ids)
        }

@api_router.get("/venue-roles/services")
async def get_venue_services():
    """Get which services each venue offers based on pricing > $0"""
    all_pricing = await db.venue_pricing.find({}, {"_id": 0}).to_list(1000)
    all_venues = await db.venues.find({}, {"_id": 0}).to_list(1000)
    venue_map = {v['id']: v['name'] for v in all_venues}

    services = {}
    for p in all_pricing:
        vid = p['venue_id']
        vname = venue_map.get(vid)
        if not vname:
            continue  # Skip orphaned pricing records
        offers_trivia = p.get('trivia_price', 0) > 0
        offers_bingo_karaoke = p.get('music_bingo_price', 0) > 0 or p.get('karaoke_price', 0) > 0
        if offers_trivia or offers_bingo_karaoke:
            services[vid] = {
                "venue_id": vid,
                "venue_name": vname,
                "offers_trivia": offers_trivia,
                "offers_bingo_karaoke": offers_bingo_karaoke
            }
    return services


# ============= NOTIFICATION ENDPOINTS =============

@api_router.post("/notifications/send-primary-report")
async def trigger_primary_report():
    """Manually trigger the Friday primary venue report emails."""
    from notifications import send_primary_friday_reports
    result = await send_primary_friday_reports()
    return {"success": True, **result}

@api_router.post("/notifications/send-secondary-availability")
async def trigger_secondary_availability():
    """Manually trigger the Monday secondary availability emails."""
    from notifications import send_secondary_monday_availability
    result = await send_secondary_monday_availability()
    return {"success": True, **result}


# Include the router in the main app
app.include_router(api_router)

# Health check endpoint for Kubernetes (must be at root level, not under /api)
@app.get("/health")
async def health_check():
    """Health check endpoint for Kubernetes liveness/readiness probes"""
    return {"status": "healthy"}

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
