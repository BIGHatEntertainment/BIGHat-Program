"""alpha.70: Karaoke sessions, singer queue, QR song requests, YouTube search.

Ported from the BIGHat-Beta-Testing prototype with these changes:
  * No SharePoint (venue logos and the overlay come from Karaoke Setup).
  * The AUDIENCE screen is the master clock: it reports 'song started' and 'song ended' and the host follows.
  * YouTube search reads the key saved in Karaoke Setup (native/karaoke_library.py).
  * Each night starts clean: a new session clears the queue and old requests.
"""
from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Request

from native import karaoke_library as kl
from native import karaoke_relay

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/karaoke", tags=["karaoke"])

db = None


def set_database(database):
    global db
    db = database


async def _clear(collection) -> None:
    """Empty a collection. A brand-new install has no data file yet, and the desktop database
    errors on delete_many in that case, so check first."""
    try:
        if await collection.count_documents({}) > 0:
            await collection.delete_many({})
    except Exception:
        pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _id() -> str:
    return str(uuid.uuid4())[:12]


async def _end_open_sessions() -> None:
    try:
        if await db.karaoke_sessions.count_documents({"is_active": True}) > 0:
            await db.karaoke_sessions.update_many({"is_active": True}, {"$set": {"is_active": False}})
    except Exception:
        pass


# ===================== Session =====================
@router.post("/session/create")
async def create_session(request: Request):
    """Start a Karaoke night. Ends any session that is still open and clears the old queue + requests."""
    data = await request.json()
    await _end_open_sessions()
    await _clear(db.karaoke_queue)
    await _clear(db.karaoke_requests)
    doc = {
        "id": _id(),
        "location": (data.get("location") or "").strip(),
        "host": data.get("host", ""),
        "host_email": data.get("host_email", ""),
        "filler_folder": data.get("filler_folder", ""),
        "audio_out": data.get("audio_out", "default"),
        "video_out": data.get("video_out", "default"),
        "is_active": True,
        "mode": "filler",
        "overlay_enabled": True,
        "qr_enabled": bool(data.get("qr_enabled", True)),
        "playback": {"song_playing": False, "song_ending": False, "current_singer": None, "mode": "filler"},
        "created_at": _now(),
    }
    await db.karaoke_sessions.insert_one(doc)
    logger.info("[Karaoke] session %s at %s", doc["id"], doc["location"])
    relay = {"ok": False}
    if doc["qr_enabled"]:
        try:                                    # alpha.82: phones can request songs through the cloud relay
            relay = await karaoke_relay.start(db, doc["location"] or "Karaoke Night")
        except Exception as e:                  # noqa: BLE001  (a QR problem must never stop the night)
            logger.warning("[Karaoke] relay start failed: %s", e)
    return {"success": True, "session": {k: v for k, v in doc.items() if k != "_id"}, "qr": relay}


@router.get("/session/active")
async def get_active_session():
    s = await db.karaoke_sessions.find_one({"is_active": True}, {"_id": 0}, sort=[("created_at", -1)])
    return {"session": s or None}


@router.post("/session/end")
async def end_session():
    await _end_open_sessions()
    try:
        await karaoke_relay.stop()
    except Exception:                           # noqa: BLE001
        pass
    return {"success": True}


@router.post("/session/mode")
async def set_mode(request: Request):
    data = await request.json()
    mode = data.get("mode", "filler")
    await db.karaoke_sessions.update_one({"is_active": True}, {"$set": {"mode": mode}})
    return {"success": True, "mode": mode}


@router.post("/session/overlay")
async def toggle_overlay(request: Request):
    data = await request.json()
    await db.karaoke_sessions.update_one({"is_active": True}, {"$set": {
        "overlay_enabled": data.get("overlay_enabled", False),
        "qr_enabled": data.get("qr_enabled", False),
    }})
    return {"success": True}


# ===================== Playback (host -> audience) and the audience clock (audience -> host) =====================
@router.post("/session/playback")
async def set_playback(request: Request):
    """Host says what should be on screen. A new song resets the audience's clock."""
    data = await request.json()
    s = await db.karaoke_sessions.find_one({"is_active": True}, {"_id": 0, "playback": 1})
    old = (s or {}).get("playback") or {}
    old_id = (old.get("current_singer") or {}).get("id")
    new_singer = data.get("current_singer")
    new_id = (new_singer or {}).get("id")
    pb = {
        "song_playing": bool(data.get("song_playing", False)),
        "song_ending": bool(data.get("song_ending", False)),
        "current_singer": new_singer,
        "mode": data.get("mode", "filler"),
        # the audience's clock belongs to ONE song; a different song starts at zero
        "audience_started": old.get("audience_started", False) if old_id == new_id else False,
        "audience_time": old.get("audience_time", 0) if old_id == new_id else 0,
        "audience_duration": old.get("audience_duration", 0) if old_id == new_id else 0,
        "video_ended": old.get("video_ended", False) if old_id == new_id else False,
        "rev": int(old.get("rev", 0)) + 1,
    }
    await db.karaoke_sessions.update_one({"is_active": True}, {"$set": {"playback": pb}})
    return {"success": True, "rev": pb["rev"]}


