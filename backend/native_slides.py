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

    host_name = pres.get("host") or pres.get("hostName") or ""
    host_email = pres.get("hostEmail") or ""
    candidates = []
    if host_email:
        candidates.append(_slugify(host_email))
    if host_name:
        candidates.append(_slugify(host_name))

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
        folder, or None."""
        json_data = {}
        if host_json_path and host_json_path.exists():
            try:
                json_data = json.loads(host_json_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                json_data = {}

        # Priority 1: JSON says 9x16 AND file exists
        rel = _rel_if_exists(json_data.get("host_image_9x16", ""), docs)
        if rel:
            return rel, "9:16"
        # Priority 2: host-9x16.* file on disk
        p = _find_by_stem(host_dir, ["host-9x16", "host_9x16", "9x16"])
        if p:
            return str(p.relative_to(docs)).replace("\\", "/"), "9:16"
        # Priority 3: JSON says 16x9 AND file exists
        rel = _rel_if_exists(json_data.get("host_image_16x9", ""), docs)
        if rel:
            return rel, "16:9"
        # Priority 4: host-16x9.* file on disk
        p = _find_by_stem(host_dir, ["host-16x9", "host_16x9", "16x9"])
        if p:
            return str(p.relative_to(docs)).replace("\\", "/"), "16:9"
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
        if (host_name and d.get("name")
                and _slugify(d["name"]) == _slugify(host_name)):
            result = _rank_asset(host_dir, hj)
            if result:
                rel, aspect = result
                return {"image_url": _to_api_url(rel), "aspect": aspect,
                        "raw_path": str(docs / rel)}
    return {"image_url": None, "aspect": None, "raw_path": None}


def load_location_assets(pres: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return an ordered list of location image assets:
        [{image_url, kind: 'branding'|'overlay', filename}, ...]

    Branding images come first (they're the "welcome" splash slides);
    overlays follow. Reads from
    `Files/Locations/<slug>/branding/` and `overlays/`.
    """
    loc_raw = pres.get("location") or ""
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
        return []

    assets: List[Dict[str, Any]] = []
    IMG_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
    for kind in ("branding", "overlays"):
        sub = loc_dir / kind
        if not sub.exists():
            continue
        for entry in sorted(sub.iterdir()):
            if entry.is_file() and entry.suffix.lower() in IMG_EXTS:
                rel = str(entry.relative_to(docs)).replace("\\", "/")
                assets.append({
                    "image_url": _to_api_url(rel),
                    "kind": "branding" if kind == "branding" else "overlay",
                    "filename": entry.name,
                })
    return assets


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


