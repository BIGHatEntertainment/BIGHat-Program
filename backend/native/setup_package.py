"""Setup Package (alpha.85), desktop side.

Packages the SHARED setup of one business so another computer under the same license email can pull it
instead of retyping: venues, venue pricing, people (master admin, admins, hosts), who works where, and
location images. Never includes passwords, hashes, tokens or keys.

Local ids differ on every computer, so the package refers to venues by NAME and people by EMAIL; applying
turns them back into this computer's own ids.

build_package(db)         -> bytes (zip)         what this computer would publish
plan_apply(db, zip_bytes) -> dict                what a pull would change (changes nothing)
apply_package(db, zip_bytes, ...) -> dict        writes it in (people are added with a temporary password; the
                                                 master admin and any existing person's password are never touched)
"""
from __future__ import annotations

import hashlib
import io
import json
import logging
import re
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import employee_sync, venue_sync
from .config import config_manager

logger = logging.getLogger("bighat-setup-package")

FORMAT = "bighat-setup-package"
IMG_EXT = {"png", "jpg", "jpeg", "gif", "webp", "mp4", "webm", "mov"}
MAX_IMAGE_BYTES = 25 * 1024 * 1024
VENUE_FIELDS = ("name", "address", "city", "state", "notes", "venue_pays_host_directly")
PRICE_FIELDS = ("trivia_price", "music_bingo_price", "karaoke_price")


def _key(s: str) -> str:
    return venue_sync.name_key(s or "")


def _email(s: str) -> str:
    return employee_sync.norm_email(s or "")


# ------------------------------------------------------------------ reading this computer
async def _collect(db) -> Dict[str, Any]:
    venues = await db.venues.find({}, {"_id": 0}).to_list(2000)
    by_vid = {v["id"]: v for v in venues}
    emps = await db.employees.find({}, {"_id": 0}).to_list(5000)
    by_eid = {e["id"]: e for e in emps}
    cfg_users = {employee_sync.norm_email(u.get("email", "")): u for u in config_manager.config.get("users", []) or []}

    people = []
    for e in emps:
        em = _email(e.get("email", ""))
        u = cfg_users.get(em) or {}
        role = "master_admin" if employee_sync.is_master(u) else ("admin" if (e.get("is_admin") or u.get("role") == "admin") else "host")
        people.append({"email": em, "name": e.get("name", ""), "phone": e.get("phone") or u.get("phone"), "role": role, "is_admin": role in ("master_admin", "admin")})
    seen = {p["email"] for p in people}
    for em, u in cfg_users.items():                       # users that have a login but no employee row (e.g. the master on an old install)
        if em and em not in seen and u.get("role") in ("master_admin", "admin"):
            people.append({"email": em, "name": u.get("display_name") or f"{u.get('first_name','')} {u.get('last_name','')}".strip(),
                           "phone": u.get("phone"), "role": u.get("role"), "is_admin": True})

    venue_rows = [{k: v.get(k) for k in VENUE_FIELDS} for v in venues]
    pricing = []
    for p in await db.venue_pricing.find({}, {"_id": 0}).to_list(2000):
        v = by_vid.get(p.get("venue_id"))
        if v:
            pricing.append({"venue": v["name"], **{k: float(p.get(k) or 0) for k in PRICE_FIELDS}})
    roles = []
    for r in await db.venue_roles.find({}, {"_id": 0}).to_list(5000):
        v, e = by_vid.get(r.get("venue_id")), by_eid.get(r.get("employee_id"))
        if v and e:
            roles.append({"venue": v["name"], "email": _email(e.get("email", "")), "role_category": r.get("role_category"), "role_type": r.get("role_type")})
    return {"venues": venue_rows, "venue_pricing": pricing, "people": people, "venue_roles": roles}


def _location_images() -> List[Tuple[str, str, Path]]:
    """[(slug, 'branding'|'overlays', file)] for every location image on this computer."""
    from . import locations_router as lr
    out = []
    root = lr._files_locations_root()
    if not root.exists():
        return out
    for loc in sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith((".", "_"))):
        for kind in ("branding", "overlays"):
            d = loc / kind
            if d.is_dir():
                for f in sorted(d.iterdir()):
                    if f.is_file() and not f.name.startswith(".") and f.suffix.lstrip(".").lower() in IMG_EXT and f.stat().st_size <= MAX_IMAGE_BYTES:
                        out.append((loc.name, kind, f))
    return out


