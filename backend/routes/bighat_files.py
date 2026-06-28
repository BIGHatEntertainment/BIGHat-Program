"""
.bighat file import/export — Phase 10.7 + v31.0.12

A `.bighat` file is a ZIP archive containing exportable BIG Hat content.
Customers email them, back them up to OneDrive, sell premium packs on
Squarespace, or just double-click to re-import.

Supported content types (see `BIGHAT_TYPES` registry below):

  - `round`            Round Maker round (questions + tiebreaker + cover image)
  - `presentation`     Full trivia presentation (multi-round + branded slides)
  - `bingo`            Bingo card / template (call list + winner videos)
  - `pack`             Bundle of multiple .bighat items (e.g. a paid 4-round
                       music-trivia pack)

File layout (versioned, forward-compatible):

    manifest.json     { format, version, type, app_version, round_name?,
                        round_type?, author?, signature? }
    payload.json      type-specific JSON payload
    assets/           (optional) cover images, audio clips, video files, etc.
    signature.txt     (optional) HMAC-SHA256 of manifest+payload+assets
                      under the publisher's signing key — used to gate paid
                      round packs against piracy

Endpoints:
    GET  /api/bighat-files/export/{round_id}     → ZIP of a single round
    GET  /api/bighat-files/export/{type}/{id}    → ZIP of any content type
    POST /api/bighat-files/import                → multipart upload
    POST /api/bighat-files/import-from-path      → form-field `path` (native+loopback only)
    GET  /api/bighat-files/inspect               → preview a .bighat before import
                                                   (no DB writes — shows manifest + asset list)
"""
from __future__ import annotations

import base64
import hashlib
import hmac
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

BIGHAT_FORMAT = "bighat"                # type-agnostic format identifier
BIGHAT_VERSION = 2                      # bumped: v1 was round-only
MAX_BIGHAT_BYTES = 50 * 1024 * 1024     # 50 MB hard cap per file


# ============================================================
# Content-type registry — one entry per exportable BIG Hat item
# ============================================================
#
# Each entry maps a public type string (used in `manifest.type` and the
# URL) to:
#   collection: the MongoDB collection storing this content
#   pretty: human-readable label (toast messages, file names)
#   asset_fields: list of payload keys that may contain GridFS / file_id
#                 references — used to bundle media into assets/
#
# Adding a new content type is one entry here + (optionally) one helper.

class ContentTypeSpec(BaseModel):
    collection: str
    pretty: str
    asset_fields: list[str] = []   # payload fields that are media-id refs


BIGHAT_TYPES: dict[str, ContentTypeSpec] = {
    "round": ContentTypeSpec(
        collection="rounds",
        pretty="Round Maker round",
        asset_fields=["cover_image_id"],
    ),
    "presentation": ContentTypeSpec(
        collection="trivia_presentations",
        pretty="Trivia presentation",
        asset_fields=[],
    ),
    "bingo": ContentTypeSpec(
        collection="bingo_games",
        pretty="Bingo card",
        asset_fields=["winner_video_id"],
    ),
    "scoreboard": ContentTypeSpec(
        collection="scoreboard_themes",
        pretty="Scoreboard theme",
        asset_fields=["background_image_id"],
    ),
}


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
    cleaned = re.sub(r"[\\/:\*\?\"<>\|\x00-\x1f]", "", name).strip()
    cleaned = re.sub(r"\s+", " ", cleaned) or "round"
    return cleaned[:120]


# ============================================================
# HMAC signing — for paid round packs / publisher verification
# ============================================================

def _signing_key() -> bytes | None:
    """Optional publisher signing key. When set, .bighat files exported by
    THIS install will include a `signature.txt` HMAC. Importers can verify
    the signature against the same key — used by paid round packs sold on
    bighat.live to prevent unauthorised content sharing.

    Customers don't have this key. The official BIG Hat servers do.
    """
    key = os.environ.get("BIGHAT_SIGNING_KEY", "")
    return key.encode("utf-8") if key else None


