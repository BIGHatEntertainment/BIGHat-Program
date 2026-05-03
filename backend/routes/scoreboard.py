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
# mongo_url from main server
# client from main server
db = None

def set_database(database):
    global db
    db = database

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
    """Fetch all score files from SharePoint scores folder via Graph API"""
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
    """Sync all SharePoint score JSON files into MongoDB"""
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


@router.post("/exports/upload")
async def upload_export(file: UploadFile = File(...)):
    """Upload an exported PNG/WebM file and return a public URL.
    WebM files are converted to MP4. PNG files can also be converted to video."""
    import subprocess
    
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


@router.post("/exports/image-to-video")
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

@router.post("/generate-video")
async def generate_scoreboard_video(req: ScoreboardVideoRequest):
    """
    Generate a scoreboard MP4 video entirely server-side.
    Renders the leaderboard as an image with Pillow, converts to MP4 with FFmpeg.
    No browser capture required — works reliably on production.
    """
    import subprocess
    from PIL import Image, ImageDraw, ImageFont
    
    is_portrait = req.aspectRatio == "portrait"
    W, H = (1080, 1920) if is_portrait else (1920, 1080)
    
    try:
        # Load fonts
        try:
            font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
            font_title = ImageFont.truetype(font_path, 64 if is_portrait else 56)
            font_date = ImageFont.truetype(font_path, 24)
            font_rank = ImageFont.truetype(font_path, 36 if is_portrait else 32)
            font_name = ImageFont.truetype(font_path, 30 if is_portrait else 26)
            font_score = ImageFont.truetype(font_path, 48 if is_portrait else 40)
            font_small = ImageFont.truetype(font_path, 16)
            font_round_label = ImageFont.truetype(font_path, 14)
        except:
            font_title = font_date = font_rank = font_name = font_score = font_small = font_round_label = ImageFont.load_default()
        
        # Create image
        img = Image.new('RGB', (W, H), '#07070E')
        draw = ImageDraw.Draw(img)
        
        # Draw synthwave grid in bottom half
        grid_top = H // 2
        horizon_y = grid_top
        
        # Horizon glow
        for i in range(40):
            alpha = int(60 * (1 - i / 40))
            y = horizon_y - 20 + i
            draw.line([(0, y), (W, y)], fill=(251, 221, 104, alpha), width=1)
        
        # Gold horizon line
        draw.line([(0, horizon_y), (W, horizon_y)], fill='#fbdd68', width=3)
        
        # Grid lines below horizon
        line_color_h = (89, 115, 247)  # Blue vertical
        line_color_v = (251, 221, 104)  # Gold horizontal
        num_v_lines = 24
        num_h_lines = 15
        for i in range(num_v_lines):
            x = int((i + 0.5) / num_v_lines * W)
            opacity = max(0, int(100 * (1 - (0.3))))  # Fade effect
            draw.line([(x, grid_top), (x, H)], fill=(*line_color_h, opacity), width=1)
        for i in range(num_h_lines):
            y = grid_top + int((i + 1) / (num_h_lines + 1) * (H - grid_top))
            fade = 1 - ((y - grid_top) / (H - grid_top)) * 0.7
            opacity = max(30, int(100 * fade))
            draw.line([(0, y), (W, y)], fill=(251, 221, 104, opacity), width=1)
        
        # Stars in top half
        import random
        random.seed(42)  # Consistent stars
        for _ in range(60):
            sx = random.randint(0, W)
            sy = random.randint(0, horizon_y)
            sr = random.randint(1, 3)
            sc = random.choice([(89, 115, 247), (251, 221, 104), (136, 146, 176), (255, 255, 255)])
            draw.ellipse([sx - sr, sy - sr, sx + sr, sy + sr], fill=sc)
        
        # Content area with margins
        pad_top = int(H * 0.08) if is_portrait else int(H * 0.06)
        pad_side = int(W * 0.05)
        cx = pad_side
        cy = pad_top
        content_w = W - 2 * pad_side
        
        # Title
        draw.text((cx, cy), "BIG HAT TRIVIA", fill='#FFD700', font=font_small)
        cy += 24
        
        # Location name
        draw.text((cx, cy), req.location, fill='#FFFFFF', font=font_title)
        cy += font_title.size + 12
        
        # Date
        if req.date:
            draw.text((cx, cy), req.date, fill='#00d4ff', font=font_date)
            cy += 32
        
        # Round labels
        if req.rounds:
            rx = cx
            for r in req.rounds:
                label = r.get('label', '')
                mult = r.get('multiplier', 1)
                text = f"{label} x{mult}" if mult > 1 else label
                bbox = font_round_label.getbbox(text)
                tw = bbox[2] - bbox[0] + 16
                pill_color = (255, 215, 0, 40) if mult > 1 else (255, 255, 255, 15)
                text_color = '#FFD700' if mult > 1 else '#666688'
                draw.rounded_rectangle([rx, cy, rx + tw, cy + 24], radius=4, fill=pill_color)
                draw.text((rx + 8, cy + 4), text, fill=text_color, font=font_round_label)
                rx += tw + 6
            cy += 36
        
        cy += 10
        
        # Rank colors
        rank_colors = [
            {'border': '#FFD700', 'bg': (255, 215, 0, 40), 'text': '#FFD700'},
            {'border': '#00d4ff', 'bg': (0, 212, 255, 30), 'text': '#00d4ff'},
            {'border': '#ff00ff', 'bg': (255, 0, 255, 25), 'text': '#ff00ff'},
        ]
        
        teams = req.teams[:10]  # Max 10 teams
        
        # Top 3 podium cards
        for idx, team in enumerate(teams[:3]):
            rc = rank_colors[idx]
            card_h = 90 if is_portrait else 80
            
            # Card background
            draw.rounded_rectangle(
                [cx, cy, cx + content_w, cy + card_h],
                radius=12, fill=rc['bg'], outline=rc['border'], width=2
            )
            
            # Rank icon area
            icon_size = 48
            icon_x = cx + 16
            icon_y = cy + (card_h - icon_size) // 2
            draw.rounded_rectangle(
                [icon_x, icon_y, icon_x + icon_size, icon_y + icon_size],
                radius=8, fill=rc['bg']
            )
            draw.text((icon_x + 8, icon_y + 6), f"#{idx + 1}", fill=rc['text'], font=font_rank)
            
            # Team name
            name_x = icon_x + icon_size + 16
            name_y = cy + 14
            name = team.get('name', f'Team {idx + 1}')
            # Truncate if too long
            max_name_w = content_w - 200
            draw.text((name_x, name_y), name, fill='#F4F2FF', font=font_name)
            
            # Round scores below name
            round_scores = team.get('roundScores', [])
            if round_scores:
                rs_y = name_y + font_name.size + 4
                rs_x = name_x
                for s in round_scores:
                    draw.text((rs_x, rs_y), str(s), fill='#666688', font=font_round_label)
                    rs_x += 28
            
            # Total score (right side)
            total = str(team.get('total', 0))
            score_bbox = font_score.getbbox(total)
            score_w = score_bbox[2] - score_bbox[0]
            draw.text(
                (cx + content_w - score_w - 24, cy + (card_h - font_score.size) // 2),
                total, fill=rc['text'], font=font_score
            )
            draw.text(
                (cx + content_w - 40, cy + card_h - 22),
                "pts", fill='#666688', font=font_round_label
            )
            
            cy += card_h + (12 if is_portrait else 10)
        
        # Remaining teams (simple rows)
        for idx, team in enumerate(teams[3:]):
            row_h = 44 if is_portrait else 38
            
            draw.rounded_rectangle(
                [cx, cy, cx + content_w, cy + row_h],
                radius=8, fill=(10, 0, 40, 150), outline=(0, 212, 255, 25), width=1
            )
            
            # Rank number
            rank_num = str(team.get('rank', idx + 4))
            draw.text((cx + 16, cy + 8), rank_num, fill='#00d4ff', font=font_small)
            
            # Team name
            draw.text((cx + 50, cy + 8), team.get('name', ''), fill='#F4F2FF', font=font_small)
            
            # Total score
            total = str(team.get('total', 0))
            total_bbox = font_small.getbbox(total)
            total_w = total_bbox[2] - total_bbox[0]
            draw.text((cx + content_w - total_w - 16, cy + 8), total, fill='#FFD700', font=font_small)
            
            cy += row_h + 6
        
        # Footer branding
        footer_y = H - 50
        draw.ellipse([cx, footer_y, cx + 16, footer_y + 16], fill='#FFD700')
        draw.text((cx + 24, footer_y), "BIG Hat Entertainment", fill='#00d4ff60', font=font_small)
        
        # Save PNG
        png_id = f"sb_{uuid.uuid4().hex[:8]}.png"
        png_path = EXPORTS_DIR / png_id
        img.save(str(png_path), 'PNG')
        logger.info(f"[Scoreboard Video] Rendered {png_id}: {W}x{H}")
        
        # Convert to MP4 with FFmpeg
        mp4_id = png_id.replace('.png', '.mp4')
        mp4_path = EXPORTS_DIR / mp4_id
        
        vf = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1"
        result = subprocess.run(
            ['ffmpeg', '-y',
             '-loop', '1', '-i', str(png_path),
             '-c:v', 'libx264', '-t', str(req.duration),
             '-pix_fmt', 'yuv420p', '-r', '20',
             '-preset', 'ultrafast', '-crf', '28',
             '-threads', '1', '-vf', vf,
             '-movflags', '+faststart',
             str(mp4_path)],
            capture_output=True, text=True, timeout=120
        )
        
        # Cleanup PNG
        try: png_path.unlink()
        except: pass
        
        if result.returncode != 0:
            logger.error(f"[Scoreboard Video] FFmpeg failed: {result.stderr[:300]}")
            raise HTTPException(status_code=500, detail=f"Video encoding failed: {result.stderr[:150]}")
        
        if not mp4_path.exists():
            raise HTTPException(status_code=500, detail="Video file not created")
        
        size = mp4_path.stat().st_size
        logger.info(f"[Scoreboard Video] Created {mp4_id}: {size} bytes, {req.duration}s @ 20fps")
        
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


@router.get("/sharepoint/file/{file_id}")
async def get_score_file_content(file_id: str):
    """Download and return the JSON content of a specific score file from SharePoint."""
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
