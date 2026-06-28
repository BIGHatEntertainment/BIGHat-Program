"""
/api/native/locations/* — Trivia Setup: per-location branding assets +
admin assignments.

What lives here
---------------
A "location" is a venue (Chicago, Cleveland, Phoenix-East, ...) for which
admins pre-load branding images / GIFs that play immediately AFTER each
round's host slide. Round count is decided per EVENT at presentation
build-time, not per location. Between-round sponsor rotations are
subscription-gated and live outside this router.

Auth model
----------
* master_admin   — full CRUD on every location, assigns admins.
* admin          — read + edit only locations whose `assigned_user_ids`
                   contains their user id. Cannot create/delete a
                   location and cannot change assignments.
* host           — no access (403).

Storage
-------
* Mongo collection `locations` — { id, name, slug, branding_images, ...}
* Image bytes — local FS under
      `<assets_root>/02_Locations/<slug>/branding/<image_id><ext>`
  matches the existing OverlayService convention so future overlay
  rendering reuses the same path layout.
"""
from __future__ import annotations

import logging
import mimetypes
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator

from .local_asset_service import _asset_root

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/native/locations", tags=["native-locations"])

# DB + user resolver injection (same pattern as admin_router)
_db = None
_user_resolver = None

# Allow-list for branding uploads. Stays narrow on purpose — we don't want
# admins uploading PDFs / EXEs etc. through the dashboard.
_ALLOWED_MIMES = {
    "image/png", "image/jpeg", "image/jpg", "image/gif",
    "image/webp",
}
_MAX_IMAGE_BYTES = 15 * 1024 * 1024     # 15 MB per image


def set_database(database) -> None:
    global _db
    _db = database


def set_current_user_resolver(resolver) -> None:
    global _user_resolver
    _user_resolver = resolver


async def _default_resolver(request: Request) -> Dict[str, Any]:
    try:
        from server import get_current_user  # type: ignore
    except ImportError as e:  # pragma: no cover
        logger.error("locations_router: get_current_user not importable: %s", e)
        raise HTTPException(500, detail="auth_unavailable")
    return await get_current_user(request)


async def _current_user(request: Request) -> Dict[str, Any]:
    resolver = _user_resolver or _default_resolver
    return await resolver(request)


def _user_id(user: Dict[str, Any]) -> Optional[str]:
    """Pull the canonical user identifier. `get_current_user` sets
    `_id` (string) for both native and legacy webapp users; `id` is
    only present in the native path. We standardise on `_id` so the
    assignment list interoperates with `/api/users` output.
    """
    return user.get("_id") or user.get("id")


def _is_master(user: Dict[str, Any]) -> bool:
    return (user or {}).get("role") == "master_admin"


def _is_admin_or_master(user: Dict[str, Any]) -> bool:
    return (user or {}).get("role") in ("master_admin", "admin")


async def _require_admin_or_master(request: Request) -> Dict[str, Any]:
    user = await _current_user(request)
    if not _is_admin_or_master(user):
        raise HTTPException(403, detail="admin_or_master_required")
    return user


async def _require_master(request: Request) -> Dict[str, Any]:
    user = await _current_user(request)
    if not _is_master(user):
        raise HTTPException(403, detail="master_admin_required")
    return user


async def _require_location_access(location_id: str, request: Request) -> tuple[Dict[str, Any], Dict[str, Any]]:
    """Return `(user, location_doc)` if this user may read/edit the location.

    master_admin: always allowed.
    admin:        only if `location.assigned_user_ids` contains their id.
    host:         never.
    """
    user = await _require_admin_or_master(request)
    loc = await _get_location_or_404(location_id)
    if _is_master(user):
        return user, loc
    # admin path: must be assigned
    assigned = set(loc.get("assigned_user_ids") or [])
    if _user_id(user) not in assigned:
        raise HTTPException(403, detail="not_assigned_to_location")
    return user, loc


# ----- Slug + name helpers -----
_SLUG_OK = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")


def _slugify(name: str) -> str:
    """Convert a friendly name into a filesystem-safe slug.

    Mirrors what the existing SharePoint convention does — lowercase,
    hyphenated, ASCII-only — so a "Phoenix East" location lands at
    `02_Locations/phoenix-east/` and is interoperable with the overlay
    pipeline if we ever need to cross-reference.
    """
    s = (name or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s[:63] or "location"


async def _get_location_or_404(location_id: str) -> Dict[str, Any]:
    if _db is None:
        raise HTTPException(500, detail="database_not_initialised")
    doc = await _db.locations.find_one({"id": location_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, detail="location_not_found")
    return doc


def _branding_dir(slug: str) -> Path:
    """Resolve `<assets_root>/02_Locations/<slug>/branding/` and mkdir."""
    root = _asset_root() / "02_Locations" / slug / "branding"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _strip_admin_only(doc: Dict[str, Any], viewer: Dict[str, Any]) -> Dict[str, Any]:
    """Admins don't need to see who else is assigned to a location (and
    it's faintly creepy). Master sees the full doc.
    """
    if _is_master(viewer):
        return doc
    out = dict(doc)
    out.pop("assigned_user_ids", None)
    return out


# ----- Pydantic models -----
class LocationCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)

    @field_validator("name")
    @classmethod
    def _trim(cls, v: str) -> str:
        return (v or "").strip()


class LocationUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=80)


