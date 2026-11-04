"""v32.2.11: "Update schedule from the Cloud": make this PC's schedule match BIG Hat Cloud, safely.

Why: the normal sync is INCREMENTAL (it asks "what changed since last time"). Anything it had to skip, hold back, or keep as a conflict is never sent
again, so a PC can drift from the Cloud with no message. This reads the Cloud's COMPLETE current schedule and compares it with this PC, event by event.

Two steps that share ONE comparison, so what you preview is exactly what happens:
  check()  read-only. Lists what would be ADDED, UPDATED, REMOVED, and what is deliberately LEFT ALONE (with the reason). Changes nothing.
  apply()  only with the host's confirmation of that same check. Backs the schedule up first, re-checks that nothing changed meanwhile, then applies it.

Safety rules (owner: "no duplicates, no unnecessary deletes"):
  * an event is matched by the Cloud id this PC already tracks; else by (venue, event type, date+time) like the normal sync, so it is never added twice
  * only events this PC CREATED from the Cloud can be removed, and only when the Cloud no longer has them and they were not edited here; anything made or edited on this PC stays
  * an event edited on this PC since the last sync is never overwritten: it is listed under "left alone" so the host knows
  * nothing is removed when the Cloud list could not be read in full (empty / short / error = no removals, ever)
  * a person is never deleted; a venue or event type the PC does not have yet is waited on, not guessed
"""
import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from . import cloud_link, cloud_sync

logger = logging.getLogger("bighat-schedule-reconcile")
MAX_LIST = 300


def _t(v: Any) -> str:
    """Event type for MATCHING only: 'Trivia' and 'trivia' are the same thing (this can only make two events match, never split them)."""
    return str(v or "").strip().lower()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _read_cloud_events() -> Dict[str, Any]:
    """The Cloud's complete current events (+ venues + people) via the same feed the sync uses, read from sequence 0. Never writes anything."""
    if not cloud_link.get_token() or not cloud_link.cloud_base_url():
        return {"ok": False, "error": "unlinked", "message": "This computer is not linked to BIG Hat Cloud."}
    r = await cloud_sync._fetch_all(0)
    if not r["ok"]:
        msg = {"unreachable": "Could not reach the Cloud. Nothing was changed.",
               "subscription_lapsed": "The Cloud subscription has lapsed. Nothing was changed.",
               "unauthorized": "The Cloud did not accept this computer's access key."}.get(r.get("error"), "The Cloud could not be read right now.")
        return {"ok": False, "error": r.get("error") or "error", "message": msg}
    if r.get("resync"):
        return {"ok": False, "error": "resync", "message": "The Cloud asked for a fresh start. Try again in a moment."}
    live: Dict[str, Dict[str, Any]] = {}
    for it in r["items"]:                                          # the feed is a log: the LAST entry for an item wins, a delete removes it
        if it.get("kind") != "event":
            continue
        cid = str(it.get("item_id"))
        if it.get("deleted") or not it.get("data"):
            live.pop(cid, None)
        else:
            live[cid] = it["data"]
    return {"ok": True, "events": live, "seq": r["seq"], "count": len(live)}


def _digest(plan: Dict[str, Any]) -> str:
    keys = {k: sorted((x["cloud_id"] for x in plan[k])) for k in ("add", "update", "remove")}
    return hashlib.sha256(json.dumps(keys, sort_keys=True).encode()).hexdigest()[:20]


def _row(cloud_id: str, data: Optional[Dict[str, Any]], local: Optional[Dict[str, Any]] = None, why: str = "") -> Dict[str, Any]:
    d = data or {}
    l = local or {}
    return {"cloud_id": cloud_id, "title": d.get("title") or l.get("title") or "", "date": str(d.get("date") or l.get("date") or "")[:16],
            "event_type": d.get("event_type") or l.get("event_type") or "", "why": why}


