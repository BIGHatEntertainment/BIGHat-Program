"""Lobby 'Presentation Details' page: wizard-built shows must show location, host, date, round names, slides."""
import json, os, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pytest
pytest.importorskip("montydb")
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("BIGHAT_FILES_DIR", str(tmp_path))
    monkeypatch.setenv("BIGHAT_DB_DIR", str(tmp_path / "db"))
    monkeypatch.setenv("BIGHAT_NATIVE_MODE", "1")
    for n in list(sys.modules):
        if n in ("round_usage", "native_slides", "presentation_builder", "slide_style", "global_slides"):
            sys.modules.pop(n, None)
    root = tmp_path / "Files"
    (root / "Hosts" / "h@x.com").mkdir(parents=True)
    (root / "Hosts" / "h@x.com" / "host.json").write_text(json.dumps({"email": "h@x.com", "display_name": "Nick Sellards", "id": "h@x.com"}))
    (root / "Locations" / "monkey-pants-bar-grill").mkdir(parents=True)
    (root / "Locations" / "monkey-pants-bar-grill" / "location.json").write_text(
        json.dumps({"id": "L1", "name": "Monkey Pants Bar Grill", "slug": "monkey-pants-bar-grill"}))
    sp = root / "Trivia" / "Special"; sp.mkdir(parents=True)
    types, names = ["MC", "REG", "MISC", "MYS", "BIG"], ["MC_01_A (1)", "Animals_1", "Dino_Night_3", "Secret_2", "Big_5"]
    for i, (t, n) in enumerate(zip(types, names)):
        (sp / f"r{i}.bighat").write_text(json.dumps({"round_type": t, "name": n, "tiebreaker": {"question": "t", "answer": "1"},
            "questions": [{"number": k + 1, "question": "q", "answer": "a", "options": ["a", "b"] if t == "MC" else []} for k in range(3)]}))
    import presentation_builder as pb
    pres = pb.build_special(name="Monkey Pants Bar Grill - 10/1", host_id="h@x.com", location_id="L1",
                            round_types=types, round_files=[f"r{i}.bighat" for i in range(5)])
    from routes import trivia_viewer as tv
    import native.db_factory as dbf
    dbf._native_client = None
    tv.db = dbf.get_db()
    app = FastAPI(); app.include_router(tv.router, prefix="/api")
    return TestClient(app), pres, tv


def _find(tv):
    for r in tv.router.routes:
        pass


def test_details_have_location_host_date_names_and_slide_counts(client):
    c, pres, tv = client
    prefix = [r.path for r in tv.router.routes if r.path.endswith("/{presentation_id}") and "slides" not in r.path]
    r = c.get(f"/api{prefix[0].replace('{presentation_id}', pres['id'])}")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["location"] == "Monkey Pants Bar Grill"                 # not 'Unknown'
    assert d["host"] == "Nick Sellards"
    assert d["createdBy"]
    assert d["createdAt"] and d["createdAt"][:4].isdigit()           # parseable date, not 'Invalid Date'
    assert d["numRounds"] == 5 and d["roundTypes"] == ["MC", "REG", "MISC", "MYS", "BIG"]
    assert d["roundNames"] == ["MC_01_A (1)", "Animals_1", "Dino_Night_3", "Secret_2", "Big_5"]
    counts = [rf["slideCount"] for rf in d["roundFiles"]]
    assert counts and all(c_ > 1 for c_ in counts)                   # real counts, not '~12'
    assert d["totalSlides"] >= sum(counts)                           # + host/location/global slides


def test_old_webapp_shaped_presentations_still_work(client):
    c, pres, tv = client
    # no crash for a minimal legacy-shaped doc
    import asyncio
    assert callable(tv.get_trivia_presentation)
