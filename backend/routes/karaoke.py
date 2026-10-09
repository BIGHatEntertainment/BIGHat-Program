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
        "qr_enabled": True,                      # alpha.95: the request QR is always on the audience screen
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
    """alpha.95: kept only so an older screen does not get an error. The overlay and the request QR are ALWAYS on:
    whatever is sent here is ignored and both stay on."""
    await db.karaoke_sessions.update_one({"is_active": True}, {"$set": {"overlay_enabled": True, "qr_enabled": True}})
    return {"success": True, "overlay_enabled": True, "qr_enabled": True}


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
        "video_error": old.get("video_error", "") if old_id == new_id else "",       # alpha.96: why the TV could not play this song
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
        "qr_enabled": True,                       # alpha.95: always on
        "overlay_enabled": True,
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
    if "error" in data:                                      # alpha.96: the TV tells the host WHY a song would not play ("" clears it)
        upd["playback.video_error"] = str(data.get("error") or "")[:40]
    if upd:
        await db.karaoke_sessions.update_one({"is_active": True}, {"$set": upd})
    return {"success": True}


@router.post("/session/preload")
async def set_preload(request: Request):
    """Host tells the audience which song to load in the background (the next singer), or clears it."""
    data = await request.json()
    pre = {"singer_id": data.get("singer_id"), "embed_url": data.get("embed_url", ""), "ready": False, "percent": 0} if data.get("singer_id") else None
    if pre and data.get("retry"):
        pre["retry"] = data.get("retry")                  # alpha.93: the host pressed "Retry loading": the audience screen starts this one afresh
    await db.karaoke_sessions.update_one({"is_active": True}, {"$set": {"preload": pre}})
    return {"success": True}


@router.post("/session/preload-report")
async def preload_report(request: Request):
    """The audience screen reports how much of the next song is REALLY buffered (alpha.89).
    percent: 0-100 of what we need before the song can start cleanly. ready: true once it is enough."""
    data = await request.json()
    s = await db.karaoke_sessions.find_one({"is_active": True}, {"_id": 0, "preload": 1})
    pre = (s or {}).get("preload") or {}
    if not pre.get("singer_id") or data.get("singer_id") != pre.get("singer_id"):
        return {"success": False, "reason": "stale"}
    upd = {}
    if "percent" in data:
        try:
            pct = max(0, min(100, int(round(float(data.get("percent") or 0)))))
        except (TypeError, ValueError):
            pct = 0
        pct = max(pct, int(pre.get("percent") or 0)) if not pre.get("ready") else pct      # never goes backwards while loading
        upd["preload.percent"] = pct
    if "buffered_seconds" in data:
        try:
            upd["preload.buffered_seconds"] = round(float(data.get("buffered_seconds") or 0), 1)
        except (TypeError, ValueError):
            pass
    if "ready" in data:
        upd["preload.ready"] = bool(data.get("ready"))
        if data.get("ready"):
            upd["preload.percent"] = 100
    if data.get("error"):
        upd["preload.error"] = str(data.get("error"))[:80]
    ops = {}
    if upd:
        ops["$set"] = upd
    if not data.get("error") and ("percent" in data or data.get("ready")):
        ops["$unset"] = {"preload.error": ""}          # alpha.93: progress after a failed try means the retry worked, so clear the error
    if ops:
        await db.karaoke_sessions.update_one({"is_active": True}, ops)
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
def _seconds(iso: str) -> int:
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    return int(m.group(1) or 0) * 3600 + int(m.group(2) or 0) * 60 + int(m.group(3) or 0) if m else 0


# ===================== alpha.104: the prototype's YouTube search, ported as written =====================
# Source: BIGHat-Beta-Testing backend/routes/karaoke.py (owner pasted the current version 2026-10-08 19:20 MST).
# Only change: the key comes from kl.youtube_key() (saved in Karaoke Setup, else the YOUTUBE_API_KEY variable).

def _ytdlp_search(search_query: str, count: int) -> list:
    """Blocking yt-dlp search. Runs in a worker thread. Returns a list of result dicts.

    Uses yt-dlp's `ytsearchN:` with extract_flat so it scrapes YouTube's public search
    page (no Data API, no quota, no key). Fast (~1s) and unlimited."""
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
    """Keep only videos that are actually EMBEDDABLE (playable in our audience view).

    Many karaoke uploads set 'Playback on other websites has been disabled by the video owner'
    (YouTube error 150). yt-dlp search can't tell us this, so we make ONE YouTube Data API
    videos.list call (part=status,contentDetails): 1 quota unit for up to 50 ids. We drop any
    video that is not embeddable / not public, and use the API's exact duration.

    Resilient: if there is no API key or the call fails, return the unfiltered list so search
    still works."""
    import httpx

    api_key = kl.youtube_key()
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
            logger.warning(f"[YouTube] embeddable check failed ({r.status_code}) - returning unfiltered")
            return results
        data = r.json()
    except Exception as e:
        logger.warning(f"[YouTube] embeddable check error: {e} - returning unfiltered")
        return results

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
        # If the API didn't return this id at all, keep it (benefit of the doubt) - but if it
        # was returned and flagged non-embeddable/private, drop it.
        if vid in embeddable and not embeddable[vid]:
            continue
        if vid in durations and durations[vid]:
            res["duration_seconds"] = durations[vid]
        filtered.append(res)

    # Safety: never hand back an empty list purely due to filtering.
    return filtered if filtered else results


@router.get("/youtube/search")
async def youtube_search(q: str = "", max_results: int = 15):
    """Search YouTube for karaoke videos via yt-dlp (NO API quota).
    A 24h MongoDB cache (LRU, 60 entries) front-runs repeat queries for instant results."""
    import asyncio

    if not q or len(q) < 2:
        return {"results": []}

    search_query = f"{q} karaoke"
    # cache_key is versioned (|v2) so old cached entries from before the embeddable filter are ignored.
    cache_key = f"{q} karaoke|v2".lower().strip()
    effective_max = min(max_results, 12)

    # Step 1: MongoDB cache (fresh <24h) - instant repeat searches.
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
            # Final fallback: fuzzy cache match on the first word so the host still sees SOMETHING.
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


# Reputable karaoke providers - results from these channels are ranked FIRST, but ALL results are kept.
KARAOKE_PROVIDERS = [
    "partytyme", "party tyme",
    "stingray karaoke", "stingray music", "stingray",
    "sing king", "singking",
    "sing2karaoke", "sing 2 karaoke",
]


def _sort_by_karaoke_providers(results: list) -> list:
    """Rank reputable karaoke providers first while KEEPING every result (stable sort)."""
    def is_provider(r) -> bool:
        blob = f"{(r.get('artist') or '').lower()} {(r.get('title') or '').lower()}"
        return any(p in blob for p in KARAOKE_PROVIDERS)

    return sorted(results, key=lambda r: 0 if is_provider(r) else 1)


@router.post("/youtube/pre-warm")
async def pre_warm_cache():
    """No-op kept for backward compatibility (yt-dlp search is unlimited; pre-warm not needed)."""
    return {"success": True, "skipped": True, "reason": "yt-dlp search is unlimited; pre-warm not needed"}
