from fastapi import FastAPI, APIRouter, HTTPException, Body, UploadFile, File, Depends
from fastapi.responses import FileResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime, timezone
import json
import re

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


def _local_scores_roots() -> list:
    """alpha.97: every folder that can hold score files, best first.
    1) Documents\\BIG Hat Entertainment\\Files\\Trivia\\Scores   (where Trivia 'Save & Exit' writes)
    2) <AppData>\\backups\\scores                              (its safety copy)
    3) Documents\\BIG Hat Entertainment\\Files\\Scoreboard   (read-only: older builds / files copied in by hand)
    4) <assets>\\01_Scores                                       (older installs / files dropped in by hand, if configured)"""
    roots = []
    try:
        from native import scores_store
        roots += [scores_store.primary_root(), scores_store.backup_root(), *scores_store.extra_read_roots()]
    except Exception as e:                                  # noqa: BLE001
        logger.warning(f"[SCOREBOARD] scores_store unavailable: {e}")
    try:
        from native.config import config_manager
        assets = config_manager.config.get("paths", {}).get("assets")
        if assets:
            roots.append(Path(assets) / "01_Scores")
    except Exception:                                       # noqa: BLE001
        pass
    # (the sample folder bundled inside the program is deliberately NOT read: a real install must never show "Demo Pub")
    out, seen = [], set()
    for r in roots:
        k = str(r)
        if k not in seen:
            seen.add(k); out.append(r)
    return out


def _local_scores_root() -> Path:
    """The main folder (where new scores are saved). Kept for the callers that only need one."""
    return _local_scores_roots()[0]


def _local_score_files() -> list:
    """[(root, venue_folder_name, file_path)] for every .json score file in every root. The same file name
    found in two roots is listed once (the first root wins), so the safety copy never shows twice."""
    found, seen = [], set()
    for root in _local_scores_roots():
        if not (root.exists() and root.is_dir()):
            continue
        for venue_dir in sorted(root.iterdir(), key=lambda p: p.name.lower()):
            if not venue_dir.is_dir():
                continue
            for f in sorted(venue_dir.iterdir(), key=lambda p: p.name.lower()):
                if f.is_file() and f.name.lower().endswith(".json"):
                    key = (venue_dir.name.lower(), f.name.lower())
                    if key in seen:
                        continue
                    seen.add(key)
                    found.append((root, venue_dir.name, f))
    return found


# Create the main app


# Create a router with the /api prefix
from native.media_tools import run as _media_run
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

    @field_validator("total_teams")
    @classmethod
    def _positive_total(cls, v: int) -> int:
        if v < 1:
            raise ValueError("total_teams must be >= 1")
        return v

    @field_validator("bye_count")
    @classmethod
    def _non_negative_byes(cls, v: int) -> int:
        if v < 0:
            raise ValueError("bye_count must be >= 0")
        return v

    @model_validator(mode="after")
    def _teams_match_total(self):
        # Only enforce when the caller supplied a non-empty teams list; an
        # empty teams array is valid for "pre-seeded" brackets.
        if self.teams and (len(self.teams) + self.bye_count) != self.total_teams:
            raise ValueError(
                "total_teams must equal len(teams) + bye_count "
                f"(got {len(self.teams)} teams + {self.bye_count} byes != "
                f"{self.total_teams})"
            )
        return self


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
    from native.media_tools import ffmpeg_ok as _ffok
    ffmpeg_ok = _ffok()

    # Count local files when in native+local mode so the UI knows whether
    # the user has any offline data to render.
    local_root = _local_scores_root()
    local_venues = 0
    local_files = 0
    if _is_local_mode():
        _all = _local_score_files()
        local_venues = len({v.lower() for _, v, _ in _all})
        local_files = len(_all)

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
        files = []
        for root, venue, f in _local_score_files():
            stat = f.stat()
            files.append({
                "file_name": f.name,
                "venue": venue,
                "file_id": str(f.relative_to(root)).replace("\\", "/"),
                "last_modified": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
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
        synced = []
        for root, venue, f in _local_score_files():
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"Could not parse local score file {f}: {e}")
                continue
            doc = {
                "file_name": f.name,
                "venue": venue,
                "last_modified": datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc).isoformat(),
                "synced_at": datetime.now(timezone.utc).isoformat(),
                "data": data,
            }
            # keyed by venue AND file name: two venues can have a night with the same file name
            await db.score_files.update_one({"venue": venue, "file_name": f.name}, {"$set": doc}, upsert=True)
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


@router.post("/scores/import")
async def import_score_file(file: UploadFile = File(...)):
    """Import a plain .json score file (what Trivia 'Save & Exit' writes) into the Scoreboard.
    It is saved in the normal score folder like any other night, then synced, so it shows up and can be turned
    into a video. A file that is not a score night is refused with a plain message (HTTP 400)."""
    from native import scores_store
    raw = await file.read()
    try:
        saved = scores_store.import_json(raw)
    except scores_store.BadScoreFile as e:
        raise HTTPException(status_code=400, detail=str(e))
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Could not save the score file on this PC: {e}")
    sync = await sync_sharepoint_data()
    return {"ok": True, "imported": saved["path"], "filename": saved["filename"], "count": sync.get("count", 0),
            "duplicate": bool(saved.get("duplicate"))}


