"""Program <-> Cloud FILE pull (memory/SYNC_CONTRACT.md file lane). The Cloud owns the files; this PC receives them.

Every 5 minutes (and on "Sync now") the Program asks GET /api/program/manifest, which lists the files this PC should have with a
sha256 for each, then downloads what is new or changed (GET /api/program/files/{id}) and files it where the app looks for it:

    category 'bighat'  -> the app's own .bighat importer (rounds land in Files/Trivia/<TYPE>/, the same as the lobby's Import button)
    category 'overlay' -> Files/Locations/<slug>/overlays/<id>.<ext>   + the location's overlay_images record
    category 'image'   -> Files/Locations/<slug>/branding/<id>.<ext>   + the location's branding_images record
    category 'sponsor' -> Files/Locations/<slug>/sponsor/              + the location's sponsor_image record
    host_avatar / host_16x9 / host_9x16 -> Files/Hosts/<host slug>/avatar|host-16x9|host-9x16.<ext> (where the profile page puts them)
                          + the person's profile_picture / host_image_16x9 / host_image_9x16 (v32.3.1)
    anything else      -> not pulled yet (no home in the Program); counted as "skipped".

Data-safety rules (the owner has zero tolerance for silent data loss):
  * It NEVER deletes. A file removed in the Cloud stays on this PC. Only a CHANGED Cloud file replaces the copy this sync brought in.
  * A file the owner put on this PC by hand is never touched: every sync-made file has a stable id (cf<8 hex of the Cloud file id>)
    recorded in <AppData>/secure/cloud_files.json; anything else in the folders is left alone.
  * The download must match the manifest's sha256 AND the X-Content-Sha256 header, or it is thrown away and retried next time.
  * Folder names come from the LOCAL location slug, never from the Cloud. File names and extensions are cleaned. Only png/jpg/gif/webp
    (and mp4/webm for overlays) under 100 MB are accepted for pictures.
  * A venue the data pull has not brought in yet makes its files WAIT (retried next pull). Nothing is lost.
  * Offline / lapsed subscription / unlinked: the Program keeps working; the pull just waits.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import mimetypes
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx

from . import cloud_link

logger = logging.getLogger("bighat-cloud-files")

PULL_EVERY = 300
MAX_PICTURE_BYTES = 100 * 1024 * 1024
MAX_BIGHAT_BYTES = 200 * 1024 * 1024
PICTURE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
OVERLAY_EXT = PICTURE_EXT | {".mp4", ".webm"}
HOST_KINDS = {"host_avatar": ("avatar", "profile_picture"), "host_16x9": ("host-16x9", "host_image_16x9"), "host_9x16": ("host-9x16", "host_image_9x16")}
KINDS = ("bighat", "overlay", "image", "sponsor") + tuple(HOST_KINDS)

_LOCK = asyncio.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ------------------------------------------------------------------ state file (same rules as cloud_sync.json)
def _path() -> Path:
    return cloud_link._dir() / "cloud_files.json"


def _blank() -> Dict[str, Any]:
    return {"files": {}, "last_pull": None, "last_ok": None, "state": "idle", "message": "", "last_counts": {}, "failed": {}}


def _read() -> Dict[str, Any]:
    p = _path()
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(d, dict):
            b = _blank()
            b.update(d)
            return b
    except FileNotFoundError:
        pass
    except (OSError, ValueError):
        try:
            os.replace(p, p.with_suffix(".json.bad"))            # keep the damaged file
        except OSError:
            pass
    return _blank()


def _write(st: Dict[str, Any]) -> None:
    p = _path()
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".cloudfiles_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(st, f, indent=1)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, p)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def public_status() -> Dict[str, Any]:
    st = _read()
    return {"state": st["state"], "message": st["message"], "last_pull": st["last_pull"], "last_ok": st["last_ok"],
            "counts": st["last_counts"], "tracked": len(st["files"]), "failed": len(st["failed"])}


# ------------------------------------------------------------------ names
def stable_id(file_id: str) -> str:
    """The id a sync-made file carries on disk and in the location record. Same Cloud file -> same id, always."""
    return "cf" + hashlib.sha1(str(file_id).encode("utf-8")).hexdigest()[:10]


def safe_ext(name: str, allowed: set) -> Optional[str]:
    ext = Path(str(name or "")).suffix.lower()
    return ext if ext in allowed else None


# ------------------------------------------------------------------ talking to the Cloud
def _headers() -> Optional[Dict[str, str]]:
    tok = cloud_link.get_token()
    return {"Authorization": f"Bearer {tok}"} if tok and cloud_link.cloud_base_url() else None


def _error_for(r: httpx.Response) -> str:
    code = ""
    try:
        code = (r.json() or {}).get("error", "")
    except ValueError:
        pass
    if r.status_code == 402 or code == "subscription_lapsed":
        return "subscription_lapsed"
    if r.status_code == 429:
        return "rate_limited"
    if r.status_code == 401 and code == "unlinked":
        return "unlinked"
    return "unauthorized" if r.status_code == 401 else "rejected"


async def _fetch_manifest() -> Dict[str, Any]:
    h = _headers()
    if not h:
        return {"ok": False, "error": "unlinked"}
    try:
        async with httpx.AsyncClient(timeout=30.0) as c:
            r = await c.get(f"{cloud_link.cloud_base_url()}/api/program/manifest", headers=h)
    except (httpx.HTTPError, ValueError):
        return {"ok": False, "error": "unreachable"}
    if r.status_code == 200:
        try:
            files = (r.json() or {}).get("files")
            return {"ok": True, "files": files if isinstance(files, list) else []}
        except ValueError:
            return {"ok": False, "error": "bad_response"}
    return {"ok": False, "error": _error_for(r)}


async def _download(file_id: str, want_sha: str, max_bytes: int) -> Tuple[Optional[bytes], str]:
    """The bytes of one file, or (None, reason). Checked against the manifest's sha256 and the X-Content-Sha256 header."""
    h = _headers()
    if not h:
        return None, "unlinked"
    try:
        async with httpx.AsyncClient(timeout=120.0) as c:
            r = await c.get(f"{cloud_link.cloud_base_url()}/api/program/files/{file_id}", headers=h)
    except (httpx.HTTPError, ValueError):
        return None, "unreachable"
    if r.status_code != 200:
        return None, _error_for(r) if r.status_code in (401, 402, 429) else f"http_{r.status_code}"
    data = r.content
    if len(data) > max_bytes:
        return None, "too_large"
    got = hashlib.sha256(data).hexdigest()
    hdr = (r.headers.get("x-content-sha256") or "").lower()
    if got != str(want_sha).lower() or (hdr and hdr != got):
        return None, "checksum_mismatch"
    return data, ""


