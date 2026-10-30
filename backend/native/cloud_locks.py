"""Round locks <-> BIG Hat Cloud (SYNC_CONTRACT kind `round_lock`, actions `lock` / `release`).

The PC stays authoritative for its own show builds. This module only
  PUSH  - tells the Cloud about new local locks, and about releases an admin made here
  PULL  - adds the locks other PCs made, and applies releases made in the Cloud
Nothing here can stop a show from building: every entry point swallows its own errors and the PC keeps its local locks.

Safety rules (owner wording, rules 1-4 of docs/CLOUD_TASK_round_locks.md):
  * a lock is only ever ADDED from the Cloud; a missing local record is NEVER read as a release by itself.
    A release is pushed ONLY when this PC's own tombstones (round_usage `released` / `released_rounds`) prove an admin released it.
  * a release from the Cloud wins over an older lock; a genuinely newer use (used_at later than released_at) stays locked.
  * an old Cloud copy cannot bring back a round this PC released (it is re-released in the Cloud instead).
State: <AppData>/secure/cloud_locks.json (atomic write, damaged file kept as .bad).
"""
import hashlib
import json
import logging
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from . import cloud_link

logger = logging.getLogger("bighat-cloud-locks")
BATCH = 200
MAX_BATCHES = 10


def _path() -> Path:
    return cloud_link._dir() / "cloud_locks.json"


def _blank() -> Dict[str, Any]:
    # pushed: local record id -> {item_id, venue (cloud id), rkey, expires}
    # released: cloud item_id -> released_at (this PC saw/did the release)
    # released_rounds: "<cloud venue>|<round key>" -> released_at
    return {"pushed": {}, "outbox": {}, "released": {}, "released_rounds": {}, "blocked": {}, "last_push": None,
            "last_message": "", "counts": {}}


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
            os.replace(p, p.with_suffix(".json.bad"))
        except OSError:
            pass
    return _blank()


def _write(st: Dict[str, Any]) -> None:
    p = _path()
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".cloudlocks_", suffix=".tmp")
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


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(d: Optional[datetime] = None) -> str:
    return (d or _now()).isoformat()


def _parse(s: Any) -> Optional[datetime]:
    import round_usage
    return round_usage._parse(s)


def _clean_uid(u):
    import round_uid
    return round_uid.clean(u)


def round_key(file_name: str) -> str:
    """Same rule as the Cloud (round_locks.round_key): lowercase stem, TYPE__ prefix and trailing -<8 hex> removed."""
    stem = (file_name or "").replace("\\", "/").rsplit("/", 1)[-1]
    if "." in stem:
        stem = stem.rsplit(".", 1)[0]
    stem = re.sub(r"^[a-z0-9]+__", "", stem.lower().strip())
    return re.sub(r"-[0-9a-f]{8}$", "", stem)


def lock_item_id(venue_id: str, rkey: str, presentation_id: Optional[str]) -> str:
    return hashlib.sha1(f"{venue_id}|{rkey}|{presentation_id or ''}".encode()).hexdigest()


