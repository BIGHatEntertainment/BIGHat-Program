"""
/api/native/* HTTP endpoints — setup wizard, license, subscription.

These endpoints are mounted unconditionally so the React frontend can probe
`/api/native/info` to decide whether to show the setup wizard. They never
touch MongoDB; they only operate on `system_config.json`.
"""
from __future__ import annotations

import bcrypt
import logging
import re as _re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel, Field, field_validator

from .config import config_manager
from .hwid import generate_hwid
from .license import (
    get_license_status,
    is_well_formed_license,
    register_seat,
    release_seat,
    set_license_key,
)
from .subscription import get_subscription, set_subscription
from . import cloud_client

router = APIRouter(prefix="/api/native", tags=["native"])
logger = logging.getLogger("bighat-native-router")


# ---------- Models ----------
class SetupSettings(BaseModel):
    company_name: Optional[str] = "BIG Hat Entertainment"
    location_name: str = Field(..., min_length=1)
    city: str = ""
    state: str = "AZ"
    trivia_source: str = "local"  # 'local' | 'cloud'


_EMAIL_RE = _re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class SetupMasterAdmin(BaseModel):
    email: str = Field(..., min_length=3)
    password: str = Field(..., min_length=6)
    first_name: str = Field(..., min_length=1)
    last_name: str = ""
    display_name: Optional[str] = None
    phone: Optional[str] = None

    @field_validator("email")
    @classmethod
    def _check_email(cls, v: str) -> str:
        v = (v or "").strip().lower()
        if not _EMAIL_RE.match(v):
            raise ValueError("invalid_email")
        return v


class SetupPaths(BaseModel):
    data_root: Optional[str] = None
    local_trivia: Optional[str] = None
    assets: Optional[str] = None
    generated: Optional[str] = None


class SetupInitRequest(BaseModel):
    license_key: str
    master_admin: SetupMasterAdmin
    settings: SetupSettings
    paths: Optional[SetupPaths] = None
    # When true, skip the authoritative cloud activate call entirely and
    # complete setup with the license flagged as `pending_cloud_activation`.
    # The 4-hour background refresh job will retry activation later. This
    # is the only safe response when the cloud reports `unknown_key` for a
    # key the user knows is valid (e.g. they just bought it and a DB-wipe
    # redeploy lost the record, or the user is genuinely offline).
    offline_mode: bool = False


class LicenseSetRequest(BaseModel):
    license_key: str
    master_admin_email: Optional[str] = None

class SubscriptionUpdateRequest(BaseModel):
    active: bool
    tier: str = "premium"
    expires_at: Optional[str] = None
    sharepoint_enabled: Optional[bool] = None
    story_generator_enabled: Optional[bool] = None
    # cloud_sync_enabled removed in v31.0.13.


class SeatRegisterRequest(BaseModel):
    label: Optional[str] = None


class CloudActivateRequest(BaseModel):
    license_key: str
    email: Optional[str] = None
    label: Optional[str] = None


class CloudDeactivateRequest(BaseModel):
    confirm: bool = False


def _read_installed_version() -> str:
    """Read backend/VERSION.txt — single source of truth used by Phase 9.1."""
    try:
        from pathlib import Path as _P
        p = _P(__file__).resolve().parent.parent / "VERSION.txt"
        return p.read_text(encoding="utf-8").strip() or "0.0.0"
    except OSError:
        return "0.0.0"


# ---------- Endpoints ----------
@router.get("/info")
async def get_native_info():
    """Used by the frontend on every load to decide UI state."""
    cfg = config_manager.public_view()
    return {
        "version": _read_installed_version(),
        "native_mode": config_manager.is_native_mode(),
        "setup_complete": cfg.get("setup_complete", False),
        "instance_id": cfg.get("instance_id"),
        "settings": cfg.get("settings", {}),
        "paths": cfg.get("paths", {}),
        "license": get_license_status(),
        "subscription": get_subscription(),
        "current_hwid": generate_hwid(),
        "users_count": len(cfg.get("users", [])),
    }


@router.get("/setup/status")
async def get_setup_status():
    return {
        "setup_complete": config_manager.config.get("setup_complete", False),
        "native_mode": config_manager.is_native_mode(),
        "users_count": len(config_manager.config.get("users", [])),
    }