@router.get("/session/playback")
async def get_playback():
    s = await db.karaoke_sessions.find_one({"is_active": True}, {"_id": 0, "playback": 1, "location": 1, "qr_enabled": 1, "overlay_enabled": 1, "preload": 1})
    if not s:
        return {"playback": None}
    return {
        "playback": s.get("playback") or {"song_playing": False, "current_singer": None, "mode": "filler"},
        "location": s.get("location", ""),
        "qr_enabled": s.get("qr_enabled", False),
        "overlay_enabled": s.get("overlay_enabled", True),
        "preload": s.get("preload"),
    }


@router.post("/session/audience-report")
async def audience_report(request: Request):
    """The audience screen reports its clock: started / time / ended. The host follows this, not its own timer."""
    data = await request.json()
    s = await db.karaoke_sessions.find_one({"is_active": True}, {"_id": 0, "playback": 1})
    pb = (s or {}).get("playback") or {}
    sid = (pb.get("current_singer") or {}).get("id")
    if not sid or data.get("singer_id") not in (None, sid):
        return {"success": False, "reason": "stale"}          # a report for a song that is no longer current
    upd = {}
    if "started" in data:
        upd["playback.audience_started"] = bool(data["started"])
    if "time" in data:
        upd["playback.audience_time"] = float(data["time"] or 0)
    if "duration" in data:
        upd["playback.audience_duration"] = float(data["duration"] or 0)
    if data.get("ended"):
        upd["playback.video_ended"] = True
    if upd:
        await db.karaoke_sessions.update_one({"is_active": True}, {"$set": upd})
    return {"success": True}


@router.post("/session/preload")
async def set_preload(request: Request):
    """Host tells the audience which song to load in the background (the next singer), or clears it."""
    data = await request.json()
    pre = {"singer_id": data.get("singer_id"), "embed_url": data.get("embed_url", ""), "ready": False} if data.get("singer_id") else None
    await db.karaoke_sessions.update_one({"is_active": True}, {"$set": {"preload": pre}})
    return {"success": True}


@router.post("/session/preload-report")
async def preload_report(request: Request):
    """The audience screen reports that the background video is really loaded."""
    data = await request.json()
    s = await db.karaoke_sessions.find_one({"is_active": True}, {"_id": 0, "preload": 1})
    pre = (s or {}).get("preload") or {}
    if not pre.get("singer_id") or data.get("singer_id") != pre.get("singer_id"):
        return {"success": False, "reason": "stale"}
    await db.karaoke_sessions.update_one({"is_active": True}, {"$set": {"preload.ready": bool(data.get("ready", True))}})
    return {"success": True}


@router.post("/session/video-ended")
async def video_ended():
    await db.karaoke_sessions.update_one({"is_active": True}, {"$set": {"playback.video_ended": True}})
    return {"success": True}


# ===================== Singer queue =====================
@router.get("/queue")
async def get_queue():
    q = await db.karaoke_queue.find({"status": {"$ne": "done"}}, {"_id": 0}).sort("position", 1).to_list(200)
    return {"queue": q}


@router.post("/queue/add")
async def add_to_queue(request: Request):
    """Add a singer, or (with assign_to) give an existing singer a song."""
    data = await request.json()
    assign_to = data.get("assign_to")
    if assign_to:
        upd = {k: data[k] for k in ("song_title", "song_artist", "embed_url", "source", "duration_seconds") if data.get(k)}
        if upd:
            await db.karaoke_queue.update_one({"id": assign_to}, {"$set": upd})
        return {"success": True}
    position = await db.karaoke_queue.count_documents({"status": {"$ne": "done"}})
    entry = {
        "id": _id(),
        "singer_name": data.get("singer_name", ""),
        "song_title": data.get("song_title", ""),
        "song_artist": data.get("song_artist", ""),
        "embed_url": data.get("embed_url", ""),
        "duration_seconds": data.get("duration_seconds", 0),
        "source": data.get("source", "manual"),
        "status": "waiting",
        "position": position,
        "added_at": _now(),
    }
    await db.karaoke_queue.insert_one(entry)
    return {"success": True, "entry": {k: v for k, v in entry.items() if k != "_id"}}


_CLEARED = {"status": "waiting", "song_title": "", "song_artist": "", "embed_url": "", "source": "", "duration_seconds": 0}


