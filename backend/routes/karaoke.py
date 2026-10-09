from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, Request
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import os
import logging
import uuid
from datetime import datetime, timezone

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/karaoke", tags=["karaoke"])

db = None
def set_database(database):
    global db
    db = database

# ===================== Models =====================

class KaraokeSession(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:12])
    location: str
    host: str
    host_email: str = ""
    filler_source: str = ""
    audio_out: str = "default"
    video_out: str = "default"
    services: Dict[str, Any] = {}
    is_active: bool = True
    mode: str = "filler"  # "filler" or "karaoke"
    overlay_enabled: bool = False
    qr_enabled: bool = False
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class SingerRequest(BaseModel):
    singer_name: str
    song_title: str
    song_artist: str = ""
    source: str = "manual"  # "manual" or "qr"

# ===================== Session Management =====================

@router.post("/session/create")
async def create_session(request: Request):
    """Create a new karaoke session. Ends any existing active session first."""
    # End all existing active sessions
    await db.karaoke_sessions.update_many({"is_active": True}, {"$set": {"is_active": False}})
    
    data = await request.json()
    session_id = str(uuid.uuid4())[:12]
    doc = {
        "id": session_id,
        "location": data.get("location", ""),
        "host": data.get("host", ""),
        "host_email": data.get("host_email", ""),
        "filler_source": data.get("filler_source", ""),
        "audio_out": data.get("audio_out", "default"),
        "video_out": data.get("video_out", "default"),
        "services": data.get("services", {}),
        "is_active": True,
        "mode": "filler",
        "overlay_enabled": False,
        "qr_enabled": data.get("qr_enabled", False),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.karaoke_sessions.insert_one(doc)
    logger.info(f"[Karaoke] Session created: {session_id} at {doc['location']}")
    return {"success": True, "session": {k: v for k, v in doc.items() if k != '_id'}}

@router.get("/session/active")
async def get_active_session():
    """Get the current active karaoke session."""
    session = await db.karaoke_sessions.find_one({"is_active": True}, {"_id": 0}, sort=[("created_at", -1)])
    if not session:
        return {"session": None}
    return {"session": session}

@router.get("/venues")
async def get_karaoke_venues():
    """Get venues that have karaoke pricing set (price > 0)."""
    pricing = await db.venue_pricing.find({"karaoke_price": {"$gt": 0}}, {"_id": 0}).to_list(100)
    venue_ids = [p["venue_id"] for p in pricing]
    venues = await db.venues.find({"id": {"$in": venue_ids}}, {"_id": 0}).to_list(100)
    venue_map = {v["id"]: v for v in venues}
    result = []
    for p in pricing:
        v = venue_map.get(p["venue_id"])
        if v:
            result.append({"id": v["id"], "name": v["name"], "karaoke_price": p["karaoke_price"]})
    result.sort(key=lambda x: x["name"])
    return {"venues": result}

@router.post("/session/end")
async def end_session():
    """End the active karaoke session."""
    await db.karaoke_sessions.update_many({"is_active": True}, {"$set": {"is_active": False}})
    return {"success": True}

@router.post("/session/playback")
async def set_playback(request: Request):
    """Host sets the current playback state — audience view polls this."""
    data = await request.json()
    await db.karaoke_sessions.update_one({"is_active": True}, {"$set": {
        "playback": {
            "song_playing": data.get("song_playing", False),
            "song_ending": data.get("song_ending", False),
            "current_singer": data.get("current_singer"),
            "mode": data.get("mode", "filler"),
        }
    }})
    return {"success": True}

@router.get("/session/playback")
async def get_playback():
    """Audience view polls this for current playback state."""
    session = await db.karaoke_sessions.find_one({"is_active": True}, {"_id": 0, "playback": 1, "location": 1, "qr_enabled": 1})
    if not session:
        return {"playback": None}
    return {
        "playback": session.get("playback", {"song_playing": False, "current_singer": None, "mode": "filler"}),
        "location": session.get("location", ""),
        "qr_enabled": session.get("qr_enabled", False),
    }

@router.get("/overlay/logo/{location_name}")
async def get_location_logo(location_name: str):
    """Fetch location logo from SharePoint: 02_Karaoke/Web App/00_Builder/01_Locations/{venue}/Logo.png"""
    import httpx, base64
    
    tenant = os.environ.get("AZURE_TENANT_ID", "")
    cid = os.environ.get("AZURE_CLIENT_ID", "")
    csec = os.environ.get("AZURE_CLIENT_SECRET", "")
    drive_id = "b!vFnSKrOPL02dj2-MZU_EHmAti4Py2yROjNNkPjQrBjDvfYp5Cu28QIG93vJSp4xs"
    
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token", data={
                "grant_type": "client_credentials", "client_id": cid, "client_secret": csec,
                "scope": "https://graph.microsoft.com/.default"
            })
            if r.status_code != 200:
                return {"logo": None}
            token = r.json()["access_token"]
        
        base_path = "02_Karaoke/Web App/00_Builder/01_Locations"
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(
                f"https://graph.microsoft.com/v1.0/drives/{drive_id}/root:/{base_path}:/children",
                headers={"Authorization": f"Bearer {token}"}
            )
            if r.status_code != 200:
                logger.error(f"[Karaoke Logo] List failed: {r.status_code}")
                return {"logo": None}
            folders = r.json().get("value", [])
        
        loc_clean = location_name.lower().replace("the ", "").replace("'", "").replace("\u2019", "").strip()
        target_folder = None
        for folder in folders:
            if not folder.get("folder"): continue
            fc = folder["name"].lower().replace("the ", "").replace("'", "").replace("\u2019", "").strip()
            if loc_clean in fc or fc in loc_clean:
                target_folder = folder; break
            for word in [w for w in loc_clean.split() if len(w) > 3]:
                if word in fc:
                    target_folder = folder; break
            if target_folder: break
        
        if not target_folder:
            logger.warning(f"[Karaoke Logo] No match for '{location_name}'")
            return {"logo": None}
        
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(
                f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{target_folder['id']}/children",
                headers={"Authorization": f"Bearer {token}"}
            )
            files = r.json().get("value", []) if r.status_code == 200 else []
        
        for f in files:
            fn = f["name"].lower()
            if fn.endswith((".png", ".jpg", ".jpeg", ".webp")):
                async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                    dl = await client.get(
                        f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{f['id']}/content",
                        headers={"Authorization": f"Bearer {token}"}
                    )
                    if dl.status_code == 200:
                        ext = fn.rsplit(".", 1)[-1]
                        return {"logo": f"data:image/{ext};base64,{base64.b64encode(dl.content).decode()}"}
        
        return {"logo": None}
    except Exception as e:
        logger.error(f"[Karaoke Logo] Error: {e}")
        return {"logo": None}