async def build_package(db) -> bytes:
    data = await _collect(db)
    images = _location_images()
    names = {l.get("slug"): l.get("name") for l in await db.locations.find({}, {"_id": 0, "slug": 1, "name": 1}).to_list(2000)}
    locs = []
    for slug in sorted({s for s, _, _ in images}):
        locs.append({"slug": slug, "name": names.get(slug) or slug,
                     "branding": [f.name for s, k, f in images if s == slug and k == "branding"],
                     "overlays": [f.name for s, k, f in images if s == slug and k == "overlays"]})
    doc = {"format": FORMAT, "format_version": 1, "built_at": datetime.now(timezone.utc).isoformat(), **data, "locations": locs}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("package.json", json.dumps(doc, indent=1, sort_keys=True))
        for slug, kind, f in images:
            z.write(f, f"images/{slug}/{kind}/{f.name}")
    return buf.getvalue()


async def _slug_map(db, pkg: Dict[str, Any]) -> Dict[str, Optional[str]]:
    """package folder name -> this computer's folder name for the SAME place (matched by name), or None if there is no such place here."""
    mine = {_key(l.get("name", "")): l.get("slug") for l in await db.locations.find({}, {"_id": 0, "slug": 1, "name": 1}).to_list(2000)}
    out: Dict[str, Optional[str]] = {}
    for l in pkg.get("locations", []):
        out[l.get("slug")] = mine.get(_key(l.get("name") or l.get("slug") or ""))
    return out


# ------------------------------------------------------------------ reading a package
def read_package(raw: bytes) -> Dict[str, Any]:
    z = zipfile.ZipFile(io.BytesIO(raw))
    doc = json.loads(z.read("package.json").decode("utf-8"))
    if doc.get("format") != FORMAT:
        raise ValueError("not a BIG Hat setup package")
    return doc


def _safe_member(name: str) -> Optional[Tuple[str, str, str]]:
    m = re.fullmatch(r"images/([A-Za-z0-9_.-]+)/(branding|overlays)/([^/\\]+)", name)
    if not m or ".." in name or m.group(1).startswith("."):
        return None
    if m.group(3).rsplit(".", 1)[-1].lower() not in IMG_EXT:
        return None
    return m.group(1), m.group(2), m.group(3)


async def plan_apply(db, raw: bytes) -> Dict[str, Any]:
    """What would a pull change here? Changes nothing. This is the 'does this computer differ?' check."""
    pkg = read_package(raw)
    mine = await _collect(db)
    have_v = {_key(v["name"]): v for v in mine["venues"]}
    have_p = {p["email"]: p for p in mine["people"]}
    have_price = {_key(p["venue"]): p for p in mine["venue_pricing"]}
    have_roles = {(_key(r["venue"]), r["email"], r["role_category"], r["role_type"]) for r in mine["venue_roles"]}
    plan = {"venues_new": [], "venues_changed": [], "pricing_new": [], "pricing_changed": [], "people_new": [], "people_changed": [],
            "roles_new": [], "images_new": 0, "images_total": 0, "warnings": []}
    for v in pkg.get("venues", []):
        cur = have_v.get(_key(v.get("name", "")))
        if not cur:
            plan["venues_new"].append(v.get("name"))
        elif any((cur.get(k) or "") != (v.get(k) or "") for k in ("address", "city", "state", "notes")) or bool(cur.get("venue_pays_host_directly")) != bool(v.get("venue_pays_host_directly")):
            plan["venues_changed"].append(v.get("name"))
    for p in pkg.get("venue_pricing", []):
        cur = have_price.get(_key(p.get("venue", "")))
        if not cur:
            plan["pricing_new"].append(p.get("venue"))
        elif any(abs(float(cur.get(k) or 0) - float(p.get(k) or 0)) > 0.001 for k in PRICE_FIELDS):
            plan["pricing_changed"].append(p.get("venue"))
    for p in pkg.get("people", []):
        cur = have_p.get(_email(p.get("email", "")))
        if not cur:
            plan["people_new"].append(p.get("email"))
        elif (cur.get("name") or "") != (p.get("name") or "") or bool(cur.get("is_admin")) != bool(p.get("is_admin")):
            plan["people_changed"].append(p.get("email"))
    for r in pkg.get("venue_roles", []):
        if (_key(r.get("venue", "")), _email(r.get("email", "")), r.get("role_category"), r.get("role_type")) not in have_roles:
            plan["roles_new"].append(f"{r.get('email')} @ {r.get('venue')}")
    z = zipfile.ZipFile(io.BytesIO(raw))
    from . import locations_router as lr
    root = lr._files_locations_root()
    smap = await _slug_map(db, pkg)
    new_venue_keys = {_key(n or "") for n in plan["venues_new"]}
    for n in z.namelist():
        m = _safe_member(n)
        if m:
            plan["images_total"] += 1
            dest_slug = smap.get(m[0])
            place = next((l.get("name") for l in pkg.get("locations", []) if l.get("slug") == m[0]), m[0])
            if dest_slug is None:
                # the place does not exist here yet: it will if the venue is also being added by this pull
                if _key(place or "") in new_venue_keys:
                    plan["images_new"] += 1
            elif not (root / dest_slug / m[1] / m[2]).exists():
                plan["images_new"] += 1
    pkg_emails = {_email(p.get("email", "")) for p in pkg.get("people", [])}
    extra = sorted(e for e in have_p if e not in pkg_emails)
    if extra:
        plan["warnings"].append(f"{len(extra)} people on this computer are not in the package; they are left as they are")
    plan["differs"] = any(plan[k] for k in ("venues_new", "venues_changed", "pricing_new", "pricing_changed", "people_new", "people_changed", "roles_new")) or plan["images_new"] > 0
    return plan


