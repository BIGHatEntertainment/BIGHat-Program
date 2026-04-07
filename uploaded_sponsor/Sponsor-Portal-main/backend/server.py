from fastapi import FastAPI, APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
import os
import logging
import asyncio
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List
import uuid
from datetime import datetime, timezone

# Rate limiting
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# Import shared database
from database import db, client

# Import routers
from routes.auth import router as auth_router
from routes.sponsors import router as sponsors_router
from routes.locations import router as locations_router
from routes.assets import router as assets_router
from routes.subscriptions import router as subscriptions_router
from routes.accounts import router as accounts_router
from routes.profile import router as profile_router
from routes.canva import router as canva_router
from routes.placements import router as placements_router
from routes.sharepoint import router as sharepoint_router
from routes.payments import router as payments_router
from routes.webhooks import router as webhooks_router
from routes.account_deletion import router as account_deletion_router

# Import scheduler
from scheduler import start_scheduler, stop_scheduler


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# Configure logging first
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============ RATE LIMITING ============
# Initialize rate limiter with IP-based limiting
limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])


# ============ REQUEST TIMEOUT MIDDLEWARE ============
class TimeoutMiddleware(BaseHTTPMiddleware):
    """Middleware to add request timeouts - prevents long-running requests from blocking"""
    
    def __init__(self, app, timeout: int = 30):
        super().__init__(app)
        self.timeout = timeout
    
    async def dispatch(self, request: Request, call_next):
        try:
            # Set a timeout for the request
            response = await asyncio.wait_for(
                call_next(request),
                timeout=self.timeout
            )
            return response
        except asyncio.TimeoutError:
            logger.warning(f"Request timeout: {request.method} {request.url.path}")
            return JSONResponse(
                status_code=504,
                content={"detail": "Request timeout - please try again"}
            )


# Lifespan context manager for startup/shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting BIG Hat Sponsor Portal API...")
    logger.info("Initializing scheduler...")
    start_scheduler()
    
    # Test database connection
    try:
        await db.command("ping")
        logger.info("✅ MongoDB connection successful")
    except Exception as e:
        logger.error(f"❌ MongoDB connection failed: {e}")
    
    yield
    
    # Shutdown
    logger.info("Shutting down...")
    stop_scheduler()
    client.close()
    logger.info("Shutdown complete")


# Create the main app with lifespan
app = FastAPI(
    lifespan=lifespan,
    title="BIG Hat Sponsor Portal API",
    description="API for BIG Hat Entertainment Sponsor Portal",
    version="1.0.0"
)

# Add rate limiter to the app state
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Add timeout middleware (30 second timeout for most requests)
app.add_middleware(TimeoutMiddleware, timeout=30)

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")


# Define Models
class StatusCheck(BaseModel):
    model_config = ConfigDict(extra="ignore")  # Ignore MongoDB's _id field
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    client_name: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class StatusCheckCreate(BaseModel):
    client_name: str