@router.post("/setup/initialize")
async def initialize_setup(payload: SetupInitRequest):
    """First-run setup wizard — creates master admin, sets license, registers seat.

    Also calls the cloud license authority at `api.bighat.live` to bind this
    machine's HWID to the supplied key. The cloud is authoritative on
    `owns_standalone` / `cloud_library_active` / seat counts — we mirror its
    response into local state. Offline-tolerant: if the cloud is unreachable
    (timeout / network error), setup still completes and the licence is
    flagged `pending_cloud_activation`; a background job retries activation
    every few hours until it succeeds. **A 4xx from the cloud** (unknown key,
    revoked, seat limit) rejects the setup so fake keys cannot be used.
    """
    if config_manager.config.get("setup_complete"):
        raise HTTPException(status_code=409, detail="setup_already_complete")

    if not is_well_formed_license(payload.license_key):
        raise HTTPException(status_code=400, detail="invalid_license_format")

    key = payload.license_key.strip().upper()
    admin_email = payload.master_admin.email.lower().strip()
    hwid = generate_hwid()

    # 1. Cloud activation (authoritative). Do this BEFORE writing local state
    #    so a 4xx from the cloud doesn't leave a half-finished config behind.
    #
    # `offline_mode=True` skips this entirely — the wizard's "Continue offline"
    # button sends this flag so an authoritative cloud rejection (e.g.
    # `unknown_key` from a wiped DB) doesn't trap the user. The local copy
    # is marked `pending_cloud_activation` and retried by the 4-hour refresh
    # job once the cloud is reachable + the key has been (re-)minted.
    if payload.offline_mode:
        cloud_resp = {"ok": False, "error": "offline_mode_requested", "skipped": True}
        pending_cloud = True
        logger.info("[setup] offline_mode requested by client; skipping cloud activate")
    else:
        cloud_resp = await cloud_client.activate(
            license_key=key,
            hwid=hwid,
            machine_name=f"Setup Wizard — {payload.master_admin.first_name}",
            email=admin_email,
        )
        pending_cloud = False
        if not cloud_resp.get("ok"):
            if cloud_resp.get("error") in ("timeout", "network_error", "server_error"):
                # Offline-tolerant: accept setup, retry later.
                pending_cloud = True
                logger.info(
                    "[setup] cloud activation deferred (%s); will retry in background",
                    cloud_resp.get("error"),
                )
            else:
                # Authoritative rejection — unknown key, revoked, seat limit, etc.
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error":       cloud_resp.get("error", "license_rejected"),
                        "message":     cloud_resp.get("message", "License could not be activated."),
                        "status_code": cloud_resp.get("status_code"),
                    },
                )

    # 2. Persist license + settings + master admin.
    set_license_key(key, admin_email)

    cfg = config_manager.config
    cfg["settings"].update(payload.settings.model_dump(exclude_none=True))
    if payload.paths:
        cfg["paths"].update(payload.paths.model_dump(exclude_none=True))

    pwd_hash = bcrypt.hashpw(
        payload.master_admin.password.encode("utf-8"), bcrypt.gensalt()
    ).decode("utf-8")
    master_user = {
        "id": str(uuid.uuid4()),
        "email": admin_email,
        "password_hash": pwd_hash,
        "first_name": payload.master_admin.first_name,
        "last_name": payload.master_admin.last_name or "",
        "display_name": (
            payload.master_admin.display_name
            or f"{payload.master_admin.first_name} {payload.master_admin.last_name}".strip()
        ),
        "phone": payload.master_admin.phone,
        "role": "master_admin",
        "is_admin": True,
        "is_master": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "auth_method": "local",
    }
    cfg["users"] = [master_user]  # wipe any prior users on initial setup

    cfg["setup_complete"] = True
    config_manager.save_config()

    # v32.0.0-alpha.30: persist the master_admin profile to
    # `BIG Hat Entertainment/Files/Hosts/<slug>/host.json` so Host Recall
    # can identify the operator offline and survive a system_config wipe.
    # Import lazily to avoid a circular import at module load time (the
    # files_router itself imports from `.config`).
    try:
        from .files_router import write_host_profile_json  # noqa: WPS433
        write_host_profile_json(master_user)
    except Exception as e:  # pragma: no cover — never fail setup over disk
        logger.warning("[setup] could not persist host.json: %s", e)

    # 3. Mirror cloud response (subscription flags, seats) OR flag pending.
    #
    # SECURITY INVARIANT — the cloud is authoritative on entitlement.
    # `pending_cloud` is ONLY reached when the cloud was unreachable
    # (timeout / network error) or the customer chose offline mode AFTER
    # the cloud had previously approved the key. We never grant
    # `owns_standalone=true` without an OK from `api.bighat.live` — the
    # repo is public, so any "trust the local key" shortcut would let
    # anyone with a well-formed BHE-XXXX string bypass payment. The
    # 4-hour refresh job promotes the local state once the cloud
    # confirms entitlement; until then features stay locked.
    if pending_cloud:
        lic = config_manager.config.setdefault("license_status", {})
        lic["pending_cloud_activation"] = True
        config_manager.save_config()
        # Local seat so the customer can use the app offline immediately.
        register_seat(label=f"Master Admin — {master_user['display_name']}")
    else:
        _apply_cloud_response_to_local_state(cloud_resp, license_key=key, email=admin_email)
        register_seat(label=f"Master Admin — {master_user['display_name']}")

    return {
        "status": "ok",
        "master_admin_email": master_user["email"],
        "hwid": hwid,
        "license": get_license_status(),
        "subscription": get_subscription(),
        "cloud": cloud_resp if not pending_cloud else {
            "ok": False, "pending": True, "error": cloud_resp.get("error"),
        },
    }


