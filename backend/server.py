from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, Depends
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
import os
import logging
import bcrypt
import jwt
import secrets
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional
import uuid
from datetime import datetime, timezone, timedelta

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# JWT config
JWT_ALGORITHM = "HS256"

def get_jwt_secret():
    return os.environ["JWT_SECRET"]

# Password utilities
def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))

# Token utilities
def create_access_token(user_id: str, email: str, role: str) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(hours=24),
        "type": "access"
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)

def create_refresh_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "exp": datetime.now(timezone.utc) + timedelta(days=7),
        "type": "refresh"
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)

# Auth dependency
async def get_current_user(request: Request) -> dict:
    token = request.cookies.get("access_token")
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, get_jwt_secret(), algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token type")
        user = await db.users.find_one({"_id": ObjectId(payload["sub"])})
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        user["_id"] = str(user["_id"])
        user.pop("password_hash", None)
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

async def require_admin(request: Request) -> dict:
    user = await get_current_user(request)
    if user.get("role") not in ["admin", "master_admin"]:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user

async def require_master_admin(request: Request) -> dict:
    user = await get_current_user(request)
    if user.get("role") != "master_admin":
        raise HTTPException(status_code=403, detail="Master admin access required")
    return user

# Pydantic models
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

class EventCreate(BaseModel):
    title: str
    event_type: str  # trivia, bingo, karaoke
    date: str
    time: str
    venue: str
    description: Optional[str] = ""
    host_id: Optional[str] = None

class EventUpdate(BaseModel):
    title: Optional[str] = None
    event_type: Optional[str] = None
    date: Optional[str] = None
    time: Optional[str] = None
    venue: Optional[str] = None
    description: Optional[str] = None
    host_id: Optional[str] = None
    status: Optional[str] = None

# Create app
app = FastAPI()
api_router = APIRouter(prefix="/api")

# ---- AUTH ROUTES ----

@api_router.post("/auth/login")
async def login(request: Request, response: Response, body: LoginRequest):
    email = body.email.lower().strip()
    ip = request.client.host if request.client else "unknown"
    identifier = f"{ip}:{email}"
    
    # Brute force check
    attempt = await db.login_attempts.find_one({"identifier": identifier})
    if attempt and attempt.get("count", 0) >= 5:
        lockout_until = attempt.get("locked_until")
        if lockout_until and datetime.now(timezone.utc) < lockout_until:
            raise HTTPException(status_code=429, detail="Too many failed attempts. Try again in 15 minutes.")
        else:
            await db.login_attempts.delete_one({"identifier": identifier})

    user = await db.users.find_one({"email": email})
    if not user or not verify_password(body.password, user["password_hash"]):
        # Increment failed attempts
        await db.login_attempts.update_one(
            {"identifier": identifier},
            {
                "$inc": {"count": 1},
                "$set": {"locked_until": datetime.now(timezone.utc) + timedelta(minutes=15)}
            },
            upsert=True
        )
        logger.warning(f"Failed login attempt for {email} from {ip}")
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    # Clear failed attempts
    await db.login_attempts.delete_many({"identifier": identifier})
    
    user_id = str(user["_id"])
    access_token = create_access_token(user_id, email, user.get("role", "host"))
    refresh_token = create_refresh_token(user_id)
    
    response.set_cookie(key="access_token", value=access_token, httponly=True, secure=False, samesite="lax", max_age=86400, path="/")
    response.set_cookie(key="refresh_token", value=refresh_token, httponly=True, secure=False, samesite="lax", max_age=604800, path="/")
    
    logger.info(f"User {email} logged in successfully")
    return {
        "id": user_id,
        "email": user["email"],
        "name": user.get("name", ""),
        "role": user.get("role", "host"),
        "token": access_token
    }