# ------------------------------------------------------------------ venues: Cloud id <-> this PC's venue/location
async def _venue_identities(db, st_sync: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """cloud venue id -> {"ids": set of normalised identities, "name", "location_id"} for every venue linked to the Cloud."""
    import round_usage as ru
    out: Dict[str, Dict[str, Any]] = {}
    for cid, m in (st_sync.get("ids", {}).get("venue") or {}).items():
        v = await db.venues.find_one({"id": m.get("local_id")}, {"_id": 0})
        if not v:
            continue
        loc = None
        if v.get("location_id"):
            loc = await db.locations.find_one({"id": v["location_id"]}, {"_id": 0})
        raw = [v.get("id"), v.get("name"), v.get("location_id")] + ([loc.get("slug"), loc.get("name"), loc.get("id")] if loc else [])
        ids = {ru.norm_location(x) for x in raw if x} - {""}
        for k in list(ids):
            ids |= ru.venue_identities(k)
        out[str(cid)] = {"ids": ids, "name": v.get("name") or "", "location_id": (loc or {}).get("id") or v.get("location_id") or ""}
    return out


def _venue_of_record(rec: Dict[str, Any], venues: Dict[str, Dict[str, Any]]) -> Optional[str]:
    import round_usage as ru
    mine = {ru.norm_location(rec.get("location")), ru.norm_location(rec.get("locationId"))} - {""}
    if not mine:
        return None
    for cid, v in venues.items():
        if mine & v["ids"]:
            return cid
    return None


def _admin_email() -> str:
    """Who the Cloud is told released a round. The Cloud accepts account owners, master admins and admin employees."""
    try:
        from native.config import config_manager
        users = (config_manager.config or {}).get("users") or []
    except Exception:                                              # noqa: BLE001
        users = []
    for want in ("master_admin", "admin"):
        for u in users:
            if u.get("role") == want and u.get("email"):
                return str(u["email"]).strip().lower()
    return ""


# ------------------------------------------------------------------ PUSH
def _plan(st: Dict[str, Any], venues: Dict[str, Dict[str, Any]]) -> None:
    """Fill the outbox: new local locks, and releases PROVEN by this PC's own tombstones."""
    import round_usage as ru
    recs = ru._load()
    by_id = {r.get("id"): r for r in recs}
    now = _now()
    tomb_p, tomb_r = ru._released(), ru._released_rounds()
    for r in recs:                                                 # 1) new local locks
        rid = r.get("id")
        exp = _parse(r.get("expiresDate"))
        if not rid or rid in st["pushed"] or (exp and exp < now):
            continue
        cid = _venue_of_record(r, venues)
        if not cid:
            continue                                               # no linked Cloud venue yet: try again next time
        rk = round_key(r.get("roundFileName") or r.get("roundFile") or "")
        if not rk:
            continue
        iid = lock_item_id(cid, rk, r.get("presentationId"))
        st["pushed"][rid] = {"item_id": iid, "venue": cid, "rkey": rk, "expires": r.get("expiresDate") or "",
                             "uid": ru._uid_of(r) or ""}
        st["outbox"]["lock:" + rid] = {"action_id": "lock:" + rid, "type": "lock", "payload": {
            "item_id": iid, "venue_id": cid, "venue_name": venues[cid]["name"],
            "round_file_name": r.get("roundFile") or r.get("roundFileName") or "", "round_type": r.get("roundType") or "",
            "round_uid": ru._uid_of(r) or ru._uid_of(r.get("roundFile") or r.get("roundFileName") or "") or "",
            "used_at": r.get("usedDate") or _iso(), "expires_at": r.get("expiresDate") or "",
            "presentation_id": r.get("presentationId") or "", "presentation_name": r.get("presentationName") or "",
            "used_by": r.get("usedBy") or ""}}
    for rid, p in list(st["pushed"].items()):                      # 2) releases
        if rid in by_id:
            continue
        exp = _parse(p.get("expires"))
        if exp and exp < now:
            st["pushed"].pop(rid, None)                            # it simply expired: nothing to tell the Cloud
            continue
        puid = (ru.UID_PREFIX + p["uid"]) if p.get("uid") else None
        loc_proven = any((rk == p["rkey"] or (puid and rk == puid)) and venues.get(p["venue"]) and lk in venues[p["venue"]]["ids"]
                         for lk, rk in tomb_r)
        pres_proven = False
        # the record id carries no presentation key here, so the round-level tombstone is the proof
        if not (loc_proven or pres_proven):
            continue                                               # record is missing but nobody released it: leave the Cloud alone
        when = _iso()
        st["released"][p["item_id"]] = when
        st["released_rounds"][f"{p['venue']}|{p['rkey']}"] = when
        st["outbox"]["rel:" + p["item_id"]] = {"action_id": "rel:" + p["item_id"] + ":" + when, "type": "release",
                                               "payload": {"item_id": p["item_id"], "released_by": _admin_email(),
                                                           **({"round_uid": p["uid"]} if p.get("uid") else {})}}
        st["pushed"].pop(rid, None)


async def _post(actions: List[Dict[str, Any]]) -> Dict[str, Any]:
    tok, base = cloud_link.get_token(), cloud_link.cloud_base_url()
    if not tok or not base:
        return {"ok": False, "error": "unlinked"}
    try:
        async with httpx.AsyncClient(timeout=30.0) as c:
            r = await c.post(f"{base}/api/program/actions", json={"actions": actions}, headers={"Authorization": f"Bearer {tok}"})
    except (httpx.HTTPError, ValueError):
        return {"ok": False, "error": "unreachable"}
    if r.status_code == 200:
        try:
            return {"ok": True, "results": (r.json() or {}).get("results") or []}
        except ValueError:
            return {"ok": False, "error": "bad_response"}
    return {"ok": False, "error": "subscription_lapsed" if r.status_code == 402 else "rejected", "status_code": r.status_code}


async def push(db, st_sync: Dict[str, Any]) -> Dict[str, Any]:
    """Queue what changed here and send the outbox. Never raises; failures leave the outbox for the next cycle."""
    counts = {"sent": 0, "applied": 0, "duplicate": 0, "rejected": 0, "waiting": 0}
    try:
        st = _read()
        venues = await _venue_identities(db, st_sync)
        _plan(st, venues)
        _write(st)                                                 # the plan is saved BEFORE any network call
        for _ in range(MAX_BATCHES):
            keys = [k for k in st["outbox"] if k not in st["blocked"]][:BATCH]
            if not keys:
                break
            batch = [st["outbox"][k] for k in keys]
            r = await _post(batch)
            if not r["ok"]:
                st["last_message"] = {"unreachable": "Could not reach the Cloud; locks will be sent later.",
                                      "subscription_lapsed": "Cloud subscription lapsed; locks stay on this PC."}.get(r["error"], "The Cloud did not take the locks yet.")
                break
            by_action = {x.get("action_id"): x for x in r["results"]}
            for k, a in zip(keys, batch):
                res = by_action.get(a["action_id"])
                if not res:
                    counts["waiting"] += 1
                    continue
                counts["sent"] += 1
                kind = res.get("result")
                if kind in ("applied", "duplicate"):
                    counts[kind] += 1
                    st["outbox"].pop(k, None)
                elif res.get("reason") == "not_admin":             # keep it; an admin's e-mail may be linked later
                    st["blocked"][k] = "not_admin"
                    counts["rejected"] += 1
                else:                                              # released / unknown_venue / not_found: the Cloud's answer is final
                    counts["rejected"] += 1
                    st["outbox"].pop(k, None)
            _write(st)
        st["last_push"] = _iso()
        st["counts"] = counts
        _write(st)
    except Exception as e:                                         # noqa: BLE001  never stop a sync (or a show) over locks
        logger.warning("cloud locks: push skipped: %s: %s", type(e).__name__, e)
    return counts


# ------------------------------------------------------------------ PULL (called by cloud_sync.apply_items)
async def apply_item(ctx, item: Dict[str, Any], data: Dict[str, Any]) -> Optional[str]:
    """Apply one `round_lock` change. Returns "wait" when its venue is not here yet."""
    import round_usage as ru
    cid = str(data.get("venue_id") or "")
    venues = getattr(ctx, "_lock_venues", None)
    if venues is None:
        venues = ctx._lock_venues = await _venue_identities(ctx.db, ctx.st)
    v = venues.get(cid)
    if not v:
        return "wait"
    iid = str(item["item_id"])
    fname = data.get("round_file_name") or ""
    st = _read()
    if data.get("released"):
        n = ru.cloud_release(v["name"], v["location_id"], fname, data.get("released_at"), round_uid=data.get("round_uid"))
        for rid, p in list(st["pushed"].items()):
            if p["item_id"] == iid or (p["venue"] == cid and p["rkey"] == round_key(fname) and rid not in {r.get("id") for r in ru._load()}):
                st["pushed"].pop(rid, None)
        st["released"][iid] = data.get("released_at") or _iso()
        st["released_rounds"][f"{cid}|{round_key(fname)}"] = data.get("released_at") or _iso()
        _ruid = _clean_uid(data.get("round_uid"))
        if _ruid:
            st["released_rounds"][f"{cid}|{ru.UID_PREFIX}{_ruid}"] = data.get("released_at") or _iso()
        st["outbox"].pop("rel:" + iid, None)
        _write(st)
        if n:
            ctx.counts["removed"] += n
        return None
    exp = _parse(data.get("expires_at"))
    if exp and exp < _now():
        return None
    used = _parse(data.get("used_at"))
    _u = _clean_uid(data.get("round_uid"))
    rel = (_parse(st["released"].get(iid)) or _parse(st["released_rounds"].get(f"{cid}|{round_key(fname)}"))
           or (_parse(st["released_rounds"].get(f"{cid}|{ru.UID_PREFIX}{_u}")) if _u else None))
    if rel and (not used or used <= rel):                          # this PC released it: an older copy must not bring it back
        st["outbox"]["rel:" + iid] = {"action_id": "rel:" + iid + ":" + _iso(rel), "type": "release",
                                      "payload": {"item_id": iid, "released_by": _admin_email()}}
        _write(st)
        return None
    if ru.cloud_is_tombstoned(v["location_id"], v["name"], fname) and not rel:
        return None                                                # released here before locks were synced: stays released
    rid = ru.cloud_add(location_id=v["location_id"], location_name=v["name"], file_name=fname, round_uid=data.get("round_uid"),
                       round_type=data.get("round_type") or "",
                       used_at=data.get("used_at"), expires_at=data.get("expires_at"), used_by=data.get("used_by") or "",
                       presentation_id=data.get("presentation_id") or "", presentation_name=data.get("presentation_name") or "")
    if rid:
        st["pushed"][rid] = {"item_id": iid, "venue": cid, "rkey": round_key(fname), "expires": data.get("expires_at") or "",
                             "uid": _u or ""}
        _write(st)
        ctx.counts["added"] += 1
    return None


def public_status() -> Dict[str, Any]:
    st = _read()
    return {"last_push": st["last_push"], "outbox": len(st["outbox"]), "blocked": len(st["blocked"]),
            "tracked": len(st["pushed"]), "message": st["last_message"], "counts": st["counts"]}