def load_round_from_disk(round_ref: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Resolve a round `.bighat` file referenced from a presentation manifest.

    `round_ref` is a dict from `presentation.roundFiles`, typically:
        {file: "MC/MC-02-A.bighat", type: "MC", order: 1, name: "MC_02_A", id: "..."}

    v32.0.0-alpha.48: **The `file` path is the source of truth.** If it
    exists on disk we return its content OUTRIGHT — even if the file's
    internal `name` / `id` fields drift (which happens all the time when
    the merchant copies MC-01-A to bootstrap MC-02-A and forgets to update
    the internal name). Previously we'd skip that file and fall back to
    the first same-type round we found, so MC-02-A ended up rendering
    MC-01-A's questions. Bug reproduced by the merchant on alpha.47.
    """
    docs = _docs_root()
    rid = round_ref.get("id") or ""
    rname = round_ref.get("name") or ""
    rtype = (round_ref.get("type") or "").upper()
    rfile = round_ref.get("file") or ""

    # ---- 1. Exact file-path match (TRUST) ---------------------------------
    if rfile:
        exact = docs / "Files" / "Trivia" / rfile
        if exact.exists():
            try:
                return json.loads(exact.read_text(encoding="utf-8"))
            except (OSError, ValueError) as e:
                logger.warning("[native-slides] exact file %s unreadable: %s", exact, e)
        # Also try the bare filename in the type folder in case the
        # manifest stored a relative path we don't expect.
        bare = _trivia_type_dir(rtype) / Path(rfile).name
        if bare != exact and bare.exists():
            try:
                return json.loads(bare.read_text(encoding="utf-8"))
            except (OSError, ValueError) as e:
                logger.warning("[native-slides] bare file %s unreadable: %s", bare, e)

    # ---- 2. Scan the type folder, match by id or fuzzy name --------------
    if rtype:
        type_dir = _trivia_type_dir(rtype)
        if type_dir.exists():
            # Try by-filename first — if a round is named "MC-02-A" in the
            # manifest and the file is `MC-02-A.bighat` on disk, we want
            # that even if the internal name field says something else.
            if rname:
                for e in type_dir.iterdir():
                    if not (e.is_file() and e.suffix.lower() == ".bighat"):
                        continue
                    stem = e.stem
                    if _norm(stem) == _norm(rname):
                        try:
                            return json.loads(e.read_text(encoding="utf-8"))
                        except (OSError, ValueError):
                            continue

            # Then try by id (internal id in the round doc)
            for e in type_dir.iterdir():
                if not (e.is_file() and e.suffix.lower() == ".bighat"):
                    continue
                try:
                    doc = json.loads(e.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                if rid and doc.get("id") == rid:
                    return doc

            # Finally try by internal `name` field (weakest signal)
            if rname:
                for e in type_dir.iterdir():
                    if not (e.is_file() and e.suffix.lower() == ".bighat"):
                        continue
                    try:
                        doc = json.loads(e.read_text(encoding="utf-8"))
                    except (OSError, ValueError):
                        continue
                    if _norm(doc.get("name", "")) == _norm(rname):
                        return doc

    # v32.0.0-alpha.48: **NO MORE LAST-RESORT RANDOM RETURN.** If we
    # can't identify the exact round the merchant chose, we return None
    # and let the renderer emit a "file not found" placeholder. Returning
    # the wrong round's questions is worse than showing an obvious error.
    logger.warning(
        "[native-slides] round not found for ref %s (file=%s, name=%s, id=%s, type=%s)",
        round_ref, rfile, rname, rid, rtype,
    )
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
    pres_name = pres.get("name") or ""
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
        # Add a small caption bar at bottom so the audience knows this is the host
        elements.append(_text(pres_name, x=160, y=STAGE_H - 100, w=STAGE_W - 320, h=80,
                              size=40, color="#cfd8ff", weight="500"))
    else:
        # Text-only fallback (same as alpha.46)
        elements = [
            _text("Tonight's Host", x=160, y=280, w=1600, h=120, size=64, color="#F4C430"),
            _text(host_name or "TBD", x=160, y=440, w=1600, h=200, size=140, weight="800"),
            _text(pres_name, x=160, y=760, w=1600, h=90, size=44, color="#cfd8ff"),
        ]
    return [_slide(0, elements, background=BG_DARK, metadata={
        "roundType": "HOST", "slideIndexInRound": 0, "isRoundTitle": True,
        "host_name": host_name, "host_image": asset.get("image_url"),
    })]


def render_location_section(pres: Dict[str, Any]) -> List[Dict[str, Any]]:
    """v32.0.0-alpha.48: emit one slide per branding + overlay image the
    location has on disk. Fall back to a single text welcome slide if
    no images are available.
    """
    loc = pres.get("location") or ""
    loc_name = loc.rstrip("/").split("/")[-1].replace("-", " ").title() if loc else ""
    assets = load_location_assets(pres)

    if not assets:
        # Text-only fallback (alpha.46 behavior)
        return [_slide(0, [
            _text("Welcome to", x=160, y=300, w=1600, h=120, size=72, color="#F4C430"),
            _text(loc_name or "Trivia Night", x=160, y=460, w=1600, h=260, size=170, weight="800"),
        ], background=BG_BLUE, metadata={
            "roundType": "LOCATION", "slideIndexInRound": 0, "isRoundTitle": True,
        })]

    out: List[Dict[str, Any]] = []
    for idx, asset in enumerate(assets):
        # Full-bleed image slide — the location's branding/overlays are
        # already designed at 16:9 by the merchant.
        elements = [_image(asset["image_url"], x=0, y=0, w=STAGE_W, h=STAGE_H)]
        out.append(_slide(idx, elements, background=BG_DARK, metadata={
            "roundType": "LOCATION", "slideIndexInRound": idx,
            "isRoundTitle": idx == 0,
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
    # SLIDE 0 — Title card (image if available, else styled cover)
    # ------------------------------------------------------------------
    title_card_url = load_round_title_card(rtype, rname)
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
    slides.append(_slide(0, title_elements, background=title_bg, metadata=meta(
        slideIndexInRound=0, isRoundTitle=True, isTitleCard=bool(title_card_url),
    )))

    # ------------------------------------------------------------------
    # SLIDES 1..N — Questions
    # ------------------------------------------------------------------
    if is_big:
        # BIG has exactly ONE clue question (per prototype spec)
        q = questions[0] if questions else {}
        clue_text = q.get("question", "")
        clue_elements = [
            _text("The Clue", x=160, y=90, w=1600, h=100, size=64,
                  color="#F4C430", weight="800"),
            _text(clue_text, x=160, y=280, w=1600, h=600,
                  size=72, weight="700"),
        ]
        slides.append(_slide(1, clue_elements, background=BG_BLUE, metadata=meta(
            slideIndexInRound=1, questionNumber=1,
        )))
    else:
        # MC/REG/MISC: expect 10 questions; MYS: expect 9. We render exactly
        # what's on disk (fewer → shorter round; more → truncate to spec).
        max_q = 9 if is_mys else 10
        for i in range(max_q):
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
                                           isReview=True)))

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

    # Try to use a bundled overlay GIF; fall back to styled text.
    # v32.0.0-alpha.50: bundled SVG stop-card (animated) in
    # `frontend/public/Time_To_Grade.svg`. Renders identically on every
    # install regardless of merchant asset uploads.
    gif_url = "/Time_To_Grade.svg"
    gif_elements = [
        _image(gif_url, x=0, y=0, w=STAGE_W, h=STAGE_H),
    ]
    slides.append(_slide(gif_idx, gif_elements, background=BG_DARK,
                         metadata=meta(slideIndexInRound=gif_idx,
                                       isGifStop=True, isPreAnswerSlide=True)))

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
                             metadata=meta(slideIndexInRound=3, isReview=True)))

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
                             metadata=meta(slideIndexInRound=ans_idx, isAnswers=True)))

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
            )))
            slides.append(_slide(6, [
                # No title — first text element IS the answer reveal
                _text(tb_a, x=160, y=440, w=1600, h=200, size=90,
                      weight="800", color="#F4C430"),
            ], background=BG_GOLD, metadata=meta(
                slideIndexInRound=6, isTiebreaker=True, isAnswers=True,
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
                             metadata=meta(slideIndexInRound=ans_idx, isAnswers=True)))

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

def native_render_section(
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
            return render_round_section(round_data, round_ref)
    except Exception as e:
        logger.exception("[native-slides] renderer failed for section %s: %s", sn, e)
        return []
    return []
