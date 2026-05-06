"""
.bighat file import/export — Phase 10.7

A `.bighat` file is a ZIP archive containing one Round Maker round (and,
in the future, optional bundled assets like cover images). Customers
save rounds to .bighat for portability — they email them to colleagues,
back them up to OneDrive, or just double-click to re-open in the app.

File layout (versioned):

    manifest.json   { format: "bighat/round", version: 1, app_version, created_at }
    round.json      { full round payload — same shape as POST /api/roundmaker/rounds }
    assets/         (optional) cover image binary, etc.

Endpoints:

    GET  /api/bighat-files/export/{round_id}   → ZIP download
    POST /api/bighat-files/import              → multipart upload (browser file picker)
    POST /api/bighat-files/import-from-path    → form-field `path`, reads from local disk
                                                  (used by BIGHat.exe file-association handoff)

The import-from-path endpoint is restricted to native mode + 127.0.0.1
clients only — it would be a remote-file-read vulnerability on the
cloud deploy.
"""
from __future__ import annotations

import io
import json
import logging
import os
import re
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel

router = APIRouter(prefix="/bighat-files", tags=["bighat-files"])
logger = logging.getLogger(__name__)

db: AsyncIOMotorDatabase | None = None
BACKEND_DIR = Path(__file__).resolve().parent.parent

BIGHAT_FORMAT = "bighat/round"
BIGHAT_VERSION = 1
MAX_BIGHAT_BYTES = 50 * 1024 * 1024  # 50 MB hard cap per file


def set_database(database) -> None:
    global db
    db = database


def _is_native_mode() -> bool:
    return os.environ.get("BIGHAT_NATIVE_MODE", "0") == "1"


def _read_app_version() -> str:
    p = BACKEND_DIR / "VERSION.txt"
    if p.is_file():
        return p.read_text(encoding="utf-8").strip()
    return "unknown"


def _safe_filename(name: str) -> str:
    """Make `name` safe to use as a Content-Disposition filename — strips
    path separators, collapses whitespace, replaces unfriendly punctuation."""
    cleaned = re.sub(r"[\\/:\*\?\"<>\|\x00-\x1f]", "", name).strip()
    cleaned = re.sub(r"\s+", " ", cleaned) or "round"
    return cleaned[:120]


# ---------- export ----------
@router.get("/export/{round_id}")
async def export_round(round_id: str):
    """Return the round as a `.bighat` ZIP file download."""
    if db is None:
        raise HTTPException(500, "database not initialised")
    doc = await db.rounds.find_one({"id": round_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Round not found")

    manifest = {
        "format": BIGHAT_FORMAT,
        "version": BIGHAT_VERSION,
        "app_version": _read_app_version(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "round_name": doc.get("name") or "Untitled",
        "round_type": doc.get("round_type") or "REG",
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))
        zf.writestr("round.json", json.dumps(doc, indent=2))
    buf.seek(0)

    fname = f"{_safe_filename(doc.get('name', 'round'))}.bighat"
    return StreamingResponse(
        buf,
        media_type="application/x-bighat",
        headers={
            "Content-Disposition": f'attachment; filename="{fname}"',
            "X-Bighat-Version": str(BIGHAT_VERSION),
        },
    )


# ---------- import (shared core) ----------
class ImportResult(BaseModel):
    round_id: str
    name: str
    round_type: str


async def _import_zip_bytes(payload: bytes) -> ImportResult:
    if db is None:
        raise HTTPException(500, "database not initialised")
    if len(payload) > MAX_BIGHAT_BYTES:
        raise HTTPException(413, f".bighat file too large (>{MAX_BIGHAT_BYTES // (1024*1024)} MB)")
    if len(payload) < 64:
        raise HTTPException(400, ".bighat file is empty or truncated")

    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            names = set(zf.namelist())
            if "manifest.json" not in names or "round.json" not in names:
                raise HTTPException(400, "Not a valid .bighat file (missing manifest.json or round.json)")
            try:
                manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as e:
                raise HTTPException(400, f"Corrupted manifest.json: {e}")
            try:
                round_doc = json.loads(zf.read("round.json").decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as e:
                raise HTTPException(400, f"Corrupted round.json: {e}")
    except zipfile.BadZipFile:
        raise HTTPException(400, "File is not a valid .bighat archive (bad zip)")

    if manifest.get("format") != BIGHAT_FORMAT:
        raise HTTPException(400, f"Unsupported file format: {manifest.get('format')!r}")
    if int(manifest.get("version", 0)) > BIGHAT_VERSION:
        raise HTTPException(
            400,
            f"This .bighat file was made with a newer version of BIG Hat "
            f"(v{manifest.get('version')}). Please update the app and try again.",
        )

    # Mint a fresh id so re-importing the same .bighat creates a new round
    # rather than colliding with an existing one. Keep the human-meaningful
    # fields (questions, name, type, cover_image_id, tiebreaker).
    new_id = str(uuid.uuid4())
    name = round_doc.get("name") or manifest.get("round_name") or "Imported round"
    round_type = round_doc.get("round_type") or manifest.get("round_type") or "REG"
    new_doc = {
        "id": new_id,
        "round_type": round_type,
        "name": name,
        "questions": round_doc.get("questions") or [],
        "tiebreaker": round_doc.get("tiebreaker"),
        "cover_image_id": round_doc.get("cover_image_id"),
        "status": "draft",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "pptx_path": None,
        "imported_from": ".bighat",
    }
    await db.rounds.insert_one(new_doc)
    new_doc.pop("_id", None)
    logger.info("[bighat-files] imported round %s (%s)", new_id, name)
    return ImportResult(round_id=new_id, name=name, round_type=round_type)


# ---------- import: browser file picker ----------
@router.post("/import", response_model=ImportResult)
async def import_round(file: UploadFile = File(...)):
    """Import a `.bighat` file uploaded via a browser <input type=file>."""
    payload = await file.read()
    return await _import_zip_bytes(payload)


# ---------- import: from a path on disk ----------
@router.post("/import-from-path", response_model=ImportResult)
async def import_round_from_path(request: Request, path: str = Form(...)):
    """Import a `.bighat` file by absolute path on the local machine.

    Used by `BIGHat.exe` when a customer double-clicks a .bighat file in
    Explorer — the wrapper hands the path to this endpoint via a query
    parameter on the URL it opens in the browser, and the React frontend
    POSTs it here.

    SECURITY: only allowed in native mode AND when the request originated
    on the loopback interface. Otherwise this is a remote-file-read.
    """
    if not _is_native_mode():
        raise HTTPException(404, "Not available in this deployment mode")
    client_host = request.client.host if request.client else ""
    # Allow loopback addresses + FastAPI TestClient's synthetic "testclient" host.
    # In native mode, uvicorn binds 127.0.0.1 so non-loopback shouldn't be reachable
    # at all — this is defence-in-depth in case someone overrides --host.
    if client_host not in {"127.0.0.1", "::1", "localhost", "testclient"}:
        raise HTTPException(403, "Local-only endpoint")

    p = Path(path).expanduser()
    if not p.is_file():
        raise HTTPException(404, f"File not found: {p}")
    try:
        payload = p.read_bytes()
    except OSError as e:
        raise HTTPException(400, f"Could not read file: {e}")
    return await _import_zip_bytes(payload)


# ---------- health ----------
@router.get("/")
async def health() -> dict:
    return {"ok": True, "format": BIGHAT_FORMAT, "version": BIGHAT_VERSION}
