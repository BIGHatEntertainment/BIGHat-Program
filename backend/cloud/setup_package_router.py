"""Setup Package (alpha.85), served by api.bighat.live.

One small "setup package" per MASTER ADMIN EMAIL: venues, venue pricing, people (no passwords), who works where,
and location images. The master publishes it from their computer; the other copies (up to the key's seat limit,
and any extra key bought under the same email) PULL it instead of retyping everything.

Rules (kept simple):
  * Every call proves it is a real, activated, un-revoked license (license key + machine id), same as the QR relay.
  * The package belongs to the license's EMAIL (one email, one package). A second key under the same email
    shares it automatically.
  * Only the computer that holds the master admin role may publish or transfer; every activated copy may pull.
  * Passwords and secrets are NEVER accepted: the upload is scanned and refused if it contains any.
  * Each publish makes a new version number and keeps a content hash, so a computer can tell if it differs.
  * Moving a package to another email needs a confirmation code sent to the CURRENT owner email.
"""
from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import re
import secrets
import time
import zipfile
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response

logger = logging.getLogger("bighat-setup-package")
router = APIRouter(tags=["setup-package"])

MAX_PACKAGE_MB = int(os.environ.get("PACKAGE_MAX_MB", "40"))
MAX_ENTRIES = int(os.environ.get("PACKAGE_MAX_ENTRIES", "600"))
TRANSFER_MINUTES = int(os.environ.get("PACKAGE_TRANSFER_MINUTES", "30"))
TRANSFER_MAX_TRIES = 5
PUBLISH_MIN_SECONDS = int(os.environ.get("PACKAGE_PUBLISH_COOLDOWN_SECONDS", "10"))
_FORBIDDEN = ("password", "passwd", "pwd", "hash", "secret", "token", "api_key", "apikey", "private_key", "license_key", "credential")
_IMG_EXT = {"png", "jpg", "jpeg", "gif", "webp", "mp4", "webm", "mov"}

_service = None
_db = None
_mailer = None


def set_runtime(*, service, db, mailer=None) -> None:
    global _service, _db, _mailer
    _service, _db, _mailer = service, db, mailer


async def ensure_indexes(db) -> None:
    try:
        await db.setup_packages.create_index("email", unique=True)
        await db.setup_transfers.create_index("email")
        await db.setup_transfers.create_index("expires_at")
    except Exception as e:                                # noqa: BLE001
        logger.warning("setup package indexes not created: %s", e)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _need() -> None:
    if _service is None or _db is None:
        raise HTTPException(status_code=503, detail="package_service_not_ready")


async def _auth(license_key: str, hwid: str) -> Dict[str, Any]:
    """Real, activated, un-revoked license. Returns {key, email} (the email is the package owner)."""
    _need()
    key = (license_key or "").strip().upper()
    ok, why, lic = await _service.validate(key=key, hwid=(hwid or "").strip())
    if not ok or lic is None:
        raise HTTPException(status_code=401, detail=f"not_allowed:{why}")
    email = str(getattr(lic, "email", "") or "").strip().lower()
    if not email:
        raise HTTPException(status_code=401, detail="license_has_no_email")
    return {"key": key, "email": email}


