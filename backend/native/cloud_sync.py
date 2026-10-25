"""Phase 3 of the Program <-> Cloud sync plan (memory/SYNC_PLAN.md, SYNC_CONTRACT.md): the ongoing PULL.

The Cloud is the master of venues, people, pricing, venue roles and events. Every 5 minutes (and at app start, and on
"Sync now") the Program asks GET /api/program/changes?since=<last_seq> with its access key and applies what came back.

Data-safety rules (the owner has zero tolerance for silent data loss):
  * State lives on disk: <AppData>/secure/cloud_sync.json, atomic write, a damaged file is kept as .bad (never replaced by empty).
  * FIRST PULL on a PC that already has its own venues/people/events does NOT apply anything. It shows a preview and waits
    for the host to press Apply (a full backup of the schedule is written first). Phase 2 (item-by-item choice) comes later.
  * Matching: venues by normalized name, people by lowercase email. Anything that matches is adopted; nothing local is deleted.
  * A local item the host changed since the last pull is NOT overwritten: it is kept and listed as a conflict.
  * Cloud removals only delete items this sync itself created. People (logins) are never deleted by a pull.
  * The master admin is never changed. Passwords are never synced; new people get a readable temporary password that is
    shown once (in memory only; it is never written to the sync file).
  * Offline / lapsed subscription / unlinked: the Program keeps working from its local copy; the pull just waits.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from . import cloud_link

logger = logging.getLogger("bighat-cloud-sync")

PULL_EVERY = 300          # seconds
PAGE = 500
KIND_ORDER = ("venue", "person", "venue_pricing", "venue_role", "event", "round_lock")

# fields that sync, per kind (the fingerprint covers exactly these)
FIELDS = {
    "venue": ("name", "address", "city", "state", "notes", "venue_pays_host_directly"),
    "person": ("name", "phone", "is_admin"),
    "venue_pricing": ("trivia_price", "music_bingo_price", "karaoke_price"),
    "venue_role": ("role_category", "role_type"),
    "event": ("title", "event_type", "date", "duration_hours", "pay_rate", "notes", "is_special_event", "status",
              "claimed_by", "claimed_at", "wore_big_hat", "social_media_posts", "winners_post"),
}
COLL = {"venue": "venues", "person": "employees", "venue_pricing": "venue_pricing", "venue_role": "venue_roles", "event": "events"}

_LOCK = asyncio.Lock()
_NEW_LOGINS: List[Dict[str, str]] = []          # one-time temporary passwords; memory only


# ------------------------------------------------------------------ state file
def _path() -> Path:
    return cloud_link._dir() / "cloud_sync.json"


def _blank() -> Dict[str, Any]:
    return {"last_seq": 0, "ids": {k: {} for k in KIND_ORDER}, "pending": {}, "conflicts": [], "first_link": "unknown",
            "last_pull": None, "last_ok": None, "state": "idle", "message": "", "last_counts": {}, "held_back": 0}


def _read() -> Dict[str, Any]:
    p = _path()
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(d, dict):
            b = _blank()
            b.update(d)
            for k in KIND_ORDER:
                b["ids"].setdefault(k, {})
            return b
    except FileNotFoundError:
        pass
    except (OSError, ValueError):
        try:
            os.replace(p, p.with_suffix(".json.bad"))        # keep the damaged file
        except OSError:
            pass
    return _blank()


def _write(st: Dict[str, Any]) -> None:
    p = _path()
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".cloudsync_", suffix=".tmp")
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


# ------------------------------------------------------------------ helpers
def _norm(v: Any) -> Any:
    if isinstance(v, bool) or v is None or isinstance(v, str):
        return v
    if isinstance(v, (int, float)):
        return float(v)
    return str(v)


def _fp(kind: str, doc: Dict[str, Any]) -> str:
    blob = json.dumps({f: _norm(doc.get(f)) for f in FIELDS[kind]}, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def _key(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def _email(s: str) -> str:
    return (s or "").strip().lower()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def take_new_logins() -> List[Dict[str, str]]:
    """Temporary passwords made by the last pulls. Returned ONCE, then forgotten."""
    out = list(_NEW_LOGINS)
    _NEW_LOGINS.clear()
    return out


def public_status() -> Dict[str, Any]:
    st = _read()
    return {"state": st["state"], "message": st["message"], "last_pull": st["last_pull"], "last_ok": st["last_ok"],
            "last_seq": st["last_seq"], "first_link": st["first_link"], "counts": st["last_counts"],
            "conflicts": st["conflicts"][-20:], "conflict_count": len(st["conflicts"]), "held_back": st["held_back"],
            "pending": len(st["pending"]), "new_logins_waiting": len(_NEW_LOGINS),
            "round_locks": _lock_status()}


def _lock_status() -> Dict[str, Any]:
    try:
        from native import cloud_locks
        return cloud_locks.public_status()
    except Exception:                                              # noqa: BLE001
        return {}


# ------------------------------------------------------------------ talking to the Cloud
async def _fetch(since: int) -> Dict[str, Any]:
    """One page of the change feed. Returns {ok, data} or {ok False, error, ...}. Never raises."""
    tok = cloud_link.get_token()
    base = cloud_link.cloud_base_url()
    if not tok or not base:
        return {"ok": False, "error": "unlinked"}
    try:
        async with httpx.AsyncClient(timeout=20.0) as c:
            r = await c.get(f"{base}/api/program/changes", params={"since": since, "limit": PAGE},
                            headers={"Authorization": f"Bearer {tok}"})
    except (httpx.HTTPError, ValueError):
        return {"ok": False, "error": "unreachable"}
    if r.status_code == 200:
        try:
            return {"ok": True, "data": r.json()}
        except ValueError:
            return {"ok": False, "error": "bad_response"}
    code = ""
    try:
        code = (r.json() or {}).get("error", "")
    except ValueError:
        pass
    if r.status_code == 402 or code == "subscription_lapsed":
        return {"ok": False, "error": "subscription_lapsed"}
    if r.status_code == 429:
        return {"ok": False, "error": "rate_limited"}
    if r.status_code == 401 and code == "unlinked":
        return {"ok": False, "error": "unlinked"}
    return {"ok": False, "error": "unauthorized" if r.status_code == 401 else "rejected", "status_code": r.status_code}


async def _fetch_all(since: int) -> Dict[str, Any]:
    items: List[Dict[str, Any]] = []
    seq = since
    resync = False
    for _ in range(200):
        r = await _fetch(seq)
        if not r["ok"]:
            return r
        d = r["data"]
        if d.get("resync_required"):
            return {"ok": True, "resync": True, "items": [], "seq": d.get("seq", 0)}
        items.extend(d.get("items") or [])
        seq = d.get("seq", seq)
        if not d.get("has_more"):
            break
    return {"ok": True, "resync": resync, "items": items, "seq": seq}


# ------------------------------------------------------------------ backup
async def _backup_schedule(db) -> str:
    """A dated copy of every synced collection, written BEFORE anything is applied. Raises if it cannot be written."""
    from native import schedule_safety
    dest = schedule_safety.folder() / "before-cloud-sync" / datetime.now().strftime("%Y%m%d-%H%M%S")
    dest.mkdir(parents=True, exist_ok=True)
    for name in ("venues", "employees", "venue_pricing", "venue_roles", "events"):
        rows = await getattr(db, name).find({}, {"_id": 0}).to_list(100000)
        (dest / f"{name}.json").write_text(json.dumps(rows, ensure_ascii=False, default=str, indent=1), encoding="utf-8")
    return str(dest)


async def _local_has_own_data(db) -> bool:
    """True when this PC already has schedule data of its own (the master admin's own employee row does not count)."""
    from native import employee_sync
    if await db.venues.count_documents({}) or await db.events.count_documents({}):
        return True
    for e in await db.employees.find({}, {"_id": 0}).to_list(1000):
        if not employee_sync.is_master(employee_sync.find_user(e.get("email", ""))):
            return True
    return False


# ------------------------------------------------------------------ applying
class _Ctx:
    def __init__(self, db, st):
        self.db, self.st = db, st
        self.counts = {"added": 0, "updated": 0, "removed": 0, "adopted": 0, "conflicts": 0, "held_back": 0, "waiting": 0}

    def ids(self, kind):
        return self.st["ids"][kind]

    def conflict(self, kind, item_id, why):
        self.counts["conflicts"] += 1
        self.st["conflicts"].append({"kind": kind, "item_id": item_id, "why": why, "at": _now()})
        self.st["conflicts"] = self.st["conflicts"][-200:]


def _local_id(ctx: _Ctx, kind: str, cloud_id: str) -> Optional[str]:
    m = ctx.ids(kind).get(str(cloud_id))
    return m["local_id"] if m else None


async def _apply_venue(ctx, item, data):
    db, cid = ctx.db, str(item["item_id"])
    m = ctx.ids("venue").get(cid)
    fields = {f: data.get(f) for f in FIELDS["venue"] if f in data}
    if m:
        cur = await db.venues.find_one({"id": m["local_id"]}, {"_id": 0})
        if cur:
            if m.get("fp") and _fp("venue", cur) != m["fp"]:
                return ctx.conflict("venue", cid, f"'{cur.get('name')}' was changed on this PC")
            await db.venues.update_one({"id": m["local_id"]}, {"$set": fields})
            m["fp"] = _fp("venue", {**cur, **fields})
            ctx.counts["updated"] += 1
            return
    match = None
    for v in await db.venues.find({}, {"_id": 0}).to_list(5000):
        if _key(v.get("name")) == _key(data.get("name")):
            match = v
            break
    if match:
        await db.venues.update_one({"id": match["id"]}, {"$set": fields})
        ctx.ids("venue")[cid] = {"local_id": match["id"], "created": False, "fp": _fp("venue", {**match, **fields})}
        ctx.counts["adopted"] += 1
        return
    doc = {"id": str(uuid.uuid4()), "address": "", "city": "", "state": "", "notes": None, "venue_pays_host_directly": False,
           "created_at": _now(), **fields}
    await db.venues.insert_one(dict(doc))
    ctx.ids("venue")[cid] = {"local_id": doc["id"], "created": True, "fp": _fp("venue", doc)}
    ctx.counts["added"] += 1


async def _apply_person(ctx, item, data):
    from native import employee_sync
    db, cid = ctx.db, str(item["item_id"])
    email = _email(data.get("email"))
    if not email or "@" not in email:
        return ctx.conflict("person", cid, "a person without a valid email was skipped")
    if employee_sync.is_master(employee_sync.find_user(email)):
        ctx.ids("person")[cid] = ctx.ids("person").get(cid) or {"local_id": None, "created": False, "fp": "", "master": True}
        return                                                    # the master admin is never changed
    fields = {"name": (data.get("name") or "").strip() or email, "phone": data.get("phone") or None,
              "is_admin": bool(data.get("is_admin"))}
    try:
        from native import cloud_profile
        before = cloud_profile.snapshot(email)                    # v32.3.1: so the name logic below cannot flatten a real profile
    except Exception:                                             # noqa: BLE001
        before = None
    m = ctx.ids("person").get(cid)
    cur = await db.employees.find_one({"id": m["local_id"]}, {"_id": 0}) if m and m.get("local_id") else None
    if not cur:
        cur = await db.employees.find_one({"email": {"$regex": f"^{re.escape(email)}$", "$options": "i"}}, {"_id": 0})
        if cur:
            m = None
    if cur:
        if m and m.get("fp") and _fp("person", cur) != m["fp"]:
            return ctx.conflict("person", cid, f"'{cur.get('name')}' was changed on this PC")
        await db.employees.update_one({"id": cur["id"]}, {"$set": fields})
        await employee_sync.upsert_user_for_employee(fields["name"], email, fields["is_admin"], fields["phone"], None, "")
        ctx.ids("person")[cid] = {"local_id": cur["id"], "created": bool(m and m.get("created")),
                                  "fp": _fp("person", {**cur, **fields}), **({"pfp": m["pfp"]} if m and m.get("pfp") else {})}
        ctx.counts["updated" if m else "adopted"] += 1
        await _apply_profile(ctx, cid, email, data, before)
        return
    doc = {"id": str(uuid.uuid4()), "email": email, "password": "", "created_at": _now(), **fields}
    await db.employees.insert_one(dict(doc))
    # v32.4.0: a person who ALREADY has a login on this PC (a hand-made program account) keeps their password. Before, the pull gave EVERY
    # person it created a new temporary password, which silently replaced that program password. Only a person with no login here gets one.
    had_login = employee_sync.find_user(email) is not None
    temp = None if had_login else employee_sync.make_temp_password()
    await employee_sync.upsert_user_for_employee(fields["name"], email, fields["is_admin"], fields["phone"], temp, "")
    if temp:
        _NEW_LOGINS.append({"email": email, "name": fields["name"], "temp_password": temp})
    ctx.ids("person")[cid] = {"local_id": doc["id"], "created": not had_login, "fp": _fp("person", doc)}
    ctx.counts["added"] += 1
    await _apply_profile(ctx, cid, email, data, before)          # a hand-made login with no employee row yet is protected too


async def _apply_profile(ctx, cid, email, data, before=None):
    """v32.3.1: the person's profile + settings from the Cloud (native/cloud_profile.py). Never stops the pull."""
    try:
        from native import cloud_profile
        await cloud_profile.apply_profile(ctx, cid, email, data, before)
    except Exception as e:                                        # noqa: BLE001
        logger.warning("cloud profile apply skipped for %s: %s", email, e)


async def _apply_pricing(ctx, item, data):
    db, cid = ctx.db, str(item["item_id"])
    vid = _local_id(ctx, "venue", data.get("venue_id") or cid)
    if not vid:
        return "wait"
    fields = {f: (data.get(f) or 0.0) for f in FIELDS["venue_pricing"]}
    cur = await db.venue_pricing.find_one({"venue_id": vid}, {"_id": 0})
    m = ctx.ids("venue_pricing").get(cid)
    if cur:
        if m and m.get("fp") and _fp("venue_pricing", cur) != m["fp"]:
            return ctx.conflict("venue_pricing", cid, "prices were changed on this PC")
        await db.venue_pricing.update_one({"venue_id": vid}, {"$set": {**fields, "updated_at": _now()}})
        ctx.ids("venue_pricing")[cid] = {"local_id": vid, "created": bool(m and m.get("created")), "fp": _fp("venue_pricing", {**cur, **fields})}
        ctx.counts["updated" if m else "adopted"] += 1
        return
    await db.venue_pricing.insert_one({"venue_id": vid, **fields, "created_at": _now(), "updated_at": _now()})
    ctx.ids("venue_pricing")[cid] = {"local_id": vid, "created": True, "fp": _fp("venue_pricing", fields)}
    ctx.counts["added"] += 1


async def _apply_role(ctx, item, data):
    db, cid = ctx.db, str(item["item_id"])
    vid = _local_id(ctx, "venue", data.get("venue_id"))
    eid = _local_id(ctx, "person", data.get("employee_id"))
    if not vid or not eid:
        return "wait"
    fields = {"role_category": data.get("role_category"), "role_type": data.get("role_type")}
    m = ctx.ids("venue_role").get(cid)
    cur = await db.venue_roles.find_one({"id": m["local_id"]}, {"_id": 0}) if m else None
    if not cur:
        cur = await db.venue_roles.find_one({"venue_id": vid, "employee_id": eid, **fields}, {"_id": 0})
        if cur:
            ctx.ids("venue_role")[cid] = {"local_id": cur["id"], "created": False, "fp": _fp("venue_role", cur)}
            ctx.counts["adopted"] += 1
            return
    if cur:
        if m.get("fp") and _fp("venue_role", cur) != m["fp"]:
            return ctx.conflict("venue_role", cid, "a role was changed on this PC")
        await db.venue_roles.update_one({"id": cur["id"]}, {"$set": {**fields, "venue_id": vid, "employee_id": eid}})
        m["fp"] = _fp("venue_role", {**cur, **fields})
        ctx.counts["updated"] += 1
        return
    doc = {"id": str(uuid.uuid4()), "venue_id": vid, "employee_id": eid, **fields, "created_at": _now()}
    await db.venue_roles.insert_one(dict(doc))
    ctx.ids("venue_role")[cid] = {"local_id": doc["id"], "created": True, "fp": _fp("venue_role", doc)}
    ctx.counts["added"] += 1


async def _local_employee_by_email(ctx, email):
    email = _email(email)
    if not email:
        return None
    return await ctx.db.employees.find_one({"email": {"$regex": f"^{re.escape(email)}$", "$options": "i"}}, {"_id": 0})


async def _apply_event(ctx, item, data):
    db, cid = ctx.db, str(item["item_id"])
    vid = _local_id(ctx, "venue", data.get("venue_id"))
    if not vid:
        return "wait"
    fields = {f: data.get(f) for f in FIELDS["event"] if f in data}
    claimer = None
    if data.get("claimed_by"):
        emp = await _local_employee_by_email(ctx, data.get("claimed_by_email"))
        if not emp:
            return "wait"                                          # the person arrives in a later pull
        claimer = emp["id"]
    fields["claimed_by"] = claimer
    m = ctx.ids("event").get(cid)
    cur = await db.events.find_one({"id": m["local_id"]}, {"_id": 0}) if m else None
    if cur:
        if m.get("fp") and _fp("event", cur) != m["fp"]:
            return ctx.conflict("event", cid, f"'{cur.get('title')}' was changed on this PC (claim or edit); kept")
        await db.events.update_one({"id": cur["id"]}, {"$set": {**fields, "venue_id": vid}})
        m["fp"] = _fp("event", {**cur, **fields})
        ctx.counts["updated"] += 1
        return
    for e in await db.events.find({"venue_id": vid, "event_type": data.get("event_type")}, {"_id": 0}).to_list(20000):
        if str(e.get("date"))[:16] == str(data.get("date"))[:16]:
            ctx.conflict("event", cid, f"'{e.get('title')}' already exists here at that time; kept as it is, not changed")
            ctx.ids("event")[cid] = {"local_id": e["id"], "created": False, "fp": _fp("event", e)}
            return
    doc = {"id": str(uuid.uuid4()), "venue_id": vid, "created_at": _now(), **fields}
    await db.events.insert_one(dict(doc))
    ctx.ids("event")[cid] = {"local_id": doc["id"], "created": True, "fp": _fp("event", doc)}
    ctx.counts["added"] += 1


async def _apply_round_lock(ctx, item, data):
    from native import cloud_locks
    return await cloud_locks.apply_item(ctx, item, data)


APPLY = {"venue": _apply_venue, "person": _apply_person, "venue_pricing": _apply_pricing,
         "venue_role": _apply_role, "event": _apply_event, "round_lock": _apply_round_lock}


async def _remove(ctx, kind, item):
    """A Cloud removal. Only things this sync created are deleted, and never a login."""
    cid = str(item["item_id"])
    m = ctx.ids(kind).get(cid)
    if not m:
        return
    if kind == "person":
        ctx.counts["held_back"] += 1                               # a pull never deletes a person or their login
        return
    if not m.get("created") or not m.get("local_id"):
        ctx.ids(kind).pop(cid, None)                               # it was here before the sync: keep it, just stop tracking
        return
    coll = getattr(ctx.db, COLL[kind])
    key = "venue_id" if kind == "venue_pricing" else "id"
    cur = await coll.find_one({key: m["local_id"]}, {"_id": 0})
    if cur and m.get("fp") and _fp(kind, cur) != m["fp"]:
        return ctx.conflict(kind, cid, "removed in the Cloud but changed on this PC; kept")
    if cur:
        await coll.delete_one({key: m["local_id"]})
        ctx.counts["removed"] += 1
    ctx.ids(kind).pop(cid, None)


async def apply_items(db, st: Dict[str, Any], items: List[Dict[str, Any]]) -> Dict[str, int]:
    ctx = _Ctx(db, st)
    work = {str(i["item_id"]) + "|" + i["kind"]: i for i in list(st["pending"].values()) + items if i.get("kind") in APPLY}
    ordered = sorted(work.values(), key=lambda i: KIND_ORDER.index(i["kind"]))
    st["pending"] = {}
    for it in ordered:
        kind = it["kind"]
        try:
            if it.get("deleted") or not it.get("data"):
                if kind != "round_lock":                           # a lock is never deleted from the Cloud, only released
                    await _remove(ctx, kind, it)
                continue
            if await APPLY[kind](ctx, it, it["data"]) == "wait":
                st["pending"][it["kind"] + "|" + str(it["item_id"])] = it
                ctx.counts["waiting"] += 1
        except Exception as e:                                     # noqa: BLE001 - one bad item must not stop the rest
            logger.warning("cloud sync: %s %s skipped: %s", kind, it.get("item_id"), e)
            ctx.conflict(kind, str(it.get("item_id")), f"could not be applied ({type(e).__name__})")
    st["held_back"] = st.get("held_back", 0) + ctx.counts["held_back"]
    try:                                                           # new venues get their Trivia/Bingo/Karaoke location
        from native import venue_sync
        await venue_sync.reconcile(db)
    except Exception as e:                                         # noqa: BLE001
        logger.warning("cloud sync: venue/location reconcile skipped: %s", e)
    return ctx.counts


# ------------------------------------------------------------------ the pull
def _preview(items: List[Dict[str, Any]]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for i in items:
        if i.get("data") and not i.get("deleted"):
            out[i["kind"]] = out.get(i["kind"], 0) + 1
    return out


async def pull_once(db, approve_first_link: bool = False) -> Dict[str, Any]:
    """One pull. Never raises. Returns the public status."""
    if _LOCK.locked():
        return {**public_status(), "message": "A sync is already running."}
    async with _LOCK:
        st = _read()
        st["last_pull"] = _now()
        try:
            if not cloud_link.get_token() or not cloud_link.cloud_base_url():
                st.update(state="not_linked", message="This computer is not linked to BIG Hat Cloud.")
                _write(st)
                return public_status()
            first = st["last_seq"] == 0 and not any(st["ids"][k] for k in KIND_ORDER)
            try:                                                   # tell the Cloud about local locks/releases first; never blocks the pull
                from native import cloud_locks
                await cloud_locks.push(db, st)
            except Exception as e:                                 # noqa: BLE001
                logger.warning("cloud sync: round-lock push skipped: %s", e)
            r = await _fetch_all(st["last_seq"])
            if not r["ok"]:
                msg = {"unreachable": "Could not reach the cloud. Working from the local copy.",
                       "subscription_lapsed": "The Cloud subscription has lapsed. Sync is paused; this PC keeps working.",
                       "rate_limited": "The cloud asked us to slow down. Will try again.",
                       "unlinked": "The cloud no longer lists this computer as linked.",
                       "unauthorized": "The cloud did not accept this computer's access key."}.get(r["error"], "The cloud could not be read right now.")
                st.update(state=r["error"], message=msg)
                _write(st)
                return public_status()
            if r.get("resync"):
                st.update(last_seq=0, state="resync", message="The cloud asked for a full re-read; doing it now.")
                _write(st)
                r = await _fetch_all(0)
                if not r["ok"]:
                    st.update(state=r["error"], message="Could not reach the cloud. Working from the local copy.")
                    _write(st)
                    return public_status()
            items = r["items"]
            if first and st["first_link"] != "approved" and not approve_first_link and await _local_has_own_data(db):
                st.update(state="needs_approval", first_link="needs_approval", last_counts={"preview": _preview(items)},
                          message="This computer already has its own schedule. Review and press Apply to merge the Cloud data in. Nothing has been changed.")
                _write(st)
                return public_status()
            backup = None
            if items:
                backup = await _backup_schedule(db)              # raises -> nothing is applied
            counts = await apply_items(db, st, items)
            st.update(last_seq=r["seq"], first_link="approved", last_ok=_now(), state="ok", last_counts=counts,
                      message=(f"Synced. {counts['added']} added, {counts['updated']} updated, {counts['adopted']} matched, "
                               f"{counts['removed']} removed, {counts['conflicts']} kept because changed here."
                               + (f" Backup: {backup}" if backup else "")))
            _write(st)
            return public_status()
        except Exception as e:                                     # noqa: BLE001
            logger.error("cloud sync failed: %s: %s", type(e).__name__, e)
            st.update(state="error", message=f"Sync stopped safely ({type(e).__name__}). Nothing was lost.")
            try:
                _write(st)
            except Exception:                                      # noqa: BLE001
                pass
            return public_status()


async def keep_pulling(db, every: int = PULL_EVERY) -> None:
    """Background loop: pull now, then every 5 minutes; slower after errors (max 30 minutes)."""
    wait = every
    while True:
        try:
            res = await pull_once(db)
            wait = every if res.get("state") in ("ok", "idle", "not_linked", "needs_approval") else min(wait * 2, 1800)
            await asyncio.sleep(wait)
        except asyncio.CancelledError:
            raise
        except Exception as e:                                     # noqa: BLE001
            logger.warning("cloud sync loop: %s", e)
            await asyncio.sleep(every)