class LocationAssignments(BaseModel):
    """PATCH /admins payload — replaces the assignment list wholesale.

    Idempotent; sending the same list twice is a no-op. We don't bother
    with add/remove micro-endpoints because the dashboard always renders
    the whole list anyway.
    """
    assigned_user_ids: List[str] = Field(default_factory=list)


class ImageOrder(BaseModel):
    image_ids: List[str] = Field(default_factory=list)


# ----- Endpoints: locations CRUD -----
@router.get("")
async def list_locations(request: Request) -> List[Dict[str, Any]]:
    """List locations the current user can see.

    master_admin: every location.
    admin:        only locations where they're in `assigned_user_ids`.
    """
    user = await _require_admin_or_master(request)
    if _db is None:
        raise HTTPException(500, detail="database_not_initialised")

    query: Dict[str, Any] = {}
    if not _is_master(user):
        query["assigned_user_ids"] = _user_id(user)

    docs = await _db.locations.find(query, {"_id": 0}).sort("name", 1).to_list(500)
    return [_strip_admin_only(d, user) for d in docs]


@router.post("", status_code=201)
async def create_location(payload: LocationCreate, request: Request) -> Dict[str, Any]:
    """master_admin only. Slug is derived from name; collisions get a
    numeric suffix (`chicago`, `chicago-2`, ...)."""
    user = await _require_master(request)
    if _db is None:
        raise HTTPException(500, detail="database_not_initialised")

    base = _slugify(payload.name)
    slug = base
    n = 2
    # Slug uniqueness — collision handling lets multiple "Chicago"s coexist.
    while await _db.locations.find_one({"slug": slug}, {"_id": 1}):
        slug = f"{base}-{n}"
        n += 1

    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": str(uuid.uuid4()),
        "name": payload.name,
        "slug": slug,
        "branding_images": [],
        "assigned_user_ids": [],
        "created_at": now,
        "updated_at": now,
        "created_by": _user_id(user),
    }
    await _db.locations.insert_one({"_id": doc["id"], **doc})
    # Pre-create the branding dir so first upload doesn't race on mkdir.
    _branding_dir(slug)
    return doc


@router.get("/{location_id}")
async def get_location(location_id: str, request: Request) -> Dict[str, Any]:
    user, loc = await _require_location_access(location_id, request)
    return _strip_admin_only(loc, user)


@router.patch("/{location_id}")
async def update_location(
    location_id: str,
    payload: LocationUpdate,
    request: Request,
) -> Dict[str, Any]:
    user, loc = await _require_location_access(location_id, request)
    updates: Dict[str, Any] = {}
    if payload.name is not None:
        new_name = payload.name.strip()
        if new_name and new_name != loc.get("name"):
            updates["name"] = new_name
    if not updates:
        return _strip_admin_only(loc, user)
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    await _db.locations.update_one({"id": location_id}, {"$set": updates})
    new_loc = await _get_location_or_404(location_id)
    return _strip_admin_only(new_loc, user)


@router.delete("/{location_id}", status_code=204)
async def delete_location(location_id: str, request: Request):
    """master_admin only. Removes DB row AND on-disk branding folder."""
    await _require_master(request)
    loc = await _get_location_or_404(location_id)
    await _db.locations.delete_one({"id": location_id})
    # Best-effort wipe — losing the folder is non-fatal if it was already
    # gone (admin nuked it manually, FS error, ...).
    folder = _asset_root() / "02_Locations" / loc.get("slug", "")
    if folder.exists():
        try:
            shutil.rmtree(folder)
        except OSError as exc:
            logger.warning("locations_router: rmtree failed for %s: %s", folder, exc)


