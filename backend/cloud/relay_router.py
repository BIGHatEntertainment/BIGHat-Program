"""QR relay for the desktop program (alpha.82), served by api.bighat.live.

Two small jobs, both so a PHONE can reach something that lives on the host's PC:

  1. FILE DROP     PC uploads a finished video/PNG  ->  public link  ->  QR.  Files expire.
  2. SONG REQUESTS Phone opens a page on the relay and sends a song request; the PC polls the
                   relay over plain outbound HTTPS and pulls the requests (no router setup).

Safety rules (kept simple on purpose):
  * Every call from the PC proves it is a real, activated, un-revoked license (license key + machine id).
  * Phones/guests need no login: they only hold a long random id from the QR.
  * Hard caps: file size, files per license, requests per night, request text length, rate limits.
  * Everything expires and is deleted.  Nothing personal is kept (a first name + a song title).
"""
from __future__ import annotations

import hashlib
import html
import logging
import os
import re
import secrets
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse

logger = logging.getLogger("bighat-relay")
router = APIRouter(tags=["qr-relay"])

# ---------- limits (env-overridable) ----------
FILE_TTL_HOURS = int(os.environ.get("RELAY_FILE_TTL_HOURS", "48"))
MAX_FILE_MB = int(os.environ.get("RELAY_MAX_FILE_MB", "150"))
MAX_FILES_PER_LICENSE = int(os.environ.get("RELAY_MAX_FILES_PER_LICENSE", "20"))
SESSION_TTL_HOURS = int(os.environ.get("RELAY_SESSION_TTL_HOURS", "14"))
MAX_REQUESTS_PER_SESSION = int(os.environ.get("RELAY_MAX_REQUESTS_PER_SESSION", "300"))
MAX_SESSIONS_PER_LICENSE = int(os.environ.get("RELAY_MAX_SESSIONS_PER_LICENSE", "5"))
PHONE_MIN_SECONDS_BETWEEN_REQUESTS = int(os.environ.get("RELAY_PHONE_COOLDOWN_SECONDS", "20"))
ALLOWED_EXT = {"mp4", "png", "jpg", "jpeg", "pdf", "webm", "gif"}

_service = None
_db = None
_files_dir: Optional[Path] = None


def set_runtime(*, service, db, files_dir: Optional[str] = None) -> None:
    global _service, _db, _files_dir
    _service, _db = service, db
    _files_dir = Path(files_dir or os.environ.get("RELAY_FILES_DIR") or "/tmp/bighat_relay_files")
    _files_dir.mkdir(parents=True, exist_ok=True)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(d: datetime) -> str:
    return d.isoformat()


def _need() -> None:
    if _service is None or _db is None or _files_dir is None:
        raise HTTPException(status_code=503, detail="relay_not_ready")


async def _auth(license_key: str, hwid: str) -> str:
    """Only a real, activated, un-revoked license may use the relay. Returns a short hash of the key (never the key)."""
    _need()
    key = (license_key or "").strip().upper()
    ok, why, _lic = await _service.validate(key=key, hwid=(hwid or "").strip())
    if not ok:
        raise HTTPException(status_code=401, detail=f"not_allowed:{why}")
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def _token() -> str:
    return secrets.token_urlsafe(16)          # ~128 bits, unguessable