def _score_file_entry(root, venue: str, f) -> Optional[Dict[str, Any]]:
    """One score file as the Scoreboard dropdown shows it. Never raises: a damaged file is reported, not skipped silently."""
    try:
        st = f.stat()
        modified = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat()
    except OSError:
        return None
    entry: Dict[str, Any] = {
        "id": f"{venue}/{f.name}",                       # unique: two venues, or two nights, never collide
        "file_name": f.name, "venue": venue, "last_modified": modified, "data": None, "error": None,
    }
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("teams"), list):
            entry["error"] = "This file has no teams in it."
        else:
            entry["data"] = data
    except (OSError, ValueError) as e:
        entry["error"] = f"Could not read this file ({type(e).__name__})."
    return entry


@router.get("/scores/local")
async def get_local_scores():
    """Fetch: every score file saved on this PC (Trivia 'Save & Exit' folder, its AppData copy, Files/Scoreboard), newest first,
    in ONE call. A GET reading the folders directly: no POST, no database step to go wrong. Also keeps the database copy up to
    date for the older routes. Files that cannot be read are listed with the reason instead of vanishing."""
    out: List[Dict[str, Any]] = []
    for root, venue, f in _local_score_files():
        e = _score_file_entry(root, venue, f)
        if e is None:
            continue
        out.append(e)
        if e["data"] is not None and db is not None:
            try:
                await db.score_files.update_one({"venue": venue, "file_name": f.name},
                                                {"$set": {"file_name": f.name, "venue": venue, "last_modified": e["last_modified"],
                                                          "synced_at": datetime.now(timezone.utc).isoformat(), "data": e["data"]}},
                                                upsert=True)
            except Exception as ex:                          # noqa: BLE001  the files are the truth; the copy is a convenience
                logger.warning(f"[SCOREBOARD] database copy skipped for {f.name}: {ex}")
    out.sort(key=lambda x: (str((x["data"] or {}).get("savedAt") or x["last_modified"])), reverse=True)
    roots = [str(r) for r in _local_scores_roots()]
    return {"files": out, "count": len([x for x in out if x["data"] is not None]),
            "unreadable": len([x for x in out if x["data"] is None]), "folders": roots[:1]}


@router.get("/scores")
async def get_scores():
    """Get all synced score files from MongoDB"""
    docs = await db.score_files.find({}, {"_id": 0}).to_list(1000)
    return {"files": docs, "count": len(docs)}


def _venue_key(v: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(v or "").lower())


@router.get("/scores/{venue}")
async def get_venue_scores(venue: str):
    """Scores for one venue. The venue is matched as PLAIN TEXT (it used to be a regex, so 'Cornish Pasty Co. (Glendale)' broke it)
    against the folder name AND the venue name written inside the file, ignoring spaces, underscores and punctuation."""
    want = _venue_key(venue)
    docs = await db.score_files.find({}, {"_id": 0}).to_list(2000)
    hit = [d for d in docs if want and (_venue_key(d.get("venue")) == want or _venue_key((d.get("data") or {}).get("location")) == want)]
    hit.sort(key=lambda d: str((d.get("data") or {}).get("savedAt") or d.get("last_modified") or ""), reverse=True)
    return {"files": hit[:100], "count": len(hit[:100])}


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

def _exports_dir() -> Path:
    """Where finished scoreboard videos/images are kept. v32.1.9: this used to be <this file's folder>/exports, created while the
    module loads. In the INSTALLED app that folder is inside PyInstaller's read-only temporary bundle, so the mkdir crashed the
    import, the whole Scoreboard router silently never mounted, and every /api/scoreboard/* call answered not_found /
    api_route_not_found (owner, v32.1.8). It now lives in the app's own data folder (AppData), which is writable, survives
    restarts (a QR link or a re-download keeps working) and is never inside the bundle. Never raises."""
    candidates = []
    try:
        from native.data_map import appdata_root
        candidates.append(appdata_root() / "scoreboard_exports")
    except Exception:                                        # noqa: BLE001
        pass
    import tempfile
    candidates.append(Path(tempfile.gettempdir()) / "bighat_scoreboard_exports")
    candidates.append(ROOT_DIR / "exports")
    for c in candidates:
        try:
            c.mkdir(parents=True, exist_ok=True)
            probe = c / ".w"
            probe.write_text("1")
            probe.unlink()
            return c
        except OSError:
            continue
    return candidates[1]                                     # cannot write anywhere: exports will fail with a message, the router still mounts