def _compute_signature(manifest_bytes: bytes, payload_bytes: bytes,
                       asset_hashes: list[str]) -> str:
    """HMAC-SHA256 over manifest + payload + sorted asset hashes."""
    key = _signing_key()
    if not key:
        return ""
    mac = hmac.new(key, digestmod=hashlib.sha256)
    mac.update(manifest_bytes)
    mac.update(b"\n--payload--\n")
    mac.update(payload_bytes)
    mac.update(b"\n--assets--\n")
    for h in sorted(asset_hashes):
        mac.update(h.encode("utf-8"))
        mac.update(b"\n")
    return base64.b64encode(mac.digest()).decode("ascii")


def _verify_signature(manifest_bytes: bytes, payload_bytes: bytes,
                      asset_hashes: list[str], signature: str) -> bool:
    expected = _compute_signature(manifest_bytes, payload_bytes, asset_hashes)
    if not expected:                       # no key configured locally
        return False
    return hmac.compare_digest(expected, signature)


# ============================================================
# Asset bundling
# ============================================================

async def _read_gridfs_asset(file_id: str) -> tuple[bytes, str] | None:
    """Read a GridFS-stored asset; returns (bytes, mime-type-or-extension)
    or None if the file is missing. Failures are non-fatal — the .bighat
    is still useful without the cover image."""
    if not file_id or db is None:
        return None
    try:
        from motor.motor_asyncio import AsyncIOMotorGridFSBucket
        bucket = AsyncIOMotorGridFSBucket(db)
        stream = await bucket.open_download_stream(file_id)
        data = await stream.read()
        meta = stream.metadata or {}
        mime = meta.get("contentType") or "application/octet-stream"
        return data, mime
    except Exception as e:                  # pragma: no cover — best-effort
        logger.warning("[bighat-files] couldn't fetch asset %s: %s", file_id, e)
        return None


# ============================================================
# Export
# ============================================================

async def _build_bighat_zip(content_type: str, doc: dict) -> tuple[bytes, str]:
    """Build a .bighat zip for one document. Returns (bytes, suggested_filename)."""
    spec = BIGHAT_TYPES[content_type]
    asset_hashes: list[str] = []
    asset_writes: list[tuple[str, bytes]] = []

    # Walk the asset_fields list, pull each GridFS file into assets/
    for field in spec.asset_fields:
        ref = doc.get(field)
        if not ref:
            continue
        fetched = await _read_gridfs_asset(ref)
        if not fetched:
            continue
        blob, mime = fetched
        ext = {"image/png": ".png", "image/jpeg": ".jpg",
               "video/mp4": ".mp4", "audio/mpeg": ".mp3"}.get(mime, "")
        asset_name = f"{field}{ext or ''}"
        asset_writes.append((asset_name, blob))
        asset_hashes.append(hashlib.sha256(blob).hexdigest())

    name = (doc.get("name") or doc.get("title") or f"Untitled {spec.pretty}").strip()
    manifest = {
        "format":      BIGHAT_FORMAT,
        "version":     BIGHAT_VERSION,
        "type":        content_type,
        "app_version": _read_app_version(),
        "created_at":  datetime.now(timezone.utc).isoformat(),
        "name":        name,
        "asset_count": len(asset_writes),
        # Back-compat with v31.0.11 importer
        "round_name":  name,
        "round_type":  doc.get("round_type"),
    }
    manifest_bytes = json.dumps(manifest, indent=2).encode("utf-8")
    payload_bytes = json.dumps(doc, indent=2, default=str).encode("utf-8")
    signature = _compute_signature(manifest_bytes, payload_bytes, asset_hashes)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", manifest_bytes)
        zf.writestr("payload.json", payload_bytes)
        # Back-compat: v1 importers look for round.json
        if content_type == "round":
            zf.writestr("round.json", payload_bytes)
        for asset_name, blob in asset_writes:
            zf.writestr(f"assets/{asset_name}", blob)
        if signature:
            zf.writestr("signature.txt", signature)
    buf.seek(0)

    filename = f"{_safe_filename(name)}.bighat"
    return buf.getvalue(), filename