async def build_plan(db, st: Dict[str, Any], cloud: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Compare. Pure with respect to the schedule: reads this PC, writes nothing."""
    plan: Dict[str, List[Dict[str, Any]]] = {"add": [], "update": [], "remove": [], "same": [], "left_alone": [], "waiting": []}
    ids_ev = st["ids"]["event"]
    ids_venue = st["ids"]["venue"]
    locals_ = {e["id"]: e for e in await db.events.find({}, {"_id": 0}).to_list(100000)}
    seen_local: set = set()
    local_by_slot: Dict[tuple, str] = {}
    for e in locals_.values():
        local_by_slot.setdefault((e.get("venue_id"), _t(e.get("event_type")), str(e.get("date"))[:16]), e["id"])
    for cid, data in cloud.items():
        vmap = ids_venue.get(str(data.get("venue_id")))
        if not vmap:
            plan["waiting"].append(_row(cid, data, why="its venue is not on this PC yet"))
            continue
        vid = vmap["local_id"]
        if data.get("claimed_by") and not await db.employees.find_one({"email": {"$regex": f"^{cloud_sync.re.escape(cloud_sync._email(data.get('claimed_by_email')))}$", "$options": "i"}}, {"_id": 0}):
            plan["waiting"].append(_row(cid, data, why="the host who claimed it is not on this PC yet"))
            continue
        m = ids_ev.get(cid)
        cur = locals_.get(m["local_id"]) if m else None
        if cur is None:                                            # not tracked (or tracked but gone here): match by venue + type + time, never add twice
            lid = local_by_slot.get((vid, _t(data.get("event_type")), str(data.get("date"))[:16]))
            cur = locals_.get(lid) if lid else None
            if cur is not None:
                plan["left_alone"].append(_row(cid, data, cur, "already on this PC at that time (matched, not added again)"))
                seen_local.add(cur["id"])
                continue
            plan["add"].append(_row(cid, data, why="in the Cloud, not on this PC"))
            continue
        seen_local.add(cur["id"])
        if m.get("fp") and cloud_sync._fp("event", cur) != m["fp"]:
            plan["left_alone"].append(_row(cid, data, cur, "edited on this PC since the last sync (kept as it is)"))
            continue
        want = {f: data.get(f) for f in cloud_sync.FIELDS["event"] if f in data and f not in ("claimed_by",)}
        have = {f: cur.get(f) for f in want}
        diff = [f for f in want if cloud_sync._norm(want[f]) != cloud_sync._norm(have[f])]
        if diff:
            plan["update"].append({**_row(cid, data, cur, "changed in the Cloud: " + ", ".join(diff)), "fields": diff})
        else:
            plan["same"].append(_row(cid, data, cur))
    # removals: ONLY events this PC created from the Cloud, that the Cloud no longer has, and nobody edited here
    for cid, m in ids_ev.items():
        if cid in cloud or not m.get("created") or not m.get("local_id"):
            continue
        cur = locals_.get(m["local_id"])
        if cur is None:
            continue
        if m.get("fp") and cloud_sync._fp("event", cur) != m["fp"]:
            plan["left_alone"].append(_row(cid, None, cur, "no longer in the Cloud, but edited on this PC (kept)"))
        else:
            plan["remove"].append(_row(cid, None, cur, "no longer in the Cloud"))
    on_pc_only = [e for i, e in locals_.items() if i not in seen_local and i not in {m.get("local_id") for m in ids_ev.values()}]
    return {"plan": plan, "on_this_pc_only": len(on_pc_only)}


async def check(db) -> Dict[str, Any]:
    """Read-only comparison. Returns a plan the host can read, with a `token` that apply() needs."""
    try:
        got = await _read_cloud_events()
        if not got["ok"]:
            return {**got, "can_apply": False}
        st = cloud_sync._read()
        res = await build_plan(db, st, got["events"])
        plan = res["plan"]
        # safety: an EMPTY or suspiciously short Cloud list never removes anything
        removals_allowed = got["count"] > 0 or not plan["remove"]
        if not removals_allowed:
            plan["left_alone"] += [{**r, "why": "the Cloud list was empty, so nothing is removed"} for r in plan["remove"]]
            plan["remove"] = []
        summary = {k: len(plan[k]) for k in plan}
        out = {"ok": True, "checked_at": _now(), "cloud_events": got["count"], "on_this_pc_only": res["on_this_pc_only"], "summary": summary,
               "token": _digest(plan), "plan": {k: v[:MAX_LIST] for k, v in plan.items() if k != "same"},
               "can_apply": bool(summary["add"] or summary["update"] or summary["remove"]),
               "message": ("This PC already matches the Cloud." if not (summary["add"] or summary["update"] or summary["remove"])
                           else f"{summary['add']} to add, {summary['update']} to update, {summary['remove']} to remove. Nothing has been changed yet.")}
        return out
    except Exception as e:                                         # noqa: BLE001
        logger.error("schedule check failed: %s: %s", type(e).__name__, e)
        return {"ok": False, "error": "error", "message": f"The check stopped safely ({type(e).__name__}). Nothing was changed.", "can_apply": False}


async def apply(db, token: str) -> Dict[str, Any]:
    """Apply EXACTLY what check() showed. Refuses if the host did not confirm that same check or the Cloud changed since."""
    if not token or not isinstance(token, str):
        return {"ok": False, "error": "no_token", "message": "Check the schedule first, then confirm."}
    async with cloud_sync._LOCK:                                   # never while the normal sync is running
        try:
            got = await _read_cloud_events()
            if not got["ok"]:
                return {**got}
            st = cloud_sync._read()
            res = await build_plan(db, st, got["events"])
            plan = res["plan"]
            if got["count"] == 0:
                plan["remove"] = []
            if _digest(plan) != token:
                return {"ok": False, "error": "changed", "message": "The schedule changed since you checked. Nothing was changed. Check again."}
            if not (plan["add"] or plan["update"] or plan["remove"]):
                return {"ok": True, "applied": {"added": 0, "updated": 0, "removed": 0}, "message": "This PC already matches the Cloud."}
            backup = await cloud_sync._backup_schedule(db)         # raises -> nothing is applied
            ctx = cloud_sync._Ctx(db, st)
            want_add = {r["cloud_id"] for r in plan["add"]} | {r["cloud_id"] for r in plan["update"]}
            for cid in want_add:                                   # the normal rules, one event at a time (venue, host, slot, conflict checks)
                try:
                    await cloud_sync._apply_event(ctx, {"item_id": cid, "kind": "event"}, got["events"][cid])
                except Exception as e:                             # noqa: BLE001 one bad event never stops the rest
                    ctx.conflict("event", cid, f"could not be applied ({type(e).__name__})")
            for r in plan["remove"]:
                await cloud_sync._remove(ctx, "event", {"item_id": r["cloud_id"], "kind": "event", "deleted": True})
            st["last_ok"] = _now()
            st["last_reconcile"] = {"at": _now(), "counts": dict(ctx.counts), "backup": backup}
            cloud_sync._write(st)
            return {"ok": True, "applied": {"added": ctx.counts["added"], "updated": ctx.counts["updated"], "removed": ctx.counts["removed"]},
                    "kept": ctx.counts["conflicts"], "backup": backup,
                    "message": f"Done. {ctx.counts['added']} added, {ctx.counts['updated']} updated, {ctx.counts['removed']} removed. A backup was saved first."}
        except Exception as e:                                     # noqa: BLE001
            logger.error("schedule apply failed: %s: %s", type(e).__name__, e)
            return {"ok": False, "error": "error", "message": f"The update stopped safely ({type(e).__name__}). Your backup was taken first."}
