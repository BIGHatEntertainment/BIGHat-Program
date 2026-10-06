"""GLOBAL SLIDES: company intro, rules, and the auto-generated Format slide.

Played once per show, BETWEEN the location slides and round 1.
Order (merchant-confirmed 2026-10-01):  ... location -> Company -> Rules -> Format -> round 1 ...

Disk is the source of truth:
  <Files>/Trivia/GlobalSlides/global_slides.json     settings (enabled flags, order, text)
  <Files>/Trivia/GlobalSlides/<id>.<ext>             uploaded images (company, rules, background)

Settings shape:
{
  "company": {"enabled": true, "images": ["<file>", ...]},   # uploaded slide image(s)
  "rules":   {"enabled": true, "images": ["<file>", ...]},
  "format":  {"enabled": true, "background": "<file>|null", "show_themes": true}
}
Global only (no per-location override), per merchant.
"""
import json
import re
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

KINDS = ("company", "rules", "sponsors")   # image-slide lists the merchant uploads (alpha.88: + sponsors)
SPONSOR_FINAL = "sponsor_final"        # alpha.88: ONE special last sponsor slide ("become a sponsor")
IMG_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
MAX_BYTES = 100 * 1024 * 1024

DEFAULTS: Dict[str, Any] = {
    "company": {"enabled": True, "images": []},
    "rules": {"enabled": True, "images": []},
    "sponsors": {"enabled": True, "images": [], "final": None},
    "format": {"enabled": True, "background": None, "show_themes": True},
}


def _root() -> Path:
    from native_slides import _docs_root
    p = _docs_root() / "Files" / "Trivia" / "GlobalSlides"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _settings_path() -> Path:
    return _root() / "global_slides.json"


def _merge(saved: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    out = json.loads(json.dumps(DEFAULTS))
    for k, v in (saved or {}).items():
        if k in out and isinstance(v, dict):
            out[k].update(v)
    # drop references to files that no longer exist
    for k in KINDS:
        out[k]["images"] = [f for f in out[k].get("images", []) if (_root() / f).is_file()]
    fin = out["sponsors"].get("final")
    if fin and not (_root() / fin).is_file():
        out["sponsors"]["final"] = None
    bg = out["format"].get("background")
    if bg and not (_root() / bg).is_file():
        out["format"]["background"] = None
    return out


def load() -> Dict[str, Any]:
    try:
        p = _settings_path()
        saved = json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}
    except (OSError, ValueError):
        saved = {}
    return _merge(saved)


def save(settings: Dict[str, Any]) -> Dict[str, Any]:
    cur = _merge(settings)
    p = _settings_path()
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cur, indent=2), encoding="utf-8")
    tmp.replace(p)
    return cur


def add_image(kind: str, filename: str, data: bytes) -> Dict[str, Any]:
    """kind: 'company' | 'rules' | 'sponsors' | 'sponsor_final' | 'format_bg'."""
    if kind not in KINDS + ("format_bg", SPONSOR_FINAL):
        raise ValueError(f"unknown kind {kind!r}")
    ext = Path(filename or "").suffix.lower()
    if ext not in IMG_EXTS:
        raise ValueError("unsupported image type (use png, jpg, webp or gif)")
    if len(data) > MAX_BYTES:
        raise ValueError("image too large (max 100 MB)")
    if not data:
        raise ValueError("empty file")
    name = f"{kind}-{uuid.uuid4().hex[:10]}{ext}"
    (_root() / name).write_bytes(data)
    cur = load()
    if kind == SPONSOR_FINAL:                      # a single slot: a new upload replaces the old one
        old = cur["sponsors"].get("final")
        cur["sponsors"]["final"] = name
        if old:
            try:
                (_root() / old).unlink()
            except OSError:
                pass
    elif kind == "format_bg":
        old = cur["format"].get("background")
        cur["format"]["background"] = name
        if old:
            try:
                (_root() / old).unlink()
            except OSError:
                pass
    else:
        cur[kind]["images"].append(name)
    return save(cur)


def remove_image(file: str) -> Dict[str, Any]:
    if not re.fullmatch(r"[A-Za-z0-9._-]+", file or ""):
        raise ValueError("bad file name")
    cur = load()
    for k in KINDS:
        cur[k]["images"] = [f for f in cur[k]["images"] if f != file]
    if cur["sponsors"].get("final") == file:
        cur["sponsors"]["final"] = None
    if cur["format"].get("background") == file:
        cur["format"]["background"] = None
    try:
        (_root() / file).unlink()
    except OSError:
        pass
    return save(cur)


def image_path(file: str) -> Optional[Path]:
    if not re.fullmatch(r"[A-Za-z0-9._-]+", file or ""):
        return None
    p = _root() / file
    return p if p.is_file() else None
