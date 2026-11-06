"""Linked PC: make the branding images and round overlays match the Cloud's (check first, then confirm).

Everything here depends on the Program being LINKED to a Cloud account. An unlinked Program never reaches this code and behaves as before.

What "match" means, and the rules (the owner has zero tolerance for silent data loss):
  * Only pictures the Cloud sync itself brought in (record uploaded_by == "cloud-sync", id cf<10 hex>) are ever removed here. A picture the owner
    put on this PC by hand is NEVER removed, even when linked.
  * A picture is "removed in the Cloud" only when the Cloud answered COMPLETELY (manifest `complete` is true and names this venue) and no longer
    lists it. An outage, an error, a partial or an old-style answer (no `complete` flag) removes NOTHING.
  * No run removes more than half of a venue's Cloud-brought pictures at once when it holds more than one (a glitch must never empty a venue).
    A venue with a single Cloud picture can still lose it. To remove more, confirm, then check again.
  * check() is read-only. remove(token) re-checks first (anything changed -> nothing removed), drops the file, the record AND the AppData safety copy,
    renumbers the rest, and writes a backup of the location's picture records first.
  * Tags and order: the Cloud's round tags and order are applied only to pictures the sync brought in AND the owner has not changed on this PC
    (see apply_meta). What the owner set by hand wins.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import cloud_files, cloud_link

logger = logging.getLogger("bighat.picture_mirror")
KIND_FIELD = {"image": "branding_images", "overlay": "overlay_images"}
KIND_DIR = {"image": "branding", "overlay": "overlays"}
MAX_REMOVE_FRACTION = 0.5
ALLOWED_TAGS = {"MC", "REG", "MISC", "MYS", "BIG", "ANS"} | {f"{k}{n}" for k in ("REG", "MISC") for n in range(1, 11)}


def clean_tags(raw: Any) -> Optional[List[str]]:
    """The Cloud's tags as the Program stores them: None (field absent = untagged), or a clean list ([] = dormant). Bad values are dropped."""
    if raw is None:
        return None
    if not isinstance(raw, list):
        return None
    out: List[str] = []
    for t in raw:
        u = str(t or "").strip().upper()
        if u in ALLOWED_TAGS and u not in out:
            out.append(u)
    return out


def _is_sync_made(rec: Dict[str, Any]) -> bool:
    return rec.get("uploaded_by") == "cloud-sync" and str(rec.get("id") or "").startswith("cf")


async def _location_for(db, cloud_venue_id: str) -> Optional[Dict[str, Any]]:
    """Cloud venue id -> this PC's location, through the same id map the pull uses. READ-ONLY: unlike the pull it never creates a location."""
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
    return loc or await db.locations.find_one({"venue_id": venue["id"]}, {"_id": 0})


async def _plan(db, manifest: Dict[str, Any]) -> Dict[str, Any]:
    """What would be removed, and what is left alone and why. Reads only: no file or database row is touched."""
    if manifest.get("complete") is not True or not isinstance(manifest.get("venues"), list):
        return {"safe": False, "why": "The Cloud did not say its picture list is complete, so nothing can be treated as removed.",
                "remove": [], "kept": [], "venues": 0}
    listed: Dict[tuple, set] = {}
    for f in manifest.get("files") or []:
        if isinstance(f, dict) and f.get("category") in KIND_FIELD and f.get("file_id"):
            listed.setdefault((str(f.get("venue_id") or ""), f["category"]), set()).add(cloud_files.stable_id(str(f["file_id"])))
    remove, kept, covered = [], [], 0
    for cloud_vid in [str(v) for v in manifest["venues"]]:
        loc = await _location_for(db, cloud_vid)
        if not loc:
            continue                                               # not brought in yet: nothing here to compare
        covered += 1
        for kind, field in KIND_FIELD.items():
            mine = [r for r in (loc.get(field) or []) if _is_sync_made(r)]
            gone = [r for r in mine if r["id"] not in listed.get((cloud_vid, kind), set())]
            if not gone:
                continue
            if len(mine) > 1 and len(gone) > len(mine) * MAX_REMOVE_FRACTION:        # one run never removes more than half of a venue's Cloud-brought pictures
                for r in gone:
                    kept.append({"venue": loc.get("name"), "kind": kind, "id": r["id"], "file": r.get("filename"),
                                 "why": "more than half of this venue's Cloud pictures look removed at once; nothing was removed (a glitch must not empty a venue)"})
                continue
            for r in gone:
                remove.append({"venue": loc.get("name"), "location_id": loc.get("id"), "slug": loc.get("slug"), "kind": kind,
                               "id": r["id"], "file": r.get("filename"), "ext": r.get("ext")})
    return {"safe": True, "remove": remove, "kept": kept, "venues": covered}