# ------------------------------------------------------------------ where a venue's files go
async def _location_for_cloud_venue(db, cloud_venue_id: str) -> Optional[Dict[str, Any]]:
    """Cloud venue id -> the data pull's id map -> the local venue -> its location (slug). None if the data pull has not brought it in yet."""
    from . import cloud_sync
    m = (cloud_sync._read().get("ids", {}).get("venue") or {}).get(str(cloud_venue_id))
    if not m:
        return None
    venue = await db.venues.find_one({"id": m.get("local_id")}, {"_id": 0})
    if not venue:
        return None
    loc = None
    if venue.get("location_id"):
        loc = await db.locations.find_one({"id": venue["location_id"]}, {"_id": 0})
    if not loc:
        loc = await db.locations.find_one({"venue_id": venue["id"]}, {"_id": 0})
    if not loc:
        from . import venue_sync
        loc = await venue_sync.ensure_location(db, venue)
    return loc


async def _save_location(db, loc: Dict[str, Any], changes: Dict[str, Any]) -> None:
    """Save a location change to the database AND Files/Locations/<slug>/location.json, the way the location routes do
    (locations_router._PersistingLocations). Without the second half the pictures would be lost the next time the app rebuilds from disk."""
    from . import locations_router as lr
    changes = {**changes, "updated_at": _now()}
    await db.locations.update_one({"id": loc["id"]}, {"$set": changes})
    row = await db.locations.find_one({"id": loc["id"]}, {"_id": 0})
    if row:
        lr._write_location_json(row)