# ====================================================================
# 1) FILE DROP
# ====================================================================
@router.post("/api/relay/files")
async def upload_file(
    license_key: str = Form(...), hwid: str = Form(...),
    file: UploadFile = File(...), label: str = Form(""),
):
    owner = await _auth(license_key, hwid)
    name = (file.filename or "file").strip()
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in ALLOWED_EXT:
        raise HTTPException(status_code=400, detail="file_type_not_allowed")
    await _purge_expired()
    count = await _db.relay_files.count_documents({"owner": owner})
    if count >= MAX_FILES_PER_LICENSE:
        raise HTTPException(status_code=429, detail="too_many_files")
    fid = _token()
    path = _files_dir / f"{fid}.{ext}"
    size, limit = 0, MAX_FILE_MB * 1024 * 1024
    try:
        with open(path, "wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > limit:
                    raise HTTPException(status_code=413, detail="file_too_big")
                out.write(chunk)
    except HTTPException:
        path.unlink(missing_ok=True)
        raise
    except Exception as e:
        path.unlink(missing_ok=True)
        logger.warning("relay upload failed: %s", e)
        raise HTTPException(status_code=500, detail="upload_failed")
    safe = re.sub(r"[^A-Za-z0-9._ -]", "_", name)[:80] or f"file.{ext}"
    expires = _now() + timedelta(hours=FILE_TTL_HOURS)
    await _db.relay_files.insert_one({
        "id": fid, "owner": owner, "path": str(path), "name": safe, "ext": ext, "size": size,
        "label": (label or "")[:60], "created_at": _iso(_now()), "expires_at": _iso(expires),
    })
    return {"id": fid, "url": f"/api/relay/d/{fid}", "expires_at": _iso(expires), "size": size}


_MIME = {"mp4": "video/mp4", "webm": "video/webm", "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
         "gif": "image/gif", "pdf": "application/pdf"}


@router.get("/d/{fid}")
@router.get("/api/relay/d/{fid}")
async def download_file(fid: str):
    """What the phone opens after scanning. Public, but needs the unguessable id."""
    _need()
    if not re.fullmatch(r"[A-Za-z0-9_-]{16,32}", fid):
        raise HTTPException(status_code=404, detail="not_found")
    doc = await _db.relay_files.find_one({"id": fid}, {"_id": 0})
    if not doc or doc.get("expires_at", "") < _iso(_now()) or not Path(doc["path"]).exists():
        return HTMLResponse(_page("This link has expired",
                                  "<p>Ask the host to show the QR code again.</p>"), status_code=404)
    return FileResponse(doc["path"], media_type=_MIME.get(doc["ext"], "application/octet-stream"),
                        filename=doc["name"], headers={"Cache-Control": "private, max-age=300"})


@router.delete("/api/relay/files/{fid}")
async def delete_file(fid: str, license_key: str, hwid: str):
    owner = await _auth(license_key, hwid)
    doc = await _db.relay_files.find_one({"id": fid, "owner": owner})
    if not doc:
        raise HTTPException(status_code=404, detail="not_found")
    Path(doc["path"]).unlink(missing_ok=True)
    await _db.relay_files.delete_one({"id": fid})
    return {"deleted": True}


async def _purge_expired() -> int:
    now = _iso(_now())
    gone = 0
    for d in await _db.relay_files.find({"expires_at": {"$lt": now}}, {"_id": 0}).to_list(500):
        Path(d["path"]).unlink(missing_ok=True)
        await _db.relay_files.delete_one({"id": d["id"]})
        gone += 1
    for s in await _db.relay_sessions.find({"expires_at": {"$lt": now}}, {"_id": 0}).to_list(200):
        await _db.relay_requests.delete_many({"session": s["id"]})
        await _db.relay_sessions.delete_one({"id": s["id"]})
        gone += 1
    return gone


# ====================================================================
# 2) KARAOKE SONG REQUESTS
# ====================================================================
@router.post("/api/relay/karaoke/sessions")
async def open_session(payload: Dict[str, Any]):
    """PC opens a night. Returns the id the QR uses. Re-opening with the same venue name returns the same id."""
    owner = await _auth(payload.get("license_key", ""), payload.get("hwid", ""))
    await _purge_expired()
    venue = (payload.get("venue") or "Karaoke Night").strip()[:60]
    existing = await _db.relay_sessions.find_one({"owner": owner, "open": True}, {"_id": 0})
    if existing:
        await _db.relay_sessions.update_one({"id": existing["id"]}, {"$set": {
            "venue": venue, "expires_at": _iso(_now() + timedelta(hours=SESSION_TTL_HOURS))}})
        return {"session": existing["id"], "url": f"/api/relay/k/{existing['id']}"}
    if await _db.relay_sessions.count_documents({"owner": owner}) >= MAX_SESSIONS_PER_LICENSE:
        raise HTTPException(status_code=429, detail="too_many_sessions")
    sid = _token()
    await _db.relay_sessions.insert_one({
        "id": sid, "owner": owner, "venue": venue, "open": True, "created_at": _iso(_now()),
        "expires_at": _iso(_now() + timedelta(hours=SESSION_TTL_HOURS))})
    return {"session": sid, "url": f"/api/relay/k/{sid}"}


@router.post("/api/relay/karaoke/sessions/{sid}/close")
async def close_session(sid: str, payload: Dict[str, Any]):
    owner = await _auth(payload.get("license_key", ""), payload.get("hwid", ""))
    s = await _db.relay_sessions.find_one({"id": sid, "owner": owner})
    if not s:
        raise HTTPException(status_code=404, detail="not_found")
    await _db.relay_requests.delete_many({"session": sid})
    await _db.relay_sessions.delete_one({"id": sid})
    return {"closed": True}


async def _session_open(sid: str) -> Dict[str, Any]:
    _need()
    s = await _db.relay_sessions.find_one({"id": sid}, {"_id": 0}) if re.fullmatch(r"[A-Za-z0-9_-]{16,32}", sid or "") else None
    if not s or not s.get("open") or s.get("expires_at", "") < _iso(_now()):
        raise HTTPException(status_code=404, detail="session_closed")
    return s


def _clean(text: Any, limit: int) -> str:
    t = re.sub(r"[\x00-\x1f\x7f]", "", str(text or "")).strip()
    return re.sub(r"\s+", " ", t)[:limit]


@router.post("/api/relay/karaoke/{sid}/request")
async def phone_request(sid: str, request: Request):
    """Phone sends a request. No login; rate limited per phone and per night."""
    s = await _session_open(sid)
    data = await request.json()
    singer, song, artist = _clean(data.get("singer_name"), 40), _clean(data.get("song_title"), 100), _clean(data.get("song_artist"), 100)
    if not singer or not song:
        raise HTTPException(status_code=400, detail="Please enter your name and a song.")
    ip = (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "?")).split(",")[0].strip()
    phone = hashlib.sha256(f"{ip}|{sid}".encode()).hexdigest()[:16]
    last = await _db.relay_requests.find_one({"session": sid, "phone": phone}, {"_id": 0}, sort=[("created_ts", -1)])
    if last and time.time() - last["created_ts"] < PHONE_MIN_SECONDS_BETWEEN_REQUESTS:
        raise HTTPException(status_code=429, detail="Please wait a moment before sending another song.")
    if await _db.relay_requests.count_documents({"session": sid}) >= MAX_REQUESTS_PER_SESSION:
        raise HTTPException(status_code=429, detail="The request list is full for tonight.")
    rid = _token()
    await _db.relay_requests.insert_one({
        "id": rid, "session": sid, "phone": phone, "singer_name": singer, "song_title": song, "song_artist": artist,
        "status": "pending", "pulled": False, "position": 0, "created_ts": time.time(), "created_at": _iso(_now())})
    return {"success": True, "request_id": rid, "message": "Request submitted!"}