@router.post("/setup/reset")
async def reset_setup(confirm: str = ""):
    """DANGEROUS: wipes config back to factory. Requires confirm=RESET-NATIVE."""
    if confirm != "RESET-NATIVE":
        raise HTTPException(status_code=400, detail="confirmation_required")
    # Reset by writing defaults
    from .config import _default_config  # noqa: WPS433

    config_manager.config = _default_config()
    config_manager.save_config()
    return {"status": "ok", "message": "system_config reset to factory defaults"}


@router.get("/license")
async def get_license():
    return get_license_status()


@router.post("/license")
async def set_license(payload: LicenseSetRequest):
    ok, msg = set_license_key(payload.license_key, payload.master_admin_email)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"status": "ok", "license": get_license_status()}


@router.post("/license/seat/register")
async def register_current_seat(payload: SeatRegisterRequest):
    ok, msg = register_seat(label=payload.label)
    if not ok:
        raise HTTPException(status_code=409, detail=msg)
    return {"status": "ok", "message": msg, "license": get_license_status()}


@router.post("/license/seat/release")
async def release_current_seat(hwid: Optional[str] = None):
    ok, msg = release_seat(hwid)
    if not ok:
        raise HTTPException(status_code=404, detail=msg)
    return {"status": "ok", "message": msg, "license": get_license_status()}


# ---------- Cloud-license activation (Phase 10.2) ----------
def _apply_cloud_response_to_local_state(resp: dict, *, license_key: str, email: Optional[str]) -> None:
    """Mirror the cloud's authoritative state into `system_config.json` so that
    `is_premium_active()` and `get_license_status()` return correct values
    even when offline."""
    set_license_key(license_key, master_admin_email=email)
    flags = {
        "sharepoint_enabled":      bool(resp.get("cloud_library_active")),
        "story_generator_enabled": bool(resp.get("owns_standalone")),
        # cloud_sync_enabled removed in v31.0.13.
        "music_bingo_enabled":     bool(resp.get("owns_standalone") and resp.get("owns_music_bingo")),
        "karaoke_enabled":         bool(resp.get("owns_standalone") and resp.get("owns_karaoke")),
        "bingo_story_enabled":     bool(resp.get("owns_standalone") and resp.get("owns_music_bingo")),
        "karaoke_story_enabled":   bool(resp.get("owns_standalone") and resp.get("owns_karaoke")),
    }
    set_subscription(
        active=bool(resp.get("owns_standalone") or resp.get("cloud_library_active")),
        tier=("premium" if resp.get("cloud_library_active")
              else "standalone" if resp.get("owns_standalone") else "free"),
        expires_at=resp.get("cloud_library_expires_at"),
        feature_flags=flags,
    )
    # Stash the last cloud snapshot for the offline-grace logic.
    sub = config_manager.config.setdefault("subscription", {})
    sub["last_cloud_validated_at"] = datetime.now(timezone.utc).isoformat()
    sub["revalidate_after"] = resp.get("revalidate_after")
    sub["owns_standalone"]    = bool(resp.get("owns_standalone"))
    sub["owns_music_bingo"]   = bool(resp.get("owns_music_bingo"))
    sub["owns_karaoke"]       = bool(resp.get("owns_karaoke"))
    sub["cloud_library_active"] = bool(resp.get("cloud_library_active"))
    config_manager.save_config()