def _picture_record(image_id: str, name: str, mime: str, size: int, order: int, ext: str) -> Dict[str, Any]:
    return {"id": image_id, "filename": name, "mime": mime, "size": size, "order": order, "uploaded_at": _now(),
            "uploaded_by": "cloud-sync", "ext": ext}


def _atomic_write(dest: Path, data: bytes) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(dest.parent), prefix=".cf_", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, dest)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


async def _put_picture(db, loc: Dict[str, Any], kind: str, f: Dict[str, Any], data: bytes) -> Tuple[bool, str]:
    """overlay / image: write <id>.<ext> into the location's folder and keep its record. A changed file replaces our own copy."""
    from . import locations_router as lr
    allowed = OVERLAY_EXT if kind == "overlay" else PICTURE_EXT
    ext = safe_ext(f.get("name"), allowed)
    if not ext:
        return False, "unsupported_type"
    field, getter = ("overlay_images", lr._overlays_dir) if kind == "overlay" else ("branding_images", lr._branding_dir)
    folder = getter(loc["slug"])
    image_id = stable_id(f["file_id"])
    for old in folder.glob(f"{image_id}.*"):                    # our own earlier copy of this Cloud file (e.g. it was a .png and is now a .gif)
        if old.suffix.lower() != ext:
            try:
                old.unlink()
            except OSError:
                pass
    _atomic_write(folder / f"{image_id}{ext}", data)
    mime = mimetypes.guess_type(f"x{ext}")[0] or "application/octet-stream"
    recs = [r for r in (loc.get(field) or []) if r.get("id") != image_id]
    cur = next((r for r in (loc.get(field) or []) if r.get("id") == image_id), None)
    rec = _picture_record(image_id, str(f.get("name") or f"{image_id}{ext}"), mime, len(data), (cur or {}).get("order", len(recs)), ext)
    if cur:
        rec["uploaded_at"] = cur.get("uploaded_at") or rec["uploaded_at"]
    recs.append(rec)
    recs.sort(key=lambda r: r.get("order", 0))
    await _save_location(db, loc, {field: recs})
    loc[field] = recs
    return True, ""


async def _put_sponsor(db, loc: Dict[str, Any], f: Dict[str, Any], data: bytes) -> Tuple[bool, str]:
    """sponsor: the location has ONE sponsor slide. A hand-made one is never replaced; only our own copy is."""
    from . import locations_router as lr
    ext = safe_ext(f.get("name"), PICTURE_EXT)
    if not ext:
        return False, "unsupported_type"
    cur = loc.get("sponsor_image") or None
    image_id = stable_id(f["file_id"])
    if cur and cur.get("uploaded_by") != "cloud-sync":
        return False, "kept_own_sponsor"
    folder = lr._sponsor_dir(loc["slug"])
    for old in folder.glob("*"):
        if old.is_file() and old.stem.startswith("cf"):
            try:
                old.unlink()
            except OSError:
                pass
    _atomic_write(folder / f"{image_id}{ext}", data)
    mime = mimetypes.guess_type(f"x{ext}")[0] or "application/octet-stream"
    rec = _picture_record(image_id, str(f.get("name") or f"{image_id}{ext}"), mime, len(data), 0, ext)
    await _save_location(db, loc, {"sponsor_image": rec})
    loc["sponsor_image"] = rec
    return True, ""