# ------------------------------------------------------------------ applying a package
async def apply_package(db, raw: bytes, *, overwrite_changed: bool = False) -> Dict[str, Any]:
    """Write a package into this computer. Adds what is missing. Existing venues/people are only changed when
    overwrite_changed is True. NEVER touches the master admin or anyone's existing password."""
    pkg = read_package(raw)
    out = {"venues_added": 0, "venues_updated": 0, "pricing_set": 0, "people_added": [], "people_updated": 0, "roles_added": 0,
           "images_added": 0, "skipped": []}
    # --- venues (also creates each venue's location through the existing venue sync)
    vid_by_key: Dict[str, str] = {}
    for v in await db.venues.find({}, {"_id": 0, "id": 1, "name": 1}).to_list(2000):
        vid_by_key[_key(v["name"])] = v["id"]
    for v in pkg.get("venues", []):
        name = (v.get("name") or "").strip()
        if not name:
            out["skipped"].append("a venue with no name")
            continue
        k = _key(name)
        if k in vid_by_key:
            if overwrite_changed:
                await db.venues.update_one({"id": vid_by_key[k]}, {"$set": {f: v.get(f) for f in ("address", "city", "state", "notes", "venue_pays_host_directly") if f in v}})
                out["venues_updated"] += 1
            continue
        doc = {"id": str(uuid.uuid4()), "name": name, "address": v.get("address") or "", "city": v.get("city") or "", "state": v.get("state") or "",
               "notes": v.get("notes"), "venue_pays_host_directly": bool(v.get("venue_pays_host_directly")), "location_id": None,
               "created_at": datetime.now(timezone.utc).isoformat()}
        await db.venues.insert_one(doc)
        try:
            await venue_sync.ensure_location(db, doc)
        except Exception as e:                       # noqa: BLE001
            logger.warning("[package] location for %s: %s", name, e)
        vid_by_key[k] = doc["id"]
        out["venues_added"] += 1
    # --- people (login accounts + schedule employees); passwords are NEVER copied
    eid_by_email: Dict[str, str] = {}
    for e in await db.employees.find({}, {"_id": 0, "id": 1, "email": 1}).to_list(5000):
        eid_by_email[_email(e.get("email", ""))] = e["id"]
    default_pw = ""
    for p in pkg.get("people", []):
        em = _email(p.get("email", ""))
        if "@" not in em:
            out["skipped"].append(f"a person with no valid email ({p.get('name')})")
            continue
        existing = employee_sync.find_user(em)
        if employee_sync.is_master(existing) or p.get("role") == "master_admin":
            # the master admin is created on each computer during its own setup; a pulled package never creates or changes one
            if em not in eid_by_email and existing:
                await employee_sync.ensure_master_employee(db)
            continue
        is_admin = bool(p.get("is_admin")) or p.get("role") == "admin"
        if em in eid_by_email:
            if overwrite_changed:
                await db.employees.update_one({"id": eid_by_email[em]}, {"$set": {"name": p.get("name") or em, "phone": p.get("phone"), "is_admin": is_admin}})
                out["people_updated"] += 1
            continue
        temp = employee_sync.make_temp_password()
        eid = str(uuid.uuid4())
        await db.employees.insert_one({"id": eid, "name": p.get("name") or em, "email": em, "phone": p.get("phone"), "is_admin": is_admin,
                                       "password": "", "created_at": datetime.now(timezone.utc).isoformat()})
        await employee_sync.upsert_user_for_employee(p.get("name") or em, em, is_admin, p.get("phone"), temp, default_pw)
        eid_by_email[em] = eid
        out["people_added"].append({"email": em, "name": p.get("name") or em, "role": "admin" if is_admin else "host", "temp_password": temp})
    # --- pricing
    for pr in pkg.get("venue_pricing", []):
        vid = vid_by_key.get(_key(pr.get("venue", "")))
        if not vid:
            out["skipped"].append(f"pricing for unknown venue {pr.get('venue')}")
            continue
        cur = await db.venue_pricing.find_one({"venue_id": vid}, {"_id": 0})
        vals = {k: float(pr.get(k) or 0) for k in PRICE_FIELDS}
        now = datetime.now(timezone.utc).isoformat()
        if not cur:
            await db.venue_pricing.insert_one({"venue_id": vid, **vals, "created_at": now, "updated_at": now}); out["pricing_set"] += 1
        elif overwrite_changed:
            await db.venue_pricing.update_one({"venue_id": vid}, {"$set": {**vals, "updated_at": now}}); out["pricing_set"] += 1
    # --- who works where
    have = {(r["venue_id"], r["employee_id"], r["role_category"], r["role_type"]) for r in await db.venue_roles.find({}, {"_id": 0}).to_list(5000)}
    for r in pkg.get("venue_roles", []):
        vid, eid = vid_by_key.get(_key(r.get("venue", ""))), eid_by_email.get(_email(r.get("email", "")))
        if not vid or not eid:
            out["skipped"].append(f"a role for {r.get('email')} at {r.get('venue')} (person or venue not found)")
            continue
        sig = (vid, eid, r.get("role_category"), r.get("role_type"))
        if sig in have:
            continue
        if r.get("role_category") not in ("trivia", "bingo_karaoke") or r.get("role_type") not in ("primary", "secondary"):
            out["skipped"].append(f"a role for {r.get('email')} at {r.get('venue')} has an unknown type")
            continue
        # the app allows ONE primary host per venue and category; never create a second one
        if r.get("role_type") == "primary" and any(h[0] == vid and h[2] == r.get("role_category") and h[3] == "primary" for h in have):
            out["skipped"].append(f"{r.get('email')} is primary {r.get('role_category')} host at {r.get('venue')}, but this computer already has a different primary there")
            continue
        have.add(sig)
        await db.venue_roles.insert_one({"id": str(uuid.uuid4()), "venue_id": vid, "employee_id": eid, "role_category": r.get("role_category"),
                                         "role_type": r.get("role_type"), "created_at": datetime.now(timezone.utc).isoformat()})
        out["roles_added"] += 1
    # --- images: write the files, then let the existing hydrate rebuild the location records from disk
    from . import locations_router as lr
    z = zipfile.ZipFile(io.BytesIO(raw))
    root = lr._files_locations_root()
    smap = await _slug_map(db, pkg)                  # computed AFTER venues were added, so new places exist
    for n in z.namelist():
        m = _safe_member(n)
        if not m:
            continue
        dest_slug = smap.get(m[0])
        if not dest_slug:
            out["skipped"].append(f"image {m[2]}: this computer has no place called '{next((l.get('name') for l in pkg.get('locations', []) if l.get('slug') == m[0]), m[0])}'")
            continue
        dest = root / dest_slug / m[1] / m[2]
        if dest.exists():
            continue
        data = z.read(n)
        if len(data) > MAX_IMAGE_BYTES:
            out["skipped"].append(f"image {m[2]} is too big")
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".part")
        tmp.write_bytes(data)
        tmp.replace(dest)
        out["images_added"] += 1
    if out["images_added"]:
        try:
            await lr._hydrate_from_disk()
        except Exception as e:                       # noqa: BLE001
            out["skipped"].append(f"images were saved but the location list could not refresh yet: {e}")
    return out