@router.get("/api/relay/karaoke/{sid}/status/{rid}")
async def phone_status(sid: str, rid: str):
    await _session_open(sid)
    r = await _db.relay_requests.find_one({"id": rid, "session": sid}, {"_id": 0})
    if not r:
        raise HTTPException(status_code=404, detail="not_found")
    return {"status": r.get("status", "pending"), "position": r.get("position", 0)}


@router.post("/api/relay/karaoke/sessions/{sid}/pull")
async def pc_pull(sid: str, payload: Dict[str, Any]):
    """PC asks 'anything new?'. Returns new requests once (marks them as pulled) and accepts the answers
    for earlier ones in the same call so the phone can show 'accepted / not this time'."""
    owner = await _auth(payload.get("license_key", ""), payload.get("hwid", ""))
    s = await _db.relay_sessions.find_one({"id": sid, "owner": owner}, {"_id": 0})
    if not s:
        raise HTTPException(status_code=404, detail="session_closed")
    for a in (payload.get("answers") or [])[:100]:
        st = a.get("status")
        if st in ("accepted", "rejected") and isinstance(a.get("id"), str):
            await _db.relay_requests.update_one({"id": a["id"], "session": sid}, {"$set": {
                "status": st, "position": int(a.get("position") or 0)}})
    new = await _db.relay_requests.find({"session": sid, "pulled": False}, {"_id": 0}).sort("created_ts", 1).to_list(50)
    for r in new:
        await _db.relay_requests.update_one({"id": r["id"]}, {"$set": {"pulled": True}})
    await _db.relay_sessions.update_one({"id": sid}, {"$set": {"last_pull": _iso(_now())}})
    return {"requests": [{k: r[k] for k in ("id", "singer_name", "song_title", "song_artist", "created_at")} for r in new],
            "venue": s.get("venue", "")}