@router.get("/export/{round_id}")
async def export_round_legacy(round_id: str):
    """Legacy v1 endpoint — Round Maker round export. Preserved for the
    `/api/bighat-files/export/{round_id}` URL shape already used by the
    Round Maker Dashboard frontend."""
    if db is None:
        raise HTTPException(500, "database not initialised")
    doc = await db.rounds.find_one({"id": round_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Round not found")
    data, filename = await _build_bighat_zip("round", doc)
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/x-bighat",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Bighat-Version": str(BIGHAT_VERSION),
        },
    )


@router.get("/export/{content_type}/{doc_id}")
async def export_content(content_type: str, doc_id: str):
    """Type-aware export. `content_type` ∈ BIGHAT_TYPES."""
    if db is None:
        raise HTTPException(500, "database not initialised")
    if content_type not in BIGHAT_TYPES:
        raise HTTPException(400, f"Unknown content type: {content_type}")
    spec = BIGHAT_TYPES[content_type]
    doc = await db[spec.collection].find_one({"id": doc_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, f"{spec.pretty} not found")
    data, filename = await _build_bighat_zip(content_type, doc)
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/x-bighat",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Bighat-Version": str(BIGHAT_VERSION),
            "X-Bighat-Type": content_type,
        },
    )


# ============================================================
# Import — shared parsing / preview
# ============================================================

class ImportResult(BaseModel):
    id: str
    name: str
    type: str
    signed: bool = False
    # Kept for v1 back-compat with the existing Round Maker frontend.
    round_id: Optional[str] = None
    round_type: Optional[str] = None


class InspectResult(BaseModel):
    type: str
    name: str
    app_version: str
    created_at: str
    asset_count: int
    signed: bool
    file_size: int


