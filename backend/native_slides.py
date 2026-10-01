"""
v32.0.0-alpha.46 — native slide section renderer.

DISK IS THE SOURCE OF TRUTH (see PRD.md § "DISK STATE IS THE ABSOLUTE
SOURCE OF TRUTH"). This module builds Editor-compatible slide dicts
directly from the `.bighat` presentation + round manifests on disk,
completely bypassing the SharePoint / PPTX pipeline.

The output shape matches `models.Slide` / `models.Element` so the
existing Editor.jsx can render it without any frontend changes:

    {
      id: "slide-<uuid>",
      order: N,
      background: "<css gradient>",
      elements: [
        {id, type: 'text'|'image', content, x, y, width, height, fontSize, ...},
        ...
      ],
      metadata: {roundType, roundNumber, slideIndexInRound, isRoundTitle, ...}
    }

Canvas is 1920x1080. All coordinates are absolute pixels in that space.
"""
from __future__ import annotations

import json
import logging
import os
import re
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 16:9 stage. All positions/sizes below are in this coordinate system.
STAGE_W = 1920
STAGE_H = 1080

# Canonical brand background (blue radial → dark) used across the app.
BG_BLUE = "radial-gradient(circle at center, #1657E8 5%, #1F5EE9 20%, #191919 90%)"
BG_DARK = "linear-gradient(180deg, #050a1a 0%, #000000 100%)"
BG_GOLD = "radial-gradient(circle at center, #f4c430 0%, #b8860b 40%, #191919 90%)"


def _uid(prefix: str = "elem") -> str:
    return f"{prefix}-{uuid.uuid4()}"


def _text(
    content: str, *, x: int, y: int, w: int, h: int,
    size: int = 60, weight: str = "700", color: str = "#ffffff",
    align: str = "center", valign: str = "middle",
    family: str = "Inter, system-ui, sans-serif",
    zindex: Optional[int] = None,
) -> Dict[str, Any]:
    return {
        "id": _uid("text"),
        "type": "text",
        "content": content,
        "x": x, "y": y, "width": w, "height": h,
        "fontSize": size,
        "fontWeight": weight,
        "color": color,
        "textAlign": align,
        "verticalAlign": valign,
        "fontFamily": family,
        "lineHeight": 1.2,
        "overflow": "hidden",
        **({"zIndex": zindex} if zindex is not None else {}),
    }


def _image(
    src: str, *, x: int, y: int, w: int, h: int, zindex: Optional[int] = None
) -> Dict[str, Any]:
    return {
        "id": _uid("img"),
        "type": "image",
        "src": src,
        "x": x, "y": y, "width": w, "height": h,
        **({"zIndex": zindex} if zindex is not None else {}),
    }


def _slide(
    order: int, elements: List[Dict[str, Any]],
    *, background: str = BG_BLUE, metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "id": _uid("slide"),
        "order": order,
        "background": background,
        "elements": elements,
        "metadata": metadata or {},
    }


# ---------------------------------------------------------------- disk lookup

def _docs_root() -> Path:
    """Same rules as trivia_viewer + native.files_router (inline for PyInstaller)."""
    override = os.environ.get("BIGHAT_FILES_DIR")
    if override:
        return Path(override).expanduser()
    home = Path.home()
    base = home / "Documents"
    if not base.exists():
        base = home
    return base / "BIG Hat Entertainment"


def bundled_asset_path(*parts: str) -> Optional[Path]:
    """Resolve a file bundled with the backend, in BOTH layouts:
    dev (backend/assets/...) and the PyInstaller-frozen app (_MEIPASS/assets/...).
    Returns None if it is not there."""
    import sys
    roots = []
    mei = getattr(sys, "_MEIPASS", None)
    if mei:
        roots.append(Path(mei))
    roots.append(Path(__file__).resolve().parent)
    for r in roots:
        p = r.joinpath(*parts)
        if p.is_file():
            return p
    return None


_GRADE_GIF_CACHE: Dict[str, str] = {}


def grade_gif_src() -> str:
    """The BIG Hat 'Time to grade' GIF (backend/assets/slides/times_up.gif) as an
    inline data URL so it renders in any webview origin. Falls back to the old
    generic SVG ONLY if the bundled file is somehow missing (build lock-in
    makes that impossible in releases)."""
    if "src" in _GRADE_GIF_CACHE:
        return _GRADE_GIF_CACHE["src"]
    p = bundled_asset_path("assets", "slides", "times_up.gif")
    if p is not None:
        try:
            import base64
            src = "data:image/gif;base64," + base64.b64encode(p.read_bytes()).decode("ascii")
            _GRADE_GIF_CACHE["src"] = src
            return src
        except OSError as e:
            logger.warning("[native-slides] grade gif unreadable: %s", e)
    logger.error("[native-slides] times_up.gif missing - falling back to generic SVG")
    return "/Time_To_Grade.svg"


def _to_data_url(rel_path: str) -> Optional[str]:
    """v32.0.0-alpha.49: **Inline the file bytes as a `data:` URL.**

    This program runs on the user's local PC — we have plenty of RAM and
    disk throughput. Cloud-scale worries about payload size do not apply.
    Reading an 18.9 MB host GIF and shipping it inline as a data URL is
    fine; it saves a whole round-trip and dodges the tauri://→http://
    origin mismatch that killed rendering in alpha.48. Returns None on
    error so the caller can fall back to text.
    """
    docs = _docs_root()
    p = docs / rel_path
    if not p.exists() or not p.is_file():
        return None
    ext = p.suffix.lower()
    mime_map = {
        ".gif": "image/gif", ".png": "image/png",
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".webp": "image/webp", ".svg": "image/svg+xml",
        ".mp4": "video/mp4", ".webm": "video/webm",
    }
    mime = mime_map.get(ext, "application/octet-stream")
    try:
        import base64
        data = p.read_bytes()
        b64 = base64.b64encode(data).decode("ascii")
        return f"data:{mime};base64,{b64}"
    except (OSError, MemoryError) as e:
        logger.warning("[native-slides] data-URL encode failed for %s: %s", p, e)
        return None


def _to_api_url(rel_path: str) -> str:
    """Return an image URL for a `Files/...` disk path.

    v32.0.0-alpha.49: **Data URL first, network URL last.** In native
    mode the app lives on the user's PC — their machine has way more
    resources than a cloud API and no cross-origin routing to worry
    about. Inlining the bytes is the cleanest, most reliable way to
    ship the image to whichever webview origin the frontend is on
    (tauri://, http://127.0.0.1:3000, tauri.localhost, etc). Only falls
    back to a network URL if the file couldn't be encoded.
    """
    data = _to_data_url(rel_path)
    if data:
        return data
    from urllib.parse import quote
    return f"/api/native/files/raw?path={quote(rel_path, safe='')}"


def _slugify(s: str) -> str:
    import re as _re
    raw = (s or "").strip().lower()
    if not raw:
        return ""
    return _re.sub(r"[^a-z0-9._@-]+", "-", raw).strip("-_.")


