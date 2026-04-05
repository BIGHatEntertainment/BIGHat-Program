from fastapi import FastAPI, APIRouter, HTTPException, Body, UploadFile, File
from fastapi.responses import FileResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime, timezone
import json

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ.get('DB_NAME', 'trivia_scoreboard')]

# Create the main app
app = FastAPI(title="BIG Hat Trivia Scoreboard API")

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ===================== MODELS =====================

def serialize_doc(doc):
    """Convert MongoDB doc to JSON-safe dict"""
    if doc is None:
        return None
    if '_id' in doc:
        doc['_id'] = str(doc['_id'])
    for key, val in doc.items():
        if isinstance(val, datetime):
            doc[key] = val.isoformat()
        elif isinstance(val, dict):
            doc[key] = serialize_doc(val)
        elif isinstance(val, list):
            doc[key] = [serialize_doc(v) if isinstance(v, dict) else v for v in val]
    return doc


class PresetCreate(BaseModel):
    name: str
    mode: str  # "leaderboard" or "tournament"
    aspect_ratio: str  # "portrait" or "landscape"
    animation_speed: float = 1.0
    config: Dict[str, Any] = {}


class TournamentCreate(BaseModel):
    name: str
    total_teams: int = 12
    bye_count: int = 4
    teams: List[Dict[str, Any]] = []
    bracket_state: Dict[str, Any] = {}


class TournamentUpdate(BaseModel):
    name: Optional[str] = None
    teams: Optional[List[Dict[str, Any]]] = None
    bracket_state: Optional[Dict[str, Any]] = None


# ===================== SHAREPOINT ROUTES =====================

@api_router.get("/")
async def root():
    return {"message": "BIG Hat Trivia Scoreboard API", "status": "active"}


@api_router.get("/sharepoint/files")
async def get_sharepoint_files():
    """Fetch all score files from SharePoint"""
    from sharepoint_service import get_all_score_files
    sharing_url = os.environ.get("SHAREPOINT_SHARING_URL")
    if not sharing_url:
        raise HTTPException(status_code=500, detail="SharePoint URL not configured")
    try:
        files = await get_all_score_files(sharing_url)
        return {"files": files, "count": len(files)}
    except Exception as e:
        logger.error(f"SharePoint sync error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/sharepoint/sync")
async def sync_sharepoint_data():
    """Sync SharePoint data into MongoDB"""
    from sharepoint_service import get_all_score_files
    sharing_url = os.environ.get("SHAREPOINT_SHARING_URL")
    if not sharing_url:
        raise HTTPException(status_code=500, detail="SharePoint URL not configured")
    try:
        files = await get_all_score_files(sharing_url)

        # Store each file's data in MongoDB
        synced = []
        for f in files:
            doc = {
                "file_name": f["file_name"],
                "venue": f["venue"],
                "last_modified": f["last_modified"],
                "synced_at": datetime.now(timezone.utc).isoformat(),
                "data": f["data"]
            }
            # Upsert by file_name
            await db.score_files.update_one(
                {"file_name": f["file_name"]},
                {"$set": doc},
                upsert=True
            )
            synced.append(f["file_name"])

        return {"synced": synced, "count": len(synced)}
    except Exception as e:
        logger.error(f"SharePoint sync error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/scores")
async def get_scores():
    """Get all synced score files from MongoDB"""
    docs = await db.score_files.find({}, {"_id": 0}).to_list(1000)
    return {"files": docs, "count": len(docs)}


@api_router.get("/scores/{venue}")
async def get_venue_scores(venue: str):
    """Get scores for a specific venue"""
    docs = await db.score_files.find(
        {"venue": {"$regex": venue, "$options": "i"}},
        {"_id": 0}
    ).sort("data.date", -1).to_list(100)
    return {"files": docs, "count": len(docs)}


# ===================== PRESET ROUTES =====================