async def _put_host_image(db, f: Dict[str, Any], data: bytes) -> Tuple[bool, str]:
    """A host picture. person_id (the Cloud's id) -> the data pull's id map -> the person here -> their login -> Files/Hosts/<slug>/.
    The master admin and a person with no login here are left alone ('waiting' is reported by the caller). Only the file of the same
    kind is replaced, and only after the new one arrived complete."""
    from . import cloud_sync, employee_sync, admin_router
    from .files_router import host_folder, write_host_profile_json
    stem, field = HOST_KINDS[f["category"]]
    ext = safe_ext(f.get("name"), PICTURE_EXT)
    if not ext:
        return False, "unsupported_type"
    m = (cloud_sync._read().get("ids", {}).get("person") or {}).get(str(f.get("person_id")))
    if not m or m.get("master") or not m.get("local_id"):
        return False, "waiting_person" if not m else "master_untouched"
    emp = await db.employees.find_one({"id": m["local_id"]}, {"_id": 0})
    user = employee_sync.find_user((emp or {}).get("email", "")) if emp else None
    if not user or employee_sync.is_master(user):
        return False, "waiting_person"
    folder = host_folder(user.get("email") or user.get("id"))
    dest = folder / f"{stem}{ext}"
    _atomic_write(dest, data)
    for prior in folder.glob(f"{stem}.*"):                       # a png turned gif must not leave the stale png to be served
        if prior != dest:
            try:
                prior.unlink()
            except OSError:
                pass
    if user.get(field) != str(dest):
        user[field] = str(dest)
        admin_router._save_config()
        try:
            await admin_router._mirror_to_db(user)
        except Exception:                                          # noqa: BLE001  the config file is the truth
            pass
    try:
        write_host_profile_json(user)
    except Exception:                                              # noqa: BLE001
        pass
    return True, ""


async def _put_bighat(f: Dict[str, Any], data: bytes) -> Tuple[bool, str]:
    """A .bighat goes through the app's own importer (the lobby's Import button): same type detection, same folders, same cleaning."""
    from routes import bighat_files
    try:
        res = await bighat_files._import_zip_bytes(data)
    except Exception as e:                                       # noqa: BLE001  HTTPException or a bad file: one file never stops the rest
        return False, f"import_failed:{getattr(e, 'detail', e)}"[:160]
    return True, f"{res.type}:{res.name}"


async def _host_ready(db, f: Dict[str, Any]) -> bool:
    """True when the picture's person is here with a login and is not the master admin (checked BEFORE downloading, so nothing is fetched for nobody)."""
    from . import cloud_sync, employee_sync
    m = (cloud_sync._read().get("ids", {}).get("person") or {}).get(str(f.get("person_id")))
    if not m or m.get("master") or not m.get("local_id"):
        return False
    emp = await db.employees.find_one({"id": m["local_id"]}, {"_id": 0})
    user = employee_sync.find_user((emp or {}).get("email", "")) if emp else None
    return bool(user) and not employee_sync.is_master(user)


