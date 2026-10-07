"""alpha.80: the Schedule's VENUES are the single list of places for the whole app.

A venue (name, address, pay setting) is the master record.  Its `location` (branding images, overlays, assigned
admins, the Files/Locations/<slug>/ folder) is created from it automatically and kept in step:

    add a venue      -> a location with the same name is created (or an existing one with that name is linked)
    rename a venue   -> the location's display name changes; its slug / image folder do NOT move
    delete a venue   -> the location is retired (hidden from every list) but its images are KEPT;
                        adding the venue again by name brings it back with its images
    startup          -> reconcile(): every location gets a venue, every venue gets a location

Links: venue["location_id"] and location["venue_id"].  Matching by name ignores case, spaces and punctuation.
All functions take the database handle so they work with MontyDB (desktop) and MongoDB (cloud) alike.
"""
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("bighat-venue-sync")


def name_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (name or "").lower())


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").strip().lower()).strip("-")
    return s[:63] or "location"


async def _unique_slug(db, name: str) -> str:
    base = _slugify(name)
    slug, n = base, 2
    while await db.locations.find_one({"slug": slug}, {"_id": 1}):
        slug = f"{base}-{n}"
        n += 1
    return slug


async def _find_location_by_name(db, name: str) -> Optional[Dict[str, Any]]:
    key = name_key(name)
    if not key:
        return None
    for loc in await db.locations.find({}, {"_id": 0}).to_list(2000):
        if name_key(loc.get("name", "")) == key:
            return loc
    return None


def _persist(loc: Dict[str, Any]) -> None:
    """Mirror to Files/Locations/<slug>/location.json (+ the AppData safety copy) like every other location write."""
    try:
        from native import locations_router as lr
        lr._branding_dir(loc["slug"])
        lr._overlays_dir(loc["slug"])
        lr._write_location_json(loc)
    except Exception as e:                                        # noqa: BLE001
        logger.warning("could not write location.json for %s: %s", loc.get("slug"), e)


async def ensure_location(db, venue: Dict[str, Any], created_by: str = "venue-sync") -> Optional[Dict[str, Any]]:
    """Make sure `venue` has a live location; link both ways.  Returns the location.  Never raises."""
    try:
        name = (venue.get("name") or "").strip()
        if not name:
            return None
        loc = None
        if venue.get("location_id"):
            loc = await db.locations.find_one({"id": venue["location_id"]}, {"_id": 0})
        if loc is None:
            loc = await _find_location_by_name(db, name)         # an existing place with this name (maybe retired)
            # never take over a location that already belongs to a DIFFERENT venue ("Zed's" and "Zed S" match loosely
            # but are two places)
            if loc is not None and loc.get("venue_id") and loc["venue_id"] != venue["id"] \
                    and await db.venues.find_one({"id": loc["venue_id"]}, {"_id": 0, "id": 1}):
                loc = None
        if loc is None:
            now = _now()
            loc = {"id": str(uuid.uuid4()), "name": name, "slug": await _unique_slug(db, name),
                   "branding_images": [], "overlay_images": [], "assigned_user_ids": [],
                   "created_at": now, "updated_at": now, "created_by": created_by, "venue_id": venue["id"]}
            await db.locations.insert_one({"_id": loc["id"], **loc})
        else:
            changes = {}
            if loc.get("venue_id") != venue["id"]:
                changes["venue_id"] = venue["id"]
            if loc.get("retired"):
                changes["retired"] = False                        # the venue is back: images reattach
            if loc.get("name") != name:
                changes["name"] = name
            if changes:
                changes["updated_at"] = _now()
                await db.locations.update_one({"id": loc["id"]}, {"$set": changes})
                loc = {**loc, **changes}
        if venue.get("location_id") != loc["id"]:
            await db.venues.update_one({"id": venue["id"]}, {"$set": {"location_id": loc["id"]}})
        _persist(loc)
        return loc
    except Exception as e:                                        # noqa: BLE001  the Schedule must never fail because of this
        logger.warning("ensure_location failed for %s: %s", venue.get("name"), e)
        return None


async def rename(db, venue: Dict[str, Any]) -> None:
    await ensure_location(db, venue)                              # ensure_location also applies a changed name


async def retire(db, venue: Dict[str, Any]) -> None:
    """Venue deleted: hide its location everywhere but keep the images and settings."""
    try:
        loc = None
        if venue.get("location_id"):
            loc = await db.locations.find_one({"id": venue["location_id"]}, {"_id": 0})
        if loc is None:
            loc = await _find_location_by_name(db, venue.get("name", ""))
        if loc is None:
            return
        await db.locations.update_one({"id": loc["id"]}, {"$set": {"retired": True, "updated_at": _now()}})
        _persist({**loc, "retired": True})
    except Exception as e:                                        # noqa: BLE001
        logger.warning("retire failed for %s: %s", venue.get("name"), e)