@router.post("/queue/next")
async def next_singer():
    """Current singer goes to the bottom with no song; the next waiting singer becomes current."""
    cur = await db.karaoke_queue.find_one({"status": "current"}, {"_id": 0})
    if cur:
        n = await db.karaoke_queue.count_documents({"status": {"$ne": "done"}})
        await db.karaoke_queue.update_one({"id": cur["id"]}, {"$set": {**_CLEARED, "position": n + 1}})
    nxt = await db.karaoke_queue.find_one({"status": "waiting"}, {"_id": 0}, sort=[("position", 1)])
    if nxt:
        await db.karaoke_queue.update_one({"id": nxt["id"]}, {"$set": {"status": "current"}})
        nxt["status"] = "current"
        return {"success": True, "current": nxt}
    return {"success": True, "current": None, "message": "Queue empty"}


@router.post("/queue/finish-current")
async def finish_current_singer():
    """Current singer goes to the bottom with no song. Does NOT start the next singer."""
    cur = await db.karaoke_queue.find_one({"status": "current"}, {"_id": 0})
    if cur:
        n = await db.karaoke_queue.count_documents({"status": {"$ne": "done"}})
        await db.karaoke_queue.update_one({"id": cur["id"]}, {"$set": {**_CLEARED, "position": n + 1}})
    return {"success": True}


@router.delete("/queue/{entry_id}")
async def remove_from_queue(entry_id: str):
    await db.karaoke_queue.delete_one({"id": entry_id})
    return {"success": True}


@router.post("/queue/reorder")
async def reorder_queue(request: Request):
    data = await request.json()
    for i, entry_id in enumerate(data.get("order", [])):
        await db.karaoke_queue.update_one({"id": entry_id}, {"$set": {"position": i}})
    return {"success": True}


@router.post("/queue/clear")
async def clear_queue():
    await _clear(db.karaoke_queue)
    return {"success": True}


# ===================== Song library (local list, optional) =====================
@router.get("/library")
async def get_song_library(q: str = ""):
    songs = await db.karaoke_library.find({}, {"_id": 0}).to_list(5000)
    if q:
        ql = q.lower()
        songs = [s for s in songs if ql in (s.get("title", "") + " " + s.get("artist", "")).lower()]
    songs.sort(key=lambda s: s.get("title", "").lower())
    return {"songs": songs[:100], "total": len(songs)}


@router.post("/library/import")
async def import_library(request: Request):
    data = await request.json()
    songs = data.get("songs", [])
    for s in songs:
        s["id"] = s.get("id", _id())
    if songs:
        await db.karaoke_library.insert_many(songs)
    return {"success": True, "imported": len(songs)}


@router.get("/request-info")
async def request_info(request: Request):
    """The address the request QR points to. TODO (deferred, 'very nice to have'): a phone on the venue Wi-Fi
    cannot open localhost, so this will return the PC's Wi-Fi address (or a cloud relay) once that is built.
    Until then it is this app's own address."""
    relay_url = karaoke_relay.current_url()
    if relay_url:                               # alpha.82: a link a phone anywhere can open
        return {"url": relay_url, "phone_reachable": True, "online": karaoke_relay.status()["online"]}
    base = str(request.base_url).rstrip("/")
    return {"url": f"{base}/karaoke/request", "phone_reachable": False, "online": karaoke_relay.status()["online"]}


# ===================== QR song requests =====================
@router.post("/request-song")
async def request_song(request: Request):
    """Public: a singer asks for a song from their phone."""
    data = await request.json()
    singer = (data.get("singer_name") or "").strip()
    song = (data.get("song_title") or "").strip()
    if not singer or not song:
        raise HTTPException(status_code=400, detail="Name and song required")
    if len(singer) > 60 or len(song) > 120 or len(data.get("song_artist") or "") > 120:
        raise HTTPException(status_code=400, detail="Too long")
    rid = _id()
    await db.karaoke_requests.insert_one({
        "id": rid, "singer_name": singer, "song_title": song,
        "song_artist": (data.get("song_artist") or "").strip(),
        "status": "pending", "position": 0, "created_at": _now(),
    })
    return {"success": True, "request_id": rid, "message": "Request submitted!"}


@router.get("/request-status/{request_id}")
async def get_request_status(request_id: str):
    r = await db.karaoke_requests.find_one({"id": request_id}, {"_id": 0})
    if not r:
        raise HTTPException(status_code=404, detail="Request not found")
    # "people ahead of you" = singers still waiting ahead of this request's queue spot
    return {"status": r.get("status", "pending"), "position": r.get("position", 0)}


@router.get("/requests/pending")
async def get_pending_requests():
    reqs = await db.karaoke_requests.find({"status": "pending"}, {"_id": 0}).sort("created_at", 1).to_list(50)
    return {"requests": reqs}