@api_router.post("/auth/register")
async def register(response: Response, body: RegisterRequest, admin: dict = Depends(require_admin)):
    email = body.email.lower().strip()
    existing = await db.users.find_one({"email": email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Only master_admin can create admin users
    if body.role in ["admin", "master_admin"] and admin.get("role") != "master_admin":
        raise HTTPException(status_code=403, detail="Only master admin can create admin users")
    
    password_hash = hash_password(body.password)
    user_doc = {
        "email": email,
        "password_hash": password_hash,
        "name": body.name,
        "role": body.role,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": admin.get("_id", "system")
    }
    result = await db.users.insert_one(user_doc)
    logger.info(f"User {email} registered by admin {admin.get('email')}")
    return {
        "id": str(result.inserted_id),
        "email": email,
        "name": body.name,
        "role": body.role
    }

@api_router.post("/auth/logout")
async def logout(response: Response):
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")
    return {"message": "Logged out"}

@api_router.get("/auth/me")
async def get_me(user: dict = Depends(get_current_user)):
    return {
        "id": user["_id"],
        "email": user["email"],
        "name": user.get("name", ""),
        "role": user.get("role", "host")
    }

@api_router.post("/auth/refresh")
async def refresh_token(request: Request, response: Response):
    token = request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(status_code=401, detail="No refresh token")
    try:
        payload = jwt.decode(token, get_jwt_secret(), algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")
        user = await db.users.find_one({"_id": ObjectId(payload["sub"])})
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        user_id = str(user["_id"])
        access_token = create_access_token(user_id, user["email"], user.get("role", "host"))
        response.set_cookie(key="access_token", value=access_token, httponly=True, secure=False, samesite="lax", max_age=86400, path="/")
        return {"message": "Token refreshed", "token": access_token}
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Refresh token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

# ---- USER MANAGEMENT (Admin) ----

@api_router.get("/users")
async def list_users(admin: dict = Depends(require_admin)):
    users = await db.users.find({}, {"password_hash": 0}).to_list(1000)
    for u in users:
        u["_id"] = str(u["_id"])
    return users

@api_router.get("/users/{user_id}")
async def get_user(user_id: str, admin: dict = Depends(require_admin)):
    user = await db.users.find_one({"_id": ObjectId(user_id)}, {"password_hash": 0})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user["_id"] = str(user["_id"])
    return user

@api_router.put("/users/{user_id}")
async def update_user(user_id: str, body: UserUpdate, admin: dict = Depends(require_admin)):
    target = await db.users.find_one({"_id": ObjectId(user_id)})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Protect master admin from being modified by non-master admins
    if target.get("role") == "master_admin" and admin.get("role") != "master_admin":
        raise HTTPException(status_code=403, detail="Cannot modify master admin")
    
    update_data = {}
    if body.name is not None:
        update_data["name"] = body.name
    if body.email is not None:
        update_data["email"] = body.email.lower().strip()
    if body.role is not None:
        if body.role in ["admin", "master_admin"] and admin.get("role") != "master_admin":
            raise HTTPException(status_code=403, detail="Only master admin can assign admin roles")
        update_data["role"] = body.role
    if body.password is not None:
        update_data["password_hash"] = hash_password(body.password)
    
    if update_data:
        await db.users.update_one({"_id": ObjectId(user_id)}, {"$set": update_data})
    
    updated = await db.users.find_one({"_id": ObjectId(user_id)}, {"password_hash": 0})
    updated["_id"] = str(updated["_id"])
    logger.info(f"User {user_id} updated by admin {admin.get('email')}")
    return updated

@api_router.delete("/users/{user_id}")
async def delete_user(user_id: str, admin: dict = Depends(require_admin)):
    target = await db.users.find_one({"_id": ObjectId(user_id)})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target.get("role") == "master_admin":
        raise HTTPException(status_code=403, detail="Cannot delete master admin")
    if str(target["_id"]) == admin.get("_id"):
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    
    await db.users.delete_one({"_id": ObjectId(user_id)})
    logger.info(f"User {user_id} deleted by admin {admin.get('email')}")
    return {"message": "User deleted"}

# ---- EVENTS / SCHEDULE ----

@api_router.post("/events")
async def create_event(body: EventCreate, user: dict = Depends(get_current_user)):
    # Only admin can create events, or host creating for themselves
    if user.get("role") not in ["admin", "master_admin"] and body.host_id and body.host_id != user["_id"]:
        raise HTTPException(status_code=403, detail="Cannot assign events to other hosts")
    
    event_doc = {
        "title": body.title,
        "event_type": body.event_type,
        "date": body.date,
        "time": body.time,
        "venue": body.venue,
        "description": body.description or "",
        "host_id": body.host_id or None,
        "claimed": bool(body.host_id),
        "status": "upcoming",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": user["_id"]
    }
    result = await db.events.insert_one(event_doc)
    event_doc["_id"] = str(result.inserted_id)
    logger.info(f"Event '{body.title}' created by {user.get('email')}")
    return event_doc

@api_router.get("/events")
async def list_events(user: dict = Depends(get_current_user)):
    events = await db.events.find({}).sort("date", 1).to_list(1000)
    for e in events:
        e["_id"] = str(e["_id"])
    return events

@api_router.get("/events/unclaimed")
async def get_unclaimed_events(user: dict = Depends(get_current_user)):
    events = await db.events.find({"claimed": False, "status": "upcoming"}).sort("date", 1).to_list(100)
    for e in events:
        e["_id"] = str(e["_id"])
    return events

@api_router.put("/events/{event_id}")
async def update_event(event_id: str, body: EventUpdate, user: dict = Depends(get_current_user)):
    event = await db.events.find_one({"_id": ObjectId(event_id)})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    
    update_data = {}
    for field in ["title", "event_type", "date", "time", "venue", "description", "host_id", "status"]:
        val = getattr(body, field, None)
        if val is not None:
            update_data[field] = val
    
    if "host_id" in update_data:
        update_data["claimed"] = bool(update_data["host_id"])
    
    if update_data:
        await db.events.update_one({"_id": ObjectId(event_id)}, {"$set": update_data})
    
    updated = await db.events.find_one({"_id": ObjectId(event_id)})
    updated["_id"] = str(updated["_id"])
    return updated

@api_router.post("/events/{event_id}/claim")
async def claim_event(event_id: str, user: dict = Depends(get_current_user)):
    event = await db.events.find_one({"_id": ObjectId(event_id)})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    if event.get("claimed"):
        raise HTTPException(status_code=400, detail="Event already claimed")
    
    await db.events.update_one(
        {"_id": ObjectId(event_id)},
        {"$set": {"host_id": user["_id"], "claimed": True}}
    )
    logger.info(f"Event {event_id} claimed by {user.get('email')}")
    return {"message": "Event claimed"}

@api_router.delete("/events/{event_id}")
async def delete_event(event_id: str, admin: dict = Depends(require_admin)):
    result = await db.events.delete_one({"_id": ObjectId(event_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Event not found")
    return {"message": "Event deleted"}

# ---- CHANGELOG / ERROR LOG ----

@api_router.get("/changelog")
async def get_changelog(user: dict = Depends(get_current_user)):
    logs = await db.changelog.find({}).sort("timestamp", -1).to_list(100)
    for l in logs:
        l["_id"] = str(l["_id"])
    return logs

@api_router.get("/errors")
async def get_error_logs(admin: dict = Depends(require_admin)):
    logs = await db.error_logs.find({}).sort("timestamp", -1).to_list(100)
    for l in logs:
        l["_id"] = str(l["_id"])
    return logs

# ---- HEALTH ----

@api_router.get("/")
async def root():
    return {"message": "BIG Hat Hub API", "status": "running"}

@api_router.get("/health")
async def health_check():
    try:
        await db.command("ping")
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {"status": "unhealthy", "database": str(e)}

# Include router
app.include_router(api_router)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Startup event - seed admin and create indexes
@app.on_event("startup")
async def startup():
    logger.info("Starting BIG Hat Hub API...")
    
    # Create indexes
    await db.users.create_index("email", unique=True)
    await db.login_attempts.create_index("identifier")
    await db.events.create_index("date")
    await db.events.create_index("claimed")
    
    # Seed master admin
    admin_email = os.environ.get("ADMIN_EMAIL", "admin@example.com").lower().strip()
    admin_password = os.environ.get("ADMIN_PASSWORD", "admin123")
    
    existing = await db.users.find_one({"email": admin_email})
    if existing is None:
        hashed = hash_password(admin_password)
        await db.users.insert_one({
            "email": admin_email,
            "password_hash": hashed,
            "name": "Nick Sellards",
            "role": "master_admin",
            "created_at": datetime.now(timezone.utc).isoformat()
        })
        logger.info(f"Master admin seeded: {admin_email}")
    elif not verify_password(admin_password, existing["password_hash"]):
        await db.users.update_one(
            {"email": admin_email},
            {"$set": {"password_hash": hash_password(admin_password)}}
        )
        logger.info(f"Master admin password updated: {admin_email}")
    
    # Seed sample events
    event_count = await db.events.count_documents({})
    if event_count == 0:
        sample_events = [
            {"title": "Tuesday Trivia Night", "event_type": "trivia", "date": "2026-01-20", "time": "7:00 PM", "venue": "The Tap House", "description": "Weekly trivia showdown", "host_id": None, "claimed": False, "status": "upcoming", "created_at": datetime.now(timezone.utc).isoformat(), "created_by": "system"},
            {"title": "Wednesday Bingo Bash", "event_type": "bingo", "date": "2026-01-21", "time": "8:00 PM", "venue": "Rusty Nail Bar", "description": "Music bingo with prizes", "host_id": None, "claimed": False, "status": "upcoming", "created_at": datetime.now(timezone.utc).isoformat(), "created_by": "system"},
            {"title": "Thursday Trivia", "event_type": "trivia", "date": "2026-01-22", "time": "7:30 PM", "venue": "Desert Ridge Tavern", "description": "General knowledge trivia", "host_id": None, "claimed": False, "status": "upcoming", "created_at": datetime.now(timezone.utc).isoformat(), "created_by": "system"},
            {"title": "Friday Night Karaoke", "event_type": "karaoke", "date": "2026-01-23", "time": "9:00 PM", "venue": "Cactus Jack's", "description": "Karaoke night", "host_id": None, "claimed": False, "status": "upcoming", "created_at": datetime.now(timezone.utc).isoformat(), "created_by": "system"},
            {"title": "Saturday Bingo Bonanza", "event_type": "bingo", "date": "2026-01-24", "time": "6:00 PM", "venue": "The Pint House", "description": "Special prize bingo night", "host_id": None, "claimed": False, "status": "upcoming", "created_at": datetime.now(timezone.utc).isoformat(), "created_by": "system"},
            {"title": "Sunday Funday Trivia", "event_type": "trivia", "date": "2026-01-25", "time": "4:00 PM", "venue": "Copper Blues", "description": "Casual Sunday trivia", "host_id": None, "claimed": False, "status": "upcoming", "created_at": datetime.now(timezone.utc).isoformat(), "created_by": "system"},
        ]
        await db.events.insert_many(sample_events)
        logger.info("Sample events seeded")
    
    # Log changelog entry
    await db.changelog.insert_one({
        "version": "1.0.0",
        "message": "BIG Hat Hub launched - SSO platform for hosts",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "type": "release"
    })
    
    logger.info("BIG Hat Hub API started successfully")

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