# ============ HEALTH CHECK ENDPOINT ============
@api_router.get("/health")
async def health_check():
    """
    Health check endpoint for load balancers and monitoring.
    Returns the status of the API and database connection.
    """
    health_status = {
        "status": "healthy",
        "api": "up",
        "database": "unknown",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    try:
        # Check database connection
        await asyncio.wait_for(db.command("ping"), timeout=5.0)
        health_status["database"] = "connected"
    except asyncio.TimeoutError:
        health_status["status"] = "degraded"
        health_status["database"] = "timeout"
    except Exception as e:
        health_status["status"] = "degraded"
        health_status["database"] = f"error: {str(e)}"
    
    return health_status


# Add your routes to the router instead of directly to app
@api_router.get("/")
async def root():
    return {"message": "Hello World"}

@api_router.post("/status", response_model=StatusCheck)
async def create_status_check(input: StatusCheckCreate):
    status_dict = input.model_dump()
    status_obj = StatusCheck(**status_dict)
    
    # Convert to dict and serialize datetime to ISO string for MongoDB
    doc = status_obj.model_dump()
    doc['timestamp'] = doc['timestamp'].isoformat()
    
    _ = await db.status_checks.insert_one(doc)
    return status_obj

@api_router.get("/status", response_model=List[StatusCheck])
async def get_status_checks():
    # Exclude MongoDB's _id field from the query results
    status_checks = await db.status_checks.find({}, {"_id": 0}).to_list(1000)
    
    # Convert ISO string timestamps back to datetime objects
    for check in status_checks:
        if isinstance(check['timestamp'], str):
            check['timestamp'] = datetime.fromisoformat(check['timestamp'])
    
    return status_checks


# Seed data endpoint - initializes database with default data if empty
@api_router.post("/init")
async def initialize_database():
    """Initialize the database with default mock data if empty"""
    
    # Check if locations already exist
    locations_count = await db.locations.count_documents({})
    sponsors_count = await db.sponsors.count_documents({})
    
    results = {"locations_created": 0, "sponsors_created": 0}
    
    if locations_count == 0:
        # Seed locations
        default_locations = [
            {"id": "loc_1", "name": "Monkey Pants", "address": "100 E Camelback Rd", "city": "Phoenix", "state": "AZ", "zip_code": "85012", "avg_attendance": 75, "status": "active"},
            {"id": "loc_2", "name": "The Casual Pint", "address": "4727 E Bell Rd", "city": "Phoenix", "state": "AZ", "zip_code": "85032", "avg_attendance": 60, "status": "active"},
            {"id": "loc_3", "name": "Handlebar Pub", "address": "7116 E Becker Ln", "city": "Scottsdale", "state": "AZ", "zip_code": "85254", "avg_attendance": 50, "status": "active"},
            {"id": "loc_4", "name": "Four Peaks Brewing", "address": "1340 E 8th St #104", "city": "Tempe", "state": "AZ", "zip_code": "85281", "avg_attendance": 90, "status": "active"},
            {"id": "loc_5", "name": "SunUp Brewing", "address": "322 E Camelback Rd", "city": "Phoenix", "state": "AZ", "zip_code": "85012", "avg_attendance": 65, "status": "active"},
            {"id": "loc_6", "name": "O.H.S.O. Brewery", "address": "4900 E Indian School Rd", "city": "Phoenix", "state": "AZ", "zip_code": "85018", "avg_attendance": 80, "status": "active"},
        ]
        await db.locations.insert_many(default_locations)
        results["locations_created"] = len(default_locations)
    
    if sponsors_count == 0:
        # Seed sponsors
        default_sponsors = [
            {"id": "user_123", "business_name": "Phoenix Coffee Co.", "email": "sponsor@business.com", "contact_name": "Phoenix Owner", "phone": "(602) 555-8511", "website": "https://phoenixcoffeeco.com", "package": "Gold Sponsor", "status": "active", "assets_count": 3, "joined_at": "2025-01-15", "is_venue_sponsor": False, "notes": ""},
            {"id": "user_124", "business_name": "Desert Auto Repair", "email": "info@desertauto.com", "contact_name": "Desert Owner", "phone": "(602) 555-1136", "website": "https://desertauto.com", "package": "Silver Sponsor", "status": "active", "assets_count": 1, "joined_at": "2025-03-20", "is_venue_sponsor": False, "notes": ""},
            {"id": "user_125", "business_name": "Mesa Fitness Center", "email": "contact@mesafitness.com", "contact_name": "Mesa Owner", "phone": "(602) 555-4422", "website": "https://mesafitness.com", "package": "Bronze Sponsor", "status": "active", "assets_count": 2, "joined_at": "2025-02-10", "is_venue_sponsor": False, "notes": ""},
        ]
        await db.sponsors.insert_many(default_sponsors)
        results["sponsors_created"] = len(default_sponsors)
    
    return {"message": "Database initialized", **results}

# Include the router in the main app
app.include_router(api_router)

# Include all routers with /api prefix
app.include_router(auth_router, prefix="/api")
app.include_router(sponsors_router, prefix="/api")
app.include_router(locations_router, prefix="/api")
app.include_router(assets_router, prefix="/api")
app.include_router(subscriptions_router, prefix="/api")
app.include_router(accounts_router, prefix="/api")
app.include_router(profile_router, prefix="/api")
app.include_router(canva_router, prefix="/api")
app.include_router(placements_router, prefix="/api")
app.include_router(sharepoint_router, prefix="/api")
app.include_router(payments_router, prefix="/api")
app.include_router(webhooks_router, prefix="/api")
app.include_router(account_deletion_router, prefix="/api")

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Note: Shutdown handled by lifespan context manager