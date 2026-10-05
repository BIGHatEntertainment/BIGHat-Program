"""alpha.74: read .bighat files made by the BIGHat File Creator tool (ZIP: manifest.json + payload.json + assets/).

The program's own rounds are plain JSON (schema "bighat-round/v1"). This module turns a Creator ZIP into that JSON,
so every part of the program (Files tool, Round Generator, presenter) can use it.

Nothing here raises for a bad file: bad input returns (None, "reason") so one broken file never breaks a list.
"""
import base64
import io
import json
import re
import uuid
import zipfile
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

ROUND_TYPES = ("MC", "REG", "MISC", "MYS", "BIG")
_IMG_MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp"}
_COVER_STEMS = {"cover", "title_card", "title", "cover_image"}
MAX_ASSET_BYTES = 12 * 1024 * 1024


def is_zip(data: bytes) -> bool:
    return data[:4] in (b"PK\x03\x04", b"PK\x05\x06")


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").strip().lower()).strip("-")
    return s or "round"


def _data_url(name: str, blob: bytes) -> Optional[str]:
    mime = _IMG_MIME.get(Path(name).suffix.lower())
    if not mime or len(blob) > MAX_ASSET_BYTES:
        return None
    return f"data:{mime};base64,{base64.b64encode(blob).decode('ascii')}"


def _round_type(manifest: dict, payload: dict, filename: str) -> str:
    for cand in (manifest.get("round_type"), payload.get("round_type"), manifest.get("type")):
        c = str(cand or "").upper()
        if c in ROUND_TYPES:
            return c
    m = re.match(r"^(MC|REG|MISC|MYS|BIG)[_\-. ]", (filename or "").upper())
    return m.group(1) if m else ""


def read_zip(data: bytes, filename: str = "") -> Tuple[Optional[Dict[str, Any]], str]:
    """Return (round_doc, "") or (None, reason).  round_doc is the program's own round JSON (schema bighat-round/v1)."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except (zipfile.BadZipFile, OSError):
        return None, "not a valid zip archive"
    try:
        names = zf.namelist()
        for n in names:
            parts = n.replace("\\", "/").split("/")
            if n.startswith("/") or ".." in parts:
                return None, f"unsafe path inside archive: {n!r}"
        if "manifest.json" not in names or "payload.json" not in names:
            return None, "missing manifest.json or payload.json"
        try:
            manifest = json.loads(zf.read("manifest.json").decode("utf-8-sig"))
            payload = json.loads(zf.read("payload.json").decode("utf-8-sig"))
        except (UnicodeDecodeError, ValueError):
            return None, "manifest.json or payload.json is not valid JSON"
        if not isinstance(manifest, dict) or not isinstance(payload, dict):
            return None, "manifest/payload must be JSON objects"
        if str(manifest.get("type") or "round").lower() not in ("round", "mc", "reg", "misc", "mys", "big"):
            return None, f"not a round file (type={manifest.get('type')!r})"

        rt = _round_type(manifest, payload, filename)
        if not rt:
            return None, "round type (MC/REG/MISC/MYS/BIG) not found"
        name = str(manifest.get("round_name") or payload.get("name") or Path(filename).stem or "Round").strip()

        def asset(ref: Any) -> Optional[str]:
            if not isinstance(ref, str) or not ref:
                return None
            ref = ref.replace("\\", "/")
            try:
                blob = zf.read(ref)
            except KeyError:
                return None
            return _data_url(ref, blob)

        questions = []
        for q in payload.get("questions") or []:
            if not isinstance(q, dict):
                continue
            q = dict(q)
            media = q.get("media") if isinstance(q.get("media"), dict) else {}
            for key in ("image", "audio", "video"):
                url = asset(media.get(key)) if key == "image" else None
                if url:
                    q["image_data_url"] = url
            questions.append(q)

        cover = asset(payload.get("cover_image"))
        if not cover:
            for n in names:
                if n.startswith("assets/") and Path(n).stem.lower() in _COVER_STEMS:
                    cover = _data_url(n, zf.read(n))
                    if cover:
                        break

        doc: Dict[str, Any] = {
            "schema": "bighat-round/v1",
            "id": str(manifest.get("content_id") or uuid.uuid4()),
            "round_type": rt,
            "name": name,
            "questions": questions,
            "tiebreaker": payload.get("tiebreaker"),
            "status": "draft",
            "imported_from": "bighat-file-creator",
            "created_at": str(manifest.get("created_at") or ""),
        }
        if cover:
            doc["cover_image_data_url"] = cover
        return doc, ""
    except Exception as e:                                     # noqa: BLE001  one bad file must never break a list
        return None, f"unreadable: {type(e).__name__}"
    finally:
        zf.close()


def normalise(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Make the questions match the Round Generator's shape (number/question/answer/options/correctOption)."""
    try:
        from routes.bighat_files import _normalise_question
    except Exception:                                          # noqa: BLE001
        return doc
    doc["questions"] = [_normalise_question(q, i) for i, q in enumerate(doc.get("questions") or [])]
    return doc


def load_any(data: bytes, filename: str = "") -> Tuple[Optional[Dict[str, Any]], str]:
    """Accept either format: the program's own JSON round, or a Creator ZIP."""
    if is_zip(data):
        doc, why = read_zip(data, filename)
        return (normalise(doc), "") if doc else (None, why)
    try:
        doc = json.loads(data.decode("utf-8-sig"))
    except (UnicodeDecodeError, ValueError):
        return None, "neither a zip archive nor valid JSON"
    if isinstance(doc, dict) and str(doc.get("schema", "")).lower().startswith("bighat-round"):
        return doc, ""
    return None, "unrecognised .bighat content"