@api_router.post("/presets")
async def create_preset(preset: PresetCreate):
    """Save an animation preset"""
    doc = preset.model_dump()
    doc["id"] = str(uuid.uuid4())
    doc["created_at"] = datetime.now(timezone.utc).isoformat()
    doc["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.presets.insert_one(doc)
    doc.pop("_id", None)
    return doc


@api_router.get("/presets")
async def get_presets():
    """Get all saved presets"""
    docs = await db.presets.find({}, {"_id": 0}).to_list(100)
    return {"presets": docs}


@api_router.get("/presets/{preset_id}")
async def get_preset(preset_id: str):
    """Get a specific preset"""
    doc = await db.presets.find_one({"id": preset_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Preset not found")
    return doc


@api_router.put("/presets/{preset_id}")
async def update_preset(preset_id: str, preset: PresetCreate):
    """Update a preset"""
    doc = preset.model_dump()
    doc["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = await db.presets.update_one(
        {"id": preset_id},
        {"$set": doc}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Preset not found")
    updated = await db.presets.find_one({"id": preset_id}, {"_id": 0})
    return updated


@api_router.delete("/presets/{preset_id}")
async def delete_preset(preset_id: str):
    """Delete a preset"""
    result = await db.presets.delete_one({"id": preset_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Preset not found")
    return {"deleted": True}


# ===================== EXPORT FILE SERVING =====================

EXPORTS_DIR = ROOT_DIR / "exports"
EXPORTS_DIR.mkdir(exist_ok=True)


@api_router.post("/exports/upload")
async def upload_export(file: UploadFile = File(...)):
    """Upload an exported PNG/WebM file and return a public URL.
    WebM files are converted to MP4. PNG files can also be converted to video."""
    import subprocess
    
    ext = file.filename.split('.')[-1] if '.' in file.filename else 'bin'
    file_id = f"{uuid.uuid4().hex[:12]}.{ext}"
    file_path = EXPORTS_DIR / file_id
    
    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)
    
    logger.info(f"Export uploaded: {file_id} ({len(content)} bytes)")
    
    # Convert WebM to MP4 for social media compatibility
    if ext == 'webm':
        mp4_id = file_id.replace('.webm', '.mp4')
        mp4_path = EXPORTS_DIR / mp4_id
        try:
            result = subprocess.run(
                ['ffmpeg', '-y', '-i', str(file_path), 
                 '-c:v', 'libx264', '-preset', 'medium',
                 '-crf', '18', '-pix_fmt', 'yuv420p',
                 '-r', '30',
                 '-movflags', '+faststart', str(mp4_path)],
                capture_output=True, text=True, timeout=180
            )
            if result.returncode == 0 and mp4_path.exists():
                logger.info(f"Converted {file_id} to {mp4_id}")
                return {
                    "file_id": mp4_id,
                    "url": f"/api/exports/{mp4_id}",
                    "size": mp4_path.stat().st_size,
                    "format": "mp4",
                }
            else:
                logger.error(f"ffmpeg conversion failed: {result.stderr[:500]}")
        except Exception as e:
            logger.error(f"ffmpeg conversion error: {e}")
    
    return {
        "file_id": file_id,
        "url": f"/api/exports/{file_id}",
        "size": len(content),
        "format": ext,
    }


@api_router.post("/exports/image-to-video")
async def image_to_video(file: UploadFile = File(...), duration: int = 15):
    """Convert a PNG image to a smooth 30fps MP4 video with fade-in effect.
    This creates a true 30fps video (450 frames for 15s) from a single high-res image."""
    import subprocess
    
    # Save the uploaded image
    img_id = f"{uuid.uuid4().hex[:12]}.png"
    img_path = EXPORTS_DIR / img_id
    content = await file.read()
    with open(img_path, "wb") as f:
        f.write(content)
    
    logger.info(f"Image uploaded for video conversion: {img_id} ({len(content)} bytes)")
    
    mp4_id = img_id.replace('.png', '.mp4')
    mp4_path = EXPORTS_DIR / mp4_id
    
    try:
        # Create a smooth 30fps MP4 from the still image
        # - loop the image for {duration} seconds
        # - fade in from black over first 2 seconds  
        # - slight zoom effect for visual interest
        # - true 30fps = duration * 30 frames
        result = subprocess.run(
            ['ffmpeg', '-y',
             '-loop', '1',
             '-i', str(img_path),
             '-c:v', 'libx264',
             '-t', str(duration),
             '-pix_fmt', 'yuv420p',
             '-r', '30',
             '-preset', 'medium',
             '-crf', '18',
             '-vf', (
                 f'fps=30,'
                 f'fade=t=in:st=0:d=2,'
                 f'zoompan=z=\'min(zoom+0.0003,1.08)\':d={duration*30}:s=1080x1920:fps=30,'
                 f'fade=t=out:st={duration-1}:d=1'
             ),
             '-movflags', '+faststart',
             str(mp4_path)],
            capture_output=True, text=True, timeout=300
        )
        
        if result.returncode != 0:
            # Fallback without zoompan (in case resolution doesn't match)
            logger.warning(f"Zoompan failed, trying simple approach: {result.stderr[:300]}")
            result = subprocess.run(
                ['ffmpeg', '-y',
                 '-loop', '1',
                 '-i', str(img_path),
                 '-c:v', 'libx264',
                 '-t', str(duration),
                 '-pix_fmt', 'yuv420p',
                 '-r', '30',
                 '-preset', 'medium',
                 '-crf', '18',
                 '-vf', f'fps=30,fade=t=in:st=0:d=2,fade=t=out:st={duration-1}:d=1',
                 '-movflags', '+faststart',
                 str(mp4_path)],
                capture_output=True, text=True, timeout=300
            )
        
        if result.returncode == 0 and mp4_path.exists():
            size = mp4_path.stat().st_size
            logger.info(f"Created video {mp4_id}: {size} bytes, {duration}s @ 30fps")
            return {
                "file_id": mp4_id,
                "url": f"/api/exports/{mp4_id}",
                "size": size,
                "format": "mp4",
                "duration": duration,
                "fps": 30,
                "total_frames": duration * 30,
            }
        else:
            logger.error(f"ffmpeg image-to-video failed: {result.stderr[:500]}")
            raise HTTPException(status_code=500, detail=f"Video creation failed: {result.stderr[:200]}")
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=500, detail="Video creation timed out")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Image-to-video error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/exports/{file_id}")
async def serve_export(file_id: str):
    """Serve an exported file for download"""
    file_path = EXPORTS_DIR / file_id
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Export not found")
    
    if file_id.endswith('.png'):
        media_type = "image/png"
    elif file_id.endswith('.mp4'):
        media_type = "video/mp4"
    elif file_id.endswith('.webm'):
        media_type = "video/webm"
    else:
        media_type = "application/octet-stream"
    
    return FileResponse(
        file_path,
        media_type=media_type,
        filename=f"bighat-export-{file_id}",
        headers={"Content-Disposition": f"attachment; filename=bighat-export-{file_id}"}
    )


# ===================== TOURNAMENT ROUTES =====================

@api_router.post("/tournaments")
async def create_tournament(tournament: TournamentCreate):
    """Create a new tournament"""
    doc = tournament.model_dump()
    doc["id"] = str(uuid.uuid4())
    doc["created_at"] = datetime.now(timezone.utc).isoformat()
    doc["updated_at"] = datetime.now(timezone.utc).isoformat()
    doc["status"] = "draft"
    await db.tournaments.insert_one(doc)
    doc.pop("_id", None)
    return doc


@api_router.get("/tournaments")
async def get_tournaments():
    """Get all tournaments"""
    docs = await db.tournaments.find({}, {"_id": 0}).to_list(100)
    return {"tournaments": docs}


@api_router.get("/tournaments/{tournament_id}")
async def get_tournament(tournament_id: str):
    """Get a specific tournament"""
    doc = await db.tournaments.find_one({"id": tournament_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Tournament not found")
    return doc


@api_router.put("/tournaments/{tournament_id}")
async def update_tournament(tournament_id: str, update: TournamentUpdate):
    """Update a tournament"""
    update_data = {k: v for k, v in update.model_dump().items() if v is not None}
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = await db.tournaments.update_one(
        {"id": tournament_id},
        {"$set": update_data}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Tournament not found")
    doc = await db.tournaments.find_one({"id": tournament_id}, {"_id": 0})
    return doc


@api_router.delete("/tournaments/{tournament_id}")
async def delete_tournament(tournament_id: str):
    """Delete a tournament"""
    result = await db.tournaments.delete_one({"id": tournament_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Tournament not found")
    return {"deleted": True}


@api_router.post("/tournaments/{tournament_id}/advance")
async def advance_tournament(tournament_id: str, body: Dict[str, Any] = Body(...)):
    """Record a match result and advance bracket"""
    doc = await db.tournaments.find_one({"id": tournament_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Tournament not found")

    bracket_state = doc.get("bracket_state", {})
    match_id = body.get("match_id")
    winner_seed = body.get("winner_seed")
    score_a = body.get("score_a")
    score_b = body.get("score_b")

    if not match_id or winner_seed is None:
        raise HTTPException(status_code=400, detail="match_id and winner_seed required")

    # Update the match result
    matches = bracket_state.get("matches", {})
    if match_id in matches:
        matches[match_id]["winner_seed"] = winner_seed
        matches[match_id]["score_a"] = score_a
        matches[match_id]["score_b"] = score_b
        matches[match_id]["completed"] = True

    bracket_state["matches"] = matches
    bracket_state["last_updated"] = datetime.now(timezone.utc).isoformat()

    await db.tournaments.update_one(
        {"id": tournament_id},
        {"$set": {"bracket_state": bracket_state, "updated_at": datetime.now(timezone.utc).isoformat()}}
    )

    updated = await db.tournaments.find_one({"id": tournament_id}, {"_id": 0})
    return updated


# Include the router
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
