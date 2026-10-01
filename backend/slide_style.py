"""Slide style settings (global + per-location). Disk is the source of truth.

Global : <Files>/Trivia/slide_style.json
Location: <Files>/Locations/<slug>/slide_style.json

Shape: {"use_global": bool (location only), "background": {"mode": "default"|"custom",
        "color": "#RRGGBB", "fill": "gradient"|"solid"}}
Only slides using the default blue background are restyled.
"""
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_BG = {"mode": "default", "color": "#1657E8", "fill": "gradient"}
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def _files_root() -> Path:
    from native_slides import _docs_root
    return _docs_root() / "Files"


def global_path() -> Path:
    return _files_root() / "Trivia" / "slide_style.json"


def location_path(slug: str) -> Path:
    return _files_root() / "Locations" / slug / "slide_style.json"


def clean_background(raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    raw = raw or {}
    color = raw.get("color") or DEFAULT_BG["color"]
    if not _HEX.match(str(color)):
        color = DEFAULT_BG["color"]
    return {
        "mode": "custom" if raw.get("mode") == "custom" else "default",
        "color": color,
        "fill": "solid" if raw.get("fill") == "solid" else "gradient",
    }


def _read(p: Path) -> Dict[str, Any]:
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except Exception:
        return {}


def _write(p: Path, doc: Dict[str, Any]) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(doc, indent=2), encoding="utf-8")


def load_global() -> Dict[str, Any]:
    return {"background": clean_background(_read(global_path()).get("background"))}


def save_global(background: Dict[str, Any]) -> Dict[str, Any]:
    doc = {"background": clean_background(background)}
    _write(global_path(), doc)
    return doc


def load_location(slug: str) -> Dict[str, Any]:
    d = _read(location_path(slug))
    return {"use_global": d.get("use_global", True) is not False,
            "background": clean_background(d.get("background"))}


def save_location(slug: str, use_global: bool, background: Dict[str, Any]) -> Dict[str, Any]:
    doc = {"use_global": bool(use_global), "background": clean_background(background)}
    _write(location_path(slug), doc)
    return doc


def effective_background(slug: Optional[str]) -> Dict[str, Any]:
    if slug:
        loc = load_location(slug)
        if not loc["use_global"]:
            return loc["background"]
    return load_global()["background"]


def _shade(hexc: str, f: float) -> str:
    r, g, b = (int(hexc[i:i + 2], 16) for i in (1, 3, 5))
    return "#%02X%02X%02X" % tuple(max(0, min(255, int(v * f))) for v in (r, g, b))


def css_for(bg: Dict[str, Any]) -> Optional[str]:
    """None = keep the default blue gradient."""
    if bg.get("mode") != "custom":
        return None
    c = bg["color"]
    if bg.get("fill") == "solid":
        return c
    return f"radial-gradient(circle at center, {c} 5%, {_shade(c, 0.95)} 20%, #191919 90%)"


def apply_to_slides(slides: List[Dict[str, Any]], slug: Optional[str], default_css: str) -> List[Dict[str, Any]]:
    css = css_for(effective_background(slug))
    if not css:
        return slides
    for s in slides:
        if s.get("background") == default_css:
            s["background"] = css
    return slides


def slug_from_presentation(pres: Dict[str, Any]) -> Optional[str]:
    loc = (pres or {}).get("location") or ""
    if not loc:
        return None
    from native_slides import _slugify
    tail = loc.replace("\\", "/").rstrip("/").split("/")[-1]
    return tail if "-" in tail else _slugify(tail)
