from fastapi import FastAPI, APIRouter
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path

from routes import presentations, trivia, trivia_viewer, trivia_import, admin, overlays, rounds, slide_fetcher, story_generator
from gridfs_service import init_gridfs_service

ROOT_DIR = Path(__file__).parent
# Load .env file (Kubernetes environment variables take precedence)
load_dotenv(ROOT_DIR / '.env', override=False)

# MongoDB connection - read from environment
mongo_url = os.environ['MONGO_URL']
db_name = os.environ['DB_NAME']

print(f"========================================")
print(f"STARTUP: MONGO_URL = {mongo_url}")
print(f"STARTUP: DB_NAME = {db_name}")
print(f"========================================")

client = AsyncIOMotorClient(mongo_url)
db = client[db_name]

# Initialize GridFS service for large slide storage
gridfs = init_gridfs_service(db)

# Create the main app without a prefix
app = FastAPI()

# Health check endpoint for Kubernetes (must be at root level, not under /api)
@app.get("/health")
async def health_check():
    """Health check endpoint for Kubernetes liveness/readiness probes"""
    return {"status": "healthy"}

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

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