@router.post("/requests/{request_id}/accept")
async def accept_request(request_id: str):
    """Host accepts: the singer joins the queue with the song they asked for."""
    r = await db.karaoke_requests.find_one({"id": request_id}, {"_id": 0})
    if not r:
        raise HTTPException(status_code=404, detail="Request not found")
    ahead = await db.karaoke_queue.count_documents({"status": "waiting"})
    await db.karaoke_requests.update_one({"id": request_id}, {"$set": {"status": "accepted", "position": ahead}})
    karaoke_relay.note_answer(r.get("remote_id", ""), "accepted", ahead)
    entry = {
        "id": _id(), "singer_name": r["singer_name"], "song_title": r["song_title"],
        "song_artist": r.get("song_artist", ""), "embed_url": "", "duration_seconds": 0,
        "source": "qr", "status": "waiting",
        "position": await db.karaoke_queue.count_documents({"status": {"$ne": "done"}}), "added_at": _now(),
    }
    await db.karaoke_queue.insert_one(entry)
    return {"success": True, "entry": {k: v for k, v in entry.items() if k != "_id"}}


@router.post("/requests/{request_id}/reject")
async def reject_request(request_id: str):
    r = await db.karaoke_requests.find_one({"id": request_id}, {"_id": 0})
    await db.karaoke_requests.update_one({"id": request_id}, {"$set": {"status": "rejected"}})
    karaoke_relay.note_answer((r or {}).get("remote_id", ""), "rejected")
    return {"success": True}


# ===================== YouTube karaoke search (cached) =====================
KARAOKE_PROVIDERS = ["karafun", "partytyme", "party tyme", "sing king", "singking", "stingray karaoke",
                     "stingray music", "karaoke version", "karaoke songs", "karaoke star", "you sing karaoke"]


def _provider_rank(item: Dict[str, Any]) -> int:
    text = f"{item.get('artist', '')} {item.get('title', '')}".lower()
    for i, p in enumerate(KARAOKE_PROVIDERS):
        if p in text:
            return i
    return 100


def _seconds(iso: str) -> int:
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    return int(m.group(1) or 0) * 3600 + int(m.group(2) or 0) * 60 + int(m.group(3) or 0) if m else 0


@router.get("/youtube/search")
async def youtube_search(q: str = "", max_results: int = 10):
    import httpx
    key = kl.youtube_key()
    if not key:
        raise HTTPException(status_code=400, detail="No YouTube key saved. Add it in Karaoke Setup.")
    if not q or len(q.strip()) < 2:
        return {"results": []}
    query = f"{q.strip()} karaoke"
    cache_key = query.lower()
    try:
        cached = await db.youtube_search_cache.find_one({"query": cache_key})
        if cached and (datetime.now(timezone.utc) - datetime.fromisoformat(cached["cached_at"])).total_seconds() < 86400:
            return {"results": cached["results"], "cached": True}
    except Exception:
        pass
    results: List[Dict[str, Any]] = []
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get("https://www.googleapis.com/youtube/v3/search", params={
                "part": "snippet", "q": query, "type": "video", "maxResults": min(max_results, 10),
                "key": key, "videoCategoryId": "10", "videoEmbeddable": "true"})
            if r.status_code == 403:
                return {"results": [], "quota_warning": True}
            if r.status_code != 200:
                raise HTTPException(status_code=502, detail="YouTube search failed")
            ids = []
            for it in r.json().get("items", []):
                vid = it.get("id", {}).get("videoId")
                if not vid:
                    continue
                sn = it.get("snippet", {})
                ids.append(vid)
                results.append({"id": vid, "title": sn.get("title", ""), "artist": sn.get("channelTitle", ""),
                                "thumbnail": sn.get("thumbnails", {}).get("medium", {}).get("url", ""),
                                "source": "youtube", "duration_seconds": 0,
                                "embed_url": f"https://www.youtube.com/embed/{vid}?autoplay=1&controls=0&rel=0&modestbranding=1"})
            if ids:
                d = await c.get("https://www.googleapis.com/youtube/v3/videos", params={"part": "contentDetails", "id": ",".join(ids), "key": key})
                if d.status_code == 200:
                    for v in d.json().get("items", []):
                        for res in results:
                            if res["id"] == v["id"]:
                                res["duration_seconds"] = _seconds(v.get("contentDetails", {}).get("duration", ""))
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("[Karaoke] YouTube search error: %s", e)
        raise HTTPException(status_code=504, detail="YouTube search timed out")
    results.sort(key=_provider_rank)
    if results:
        await db.youtube_search_cache.update_one({"query": cache_key}, {"$set": {"query": cache_key, "results": results, "cached_at": _now()}}, upsert=True)
    return {"results": results}
