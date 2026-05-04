from fastapi import FastAPI, APIRouter, HTTPException, Body, UploadFile, File, Depends
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
# mongo_url from main server
# client from main server
db = None

def set_database(database):
    global db
    db = database


# Native-mode premium gate for FFmpeg-heavy export endpoints.
# Reuses the same `story_generator_enabled` feature flag so "rich media
# generation" (story videos + scoreboard videos) is a single user-visible
# premium line item. No-op in webapp mode.
try:
    from native.feature_gate import require_native_premium as _rnp
    _video_gate = [Depends(_rnp("story_generator_enabled"))]
    _cloud_sync_gate = [Depends(_rnp("cloud_sync_enabled"))]
except ImportError as _e:
    logging.getLogger(__name__).error(
        f"[SCOREBOARD-GATE] native.feature_gate unavailable — premium gates DISABLED: {_e}"
    )
    _video_gate = []
    _cloud_sync_gate = []


def _is_local_mode() -> bool:
    """True when the scoreboard should read scores from disk instead of SharePoint."""
    try:
        from native.asset_factory import can_use_cloud
        return not can_use_cloud()
    except ImportError as e:
        logger.error(
            f"[SCOREBOARD] native.asset_factory unavailable — falling back to cloud mode: {e}"
        )
        return False


def _local_scores_root() -> Path:
    """`<assets>/01_Scores/` — folder of per-venue subfolders of `.json` score files."""
    try:
        from native.config import config_manager
        assets = config_manager.config.get("paths", {}).get("assets")
        if assets:
            return Path(assets) / "01_Scores"
    except Exception:
        pass
    return ROOT_DIR.parent / "native" / "data" / "assets" / "01_Scores"

# Create the main app


# Create a router with the /api prefix
router = APIRouter(prefix="/scoreboard", tags=["scoreboard"])

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

@router.get("/")
async def root():
    return {"message": "BIG Hat Trivia Scoreboard API", "status": "active"}


@router.get("/status")
async def scoreboard_status() -> Dict[str, Any]:
    """Expose mode + subscription + local-score counts so the frontend can
    decide whether to show the upgrade banner, the cloud-sync button, or
    the local scores list.
    """
    native_mode = os.environ.get("BIGHAT_NATIVE_MODE", "0") in ("1", "true", "True", "yes")
    sub: Dict[str, Any] = {"active": False, "tier": "free"}
    try:
        from native.subscription import get_subscription
        sub = get_subscription()
    except Exception:
        pass

    import shutil
    ffmpeg_ok = shutil.which("ffmpeg") is not None

    # Count local files when in native+local mode so the UI knows whether
    # the user has any offline data to render.
    local_root = _local_scores_root()
    local_venues = 0
    local_files = 0
    if _is_local_mode() and local_root.exists():
        for venue_dir in local_root.iterdir():
            if venue_dir.is_dir():
                local_venues += 1
                local_files += sum(
                    1 for f in venue_dir.iterdir()
                    if f.is_file() and f.name.lower().endswith(".json")
                )

    try:
        tournaments = await db.tournaments.count_documents({})
        presets = await db.presets.count_documents({})
        synced_files = await db.score_files.count_documents({})
    except Exception:
        tournaments = presets = synced_files = 0

    mode = "cloud" if not native_mode else ("local" if _is_local_mode() else "cloud")
    video_export_available = (not native_mode) or bool(
        sub.get("active") and sub.get("story_generator_enabled")
    )
    cloud_sync_available = (not native_mode) or bool(
        sub.get("active") and sub.get("cloud_sync_enabled")
    )

    return {
        "mode": mode,
        "native_mode": native_mode,
        "subscription": sub,
        "ffmpeg_ok": ffmpeg_ok,
        "video_export_available": video_export_available,
        "cloud_sync_available": cloud_sync_available,
        "local_scores": {
            "root": str(local_root),
            "venues": local_venues,
            "files": local_files,
        },
        "db_counts": {
            "tournaments": tournaments,
            "presets": presets,
            "synced_files": synced_files,
        },
    }


SP_DRIVE_ID = "b!vFnSKrOPL02dj2-MZU_EHmAti4Py2yROjNNkPjQrBjDvfYp5Cu28QIG93vJSp4xs"
SP_SCORES_FOLDER_ID = "01Z4PLCYTDUSDUZ2ONIZFYVB54TIOLWSRQ"

