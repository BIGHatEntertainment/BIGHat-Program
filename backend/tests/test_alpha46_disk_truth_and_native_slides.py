"""
Regression tests for v32.0.0-alpha.46 patches.

Locks in the four bug fixes discovered from the merchant's alpha.45
debug log upload after a fresh install + restart cycle:

  1. `GET /api/presentations/{id}` — disk-fallback: after an app restart
     the fresh MontyDB doesn't have the presentation, but the `.bighat`
     manifest on disk does. Endpoint must NOT 404 for content on disk.

  2. `GET /api/slide-fetcher/sections-list/{id}` — disk-fallback so
     restart doesn't break the Editor's section-loading loop.

  3. `POST /api/slide-fetcher/fetch-section/{id}/{section}` — native
     rendering path that builds Editor-compatible slides directly from
     `.bighat` files. Fixes: "Package not found at C:\\...\\Temp\\
     fetch_host_XXX\\file_0.pptx" 500 the merchant saw on alpha.45.

  4. `POST /api/slide-fetcher/store-all/{id}` — accepts raw-list,
     wrapped-object, empty, or missing body without 422ing.

  Bonus: `GET /api/trivia-viewer/list` — never 500s (MontyDB thread /
  coroutine failures fall back to a disk-only scan).

PRD rule enforced (see `/app/memory/PRD.md § DISK STATE IS THE ABSOLUTE
SOURCE OF TRUTH`): disk is the source of truth. Every endpoint touching
presentations must fall back to disk when the DB misses.
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any, Dict

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ------- native_slides helpers ---------------------------------------------

def test_native_slides_module_importable():
    from native_slides import (
        native_render_section, load_presentation_from_disk,
        load_round_from_disk, render_host_section,
    )
    assert callable(native_render_section)
    assert callable(load_presentation_from_disk)
    assert callable(load_round_from_disk)


def _write_test_bundle(tmp_path: Path) -> Dict[str, str]:
    """Write a presentation + round pair under a fake BIGHAT_FILES_DIR
    and return the ids. Callers must set BIGHAT_FILES_DIR=tmp_path before
    the routes see it (this fixture returns the id for direct-import tests
    that respect the env var)."""
    files = tmp_path / "Files"
    (files / "Trivia" / "Rounds").mkdir(parents=True)
    (files / "Trivia" / "MC").mkdir(parents=True)

    round_id = f"round-{uuid.uuid4().hex[:8]}"
    round_doc = {
        "id": round_id,
        "name": "MC_Test_Alpha46",
        "round_type": "MC",
        "questions": [
            {"number": 1, "question": "Q1?",
             "options": ["A", "B", "C", "D"], "correctOption": 0, "answer": "A"},
            {"number": 2, "question": "Q2?",
             "options": ["W", "X", "Y", "Z"], "correctOption": 2, "answer": "Y"},
        ],
    }
    (files / "Trivia" / "MC" / "MC_Test_Alpha46.bighat").write_text(
        json.dumps(round_doc), encoding="utf-8",
    )

    pres_id = f"pres-{uuid.uuid4().hex[:8]}"
    pres_doc = {
        "id": pres_id,
        "name": "Alpha46 Regression Presentation",
        "type": "trivia-imported",
        "createdBy": "tester",
        "createdAt": "2026-02-05T00:00:00Z",
        "host": "Test Host",
        "location": "Locations/Test Bar",
        "numRounds": 1,
        "roundFiles": [
            {"id": round_id, "name": "MC_Test_Alpha46", "type": "MC", "order": 1,
             "file": "MC/MC_Test_Alpha46.bighat"},
        ],
    }
    (files / "Trivia" / "Rounds" / f"pres.bighat").write_text(
        json.dumps(pres_doc), encoding="utf-8",
    )
    return {"pres_id": pres_id, "round_id": round_id}


def test_disk_lookup_finds_presentation_and_round(tmp_path, monkeypatch):
    ids = _write_test_bundle(tmp_path)
    monkeypatch.setenv("BIGHAT_FILES_DIR", str(tmp_path))

    from native_slides import load_presentation_from_disk, load_round_from_disk
    pres = load_presentation_from_disk(ids["pres_id"])
    assert pres is not None
    assert pres["id"] == ids["pres_id"]
    assert pres["host"] == "Test Host"

    round_ref = pres["roundFiles"][0]
    round_data = load_round_from_disk(round_ref)
    assert round_data is not None
    assert round_data["id"] == ids["round_id"]
    assert len(round_data["questions"]) == 2


# ------- native_render_section --------------------------------------------

def test_native_render_host_produces_editor_shape(tmp_path, monkeypatch):
    ids = _write_test_bundle(tmp_path)
    monkeypatch.setenv("BIGHAT_FILES_DIR", str(tmp_path))

    from native_slides import load_presentation_from_disk, native_render_section
    pres = load_presentation_from_disk(ids["pres_id"])
    slides = native_render_section(pres, "host")

    assert len(slides) == 1
    s = slides[0]
    # Editor.jsx expects: id, order, background, elements[], metadata
    assert isinstance(s["id"], str) and s["id"].startswith("slide-")
    assert s["order"] == 0
    assert "background" in s
    assert isinstance(s["elements"], list) and len(s["elements"]) >= 1
    # Every element must have Editor-compatible keys
    for el in s["elements"]:
        assert "type" in el and el["type"] in ("text", "image", "shape", "overlay", "video")
        assert "x" in el and "y" in el and "width" in el and "height" in el
    # Host name must appear in one of the text elements
    texts = [e["content"] for e in s["elements"] if e["type"] == "text"]
    assert any("Test Host" in t for t in texts if t)


def test_native_render_round_produces_full_slide_sequence(tmp_path, monkeypatch):
    ids = _write_test_bundle(tmp_path)
    monkeypatch.setenv("BIGHAT_FILES_DIR", str(tmp_path))

    from native_slides import load_presentation_from_disk, native_render_section
    pres = load_presentation_from_disk(ids["pres_id"])
    slides = native_render_section(pres, "round_1")

    # cover + 2 questions + review + answers + score-slide = 6
    assert len(slides) == 6
    # First slide: cover with round title
    assert slides[0]["metadata"].get("isRoundTitle") is True
    assert slides[0]["metadata"]["roundNumber"] == 1
    assert slides[0]["metadata"]["roundType"] == "MC"
    # Every question slide has the question text
    q_slides = [s for s in slides if s["metadata"].get("questionNumber")]
    assert len(q_slides) == 2
    for qs in q_slides:
        texts = [e["content"] for e in qs["elements"] if e["type"] == "text"]
        assert any("?" in t for t in texts if t)  # contains a question


def test_native_render_unknown_section_returns_empty(tmp_path, monkeypatch):
    ids = _write_test_bundle(tmp_path)
    monkeypatch.setenv("BIGHAT_FILES_DIR", str(tmp_path))
    from native_slides import load_presentation_from_disk, native_render_section
    pres = load_presentation_from_disk(ids["pres_id"])
    assert native_render_section(pres, "made-up-section") == []


def test_native_render_missing_round_returns_placeholder(tmp_path, monkeypatch):
    """If a round ref points to a file that isn't on disk, we return a
    single placeholder cover — never crash the show."""
    monkeypatch.setenv("BIGHAT_FILES_DIR", str(tmp_path))
    (tmp_path / "Files" / "Trivia" / "Rounds").mkdir(parents=True)

    pres = {
        "id": "orphan-pres",
        "roundFiles": [{"id": "missing", "name": "Missing", "type": "MC",
                        "order": 1, "file": "MC/does-not-exist.bighat"}],
    }
    from native_slides import native_render_section
    slides = native_render_section(pres, "round_1")
    assert len(slides) == 1
    assert slides[0]["metadata"]["isRoundTitle"] is True


# ------- source-level guarantees for the four route patches ----------------

def test_slide_fetcher_uses_native_render_before_sharepoint():
    """Verify slide_fetcher.py imports native_render_section AND calls it
    inside fetch_section before touching SharePoint. Regression guard for
    the "just visuals" alpha.44 crash."""
    src = (ROOT / "routes" / "slide_fetcher.py").read_text()
    assert "from native_slides import" in src
    # The native render call must happen INSIDE fetch_section, BEFORE the
    # SharePoint pipeline is initialised.
    fs_start = src.index("async def fetch_section")
    fs_end = src.index("@router.get", fs_start)
    body = src[fs_start:fs_end]
    idx_native = body.find("_native_render_section")
    idx_sp = body.find("SharePointService(")
    assert idx_native >= 0, "fetch_section must call _native_render_section"
    assert idx_sp >= 0, "SharePoint fallback must still exist for cloud mode"
    assert idx_native < idx_sp, (
        "alpha.46 regression: native render must run BEFORE the SharePoint "
        "pipeline, otherwise native builds still hit the 'Package not found' 500"
    )


def test_sections_list_falls_back_to_disk():
    src = (ROOT / "routes" / "slide_fetcher.py").read_text()
    sl_start = src.index("async def get_sections_list")
    sl_end = src.index("@router.post", sl_start)
    body = src[sl_start:sl_end]
    assert "_load_pres_from_disk" in body, (
        "alpha.46: get_sections_list must fall back to disk on DB miss"
    )


def test_presentations_get_falls_back_to_disk():
    src = (ROOT / "routes" / "presentations.py").read_text()
    gp_start = src.index("async def get_presentation(")
    gp_end = src.index("@router.", gp_start + 1)
    body = src[gp_start:gp_end]
    # Must scan `Files/Trivia/Rounds/*.bighat` before 404ing
    assert "Rounds" in body and ".bighat" in body, (
        "alpha.46: get_presentation must scan disk before returning 404"
    )
    # Must still raise 404 at the very end (when disk misses too)
    assert 'HTTPException(status_code=404' in body


def test_store_all_accepts_arbitrary_body_shapes():
    src = (ROOT / "routes" / "slide_fetcher.py").read_text()
    sa_start = src.index("async def store_all_slides")
    sa_end = src.index("async def _fetch_pptx_slides", sa_start)
    body = src[sa_start:sa_end]
    # Signature must NOT force a required `slides: list` body param (that's
    # what 422s empty payloads).
    assert "slides: list" not in body[:200], (
        "alpha.46: store_all_slides signature must not require slides:list "
        "as a positional param — that 422s the wizard's empty-body call"
    )
    # Should read the raw body ourselves and handle list | dict | empty.
    assert "await request.json()" in body
    assert "isinstance(payload, list)" in body
    assert "isinstance(payload, dict)" in body


def test_trivia_viewer_list_never_500s():
    src = (ROOT / "routes" / "trivia_viewer.py").read_text()
    # Locate the list handler
    lh_start = src.index("async def list_trivia_presentations")
    lh_end = src.index("@router.", lh_start + 1)
    body = src[lh_start:lh_end]
    # Outer except must return an empty list (or disk-only fallback), not
    # raise HTTPException(500).
    assert 'raise HTTPException(status_code=500' not in body, (
        "alpha.46 regression: /trivia-viewer/list top-level except must "
        "return a payload, not 500 (frontend Promise.all cascades)"
    )
    assert "disk-only fallback" in body or "return []" in body


# ------- end-to-end round-trip via TestClient ------------------------------

@pytest.fixture(scope="module")
def api_client(tmp_path_factory, monkeypatch_module=None):
    """Fresh TestClient with a scratch BIGHAT_FILES_DIR. Uses the real
    server import (server.py), so route wiring is validated too."""
    tmp = tmp_path_factory.mktemp("alpha46_e2e")
    os.environ["BIGHAT_FILES_DIR"] = str(tmp)
    # Reload server to pick up env
    for name in list(sys.modules):
        if name.startswith(("server", "routes", "native", "native_slides")):
            sys.modules.pop(name, None)
    import server as _server
    from fastapi.testclient import TestClient
    return TestClient(_server.app), tmp


def test_e2e_presentation_survives_db_wipe(api_client):
    """Merchant-facing scenario: build a presentation, wipe the DB (i.e.
    simulate an app restart), and confirm the endpoints still serve the
    presentation from disk."""
    client, tmp = api_client
    ids = _write_test_bundle(tmp)
    pid = ids["pres_id"]

    # /presentations/{id} — must find via disk fallback
    r = client.get(f"/api/presentations/{pid}")
    assert r.status_code == 200, r.text
    assert r.json()["id"] == pid
    # Explicit disk source marker
    assert r.json().get("source") == "native-disk"

    # /slide-fetcher/sections-list/{id} — must find via disk fallback
    r = client.get(f"/api/slide-fetcher/sections-list/{pid}")
    assert r.status_code == 200, r.text
    sections = r.json()["sections"]
    names = {s["name"] for s in sections}
    assert "host" in names and "round_1" in names

    # /slide-fetcher/fetch-section/{id}/host — native render, real content
    r = client.post(f"/api/slide-fetcher/fetch-section/{pid}/host", json={})
    assert r.status_code == 200, r.text
    payload = r.json()
    assert payload["source"] == "native-disk"
    assert payload["slidesCount"] >= 1
    # /store-all with empty body — must not 422
    r = client.post(f"/api/slide-fetcher/store-all/{pid}", json={})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "skipped"