@router.post("/license/cloud/activate")
async def cloud_activate(payload: CloudActivateRequest):
    """Online activation: tells `api.bighat.live` to bind this machine's HWID
    to the supplied license key. Mirrors the cloud's response into local state."""
    key = payload.license_key.strip().upper()
    if not is_well_formed_license(key):
        raise HTTPException(status_code=400, detail="invalid_license_format")
    hwid = generate_hwid()
    resp = await cloud_client.activate(
        license_key=key, hwid=hwid,
        machine_name=payload.label,
        email=payload.email,
    )
    if not resp.get("ok"):
        is_transport_err = resp.get("error") in ("timeout", "network_error", "server_error")
        raise HTTPException(
            status_code=503 if is_transport_err else 400,
            detail={
                "error":      resp.get("error", "cloud_unreachable"),
                "message":    resp.get("message", ""),
                "status_code": resp.get("status_code"),
            },
        )
    _apply_cloud_response_to_local_state(resp, license_key=key, email=payload.email)
    register_seat(label=payload.label or "This computer")
    return {
        "status":       "ok",
        "license":      get_license_status(),
        "subscription": get_subscription(),
        "cloud":        resp,
    }


@router.post("/license/cloud/validate")
async def cloud_validate():
    """Periodic re-check (UI cron'd at startup + every 7 days). Refreshes
    local subscription state from the cloud's authoritative truth.

    On transport error we DO NOT raise — the cached state is still honoured
    via the offline grace window. We surface the error in the payload so
    the UI can show a "last checked X minutes ago, offline" badge."""
    cfg = config_manager.config
    lic = cfg.get("license_status", {}) or {}
    key = lic.get("key")
    if not key:
        raise HTTPException(status_code=400, detail="no_license_key_set")
    hwid = generate_hwid()
    resp = await cloud_client.validate(license_key=key, hwid=hwid)
    if resp.get("ok") and resp.get("error") is None:
        _apply_cloud_response_to_local_state(resp, license_key=key, email=None)
        return {
            "status":       "ok",
            "license":      get_license_status(),
            "subscription": get_subscription(),
            "cloud":        resp,
        }
    # Network error → don't downgrade; bubble up the offline state.
    return {
        "status":       "offline",
        "license":      get_license_status(),
        "subscription": get_subscription(),
        "error":        resp.get("error"),
        "message":      resp.get("message"),
    }


@router.post("/license/cloud/deactivate")
async def cloud_deactivate(payload: CloudDeactivateRequest):
    """Move-to-new-machine path. Releases the seat on the cloud + locally.
    User must `confirm=true` to prevent accidental clicks."""
    if not payload.confirm:
        raise HTTPException(status_code=400, detail="confirmation_required")
    cfg = config_manager.config
    lic = cfg.get("license_status", {}) or {}
    key = lic.get("key")
    if not key:
        raise HTTPException(status_code=400, detail="no_license_key_set")
    hwid = generate_hwid()
    resp = await cloud_client.deactivate(license_key=key, hwid=hwid)
    # Even if cloud is unreachable, free the local seat so the user can move on.
    release_seat(hwid)
    set_subscription(active=False, tier="free")
    return {
        "status": "ok" if resp.get("ok") else "offline",
        "license": get_license_status(),
        "cloud":  resp,
    }



@router.get("/subscription")
async def get_sub():
    return get_subscription()


@router.post("/subscription")
async def update_sub(payload: SubscriptionUpdateRequest):
    flags = {
        k: v
        for k, v in payload.model_dump().items()
        if k
        in ("sharepoint_enabled", "story_generator_enabled")
        and v is not None
    }
    sub = set_subscription(
        active=payload.active,
        tier=payload.tier,
        expires_at=payload.expires_at,
        feature_flags=flags or None,
    )
    return {"status": "ok", "subscription": sub}


