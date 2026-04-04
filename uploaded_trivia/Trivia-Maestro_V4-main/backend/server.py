from fastapi import FastAPI, APIRouter
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
import gc
from pathlib import Path
from contextlib import asynccontextmanager

from routes import presentations, trivia, trivia_viewer, trivia_import, admin, overlays, rounds, slide_fetcher, story_generator, story_builds, scores
from gridfs_service import init_gridfs_service

ROOT_DIR = Path(__file__).parent
# Load .env file (Kubernetes environment variables take precedence)
load_dotenv(ROOT_DIR / '.env', override=False)

# MongoDB connection - read from environment
mongo_url = os.environ['MONGO_URL']
db_name = os.environ['DB_NAME']

print("========================================")
print(f"STARTUP: MONGO_URL = {mongo_url}")
print(f"STARTUP: DB_NAME = {db_name}")
print("========================================")

# OPTIMIZATION: Configure MongoDB connection pool for production
# Limit connections to prevent resource exhaustion
client = AsyncIOMotorClient(
    mongo_url,
    maxPoolSize=10,          # Max connections in pool (default 100 is too high)
    minPoolSize=1,           # Min connections to maintain
    maxIdleTimeMS=30000,     # Close idle connections after 30s
    serverSelectionTimeoutMS=5000,  # Fail fast if can't connect
    connectTimeoutMS=5000,   # Connection timeout
    socketTimeoutMS=30000,   # Socket timeout for operations
)
db = client[db_name]

# Initialize GridFS service for large slide storage
gridfs = init_gridfs_service(db)

# OPTIMIZATION: Lifespan context manager for startup/shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("🚀 Starting up - initializing resources")
    yield
    # Shutdown
    logger.info("🛑 Shutting down - cleaning up resources")
    client.close()
    gc.collect()  # Force garbage collection on shutdown

# Create the main app with lifespan
app = FastAPI(lifespan=lifespan)

# Health check endpoint for Kubernetes (must be at root level, not under /api)
@app.get("/health")
async def health_check():
    """Health check endpoint for Kubernetes liveness/readiness probes"""
    try:
        # OPTIMIZATION: Quick database ping to verify connection
        await db.command('ping')
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {"status": "degraded", "database": "disconnected", "error": str(e)}

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# Set database for routers
presentations.set_database(db)
trivia.set_database(db)
trivia_viewer.set_database(db)
trivia_import.set_database(db)
admin.set_database(db)
overlays.set_database(db)
rounds.set_database(db)
slide_fetcher.set_database(db)
story_generator.set_database(db)

# Add routes to the API router
@api_router.get("/")
async def root():
    return {"message": "BIG Hat Presenter API"}

# Include routers
api_router.include_router(presentations.router)
api_router.include_router(trivia.router)
api_router.include_router(trivia_viewer.router)
api_router.include_router(trivia_import.router)
api_router.include_router(admin.router)
api_router.include_router(overlays.router)
api_router.include_router(rounds.router)
api_router.include_router(slide_fetcher.router)
api_router.include_router(story_generator.router)
api_router.include_router(story_builds.router)
api_router.include_router(scores.router)

# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# OPTIMIZATION: Periodic garbage collection endpoint for manual trigger if needed
@app.post("/api/admin/gc")
async def trigger_gc():
    """Manually trigger garbage collection - use sparingly"""
    collected = gc.collect()
    return {"collected_objects": collected}