@router.post("/session/video-ended")
async def video_ended():
    """Audience view reports that the YouTube video has ended."""
    session = await db.karaoke_sessions.find_one({"is_active": True})
    if session:
        await db.karaoke_sessions.update_one({"is_active": True}, {"$set": {"playback.video_ended": True}})
    return {"success": True}

@router.post("/session/mode")
async def set_mode(request: Request):
    """Switch between filler and karaoke mode."""
    data = await request.json()
    mode = data.get("mode", "filler")
    await db.karaoke_sessions.update_one({"is_active": True}, {"$set": {"mode": mode}})
    return {"success": True, "mode": mode}

@router.post("/session/overlay")
async def toggle_overlay(request: Request):
    """Toggle overlay on/off."""
    data = await request.json()
    await db.karaoke_sessions.update_one({"is_active": True}, {"$set": {
        "overlay_enabled": data.get("overlay_enabled", False),
        "qr_enabled": data.get("qr_enabled", False),
    }})
    return {"success": True}

# ===================== Singer Queue =====================

@router.get("/queue")
async def get_queue():
    """Get the singer queue."""
    queue = await db.karaoke_queue.find({"status": {"$ne": "done"}}, {"_id": 0}).sort("position", 1).to_list(100)
    return {"queue": queue}

@router.post("/queue/add")
async def add_to_queue(request: Request):
    """Add a singer to the queue, or assign a song to an existing entry."""
    data = await request.json()
    
    # If assign_to is set, update existing entry with song info
    assign_to = data.get("assign_to")
    if assign_to:
        update = {}
        if data.get("song_title"): update["song_title"] = data["song_title"]
        if data.get("song_artist"): update["song_artist"] = data["song_artist"]
        if data.get("embed_url"): update["embed_url"] = data["embed_url"]
        if data.get("source"): update["source"] = data["source"]
        if data.get("duration_seconds"): update["duration_seconds"] = data["duration_seconds"]
        if update:
            await db.karaoke_queue.update_one({"id": assign_to}, {"$set": update})
        return {"success": True}
    
    position = await db.karaoke_queue.count_documents({"status": {"$ne": "done"}})
    entry = {
        "id": str(uuid.uuid4())[:12],
        "singer_name": data.get("singer_name", ""),
        "song_title": data.get("song_title", ""),
        "song_artist": data.get("song_artist", ""),
        "embed_url": data.get("embed_url", ""),
        "duration_seconds": data.get("duration_seconds", 0),
        "source": data.get("source", "manual"),
        "status": "waiting",
        "position": position,
        "added_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.karaoke_queue.insert_one(entry)
    return {"success": True, "entry": {k: v for k, v in entry.items() if k != '_id'}}

@router.post("/queue/next")
async def next_singer():
    """Move current singer to bottom of queue (with no song), promote next waiting to current."""
    # Get current singer info before moving
    current = await db.karaoke_queue.find_one({"status": "current"}, {"_id": 0})
    
    # Move current singer to bottom of queue with cleared song
    if current:
        max_pos = await db.karaoke_queue.count_documents({"status": {"$ne": "done"}})
        await db.karaoke_queue.update_one({"id": current["id"]}, {"$set": {
            "status": "waiting",
            "song_title": "",
            "song_artist": "",
            "embed_url": "",
            "source": "",
            "position": max_pos + 1,
        }})
        # Mark any linked QR request as done
        await db.karaoke_requests.update_many(
            {"queue_entry_id": current["id"], "status": "accepted"},
            {"$set": {"status": "done"}}
        )
    
    # Get next waiting
    next_entry = await db.karaoke_queue.find_one({"status": "waiting"}, {"_id": 0}, sort=[("position", 1)])
    if next_entry:
        await db.karaoke_queue.update_one({"id": next_entry["id"]}, {"$set": {"status": "current"}})
        return {"success": True, "current": next_entry}
    return {"success": True, "current": None, "message": "Queue empty"}

@router.post("/queue/finish-current")
async def finish_current_singer():
    """Move current singer to bottom of queue with cleared song. Does NOT promote next singer."""
    current = await db.karaoke_queue.find_one({"status": "current"}, {"_id": 0})
    if current:
        max_pos = await db.karaoke_queue.count_documents({"status": {"$ne": "done"}})
        await db.karaoke_queue.update_one({"id": current["id"]}, {"$set": {
            "status": "waiting",
            "song_title": "",
            "song_artist": "",
            "embed_url": "",
            "source": "",
            "duration_seconds": 0,
            "position": max_pos + 1,
        }})
        # Mark any linked QR request as 'done' so the singer's device shows "Thanks for singing!"
        await db.karaoke_requests.update_many(
            {"queue_entry_id": current["id"], "status": "accepted"},
            {"$set": {"status": "done"}}
        )
    return {"success": True}

@router.delete("/queue/{entry_id}")
async def remove_from_queue(entry_id: str):
    """Remove a singer from the queue."""
    await db.karaoke_queue.delete_one({"id": entry_id})
    return {"success": True}

@router.post("/queue/reorder")
async def reorder_queue(request: Request):
    """Reorder the queue."""
    data = await request.json()
    order = data.get("order", [])  # list of entry IDs in new order
    for i, entry_id in enumerate(order):
        await db.karaoke_queue.update_one({"id": entry_id}, {"$set": {"position": i}})
    return {"success": True}

@router.post("/queue/clear")
async def clear_queue(request: Request):
    """Clear the entire queue. GUARDED: requires an explicit {"confirm": true} flag so a stray,
    duplicate, or accidental call can never wipe the singer list. Only the host's explicit
    'End Session' action sends the flag."""
    data = {}
    try:
        data = await request.json()
    except Exception:
        data = {}
    if not data.get("confirm"):
        raise HTTPException(status_code=400, detail="Queue clear requires explicit confirmation")
    result = await db.karaoke_queue.delete_many({})
    logger.info(f"[Karaoke] Queue cleared by explicit host action ({result.deleted_count} entries)")
    return {"success": True, "removed": result.deleted_count}

# ===================== Song Library (for QR browsing) =====================

@router.get("/library")
async def get_song_library(q: str = ""):
    """Search the song library. Used by QR code mobile interface."""
    query = {}
    if q:
        query = {"$or": [
            {"title": {"$regex": q, "$options": "i"}},
            {"artist": {"$regex": q, "$options": "i"}},
        ]}
    songs = await db.karaoke_library.find(query, {"_id": 0}).sort("title", 1).to_list(100)
    return {"songs": songs, "total": len(songs)}

@router.post("/library/import")
async def import_library(request: Request):
    """Import songs into the library (admin)."""
    data = await request.json()
    songs = data.get("songs", [])
    if songs:
        for song in songs:
            song["id"] = song.get("id", str(uuid.uuid4())[:12])
        await db.karaoke_library.insert_many(songs)
    return {"success": True, "imported": len(songs)}

# ===================== QR Song Request (public) =====================

@router.post("/request-song")
async def request_song(request: Request):
    """Public: singer submits a song request via QR code."""
    data = await request.json()
    singer = data.get("singer_name", "").strip()
    song = data.get("song_title", "").strip()
    song_artist = data.get("song_artist", "").strip()
    if not singer or not song:
        raise HTTPException(status_code=400, detail="Name and song required")
    
    req_id = str(uuid.uuid4())[:12]
    entry = {
        "id": req_id,
        "singer_name": singer,
        "song_title": song,
        "song_artist": song_artist,
        "status": "pending",  # pending, accepted, rejected
        "position": 0,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.karaoke_requests.insert_one(entry)
    return {"success": True, "request_id": req_id, "message": f"Request submitted!"}

@router.get("/request-status/{request_id}")
async def get_request_status(request_id: str):
    """Public: check status of a song request. Dynamically computes the current
    queue position from the linked queue entry so the singer's device sees live updates."""
    req = await db.karaoke_requests.find_one({"id": request_id}, {"_id": 0})
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    status = req.get("status", "pending")
    position = 0
    is_current = False
    queue_id = req.get("queue_entry_id")
    if queue_id:
        entry = await db.karaoke_queue.find_one({"id": queue_id}, {"_id": 0})
        if not entry or entry.get("status") == "done":
            # Singer already sang and is done — mark accordingly
            return {"status": "done", "position": 0, "is_current": False}
        if entry.get("status") == "current":
            is_current = True
            position = 0
        else:
            # Count how many entries are ahead: current + waiting entries with lower position
            ahead = await db.karaoke_queue.count_documents({
                "status": {"$in": ["waiting", "current"]},
                "id": {"$ne": queue_id},
                "position": {"$lt": entry.get("position", 0)},
            })
            # Also count "current" singer (they have no position number necessarily)
            has_current = await db.karaoke_queue.count_documents({"status": "current"})
            position = ahead + has_current
            # Don't double-count if current is also ahead by position
            if has_current:
                current_ahead = await db.karaoke_queue.count_documents({
                    "status": "current",
                    "position": {"$lt": entry.get("position", 0)},
                })
                if current_ahead:
                    position -= 1  # avoid double count
    return {"status": status, "position": position, "is_current": is_current}

@router.get("/requests/pending")
async def get_pending_requests():
    """Host: get all pending QR song requests."""
    reqs = await db.karaoke_requests.find({"status": "pending"}, {"_id": 0}).sort("created_at", 1).to_list(50)
    return {"requests": reqs}

@router.post("/requests/{request_id}/accept")
async def accept_request(request_id: str):
    """Host: accept a song request. Adds the singer to the queue and links the
    queue entry back to the request so /request-status can compute a live position."""
    req = await db.karaoke_requests.find_one({"id": request_id})
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    # Add to queue
    position = await db.karaoke_queue.count_documents({"status": {"$ne": "done"}})
    queue_id = str(uuid.uuid4())[:12]
    queue_entry = {
        "id": queue_id,
        "singer_name": req.get("singer_name", ""),
        "song_title": req.get("song_title", ""),
        "song_artist": req.get("song_artist", ""),
        "embed_url": "",
        "duration_seconds": 0,
        "source": "qr_request",
        "status": "waiting",
        "position": position,
        "added_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.karaoke_queue.insert_one(queue_entry)
    await db.karaoke_requests.update_one(
        {"id": request_id},
        {"$set": {"status": "accepted", "queue_entry_id": queue_id}}
    )
    return {"success": True, "queue_entry_id": queue_id}

@router.post("/requests/{request_id}/reject")
async def reject_request(request_id: str):
    """Host: reject a song request."""
    await db.karaoke_requests.update_one({"id": request_id}, {"$set": {"status": "rejected"}})
    return {"success": True}


# ===================== YouTube Karaoke Search =====================

def _ytdlp_search(search_query: str, count: int) -> list:
    """Blocking yt-dlp search. Runs in a worker thread. Returns a list of result dicts.

    Uses yt-dlp's `ytsearchN:` with extract_flat so it scrapes YouTube's public search
    page (no Data API, no quota, no key). Fast (~1s) and unlimited — this is what lets
    the karaoke host search all night without ever running out of searches."""
    import yt_dlp

    opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,   # don't resolve each video (fast); we only need metadata
        "skip_download": True,
        "default_search": "ytsearch",
        "noplaylist": True,
        "socket_timeout": 12,
    }
    results = []
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(f"ytsearch{count}:{search_query}", download=False)
    for e in (info or {}).get("entries", []) or []:
        vid = e.get("id")
        if not vid:
            continue
        dur = e.get("duration")
        try:
            dur = int(dur) if dur else 0
        except (TypeError, ValueError):
            dur = 0
        results.append({
            "id": vid,
            "title": e.get("title", "") or "",
            "artist": e.get("channel") or e.get("uploader") or "",
            "thumbnail": f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg",
            "source": "youtube",
            "embed_url": f"https://www.youtube.com/embed/{vid}?autoplay=1&controls=0&rel=0&modestbranding=1",
            "duration_seconds": dur,
        })
    return results


async def _filter_embeddable(results: list) -> list:
    """Keep only videos that are actually EMBEDDABLE (playable in our iframe/audience view).

    Many karaoke uploads (e.g. KaraFun, some Sing King) set 'Playback on other websites has
    been disabled by the video owner' → YouTube error 150, showing 'Video unavailable' on the
    TV. yt-dlp search can't tell us this, so we make ONE cheap YouTube Data API videos.list
    call (part=status,contentDetails) — it costs just 1 quota unit for up to 50 ids (vs 100
    per search the old way), so this stays effectively unlimited for a live night. We drop any
    video that is not embeddable / not public, and use the API's exact duration when present.

    NOTE: YouTube Premium does NOT lift embed restrictions — they're set per-video by the
    uploader — so filtering to embeddable songs is the only reliable way to guarantee playback.

    Resilient: if there's no API key or the call fails, return the unfiltered list so search
    still works (host may occasionally hit a non-embeddable one, but never a blank search)."""
    import httpx

    api_key = os.environ.get("YOUTUBE_API_KEY", "")
    if not api_key or not results:
        return results

    ids = [r["id"] for r in results if r.get("id")]
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            r = await client.get("https://www.googleapis.com/youtube/v3/videos", params={
                "part": "status,contentDetails",
                "id": ",".join(ids[:50]),
                "key": api_key,
            })
        if r.status_code != 200:
            logger.warning(f"[YouTube] embeddable check failed ({r.status_code}) — returning unfiltered")
            return results
        data = r.json()
    except Exception as e:
        logger.warning(f"[YouTube] embeddable check error: {e} — returning unfiltered")
        return results

    import re
    embeddable = {}
    durations = {}
    for it in data.get("items", []):
        vid = it["id"]
        status = it.get("status", {})
        embeddable[vid] = bool(status.get("embeddable")) and status.get("privacyStatus") == "public"
        dur_str = it.get("contentDetails", {}).get("duration", "")
        m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", dur_str)
        if m:
            durations[vid] = int(m.group(1) or 0) * 3600 + int(m.group(2) or 0) * 60 + int(m.group(3) or 0)

    filtered = []
    for res in results:
        vid = res.get("id")
        # If the API didn't return this id at all, keep it (benefit of the doubt) — but if it
        # was returned and flagged non-embeddable/private, drop it.
        if vid in embeddable and not embeddable[vid]:
            continue
        if vid in durations and durations[vid]:
            res["duration_seconds"] = durations[vid]
        filtered.append(res)

    # Safety: never hand back an empty list purely due to filtering — if everything got
    # filtered (unlikely), fall back to the original so the host still sees options.
    return filtered if filtered else results


@router.get("/youtube/search")
async def youtube_search(q: str = "", max_results: int = 15):
    """Search YouTube for karaoke videos via yt-dlp (NO API quota).

    Previously used the YouTube Data API v3 which has a hard ~100-searches/day free cap —
    a live karaoke night blew through it in ~30 minutes and searches went dead. yt-dlp
    scrapes YouTube search directly, so searches are unlimited and free. A 24h MongoDB
    cache (LRU, 60 entries) still front-runs repeat queries for instant results."""
    import asyncio

    if not q or len(q) < 2:
        return {"results": []}

    search_query = f"{q} karaoke"
    # cache_key is versioned (|v2) so old cached entries from before the embeddable filter are
    # ignored — otherwise a redeploy could still serve previously-cached non-embeddable videos.
    cache_key = f"{q} karaoke|v2".lower().strip()
    effective_max = min(max_results, 12)

    # Step 1: MongoDB cache (fresh <24h) — instant repeat searches.
    try:
        cached = await db.youtube_search_cache.find_one({"query": cache_key})
        if cached:
            cache_age = (datetime.now(timezone.utc) - datetime.fromisoformat(cached["cached_at"])).total_seconds()
            if cache_age < 86400:  # 24h
                logger.info(f"[YouTube] Cache hit for '{q}' ({len(cached['results'])} results)")
                try:
                    await db.youtube_search_cache.update_one(
                        {"query": cache_key},
                        {"$set": {"last_accessed_at": datetime.now(timezone.utc).isoformat()}},
                    )
                    await _enforce_cache_cap()
                except Exception:
                    pass
                return {"results": cached["results"], "cached": True}
    except Exception as e:
        logger.warning(f"[YouTube] Cache read error: {e}")

    # Step 2: yt-dlp search in a worker thread (blocking lib) with one retry.
    results = []
    for attempt in range(2):
        try:
            results = await asyncio.wait_for(
                asyncio.to_thread(_ytdlp_search, search_query, effective_max),
                timeout=20,
            )
            break
        except Exception as e:
            logger.warning(f"[YouTube] yt-dlp search attempt {attempt + 1} failed: {e}")
            if attempt == 0:
                await asyncio.sleep(0.5)
                continue
            # Final fallback: fuzzy cache match on the first word so the host still sees
            # SOMETHING rather than an empty list if yt-dlp hiccups.
            try:
                first_word = q.lower().split()[0]
                fuzzy = await db.youtube_search_cache.find(
                    {"query": {"$regex": first_word, "$options": "i"}},
                ).sort("cached_at", -1).limit(1).to_list(1)
                if fuzzy:
                    return {"results": fuzzy[0]["results"], "cached": True, "fuzzy": True}
            except Exception:
                pass
            return {"results": []}

    # Drop videos the owner disabled for embedding (would show 'Video unavailable' on the TV).
    results = await _filter_embeddable(results)

    # Prioritize reputable karaoke providers (keeps ALL results, just re-orders).
    results = _sort_by_karaoke_providers(results)

    # Step 3: Cache with LRU eviction (last 60 songs).
    if results:
        try:
            now_iso = datetime.now(timezone.utc).isoformat()
            await db.youtube_search_cache.update_one(
                {"query": cache_key},
                {"$set": {
                    "query": cache_key,
                    "results": results,
                    "cached_at": now_iso,
                    "last_accessed_at": now_iso,
                }},
                upsert=True,
            )
            await _enforce_cache_cap()
        except Exception as e:
            logger.warning(f"[YouTube] Cache write error: {e}")

    return {"results": results}


CACHE_MAX_ENTRIES = 60

async def _enforce_cache_cap():
    """Keep only the 60 most-recently-accessed entries. Evicts oldest by last_accessed_at."""
    try:
        total = await db.youtube_search_cache.count_documents({})
        if total <= CACHE_MAX_ENTRIES:
            return
        excess = total - CACHE_MAX_ENTRIES
        # Backfill: entries without last_accessed_at sort as smallest — get evicted first (good)
        oldest = await db.youtube_search_cache.find(
            {},
            {"_id": 1, "query": 1},
        ).sort([("last_accessed_at", 1), ("cached_at", 1)]).limit(excess).to_list(excess)
        if oldest:
            ids = [o["_id"] for o in oldest]
            await db.youtube_search_cache.delete_many({"_id": {"$in": ids}})
            logger.info(f"[YouTube] LRU eviction: dropped {len(ids)} old cache entries (cap={CACHE_MAX_ENTRIES})")
    except Exception as e:
        logger.warning(f"[YouTube] LRU eviction error: {e}")


# Reputable karaoke providers — results from these channels are ranked FIRST, but ALL
# results are kept so the host always sees every option (fewer re-searches → less quota use).
KARAOKE_PROVIDERS = [
    "partytyme", "party tyme",
    "stingray karaoke", "stingray music", "stingray",
    "sing king", "singking",
    "sing2karaoke", "sing 2 karaoke",
]


def _sort_by_karaoke_providers(results: list) -> list:
    """Rank reputable karaoke providers first while KEEPING every result.
    Filtering down to a whitelist collapsed some songs to a single option, forcing the
    host to re-search (and burn YouTube quota). Sorting preserves all options and still
    surfaces the trusted providers at the top."""
    def is_provider(r) -> bool:
        blob = f"{(r.get('artist') or '').lower()} {(r.get('title') or '').lower()}"
        return any(p in blob for p in KARAOKE_PROVIDERS)

    # Stable sort: provider matches (False<True → invert) float to the top, order preserved.
    return sorted(results, key=lambda r: 0 if is_provider(r) else 1)


# Top 50 popular karaoke songs for pre-warming the cache
POPULAR_KARAOKE_SONGS = [
    "Bohemian Rhapsody", "Don't Stop Believin", "Sweet Caroline",
    "Livin on a Prayer", "Mr Brightside", "Take Me Home Country Roads",
    "I Want It That Way", "Somebody That I Used to Know", "Shallow",
    "Dancing Queen", "Total Eclipse of the Heart", "Build Me Up Buttercup",
    "Piano Man", "Wonderwall", "Africa", "Summer Nights",
    "Love Shack", "Friends in Low Places", "You Oughta Know",
    "Wannabe", "Baby One More Time", "Since U Been Gone",
    "Toxic", "Crazy In Love", "Umbrella", "Rolling in the Deep",
    "Uptown Funk", "Happy", "Old Town Road", "Shake It Off",
    "Blank Space", "Bad Guy", "Levitating", "Blinding Lights",
    "Shape of You", "Despacito", "Closer", "Sunflower",
    "Stay", "Heat Waves", "As It Was", "Anti-Hero",
    "Flowers", "Creep", "Under the Bridge", "Black Hole Sun",
    "Come As You Are", "No Scrubs", "I Will Survive", "Respect",
]


@router.post("/youtube/pre-warm")
async def pre_warm_cache():
    """No-op kept for backward compatibility.

    Pre-warming existed only to conserve the YouTube Data API's tiny daily quota. Search
    now runs on yt-dlp (unlimited, no quota), so bulk pre-warming is unnecessary — and the
    old version was itself the quota killer (up to 25 Data API searches = 2,500 units on
    every player load, which exhausted the daily limit in a few reloads and killed live
    search). Returns immediately; live searches hit yt-dlp directly and cache themselves."""
    return {"success": True, "skipped": True, "reason": "yt-dlp search is unlimited; pre-warm not needed"}

# ===================== Services Status =====================

@router.get("/services")
async def get_services():
    """Get connected third-party service status."""
    return {
        "services": [
            {"name": "KaraFun", "status": "not_connected", "description": "Stream karaoke tracks with lyrics"},
            {"name": "PartyTyme.net", "status": "not_connected", "description": "Professional karaoke subscription"},
            {"name": "YouTube", "status": "available", "description": "Search YouTube karaoke videos"},
            {"name": "Local Files", "status": "available", "description": "CDG+MP3 or MP4 karaoke files"},
        ]
    }