@router.get("/hwid")
async def get_hwid():
    return {"hwid": generate_hwid()}


@router.get("/config")
async def get_full_config():
    """Master-Admin only in production. For Phase 0 this is open for debugging."""
    return config_manager.public_view()



@router.post("/errors/report")
async def report_frontend_error(payload: Dict[str, Any] = Body(...)):
    """Sink for the React ErrorBoundary. We log to the standard
    supervisor stream so `tail -f /var/log/supervisor/backend.err.log`
    surfaces frontend crashes without needing DevTools open.

    The endpoint deliberately never raises — the frontend fire-and-
    forgets with `keepalive: true` during teardown, and we don't want
    a validation error to become the reason the user's Reload button
    disappears.
    """
    try:
        msg = str(payload.get("message") or "").strip()[:400]
        stack = str(payload.get("stack") or "").strip()[:2000]
        comp = str(payload.get("componentStack") or "").strip()[:2000]
        loc = str(payload.get("location") or "").strip()[:400]
        logger.error(
            "[frontend-error-boundary] loc=%s msg=%s\n  stack=%s\n  componentStack=%s",
            loc, msg, stack, comp,
        )
    except Exception as e:  # pragma: no cover
        logger.warning("[frontend-error-boundary] failed to log report: %s", e)
    return {"ok": True}


# ---------------------------------------------------------------------------
# v32.0.0-alpha.52 — Slide attestation endpoint.
#
# The merchant demanded flags to verify that slides are truly ported from
# the prototype and not fabricated. This endpoint returns a summary of
# every slide's provenance for a given presentation on disk:
#
#   - which round each slide belongs to
#   - which `.bighat` file on disk sourced it (with format: ZIP vs bare-JSON)
#   - whether the title card was: embedded / disk-per-category / disk-per-round
#     / bundled-default / text-fallback
#   - the `_verified_from_prototype` line-range citation for each slide
#   - simple health flags (does every question slide have text? etc.)
#
# GET /api/native/attest/{presentation_id}
# ---------------------------------------------------------------------------
@router.get("/attest/{presentation_id}")
async def attest_presentation(presentation_id: str):
    """Return provenance report for a presentation's rendered slides."""
    try:
        import native_slides as ns
    except ImportError as e:
        raise HTTPException(status_code=500, detail=f"native_slides import failed: {e}")

    pres = ns.load_presentation_from_disk(presentation_id)
    if not pres:
        raise HTTPException(status_code=404, detail=f"presentation {presentation_id} not on disk")

    round_files = pres.get("roundFiles") or []
    rounds_report: list = []
    slides_summary: list = []

    for rf in round_files:
        rtype = (rf.get("type") or "").upper()
        rorder = rf.get("order")
        rpath = rf.get("file") or rf.get("path") or ""
        doc = ns.load_round_from_disk({
            "type": rtype, "name": rf.get("name"),
            "id": rf.get("id"), "file": rpath,
        })
        source_format = "missing"
        if doc is not None:
            source_format = doc.get("_source_format", "bare-json")

        if not doc:
            rounds_report.append({
                "round_order": rorder, "round_type": rtype,
                "file": rpath, "source_format": source_format,
                "num_questions": 0, "num_slides_rendered": 0,
                "has_embedded_cover": False,
            })
            continue

        slides = ns.render_round_section(
            doc, {"type": rtype, "name": doc.get("name"), "order": rorder},
        )
        cover_source = None
        for s in slides:
            md = s.get("metadata") or {}
            if md.get("isRoundTitle"):
                cover_source = md.get("_title_card_source")
                break

        rounds_report.append({
            "round_order": rorder, "round_type": rtype,
            "file": rpath, "source_format": source_format,
            "num_questions": len(doc.get("questions") or []),
            "num_slides_rendered": len(slides),
            "has_embedded_cover": bool(doc.get("cover_image_data_url")),
            "title_card_source": cover_source,
        })
        for s in slides:
            md = s.get("metadata") or {}
            slides_summary.append({
                "round": rorder, "round_type": rtype,
                "slide_in_round": md.get("slideIndexInRound"),
                "is_round_title": bool(md.get("isRoundTitle")),
                "is_title_card_image": bool(md.get("isTitleCard")),
                "title_card_source": md.get("_title_card_source"),
                "question_number": md.get("questionNumber"),
                "has_question_text": md.get("_has_question_text"),
                "has_options": md.get("_has_options"),
                "verified_from_prototype": md.get("_verified_from_prototype"),
                "num_elements": len(s.get("elements") or []),
            })

    # Health flags
    total_slides = len(slides_summary)
    slides_with_image_title = sum(1 for s in slides_summary
                                  if s["is_round_title"] and s["is_title_card_image"])
    text_fallback_titles = sum(1 for s in slides_summary
                               if s["is_round_title"] and s["title_card_source"] == "text-fallback-no-image")
    missing_question_text = [
        {"round": s["round"], "q": s["question_number"]}
        for s in slides_summary
        if s["question_number"] is not None and s["has_question_text"] is False
    ]
    all_slides_stamped = all(
        s["verified_from_prototype"] or s["is_round_title"] for s in slides_summary
    )

    return {
        "presentation_id": presentation_id,
        "presentation_name": pres.get("name"),
        "num_rounds": len(round_files),
        "rounds": rounds_report,
        "health": {
            "total_slides": total_slides,
            "title_slides_with_image": slides_with_image_title,
            "title_slides_fallback_to_text": text_fallback_titles,
            "questions_missing_text": missing_question_text,
            "all_slides_prototype_stamped": all_slides_stamped,
        },
        "slides": slides_summary,
    }