async def reconcile(db) -> Dict[str, int]:
    """Startup: link every venue to a location and every location to a venue.  Safe to run any number of times."""
    out = {"venues": 0, "locations_created": 0, "venues_created": 0, "linked": 0}
    try:
        venues = await db.venues.find({}, {"_id": 0}).to_list(2000)
        out["venues"] = len(venues)
        try:
            await db.venues.update_many({"notes": {"$regex": "^Added from your Trivia Setup"}}, {"$set": {"notes": ""}})
        except Exception:                                         # noqa: BLE001  (cosmetic clean-up only)
            pass
        for v in venues:
            before = await db.locations.count_documents({})
            had = bool(v.get("location_id"))
            loc = await ensure_location(db, v)
            if loc is not None:
                if await db.locations.count_documents({}) > before:
                    out["locations_created"] += 1
                elif not had:
                    out["linked"] += 1
        # alpha.92: the Schedule is the ONLY place venues are created. A location (picture folder) with no
        # Schedule venue is simply not listed; it is never turned into a venue.
        if any(out[k] for k in ("locations_created", "venues_created", "linked")):
            logger.info("[venue-sync] reconcile: %s", out)
    except Exception as e:                                        # noqa: BLE001
        logger.warning("[venue-sync] reconcile failed: %s", e)
    return out


# ------------------------------------------------------------------ alpha.86: one rule for "which venues are on for this game"
GAME_PRICE_FIELD = {"trivia": "trivia_price", "bingo": "music_bingo_price", "karaoke": "karaoke_price"}


async def ensure_all_linked(db) -> Dict[str, int]:
    """Safe to call at any time (it is cheap when everything is already linked).
    Called at startup AND whenever a list of places is asked for, so a place that appears later
    (a folder restored from OneDrive, a pulled Setup Package) gets its Schedule venue right away,
    instead of only after the next restart."""
    return await reconcile(db)


async def venue_prices(db) -> Dict[str, Dict[str, float]]:
    """venue id -> {trivia_price, music_bingo_price, karaoke_price}."""
    out: Dict[str, Dict[str, float]] = {}
    for p in await db.venue_pricing.find({}, {"_id": 0}).to_list(5000):
        vid = p.get("venue_id")
        if vid:
            out[vid] = {f: float(p.get(f) or 0) for f in GAME_PRICE_FIELD.values()}
    return out


async def venues_for_game(db, game: str) -> List[Dict[str, Any]]:
    """THE rule (user, 2026-10-06): the Schedule's venues are the source of truth, and a venue is available for a game
    only when that game's price is above $0.  Returns the venue records (with their `location_id`), A to Z."""
    field = GAME_PRICE_FIELD.get(game)
    if not field:
        return []
    prices = await venue_prices(db)
    venues = await db.venues.find({}, {"_id": 0}).to_list(5000)
    # alpha.92: a venue with no prices entered yet is listed everywhere; once any game is priced, only priced games list it
    def _listed(v):
        pr = prices.get(v.get("id"))
        if not pr or not any(x > 0 for x in pr.values()):
            return True                      # no prices entered at all yet: show it everywhere
        return pr.get(field, 0.0) > 0        # some game is priced: show it only for games that are priced
    on = [v for v in venues if _listed(v)]
    on.sort(key=lambda v: (v.get("name") or "").lower())
    return on


async def location_ids_for_game(db, game: str) -> set:
    """The ids of the LOCATIONS (picture folders) that belong to venues available for this game.
    alpha.90: a venue's place is found three ways, so a priced venue can never lose its place:
      1. the location its own location_id points to, IF that location still exists
      2. any location whose venue_id points back at the venue
      3. the location with the same name"""
    ids = set()
    locs = await db.locations.find({}, {"_id": 0, "id": 1, "name": 1, "venue_id": 1, "retired": 1}).to_list(5000)
    live = {l["id"]: l for l in locs if l.get("id") and not l.get("retired")}
    for v in await venues_for_game(db, game):
        found = set()
        lid = v.get("location_id")
        if lid and lid in live:
            found.add(lid)
        for l in live.values():
            if l.get("venue_id") == v.get("id"):
                found.add(l["id"])
        if not found:
            loc = await _find_location_by_name(db, v.get("name", ""))
            if loc and loc.get("id") in live:
                found.add(loc["id"])
        ids |= found
    return ids