# ---------- the phone page (self-contained, no React, works on any phone) ----------
def _page(title: str, body: str) -> str:
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title>
<style>body{{margin:0;font-family:system-ui,sans-serif;background:#0a1428;color:#e5edff;display:flex;
justify-content:center;padding:24px}}main{{width:100%;max-width:420px}}h1{{color:#fbdd68;font-size:26px}}
label{{display:block;margin:14px 0 4px;color:#8892b0;font-size:14px}}input{{width:100%;box-sizing:border-box;padding:14px;
font-size:18px;border-radius:10px;border:1px solid #2a3a66;background:#0f1d3a;color:#fff}}
button{{width:100%;margin-top:22px;padding:16px;font-size:18px;font-weight:700;border:0;border-radius:10px;
background:#fbdd68;color:#1a1a1a}}button:disabled{{opacity:.5}}.msg{{margin-top:16px;font-size:16px}}
.err{{color:#ff8a8a}}.ok{{color:#4ade80}}</style></head><body><main><h1>{html.escape(title)}</h1>{body}</main></body></html>"""


_REQUEST_FORM = """
<p>Pick a song and the host will see it on their screen.</p>
<label>Your name</label><input id="n" maxlength="40" autocomplete="given-name">
<label>Song title</label><input id="s" maxlength="100">
<label>Artist (optional)</label><input id="a" maxlength="100">
<button id="go">Request this song</button><div id="m" class="msg"></div>
<script>
const SID="__SID__";let rid=null,timer=null;
const $=i=>document.getElementById(i),say=(t,c)=>{$('m').textContent=t;$('m').className='msg '+(c||'')};
$('go').onclick=async()=>{
  const n=$('n').value.trim(),s=$('s').value.trim();if(!n||!s){say('Please enter your name and a song.','err');return}
  $('go').disabled=true;say('Sending...');
  try{const r=await fetch('/api/relay/karaoke/'+SID+'/request',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({singer_name:n,song_title:s,song_artist:$('a').value.trim()})});
    const d=await r.json();
    if(!r.ok){say(d.detail||'Could not send. Try again.','err');$('go').disabled=false;return}
    rid=d.request_id;say('Sent! Waiting for the host...','ok');timer=setInterval(poll,4000);poll();
  }catch(e){say('No connection. Check your signal and try again.','err');$('go').disabled=false}
};
async function poll(){try{const r=await fetch('/api/relay/karaoke/'+SID+'/status/'+rid);if(!r.ok)return;const d=await r.json();
  if(d.status==='accepted'){clearInterval(timer);say("You're in the queue!"+(d.position?(' People ahead of you: '+d.position):''),'ok');$('go').disabled=false;$('go').textContent='Request another song';$('s').value='';$('a').value=''}
  else if(d.status==='rejected'){clearInterval(timer);say("The host couldn't fit that one in. Try another song.",'err');$('go').disabled=false}
}catch(e){}}
</script>"""


@router.get("/k/{sid}")
@router.get("/api/relay/k/{sid}")
async def phone_page(sid: str):
    try:
        s = await _session_open(sid)
    except HTTPException:
        return HTMLResponse(_page("Karaoke requests are closed",
                                  "<p>The host has ended requests for tonight, or the QR is old. Ask the host.</p>"), status_code=404)
    body = _REQUEST_FORM.replace("__SID__", sid)
    return HTMLResponse(_page(f"Request a song at {s.get('venue') or 'karaoke'}", body))
