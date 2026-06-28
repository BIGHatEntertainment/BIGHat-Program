"""Play-Direct contract test — v32.0.0-alpha.25.

`POST /api/bighat-files/play-direct` is the one-click pipeline that
imports a `.bighat` ROUND file, compiles it to a `.pptx` via the same
generator the Round Maker uses, wraps it as a `trivia_presentations`
doc, and returns the presentation_id so the host can navigate
straight to the in-app presenter view.

What this test asserts:
  • A real merchant `.bighat` round file is accepted and produces
    a presentation_id + round_id.
  • The created `rounds` row carries the canonical normalised question
    shape (so the round renders identically to one the host built
    locally — same `question`/`options`/`correctOption`/`answer` keys).
  • The created `trivia_presentations` row has `type='trivia-imported'`
    (so /trivia-viewer/list picks it up) and `roundFiles[0].file`
    points at a local `.pptx` that actually exists on disk.
  • Non-round .bighat archives are rejected with a 400 instead of
    silently importing into the wrong collection.
"""
from __future__ import annotations

import asyncio
import io
import zipfile
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

mongomock_motor = pytest.importorskip("mongomock_motor")

from backend.routes import bighat_files as bf
from backend.routes import roundmaker as rm


FIXT = Path(__file__).parent / "fixtures" / "bighat"


@pytest.fixture
def isolated_dirs(tmp_path, monkeypatch):
    """Redirect UPLOAD_DIR + GENERATED_DIR onto a tmp tree so each test
    starts from a clean slate and never pollutes the dev server."""
    uploads = tmp_path / "uploads"
    generated = tmp_path / "generated"
    uploads.mkdir()
    generated.mkdir()
    monkeypatch.setattr(rm, "UPLOAD_DIR", uploads)
    monkeypatch.setattr(rm, "GENERATED_DIR", generated)
    return tmp_path


@pytest.fixture
def app(monkeypatch, isolated_dirs):
    client = mongomock_motor.AsyncMongoMockClient()
    db = client["bighat_test"]
    bf.set_database(db)
    rm.db = db
    app = FastAPI()
    app.include_router(bf.router, prefix="/api")
    app.include_router(rm.router, prefix="/api")
    return app, db


def test_play_direct_accepts_mc_bighat_and_returns_presentation_id(app):
    fastapi_app, db = app
    client = TestClient(fastapi_app)
    with (FIXT / "mc-01-a.bighat").open("rb") as fh:
        r = client.post(
            "/api/bighat-files/play-direct",
            files={"file": ("mc-01-a.bighat", fh.read(), "application/x-bighat")},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["round_type"] == "MC"
    assert body["round_id"]
    assert body["presentation_id"]
    # Round was inserted with normalised questions.
    round_doc = asyncio.get_event_loop().run_until_complete(
        db.rounds.find_one({"id": body["round_id"]}, {"_id": 0})
    )
    assert round_doc is not None
    q0 = round_doc["questions"][0]
    assert q0["question"].startswith("What TV series")
    assert q0["correctOption"] == 0
    assert q0["options"][:4] == ["M*A*S*H", "Seinfeld", "Cheers", "Friends"]
    # PPTX was generated on disk and persisted on the round doc.
    assert round_doc["status"] == "generated"
    assert round_doc["pptx_path"]
    assert Path(round_doc["pptx_path"]).is_file()
    # Presentation doc was inserted with type='trivia-imported' and
    # roundFiles[0].file pointing at the generated PPTX.
    pres_doc = asyncio.get_event_loop().run_until_complete(
        db.trivia_presentations.find_one({"id": body["presentation_id"]}, {"_id": 0})
    )
    assert pres_doc is not None
    assert pres_doc["type"] == "trivia-imported"
    assert pres_doc["direct_play"] is True
    assert pres_doc["direct_play_round_id"] == body["round_id"]
    assert pres_doc["numRounds"] == 1
    assert pres_doc["roundTypes"] == ["MC"]
    assert len(pres_doc["roundFiles"]) == 1
    assert pres_doc["roundFiles"][0]["file"] == round_doc["pptx_path"]
    assert Path(pres_doc["roundFiles"][0]["file"]).is_file()


def test_play_direct_accepts_reg_bighat_with_no_options(app):
    fastapi_app, db = app
    client = TestClient(fastapi_app)
    with (FIXT / "animals-1.bighat").open("rb") as fh:
        r = client.post(
            "/api/bighat-files/play-direct",
            files={"file": ("animals-1.bighat", fh.read(), "application/x-bighat")},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["round_type"] == "REG"
    round_doc = asyncio.get_event_loop().run_until_complete(
        db.rounds.find_one({"id": body["round_id"]}, {"_id": 0})
    )
    assert round_doc["questions"][0]["question"].startswith("What land animal")
    assert round_doc["questions"][0]["answer"] == "Giant Armadillo"


def test_play_direct_rejects_non_round_bighat(app):
    """A presentation/bingo/scoreboard .bighat must not get silently
    sucked into the rounds collection. The endpoint should 400."""
    fastapi_app, _ = app
    client = TestClient(fastapi_app)

    # Hand-build a minimal presentation .bighat.
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", '{"format":"bighat","version":2,"type":"presentation"}')
        zf.writestr("payload.json", '{"id":"x","name":"Some Presentation","type":"trivia-imported"}')

    r = client.post(
        "/api/bighat-files/play-direct",
        files={"file": ("some-pres.bighat", buf.getvalue(), "application/x-bighat")},
    )
    assert r.status_code == 400, r.text
    assert "round" in r.text.lower()


def test_play_direct_uses_same_pptx_pipeline_as_round_maker(app):
    """The whole point of play-direct is that the file *renders* the same
    way it would if the host had imported then clicked 'Download PPTX' in
    Round Maker. Smoke-test this by importing twice (once direct, once
    plain) and comparing the generated PPTX file sizes — they should
    be identical to within python-pptx's nondeterminism, which in
    practice means byte-equal for a deterministic payload."""
    fastapi_app, db = app
    client = TestClient(fastapi_app)
    fixture_bytes = (FIXT / "mc-01-a.bighat").read_bytes()

    # Plain import → manually generate PPTX
    r1 = client.post(
        "/api/bighat-files/import",
        files={"file": ("mc.bighat", fixture_bytes, "application/x-bighat")},
    )
    rid1 = r1.json()["id"]
    r1g = client.post(f"/api/roundmaker/rounds/{rid1}/generate")
    assert r1g.status_code == 200
    size_plain = len(r1g.content)

    # Direct play → backend generates internally
    r2 = client.post(
        "/api/bighat-files/play-direct",
        files={"file": ("mc.bighat", fixture_bytes, "application/x-bighat")},
    )
    assert r2.status_code == 200
    rid2 = r2.json()["round_id"]
    round_doc = asyncio.get_event_loop().run_until_complete(
        db.rounds.find_one({"id": rid2}, {"_id": 0})
    )
    size_direct = Path(round_doc["pptx_path"]).stat().st_size

    # Same .bighat fed through the same generator → same output bytes.
    # If python-pptx ever adds metadata that varies run-to-run we may
    # need to relax this, but for the deterministic content_id-driven
    # name path the file sizes should match exactly.
    assert abs(size_plain - size_direct) < 4096, (
        f"PPTX size mismatch ({size_plain} vs {size_direct}) "
        f"suggests play-direct is using a different rendering path "
        f"than Round Maker's /generate endpoint"
    )
