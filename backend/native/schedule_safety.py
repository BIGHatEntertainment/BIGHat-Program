"""alpha.92: the Schedule's data (every tab) is also kept as plain JSON files in AppData\\backups\\schedule.

  * every 60 seconds (and at shutdown) each Schedule collection is copied to its own file, but only when it changed
  * a collection that is EMPTY never overwrites a file that has data (so a wiped database cannot erase the copy)
  * at startup, a collection that is EMPTY while its file has data is filled back from the file
  * the last 10 copies of each file are kept in a dated folder, so a bad day can be undone by hand
Nothing here ever overwrites or deletes data that is in the database."""
from __future__ import annotations

import asyncio
import json
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict

logger = logging.getLogger("bighat-schedule-safety")

# every tab of the Schedule: Employees, Venues, Pricing, Roles, Events (+Weekly/Monthly), plus blackout dates and payments
COLLECTIONS = ["employees", "venues", "venue_pricing", "venue_roles", "events",
               "blackout_dates", "payment_acknowledgments", "monthly_archives"]
KEEP = 10


def folder() -> Path:
    from native.data_map import backups_dir
    p = backups_dir() / "schedule"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _file(name: str) -> Path:
    return folder() / f"{name}.json"


def _read(name: str):
    try:
        return json.loads(_file(name).read_text(encoding="utf-8"))
    except Exception:                                                   # noqa: BLE001
        return []


async def snapshot(db) -> Dict[str, int]:
    """Copy each Schedule collection to its file. Returns {collection: rows written}."""
    out: Dict[str, int] = {}
    for name in COLLECTIONS:
        try:
            rows = await getattr(db, name).find({}, {"_id": 0}).to_list(100000)
            if not rows:
                continue                                                 # empty never replaces a copy that has data
            text = json.dumps(rows, ensure_ascii=False, default=str, indent=1)
            f = _file(name)
            if f.is_file() and f.read_text(encoding="utf-8") == text:
                continue                                                 # unchanged
            if f.is_file():                                              # keep the previous copy, dated
                old = folder() / "history" / name
                old.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, old / (datetime.now().strftime("%Y%m%d-%H%M%S") + ".json"))
                for extra in sorted(old.glob("*.json"))[:-KEEP]:
                    extra.unlink(missing_ok=True)
            tmp = f.with_suffix(".tmp")
            tmp.write_text(text, encoding="utf-8")
            tmp.replace(f)                                               # never a half-written file
            out[name] = len(rows)
        except Exception as e:                                           # noqa: BLE001
            logger.warning("[schedule-safety] could not copy %s: %s", name, e)
    try:
        w = await write_venue_files(db)
        if w:
            out["venue_files"] = w
    except Exception as e:                                               # noqa: BLE001
        logger.warning("[schedule-safety] venue files: %s", e)
    return out


async def restore_if_empty(db) -> Dict[str, int]:
    """At startup: a Schedule collection that is empty, with a copy that has data, is filled from the copy."""
    out: Dict[str, int] = {}
    for name in COLLECTIONS:
        try:
            col = getattr(db, name)
            if await col.count_documents({}) > 0:
                continue
            rows = _read(name)
            if not rows:
                continue
            for r in rows:
                await col.insert_one(dict(r))
            out[name] = len(rows)
            logger.warning("[schedule-safety] %s was EMPTY; restored %d rows from the copy", name, len(rows))
        except Exception as e:                                           # noqa: BLE001
            logger.warning("[schedule-safety] could not restore %s: %s", name, e)
    try:
        r = await restore_venue_files(db)
        if r:
            out["venue_files"] = r
    except Exception as e:                                               # noqa: BLE001
        logger.warning("[schedule-safety] venue files restore: %s", e)
    return out


# ------------------------------------------------------------------ alpha.97: a file you can SEE, per venue
# Documents\\BIG Hat Entertainment\\Files\\Locations\\<venue>\\venue-data.json  holds that venue's Schedule data:
# its prices, its pay roles, its events and its blackout dates. Open it in any text editor to see what is saved.
PER_VENUE = {"venue_pricing": "pricing", "venue_roles": "roles", "events": "events", "blackout_dates": "blackout_dates"}


def _venue_file(slug: str) -> Path:
    from native.data_map import docs_root
    return docs_root() / "Locations" / slug / "venue-data.json"


def _slug(name: str) -> str:
    import re
    return re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")


async def write_venue_files(db) -> int:
    """Write one venue-data.json per venue (only when it changed). Returns how many files were written."""
    n = 0
    try:
        venues = await db.venues.find({}, {"_id": 0}).to_list(5000)
    except Exception:                                                    # noqa: BLE001
        return 0
    cols = {}
    for coll in PER_VENUE:
        try:
            cols[coll] = await getattr(db, coll).find({}, {"_id": 0}).to_list(100000)
        except Exception:                                                # noqa: BLE001
            cols[coll] = []
    for v in venues:
        slug = _slug(v.get("name", ""))
        if not slug or not v.get("id"):
            continue
        doc = {"venue": {k: v.get(k) for k in ("id", "name", "address", "city", "state", "zip_code", "phone") if k in v}}
        for coll, key in PER_VENUE.items():
            doc[key] = [r for r in cols[coll] if r.get("venue_id") == v["id"]]
        if not any(doc[k] for k in PER_VENUE.values()):
            continue                                                     # nothing entered yet: no empty file
        text = json.dumps(doc, ensure_ascii=False, default=str, indent=2)
        try:
            f = _venue_file(slug)
            if f.is_file() and f.read_text(encoding="utf-8") == text:
                continue
            f.parent.mkdir(parents=True, exist_ok=True)
            tmp = f.with_suffix(".tmp")
            tmp.write_text(text, encoding="utf-8")
            tmp.replace(f)
            n += 1
        except Exception as e:                                           # noqa: BLE001
            logger.warning("[schedule-safety] could not write venue file for %s: %s", slug, e)
    return n


async def restore_venue_files(db) -> int:
    """At startup: a venue that exists but has NO prices/roles/events in the database is refilled from its venue-data.json."""
    n = 0
    try:
        venues = await db.venues.find({}, {"_id": 0}).to_list(5000)
    except Exception:                                                    # noqa: BLE001
        return 0
    for v in venues:
        try:
            f = _venue_file(_slug(v.get("name", "")))
            if not f.is_file():
                continue
            doc = json.loads(f.read_text(encoding="utf-8"))
            for coll, key in PER_VENUE.items():
                rows = doc.get(key) or []
                if not rows:
                    continue
                col = getattr(db, coll)
                if await col.count_documents({"venue_id": v["id"]}) > 0:
                    continue                                             # something is there already: never overwrite it
                for r in rows:
                    r = dict(r); r["venue_id"] = v["id"]
                    await col.insert_one(r)
                n += len(rows)
        except Exception as e:                                           # noqa: BLE001
            logger.warning("[schedule-safety] could not restore venue file for %s: %s", v.get("name"), e)
    return n


async def keep_copying(db, every: int = 60) -> None:
    while True:
        try:
            await asyncio.sleep(every)
            await snapshot(db)
        except asyncio.CancelledError:
            try:
                await snapshot(db)                                       # last copy on the way out
            except Exception:                                            # noqa: BLE001
                pass
            raise
        except Exception as e:                                           # noqa: BLE001
            logger.warning("[schedule-safety] copy loop: %s", e)
