"""v32.0.0-alpha.52 — remove hallucinated "The Clue" header, per-category
REG title-card lookup, prototype verification flags, `/api/native/attest`
endpoint.

Merchant demand (2026-02-06):
  1. STOP inventing text that isn't in the prototype ("The Clue" header
     on BIG round slide 1).
  2. Add flags to every slide's metadata that cite the exact prototype
     file+lines the layout was ported from.
  3. Wire an attestation endpoint the merchant can hit to audit what's
     rendered from what source.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import native_slides as ns  # noqa: E402


# ---------------------------------------------------------------------------
# 1. "The Clue" header is REMOVED from BIG round slide 1.
#    Slide 1 must have ONLY the clue text — no yellow "The Clue" chip.
# ---------------------------------------------------------------------------

def test_big_round_slide1_has_no_the_clue_header():
    doc = {
        "round_type": "BIG",
        "name": "The BIG Question",
        "questions": [
            {"number": 1, "question": "Name the 10 baseball spring-training venues.", "answer": ""},
        ],
    }
    slides = ns.render_round_section(doc, {"type": "BIG", "name": doc["name"], "order": 6})
    assert len(slides) >= 2
    q_slide = slides[1]
    texts = [
        (e.get("content") or "").strip()
        for e in q_slide["elements"] if e["type"] == "text"
    ]
    assert "The Clue" not in texts, (
        f"'The Clue' header must NOT appear on BIG round slide 1. Got texts: {texts}"
    )
    # And the clue text itself IS on the slide.
    assert any("baseball spring-training" in t for t in texts), (
        f"Actual clue text missing from BIG slide 1: {texts}"
    )
    # Exactly ONE text element (the clue) — no header, no chip.
    assert len(texts) == 1, f"Expected 1 text element on BIG clue slide, got {len(texts)}: {texts}"


# ---------------------------------------------------------------------------
# 2. Every slide is stamped with `_verified_from_prototype` OR is the
#    title slide (title slide has `_title_card_source` instead).
# ---------------------------------------------------------------------------

def test_every_slide_has_prototype_provenance():
    doc = {
        "round_type": "MC",
        "name": "Multiple Choice",
        "questions": [
            {"number": i, "question": f"Q{i}?", "answer": "A",
             "options": ["A", "B", "C", "D"], "correctOption": 0}
            for i in range(1, 11)
        ],
    }
    slides = ns.render_round_section(doc, {"type": "MC", "name": doc["name"], "order": 1})
    for s in slides:
        md = s.get("metadata") or {}
        assert md.get("_verified_from_prototype") or md.get("_title_card_source"), (
            f"slide {md.get('slideIndexInRound')} missing prototype provenance flag; "
            f"metadata={md}"
        )


def test_title_card_source_flag_records_fallback():
    """When no embedded cover AND no disk asset, the fallback source is
    stamped `bundled-default` (a placeholder JPG/SVG in frontend/public)."""
    doc = {"round_type": "MC", "name": "MC Test", "questions": []}
    slides = ns.render_round_section(doc, {"type": "MC", "name": "MC Test", "order": 1})
    title_md = slides[0]["metadata"]
    assert title_md.get("isRoundTitle") is True
    assert title_md.get("_title_card_source") in (
        "bundled-default", "disk-per-round", "text-fallback-no-image",
        "bighat-embedded-cover",
    ), title_md.get("_title_card_source")


# ---------------------------------------------------------------------------
# 3. Per-category REG title-card lookup — when the REG round's first
#    question has a `category` field AND a matching image exists on
#    disk at Files/Trivia/REG/title-cards/<slug>.jpg, that image wins
#    over the bundled placeholder.
# ---------------------------------------------------------------------------

def test_reg_round_uses_per_category_title_card_from_disk(tmp_path, monkeypatch):
    """Merchant expects animals-1.bighat → REG round → Animals category
    → title-cards/animals.jpg to render as the title slide."""
    docs = tmp_path
    tc_dir = docs / "Files" / "Trivia" / "REG" / "title-cards"
    tc_dir.mkdir(parents=True)
    img = tc_dir / "animals.jpg"
    img.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 32)

    monkeypatch.setattr(ns, "_docs_root", lambda: docs)

    doc = {
        "round_type": "REG",
        "name": "Animals",
        "questions": [
            {"number": i, "question": f"Animal Q{i}?", "answer": "A",
             "category": "Animals"}
            for i in range(1, 11)
        ],
    }
    slides = ns.render_round_section(doc, {"type": "REG", "name": "Animals", "order": 2})
    title = slides[0]
    md = title["metadata"]
    assert md["_title_card_source"].startswith("disk-category:animals"), md["_title_card_source"]
    imgs = [e for e in title["elements"] if e["type"] == "image"]
    assert imgs, "expected an <image> element on REG title slide"


# ---------------------------------------------------------------------------
# 4. Attestation endpoint returns provenance report.
# ---------------------------------------------------------------------------

def test_attestation_endpoint_report_shape(tmp_path, monkeypatch):
    """Minimal contract: /api/native/attest/<id> returns a report with
    per-round provenance and health flags."""
    from fastapi.testclient import TestClient

    # Build a minimal on-disk presentation
    docs = tmp_path
    monkeypatch.setenv("BIGHAT_FILES_DIR", str(docs))
    rounds_dir = docs / "Files" / "Trivia" / "Rounds"
    rounds_dir.mkdir(parents=True)
    pres_file = rounds_dir / "pres-1.bighat"
    round_file = docs / "Files" / "Trivia" / "REG" / "test-round.bighat"
    round_file.parent.mkdir(parents=True)
    round_file.write_text(json.dumps({
        "id": "r1", "round_type": "REG", "name": "TestReg",
        "questions": [{"number": 1, "question": "Q?", "answer": "A"}],
    }))
    pres_file.write_text(json.dumps({
        "id": "pres-1", "name": "Test Show", "type": "trivia-presentation",
        "roundFiles": [{"order": 1, "type": "REG",
                        "file": "Files/Trivia/REG/test-round.bighat"}],
    }))

    monkeypatch.setattr(ns, "_docs_root", lambda: docs)

    from native.router import router
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    resp = client.get("/api/native/attest/pres-1")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["presentation_id"] == "pres-1"
    assert body["num_rounds"] == 1
    assert len(body["rounds"]) == 1
    r = body["rounds"][0]
    assert r["round_type"] == "REG"
    assert r["num_questions"] == 1
    assert r["num_slides_rendered"] > 0
    assert "health" in body
    assert body["health"]["total_slides"] == r["num_slides_rendered"]
