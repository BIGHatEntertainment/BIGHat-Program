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
        {file: "MC/MC_01_A.bighat", type: "MC", order: 1, name: "MC_01_A", id: "..."}

    Strategy: try the exact `file` path relative to `Files/Trivia/`,
    then scan `Files/Trivia/<TYPE>/` for a filename or id match.
    """
    docs = _docs_root()
    rid = round_ref.get("id") or ""
    rname = round_ref.get("name") or ""
    rtype = (round_ref.get("type") or "").upper()
    rfile = round_ref.get("file") or ""

    candidates: List[Path] = []
    if rfile:
        p1 = docs / "Files" / "Trivia" / rfile
        candidates.append(p1)
        # Bare filename variant
        candidates.append(_trivia_type_dir(rtype) / Path(rfile).name)
    if rtype:
        type_dir = _trivia_type_dir(rtype)
        if type_dir.exists():
            for e in type_dir.iterdir():
                if e.is_file() and e.suffix.lower() == ".bighat":
                    candidates.append(e)

    seen: set = set()
    for path in candidates:
        key = str(path.resolve()) if path.exists() else str(path)
        if key in seen:
            continue
        seen.add(key)
        if not path.exists():
            continue
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        # id match wins outright
        if rid and doc.get("id") == rid:
            return doc
        # Otherwise fall back to name match
        if rname and doc.get("name") == rname:
            return doc
    # Last resort: return first same-type round we found (better than nothing).
    for path in candidates:
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
    return None


# ---------------------------------------------------------------- renderers

def render_host_section(pres: Dict[str, Any]) -> List[Dict[str, Any]]:
    host = pres.get("host") or pres.get("hostName") or ""
    name = pres.get("name") or ""
    elements = [
        _text("Tonight's Host", x=160, y=280, w=1600, h=120, size=64, color="#F4C430"),
        _text(host or "TBD", x=160, y=440, w=1600, h=200, size=140, weight="800"),
        _text(name, x=160, y=760, w=1600, h=90, size=44, color="#cfd8ff"),
    ]
    return [_slide(0, elements, background=BG_DARK, metadata={
        "roundType": "HOST", "slideIndexInRound": 0, "isRoundTitle": True,
    })]


def render_location_section(pres: Dict[str, Any]) -> List[Dict[str, Any]]:
    loc = pres.get("location") or ""
    loc_name = loc.rstrip("/").split("/")[-1] if loc else ""
    elements = [
        _text("Welcome to", x=160, y=300, w=1600, h=120, size=72, color="#F4C430"),
        _text(loc_name or "Trivia Night", x=160, y=460, w=1600, h=260, size=170, weight="800"),
    ]
    return [_slide(0, elements, background=BG_BLUE, metadata={
        "roundType": "LOCATION", "slideIndexInRound": 0, "isRoundTitle": True,
    })]


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

    # 0. Cover
    cover_elements = [
        _text(rname or f"Round {rorder}", x=160, y=380, w=1600, h=260, size=170, weight="800"),
        _text(f"Round {rorder}" if rorder else rtype, x=160, y=680, w=1600, h=100,
              size=60, color="#F4C430"),
    ]
    slides.append(_slide(len(slides), cover_elements, background=BG_BLUE, metadata={
        "roundType": rtype, "roundNumber": rorder,
        "slideIndexInRound": slide_idx, "isRoundTitle": True,
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