async def _get_sp_token():
    import httpx
    tenant = os.environ.get("ROUNDMAKER_TENANT_ID", os.environ.get("AZURE_TENANT_ID", ""))
    cid = os.environ.get("ROUNDMAKER_CLIENT_ID", os.environ.get("AZURE_CLIENT_ID", ""))
    csec = os.environ.get("ROUNDMAKER_CLIENT_SECRET", os.environ.get("AZURE_CLIENT_SECRET", ""))
    if not all([tenant, cid, csec]): return None
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token", data={
            "grant_type": "client_credentials", "client_id": cid, "client_secret": csec,
            "scope": "https://graph.microsoft.com/.default"
        })
        return r.json()["access_token"] if r.status_code == 200 else None

@router.get("/sharepoint/files")
async def get_sharepoint_files():
    """Fetch all score files from SharePoint scores folder via Graph API.

    Native local mode: scan `<assets>/01_Scores/<venue>/*.json` on disk.
    Keeps the response shape identical so the frontend doesn't care.
    """
    if _is_local_mode():
        root = _local_scores_root()
        files = []
        if root.exists() and root.is_dir():
            for venue_dir in sorted(root.iterdir(), key=lambda p: p.name.lower()):
                if not venue_dir.is_dir():
                    continue
                for f in sorted(venue_dir.iterdir(), key=lambda p: p.name.lower()):
                    if f.is_file() and f.name.lower().endswith(".json"):
                        stat = f.stat()
                        rel = str(f.relative_to(root)).replace("\\", "/")
                        files.append({
                            "file_name": f.name,
                            "venue": venue_dir.name,
                            "file_id": rel,
                            "last_modified": datetime.fromtimestamp(
                                stat.st_mtime, tz=timezone.utc
                            ).isoformat(),
                            "size": stat.st_size,
                        })
        return {"files": files, "count": len(files), "source": "local"}

    import httpx
    token = await _get_sp_token()
    if not token:
        raise HTTPException(status_code=500, detail="SharePoint authentication failed")
    try:
        headers = {"Authorization": f"Bearer {token}"}
        files = []
        async with httpx.AsyncClient(timeout=20) as client:
            # List location subfolders
            r = await client.get(f"https://graph.microsoft.com/v1.0/drives/{SP_DRIVE_ID}/items/{SP_SCORES_FOLDER_ID}/children", headers=headers)
            if r.status_code != 200:
                raise HTTPException(status_code=500, detail="Failed to list scores folder")
            
            for folder in r.json().get("value", []):
                if not folder.get("folder"):
                    continue
                venue = folder["name"]
                # List JSON files in each venue subfolder
                r2 = await client.get(f"https://graph.microsoft.com/v1.0/drives/{SP_DRIVE_ID}/items/{folder['id']}/children", headers=headers)
                if r2.status_code == 200:
                    for f in r2.json().get("value", []):
                        if f.get("name", "").endswith(".json"):
                            files.append({
                                "file_name": f["name"],
                                "venue": venue,
                                "file_id": f["id"],
                                "last_modified": f.get("lastModifiedDateTime", ""),
                                "size": f.get("size", 0)
                            })
        return {"files": files, "count": len(files)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"SharePoint files error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/sharepoint/sync")
