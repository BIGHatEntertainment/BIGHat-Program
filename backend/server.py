from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, Depends
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
from contextlib import asynccontextmanager
import os
import logging
import bcrypt
import jwt as pyjwt
import secrets
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional
import uuid
from datetime import datetime, timezone, timedelta

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("bighat-hub")

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# JWT config
JWT_ALGORITHM = "HS256"
def get_jwt_secret():
    return os.environ["JWT_SECRET"]

# ===== PASSWORD UTILITIES =====
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))

def create_access_token(user_id: str, email: str, role: str) -> str:
    payload = {"sub": user_id, "email": email, "role": role, "exp": datetime.now(timezone.utc) + timedelta(hours=24), "type": "access"}
    return pyjwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)

def create_refresh_token(user_id: str) -> str:
    payload = {"sub": user_id, "exp": datetime.now(timezone.utc) + timedelta(days=7), "type": "refresh"}
    return pyjwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)

# ===== AUTH DEPENDENCIES =====
async def get_current_user(request: Request) -> dict:
    token = request.cookies.get("access_token")
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = pyjwt.decode(token, get_jwt_secret(), algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token type")
        user = await db.users.find_one({"_id": ObjectId(payload["sub"])})
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        user["_id"] = str(user["_id"])
        user.pop("password_hash", None)
        return user
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except pyjwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

async def require_admin(request: Request) -> dict:
    user = await get_current_user(request)
    if user.get("role") not in ["admin", "master_admin"]:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user

# ===== HUB MODELS =====
class LoginRequest(BaseModel):
    email: str
    password: str

class RegisterRequest(BaseModel):
    email: str
    password: str
    name: str
    role: str = "host"

class UserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None
    password: Optional[str] = None

# ===== SCHEDULE MODELS (from Calendar-Scheduler) =====
class ScheduleEmployee(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    email: str
    phone: Optional[str] = None
    is_admin: bool = False
    password: str = "B1GHat"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class ScheduleEmployeeCreate(BaseModel):
    name: str
    email: str
    phone: Optional[str] = None
    is_admin: bool = False
    password: Optional[str] = "B1GHat"

class Venue(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    address: str
    city: str = "Phoenix"
    state: str = "AZ"
    notes: Optional[str] = None
    venue_pays_host_directly: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class VenueCreate(BaseModel):
    name: str
    address: str
    city: str = "Phoenix"
    state: str = "AZ"
    notes: Optional[str] = None
    venue_pays_host_directly: bool = False

class ScheduleEvent(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    event_type: str
    venue_id: str
    date: datetime
    duration_hours: float = 2.0
    pay_rate: Optional[float] = None
    notes: Optional[str] = None
    claimed_by: Optional[str] = None
    claimed_at: Optional[datetime] = None
    status: str = "available"
    wore_big_hat: bool = False
    social_media_posts: bool = False
    winners_post: bool = False
    is_special_event: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class ScheduleEventCreate(BaseModel):
    title: str
    event_type: str
    venue_id: str
    date: datetime
    duration_hours: float = 2.0
    pay_rate: Optional[float] = None
    notes: Optional[str] = None

class ScheduleEventUpdate(BaseModel):
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

class PaymentAcknowledgment(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event_id: str
    event_title: str
    event_type: str
    venue_name: str
    employee_id: str
    employee_name: str
    employee_email: str = ""
    event_date: datetime
    base_pay: float
    bonuses: float
    bonus_details: List[str] = []
    wore_big_hat: bool = False
    social_media_posts: bool = False
    winners_post: bool = False
    total_pay: float
    venue_id: str
    venue_pays_host_directly: bool = False
    acknowledged_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    acknowledged_month: str

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
    month: str
    archived_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    total_income: float = 0.0
    income_by_location: dict = {}
    income_by_event: List[dict] = []
    total_outgoing: float = 0.0
    payments_by_event: List[dict] = []
    net_revenue: float = 0.0
    event_count: int = 0
    payment_count: int = 0

class BlackoutDate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    employee_id: str
    start_date: str
    end_date: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class BlackoutDateCreate(BaseModel):
    employee_id: str
    start_date: str
    end_date: str

class VenueRole(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    venue_id: str
    employee_id: str
    role_category: str
    role_type: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class VenueRoleCreate(BaseModel):
    venue_id: str
    employee_id: str
    role_category: str
    role_type: str

class AdminAssign(BaseModel):
    employee_id: str

class UpdateBonuses(BaseModel):
    wore_big_hat: bool
    social_media_posts: bool
    winners_post: bool

# ===== SCHEDULER REFERENCE =====
scheduler_instance = None

# ===== LIFESPAN =====
async def seed_data():
    """Seed master admin, employees, venues and events"""
    # Seed master admin user
    admin_email = os.environ.get("ADMIN_EMAIL", "admin@example.com").lower().strip()
    admin_password = os.environ.get("ADMIN_PASSWORD", "admin123")
    existing = await db.users.find_one({"email": admin_email})
    if existing is None:
        hashed = hash_password(admin_password)
        await db.users.insert_one({
            "email": admin_email, "password_hash": hashed, "name": "Nick Sellards",
            "role": "master_admin", "created_at": datetime.now(timezone.utc).isoformat()
        })
        logger.info(f"Master admin seeded: {admin_email}")
    elif not verify_password(admin_password, existing["password_hash"]):
        await db.users.update_one({"email": admin_email}, {"$set": {"password_hash": hash_password(admin_password)}})

    # Seed schedule employees (hosts)
    emp_count = await db.employees.count_documents({})
    if emp_count == 0:
        employees_data = [
            {"id": str(uuid.uuid4()), "name": "Nick Sellards", "email": "sellards@bighat.live", "is_admin": True, "password": "B1GHat", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": str(uuid.uuid4()), "name": "Alex Rivera", "email": "alex@bighat.live", "is_admin": False, "password": "B1GHat", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": str(uuid.uuid4()), "name": "Jordan Blake", "email": "jordan@bighat.live", "is_admin": False, "password": "B1GHat", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": str(uuid.uuid4()), "name": "Casey Morgan", "email": "casey@bighat.live", "is_admin": False, "password": "B1GHat", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": str(uuid.uuid4()), "name": "Taylor Reed", "email": "taylor@bighat.live", "is_admin": False, "password": "B1GHat", "created_at": datetime.now(timezone.utc).isoformat()},
        ]
        await db.employees.insert_many(employees_data)
        logger.info(f"Seeded {len(employees_data)} employees")

    # Seed venues
    venue_count = await db.venues.count_documents({})
    if venue_count == 0:
        venues_data = [
            {"id": "venue-taphouse", "name": "The Tap House", "address": "123 Main St", "city": "Phoenix", "state": "AZ", "venue_pays_host_directly": False, "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "venue-rustynail", "name": "Rusty Nail Bar", "address": "456 Oak Ave", "city": "Scottsdale", "state": "AZ", "venue_pays_host_directly": False, "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "venue-desertridge", "name": "Desert Ridge Tavern", "address": "789 Desert Blvd", "city": "Phoenix", "state": "AZ", "venue_pays_host_directly": False, "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "venue-cactusjacks", "name": "Cactus Jack's", "address": "321 Cactus Way", "city": "Tempe", "state": "AZ", "venue_pays_host_directly": False, "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "venue-pinthouse", "name": "The Pint House", "address": "654 Brewery Ln", "city": "Mesa", "state": "AZ", "venue_pays_host_directly": False, "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "venue-copperblues", "name": "Copper Blues", "address": "987 Music Row", "city": "Phoenix", "state": "AZ", "venue_pays_host_directly": False, "created_at": datetime.now(timezone.utc).isoformat()},
        ]
        await db.venues.insert_many(venues_data)
        logger.info(f"Seeded {len(venues_data)} venues")

        # Seed venue pricing
        pricing_data = [
            {"venue_id": "venue-taphouse", "trivia_price": 200, "music_bingo_price": 200, "karaoke_price": 0, "created_at": datetime.now(timezone.utc).isoformat(), "updated_at": datetime.now(timezone.utc).isoformat()},
            {"venue_id": "venue-rustynail", "trivia_price": 175, "music_bingo_price": 200, "karaoke_price": 0, "created_at": datetime.now(timezone.utc).isoformat(), "updated_at": datetime.now(timezone.utc).isoformat()},
            {"venue_id": "venue-desertridge", "trivia_price": 200, "music_bingo_price": 0, "karaoke_price": 0, "created_at": datetime.now(timezone.utc).isoformat(), "updated_at": datetime.now(timezone.utc).isoformat()},
            {"venue_id": "venue-cactusjacks", "trivia_price": 0, "music_bingo_price": 0, "karaoke_price": 150, "created_at": datetime.now(timezone.utc).isoformat(), "updated_at": datetime.now(timezone.utc).isoformat()},
            {"venue_id": "venue-pinthouse", "trivia_price": 0, "music_bingo_price": 225, "karaoke_price": 0, "created_at": datetime.now(timezone.utc).isoformat(), "updated_at": datetime.now(timezone.utc).isoformat()},
            {"venue_id": "venue-copperblues", "trivia_price": 200, "music_bingo_price": 200, "karaoke_price": 175, "created_at": datetime.now(timezone.utc).isoformat(), "updated_at": datetime.now(timezone.utc).isoformat()},
        ]
        await db.venue_pricing.insert_many(pricing_data)

    # Seed schedule events
    event_count = await db.events.count_documents({})
    if event_count == 0:
        employees = await db.employees.find({}, {"_id": 0, "id": 1}).to_list(10)
        emp_ids = [e["id"] for e in employees]
        
        # Generate events for next 4 weeks from now
        now = datetime.now(timezone.utc)
        # Start from next Monday
        days_until_monday = (7 - now.weekday()) % 7
        if days_until_monday == 0:
            days_until_monday = 7
        base_date = (now + timedelta(days=days_until_monday)).replace(hour=0, minute=0, second=0, microsecond=0)
        events_data = []
        
        recurring = [
            ("Tuesday Trivia Night", "Trivia", "venue-taphouse", 1, "19:00"),
            ("Wednesday Bingo Bash", "Music Bingo", "venue-rustynail", 2, "20:00"),
            ("Thursday Trivia", "Trivia", "venue-desertridge", 3, "19:30"),
            ("Friday Night Karaoke", "Karaoke", "venue-cactusjacks", 4, "21:00"),
            ("Saturday Bingo Bonanza", "Music Bingo", "venue-pinthouse", 5, "18:00"),
            ("Sunday Funday Trivia", "Trivia", "venue-copperblues", 6, "16:00"),
        ]
        
        for week in range(4):
            for title, etype, vid, day_offset, time_str in recurring:
                h, m = map(int, time_str.split(":"))
                event_date = base_date + timedelta(days=week * 7 + day_offset, hours=h, minutes=m)
                events_data.append({
                    "id": str(uuid.uuid4()),
                    "title": title,
                    "event_type": etype,
                    "venue_id": vid,
                    "date": event_date.isoformat(),
                    "duration_hours": 2.0,
                    "claimed_by": None,
                    "claimed_at": None,
                    "status": "available",
                    "wore_big_hat": False,
                    "social_media_posts": False,
                    "winners_post": False,
                    "is_special_event": False,
                    "created_at": datetime.now(timezone.utc).isoformat()
                })
        
        await db.events.insert_many(events_data)
        logger.info(f"Seeded {len(events_data)} schedule events")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global scheduler_instance
    logger.info("Starting BIG Hat Hub API...")
    
    # Create indexes
    await db.users.create_index("email", unique=True)
    await db.login_attempts.create_index("identifier")
    await db.events.create_index("date")
    await db.employees.create_index("email")
    await db.employees.create_index("id", unique=True)
    await db.venues.create_index("id", unique=True)
    
    # Seed data
    await seed_data()
    
    # Initialize GridFS
    try:
        from gridfs_service import init_gridfs_service
        init_gridfs_service(db)
        logger.info("GridFS service initialized")
    except Exception as e:
        logger.warning(f"GridFS not initialized: {e}")
    
    # Start scheduler
    try:
        from scheduler import start_scheduler
        scheduler_instance = start_scheduler()
        logger.info("Scheduler initialized")
    except Exception as e:
        logger.warning(f"Scheduler not started: {e}")
    
    logger.info("BIG Hat Hub API started successfully")
    yield
    
    if scheduler_instance:
        scheduler_instance.shutdown()
    client.close()


# ===== APP SETUP =====
app = FastAPI(lifespan=lifespan)

# Custom CORS middleware
class CustomCORSMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        origin = request.headers.get("origin", "*")
        if request.method == "OPTIONS":
            response = JSONResponse(content={}, status_code=200)
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS, PATCH"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Session-ID, X-Requested-With, Accept"
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Access-Control-Max-Age"] = "600"
            return response
        response = await call_next(request)
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS, PATCH"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Session-ID, X-Requested-With, Accept"
        return response

app.add_middleware(CustomCORSMiddleware)

api_router = APIRouter(prefix="/api")

# =============================================
# HUB AUTH ROUTES
# =============================================

@api_router.post("/auth/login")
async def login(request: Request, response: Response, body: LoginRequest):
    email = body.email.lower().strip()
    ip = request.client.host if request.client else "unknown"
    identifier = f"{ip}:{email}"
    attempt = await db.login_attempts.find_one({"identifier": identifier})
    if attempt and attempt.get("count", 0) >= 5:
        lockout_until = attempt.get("locked_until")
        if lockout_until and datetime.now(timezone.utc) < lockout_until:
            raise HTTPException(status_code=429, detail="Too many failed attempts. Try again in 15 minutes.")
        else:
            await db.login_attempts.delete_one({"identifier": identifier})
    user = await db.users.find_one({"email": email})
    if not user or not verify_password(body.password, user["password_hash"]):
        await db.login_attempts.update_one({"identifier": identifier}, {"$inc": {"count": 1}, "$set": {"locked_until": datetime.now(timezone.utc) + timedelta(minutes=15)}}, upsert=True)
        raise HTTPException(status_code=401, detail="Invalid email or password")
    await db.login_attempts.delete_many({"identifier": identifier})
    user_id = str(user["_id"])
    access_token = create_access_token(user_id, email, user.get("role", "host"))
    refresh_token = create_refresh_token(user_id)
    response.set_cookie(key="access_token", value=access_token, httponly=True, secure=False, samesite="lax", max_age=86400, path="/")
    response.set_cookie(key="refresh_token", value=refresh_token, httponly=True, secure=False, samesite="lax", max_age=604800, path="/")
    return {"id": user_id, "email": user["email"], "name": user.get("name", ""), "role": user.get("role", "host"), "token": access_token}

@api_router.post("/auth/register")
async def register(response: Response, body: RegisterRequest, admin: dict = Depends(require_admin)):
    email = body.email.lower().strip()
    existing = await db.users.find_one({"email": email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    if body.role in ["admin", "master_admin"] and admin.get("role") != "master_admin":
        raise HTTPException(status_code=403, detail="Only master admin can create admin users")
    result = await db.users.insert_one({"email": email, "password_hash": hash_password(body.password), "name": body.name, "role": body.role, "created_at": datetime.now(timezone.utc).isoformat(), "created_by": admin.get("_id", "system")})
    return {"id": str(result.inserted_id), "email": email, "name": body.name, "role": body.role}

@api_router.post("/auth/logout")
async def logout(response: Response):
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")
    return {"message": "Logged out"}

@api_router.post("/auth/google-callback")
async def google_callback(request: Request, response: Response):
    """Exchange session_id from Emergent Google Auth for a user session"""
    import httpx
    body = await request.json()
    session_id = body.get("session_id")
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id required")
    
    # Exchange session_id for user data from Emergent Auth
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data",
                headers={"X-Session-ID": session_id}
            )
            if resp.status_code != 200:
                raise HTTPException(status_code=401, detail="Invalid session")
            google_data = resp.json()
    except httpx.HTTPError as e:
        logger.error(f"Google auth error: {e}")
        raise HTTPException(status_code=500, detail="Auth service unavailable")
    
    email = google_data.get("email", "").lower().strip()
    name = google_data.get("name", "")
    picture = google_data.get("picture", "")
    
    # Find or create user
    user = await db.users.find_one({"email": email})
    if user:
        # Update name/picture if changed
        await db.users.update_one({"email": email}, {"$set": {"name": name, "picture": picture}})
        user_id = str(user["_id"])
        role = user.get("role", "host")
    else:
        # Create new user as host
        result = await db.users.insert_one({
            "email": email, "password_hash": hash_password(secrets.token_hex(16)),
            "name": name, "picture": picture, "role": "host",
            "created_at": datetime.now(timezone.utc).isoformat(), "auth_method": "google"
        })
        user_id = str(result.inserted_id)
        role = "host"
    
    # Create JWT tokens
    access_token = create_access_token(user_id, email, role)
    refresh_token_val = create_refresh_token(user_id)
    
    response.set_cookie(key="access_token", value=access_token, httponly=True, secure=False, samesite="lax", max_age=86400, path="/")
    response.set_cookie(key="refresh_token", value=refresh_token_val, httponly=True, secure=False, samesite="lax", max_age=604800, path="/")
    
    logger.info(f"Google auth: {email} logged in as {role}")
    return {"id": user_id, "email": email, "name": name, "role": role, "token": access_token}



@api_router.get("/auth/me")
async def get_me(user: dict = Depends(get_current_user)):
    return {"id": user["_id"], "email": user["email"], "name": user.get("name", ""), "role": user.get("role", "host")}

@api_router.post("/auth/refresh")
async def refresh_token(request: Request, response: Response):
    token = request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(status_code=401, detail="No refresh token")
    try:
        payload = pyjwt.decode(token, get_jwt_secret(), algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")
        user = await db.users.find_one({"_id": ObjectId(payload["sub"])})
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        access_token = create_access_token(str(user["_id"]), user["email"], user.get("role", "host"))
        response.set_cookie(key="access_token", value=access_token, httponly=True, secure=False, samesite="lax", max_age=86400, path="/")
        return {"message": "Token refreshed", "token": access_token}
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Refresh token expired")
    except pyjwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

# =============================================
# HUB USER MANAGEMENT (Admin)
# =============================================

@api_router.get("/users")
async def list_users(admin: dict = Depends(require_admin)):
    users = await db.users.find({}, {"password_hash": 0}).to_list(1000)
    for u in users:
        u["_id"] = str(u["_id"])
    return users

@api_router.put("/users/{user_id}")
async def update_user(user_id: str, body: UserUpdate, admin: dict = Depends(require_admin)):
    target = await db.users.find_one({"_id": ObjectId(user_id)})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target.get("role") == "master_admin" and admin.get("role") != "master_admin":
        raise HTTPException(status_code=403, detail="Cannot modify master admin")
    update_data = {}
    if body.name is not None: update_data["name"] = body.name
    if body.email is not None: update_data["email"] = body.email.lower().strip()
    if body.role is not None:
        if body.role in ["admin", "master_admin"] and admin.get("role") != "master_admin":
            raise HTTPException(status_code=403, detail="Only master admin can assign admin roles")
        update_data["role"] = body.role
    if body.password is not None: update_data["password_hash"] = hash_password(body.password)
    if update_data:
        await db.users.update_one({"_id": ObjectId(user_id)}, {"$set": update_data})
    updated = await db.users.find_one({"_id": ObjectId(user_id)}, {"password_hash": 0})
    updated["_id"] = str(updated["_id"])
    return updated

@api_router.delete("/users/{user_id}")
async def delete_user(user_id: str, admin: dict = Depends(require_admin)):
    target = await db.users.find_one({"_id": ObjectId(user_id)})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target.get("role") == "master_admin":
        raise HTTPException(status_code=403, detail="Cannot delete master admin")
    await db.users.delete_one({"_id": ObjectId(user_id)})
    return {"message": "User deleted"}

# =============================================
# SCHEDULE - HOST AUTH (legacy from scheduler app)
# =============================================

@api_router.post("/admin/verify")
async def verify_admin_passcode(auth: AdminAuth):
    if auth.passcode == "121589":
        return {"success": True, "message": "Admin authenticated"}
    admin_employees = await db.employees.find({"is_admin": True}, {"_id": 0}).to_list(100)
    for adm in admin_employees:
        pwd = adm.get('password', '')
        if pwd and pwd != 'B1GHat' and auth.passcode == pwd:
            return {"success": True, "message": f"Admin authenticated as {adm.get('name')}"}
    raise HTTPException(status_code=401, detail="Invalid passcode")

@api_router.post("/host/login")
async def host_login(login_data: HostLogin):
    employee = await db.employees.find_one({"name": login_data.name}, {"_id": 0})
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    if login_data.password == "121589" or login_data.password == employee.get('password', 'B1GHat'):
        return {"success": True, "employee": {"id": employee['id'], "name": employee['name'], "email": employee['email'], "is_admin": employee.get('is_admin', False)}}
    raise HTTPException(status_code=401, detail="Invalid password")

@api_router.post("/host/password/change")
async def change_host_password(change: PasswordChange):
    employee = await db.employees.find_one({"id": change.employee_id})
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    current_pwd = employee.get('password', 'B1GHat')
    if change.current_password != current_pwd and change.current_password != "121589":
        raise HTTPException(status_code=401, detail="Current password is incorrect")
    await db.employees.update_one({"id": change.employee_id}, {"$set": {"password": change.new_password}})
    return {"success": True, "message": "Password changed successfully"}

@api_router.get("/host/password/is-default/{employee_id}")
async def check_default_password(employee_id: str):
    employee = await db.employees.find_one({"id": employee_id}, {"_id": 0})
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    is_default = employee.get('password', 'B1GHat') == 'B1GHat'
    return {"is_default": is_default, "default_password": "B1GHat" if is_default else None}

@api_router.post("/host/password/verify")
async def verify_host_password(verify: PasswordVerify):
    employee = await db.employees.find_one({"id": verify.employee_id})
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    if verify.password == "121589" or verify.password == employee.get('password', 'B1GHat'):
        return {"success": True}
    raise HTTPException(status_code=401, detail="Invalid password")

@api_router.post("/employees/{employee_id}/password/reset")
async def reset_employee_password(employee_id: str, reset: PasswordReset):
    employee = await db.employees.find_one({"id": employee_id})
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    await db.employees.update_one({"id": employee_id}, {"$set": {"password": reset.new_password}})
    return {"success": True, "message": "Password reset successfully"}

# =============================================
# SCHEDULE - EMPLOYEES
# =============================================

@api_router.post("/employees", response_model=ScheduleEmployee)
async def create_schedule_employee(employee: ScheduleEmployeeCreate):
    obj = ScheduleEmployee(**employee.model_dump())
    doc = obj.model_dump()
    doc['created_at'] = doc['created_at'].isoformat()
    await db.employees.insert_one(doc)
    return obj

@api_router.get("/employees")
async def get_schedule_employees():
    employees = await db.employees.find({}, {"_id": 0}).to_list(1000)
    for emp in employees:
        if isinstance(emp.get('created_at'), str):
            emp['created_at'] = datetime.fromisoformat(emp['created_at'])
    return employees

@api_router.get("/employees/{employee_id}")
async def get_schedule_employee(employee_id: str):
    employee = await db.employees.find_one({"id": employee_id}, {"_id": 0})
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    if isinstance(employee.get('created_at'), str):
        employee['created_at'] = datetime.fromisoformat(employee['created_at'])
    return employee

@api_router.put("/employees/{employee_id}")
async def update_schedule_employee(employee_id: str, employee: ScheduleEmployeeCreate):
    existing = await db.employees.find_one({"id": employee_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Employee not found")
    await db.employees.update_one({"id": employee_id}, {"$set": employee.model_dump()})
    updated = await db.employees.find_one({"id": employee_id}, {"_id": 0})
    if isinstance(updated.get('created_at'), str):
        updated['created_at'] = datetime.fromisoformat(updated['created_at'])
    return updated

@api_router.delete("/employees/{employee_id}")
async def delete_schedule_employee(employee_id: str):
    result = await db.employees.delete_one({"id": employee_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Employee not found")
    return {"success": True, "message": "Employee deleted"}

# =============================================
# SCHEDULE - VENUES
# =============================================

@api_router.post("/venues", response_model=Venue)
async def create_venue(venue: VenueCreate):
    obj = Venue(**venue.model_dump())
    doc = obj.model_dump()
    doc['created_at'] = doc['created_at'].isoformat()
    await db.venues.insert_one(doc)
    return obj

@api_router.get("/venues")
async def get_venues():
    venues = await db.venues.find({}, {"_id": 0}).to_list(1000)
    for v in venues:
        if isinstance(v.get('created_at'), str):
            v['created_at'] = datetime.fromisoformat(v['created_at'])
    return venues

@api_router.put("/venues/{venue_id}")
async def update_venue(venue_id: str, venue: VenueCreate):
    existing = await db.venues.find_one({"id": venue_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Venue not found")
    await db.venues.update_one({"id": venue_id}, {"$set": venue.model_dump()})
    updated = await db.venues.find_one({"id": venue_id}, {"_id": 0})
    if isinstance(updated.get('created_at'), str):
        updated['created_at'] = datetime.fromisoformat(updated['created_at'])
    return updated

@api_router.delete("/venues/{venue_id}")
async def delete_venue(venue_id: str):
    result = await db.venues.delete_one({"id": venue_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Venue not found")
    return {"success": True, "message": "Venue deleted"}

# =============================================
# SCHEDULE - EVENTS
# =============================================

@api_router.post("/events")
async def create_schedule_event(event: ScheduleEventCreate):
    venue = await db.venues.find_one({"id": event.venue_id})
    if not venue:
        raise HTTPException(status_code=404, detail="Venue not found")
    obj = ScheduleEvent(**event.model_dump())
    doc = obj.model_dump()
    doc['date'] = doc['date'].isoformat()
    doc['created_at'] = doc['created_at'].isoformat()
    if doc['claimed_at']:
        doc['claimed_at'] = doc['claimed_at'].isoformat()
    await db.events.insert_one(doc)
    return obj

@api_router.get("/events")
async def get_schedule_events(include_past: bool = False):
    query = {}
    if not include_past:
        query['date'] = {'$gte': datetime.now(timezone.utc).isoformat()}
    events = await db.events.find(query, {"_id": 0}).sort("date", 1).to_list(1000)
    for event in events:
        if isinstance(event.get('date'), str):
            event['date'] = datetime.fromisoformat(event['date'])
        if isinstance(event.get('created_at'), str):
            event['created_at'] = datetime.fromisoformat(event['created_at'])
        if event.get('claimed_at') and isinstance(event['claimed_at'], str):
            event['claimed_at'] = datetime.fromisoformat(event['claimed_at'])
    return events

@api_router.get("/events/unclaimed")
async def get_unclaimed_events():
    # Calculate current week boundaries in MST (UTC-7)
    MST_OFFSET = timedelta(hours=-7)
    now_mst = datetime.now(timezone.utc) + MST_OFFSET
    
    # Week runs Sunday to Saturday in MST
    day_of_week = now_mst.weekday()  # 0=Mon, 6=Sun
    # Days since last Sunday
    days_since_sunday = (day_of_week + 1) % 7
    week_start_mst = (now_mst - timedelta(days=days_since_sunday)).replace(hour=0, minute=0, second=0, microsecond=0)
    week_end_mst = week_start_mst + timedelta(days=7)
    
    # Convert back to UTC for querying
    week_start_utc = week_start_mst - MST_OFFSET
    week_end_utc = week_end_mst - MST_OFFSET
    
    events = await db.events.find({
        "claimed_by": None,
        "status": "available",
        "date": {"$gte": week_start_utc.isoformat(), "$lt": week_end_utc.isoformat()}
    }, {"_id": 0}).sort("date", 1).to_list(100)
    
    venues = await db.venues.find({}, {"_id": 0}).to_list(100)
    venue_map = {v["id"]: v["name"] for v in venues}
    result = []
    for e in events:
        if isinstance(e.get('date'), str):
            e['date'] = datetime.fromisoformat(e['date'])
        # Convert to MST for display
        event_mst = e['date'] + MST_OFFSET if e['date'].tzinfo else e['date'] + MST_OFFSET
        result.append({
            "_id": e["id"],
            "title": e["title"],
            "event_type": e["event_type"],
            "venue": venue_map.get(e["venue_id"], "Unknown"),
            "date": event_mst.strftime("%a %b %-d"),
            "time": event_mst.strftime("%-I:%M %p"),
        })
    return result

@api_router.get("/events/claim-eligibility")
async def get_claim_eligibility():
    now_iso = datetime.now(timezone.utc).isoformat()
    elig_events = await db.events.find({"date": {"$gte": now_iso}, "claimed_by": None}, {"_id": 0}).to_list(2000)
    all_roles = await db.venue_roles.find({"role_type": "primary"}, {"_id": 0}).to_list(500)
    all_blackouts = await db.blackout_dates.find({}, {"_id": 0}).to_list(1000)
    today = datetime.now(timezone.utc).date()
    result = {}
    for event in elig_events:
        rc = _map_event_type_to_category(event.get('event_type', ''))
        if not rc:
            result[event['id']] = {"status": "open"}
            continue
        pr = next((r for r in all_roles if r['venue_id'] == event['venue_id'] and r['role_category'] == rc), None)
        if not pr:
            result[event['id']] = {"status": "open"}
            continue
        pid = pr['employee_id']
        ed = event['date']
        if isinstance(ed, str):
            event_date = datetime.fromisoformat(ed)
        else:
            event_date = ed
        if event_date.tzinfo is None:
            event_date = event_date.replace(tzinfo=timezone.utc)
        eds = event_date.strftime('%Y-%m-%d')
        has_blackout = any(b['employee_id'] == pid and b['start_date'] <= eds <= b['end_date'] for b in all_blackouts)
        if has_blackout:
            result[event['id']] = {"status": "open"}
            continue
        edo = event_date.date()
        wd = edo.weekday()
        db_val = (wd + 1) % 7
        if db_val == 0:
            db_val = 7
        ps = edo - timedelta(days=db_val)
        if today > ps:
            result[event['id']] = {"status": "open"}
        else:
            result[event['id']] = {"status": "primary_only", "primary_employee_id": pid, "opens_at": (ps + timedelta(days=1)).isoformat()}
    return result

@api_router.get("/events/{event_id}")
async def get_schedule_event(event_id: str):
    event = await db.events.find_one({"id": event_id}, {"_id": 0})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    if isinstance(event.get('date'), str):
        event['date'] = datetime.fromisoformat(event['date'])
    if isinstance(event.get('created_at'), str):
        event['created_at'] = datetime.fromisoformat(event['created_at'])
    if event.get('claimed_at') and isinstance(event['claimed_at'], str):
        event['claimed_at'] = datetime.fromisoformat(event['claimed_at'])
    return event

@api_router.put("/events/{event_id}")
async def update_schedule_event(event_id: str, event: ScheduleEventUpdate):
    existing = await db.events.find_one({"id": event_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Event not found")
    update_data = event.model_dump(exclude_unset=True)
    if 'date' in update_data and update_data['date']:
        update_data['date'] = update_data['date'].isoformat()
    await db.events.update_one({"id": event_id}, {"$set": update_data})
    updated = await db.events.find_one({"id": event_id}, {"_id": 0})
    if isinstance(updated.get('date'), str):
        updated['date'] = datetime.fromisoformat(updated['date'])
    if isinstance(updated.get('created_at'), str):
        updated['created_at'] = datetime.fromisoformat(updated['created_at'])
    if updated.get('claimed_at') and isinstance(updated['claimed_at'], str):
        updated['claimed_at'] = datetime.fromisoformat(updated['claimed_at'])
    return updated

@api_router.delete("/events/{event_id}")
async def delete_schedule_event(event_id: str):
    result = await db.events.delete_one({"id": event_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Event not found")
    return {"success": True, "message": "Event deleted"}

def _map_event_type_to_category(event_type: str) -> str:
    if event_type == 'Trivia':
        return 'trivia'
    if event_type in ('Music Bingo', 'Karaoke'):
        return 'bingo_karaoke'
    return ''

async def compute_event_eligibility(event: dict) -> dict:
    rc = _map_event_type_to_category(event.get('event_type', ''))
    if not rc:
        return {"status": "open"}
    pr = await db.venue_roles.find_one({"venue_id": event['venue_id'], "role_category": rc, "role_type": "primary"}, {"_id": 0})
    if not pr:
        return {"status": "open"}
    pid = pr['employee_id']
    ed = event['date']
    if isinstance(ed, str):
        event_date = datetime.fromisoformat(ed)
    else:
        event_date = ed
    if event_date.tzinfo is None:
        event_date = event_date.replace(tzinfo=timezone.utc)
    eds = event_date.strftime('%Y-%m-%d')
    bo = await db.blackout_dates.find_one({"employee_id": pid, "start_date": {"$lte": eds}, "end_date": {"$gte": eds}})
    if bo:
        return {"status": "open"}
    edo = event_date.date()
    wd = edo.weekday()
    db_val = (wd + 1) % 7
    if db_val == 0:
        db_val = 7
    ps = edo - timedelta(days=db_val)
    if datetime.now(timezone.utc).date() > ps:
        return {"status": "open"}
    return {"status": "primary_only", "primary_employee_id": pid, "opens_at": (ps + timedelta(days=1)).isoformat()}

@api_router.post("/events/{event_id}/claim")
async def claim_schedule_event(event_id: str, claim: ClaimEvent):
    event = await db.events.find_one({"id": event_id})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    if event.get('claimed_by'):
        raise HTTPException(status_code=400, detail="Event already claimed")
    employee = await db.employees.find_one({"id": claim.employee_id})
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    eligibility = await compute_event_eligibility(event)
    if eligibility["status"] == "primary_only" and claim.employee_id != eligibility["primary_employee_id"]:
        pe = await db.employees.find_one({"id": eligibility["primary_employee_id"]}, {"_id": 0, "name": 1})
        pn = pe["name"] if pe else "the primary host"
        raise HTTPException(status_code=403, detail=f"Reserved for {pn}. Opens on {eligibility['opens_at']}.")
    await db.events.update_one({"id": event_id}, {"$set": {"claimed_by": claim.employee_id, "claimed_at": datetime.now(timezone.utc).isoformat(), "status": "claimed"}})
    return {"success": True, "message": "Event claimed successfully"}

@api_router.post("/events/{event_id}/unclaim")
async def unclaim_schedule_event(event_id: str):
    event = await db.events.find_one({"id": event_id})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    await db.events.update_one({"id": event_id}, {"$set": {"claimed_by": None, "claimed_at": None, "status": "available", "wore_big_hat": False, "social_media_posts": False, "winners_post": False}})
    return {"success": True, "message": "Event unclaimed"}

@api_router.post("/events/{event_id}/admin-assign")
async def admin_assign_event(event_id: str, assign: AdminAssign):
    event = await db.events.find_one({"id": event_id})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    employee = await db.employees.find_one({"id": assign.employee_id})
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    await db.events.update_one({"id": event_id}, {"$set": {"claimed_by": assign.employee_id, "claimed_at": datetime.now(timezone.utc).isoformat(), "status": "claimed"}})
    return {"success": True, "message": f"Host {employee.get('name')} assigned"}

@api_router.post("/events/{event_id}/bonuses")
async def update_event_bonuses(event_id: str, bonuses: UpdateBonuses):
    event = await db.events.find_one({"id": event_id})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    await db.events.update_one({"id": event_id}, {"$set": {"wore_big_hat": bonuses.wore_big_hat, "social_media_posts": bonuses.social_media_posts, "winners_post": bonuses.winners_post}})
    return {"success": True}

# =============================================
# SCHEDULE - VENUE PRICING
# =============================================

@api_router.post("/venue_pricing")
async def create_venue_pricing(pricing: VenuePricingCreate):
    venue = await db.venues.find_one({"id": pricing.venue_id})
    if not venue:
        raise HTTPException(status_code=404, detail="Venue not found")
    existing = await db.venue_pricing.find_one({"venue_id": pricing.venue_id})
    if existing:
        update_data = pricing.model_dump()
        update_data['updated_at'] = datetime.now(timezone.utc).isoformat()
        await db.venue_pricing.update_one({"venue_id": pricing.venue_id}, {"$set": update_data})
        updated = await db.venue_pricing.find_one({"venue_id": pricing.venue_id}, {"_id": 0})
        return updated
    else:
        obj = VenuePricing(**pricing.model_dump())
        doc = obj.model_dump()
        doc['created_at'] = doc['created_at'].isoformat()
        doc['updated_at'] = doc['updated_at'].isoformat()
        await db.venue_pricing.insert_one(doc)
        return doc

@api_router.get("/venue_pricing")
async def get_all_venue_pricing():
    return await db.venue_pricing.find({}, {"_id": 0}).to_list(1000)

@api_router.get("/venue_pricing/{venue_id}")
async def get_venue_pricing(venue_id: str):
    pricing = await db.venue_pricing.find_one({"venue_id": venue_id}, {"_id": 0})
    if not pricing:
        return {"venue_id": venue_id, "trivia_price": 0, "music_bingo_price": 0, "karaoke_price": 0}
    return pricing

# =============================================
# SCHEDULE - REPORTS
# =============================================

@api_router.get("/reports/weekly")
async def get_weekly_report(week_start: Optional[str] = None):
    if week_start:
        start_date = datetime.fromisoformat(week_start)
    else:
        today = datetime.now(timezone.utc)
        days_since_friday = (today.weekday() - 4) % 7
        start_date = (today - timedelta(days=days_since_friday)).replace(hour=0, minute=0, second=0, microsecond=0)
    end_date = start_date + timedelta(days=7)
    acked = await db.payment_acknowledgments.find({}, {"_id": 0, "event_id": 1}).to_list(1000)
    acked_ids = [a['event_id'] for a in acked]
    events = await db.events.find({"date": {"$gte": start_date.isoformat(), "$lt": end_date.isoformat()}, "claimed_by": {"$ne": None}, "id": {"$nin": acked_ids}}, {"_id": 0}).to_list(1000)
    items = []
    for event in events:
        emp = await db.employees.find_one({"id": event['claimed_by']}, {"_id": 0})
        venue = await db.venues.find_one({"id": event['venue_id']}, {"_id": 0})
        if emp and venue:
            vpd = venue.get('venue_pays_host_directly', False)
            if vpd:
                base_pay = 150
            elif event['event_type'] == 'Trivia':
                base_pay = 60
            elif event['event_type'] == 'Music Bingo':
                base_pay = 70
            elif event['event_type'] == 'Karaoke':
                base_pay = 25 * event.get('duration_hours', 2)
            else:
                base_pay = 0
            bonuses = 0
            bonus_details = []
            if not vpd and event['event_type'] in ['Trivia', 'Music Bingo']:
                if event.get('wore_big_hat'): bonuses += 20; bonus_details.append('BIG Hat (+$20)')
                if event.get('social_media_posts'): bonuses += 5; bonus_details.append('Social Media (+$5)')
                if event.get('winners_post'): bonuses += 5; bonus_details.append('Winners Post (+$5)')
            items.append({"event_id": event['id'], "event_title": event['title'], "employee_id": event['claimed_by'], "employee_name": emp['name'], "venue_id": venue['id'], "venue_name": venue['name'], "event_type": event['event_type'], "date": event['date'], "duration_hours": event['duration_hours'], "base_pay": base_pay, "bonuses": bonuses, "bonus_details": bonus_details, "wore_big_hat": event.get('wore_big_hat', False), "social_media_posts": event.get('social_media_posts', False), "winners_post": event.get('winners_post', False), "total_pay": base_pay + bonuses, "venue_pays_host_directly": vpd})
    return {"week_start": start_date.isoformat(), "week_end": end_date.isoformat(), "events": items}

@api_router.post("/reports/payment/acknowledge")
async def acknowledge_payment(ack: AcknowledgePayment):
    event = await db.events.find_one({"id": ack.event_id})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    await db.events.update_one({"id": ack.event_id}, {"$set": {"wore_big_hat": ack.wore_big_hat, "social_media_posts": ack.social_media_posts, "winners_post": ack.winners_post}})
    emp = await db.employees.find_one({"id": event['claimed_by']})
    venue = await db.venues.find_one({"id": event['venue_id']})
    if not emp or not venue:
        raise HTTPException(status_code=404, detail="Employee or venue not found")
    vpd = venue.get('venue_pays_host_directly', False)
    if vpd: base_pay = 150
    elif event['event_type'] == 'Trivia': base_pay = 60
    elif event['event_type'] == 'Music Bingo': base_pay = 70
    elif event['event_type'] == 'Karaoke': base_pay = 25 * event.get('duration_hours', 2)
    else: base_pay = 0
    bonuses = 0; bonus_details = []
    if not vpd and event['event_type'] in ['Trivia', 'Music Bingo']:
        if ack.wore_big_hat: bonuses += 20; bonus_details.append('BIG Hat (+$20)')
        if ack.social_media_posts: bonuses += 5; bonus_details.append('Social Media (+$5)')
        if ack.winners_post: bonuses += 5; bonus_details.append('Winners Post (+$5)')
    event_date = datetime.fromisoformat(event['date'])
    doc = PaymentAcknowledgment(event_id=event['id'], event_title=event['title'], event_type=event['event_type'], venue_id=venue['id'], venue_name=venue['name'], employee_id=emp['id'], employee_name=emp['name'], employee_email=emp.get('email', ''), event_date=event_date, base_pay=base_pay, bonuses=bonuses, bonus_details=bonus_details, wore_big_hat=ack.wore_big_hat, social_media_posts=ack.social_media_posts, winners_post=ack.winners_post, total_pay=base_pay + bonuses, venue_pays_host_directly=vpd, acknowledged_month=event_date.strftime('%Y-%m')).model_dump()
    doc['event_date'] = doc['event_date'].isoformat()
    doc['acknowledged_at'] = doc['acknowledged_at'].isoformat()
    await db.payment_acknowledgments.insert_one(doc)
    return {"success": True}

@api_router.get("/reports/payment/history")
async def get_payment_history(month: Optional[str] = None):
    query = {"acknowledged_month": month} if month else {}
    return await db.payment_acknowledgments.find(query, {"_id": 0}).sort("acknowledged_at", -1).to_list(1000)

@api_router.get("/reports/monthly/expected_income")
async def get_monthly_expected_income(month: str, venue_id: Optional[str] = None):
    year, month_num = map(int, month.split('-'))
    MST = 7
    month_start = datetime(year, month_num, 1, MST, 0, 0, tzinfo=timezone.utc)
    month_end = datetime(year + 1, 1, 1, MST, 0, 0, tzinfo=timezone.utc) if month_num == 12 else datetime(year, month_num + 1, 1, MST, 0, 0, tzinfo=timezone.utc)
    query = {"date": {"$gte": month_start.isoformat(), "$lt": month_end.isoformat()}}
    if venue_id: query["venue_id"] = venue_id
    events = await db.events.find(query, {"_id": 0}).to_list(1000)
    pricing_list = await db.venue_pricing.find({}, {"_id": 0}).to_list(1000)
    pm = {p['venue_id']: p for p in pricing_list}
    venues_list = await db.venues.find({}, {"_id": 0}).to_list(1000)
    vm = {v['id']: v for v in venues_list}
    total = 0; breakdown = []
    for ev in events:
        v = vm.get(ev['venue_id'])
        if v and v.get('venue_pays_host_directly'):
            price = 150
        else:
            vp = pm.get(ev['venue_id'])
            if not vp: continue
            price = vp.get({'Trivia': 'trivia_price', 'Music Bingo': 'music_bingo_price', 'Karaoke': 'karaoke_price'}.get(ev['event_type'], ''), 0)
        if price > 0:
            total += price
            breakdown.append({"event_id": ev['id'], "event_type": ev['event_type'], "venue_id": ev['venue_id'], "date": ev['date'], "expected_income": price, "venue_pays_host_directly": v.get('venue_pays_host_directly', False) if v else False})
    return {"month": month, "venue_id": venue_id, "total_expected_income": total, "event_count": len(breakdown), "events": breakdown}

# =============================================
# SCHEDULE - BLACKOUTS
# =============================================

@api_router.get("/blackouts")
async def get_all_blackouts():
    return await db.blackout_dates.find({}, {"_id": 0}).to_list(1000)

@api_router.get("/blackouts/employee/{employee_id}")
async def get_employee_blackouts(employee_id: str):
    return await db.blackout_dates.find({"employee_id": employee_id}, {"_id": 0}).to_list(100)

@api_router.get("/blackouts/month/{month}")
async def get_blackouts_by_month(month: str):
    year, month_num = map(int, month.split('-'))
    month_start = f"{year}-{month_num:02d}-01"
    if month_num == 12:
        next_m = f"{year + 1}-01-01"
    else:
        next_m = f"{year}-{month_num + 1:02d}-01"
    from datetime import datetime as dt
    last_day = (dt.strptime(next_m, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
    blackouts = await db.blackout_dates.find({"$and": [{"start_date": {"$lte": last_day}}, {"end_date": {"$gte": month_start}}]}, {"_id": 0}).to_list(1000)
    result = []
    for b in blackouts:
        emp = await db.employees.find_one({"id": b["employee_id"]}, {"_id": 0, "name": 1})
        result.append({**b, "employee_name": emp["name"] if emp else "Unknown"})
    return result

@api_router.post("/blackouts")
async def create_blackout(blackout: BlackoutDateCreate):
    emp = await db.employees.find_one({"id": blackout.employee_id})
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    new_bo = BlackoutDate(employee_id=blackout.employee_id, start_date=blackout.start_date, end_date=blackout.end_date)
    doc = new_bo.model_dump()
    doc['created_at'] = doc['created_at'].isoformat()
    await db.blackout_dates.insert_one(doc)
    return {k: v for k, v in doc.items() if k != '_id'}

@api_router.delete("/blackouts/{blackout_id}")
async def delete_blackout(blackout_id: str):
    result = await db.blackout_dates.delete_one({"id": blackout_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Blackout not found")
    return {"success": True}

# =============================================
# SCHEDULE - VENUE ROLES
# =============================================

@api_router.get("/venue-roles")
async def get_all_venue_roles():
    return await db.venue_roles.find({}, {"_id": 0}).to_list(1000)

@api_router.get("/venue-roles/venue/{venue_id}")
async def get_venue_roles_by_venue(venue_id: str):
    return await db.venue_roles.find({"venue_id": venue_id}, {"_id": 0}).to_list(100)

@api_router.get("/venue-roles/employee/{employee_id}")
async def get_employee_roles(employee_id: str):
    return await db.venue_roles.find({"employee_id": employee_id}, {"_id": 0}).to_list(100)

@api_router.post("/venue-roles")
async def create_venue_role(role: VenueRoleCreate):
    if role.role_category not in ("trivia", "bingo_karaoke"):
        raise HTTPException(status_code=400, detail="Invalid role_category")
    if role.role_type not in ("primary", "secondary"):
        raise HTTPException(status_code=400, detail="Invalid role_type")
    venue = await db.venues.find_one({"id": role.venue_id})
    if not venue: raise HTTPException(status_code=404, detail="Venue not found")
    emp = await db.employees.find_one({"id": role.employee_id})
    if not emp: raise HTTPException(status_code=404, detail="Employee not found")
    if role.role_type == "primary":
        ep = await db.venue_roles.find_one({"venue_id": role.venue_id, "role_category": role.role_category, "role_type": "primary"})
        if ep: raise HTTPException(status_code=400, detail="Primary already exists")
    ex = await db.venue_roles.find_one({"venue_id": role.venue_id, "employee_id": role.employee_id, "role_category": role.role_category, "role_type": role.role_type})
    if ex: raise HTTPException(status_code=400, detail="Role already exists")
    nr = VenueRole(**role.model_dump())
    doc = nr.model_dump()
    doc['created_at'] = doc['created_at'].isoformat()
    await db.venue_roles.insert_one(doc)
    return {k: v for k, v in doc.items() if k != '_id'}

@api_router.delete("/venue-roles/{role_id}")
async def delete_venue_role(role_id: str):
    result = await db.venue_roles.delete_one({"id": role_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Role not found")
    return {"success": True}

@api_router.get("/venue-roles/validate/{employee_id}")
async def validate_employee_roles(employee_id: str):
    all_roles = await db.venue_roles.find({"employee_id": employee_id}, {"_id": 0}).to_list(100)
    primary_roles = [r for r in all_roles if r["role_type"] == "primary"]
    if not primary_roles:
        return {"valid": True, "needs_secondary": False}
    pvids = set(r["venue_id"] for r in primary_roles)
    svids = set(r["venue_id"] for r in all_roles if r["role_type"] == "secondary") - pvids
    return {"valid": bool(svids), "needs_secondary": not bool(svids), "primary_venue_ids": list(pvids)}

@api_router.get("/venue-roles/services")
async def get_venue_services():
    all_pricing = await db.venue_pricing.find({}, {"_id": 0}).to_list(1000)
    all_venues = await db.venues.find({}, {"_id": 0}).to_list(1000)
    vm = {v['id']: v['name'] for v in all_venues}
    services = {}
    for p in all_pricing:
        vid = p['venue_id']
        vn = vm.get(vid)
        if not vn: continue
        ot = p.get('trivia_price', 0) > 0
        obk = p.get('music_bingo_price', 0) > 0 or p.get('karaoke_price', 0) > 0
        if ot or obk:
            services[vid] = {"venue_id": vid, "venue_name": vn, "offers_trivia": ot, "offers_bingo_karaoke": obk}
    return services


# =============================================
# HEALTH & MISC
# =============================================

@api_router.get("/")
async def root():
    return {"message": "BIG Hat Hub API", "status": "running"}

@api_router.get("/health")
async def health_check():
    try:
        await db.command("ping")
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        return {"status": "unhealthy", "database": str(e)}

@api_router.get("/changelog")
async def get_changelog(user: dict = Depends(get_current_user)):
    logs = await db.changelog.find({}).sort("timestamp", -1).to_list(100)
    for l in logs:
        l["_id"] = str(l["_id"])
    return logs

# Include trivia presenter routes (independent - no proxy)
try:
    from routes import presentations as trivia_presentations_routes
    from routes import trivia as trivia_routes
    from routes import trivia_viewer as trivia_viewer_routes
    from routes import trivia_import as trivia_import_routes
    from routes import admin as trivia_admin_routes
    from routes import overlays as trivia_overlays_routes
    from routes import rounds as trivia_rounds_routes
    from routes import slide_fetcher as trivia_slide_fetcher_routes
    from routes import story_builds as trivia_story_builds_routes
    from routes import scores as trivia_scores_routes
    
    # Set database for all trivia route modules
    for module in [trivia_presentations_routes, trivia_routes, trivia_viewer_routes, 
                   trivia_import_routes, trivia_admin_routes, trivia_overlays_routes,
                   trivia_rounds_routes, trivia_slide_fetcher_routes, trivia_scores_routes]:
        if hasattr(module, 'set_database'):
            module.set_database(db)
    
    # Mount all trivia routers on the /api prefix
    api_router.include_router(trivia_presentations_routes.router)
    api_router.include_router(trivia_routes.router)
    api_router.include_router(trivia_viewer_routes.router)
    api_router.include_router(trivia_import_routes.router)
    api_router.include_router(trivia_admin_routes.router)
    api_router.include_router(trivia_overlays_routes.router)
    api_router.include_router(trivia_rounds_routes.router)
    api_router.include_router(trivia_slide_fetcher_routes.router)
    api_router.include_router(trivia_story_builds_routes.router)
    api_router.include_router(trivia_scores_routes.router)
    
    # Try to load story generator too
    try:
        from routes import story_generator as trivia_story_gen_routes
        if hasattr(trivia_story_gen_routes, 'set_database'):
            trivia_story_gen_routes.set_database(db)
        api_router.include_router(trivia_story_gen_routes.router)
    except Exception as e:
        logger.warning(f"Story generator routes not loaded: {e}")
    
    logger.info("Trivia presenter routes mounted successfully (independent mode)")
except Exception as e:
    logger.warning(f"Could not load trivia presenter routes: {e}")

# Mount Round Generator routes
try:
    from routes import roundmaker as roundmaker_routes
    if hasattr(roundmaker_routes, 'set_database'):
        roundmaker_routes.set_database(db)
    api_router.include_router(roundmaker_routes.router)
    logger.info("Round Generator routes mounted successfully")
except Exception as e:
    logger.warning(f"Could not load Round Generator routes: {e}")

# Mount Bingo routes
try:
    from routes import bingo as bingo_routes
    if hasattr(bingo_routes, 'set_database'):
        bingo_routes.set_database(db)
    api_router.include_router(bingo_routes.router)
    logger.info("Bingo routes mounted successfully")
except Exception as e:
    logger.warning(f"Could not load Bingo routes: {e}")

# Mount Scoreboard routes
try:
    from routes import scoreboard as scoreboard_routes
    if hasattr(scoreboard_routes, 'set_database'):
        scoreboard_routes.set_database(db)
    api_router.include_router(scoreboard_routes.router)
    logger.info("Scoreboard routes mounted successfully")
except Exception as e:
    logger.warning(f"Could not load Scoreboard routes: {e}")

# Include router
app.include_router(api_router)


# Bingo WebSocket endpoint (must be on app level, not sub-router)
try:
    from routes.bingo import manager as bingo_manager
    from fastapi import WebSocket, WebSocketDisconnect
    
    @app.websocket("/api/bingo/ws/game")
    async def bingo_websocket(websocket: WebSocket):
        await bingo_manager.connect(websocket)
        try:
            while True:
                data = await websocket.receive_json()
                if data.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
        except WebSocketDisconnect:
            bingo_manager.disconnect(websocket)
        except Exception:
            bingo_manager.disconnect(websocket)
    
    logger.info("Bingo WebSocket endpoint registered at /api/bingo/ws/game")
except Exception as e:
    logger.warning(f"Could not register Bingo WebSocket: {e}")


@app.get("/health")
async def root_health():
    return {"status": "healthy"}