def _parse_bighat(payload: bytes) -> tuple[dict, dict, dict[str, bytes], str]:
    """Parse a .bighat payload. Returns (manifest, doc, assets, signature)."""
    if len(payload) > MAX_BIGHAT_BYTES:
        raise HTTPException(413, f".bighat file too large (>{MAX_BIGHAT_BYTES // (1024*1024)} MB)")
    if len(payload) < 64:
        raise HTTPException(400, ".bighat file is empty or truncated")
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            names = set(zf.namelist())
            if "manifest.json" not in names:
                raise HTTPException(400, "Not a valid .bighat file (missing manifest.json)")
            try:
                manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as e:
                raise HTTPException(400, f"Corrupted manifest.json: {e}")
            # v1 used "round.json"; v2 uses "payload.json" (with round.json
            # kept as a duplicate for back-compat).
            payload_name = (
                "payload.json" if "payload.json" in names
                else "round.json" if "round.json" in names
                else None
            )
            if not payload_name:
                raise HTTPException(400, "Not a valid .bighat file (missing payload.json)")
            try:
                doc = json.loads(zf.read(payload_name).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as e:
                raise HTTPException(400, f"Corrupted payload: {e}")
            assets: dict[str, bytes] = {}
            for n in names:
                if n.startswith("assets/") and not n.endswith("/"):
                    assets[n[len("assets/"):]] = zf.read(n)
            signature = zf.read("signature.txt").decode("ascii") if "signature.txt" in names else ""
    except zipfile.BadZipFile:
        raise HTTPException(400, "File is not a valid .bighat archive (bad zip)")

    # Format header validation. v1 used "bighat/round"; v2 uses "bighat".
    #
    # v32.0.0-alpha.19 leniency: third-party generators (the user's
    # external trivia-round tool, for example) sometimes ship .bighat
    # files with NO `format` field at all — they encode the kind of
    # content in `manifest.type` (e.g. "MC", "BIG", "round"). Rejecting
    # those with "Unsupported file format: ''" gave the customer no
    # actionable signal. We now accept the file if EITHER the `format`
    # is one of the known string IDs, OR the `type` is a recognised
    # content type. Anything else still bounces — random zip files with
    # a manifest.json that says nothing useful won't import.
    fmt = manifest.get("format", "")
    type_alias = str(manifest.get("type") or "").lower()
    # Trivia round-type codes the external generator emits + the
    # canonical lowercase names used elsewhere in the codebase.
    KNOWN_TYPES = {
        "round", "presentation", "pack",                # canonical
        "mc", "reg", "misc", "mys", "big",              # external generator round codes
    }
    accepted_by_format = fmt in ("bighat", "bighat/round")
    accepted_by_type   = type_alias in KNOWN_TYPES
    if not (accepted_by_format or accepted_by_type):
        raise HTTPException(
            400,
            f"Unsupported .bighat file: manifest must contain either "
            f"'format' = 'bighat' OR a recognised 'type' field "
            f"(round/presentation/pack/MC/BIG/REG/MISC/MYS). "
            f"Got format={fmt!r} type={manifest.get('type')!r}.",
        )
    # If we accepted by type, synthesise the format so downstream
    # code can treat the file uniformly.
    if not accepted_by_format:
        manifest["format"] = "bighat"
    if int(manifest.get("version", 0)) > BIGHAT_VERSION:
        raise HTTPException(
            400,
            f"This .bighat file was made with a newer version of BIG Hat "
            f"(v{manifest.get('version')}). Please update the app and try again.",
        )
    return manifest, doc, assets, signature


@router.post("/inspect", response_model=InspectResult)
async def inspect_bighat(file: UploadFile = File(...)) -> InspectResult:
    """Read a .bighat without committing it to the DB. Lets the frontend
    show a confirmation dialog before importing ('You're about to import
    "80s Music Trivia" — 4 rounds, signed by BIG Hat Entertainment.
    Continue?')."""
    payload = await file.read()
    manifest, doc, assets, signature = _parse_bighat(payload)
    # Default type is "round" for legacy v1 files.
    ctype = manifest.get("type") or "round"
    return InspectResult(
        type=ctype,
        name=manifest.get("name") or manifest.get("round_name") or doc.get("name") or "Untitled",
        app_version=manifest.get("app_version", "unknown"),
        created_at=manifest.get("created_at", ""),
        asset_count=len(assets),
        signed=bool(signature),
        file_size=len(payload),
    )


# ============================================================
# Third-party generator translation helpers (v32.0.0-alpha.23)
# ============================================================
#
# The merchant uses an external web tool ("`.bighat` Round Generator")
# that exports `.bighat` archives with a richer per-question shape than
# what the local Round Maker schema expects. Without translation, the
# imported rounds render with blank question text, unchecked correct
# answers, and missing title cards — every UX symptom the merchant
# reported on alpha.22.

def _coerce_question_text(q: dict) -> str:
    """Pull the question/prompt text out of a question dict, trying the
    field names every generator I've seen in the wild has used."""
    for k in ("question", "prompt", "text", "q", "title"):
        v = q.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def _coerce_options_and_answer(q: dict) -> tuple[list[str], int | None, str]:
    """Return `(options_strings, correctOption_idx_or_None, answer_text)`.

    Handles four shapes:
      1. `options: ["A text", "B text", "C text", "D text"]` + a
         separate `answer` / `correctAnswer` / `correct_answer` string
         or letter, OR a separate `correctOption: int`.
      2. `options: [{text: "...", correct: true}, ...]`  (the external
         generator's preferred shape — that's what the screenshot
         shows: option A has `correct: true`, the rest false).
      3. `options: [{label/value: "...", isCorrect/is_correct: true}, ...]`
         (camelCase / snake_case variants — also seen).
      4. Per-key flatlay: `option_a, option_b, option_c, option_d` +
         `correct_answer: "A"` or `correctAnswer: "A"`.
    """
    raw = q.get("options")

    options: list[str] = []
    correct_idx: int | None = None

    if isinstance(raw, list) and raw:
        if all(isinstance(o, str) for o in raw):
            options = [str(o) for o in raw]
        else:
            for o in raw:
                if isinstance(o, dict):
                    text = ""
                    for k in ("text", "label", "value", "option", "answer"):
                        v = o.get(k)
                        if isinstance(v, str) and v.strip():
                            text = v.strip()
                            break
                    options.append(text)
                    if correct_idx is None:
                        for ck in ("correct", "is_correct", "isCorrect", "right", "is_right"):
                            if o.get(ck) is True:
                                correct_idx = len(options) - 1
                                break
                else:
                    options.append(str(o))
    else:
        # Per-key flatlay (option_a / option_b / …).
        for i, letter in enumerate(["a", "b", "c", "d"]):
            v = q.get(f"option_{letter}") or q.get(f"option{letter.upper()}")
            if isinstance(v, str) and v.strip():
                options.append(v.strip())

    # Resolve answer / correctOption from explicit fields if not derived
    # already from a per-option flag.
    if correct_idx is None:
        if isinstance(q.get("correctOption"), int):
            correct_idx = q["correctOption"]
        elif isinstance(q.get("correct_option"), int):
            correct_idx = q["correct_option"]
        else:
            # Also include plain `answer` here — for MC rounds it commonly
            # contains the correct option's TEXT (or its A/B/C/D letter)
            # and we want to surface that as the checked checkbox in the UI.
            for ak in ("correctAnswer", "correct_answer", "correct", "answer"):
                raw_a = q.get(ak)
                if isinstance(raw_a, str) and raw_a.strip():
                    cleaned = raw_a.strip().upper()
                    # Letter shortcut (A/B/C/D)
                    if cleaned in {"A", "B", "C", "D"} and len(options) >= ord(cleaned) - 64:
                        correct_idx = ord(cleaned) - ord("A")
                        break
                    # Otherwise match by text against the options list.
                    for i, opt in enumerate(options):
                        if opt.strip().casefold() == raw_a.strip().casefold():
                            correct_idx = i
                            break
                    if correct_idx is not None:
                        break

    # answer_text — pick the explicit field if present, else derive from
    # the correctOption back into a string. Some non-MC round types use
    # `answer` directly without an options list.
    answer_text = ""
    for ak in ("answer", "correctAnswer", "correct_answer"):
        v = q.get(ak)
        if isinstance(v, str) and v.strip():
            answer_text = v.strip()
            break
    # If the explicit field was just a letter shortcut (A/B/C/D) and we
    # resolved an index into the options list, prefer the resolved option
    # text — letters are ambiguous and the dashboard renders the answer
    # string directly into the slide.
    if correct_idx is not None and 0 <= correct_idx < len(options):
        if not answer_text or (
            len(answer_text) == 1 and answer_text.upper() in {"A", "B", "C", "D"}
        ):
            answer_text = options[correct_idx]

    return options, correct_idx, answer_text


def _normalise_question(q: dict, idx: int) -> dict:
    """Translate a third-party question dict into the local schema's
    canonical shape. Pass-through fields beyond the canonical six are
    preserved on the resulting dict so nothing the generator might
    later add gets dropped.
    """
    if not isinstance(q, dict):
        return {"number": idx + 1, "question": str(q or ""), "answer": "",
                "options": None, "correctOption": None}

    out = dict(q)
    out["number"] = q.get("number") if isinstance(q.get("number"), int) else idx + 1
    out["question"] = _coerce_question_text(q)
    opts, correct_idx, answer_text = _coerce_options_and_answer(q)
    if opts:
        out["options"] = opts
    if correct_idx is not None:
        out["correctOption"] = correct_idx
    if answer_text:
        out["answer"] = answer_text
    # Guarantee both required fields exist on the dict so QuestionItem
    # validation doesn't raise (empty strings render as "undefined…"
    # placeholders in the UI which is correct UX for a malformed row).
    out.setdefault("answer", "")
    out.setdefault("question", "")
    return out


async def _ingest_cover_image(assets: dict[str, bytes]) -> str | None:
    """If the .bighat archive bundles a title-card / cover image under
    `assets/title_card.*` or `assets/cover.*` (the external generator's
    convention is `title_card.png`), upload it to GridFS and return the
    file id so the importer can persist `doc.cover_image_id`. Returns
    None if no recognisable cover asset was bundled.
    """
    if not assets or db is None:
        return None
    # Heuristic: any asset whose filename stem is in our canonical set,
    # regardless of extension.
    canonical_stems = {"title_card", "title", "cover", "cover_image"}
    chosen: tuple[str, bytes] | None = None
    for asset_path, blob in assets.items():
        stem = Path(asset_path).stem.lower()
        if stem in canonical_stems:
            chosen = (asset_path, blob)
            break
    if not chosen:
        return None
    name, blob = chosen
    suffix = Path(name).suffix.lower()
    mime = {
        ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".gif": "image/gif", ".webp": "image/webp",
    }.get(suffix, "application/octet-stream")
    try:
        from motor.motor_asyncio import AsyncIOMotorGridFSBucket
        bucket = AsyncIOMotorGridFSBucket(db)
        file_id = await bucket.upload_from_stream(
            f"imported-{name}",
            io.BytesIO(blob),
            metadata={"contentType": mime, "imported_from": ".bighat"},
        )
        return str(file_id)
    except Exception as exc:                       # pragma: no cover
        logger.warning("[bighat-files] cover image upload failed: %s", exc)
        return None


async def _import_zip_bytes(payload: bytes) -> ImportResult:
    if db is None:
        raise HTTPException(500, "database not initialised")
    manifest, doc, assets, signature = _parse_bighat(payload)
    raw_type = str(manifest.get("type") or "round")
    # Normalise alias → canonical content type. Third-party round
    # generators emit the round-KIND (MC/BIG/REG/MISC/MYS) in
    # `manifest.type`; treat all of those as `round`. `_parse_bighat`
    # already accepted the file via KNOWN_TYPES, so reaching this branch
    # with a non-canonical alias is the expected path.
    _ROUND_ALIASES = {"mc", "reg", "misc", "mys", "big", "round"}
    if raw_type.lower() in _ROUND_ALIASES:
        content_type = "round"
        # Stash the original code so the round_type backfill below can
        # promote "MC" / "BIG" / ... to `RoundResponse.round_type`.
        manifest.setdefault("round_type", raw_type.upper() if raw_type.lower() != "round" else None)
    else:
        content_type = raw_type
    if content_type not in BIGHAT_TYPES:
        raise HTTPException(400, f"Unknown content type: {raw_type}")
    spec = BIGHAT_TYPES[content_type]

    # If this install has a signing key configured and the file is signed,
    # verify before importing. (Unsigned files are still allowed — the
    # signing flow is only required for paid packs.)
    if signature and _signing_key():
        # Re-pack the manifest/payload bytes EXACTLY as they were on export.
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            mb = zf.read("manifest.json")
            pb = zf.read("payload.json" if "payload.json" in zf.namelist() else "round.json")
        asset_hashes = [hashlib.sha256(blob).hexdigest() for _, blob in assets.items()]
        if not _verify_signature(mb, pb, asset_hashes, signature):
            raise HTTPException(400, "Signature mismatch — file may be tampered or signed by a different publisher.")

    # Mint a fresh id so re-importing creates a new document. Strip BSON id.
    new_id = str(uuid.uuid4())
    doc.pop("_id", None)
    doc["id"] = new_id
    doc["created_at"] = datetime.now(timezone.utc).isoformat()
    doc["imported_from"] = ".bighat"
    # ALWAYS land a "draft" status. The previous `if "status" in doc` guard
    # silently dropped this when the source payload lacked a status field
    # entirely (as third-party round generators do), leaving the inserted
    # row without the `status: str` field that `RoundResponse` requires.
    # One bad row was enough to make `GET /api/roundmaker/rounds` 500 with
    # a Pydantic validation error, hiding ALL rounds from the dashboard.
    # See v32.0.0-alpha.21 changelog for the failure mode.
    doc["status"] = "draft"
    name = (
        doc.get("name")
        or doc.get("title")
        or manifest.get("name")
        or manifest.get("round_name")
        or f"Imported {spec.pretty}"
    )
    doc["name"] = name

    # Round-specific required fields. `RoundResponse` declares `round_type`
    # as a non-optional `str`; external generators emit the round kind in
    # `manifest.type` (e.g. "MC", "REG", "MISC", "MYS", "BIG") and DON'T
    # always copy it into the payload. Backfill from the manifest before
    # insertion so the list endpoint can validate the row.
    if content_type == "round":
        rt = (
            doc.get("round_type")
            or manifest.get("round_type")
            or str(manifest.get("type") or "").upper()
            or "MC"
        )
        # Only well-known codes survive; anything weird falls back to MC.
        if rt not in {"MC", "REG", "MISC", "MYS", "BIG"}:
            rt = "MC"
        doc["round_type"] = rt
        # `pptx_path` is declared `Optional[str]` so None is fine, but
        # `questions` is required as a list. Default to [] so the row
        # is renderable even if the upstream payload was empty.
        if not isinstance(doc.get("questions"), list):
            doc["questions"] = []
        doc.setdefault("pptx_path", None)

        # ─── Question shape normalisation (v32.0.0-alpha.23) ────────
        # The local `QuestionItem` schema wants
        #   { number, question, answer, options:[str,…], correctOption:int }
        # but third-party generators (the external `.bighat Round
        # Generator` web tool the merchant uses) ship a richer mix:
        #   • question text under `question` | `prompt` | `text` | `q`
        #   • options either as plain strings, OR as objects
        #     `{ text|label|value, correct|is_correct|isCorrect }`
        #     OR as `option_a / option_b / option_c / option_d`
        #   • answer under `answer` | `correctAnswer` | `correct_answer`
        #     OR derivable from `correct: true` on one of the options
        # If we just insert their payload verbatim, the dashboard
        # renders the placeholder "Question undefined…" and no checkbox
        # ticks — exactly what the merchant reported in alpha.22.
        doc["questions"] = [_normalise_question(q, idx)
                            for idx, q in enumerate(doc["questions"])]

        # ─── Title card asset extraction (v32.0.0-alpha.23) ─────────
        # If the .bighat bundles a title-card image at
        # `assets/title_card.*` (the external generator's convention)
        # or anything pattern-matching cover/title in the assets dir,
        # promote it into GridFS and set `doc.cover_image_id` so the
        # Round Maker UI renders the thumbnail.
        ci = await _ingest_cover_image(assets)
        if ci:
            doc["cover_image_id"] = ci

    # Asset rehydration. We don't restore them into GridFS automatically
    # (would need to know the bucket layout per type) — instead we stash
    # them under doc["imported_assets"] so a per-type post-processor can
    # pick them up. The export is still functional; the cover image just
    # needs to be re-uploaded on first edit.
    if assets:
        doc["imported_assets"] = list(assets.keys())

    await db[spec.collection].insert_one(doc)
    logger.info("[bighat-files] imported %s %s (%s)", content_type, new_id, name)

    return ImportResult(
        id=new_id, name=name, type=content_type,
        signed=bool(signature),
        round_id=new_id if content_type == "round" else None,
        round_type=doc.get("round_type") if content_type == "round" else None,
    )


@router.post("/import", response_model=ImportResult)
async def import_bighat(file: UploadFile = File(...)):
    """Import a `.bighat` file uploaded via a browser <input type=file>."""
    payload = await file.read()
    return await _import_zip_bytes(payload)


@router.post("/import-from-path", response_model=ImportResult)
async def import_from_path(request: Request, path: str = Form(...)):
    """Import a `.bighat` file by absolute path on the local machine.
    Used by the .bighat file-association handoff in Windows Explorer."""
    if not _is_native_mode():
        raise HTTPException(404, "Not available in this deployment mode")
    client_host = request.client.host if request.client else ""
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


@router.get("/types")
async def list_types() -> dict:
    """List supported content types. Used by the import dialog to show the
    user which kinds of .bighat files they can import."""
    return {
        "version": BIGHAT_VERSION,
        "format": BIGHAT_FORMAT,
        "types": {k: v.pretty for k, v in BIGHAT_TYPES.items()},
        "signing_enabled": bool(_signing_key()),
    }


@router.get("/")
async def health() -> dict:
    return {"ok": True, "format": BIGHAT_FORMAT, "version": BIGHAT_VERSION}