# ----- Endpoints: branding images -----
@router.post("/{location_id}/images", status_code=201)
async def upload_branding_image(
    location_id: str,
    request: Request,
    file: UploadFile = File(...),
) -> Dict[str, Any]:
    """Upload one branding image/GIF. Returns the added image record.

    Order defaults to the end of the existing list — drag-to-reorder is
    a separate PATCH.
    """
    user, loc = await _require_location_access(location_id, request)

    # MIME sniff. Trust the browser-provided content_type as long as it's
    # in the allow-list; the OS path picker on macOS sometimes ships
    # `application/octet-stream` for .gif so we also fall back to the
    # extension.
    mime = (file.content_type or "").lower()
    if mime not in _ALLOWED_MIMES:
        guessed, _ = mimetypes.guess_type(file.filename or "")
        if (guessed or "").lower() in _ALLOWED_MIMES:
            mime = (guessed or "").lower()
        else:
            raise HTTPException(415, detail=f"unsupported_mime:{mime or 'unknown'}")

    raw = await file.read()
    if len(raw) > _MAX_IMAGE_BYTES:
        raise HTTPException(413, detail=f"file_too_large:{len(raw)}")
    if not raw:
        raise HTTPException(400, detail="empty_file")

    ext = mimetypes.guess_extension(mime) or Path(file.filename or "").suffix or ".bin"
    image_id = str(uuid.uuid4())
    dst = _branding_dir(loc["slug"]) / f"{image_id}{ext}"
    dst.write_bytes(raw)

    record = {
        "id": image_id,
        "filename": file.filename or f"branding{ext}",
        "mime": mime,
        "size": len(raw),
        "order": len(loc.get("branding_images") or []),
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "uploaded_by": _user_id(user),
        "ext": ext,
    }
    await _db.locations.update_one(
        {"id": location_id},
        {
            "$push": {"branding_images": record},
            "$set": {"updated_at": record["uploaded_at"]},
        },
    )
    return record


@router.get("/{location_id}/images/{image_id}/raw")
async def get_branding_image_raw(
    location_id: str,
    image_id: str,
    request: Request,
):
    """Stream the binary so the dashboard <img> tags can render."""
    user, loc = await _require_location_access(location_id, request)
    img = next((i for i in (loc.get("branding_images") or []) if i.get("id") == image_id), None)
    if not img:
        raise HTTPException(404, detail="image_not_found")
    path = _branding_dir(loc["slug"]) / f"{image_id}{img.get('ext','.bin')}"
    if not path.is_file():
        raise HTTPException(404, detail="image_file_missing")
    return FileResponse(str(path), media_type=img.get("mime") or "application/octet-stream")


@router.delete("/{location_id}/images/{image_id}", status_code=204)
async def delete_branding_image(
    location_id: str,
    image_id: str,
    request: Request,
):
    user, loc = await _require_location_access(location_id, request)
    images = loc.get("branding_images") or []
    img = next((i for i in images if i.get("id") == image_id), None)
    if not img:
        raise HTTPException(404, detail="image_not_found")
    # Remove file (best-effort).
    path = _branding_dir(loc["slug"]) / f"{image_id}{img.get('ext','.bin')}"
    if path.is_file():
        try:
            path.unlink()
        except OSError as exc:
            logger.warning("locations_router: image unlink failed for %s: %s", path, exc)
    # Pull from DB. Recalculate order so the remaining images stay 0..N-1.
    remaining = [i for i in images if i.get("id") != image_id]
    for idx, i in enumerate(remaining):
        i["order"] = idx
    await _db.locations.update_one(
        {"id": location_id},
        {"$set": {
            "branding_images": remaining,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }},
    )


@router.patch("/{location_id}/images/order")
async def reorder_branding_images(
    location_id: str,
    payload: ImageOrder,
    request: Request,
) -> Dict[str, Any]:
    """Apply a drag-and-drop reorder. The payload's `image_ids` list is
    the new visual order, top-to-bottom. Unknown IDs are ignored; missing
    IDs from the existing list keep their relative order, appended at
    the end."""
    user, loc = await _require_location_access(location_id, request)
    images = loc.get("branding_images") or []
    by_id = {i.get("id"): i for i in images if i.get("id")}

    ordered: List[Dict[str, Any]] = []
    seen = set()
    for img_id in payload.image_ids:
        if img_id in by_id and img_id not in seen:
            ordered.append(by_id[img_id])
            seen.add(img_id)
    # Append any images the client forgot to mention (defensive — race
    # where someone else uploaded a new image while this client was
    # dragging).
    for img in images:
        if img.get("id") not in seen:
            ordered.append(img)

    for idx, img in enumerate(ordered):
        img["order"] = idx

    await _db.locations.update_one(
        {"id": location_id},
        {"$set": {
            "branding_images": ordered,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }},
    )
    return {"branding_images": ordered}


# ----- Endpoints: admin assignments -----
@router.patch("/{location_id}/admins")
async def set_assignments(
    location_id: str,
    payload: LocationAssignments,
    request: Request,
) -> Dict[str, Any]:
    """master_admin only. Replaces `assigned_user_ids` wholesale.

    We don't verify each id corresponds to an existing admin user — the
    list comes from a typeahead populated by `/api/native/admin/users`
    which already constrains the input. Stale IDs are harmless: the
    access guard ignores them.
    """
    await _require_master(request)
    loc = await _get_location_or_404(location_id)
    # Dedupe while preserving order.
    seen = set()
    cleaned: List[str] = []
    for uid in payload.assigned_user_ids:
        if uid and uid not in seen:
            seen.add(uid)
            cleaned.append(uid)
    await _db.locations.update_one(
        {"id": location_id},
        {"$set": {
            "assigned_user_ids": cleaned,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }},
    )
    return {"assigned_user_ids": cleaned}