# ---------------------------------------------------------------------------
# v32.0.0-alpha.53 — Hardcoded Build Wizard + Round Roulette endpoints.
#
# Full spec: see `/app/backend/presentation_builder.py` module docstring.
# Every rule the merchant listed on 2026-02-06 (17-step flow) is encoded
# in that module; these endpoints are thin HTTP adapters over it.
# ---------------------------------------------------------------------------


class WizardBuildRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    host_id: str = Field(..., min_length=1)
    location_id: str = Field(..., min_length=1)
    round_count: int = Field(..., ge=5, le=6)
    round_files: List[str]
    intro_pack_id: Optional[str] = None


class RouletteBuildRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    host_id: str = Field(..., min_length=1)
    location_id: str = Field(..., min_length=1)
    round_count: int = Field(..., ge=5, le=6)
    reg_pool: List[str] = Field(..., min_length=1)
    misc_pool: List[str] = Field(..., min_length=1)
    big_pool: List[str] = Field(..., min_length=1)
    mc_pool: Optional[List[str]] = None
    mys_pool: Optional[List[str]] = None
    seed: Optional[int] = None
    intro_pack_id: Optional[str] = None


class IntroPackCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    slides: List[Dict[str, Any]] = Field(default_factory=list)


class OverlayTagRequest(BaseModel):
    applies_to_round_types: List[str] = Field(default_factory=list)

    @field_validator("applies_to_round_types")
    @classmethod
    def _upper(cls, v: List[str]) -> List[str]:
        allowed = {"MC", "REG", "MISC", "MYS", "BIG"}
        cleaned = [(t or "").strip().upper() for t in v]
        bad = [t for t in cleaned if t and t not in allowed]
        if bad:
            raise ValueError(f"unknown round types: {bad}")
        return [t for t in cleaned if t]


async def _ensure_host_on_disk(host_id: str) -> None:
    """v32.0.0-alpha.56: the wizard's host dropdown is fed by config users
    AND `db.users` (id may be `native_user_id`, `id`, `_id`, or email) —
    but the sync builder validates against `Files/Hosts/*/host.json`.
    If the id doesn't resolve on disk yet, materialize host.json from the
    DB/config record before validation (disk is truth — self-heal)."""
    key = (host_id or "").strip()
    if not key:
        return
    try:
        from presentation_builder import _load_host, BuildValidationError
        try:
            _load_host(key)
            return  # already resolvable on disk
        except BuildValidationError:
            pass
        user: Optional[Dict[str, Any]] = None
        # 1. config users
        for u in (config_manager.config.get("users") or []):
            if (str(u.get("id") or "").lower() == key.lower()
                    or str(u.get("email") or "").lower() == key.lower()):
                user = dict(u)
                break
        # 2. db.users
        if user is None:
            try:
                from routes.trivia import db as _db
            except ImportError:
                _db = None
            if _db is not None:
                docs = await _db.users.find(
                    {"role": {"$in": ["master_admin", "admin", "host"]}},
                    {"password_hash": 0},
                ).to_list(1000)
                for u in docs:
                    cand_ids = {
                        str(u.get("native_user_id") or "").lower(),
                        str(u.get("id") or "").lower(),
                        str(u.get("_id") or "").lower(),
                        str(u.get("email") or "").lower(),
                    }
                    if key.lower() in cand_ids:
                        user = {k: v for k, v in u.items() if k != "_id"}
                        break
        if user is None:
            return  # let the builder raise its normal 400
        user.setdefault("id", key)
        from .files_router import write_host_profile_json
        write_host_profile_json(user)
        logger.info("[build] materialized host.json for %s", key)
    except Exception as e:  # never block the build over self-heal
        logger.warning("[build] host materialize failed for %s: %s", key, e)