EXPORTS_DIR = _exports_dir()


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
            result = _media_run(
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
        from native.media_tools import probe_size
        size = probe_size(input_path)

        # Default to landscape 1920x1080
        out_w, out_h = 1920, 1080
        if size:
            in_w, in_h = size
            if in_h > in_w:
                # Portrait input → portrait output
                out_w, out_h = 1080, 1920
            logger.info(f"[Scoreboard Video] Input: {in_w}x{in_h} → Output: {out_w}x{out_h}")
        
        # Enforce exact output resolution with scale→crop→setsar
        vf = f"scale={out_w}:{out_h}:force_original_aspect_ratio=increase,crop={out_w}:{out_h},setsar=1"
        
        result = _media_run(
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
    Generate the scoreboard MP4 on this PC. v32.1.10: drawn like the Trivia Player's FINAL SCORES slide (native/scoreboard_video.py):
    big text, the bundled Lemonada title, a still grid, and the team list scrolling up so EVERY team is shown (the old picture listed 10).
    """
    from native import scoreboard_video as sv

    is_portrait = req.aspectRatio == "portrait"
    W, H = (1080, 1920) if is_portrait else (1920, 1080)
    FPS = 20
    teams = [t for t in (req.teams or []) if isinstance(t, dict)]
    if not teams:
        raise HTTPException(status_code=400, detail="No teams to show. Select a score file first.")
    # the caller's duration is kept as a minimum for short lists; a long list gets the time it needs to scroll once
    seconds = max(int(req.duration or 0), sv.video_seconds(len(teams))) if len(teams) > 5 else max(8, int(req.duration or 0) or 12)
    seconds = min(seconds, 90)

    try:
        mp4_id = f"sb_{uuid.uuid4().hex[:8]}.mp4"
        mp4_path = EXPORTS_DIR / mp4_id
        from native.media_tools import ffmpeg_path as _ffp
        import asyncio
        ok, err = await asyncio.get_event_loop().run_in_executor(                   # keep the app responsive while it draws
            None, sv.encode_mp4, str(mp4_path), W, H, teams, req.location, req.date, req.rounds or [], seconds, FPS, _ffp())
        if not ok:
            logger.error(f"[Scoreboard Video] FFmpeg failed: {err}")
            raise HTTPException(status_code=500, detail=f"Video encoding failed: {err[:150]}")
        if not mp4_path.exists():
            raise HTTPException(status_code=500, detail="Video file not created")
        size = mp4_path.stat().st_size
        logger.info(f"[Scoreboard Video] Created {mp4_id}: {size} bytes, {seconds}s @ {FPS}fps, {W}x{H}")
        return {"success": True, "file_id": mp4_id, "url": f"/api/scoreboard/exports/{mp4_id}", "size": size,
                "duration": seconds, "width": W, "height": H, "teams": len(teams)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Scoreboard Video] Error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Video generation failed: {str(e)[:100]}")



@router.post("/exports/{file_id}/qr-publish")
async def qr_publish_export(file_id: str):
    """alpha.82: upload an exported PNG/MP4 to the QR relay and return a link a PHONE can open (https, ~2 days)."""
    from native import relay_client
    if file_id != Path(file_id).name or "/" in file_id or "\\" in file_id or file_id.startswith("."):
        raise HTTPException(status_code=400, detail="bad file id")
    file_path = EXPORTS_DIR / file_id
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="That export is no longer on this computer. Export it again.")
    res = await relay_client.publish_file(str(file_path), label="scoreboard")
    if not res.get("ok"):
        return {"success": False, "error": res.get("error"), "message": res.get("message")}
    return {"success": True, "url": res["url"], "expires_at": res.get("expires_at")}


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


class TournamentAdvance(BaseModel):
    """Record a single match result and advance the bracket.

    Example body:
        {
          "match_id": "qf_1",
          "winner_seed": 3,
          "score_a": 42,
          "score_b": 37
        }

    `winner_seed` is the seed number of the winning team. `score_a` /
    `score_b` are optional and stored verbatim on the match record.
    """
    match_id: str = Field(..., min_length=1)
    winner_seed: int
    score_a: Optional[int] = None
    score_b: Optional[int] = None


@router.post("/tournaments/{tournament_id}/advance")
async def advance_tournament(tournament_id: str, body: TournamentAdvance):
    """Record a match result and advance bracket"""
    doc = await db.tournaments.find_one({"id": tournament_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Tournament not found")

    bracket_state = doc.get("bracket_state", {})
    match_id = body.match_id
    winner_seed = body.winner_seed
    score_a = body.score_a
    score_b = body.score_b

    # Update the match result
    matches = bracket_state.get("matches", {})
    if match_id not in matches:
        raise HTTPException(
            status_code=404,
            detail=f"match_not_found: '{match_id}' is not in bracket_state.matches",
        )
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
        src = None
        for r in _local_scores_roots():
            cand = (r / file_id).resolve()
            try:
                cand.relative_to(r.resolve())                    # path-traversal guard
            except ValueError:
                raise HTTPException(status_code=400, detail="invalid path")
            if cand.exists() and cand.is_file():
                src = cand
                break
        if src is None:
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