def _digest(plan: Dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(sorted((r["location_id"], r["kind"], r["id"]) for r in plan["remove"])).encode()).hexdigest()[:24]


async def check(db) -> Dict[str, Any]:
    if not cloud_link.get_token() or not cloud_link.cloud_base_url():
        return {"ok": False, "error": "not_linked", "message": "This computer is not linked to BIG Hat Cloud. Its pictures are managed here, as always."}
    m = await cloud_files._fetch_manifest()
    if not m["ok"]:
        why = {"unreachable": "Could not reach the Cloud.", "subscription_lapsed": "The Cloud subscription has lapsed.",
               "unauthorized": "The Cloud did not accept this computer's access key."}.get(m["error"], "The Cloud could not be read right now.")
        return {"ok": False, "error": m["error"], "message": why + " Nothing was changed."}
    plan = await _plan(db, m)
    out = {"ok": True, **plan, "token": _digest(plan) if plan["safe"] else "", "can_remove": len(plan["remove"])}
    if not plan["safe"]:
        out["message"] = plan["why"]
    elif plan["remove"]:
        out["message"] = f"{len(plan['remove'])} picture(s) the Cloud no longer has can be removed from this computer."
    else:
        out["message"] = "This computer's branding images and overlays match the Cloud."
    return out


async def remove(db, token: str) -> Dict[str, Any]:
    """Removes exactly what the last check listed. Re-checks first; a record backup is written before anything is removed."""
    if not token or not isinstance(token, str):
        return {"ok": False, "error": "no_token", "message": "Check first, then confirm."}
    plan = await check(db)
    if not plan.get("ok"):
        return plan
    if not plan.get("token") or plan["token"] != token:
        return {"ok": False, "error": "changed", "message": "The pictures or the Cloud changed since you checked. Nothing was removed. Check again."}
    from . import locations_router as lr
    by_loc: Dict[str, List[Dict[str, Any]]] = {}
    for r in plan["remove"]:
        by_loc.setdefault(r["location_id"], []).append(r)
    from native import schedule_safety
    dest = schedule_safety.folder() / "before-picture-match" / datetime.now().strftime("%Y%m%d-%H%M%S")
    dest.mkdir(parents=True, exist_ok=True)
    removed = 0
    for loc_id, rows in by_loc.items():
        loc = await db.locations.find_one({"id": loc_id}, {"_id": 0})
        if not loc:
            continue
        (dest / f"{loc.get('slug')}.json").write_text(json.dumps({k: loc.get(k) for k in ("branding_images", "overlay_images")}, indent=1, default=str), encoding="utf-8")
        for kind, field in KIND_FIELD.items():
            ids = {r["id"] for r in rows if r["kind"] == kind}
            if not ids:
                continue
            keep = [r for r in (loc.get(field) or []) if r.get("id") not in ids or not _is_sync_made(r)]
            gone = [r for r in (loc.get(field) or []) if r.get("id") in ids and _is_sync_made(r)]
            folder = lr._overlays_dir(loc["slug"]) if kind == "overlay" else lr._branding_dir(loc["slug"])
            for r in gone:
                p = folder / f"{r['id']}{r.get('ext') or '.bin'}"
                try:
                    if p.is_file():
                        p.unlink()
                except OSError as exc:
                    logger.warning("[picture-mirror] could not remove %s: %s", p, exc)
                lr._forget_picture(loc["slug"], KIND_DIR[kind], r["id"], r.get("ext"))
                removed += 1
            for i, r in enumerate(keep):
                r["order"] = i
            await cloud_files._save_location(db, loc, {field: keep})
            loc[field] = keep
    return {"ok": True, "removed": removed, "backup": str(dest),
            "message": f"Done. {removed} picture(s) removed to match the Cloud. A copy of the old list was saved first. Pictures you added yourself were not touched."}
