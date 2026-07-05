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


def _to_api_url(rel_path: str) -> str:
    """Convert a `Files/...` relative path into the API URL that the
    frontend can `<img>` load. `rel_path` should be forward-slashed."""
    # The backend serves any file under docs root via /api/native/files/raw
    # with `path=` set to the docs-relative path. We URL-encode `/` inside
    # the path as `%2F` so it survives the query-string round-trip.
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
    Reads `Files/Hosts/<slug>/host.json` for `host_image_9x16` (preferred)
    then `host_image_16x9`. Both live as absolute `/api/native/files/raw?path=…`
    URLs. If the JSON is missing but a `host-9x16.*` or `host-16x9.*` file
    exists in the host folder we surface that too.
    """
    from urllib.parse import unquote, urlparse, parse_qs

    host_name = pres.get("host") or pres.get("hostName") or ""
    host_email = pres.get("hostEmail") or ""
    # Presentation manifests sometimes store the email as `host` — accept both.
    candidates = []
    if host_email:
        candidates.append(_slugify(host_email))
    if host_name:
        candidates.append(_slugify(host_name))
    # Try email-shaped variant on the name (e.g. "Nick Sellards" ->
    # "sellards@bighat.live" isn't inferable, so we rely on manifest).

    docs = _docs_root()
    hosts_root = docs / "Files" / "Hosts"

    def _resolve_from_json(host_json_path: Path):
        try:
            data = json.loads(host_json_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        for key, aspect in (("host_image_9x16", "9:16"),
                            ("host_image_16x9", "16:9"),
                            ("profile_picture", "1:1")):
            val = data.get(key)
            if not val:
                continue
            # `val` is typically an API URL like /api/native/files/raw?path=Files/...
            # Extract the relative path so we can verify the file exists.
            rel = None
            if val.startswith("/api/native/files/raw"):
                parsed = urlparse(val)
                q = parse_qs(parsed.query)
                rel = unquote(q.get("path", [""])[0])
            elif val.startswith("Files/"):
                rel = val
            elif val.startswith("http"):
                # External URL — trust it as-is.
                return {"image_url": val, "aspect": aspect, "raw_path": None}
            if rel:
                p = docs / rel
                if p.exists():
                    return {"image_url": _to_api_url(rel), "aspect": aspect,
                            "raw_path": str(p)}
        return None

    # 1. Try the candidate slug folders
    if hosts_root.exists():
        for slug in candidates:
            if not slug:
                continue
            host_dir = hosts_root / slug
            hj = host_dir / "host.json"
            if hj.exists():
                found = _resolve_from_json(hj)
                if found:
                    return found
            # 2. Bare filename fallback in the host folder
            for stem_aspect in (("host-9x16", "9:16"), ("host-16x9", "16:9"),
                                ("avatar", "1:1"), ("profile", "1:1")):
                stem, aspect = stem_aspect
                for ext in (".gif", ".png", ".jpg", ".jpeg", ".webp"):
                    p = host_dir / f"{stem}{ext}"
                    if p.exists():
                        rel = str(p.relative_to(docs)).replace("\\", "/")
                        return {"image_url": _to_api_url(rel), "aspect": aspect,
                                "raw_path": str(p)}
        # 3. Scan every host folder in case the slug logic missed
        for host_dir in hosts_root.iterdir():
            if not host_dir.is_dir():
                continue
            hj = host_dir / "host.json"
            if hj.exists():
                try:
                    d = json.loads(hj.read_text(encoding="utf-8"))
                    if (d.get("name") and host_name
                            and _slugify(d["name"]) == _slugify(host_name)):
                        found = _resolve_from_json(hj)
                        if found:
                            return found
                except (OSError, ValueError):
                    continue
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
    Returns an API URL or None.
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
    return None


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
    """Build the full slide list for one round:
        cover → Q×N → review → answers → (tiebreaker if BIG)
    """
    slides: List[Dict[str, Any]] = []
    rtype = (round_ref.get("type") or round_data.get("round_type") or "").upper()
    rname = round_ref.get("name") or round_data.get("name") or ""
    rorder = round_ref.get("order", 0) or 0
    questions = round_data.get("questions") or []
    is_big = rtype == "BIG"

    slide_idx = 0

    # 0. Title card image (if present on disk) — full-bleed 16:9
    title_card_url = load_round_title_card(rtype, rname)
    if title_card_url:
        tc_elements = [_image(title_card_url, x=0, y=0, w=STAGE_W, h=STAGE_H)]
        slides.append(_slide(len(slides), tc_elements, background=BG_DARK, metadata={
            "roundType": rtype, "roundNumber": rorder,
            "slideIndexInRound": slide_idx, "isRoundTitle": True, "isTitleCard": True,
        }))
        slide_idx += 1

    # 1. Cover (always, whether or not a title-card asset was found)
    cover_elements = [
        _text(rname or f"Round {rorder}", x=160, y=380, w=1600, h=260, size=170, weight="800"),
        _text(f"Round {rorder}" if rorder else rtype, x=160, y=680, w=1600, h=100,
              size=60, color="#F4C430"),
    ]
    slides.append(_slide(len(slides), cover_elements, background=BG_BLUE, metadata={
        "roundType": rtype, "roundNumber": rorder,
        "slideIndexInRound": slide_idx, "isRoundTitle": not title_card_url,
    }))
    slide_idx += 1

    # 1..N. Questions
    for q in questions:
        qnum = q.get("number") or q.get("num") or slide_idx
        qtext = q.get("question", "")
        options = q.get("options") or []
        header = f"Question {qnum}"
        elements: List[Dict[str, Any]] = [
            _text(header, x=160, y=140, w=1600, h=90, size=54, color="#F4C430", weight="700"),
            _text(qtext, x=160, y=280, w=1600, h=380, size=64, weight="700"),
        ]
        if is_big:
            # BIG rounds: show clue only. Answers list appears on the answers slide.
            pass
        elif options:
            # Multiple choice - render as A/B/C/D grid
            letters = ["A", "B", "C", "D", "E", "F"]
            for i, opt in enumerate(options[:6]):
                row = i // 2
                col = i % 2
                elements.append(_text(
                    f"{letters[i]}. {opt}",
                    x=200 + col * 800, y=720 + row * 100, w=760, h=80,
                    size=44, weight="600", align="left",
                ))
        slides.append(_slide(len(slides), elements, background=BG_BLUE, metadata={
            "roundType": rtype, "roundNumber": rorder,
            "slideIndexInRound": slide_idx, "questionNumber": qnum,
        }))
        slide_idx += 1

    # Review slide — all questions restated, no answers
    if questions:
        review_lines: List[Dict[str, Any]] = [
            _text(f"{rname} — Review", x=160, y=90, w=1600, h=90, size=56,
                  color="#F4C430", weight="700"),
        ]
        max_q = len(questions)
        row_h = max(50, min(80, (STAGE_H - 260) // max(1, max_q)))
        for i, q in enumerate(questions):
            qn = q.get("number") or (i + 1)
            qt = q.get("question", "")
            review_lines.append(_text(
                f"{qn}. {qt}",
                x=160, y=220 + i * row_h, w=1600, h=row_h,
                size=min(40, row_h - 8), align="left", weight="500",
            ))
        slides.append(_slide(len(slides), review_lines, background=BG_BLUE, metadata={
            "roundType": rtype, "roundNumber": rorder,
            "slideIndexInRound": slide_idx, "isReview": True,
        }))
        slide_idx += 1

    # Answers slide
    if is_big and questions:
        q = questions[0]
        raw = q.get("answer") or ""
        lines = _big_answer_lines(raw)
        elems: List[Dict[str, Any]] = [
            _text(f"{rname} — Answers", x=160, y=90, w=1600, h=90, size=56,
                  color="#F4C430", weight="700"),
            _text(q.get("question", ""), x=160, y=200, w=1600, h=120, size=40, weight="500"),
        ]
        row_h = max(40, min(70, (STAGE_H - 380) // max(1, len(lines) or 1)))
        for i, ln in enumerate(lines):
            elems.append(_text(
                f"{i + 1}. {ln}",
                x=200, y=360 + i * row_h, w=1520, h=row_h,
                size=min(38, row_h - 6), align="left", weight="600",
            ))
        slides.append(_slide(len(slides), elems, background=BG_BLUE, metadata={
            "roundType": rtype, "roundNumber": rorder,
            "slideIndexInRound": slide_idx, "isAnswers": True,
        }))
        slide_idx += 1

        # BIG tiebreaker (if present)
        tb = round_data.get("tiebreaker") or {}
        if tb.get("question") or tb.get("answer"):
            tb_elems = [
                _text("Tiebreaker", x=160, y=140, w=1600, h=100, size=72,
                      color="#F4C430", weight="800"),
                _text(tb.get("question", ""), x=160, y=340, w=1600, h=280,
                      size=54, weight="600"),
                _text(f"Answer: {tb.get('answer', '')}", x=160, y=720, w=1600, h=120,
                      size=48, color="#F4C430", weight="700"),
            ]
            slides.append(_slide(len(slides), tb_elems, background=BG_GOLD, metadata={
                "roundType": rtype, "roundNumber": rorder,
                "slideIndexInRound": slide_idx, "isTiebreaker": True,
            }))
            slide_idx += 1
    elif questions:
        elems = [
            _text(f"{rname} — Answers", x=160, y=90, w=1600, h=90, size=56,
                  color="#F4C430", weight="700"),
        ]
        row_h = max(60, min(90, (STAGE_H - 280) // max(1, len(questions))))
        for i, q in enumerate(questions):
            qn = q.get("number") or (i + 1)
            qt = q.get("question", "")
            ans = q.get("answer", "")
            elems.append(_text(
                f"{qn}. {qt}",
                x=160, y=220 + i * row_h, w=1000, h=row_h,
                size=min(34, row_h - 10), align="left", weight="500",
            ))
            elems.append(_text(
                ans,
                x=1180, y=220 + i * row_h, w=580, h=row_h,
                size=min(34, row_h - 10), align="left",
                weight="700", color="#F4C430",
            ))
        slides.append(_slide(len(slides), elems, background=BG_BLUE, metadata={
            "roundType": rtype, "roundNumber": rorder,
            "slideIndexInRound": slide_idx, "isAnswers": True,
        }))
        slide_idx += 1

    # Score slide after non-BIG rounds (frontend places score tracker overlay here)
    if not is_big:
        slides.append(_slide(len(slides), [
            _text(f"Round {rorder} Scores", x=160, y=90, w=1600, h=100, size=64,
                  color="#F4C430", weight="800"),
        ], background=BG_BLUE, metadata={
            "roundType": rtype, "roundNumber": rorder,
            "slideIndexInRound": slide_idx, "isScoreSlide": True,
        }))

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