@router.post("/presentations/build")
async def build_presentation_from_wizard(payload: WizardBuildRequest = Body(...)):
    """Step 12 of the merchant's spec — Build Wizard confirms → this
    endpoint writes the presentation `.bighat` on disk and returns it."""
    try:
        from presentation_builder import build_from_wizard, BuildValidationError
    except ImportError as e:
        raise HTTPException(500, detail=f"presentation_builder import failed: {e}")
    await _ensure_host_on_disk(payload.host_id)
    try:
        return build_from_wizard(
            name=payload.name,
            host_id=payload.host_id,
            location_id=payload.location_id,
            round_count=payload.round_count,
            round_files=payload.round_files,
            intro_pack_id=payload.intro_pack_id,
        )
    except BuildValidationError as e:
        raise HTTPException(400, detail=str(e))


@router.post("/presentations/roulette")
async def build_presentation_from_roulette(payload: RouletteBuildRequest = Body(...)):
    """Round Roulette — slot machine confirms → this endpoint spins,
    picks, writes the presentation `.bighat`, and returns picks + doc."""
    try:
        from presentation_builder import build_from_roulette, BuildValidationError
    except ImportError as e:
        raise HTTPException(500, detail=f"presentation_builder import failed: {e}")
    await _ensure_host_on_disk(payload.host_id)
    try:
        return build_from_roulette(
            name=payload.name,
            host_id=payload.host_id,
            location_id=payload.location_id,
            round_count=payload.round_count,
            reg_pool=payload.reg_pool,
            misc_pool=payload.misc_pool,
            big_pool=payload.big_pool,
            mc_pool=payload.mc_pool,
            mys_pool=payload.mys_pool,
            seed=payload.seed,
            intro_pack_id=payload.intro_pack_id,
        )
    except BuildValidationError as e:
        raise HTTPException(400, detail=str(e))


@router.get("/round-pool/{round_type}")
async def list_round_pool(round_type: str):
    """List available `.bighat` files in a specific round-type folder.
    Used by the Wizard and Roulette dropdowns."""
    from presentation_builder import _list_round_files_of_type
    rt = round_type.upper()
    if rt not in ("MC", "REG", "MISC", "MYS", "BIG"):
        raise HTTPException(400, detail=f"invalid round type {rt!r}")
    files = _list_round_files_of_type(rt)
    return {
        "round_type": rt,
        "count": len(files),
        "files": [f.name for f in files],
    }


@router.get("/intros")
async def list_intros_endpoint():
    from presentation_builder import list_intro_packs
    return {"packs": list_intro_packs()}


@router.get("/intros/{intro_id}")
async def get_intro_pack(intro_id: str):
    from presentation_builder import load_intro_pack
    doc = load_intro_pack(intro_id)
    if not doc:
        raise HTTPException(404, detail=f"intro_pack {intro_id!r} not found")
    return doc


@router.post("/intros")
async def create_intro_pack(payload: IntroPackCreateRequest = Body(...)):
    from presentation_builder import save_intro_pack
    return save_intro_pack(payload.name, payload.slides)


@router.delete("/intros/{intro_id}", status_code=204)
async def delete_intro_pack_endpoint(intro_id: str):
    from presentation_builder import delete_intro_pack
    if not delete_intro_pack(intro_id):
        raise HTTPException(404, detail=f"intro_pack {intro_id!r} not found")