async def sync_sharepoint_data():
    """Sync all SharePoint score JSON files into the DB.

    Native local mode: sync local `<assets>/01_Scores/<venue>/*.json` files
    into `db.score_files`. This gives the frontend one consistent API: the
    scoreboard reads `db.score_files` regardless of asset source.
    """
    if _is_local_mode():
        root = _local_scores_root()
        synced = []
        if root.exists() and root.is_dir():
            for venue_dir in sorted(root.iterdir(), key=lambda p: p.name.lower()):
                if not venue_dir.is_dir():
                    continue
                venue = venue_dir.name
                for f in sorted(venue_dir.iterdir(), key=lambda p: p.name.lower()):
                    if not (f.is_file() and f.name.lower().endswith(".json")):
                        continue
                    try:
                        with open(f, "r", encoding="utf-8") as fh:
                            data = json.load(fh)
                    except (json.JSONDecodeError, OSError) as e:
                        logger.warning(f"Could not parse local score file {f}: {e}")
                        continue
                    doc = {
                        "file_name": f.name,
                        "venue": venue,
                        "last_modified": datetime.fromtimestamp(
                            f.stat().st_mtime, tz=timezone.utc
                        ).isoformat(),
                        "synced_at": datetime.now(timezone.utc).isoformat(),
                        "data": data,
                    }
                    await db.score_files.update_one(
                        {"file_name": f.name},
                        {"$set": doc},
                        upsert=True,
                    )
                    synced.append(f.name)
        return {"synced": synced, "count": len(synced), "source": "local"}

    import httpx
    token = await _get_sp_token()
    if not token:
        raise HTTPException(status_code=500, detail="SharePoint auth failed")
    try:
        headers = {"Authorization": f"Bearer {token}"}
        synced = []
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            r = await client.get(f"https://graph.microsoft.com/v1.0/drives/{SP_DRIVE_ID}/items/{SP_SCORES_FOLDER_ID}/children", headers=headers)
            if r.status_code != 200:
                raise HTTPException(status_code=500, detail="Failed to list scores folder")
            
            for folder in r.json().get("value", []):
                if not folder.get("folder"):
                    continue
                venue = folder["name"]
                r2 = await client.get(f"https://graph.microsoft.com/v1.0/drives/{SP_DRIVE_ID}/items/{folder['id']}/children", headers=headers)
                if r2.status_code != 200:
                    continue
                
                for f in r2.json().get("value", []):
                    if not f.get("name", "").endswith(".json"):
                        continue
                    # Download the JSON file
                    r3 = await client.get(f"https://graph.microsoft.com/v1.0/drives/{SP_DRIVE_ID}/items/{f['id']}/content", headers=headers)
                    if r3.status_code == 200:
                        try:
                            data = r3.json()
                            doc = {
                                "file_name": f["name"],
                                "venue": venue,
                                "last_modified": f.get("lastModifiedDateTime", ""),
                                "synced_at": datetime.now(timezone.utc).isoformat(),
                                "data": data
                            }
                            await db.score_files.update_one(
                                {"file_name": f["name"]},
                                {"$set": doc},
                                upsert=True
                            )
                            synced.append(f["name"])
                        except:
                            pass
        return {"synced": synced, "count": len(synced)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"SharePoint sync error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scores")
async def get_scores():
    """Get all synced score files from MongoDB"""
    docs = await db.score_files.find({}, {"_id": 0}).to_list(1000)
    return {"files": docs, "count": len(docs)}


@router.get("/scores/{venue}")
async def get_venue_scores(venue: str):
    """Get scores for a specific venue"""
    docs = await db.score_files.find(
        {"venue": {"$regex": venue, "$options": "i"}},
        {"_id": 0}
    ).sort("data.date", -1).to_list(100)
    return {"files": docs, "count": len(docs)}


# ===================== PRESET ROUTES =====================