# ------------------------------------------------------------------ one pull
async def pull_once(db) -> Dict[str, Any]:
    """One pull. Never raises. Returns the public status."""
    if _LOCK.locked():
        return {**public_status(), "message": "A file sync is already running."}
    async with _LOCK:
        st = _read()
        st["last_pull"] = _now()
        counts = {"added": 0, "updated": 0, "unchanged": 0, "waiting": 0, "skipped": 0, "failed": 0}
        try:
            if not cloud_link.get_token() or not cloud_link.cloud_base_url():
                st.update(state="not_linked", message="This computer is not linked to BIG Hat Cloud.")
                _write(st)
                return public_status()
            m = await _fetch_manifest()
            if not m["ok"]:
                msg = {"unreachable": "Could not reach the cloud. Working from the local copy.",
                       "subscription_lapsed": "The Cloud subscription has lapsed. File sync is paused; this PC keeps working.",
                       "rate_limited": "The cloud asked us to slow down. Will try again.",
                       "unlinked": "The cloud no longer lists this computer as linked.",
                       "unauthorized": "The cloud did not accept this computer's access key."}.get(m["error"], "The cloud files could not be read right now.")
                st.update(state=m["error"], message=msg)
                _write(st)
                return public_status()
            for f in m["files"]:
                if not isinstance(f, dict) or not f.get("file_id") or f.get("category") not in KINDS:
                    counts["skipped"] += 1
                    continue
                fid, kind, sha = str(f["file_id"]), f["category"], str(f.get("sha256") or "").lower()
                seen = st["files"].get(fid)
                if seen and seen.get("sha256") == sha and seen.get("done"):
                    counts["unchanged"] += 1
                    continue
                loc = None
                if kind not in ("bighat",) and kind not in HOST_KINDS:
                    loc = await _location_for_cloud_venue(db, f.get("venue_id"))
                    if not loc:
                        counts["waiting"] += 1                    # the venue has not arrived yet: try again next pull
                        continue
                if kind in HOST_KINDS and not await _host_ready(db, f):
                    counts["waiting"] += 1                        # the person has not arrived (or is the master admin): nothing is fetched
                    continue
                limit = MAX_BIGHAT_BYTES if kind == "bighat" else MAX_PICTURE_BYTES
                if int(f.get("size") or 0) > limit:
                    st["failed"][fid] = {"name": f.get("name"), "why": "too_large", "at": _now()}
                    counts["failed"] += 1
                    continue
                data, why = await _download(fid, sha, limit)
                if data is None:
                    if why in ("unreachable", "unlinked", "subscription_lapsed", "rate_limited"):
                        st.update(state=why, message="The cloud stopped answering part-way. Will try again.")
                        _write(st)
                        return public_status()
                    st["failed"][fid] = {"name": f.get("name"), "why": why, "at": _now()}
                    counts["failed"] += 1
                    continue
                if kind == "bighat":
                    ok, note = await _put_bighat(f, data)
                elif kind in HOST_KINDS:
                    ok, note = await _put_host_image(db, f, data)
                elif kind == "sponsor":
                    ok, note = await _put_sponsor(db, loc, f, data)
                else:
                    ok, note = await _put_picture(db, loc, kind, f, data)
                if ok:
                    counts["updated" if seen else "added"] += 1
                    st["files"][fid] = {"sha256": sha, "kind": kind, "name": f.get("name"), "venue_id": f.get("venue_id"), "done": True, "at": _now(),
                                        "note": note if kind == "bighat" else ""}
                    st["failed"].pop(fid, None)
                elif note == "kept_own_sponsor":
                    counts["skipped"] += 1
                elif note in ("waiting_person", "master_untouched"):
                    counts["waiting" if note == "waiting_person" else "skipped"] += 1
                else:
                    st["failed"][fid] = {"name": f.get("name"), "why": note, "at": _now()}
                    counts["failed"] += 1
                _write(st)                                        # after every file: a crash never loses what already arrived
            st.update(last_ok=_now(), state="ok", last_counts=counts,
                      message=(f"Files synced. {counts['added']} new, {counts['updated']} changed, {counts['unchanged']} already here"
                               + (f", {counts['waiting']} waiting for their venue" if counts["waiting"] else "")
                               + (f", {counts['failed']} could not be used" if counts["failed"] else "") + "."))
            _write(st)
            return public_status()
        except Exception as e:                                     # noqa: BLE001
            logger.error("cloud file sync failed: %s: %s", type(e).__name__, e)
            st.update(state="error", message=f"File sync stopped safely ({type(e).__name__}). Nothing was lost.")
            try:
                _write(st)
            except Exception:                                      # noqa: BLE001
                pass
            return public_status()


async def keep_pulling(db, every: int = PULL_EVERY) -> None:
    """Background loop: after the data pull has had a minute to bring the venues in, pull files every 5 minutes (slower after errors)."""
    await asyncio.sleep(60)
    wait = every
    while True:
        try:
            res = await pull_once(db)
            wait = every if res.get("state") in ("ok", "idle", "not_linked") else min(wait * 2, 1800)
            await asyncio.sleep(wait)
        except asyncio.CancelledError:
            raise
        except Exception as e:                                     # noqa: BLE001
            logger.warning("cloud file loop: %s", e)
            await asyncio.sleep(every)