def load_host_asset(pres: Dict[str, Any]) -> Dict[str, Any]:
    """Locate the host's 9:16 vertical / 16:9 landscape image on disk.

    Returns `{"image_url": str | None, "aspect": "9:16"|"16:9", "raw_path": str|None}`.

    v32.0.0-alpha.49: **Filesystem walk is authoritative.** We no longer
    trust the `host.json` fields alone — if they're missing or stale we
    still discover `host-9x16.*`, `host-16x9.*`, `avatar.*`, `profile.*`
    files in the host folder. Priority order:
        1. `host_image_9x16` from host.json  (if file exists on disk)
        2. Any `host-9x16.<ext>` file in the host folder
        3. `host_image_16x9` from host.json  (if file exists on disk)
        4. Any `host-16x9.<ext>` file in the host folder
        5. `profile_picture` from host.json  (if file exists on disk)
        6. `avatar.<ext>` / `profile.<ext>` in the host folder
    """
    from urllib.parse import unquote, urlparse, parse_qs

    host_name = pres.get("host") or pres.get("hostName") or pres.get("host_name") or ""
    host_email = pres.get("hostEmail") or ""
    host_id = pres.get("hostId") or pres.get("host_id") or ""
    candidates = []
    if host_email:
        candidates.append(_slugify(host_email))
    if host_name:
        candidates.append(_slugify(host_name))
    if host_id:
        candidates.append(_slugify(host_id))

    docs = _docs_root()
    hosts_root = docs / "Files" / "Hosts"
    IMG_EXTS = (".gif", ".png", ".jpg", ".jpeg", ".webp")

    def _rel_if_exists(val: str, docs_root: Path) -> Optional[str]:
        """Resolve a host.json path-value to a docs-relative path IFF the
        file exists on disk. Accepts `/api/native/files/raw?path=Files/...`,
        `Files/...`, or absolute paths."""
        if not val:
            return None
        rel = None
        if val.startswith("http") and "path=" in val:
            parsed = urlparse(val)
            q = parse_qs(parsed.query)
            rel = unquote(q.get("path", [""])[0])
        elif val.startswith("/api/native/files/raw"):
            parsed = urlparse(val)
            q = parse_qs(parsed.query)
            rel = unquote(q.get("path", [""])[0])
        elif val.startswith("Files/"):
            rel = val
        elif val.startswith("/") and (docs_root / val.lstrip("/")).exists():
            rel = val.lstrip("/")
        if rel and (docs_root / rel).exists():
            return rel
        return None

    def _find_by_stem(host_dir: Path, stems: List[str]) -> Optional[Path]:
        for stem in stems:
            for ext in IMG_EXTS:
                p = host_dir / f"{stem}{ext}"
                if p.exists():
                    return p
        return None

    def _rank_asset(host_dir: Path, host_json_path: Optional[Path]):
        """Return the best `(rel_path, aspect)` tuple for a given host
        folder, or None.

        v32.0.0-alpha.51: **PREFER 16:9 over 9:16.** Slide 1 is a
        landscape wide-view host image per the merchant's current spec.
        The 9:16 portrait variant is a fallback (some hosts only have
        the vertical asset).
        """
        json_data = {}
        if host_json_path and host_json_path.exists():
            try:
                json_data = json.loads(host_json_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                json_data = {}

        # Priority 1: JSON says 16x9 AND file exists (LANDSCAPE — wide view)
        rel = _rel_if_exists(json_data.get("host_image_16x9", ""), docs)
        if rel:
            return rel, "16:9"
        # Priority 2: host-16x9.* file on disk
        p = _find_by_stem(host_dir, ["host-16x9", "host_16x9", "16x9"])
        if p:
            return str(p.relative_to(docs)).replace("\\", "/"), "16:9"
        # Priority 3: JSON says 9x16 AND file exists (portrait fallback)
        rel = _rel_if_exists(json_data.get("host_image_9x16", ""), docs)
        if rel:
            return rel, "9:16"
        # Priority 4: host-9x16.* file on disk
        p = _find_by_stem(host_dir, ["host-9x16", "host_9x16", "9x16"])
        if p:
            return str(p.relative_to(docs)).replace("\\", "/"), "9:16"
        # Priority 5: JSON profile_picture
        rel = _rel_if_exists(json_data.get("profile_picture", ""), docs)
        if rel:
            return rel, "1:1"
        # Priority 6: avatar.* / profile.*
        p = _find_by_stem(host_dir, ["avatar", "profile"])
        if p:
            return str(p.relative_to(docs)).replace("\\", "/"), "1:1"
        return None

    if not hosts_root.exists():
        return {"image_url": None, "aspect": None, "raw_path": None}

    # Try the candidate slug folders first
    for slug in candidates:
        if not slug:
            continue
        host_dir = hosts_root / slug
        if not host_dir.exists():
            continue
        result = _rank_asset(host_dir, host_dir / "host.json")
        if result:
            rel, aspect = result
            return {"image_url": _to_api_url(rel), "aspect": aspect,
                    "raw_path": str(docs / rel)}

    # Fallback: scan every host folder — match host.json's `name`
    for host_dir in hosts_root.iterdir():
        if not host_dir.is_dir():
            continue
        hj = host_dir / "host.json"
        if not hj.exists():
            continue
        try:
            d = json.loads(hj.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        # v32.0.0-alpha.59: match on id / email / display_name too — the
        # schema-v2 build docs carry host_id, and host folders are named
        # by email-slug.
        keys = {_slugify(host_name)} if host_name else set()
        if host_id:
            keys.add(str(host_id).lower())
        matched = False
        for field in ("name", "display_name", "email", "id"):
            v = d.get(field)
            if not v:
                continue
            if _slugify(str(v)) in keys or str(v).lower() in keys:
                matched = True
                break
        if matched:
            result = _rank_asset(host_dir, hj)
            if result:
                rel, aspect = result
                return {"image_url": _to_api_url(rel), "aspect": aspect,
                        "raw_path": str(docs / rel)}
    return {"image_url": None, "aspect": None, "raw_path": None}


def _location_dir_by_id(loc_root: Path, loc_id: str) -> Optional[Path]:
    """Find Files/Locations/<slug>/ whose location.json id (or slug/name)
    matches. Returns None if nothing matches."""
    want = (loc_id or "").strip().lower()
    if not want:
        return None
    try:
        for entry in loc_root.iterdir():
            lj = entry / "location.json"
            if not (entry.is_dir() and lj.is_file()):
                continue
            try:
                d = json.loads(lj.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if want in {str(d.get("id", "")).lower(), str(d.get("slug", "")).lower(),
                        str(d.get("name", "")).lower()}:
                return entry
    except OSError:
        pass
    return None


def load_location_assets(pres: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return an ordered list of location image assets:
        [{image_url, kind: 'branding'|'overlay', filename}, ...]

    Branding images come first (they're the "welcome" splash slides);
    overlays follow. Reads from
    `Files/Locations/<slug>/branding/` and `overlays/`.
    """
    # alpha.64: wizard-built shows (schema v2) carry location_slug /
    # location_name / location_id and no plain `location`. Try them all.
    loc_raw = (pres.get("location") or pres.get("location_slug")
               or pres.get("location_name") or pres.get("location_id") or "")
    # Location may be `Locations/monkey-pants-bar-grill` (folder-style),
    # `monkey-pants-bar-grill` (slug), or `Monkey Pants Bar Grill` (name).
    docs = _docs_root()
    loc_root = docs / "Files" / "Locations"
    if not loc_root.exists() or not loc_raw:
        return []

    # Normalise to slug
    tail = loc_raw.replace("\\", "/").rstrip("/").split("/")[-1]
    slug = tail if "-" in tail else _slugify(tail)
    loc_dir = loc_root / slug
    if not loc_dir.exists():
        # Try case-insensitive lookup
        for entry in loc_root.iterdir():
            if entry.is_dir() and entry.name.lower() == slug.lower():
                loc_dir = entry
                break
    if not loc_dir.exists():
        # alpha.64: the wizard stores the location ID (a UUID) in
        # pres["location"], not a folder name. Resolve it through each
        # folder's location.json (written by the locations router).
        found = _location_dir_by_id(loc_root, tail)
        if found is not None:
            loc_dir = found
    if not loc_dir.exists():
        return []

    assets: List[Dict[str, Any]] = []
    IMG_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
    # Overlays are NOT location slides: they are composited onto round
    # slides only (see _apply_location_overlays). Branding only here.
    sub = loc_dir / "branding"
    if not sub.exists():
        return assets

    on_disk = {e.stem: e for e in sub.iterdir()
               if e.is_file() and e.suffix.lower() in IMG_EXTS and not e.name.startswith(".")}

    # alpha.64: follow the merchant's drag-and-drop order from Trivia Setup
    # (saved in location.json -> branding_images[].order). Files that are not
    # in the saved list (added by hand in Explorer) are appended afterwards,
    # sorted by name, so nothing in the branding folder is ever skipped.
    ordered: List[Path] = []
    names: Dict[str, str] = {}
    try:
        meta = json.loads((loc_dir / "location.json").read_text(encoding="utf-8"))
        recs = sorted(meta.get("branding_images") or [], key=lambda r: r.get("order", 0))
        for r in recs:
            f = on_disk.pop(r.get("id"), None)
            if f is not None:
                ordered.append(f)
                names[f.name] = r.get("filename") or f.name
    except (OSError, ValueError, AttributeError):
        pass
    ordered.extend(sorted(on_disk.values(), key=lambda e: e.name.lower()))

    for entry in ordered:
        rel = str(entry.relative_to(docs)).replace("\\", "/")
        assets.append({
            "image_url": _to_api_url(rel),
            "kind": "branding",
            "filename": names.get(entry.name, entry.name),
        })
    return assets


def _capture_log(event: str, **data) -> None:
    """Mirror backend diagnostics into the merchant-facing debug log
    (Files/Logs/app.log) so exported logs show title-card resolution."""
    try:
        from routes.debug_log import _get_capture_logger
        import json as _json
        from datetime import datetime as _dt, timezone as _tz
        _get_capture_logger().info(_json.dumps({
            "at": _dt.now(_tz.utc).isoformat(),
            "type": "backend",
            "session": "",
            "data": {"event": event, **data},
        }, default=str, ensure_ascii=False))
    except Exception:
        pass


def _inline_roundmaker_upload(cover_image_id: str) -> Optional[str]:
    """v32.0.0-alpha.54: For legacy bare-JSON .bighat files, the
    round-maker stores the title-card image at
    ``backend/roundmaker_uploads/<cover_image_id>.<ext>``. When the round
    generator preview shows a "POP-CULTURE" image, THAT is the file the
    presentation renderer must inline as slide 0. This helper does the
    disk lookup + base64 inlining.
    """
    if not cover_image_id:
        return None
    # Never let a caller sneak a path traversal through the ID.
    if "/" in cover_image_id or "\\" in cover_image_id or ".." in cover_image_id:
        return None
    from base64 import b64encode

    IMG_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}

    def _encode(entry: Path) -> Optional[str]:
        try:
            raw = entry.read_bytes()
        except OSError:
            return None
        ext = entry.suffix.lower()
        mime = {".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                ".png": "image/png", ".gif": "image/gif",
                ".webp": "image/webp"}.get(ext, "image/jpeg")
        return f"data:{mime};base64,{b64encode(raw).decode('ascii')}"

    # `roundmaker_uploads/` lives next to server.py. Resolve relative to
    # THIS module so it works whether we're running from `/app/backend`,
    # from the Tauri sidecar bundle, or from a pytest tmp_path.
    module_dir = Path(__file__).resolve().parent
    upload_dirs = [
        module_dir / "roundmaker_uploads",
        # Some packaging layouts put backend/ one level deeper.
        module_dir.parent / "backend" / "roundmaker_uploads",
    ]
    # Env override (set by the launcher in frozen builds — the persistent
    # per-user dir) + tests.
    import os as _os
    env_dir = _os.environ.get("BIGHAT_ROUNDMAKER_UPLOADS")
    if env_dir:
        upload_dirs.insert(0, Path(env_dir))
    for up in upload_dirs:
        if not up.is_dir():
            continue
        for entry in up.iterdir():
            if entry.stem != cover_image_id:
                continue
            url = _encode(entry)
            if url:
                _capture_log("cover-resolved", cover_image_id=cover_image_id,
                             source="uploads", path=str(entry))
                return url

    # v32.0.0-alpha.55 RECOVERY FALLBACK: for rounds created before the
    # uploads dir was made persistent, the upload copy is gone — but the
    # ORIGINAL title-card artwork still lives in the local assets folder
    # (that's what the round-maker preview reads, which is why the preview
    # kept working). For REG rounds `cover_image_id` is the artwork's
    # filename stem (e.g. "1970s"), so a stem match inside the TitleCards
    # tree recovers the exact same image.
    # v32.0.0-alpha.57: widened — this program runs on the user's own PC,
    # so we can afford to sweep the docs tree and the whole assets library
    # (capped) for a stem match before giving up.
    assets = _assets_root()
    search_roots = [
        assets / "01_Trivia" / "Web App" / "00_Builder" / "04_TitleCards",
        _docs_root() / "Files" / "Trivia",
        assets,
    ]
    scanned = 0
    seen_roots = []
    for root in search_roots:
        if not root.is_dir():
            seen_roots.append({"root": str(root), "exists": False})
            continue
        seen_roots.append({"root": str(root), "exists": True})
        try:
            for entry in root.rglob("*"):
                scanned += 1
                if scanned > 60000:
                    break
                if not entry.is_file() or entry.suffix.lower() not in IMG_EXTS:
                    continue
                if entry.stem != cover_image_id:
                    continue
                url = _encode(entry)
                if url:
                    logger.info("[bighat] cover %s recovered from %s",
                                cover_image_id, entry)
                    _capture_log("cover-resolved", cover_image_id=cover_image_id,
                                 source="disk-recovery", path=str(entry))
                    return url
        except OSError:
            continue
    _capture_log("cover-MISS", cover_image_id=cover_image_id,
                 uploads_dirs=[{"dir": str(u), "exists": u.is_dir()}
                               for u in dict.fromkeys(upload_dirs)],
                 search_roots=seen_roots, files_scanned=scanned)
    return None


def _assets_root() -> Path:
    """Local assets root (mirrors routes.roundmaker._local_assets_root)."""
    try:
        from native.config import config_manager
        p = config_manager.config.get("paths", {}).get("assets")
        if p:
            return Path(p)
    except Exception:
        pass
    return Path(__file__).resolve().parent / "native" / "data" / "assets"



def load_round_title_card(round_type: str, round_name: str = "") -> Optional[str]:
    """Look for a title-card image for a round. Priority:
        1. `Files/Trivia/<TYPE>/title-cards/<round_name>.<ext>` (per-round)
        2. `Files/Trivia/<TYPE>/title-cards/<TYPE>.<ext>`         (per-type)
        3. `Files/Trivia/title-cards/<TYPE>.<ext>`                 (global)
        4. **Bundled default** at `/<TYPE>_Title_Card.jpg|.svg` served
           by the frontend from its `public/` folder (works in Tauri
           because the built frontend bundle includes them).
    Returns an image URL (`data:` URL for disk assets, `/<name>.jpg`
    for bundled defaults). Returns None if nothing found.
    """
    docs = _docs_root()
    rt = (round_type or "").upper()
    IMG_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".gif")

    search_dirs = [
        docs / "Files" / "Trivia" / rt / "title-cards",
        docs / "Files" / "Trivia" / "title-cards",
    ]
    for tc_dir in search_dirs:
        if not tc_dir.exists():
            continue
        # Per-round: <round_name>.<ext>
        if round_name:
            for ext in IMG_EXTS:
                p = tc_dir / f"{round_name}{ext}"
                if p.exists():
                    return _to_api_url(str(p.relative_to(docs)).replace("\\", "/"))
        # Per-type: <TYPE>.<ext>
        for ext in IMG_EXTS:
            p = tc_dir / f"{rt}{ext}"
            if p.exists():
                return _to_api_url(str(p.relative_to(docs)).replace("\\", "/"))

    # v32.0.0-alpha.49: bundled defaults shipped in
    # `frontend/public/<TYPE>_Title_Card.jpg` (MC, BIG, MYS) and
    # `<TYPE>_Title_Card.svg` (REG, MISC). The frontend loads these from
    # its own origin — no data-URL round-trip needed for bundled
    # artwork. This is what the merchant meant by "the assets are RIGHT
    # THERE" — MC_Title_Card.jpg etc. have always been in public/.
    _BUNDLED_TITLE_CARDS = {
        "MC": "/MC_Title_Card.jpg",
        "REG": "/REG_Title_Card.svg",
        "MISC": "/MISC_Title_Card.svg",
        "NONSENSE": "/MISC_Title_Card.svg",
        "MYS": "/MYS_Title_Card.jpg",
        "BIG": "/BIG_Title_Card.jpg",
    }
    return _BUNDLED_TITLE_CARDS.get(rt)


def _rounds_dir() -> Path:
    return _docs_root() / "Files" / "Trivia" / "Rounds"


def _trivia_type_dir(round_type: str) -> Path:
    return _docs_root() / "Files" / "Trivia" / (round_type or "").upper()


def _special_dir() -> Path:
    return _docs_root() / "Files" / "Trivia" / "Special"


def load_presentation_from_disk(presentation_id: str) -> Optional[Dict[str, Any]]:
    """Scan `Files/Trivia/Rounds/*.bighat` for a manifest with matching id."""
    rd = _rounds_dir()
    if not rd.exists():
        return None
    for entry in rd.iterdir():
        if not entry.is_file() or entry.suffix.lower() != ".bighat":
            continue
        try:
            doc = json.loads(entry.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if doc.get("id") == presentation_id:
            doc["_disk_path"] = str(entry)
            return doc
    return None


def _read_bighat_round(path: Path) -> Optional[Dict[str, Any]]:
    """v32.0.0-alpha.51: `.bighat` files are ZIP archives (magic bytes
    `PK\\x03\\x04`), NOT bare JSON. Each contains:
        manifest.json — format_version, content_id, round_type, source
        payload.json  — name, round_type, questions[], cover_image (asset ref)
        assets/*      — bundled images (cover.jpg = round title card)

    This function unzips, reads `payload.json`, extracts the cover
    image as a data URL, normalises the question field names to what
    `render_round_section` expects, and returns a merged dict.

    Field-name normalisation (payload.json → renderer):
        n              → number
        prompt         → question
        correct_index  → correctOption
        media          → media (passthrough — merchant-embedded per-Q images)
        (answer, options are already the right names)
    """
    import zipfile
    from base64 import b64encode

    try:
        with open(path, "rb") as f:
            header = f.read(4)
    except OSError:
        return None
    if not header.startswith(b"PK"):
        # Legacy bare-JSON .bighat (created before the ZIP format). Fall
        # back to plain read + inline the `cover_image_id` asset when it
        # points to a file in the round-maker's `roundmaker_uploads/`
        # folder (spec: the exact image shown in the round preview MUST
        # be the title-card slide in the presentation).
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        try:
            cid = doc.get("cover_image_id")
            if cid and not doc.get("cover_image_data_url"):
                data_url = _inline_roundmaker_upload(cid)
                if data_url:
                    doc["cover_image_data_url"] = data_url
                    doc["_title_card_source_hint"] = "roundmaker-upload"
                    # v32.0.0-alpha.56 SELF-HEAL: write the embed back into
                    # the .bighat so the round is self-contained forever,
                    # even if the source image later disappears. This runs
                    # on the user's own PC — the file is ours to fix.
                    try:
                        healed = {k: v for k, v in doc.items()
                                  if not k.startswith("_")}
                        path.write_text(json.dumps(healed, indent=2),
                                        encoding="utf-8")
                        logger.info("[bighat] self-healed cover into %s", path)
                    except OSError as we:
                        logger.warning("[bighat] self-heal write failed for %s: %s",
                                       path, we)
        except Exception as e:  # pragma: no cover
            logger.warning("[bighat] cover-inline failed for %s: %s", path, e)
        return doc

    try:
        with zipfile.ZipFile(path, "r") as zf:
            names = set(zf.namelist())
            if "payload.json" not in names:
                return None
            payload = json.loads(zf.read("payload.json").decode("utf-8"))
            manifest = {}
            if "manifest.json" in names:
                try:
                    manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
                except (ValueError, KeyError):
                    manifest = {}

            # Extract cover image as a data URL if present
            cover_data_url = None
            cover_ref = payload.get("cover_image") or ""
            if cover_ref and cover_ref in names:
                raw = zf.read(cover_ref)
                ext = Path(cover_ref).suffix.lower()
                mime = {".gif": "image/gif", ".png": "image/png",
                        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                        ".webp": "image/webp", ".svg": "image/svg+xml"
                        }.get(ext, "application/octet-stream")
                cover_data_url = f"data:{mime};base64,{b64encode(raw).decode('ascii')}"
            # v32.0.0-alpha.55: ZIP payloads that reference a cover by
            # `cover_image_id` (no bundled asset) get the same disk lookup
            # as legacy bare-JSON rounds.
            if not cover_data_url and payload.get("cover_image_id"):
                cover_data_url = _inline_roundmaker_upload(payload["cover_image_id"])

            # Extract per-question media assets (some questions embed images).
            # `media` may be a bare string ("assets/q1.gif") OR a dict
            # ({"image": "assets/q1.gif"} / {"video": "assets/x.mp4"}).
            questions_norm: List[Dict[str, Any]] = []
            for q in (payload.get("questions") or []):
                media_url = None
                raw_media = q.get("media")
                media_ref = ""
                if isinstance(raw_media, str):
                    media_ref = raw_media
                elif isinstance(raw_media, dict):
                    for k in ("image", "video", "gif", "src", "path"):
                        v = raw_media.get(k)
                        if isinstance(v, str) and v:
                            media_ref = v
                            break
                if media_ref and media_ref in names:
                    raw = zf.read(media_ref)
                    ext = Path(media_ref).suffix.lower()
                    mime = {".gif": "image/gif", ".png": "image/png",
                            ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                            ".webp": "image/webp",
                            ".mp4": "video/mp4", ".webm": "video/webm",
                            }.get(ext, "application/octet-stream")
                    media_url = f"data:{mime};base64,{b64encode(raw).decode('ascii')}"

                # Merge legacy + new field names so downstream code works
                # regardless of which format the .bighat used.
                questions_norm.append({
                    "number": q.get("n") or q.get("number") or (len(questions_norm) + 1),
                    "question": q.get("prompt") or q.get("question") or "",
                    "answer": q.get("answer", ""),
                    "options": q.get("options") or [],
                    "correctOption": q.get("correct_index",
                                          q.get("correctOption", 0)),
                    "category": q.get("category", ""),
                    "points": q.get("points"),
                    "media_url": media_url,
                    "media_ref": media_ref,
                })

            return {
                "id": manifest.get("content_id") or payload.get("id"),
                "name": payload.get("name") or manifest.get("round_name") or "",
                "round_type": payload.get("round_type") or manifest.get("round_type") or "",
                "questions": questions_norm,
                "tiebreaker": payload.get("tiebreaker") or {},
                "cover_image_data_url": cover_data_url,
                "_manifest": manifest,
                "_source_format": "bighat-zip",
            }
    except (zipfile.BadZipFile, KeyError, ValueError, OSError) as e:
        logger.warning("[native-slides] .bighat unzip failed for %s: %s", path, e)
        return None


def load_round_from_disk(round_ref: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Resolve a round `.bighat` file. The `file` path is source of truth.

    v32.0.0-alpha.51: Now uses `_read_bighat_round` which correctly
    unzips the archive and extracts cover.jpg as a data URL.
    """
    docs = _docs_root()
    rid = round_ref.get("id") or ""
    rname = round_ref.get("name") or ""
    rtype = (round_ref.get("type") or "").upper()
    # v32.0.0-alpha.56: the Build Wizard fallback (`import-trivia`) stores
    # the round reference under `path` (often an ABSOLUTE native path from
    # /api/trivia/round-files) — honour it, don't just read `file`.
    rfile = round_ref.get("file") or round_ref.get("path") or ""

    # 0. SPECIAL rounds (alpha.63) are only ever read from Files/Trivia/Special.
    if round_ref.get("special"):
        cands = []
        if rfile:
            cands += [docs / "Files" / "Trivia" / rfile, docs / rfile,
                      _special_dir() / Path(rfile).name]
        for c in cands:
            if c.is_file():
                doc = _read_bighat_round(c)
                if doc is not None:
                    return doc
        return None

    # 1. Exact file-path match (TRUST)
    if rfile:
        pf = Path(rfile)
        if pf.is_absolute() and pf.is_file():
            doc = _read_bighat_round(pf)
            if doc is not None:
                return doc
        exact = docs / "Files" / "Trivia" / rfile
        if exact.exists():
            doc = _read_bighat_round(exact)
            if doc is not None:
                return doc
        bare = _trivia_type_dir(rtype) / Path(rfile).name
        if bare != exact and bare.exists():
            doc = _read_bighat_round(bare)
            if doc is not None:
                return doc

    # 2. Scan the type folder
    if rtype:
        type_dir = _trivia_type_dir(rtype)
        if type_dir.exists():
            # By-filename first
            if rname:
                for e in type_dir.iterdir():
                    if not (e.is_file() and e.suffix.lower() == ".bighat"):
                        continue
                    if _norm(e.stem) == _norm(rname):
                        doc = _read_bighat_round(e)
                        if doc is not None:
                            return doc
            # By-id
            for e in type_dir.iterdir():
                if not (e.is_file() and e.suffix.lower() == ".bighat"):
                    continue
                doc = _read_bighat_round(e)
                if doc is None:
                    continue
                if rid and doc.get("id") == rid:
                    return doc
            # By-internal-name
            if rname:
                for e in type_dir.iterdir():
                    if not (e.is_file() and e.suffix.lower() == ".bighat"):
                        continue
                    doc = _read_bighat_round(e)
                    if doc is None:
                        continue
                    if _norm(doc.get("name", "")) == _norm(rname):
                        return doc

    logger.warning("[native-slides] round not found for ref %s", round_ref)
    return None


def _norm(s: str) -> str:
    """Fuzzy match helper: lower + strip + treat hyphens/underscores/spaces
    as equivalent. So `MC-02-A`, `mc_02_a`, `MC 02 A` all normalise to
    `mc02a`."""
    if not s:
        return ""
    out = s.strip().lower()
    for ch in ("-", "_", " ", "."):
        out = out.replace(ch, "")
    return out


# ---------------------------------------------------------------- renderers

def render_host_section(pres: Dict[str, Any]) -> List[Dict[str, Any]]:
    """v32.0.0-alpha.48: Slide 1 is the host's 9:16 image (vertical
    portrait) centered on the 16:9 stage. Text fallback if no image on
    disk.
    """
    host_name = pres.get("host") or pres.get("hostName") or ""
    asset = load_host_asset(pres)
    elements: List[Dict[str, Any]] = []
    if asset.get("image_url"):
        aspect = asset.get("aspect")
        if aspect == "9:16":
            # 9:16 portrait — fit height, centered horizontally.
            # 1080 tall → 607.5 wide at 9:16 ratio; center at 656px x.
            img_w = int(STAGE_H * 9 / 16)  # 607
            img_x = (STAGE_W - img_w) // 2  # 656
            elements.append(_image(asset["image_url"], x=img_x, y=0, w=img_w, h=STAGE_H))
        elif aspect == "16:9":
            # 16:9 fills the whole stage.
            elements.append(_image(asset["image_url"], x=0, y=0, w=STAGE_W, h=STAGE_H))
        else:
            # 1:1 or unknown — square centered in the 16:9 frame.
            img_h = STAGE_H - 200
            img_w = img_h
            img_x = (STAGE_W - img_w) // 2
            img_y = 100
            elements.append(_image(asset["image_url"], x=img_x, y=img_y, w=img_w, h=img_h))
        # alpha.64: NO caption. The presentation name is internal bookkeeping
        # and must never show to the host or the audience.
    else:
        # Text-only fallback (same as alpha.46)
        elements = [
            _text("Tonight's Host", x=160, y=280, w=1600, h=120, size=64, color="#F4C430"),
            _text(host_name or "TBD", x=160, y=440, w=1600, h=200, size=140, weight="800"),
        ]
    return [_slide(0, elements, background=BG_DARK, metadata={
        "roundType": "HOST", "slideIndexInRound": 0, "isRoundTitle": True,
        "host_name": host_name, "host_image": asset.get("image_url"),
    })]


def render_location_section(pres: Dict[str, Any]) -> List[Dict[str, Any]]:
    """LOCATION section (alpha.64):

      1. the RESERVED REWARDS SLOT: always the first slide, directly after
         the host slide. Text-free. The BIG Hat Rewards app tie-in renders
         here later. Never remove it.
      2. then EVERY image in the location's Trivia Setup "Branding images"
         (Files/Locations/<slug>/branding/), in the order the merchant set.
    """
    assets = load_location_assets(pres)

    out: List[Dict[str, Any]] = [_slide(0, [], background=BG_BLUE, metadata={
        "roundType": "LOCATION", "slideIndexInRound": 0, "isRoundTitle": True,
        "isRewardsSlot": True,
    })]
    for idx, asset in enumerate(assets, start=1):
        # Full-bleed image slide: branding images are designed at 16:9.
        elements = [_image(asset["image_url"], x=0, y=0, w=STAGE_W, h=STAGE_H)]
        out.append(_slide(idx, elements, background=BG_DARK, metadata={
            "roundType": "LOCATION", "slideIndexInRound": idx,
            "isRoundTitle": False,
            "asset_kind": asset["kind"], "asset_filename": asset["filename"],
        }))
    return out


def _big_answer_lines(raw: str) -> List[str]:
    raw = (raw or "").strip()
    if not raw:
        return []
    if "\n" in raw:
        return [x.strip() for x in raw.split("\n") if x.strip()]
    if "," in raw:
        return [x.strip() for x in raw.split(",") if x.strip()]
    return [raw]


def render_round_section(
    round_data: Dict[str, Any], round_ref: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """v32.0.0-alpha.50: VERBATIM PORT of the prototype's slide structure.

    See prototype `components/trivia/editor/PresentationMode.jsx` which
    documents the exact 0-indexed layout. The Presenter's answer-reveal,
    auto-advance timer, and "time to grade" flow all key off these
    positions — any drift breaks the host's grading workflow.

        MC/REG/MISC:  0=title, 1-10=questions, 11=review, 12=.gif(STOP), 13=answers
        MYS:          0=title, 1-9=questions,  10=review, 11=.gif(STOP), 12=answers
        BIG:          0=title, 1=question,     2=.gif(STOP), 3=review, 4=answers,
                      5=tiebreaker-question, 6=tiebreaker-answer

    Answer slides MUST have NO title element — `getAnswerCount` counts ALL
    text elements as answers. Adding a header would offset the reveal by 1.
    """
    slides: List[Dict[str, Any]] = []
    rtype = (round_ref.get("type") or round_data.get("round_type") or "").upper()
    rname = round_ref.get("name") or round_data.get("name") or ""
    rorder = round_ref.get("order", 0) or 0
    questions = round_data.get("questions") or []
    is_big = rtype == "BIG"
    is_mys = rtype == "MYS"

    def meta(**extra):
        return {
            "roundType": rtype, "roundNumber": rorder,
            "roundName": rname,
            **extra,
        }

    # ------------------------------------------------------------------
    # SLIDE 0 — Title card. Priority per merchant spec:
    #   1. The .bighat's OWN embedded cover_image (assets/cover.jpg)
    #   2. Per-round asset on disk (Files/Trivia/<TYPE>/title-cards/...)
    #   3. Bundled default in frontend/public/<TYPE>_Title_Card.jpg|svg
    # v32.0.0-alpha.51: `.bighat` files are ZIP archives — the round-
    # generator's title-card artwork is BUNDLED INSIDE. Always prefer it.
    # ------------------------------------------------------------------
    embedded_cover = round_data.get("cover_image_data_url")
    title_card_source = None  # verification/attestation
    if embedded_cover:
        title_card_url = embedded_cover
        title_card_source = "bighat-embedded-cover"
    else:
        # Try category-slug lookup for REG (each REG round is a category
        # like "Animals", "Sports"; matching image lives on disk at
        # Files/Trivia/REG/title-cards/<slug>.jpg).
        category = (
            (questions[0].get("category") if questions else None)
            or round_data.get("category")
            or ""
        )
        title_card_url = None
        if rtype == "REG" and category:
            slug = re.sub(r"[^a-zA-Z0-9]+", "-", category.strip()).strip("-").lower()
            for ext in (".jpg", ".jpeg", ".png", ".webp"):
                p = _docs_root() / "Files" / "Trivia" / "REG" / "title-cards" / f"{slug}{ext}"
                if p.exists():
                    title_card_url = _to_api_url(str(p.relative_to(_docs_root())).replace("\\", "/"))
                    title_card_source = f"disk-category:{slug}{ext}"
                    break
        if not title_card_url:
            title_card_url = load_round_title_card(rtype, rname)
            if title_card_url:
                title_card_source = (
                    "bundled-default" if title_card_url.startswith("/") else "disk-per-round"
                )
    if title_card_url:
        title_elements = [_image(title_card_url, x=0, y=0, w=STAGE_W, h=STAGE_H)]
        title_bg = BG_DARK
    else:
        title_elements = [
            _text(rname or f"Round {rorder}", x=160, y=380, w=1600, h=260,
                  size=170, weight="800"),
            _text(f"Round {rorder}" if rorder else rtype, x=160, y=680, w=1600, h=100,
                  size=60, color="#F4C430"),
        ]
        title_bg = BG_BLUE
        title_card_source = "text-fallback-no-image"
    slides.append(_slide(0, title_elements, background=title_bg, metadata=meta(
        slideIndexInRound=0, isRoundTitle=True, isTitleCard=bool(title_card_url),
        _title_card_source=title_card_source,
        _verified_from_prototype="PresentationMode.jsx#L48-L129 (slide 0 = title card)",
    )))
    _capture_log("title-card", round=rname, type=rtype, order=rorder,
                 source=title_card_source,
                 cover_image_id=round_data.get("cover_image_id"),
                 had_embedded=bool(round_data.get("cover_image_data_url")),
                 disk_path=round_data.get("_disk_path"))

    # ------------------------------------------------------------------
    # SLIDES 1..N — Questions
    # ------------------------------------------------------------------
    if is_big:
        # BIG round: slide 1 is the clue. Prototype PPTX shows ONLY the clue
        # text centered on the dark stage — no "The Clue" header, no
        # question-number chip. Verified against:
        #   _reference/standalone_v30/frontend/src/components/trivia/editor/
        #     PresentationMode.jsx#L67-L129 (BIG slide layout comments)
        # and the merchant's Feb-6 clarification ("WHAT THE FUCK is 'The Clue'?").
        q = questions[0] if questions else {}
        clue_text = q.get("question", "")
        clue_elements = [
            _text(clue_text, x=160, y=240, w=1600, h=640,
                  size=88, weight="700", align="center"),
        ]
        slides.append(_slide(1, clue_elements, background=BG_BLUE, metadata=meta(
            slideIndexInRound=1, questionNumber=1,
            _verified_from_prototype="PresentationMode.jsx#L67-L129 (BIG clue slide)",
        )))
    else:
        # MC/REG/MISC: expect 10 questions; MYS: expect 9. We render exactly
        # what's on disk (fewer → shorter round; more → truncate to spec).
        max_q = 9 if is_mys else 10
        # SPECIAL rounds (alpha.63) may have fewer questions: skip the blank
        # placeholder slides entirely. Every slide keeps its canonical
        # slideIndexInRound (review 11/10, gif 12/11, answers 13/12) so the
        # player's timers + reveal logic work unchanged.
        is_special = bool(round_ref.get("special"))
        for i in range(max_q):
            if is_special and i >= len(questions):
                break
            if i < len(questions):
                q = questions[i]
                qnum = q.get("number") or (i + 1)
                qtext = q.get("question", "")
                options = q.get("options") or []
            else:
                qnum, qtext, options = i + 1, "", []
            elements: List[Dict[str, Any]] = [
                _text(f"Question {qnum}", x=160, y=110, w=1600, h=100,
                      size=54, color="#F4C430", weight="700"),
                _text(qtext, x=160, y=260, w=1600, h=400,
                      size=72, weight="700"),
            ]
            # MC = 4-option grid. REG/MISC/MYS = no options shown (question only).
            if rtype == "MC" and options:
                letters = ["A", "B", "C", "D"]
                for j, opt in enumerate(options[:4]):
                    row = j // 2
                    col = j % 2
                    elements.append(_text(
                        f"{letters[j]}. {opt}",
                        x=200 + col * 800, y=720 + row * 110, w=760, h=100,
                        size=48, weight="600", align="left",
                    ))
            slides.append(_slide(i + 1, elements, background=BG_BLUE, metadata=meta(
                slideIndexInRound=i + 1, questionNumber=qnum,
                _verified_from_prototype=(
                    "PresentationMode.jsx#L67-L129 (MC=Q+options, "
                    "REG/MISC/MYS=Q only)"
                ),
                _has_question_text=bool(qtext),
                _has_options=bool(rtype == "MC" and options),
            )))

    # ------------------------------------------------------------------
    # REVIEW SLIDE (all questions, no answers)
    # ------------------------------------------------------------------
    if is_big:
        review_idx = 3  # BIG spec: review is slide 3 (after gif at 2)
        review_bg = BG_BLUE
        # For BIG we don't do a traditional review; skip and instead
        # place the review AFTER the .gif per prototype spec.
    else:
        review_idx = (9 if is_mys else 10) + 1  # MYS=10, MC/REG/MISC=11

    if not is_big:
        review_elements = [
            _text(f"{rname} — Review", x=160, y=90, w=1600, h=90,
                  size=56, color="#F4C430", weight="700"),
        ]
        n = min(len(questions), 9 if is_mys else 10)
        row_h = max(60, min(90, (STAGE_H - 260) // max(1, n)))
        for i in range(n):
            q = questions[i]
            qn = q.get("number") or (i + 1)
            qt = q.get("question", "")
            review_elements.append(_text(
                f"{qn}. {qt}",
                x=160, y=220 + i * row_h, w=1600, h=row_h,
                size=min(42, row_h - 8), align="left", weight="500",
            ))
        slides.append(_slide(review_idx, review_elements, background=BG_BLUE,
                             metadata=meta(slideIndexInRound=review_idx,
                                           isReview=True,
                                           _verified_from_prototype="PresentationMode.jsx#L67-L129 (review, all Qs listed)")))

    # ------------------------------------------------------------------
    # .gif(STOP) SLIDE — "Time to grade" pause. Auto-advance stops here;
    # host manually clicks to reveal answers. Matches prototype exactly.
    # ------------------------------------------------------------------
    if is_big:
        gif_idx = 2
    elif is_mys:
        gif_idx = 11
    else:
        gif_idx = 12

    # alpha.62: the stop card is the BIG Hat "Time's up / Time to grade" GIF,
    # bundled at backend/assets/slides/times_up.gif (see grade_gif_src()).
    # It is ALWAYS inserted after the review slide, regardless of how many
    # questions the round has.
    gif_url = grade_gif_src()   # alpha.62: BIG Hat times_up.gif, always bundled
    gif_elements = [
        _image(gif_url, x=0, y=0, w=STAGE_W, h=STAGE_H),
    ]
    slides.append(_slide(gif_idx, gif_elements, background=BG_DARK,
                         metadata=meta(slideIndexInRound=gif_idx,
                                       isGifStop=True, isPreAnswerSlide=True,
                                       _verified_from_prototype="PresentationMode.jsx#L67-L129 (STOP gif / Time to Grade)")))

    # For BIG: review slide comes AFTER the gif (index 3)
    if is_big and questions:
        q = questions[0]
        review_elements = [
            _text(f"{rname} — Review", x=160, y=90, w=1600, h=90,
                  size=56, color="#F4C430", weight="700"),
            _text(q.get("question", ""), x=160, y=280, w=1600, h=600,
                  size=64, weight="600"),
        ]
        slides.append(_slide(3, review_elements, background=BG_BLUE,
                             metadata=meta(slideIndexInRound=3, isReview=True,
                                           _verified_from_prototype="PresentationMode.jsx#L67-L129 (BIG review at index 3)")))

    # ------------------------------------------------------------------
    # ANSWERS SLIDE — **NO TITLE ELEMENT**. All text elements are answers.
    # Progressive reveal keys off text-element count.
    # ------------------------------------------------------------------
    if is_big:
        ans_idx = 4
    elif is_mys:
        ans_idx = 12
    else:
        ans_idx = 13

    if is_big and questions:
        # BIG: one answer, or a list of answers if the clue has multiple.
        q = questions[0]
        raw = q.get("answer") or ""
        lines = _big_answer_lines(raw)
        if not lines:
            lines = [raw] if raw else ["(no answer)"]
        # NO TITLE. Each line is a text element = one answer reveal step.
        ans_elements = []
        row_h = max(60, min(100, (STAGE_H - 200) // max(1, len(lines))))
        for i, ln in enumerate(lines):
            ans_elements.append(_text(
                ln,
                x=160, y=100 + i * row_h, w=1600, h=row_h,
                size=min(64, row_h - 10),
                weight="700", color="#F4C430", align="center",
            ))
        slides.append(_slide(ans_idx, ans_elements, background=BG_BLUE,
                             metadata=meta(slideIndexInRound=ans_idx, isAnswers=True,
                                           _verified_from_prototype="PresentationMode.jsx#L67-L129 (BIG answer reveal, NO title element)")))

        # Tiebreaker (BIG-only): slides 5 + 6 = question / answer
        tb = round_data.get("tiebreaker") or {}
        tb_q = tb.get("question", "")
        tb_a = tb.get("answer", "")
        if tb_q or tb_a:
            slides.append(_slide(5, [
                _text("Tiebreaker", x=160, y=140, w=1600, h=100, size=88,
                      color="#F4C430", weight="800"),
                _text(tb_q, x=160, y=340, w=1600, h=500, size=60, weight="600"),
            ], background=BG_GOLD, metadata=meta(
                slideIndexInRound=5, isTiebreaker=True,
                _verified_from_prototype="PresentationMode.jsx#L67-L129 (BIG tiebreaker Q at index 5)",
            )))
            slides.append(_slide(6, [
                # No title — first text element IS the answer reveal
                _text(tb_a, x=160, y=440, w=1600, h=200, size=90,
                      weight="800", color="#F4C430"),
            ], background=BG_GOLD, metadata=meta(
                slideIndexInRound=6, isTiebreaker=True, isAnswers=True,
                _verified_from_prototype="PresentationMode.jsx#L67-L129 (BIG tiebreaker A at index 6)",
            )))
    else:
        # MC/REG/MISC/MYS: N answers, one text element each. NO TITLE.
        n = min(len(questions), 9 if is_mys else 10)
        ans_elements = []
        row_h = max(70, (STAGE_H - 160) // max(1, n))
        for i in range(n):
            q = questions[i]
            qn = q.get("number") or (i + 1)
            ans = q.get("answer", "")
            ans_elements.append(_text(
                f"{qn}. {ans}",
                x=160, y=80 + i * row_h, w=1600, h=row_h,
                size=min(48, row_h - 12),
                align="left", weight="700", color="#F4C430",
            ))
        slides.append(_slide(ans_idx, ans_elements, background=BG_BLUE,
                             metadata=meta(slideIndexInRound=ans_idx, isAnswers=True,
                                           _verified_from_prototype="PresentationMode.jsx#L67-L129 (answers reveal, NO title element)")))

    return slides


def render_sponsors_section(pres: Dict[str, Any]) -> List[Dict[str, Any]]:
    sponsor_files = pres.get("sponsorFiles") or []
    if not sponsor_files:
        # Single generic sponsor placeholder
        return [_slide(0, [
            _text("Thanks to our Sponsors", x=160, y=440, w=1600, h=200,
                  size=90, weight="800", color="#F4C430"),
        ], background=BG_DARK, metadata={
            "roundType": "SPONSOR", "slideIndexInRound": 0, "isRoundTitle": True,
        })]
    out: List[Dict[str, Any]] = []
    for i, ref in enumerate(sponsor_files):
        # If ref looks like an image path, embed it. Otherwise show the name.
        elements: List[Dict[str, Any]] = [
            _text("Sponsor", x=160, y=90, w=1600, h=80, size=44, color="#F4C430"),
        ]
        if isinstance(ref, str) and any(ref.lower().endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".webp", ".gif")):
            elements.append(_image(ref, x=460, y=220, w=1000, h=700))
        else:
            label = ref if isinstance(ref, str) else str(ref)
            elements.append(_text(label, x=160, y=440, w=1600, h=200, size=110, weight="800"))
        out.append(_slide(i, elements, background=BG_DARK, metadata={
            "roundType": "SPONSOR", "slideIndexInRound": i,
        }))
    return out


def render_winners_section() -> List[Dict[str, Any]]:
    return [_slide(0, [
        _text("Tonight's Winners", x=160, y=280, w=1600, h=140, size=90,
              color="#F4C430", weight="800"),
        _text("Thanks for playing!", x=160, y=560, w=1600, h=120, size=64, weight="500"),
    ], background=BG_GOLD, metadata={
        "roundType": "WINNERS", "slideIndexInRound": 0, "isRoundTitle": True,
    })]


def render_final_scores_section() -> List[Dict[str, Any]]:
    return [_slide(0, [
        _text("Final Scores", x=160, y=200, w=1600, h=200, size=140,
              color="#F4C430", weight="800"),
    ], background=BG_BLUE, metadata={
        "roundType": "WINNERS", "slideIndexInRound": 4,
        "isFinalScoresSlide": True, "isRoundTitle": True,
    })]


# ---------------------------------------------------------------- dispatcher

def _native_render_section_raw(
    presentation: Dict[str, Any], section_name: str, body: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Dispatch a section-name to the right renderer, using disk data.

    Returns a list of Editor-compatible slide dicts. On unknown section or
    missing round data, returns [] — the caller is expected to move on to
    the next section rather than 500.
    """
    body = body or {}
    sn = (section_name or "").lower()

    try:
        if sn == "host":
            return render_host_section(presentation)
        if sn == "company":
            return render_company_section(presentation)
        if sn == "rules":
            return render_rules_section(presentation)
        if sn == "format":
            return render_format_section(presentation)
        if sn == "location":
            return render_location_section(presentation)
        if sn == "sponsors":
            return render_sponsors_section(presentation)
        if sn == "winners":
            return render_winners_section()
        if sn in ("final_scores", "final-scores"):
            return render_final_scores_section()
        if sn.startswith("round_"):
            try:
                round_num = int(sn.split("_", 1)[1])
            except (ValueError, IndexError):
                return []
            round_files = presentation.get("roundFiles") or []
            round_ref: Optional[Dict[str, Any]] = None
            for rf in round_files:
                if rf.get("order") == round_num:
                    round_ref = rf
                    break
            # If no exact-order match, fall back to positional index.
            if not round_ref and 1 <= round_num <= len(round_files):
                round_ref = round_files[round_num - 1]
            if not round_ref:
                round_ref = {"order": round_num, "type": body.get("roundType", "")}
            round_data = load_round_from_disk(round_ref)
            if not round_data:
                # Placeholder cover so the show doesn't crash.
                logger.warning("[native-slides] no disk data for round ref %s", round_ref)
                return [_slide(0, [
                    _text(round_ref.get("name") or f"Round {round_num}",
                          x=160, y=380, w=1600, h=260, size=140, weight="800"),
                    _text("(round file not found on disk)",
                          x=160, y=680, w=1600, h=100, size=44, color="#F4C430"),
                ], background=BG_BLUE, metadata={
                    "roundType": (round_ref.get("type") or "").upper(),
                    "roundNumber": round_num,
                    "slideIndexInRound": 0, "isRoundTitle": True,
                })]
            slides = render_round_section(round_data, round_ref)
            # v32.0.0-alpha.53 — apply location overlays to Q + A slides
            # (spec step 17, filter option 3b: question + answer slides only).
            # Overlays are pre-fetched by the slide-fetcher endpoint and
            # passed in via `body["_location_overlays"]` so this renderer
            # stays synchronous (no async DB access here).
            overlays = body.get("_location_overlays") if body else None
            if overlays:
                slides = _apply_location_overlays(
                    slides, overlays, presentation.get("location_id"), round_ref,
                )
            return slides
    except Exception as e:
        logger.exception("[native-slides] renderer failed for section %s: %s", sn, e)
        return []
    return []


# ---------------------------------------------------------------------------
# GLOBAL SLIDES (alpha.64): company intro, rules, Format. Between the location
# slides and round 1. See global_slides.py for storage.
# ---------------------------------------------------------------------------

_FORMAT_LABELS = {
    "MC": ("Multiple Choice", 1, "green"),
    "REG": ("General Topic", 1, "red"),
    "MISC": ("Specific Topic", 1, "blue"),
    "MYS": ("Mystery Topic", 2, "purple"),
    "BIG": ("The BIG Question", 3, "gold"),
}
# Pill artwork is 590x58 on the 1920x1080 stage, centred, 85px pitch (merchant's template).
_PILL_W, _PILL_H, _PILL_PITCH = 590, 58, 85
_PILL_X = (STAGE_W - _PILL_W) // 2
_FORMAT_SERIF = "'Noto Serif Condensed', 'Droid Serif', 'Liberation Serif', Georgia, serif"


def clean_theme(round_name: str) -> str:
    """'Animals_1' -> 'Animals'; 'Dino_Night_3' -> 'Dino Night'.
    Pure codes like 'MC_01_A (1)' return '' so the caller uses the generic label."""
    n = (round_name or "").strip()
    n = re.sub(r"\s*\(\d+\)\s*$", "", n)                 # trailing "(1)"
    n = n.replace("_", " ").replace("-", " ")
    n = re.sub(r"\s+", " ", n).strip()
    n = re.sub(r"(?:\s+(?:\d{1,3}|[A-Za-z]))+$", "", n).strip()  # trailing number / single letter
    if not n or re.fullmatch(r"(?i)(mc|reg|misc|mys|big)(\s*\d*)?", n):
        return ""
    if re.fullmatch(r"(?i)(mc|reg|misc|mys|big)\b.*", n) and len(n.split()) <= 2 and any(c.isdigit() for c in (round_name or "")):
        return ""
    return n[:34]


def format_pill_label(rtype: str, round_name: str, show_themes: bool) -> str:
    base, pts, _ = _FORMAT_LABELS.get((rtype or "").upper(), (rtype or "Round", 1, "grey"))
    r = (rtype or "").upper()
    word = "Point" if pts == 1 else "Points"
    theme = clean_theme(round_name) if (show_themes and r in ("REG", "MISC")) else ""
    # Mystery stays a secret (merchant rule); MC and BIG keep their standard names.
    name = f"{base}: {theme}" if theme else base
    return f"{name} - {pts} {word} each"


def _global_image_src(file: str) -> Optional[str]:
    import global_slides as gs
    p = gs.image_path(file)
    if p is None:
        return None
    try:
        import base64, mimetypes
        mime = mimetypes.guess_type(p.name)[0] or "image/png"
        return f"data:{mime};base64," + base64.b64encode(p.read_bytes()).decode("ascii")
    except OSError:
        return None


def _format_background_src() -> Optional[str]:
    import global_slides as gs
    st = gs.load()["format"]
    if st.get("background"):
        src = _global_image_src(st["background"])
        if src:
            return src
    p = bundled_asset_path("assets", "slides", "format", "format-bg-placeholder.png")
    if p is None:
        return None
    key = "fmt_bg"
    if key not in _GRADE_GIF_CACHE:
        import base64
        _GRADE_GIF_CACHE[key] = "data:image/png;base64," + base64.b64encode(p.read_bytes()).decode("ascii")
    return _GRADE_GIF_CACHE[key]


def _pill_src(color: str) -> Optional[str]:
    key = f"pill_{color}"
    if key in _GRADE_GIF_CACHE:
        return _GRADE_GIF_CACHE[key]
    p = bundled_asset_path("assets", "slides", "format", f"pill-{color}.png")
    if p is None:
        return None
    import base64
    _GRADE_GIF_CACHE[key] = "data:image/png;base64," + base64.b64encode(p.read_bytes()).decode("ascii")
    return _GRADE_GIF_CACHE[key]


def render_company_section(pres: Dict[str, Any]) -> List[Dict[str, Any]]:
    return _render_image_group(pres, "company", "COMPANY")


def render_rules_section(pres: Dict[str, Any]) -> List[Dict[str, Any]]:
    return _render_image_group(pres, "rules", "RULES")


def _render_image_group(pres: Dict[str, Any], kind: str, rtype: str) -> List[Dict[str, Any]]:
    """One full-bleed slide per uploaded image (merchant uploads these)."""
    import global_slides as gs
    st = gs.load()[kind]
    if not st.get("enabled", True):
        return []
    out: List[Dict[str, Any]] = []
    for idx, f in enumerate(st.get("images", [])):
        src = _global_image_src(f)
        if not src:
            continue
        out.append(_slide(idx, [_image(src, x=0, y=0, w=STAGE_W, h=STAGE_H)],
                          background=BG_DARK, metadata={
            "roundType": rtype, "slideIndexInRound": idx, "isRoundTitle": False,
            "isGlobalSlide": True, "globalKind": kind,
        }))
    return out


def render_format_section(pres: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The 'Format' slide: one pill per ROUND ACTUALLY IN THIS SHOW, in play
    order, coloured by round type, with live text and the points each is worth.
    REG / MISC pills carry the round's theme; Mystery never does."""
    import global_slides as gs
    st = gs.load()["format"]
    if not st.get("enabled", True):
        return []
    refs = [r for r in (pres.get("roundFiles") or []) if r.get("type")]
    if not refs:
        return []
    # Resolve each round's display name (theme) from the round file itself.
    rows = []
    for r in refs:
        rtype = (r.get("type") or "").upper()
        name = r.get("name") or ""
        if not name:
            try:
                doc = load_round_from_disk(r) or {}
                name = doc.get("name") or ""
            except Exception:  # noqa: BLE001
                name = ""
        rows.append((rtype, name))

    n = len(rows)
    total_h = (n - 1) * _PILL_PITCH + _PILL_H
    top = max(330, (STAGE_H + 200 - total_h) // 2)   # centred in the area under the title
    elements: List[Dict[str, Any]] = []
    bg = _format_background_src()
    if bg:
        elements.append(_image(bg, x=0, y=0, w=STAGE_W, h=STAGE_H))
    for i, (rtype, name) in enumerate(rows):
        color = _FORMAT_LABELS.get(rtype, ("", 1, "grey"))[2]
        y = top + i * _PILL_PITCH
        pill = _pill_src(color)
        if pill:
            elements.append(_image(pill, x=_PILL_X, y=y, w=_PILL_W, h=_PILL_H))
        label = format_pill_label(rtype, name, st.get("show_themes", True))
        # Condensed serif averages ~0.40 em per character; fit the label inside the pill.
        avail = _PILL_W - 60
        size = max(22, min(40, int(avail / (0.40 * max(len(label), 1)))))
        elements.append(_text(label, x=_PILL_X + 30, y=y, w=_PILL_W - 60, h=_PILL_H,
                              size=size, weight="500",
                              color="#ffffff", family=_FORMAT_SERIF))
    return [_slide(0, elements, background=BG_BLUE, metadata={
        "roundType": "FORMAT", "slideIndexInRound": 0, "isRoundTitle": False,
        "isGlobalSlide": True, "globalKind": "format",
    })]


# ---------------------------------------------------------------------------
# v32.0.0-alpha.53 — Location overlay compositing (spec step 17).
# ---------------------------------------------------------------------------

def _apply_location_overlays(
    slides: List[Dict[str, Any]],
    overlays: List[Dict[str, Any]],
    location_id: Optional[str],
    round_ref: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Composite the location's round-type-tagged overlays on top of
    QUESTION + ANSWER slides only (option 3b, merchant spec).

    `overlays` is the pre-fetched `locations.overlay_images` list (from
    the slide-fetcher endpoint). Each overlay may carry
    `applies_to_round_types: ["MC","REG",...]`; untagged overlays apply
    to ALL round types (backwards compat).
    """
    if not overlays or not location_id:
        return slides
    try:
        from presentation_builder import overlays_for_round_type
    except ImportError:
        return slides
    rtype = (round_ref.get("type") or "").upper()
    q_matched = overlays_for_round_type(overlays, rtype, "question")
    a_matched = overlays_for_round_type(overlays, rtype, "answer")
    if not q_matched and not a_matched:
        return slides

    def _overlay_url(loc_id: str, img: Dict[str, Any]) -> str:
        return f"/api/native/locations/{loc_id}/overlays/{img['id']}/raw"

    out: List[Dict[str, Any]] = []
    for s in slides:
        md = s.get("metadata") or {}
        is_q = (md.get("questionNumber") is not None
                and not md.get("isAnswers") and not md.get("isReview"))
        is_a = bool(md.get("isAnswers"))
        matched = a_matched if is_a else q_matched
        if not (is_q or is_a) or not matched:
            out.append(s)
            continue
        s = dict(s)
        elements = list(s.get("elements") or [])
        for ov in matched:
            elements.append(_image(
                _overlay_url(location_id, ov),
                x=0, y=0, w=STAGE_W, h=STAGE_H,
            ))
        s["elements"] = elements
        md = dict(md)
        md["_location_overlays_applied"] = [ov["id"] for ov in matched]
        s["metadata"] = md
        out.append(s)
    return out



def native_render_section(
    presentation: Dict[str, Any], section_name: str, body: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Render a section, then apply global / per-location slide style."""
    slides = _native_render_section_raw(presentation, section_name, body)
    try:
        import slide_style
        slides = slide_style.apply_to_slides(
            slides, slide_style.slug_from_presentation(presentation), BG_BLUE,
        )
    except Exception as e:  # never break a show over styling
        logger.warning("[slide-style] skipped: %s", e)
    return slides