@router.post("/presets")
async def create_preset(preset: PresetCreate):
    """Save an animation preset"""
    doc = preset.model_dump()
    doc["id"] = str(uuid.uuid4())
    doc["created_at"] = datetime.now(timezone.utc).isoformat()
    doc["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.presets.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.get("/presets")
async def get_presets():
    """Get all saved presets"""
    docs = await db.presets.find({}, {"_id": 0}).to_list(100)
    return {"presets": docs}


@router.get("/presets/{preset_id}")
async def get_preset(preset_id: str):
    """Get a specific preset"""
    doc = await db.presets.find_one({"id": preset_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Preset not found")
    return doc


@router.put("/presets/{preset_id}")
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


@router.delete("/presets/{preset_id}")
async def delete_preset(preset_id: str):
    """Delete a preset"""
    result = await db.presets.delete_one({"id": preset_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Preset not found")
    return {"deleted": True}


# ===================== EXPORT FILE SERVING =====================

EXPORTS_DIR = ROOT_DIR / "exports"
EXPORTS_DIR.mkdir(exist_ok=True)


@router.post("/exports/upload", dependencies=_video_gate)
async def upload_export(file: UploadFile = File(...)):
    """Upload an exported PNG/WebM file and return a public URL.
    WebM files are converted to MP4. PNG files can also be converted to video."""
    import subprocess

    # Pre-existing F821 fix: derive `ext` from the uploaded filename (or default to 'bin').
    ext = (file.filename.rsplit('.', 1)[-1].lower()
           if file.filename and '.' in file.filename else 'bin')

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
                    "url": f"/api/scoreboard/exports/{mp4_id}",
                    "size": mp4_path.stat().st_size,
                    "format": "mp4",
                }
            else:
                logger.error(f"ffmpeg conversion failed: {result.stderr[:500]}")
        except Exception as e:
            logger.error(f"ffmpeg conversion error: {e}")
    
    return {
        "file_id": file_id,
        "url": f"/api/scoreboard/exports/{file_id}",
        "size": len(content),
        "format": ext,
    }


@router.post("/exports/image-to-video", dependencies=_video_gate)
async def image_to_video(file: UploadFile = File(...), duration: int = 15):
    """Convert a PNG screenshot to a smooth 20fps MP4 video."""
    import subprocess
    
    content = await file.read()
    if not content or len(content) < 100:
        raise HTTPException(status_code=400, detail="Empty or invalid file uploaded")
    
    input_id = f"{uuid.uuid4().hex[:12]}.png"
    input_path = EXPORTS_DIR / input_id
    with open(input_path, "wb") as f:
        f.write(content)
    
    logger.info(f"[Scoreboard Video] Input: {input_id} ({len(content)} bytes)")
    
    mp4_id = input_id.replace('.png', '.mp4')
    mp4_path = EXPORTS_DIR / mp4_id
    
    try:
        # Detect input dimensions to determine landscape vs portrait
        probe = subprocess.run(
            ['ffprobe', '-v', 'error', '-select_streams', 'v:0',
             '-show_entries', 'stream=width,height', '-of', 'csv=p=0',
             str(input_path)],
            capture_output=True, text=True, timeout=10
        )
        
        # Default to landscape 1920x1080
        out_w, out_h = 1920, 1080
        if probe.returncode == 0 and probe.stdout.strip():
            parts = probe.stdout.strip().split(',')
            if len(parts) == 2:
                in_w, in_h = int(parts[0]), int(parts[1])
                if in_h > in_w:
                    # Portrait input → portrait output
                    out_w, out_h = 1080, 1920
                logger.info(f"[Scoreboard Video] Input: {in_w}x{in_h} → Output: {out_w}x{out_h}")
        
        # Enforce exact output resolution with scale→crop→setsar
        vf = f"scale={out_w}:{out_h}:force_original_aspect_ratio=increase,crop={out_w}:{out_h},setsar=1"
        
        result = subprocess.run(
            ['ffmpeg', '-y',
             '-loop', '1',
             '-i', str(input_path),
             '-c:v', 'libx264',
             '-t', str(duration),
             '-pix_fmt', 'yuv420p',
             '-r', '20',
             '-preset', 'ultrafast',
             '-crf', '28',
             '-threads', '1',
             '-vf', vf,
             '-movflags', '+faststart',
             str(mp4_path)],
            capture_output=True, text=True, timeout=180
        )
        
        if result.returncode != 0:
            logger.error(f"[Scoreboard Video] ffmpeg failed: {result.stderr[:500]}")
            raise HTTPException(status_code=500, detail=f"Video creation failed: {result.stderr[:200]}")
        
        if mp4_path.exists():
            size = mp4_path.stat().st_size
            logger.info(f"[Scoreboard Video] Created {mp4_id}: {size} bytes, {duration}s @ 20fps, {out_w}x{out_h}")
            try: input_path.unlink()
            except: pass
            return {
                "file_id": mp4_id,
                "url": f"/api/scoreboard/exports/{mp4_id}",
                "size": size,
                "format": "mp4",
                "duration": duration,
            }
        else:
            raise HTTPException(status_code=500, detail="Video file not created")
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=500, detail="Video creation timed out")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Scoreboard Video] Error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


# ===================== SERVER-SIDE SCOREBOARD VIDEO GENERATION =====================

class ScoreboardVideoRequest(BaseModel):
    """Request to generate a scoreboard video entirely server-side (no browser capture)."""
    teams: List[Dict[str, Any]]
    location: str = "BIG Hat Trivia"
    date: str = ""
    rounds: List[Dict[str, Any]] = []
    aspectRatio: str = "landscape"  # "landscape" or "portrait"
    duration: int = 15

@router.post("/generate-video", dependencies=_video_gate)
async def generate_scoreboard_video(req: ScoreboardVideoRequest):
    """
    Generate a scoreboard MP4 video entirely server-side.
    Renders animated scrolling synthwave grid + static scoreboard overlay.
    Outputs 10fps × duration frames compiled by FFmpeg.
    """
    import subprocess, shutil, tempfile
    from PIL import Image, ImageDraw, ImageFont
    
    is_portrait = req.aspectRatio == "portrait"
    W, H = (1080, 1920) if is_portrait else (1920, 1080)
    FPS = 10  # 10fps is enough for a smooth grid scroll, fast to render
    TOTAL_FRAMES = FPS * req.duration
    GRID_CYCLE_S = 6  # seconds for one full grid scroll cycle
    
    temp_dir = None
    try:
        temp_dir = tempfile.mkdtemp(prefix="sb_video_")
        
        # Load fonts
        try:
            fp = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
            font_title = ImageFont.truetype(fp, 64 if is_portrait else 56)
            font_date = ImageFont.truetype(fp, 24)
            font_rank = ImageFont.truetype(fp, 36 if is_portrait else 32)
            font_name = ImageFont.truetype(fp, 30 if is_portrait else 26)
            font_score = ImageFont.truetype(fp, 48 if is_portrait else 40)
            font_small = ImageFont.truetype(fp, 16)
            font_rlabel = ImageFont.truetype(fp, 14)
        except Exception:
            font_title = font_date = font_rank = font_name = font_score = font_small = font_rlabel = ImageFont.load_default()
        
        grid_top = H // 2
        grid_h = H - grid_top
        num_v = 24
        h_spacing = 40  # tighter spacing for more visible scroll
        
        # ---- Helper: render grid frame at a given scroll offset ----
        def render_grid(scroll_pct):
            """Return an RGB image of the background + animated grid at scroll_pct (0→1)."""
            bg = Image.new('RGB', (W, H), (7, 7, 14))
            d = ImageDraw.Draw(bg)
            
            # Sky gradient (top half)
            for y in range(grid_top):
                t = y / grid_top
                r = int(0 + t * 10)
                g = int(7 + t * 18)
                b = int(14 + t * 50)
                d.line([(0, y), (W, y)], fill=(r, g, b))
            
            # Stars
            import random
            random.seed(42)
            for _ in range(50):
                sx, sy = random.randint(0, W), random.randint(0, grid_top - 10)
                sr = random.randint(1, 2)
                sc = random.choice([(89, 115, 247), (251, 221, 104), (200, 200, 220), (255, 255, 255)])
                d.ellipse([sx-sr, sy-sr, sx+sr, sy+sr], fill=sc)
            
            # Horizon glow
            for i in range(30):
                alpha_f = 1.0 - (i / 30)
                c = (int(251 * alpha_f * 0.15), int(221 * alpha_f * 0.15), int(104 * alpha_f * 0.15))
                d.line([(0, grid_top - 15 + i), (W, grid_top - 15 + i)], fill=c)
            
            # Gold horizon line
            d.line([(0, grid_top), (W, grid_top)], fill=(251, 221, 104), width=3)
            d.line([(0, grid_top + 1), (W, grid_top + 1)], fill=(200, 176, 80), width=1)
            
            # Vertical lines (parallel, static)
            for i in range(num_v):
                x = int((i + 0.5) / num_v * W)
                for y in range(grid_top + 3, H):
                    fade = 1.0 - ((y - grid_top) / grid_h) * 0.6  # fade toward bottom
                    if fade < 0.05:
                        break
                    # Near horizon: very faint, gets stronger lower
                    near_horizon = min(1.0, (y - grid_top) / (grid_h * 0.15))
                    opacity = fade * near_horizon
                    c = (int(89 * opacity * 0.45), int(115 * opacity * 0.45), int(247 * opacity * 0.45))
                    if c[2] > 2:
                        d.point((x, y), fill=c)
            
            # Horizontal lines (scroll upward)
            total_lines = int(grid_h / h_spacing) + 4
            offset_px = scroll_pct * h_spacing  # scroll within one spacing unit
            for i in range(total_lines):
                y = grid_top + int(i * h_spacing - offset_px)
                if y <= grid_top or y >= H:
                    continue
                dist_from_horizon = (y - grid_top) / grid_h
                # 10-step fade: transparent at horizon → visible at bottom
                fade = min(1.0, dist_from_horizon * 2.0)
                if fade < 0.02:
                    continue
                c = (int(251 * fade * 0.5), int(221 * fade * 0.5), int(104 * fade * 0.5))
                d.line([(0, y), (W, y)], fill=c, width=2)
            
            return bg
        
        # ---- Render scoreboard foreground (once, RGBA with transparency) ----
        fg = Image.new('RGBA', (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(fg)
        
        pad_top = int(H * 0.15)
        pad_side = int(W * 0.05)
        cx, cy = pad_side, pad_top
        content_w = W - 2 * pad_side
        
        # Title
        d.text((cx, cy), "BIG HAT TRIVIA", fill=(255, 215, 0, 255), font=font_small)
        cy += 24
        d.text((cx, cy), req.location, fill=(255, 255, 255, 255), font=font_title)
        cy += font_title.size + 12
        if req.date:
            d.text((cx, cy), req.date, fill=(0, 212, 255, 255), font=font_date)
            cy += 32
        
        # Round labels
        if req.rounds:
            rx = cx
            for r in req.rounds:
                label = r.get('label', '')
                mult = r.get('multiplier', 1)
                text = f"{label} x{mult}" if mult > 1 else label
                bbox = font_rlabel.getbbox(text)
                tw = bbox[2] - bbox[0] + 16
                bg_c = (255, 215, 0, 50) if mult > 1 else (255, 255, 255, 20)
                txt_c = (255, 215, 0, 255) if mult > 1 else (100, 100, 136, 255)
                d.rounded_rectangle([rx, cy, rx + tw, cy + 24], radius=4, fill=bg_c)
                d.text((rx + 8, cy + 4), text, fill=txt_c, font=font_rlabel)
                rx += tw + 6
            cy += 36
        cy += 10
        
        rank_styles = [
            {'border': (255, 215, 0), 'bg': (255, 215, 0, 45), 'text': (255, 215, 0, 255)},
            {'border': (0, 212, 255), 'bg': (0, 212, 255, 35), 'text': (0, 212, 255, 255)},
            {'border': (255, 0, 255), 'bg': (255, 0, 255, 30), 'text': (255, 0, 255, 255)},
        ]
        teams = req.teams[:10]
        
        for idx, team in enumerate(teams[:3]):
            rs = rank_styles[idx]
            card_h = 90 if is_portrait else 80
            d.rounded_rectangle([cx, cy, cx + content_w, cy + card_h], radius=12, fill=rs['bg'], outline=rs['border'], width=2)
            icon_sz = 48
            ix, iy = cx + 16, cy + (card_h - icon_sz) // 2
            d.rounded_rectangle([ix, iy, ix + icon_sz, iy + icon_sz], radius=8, fill=rs['bg'])
            d.text((ix + 6, iy + 6), f"#{idx+1}", fill=rs['text'], font=font_rank)
            nx = ix + icon_sz + 16
            d.text((nx, cy + 14), team.get('name', ''), fill=(244, 242, 255, 255), font=font_name)
            rs_list = team.get('roundScores', [])
            if rs_list:
                rsy = cy + 14 + font_name.size + 4
                rsx = nx
                for s in rs_list:
                    d.text((rsx, rsy), str(s), fill=(100, 100, 136, 255), font=font_rlabel)
                    rsx += 28
            total = str(team.get('total', 0))
            sb = font_score.getbbox(total)
            sw = sb[2] - sb[0]
            d.text((cx + content_w - sw - 24, cy + (card_h - font_score.size) // 2), total, fill=rs['text'], font=font_score)
            d.text((cx + content_w - 40, cy + card_h - 22), "pts", fill=(100, 100, 136, 255), font=font_rlabel)
            cy += card_h + (12 if is_portrait else 10)
        
        for idx, team in enumerate(teams[3:]):
            row_h = 44 if is_portrait else 38
            d.rounded_rectangle([cx, cy, cx + content_w, cy + row_h], radius=8, fill=(10, 0, 40, 180), outline=(0, 212, 255, 30), width=1)
            d.text((cx + 16, cy + 8), str(team.get('rank', idx + 4)), fill=(0, 212, 255, 200), font=font_small)
            d.text((cx + 50, cy + 8), team.get('name', ''), fill=(244, 242, 255, 255), font=font_small)
            total = str(team.get('total', 0))
            tb = font_small.getbbox(total)
            tw = tb[2] - tb[0]
            d.text((cx + content_w - tw - 16, cy + 8), total, fill=(255, 215, 0, 255), font=font_small)
            cy += row_h + 6
        
        # Footer
        fy = H - 50
        d.ellipse([cx, fy, cx + 16, fy + 16], fill=(255, 215, 0, 255))
        d.text((cx + 24, fy), "BIG Hat Entertainment", fill=(0, 212, 255, 100), font=font_small)
        
        logger.info(f"[Scoreboard Video] Foreground rendered, generating {TOTAL_FRAMES} frames...")
        
        # ---- Render frames: grid(scroll) + foreground composite ----
        for frame_idx in range(TOTAL_FRAMES):
            t = frame_idx / FPS  # time in seconds
            scroll_pct = (t % GRID_CYCLE_S) / GRID_CYCLE_S  # 0→1 within cycle
            
            bg = render_grid(scroll_pct)
            bg.paste(fg, (0, 0), fg)  # composite foreground with alpha
            
            frame_path = os.path.join(temp_dir, f"frame_{frame_idx:04d}.png")
            bg.save(frame_path, 'PNG')
        
        logger.info(f"[Scoreboard Video] {TOTAL_FRAMES} frames saved, encoding with FFmpeg...")
        
        # ---- FFmpeg: frames → MP4 ----
        mp4_id = f"sb_{uuid.uuid4().hex[:8]}.mp4"
        mp4_path = EXPORTS_DIR / mp4_id
        
        result = subprocess.run(
            ['ffmpeg', '-y',
             '-framerate', str(FPS),
             '-i', os.path.join(temp_dir, 'frame_%04d.png'),
             '-c:v', 'libx264',
             '-pix_fmt', 'yuv420p',
             '-preset', 'ultrafast',
             '-crf', '28',
             '-threads', '1',
             '-movflags', '+faststart',
             str(mp4_path)],
            capture_output=True, text=True, timeout=180
        )
        
        if result.returncode != 0:
            logger.error(f"[Scoreboard Video] FFmpeg failed: {result.stderr[:300]}")
            raise HTTPException(status_code=500, detail=f"Video encoding failed: {result.stderr[:150]}")
        
        if not mp4_path.exists():
            raise HTTPException(status_code=500, detail="Video file not created")
        
        size = mp4_path.stat().st_size
        logger.info(f"[Scoreboard Video] Created {mp4_id}: {size} bytes, {req.duration}s @ {FPS}fps, {W}x{H}")
        
        return {
            "success": True,
            "file_id": mp4_id,
            "url": f"/api/scoreboard/exports/{mp4_id}",
            "size": size,
            "duration": req.duration,
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Scoreboard Video] Error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Video generation failed: {str(e)[:100]}")
    finally:
        if temp_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)



@router.get("/exports/{file_id}")
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

@router.post("/tournaments")
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


@router.get("/tournaments")
async def get_tournaments():
    """Get all tournaments"""
    docs = await db.tournaments.find({}, {"_id": 0}).to_list(100)
    return {"tournaments": docs}


@router.get("/tournaments/{tournament_id}")
async def get_tournament(tournament_id: str):
    """Get a specific tournament"""
    doc = await db.tournaments.find_one({"id": tournament_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Tournament not found")
    return doc


@router.put("/tournaments/{tournament_id}")
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


@router.delete("/tournaments/{tournament_id}")
async def delete_tournament(tournament_id: str):
    """Delete a tournament"""
    result = await db.tournaments.delete_one({"id": tournament_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Tournament not found")
    return {"deleted": True}


@router.post("/tournaments/{tournament_id}/advance")
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


@router.get("/sharepoint/file/{file_id:path}")
async def get_score_file_content(file_id: str):
    """Download and return the JSON content of a specific score file.

    Native local mode: `file_id` is the relative path under the local
    scores root (e.g. `Demo Pub/2026-05-01.json`). Cloud mode: Graph itemId.
    """
    if _is_local_mode():
        src = (_local_scores_root() / file_id).resolve()
        root = _local_scores_root().resolve()
        # Path-traversal guard
        try:
            src.relative_to(root)
        except ValueError:
            raise HTTPException(status_code=400, detail="invalid path")
        if not src.exists() or not src.is_file():
            raise HTTPException(status_code=404, detail="Score file not found")
        try:
            with open(src, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except (json.JSONDecodeError, OSError) as e:
            raise HTTPException(status_code=500, detail=f"Invalid JSON: {e}")

    import httpx
    token = await _get_sp_token()
    if not token:
        raise HTTPException(status_code=500, detail="SharePoint auth failed")
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            r = await client.get(
                f"https://graph.microsoft.com/v1.0/drives/{SP_DRIVE_ID}/items/{file_id}/content",
                headers={"Authorization": f"Bearer {token}"}
            )
            if r.status_code == 200:
                return r.json()
            raise HTTPException(status_code=r.status_code, detail="Failed to download file")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