def _scan_for_secrets(obj: Any, path: str = "") -> Optional[str]:
    """Refuse anything that looks like a password or secret anywhere in the package data."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if any(f in str(k).lower() for f in _FORBIDDEN):
                return f"{path}/{k}"
            bad = _scan_for_secrets(v, f"{path}/{k}")
            if bad:
                return bad
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            bad = _scan_for_secrets(v, f"{path}[{i}]")
            if bad:
                return bad
    return None


def _validate_zip(raw: bytes) -> Dict[str, Any]:
    """Open the uploaded zip safely and return the parsed package.json. Refuses anything odd."""
    if len(raw) > MAX_PACKAGE_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail="package_too_big")
    try:
        z = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="not_a_package")
    names = z.namelist()
    if len(names) > MAX_ENTRIES or "package.json" not in names:
        raise HTTPException(status_code=400, detail="bad_package")
    total = 0
    for info in z.infolist():
        n = info.filename
        if n.startswith("/") or ".." in n.split("/") or "\\" in n or n.endswith("/") and info.file_size:
            raise HTTPException(status_code=400, detail="bad_package_path")
        total += info.file_size
        if total > MAX_PACKAGE_MB * 3 * 1024 * 1024:            # zip bomb guard
            raise HTTPException(status_code=413, detail="package_too_big")
        if n != "package.json":
            if not n.startswith("images/") or n.rsplit(".", 1)[-1].lower() not in _IMG_EXT:
                raise HTTPException(status_code=400, detail="bad_package_file")
    try:
        data = json.loads(z.read("package.json").decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="bad_package_json")
    if not isinstance(data, dict) or data.get("format") != "bighat-setup-package":
        raise HTTPException(status_code=400, detail="bad_package_format")
    bad = _scan_for_secrets(data)
    if bad:
        raise HTTPException(status_code=400, detail=f"package_contains_a_secret:{bad}")
    return data


def content_hash(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _summary(doc: Dict[str, Any]) -> Dict[str, Any]:
    return {k: doc.get(k) for k in ("version", "hash", "size", "published_at", "published_by", "counts")}


# ---------------------------------------------------------------- publish / status / pull
@router.post("/api/setup-package/publish")
async def publish(request: Request, license_key: str = Form(...), hwid: str = Form(...),
                  is_master: str = Form("0"), expected_version: str = Form(""),
                  machine_label: str = Form(""), file: UploadFile = File(...)):
    a = await _auth(license_key, hwid)
    if is_master != "1":
        raise HTTPException(status_code=403, detail="only_the_master_admin_can_publish")
    raw = await file.read(MAX_PACKAGE_MB * 1024 * 1024 + 1)
    data = _validate_zip(raw)
    cur = await _db.setup_packages.find_one({"email": a["email"]}, {"_id": 0, "blob": 0})
    if cur and time.time() - float(cur.get("published_ts", 0)) < PUBLISH_MIN_SECONDS:
        raise HTTPException(status_code=429, detail="please_wait_a_moment")
    # Optimistic check: if another computer published meanwhile, ask the master to pull first (nothing is overwritten silently).
    if cur and expected_version not in ("", str(cur.get("version"))):
        raise HTTPException(status_code=409, detail=f"newer_version_exists:{cur.get('version')}")
    version = int(cur.get("version", 0)) + 1 if cur else 1
    counts = {k: len(data.get(k) or []) for k in ("venues", "venue_pricing", "people", "venue_roles", "locations")}
    doc = {"email": a["email"], "version": version, "hash": content_hash(raw), "size": len(raw), "blob": raw,
           "published_at": _now().isoformat(), "published_ts": time.time(), "published_by": (machine_label or "")[:60],
           "counts": counts}
    if cur:
        await _db.setup_packages.replace_one({"email": a["email"]}, doc)
    else:
        await _db.setup_packages.insert_one(doc)
    return {"ok": True, **_summary(doc)}


@router.post("/api/setup-package/status")
async def status(payload: Dict[str, Any]):
    """Cheap check any activated copy can make: is there a package, and which version/hash?"""
    a = await _auth(payload.get("license_key", ""), payload.get("hwid", ""))
    cur = await _db.setup_packages.find_one({"email": a["email"]}, {"_id": 0, "blob": 0})
    return {"exists": bool(cur), **(_summary(cur) if cur else {})}


@router.post("/api/setup-package/pull")
async def pull(payload: Dict[str, Any]):
    a = await _auth(payload.get("license_key", ""), payload.get("hwid", ""))
    cur = await _db.setup_packages.find_one({"email": a["email"]}, {"_id": 0})
    if not cur:
        raise HTTPException(status_code=404, detail="no_package")
    blob = cur["blob"]
    return Response(content=bytes(blob), media_type="application/zip",
                    headers={"X-Package-Version": str(cur["version"]), "X-Package-Hash": cur["hash"]})


# ---------------------------------------------------------------- transfer to another email
@router.post("/api/setup-package/transfer/start")
async def transfer_start(payload: Dict[str, Any]):
    """Master asks to move the package to another email. A confirmation code goes to the CURRENT owner email."""
    a = await _auth(payload.get("license_key", ""), payload.get("hwid", ""))
    if not payload.get("is_master"):
        raise HTTPException(status_code=403, detail="only_the_master_admin_can_transfer")
    target = str(payload.get("to_email") or "").strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", target) or target == a["email"]:
        raise HTTPException(status_code=400, detail="bad_target_email")
    if not await _db.setup_packages.find_one({"email": a["email"]}, {"_id": 0, "email": 1}):
        raise HTTPException(status_code=404, detail="no_package")
    if await _db.setup_packages.find_one({"email": target}, {"_id": 0, "email": 1}):
        raise HTTPException(status_code=409, detail="target_already_has_a_package")
    code = f"{secrets.randbelow(1000000):06d}"
    await _db.setup_transfers.delete_many({"email": a["email"]})
    await _db.setup_transfers.insert_one({"email": a["email"], "to": target, "code_hash": hashlib.sha256(code.encode()).hexdigest(),
                                          "tries": 0, "expires_at": (_now() + timedelta(minutes=TRANSFER_MINUTES)).isoformat()})
    sent = False
    if _mailer is not None:
        try:
            sent = await _mailer._send(
                to=a["email"], subject="BIG Hat: confirm moving your setup package",
                html=f"<p>Someone asked to move your BIG Hat setup package to <b>{target}</b>.</p><p>Your confirmation code is <b>{code}</b> (valid {TRANSFER_MINUTES} minutes).</p><p>If this was not you, ignore this email: nothing will change.</p>",
                text=f"Someone asked to move your BIG Hat setup package to {target}. Confirmation code: {code} (valid {TRANSFER_MINUTES} minutes). If this was not you, ignore this email.")
        except Exception as e:                            # noqa: BLE001
            logger.warning("transfer email failed: %s", e)
    if not sent:
        await _db.setup_transfers.delete_many({"email": a["email"]})
        raise HTTPException(status_code=503, detail="could_not_send_the_confirmation_email")
    return {"ok": True, "sent_to": _mask(a["email"]), "valid_minutes": TRANSFER_MINUTES}


@router.post("/api/setup-package/transfer/confirm")
async def transfer_confirm(payload: Dict[str, Any]):
    a = await _auth(payload.get("license_key", ""), payload.get("hwid", ""))
    if not payload.get("is_master"):
        raise HTTPException(status_code=403, detail="only_the_master_admin_can_transfer")
    t = await _db.setup_transfers.find_one({"email": a["email"]}, {"_id": 0})
    if not t or t["expires_at"] < _now().isoformat():
        raise HTTPException(status_code=400, detail="code_expired_or_not_requested")
    if int(t.get("tries", 0)) >= TRANSFER_MAX_TRIES:
        await _db.setup_transfers.delete_many({"email": a["email"]})
        raise HTTPException(status_code=429, detail="too_many_wrong_codes")
    if hashlib.sha256(str(payload.get("code") or "").strip().encode()).hexdigest() != t["code_hash"]:
        await _db.setup_transfers.update_one({"email": a["email"]}, {"$set": {"tries": int(t.get("tries", 0)) + 1}})
        raise HTTPException(status_code=400, detail="wrong_code")
    if await _db.setup_packages.find_one({"email": t["to"]}, {"_id": 0, "email": 1}):
        raise HTTPException(status_code=409, detail="target_already_has_a_package")
    await _db.setup_packages.update_one({"email": a["email"]}, {"$set": {"email": t["to"]}})
    await _db.setup_transfers.delete_many({"email": a["email"]})
    return {"ok": True, "moved_to": t["to"]}


def _mask(email: str) -> str:
    n, _, d = email.partition("@")
    return (n[:2] + "***@" + d) if n else email
