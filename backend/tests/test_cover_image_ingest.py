"""Cover-image ingest + serving contract — v32.0.0-alpha.24.

When a `.bighat` archive bundles `assets/cover.*` or `assets/title_card.*`,
the importer (`_ingest_cover_image`) must:
  • drop the image bytes into the Round Maker UPLOAD_DIR with a uuid
    stem and the original extension,
  • return the stem so it can be persisted on `doc.cover_image_id`,
  • cause `GET /api/roundmaker/cover-image/{stem}` to stream those bytes
    back (extension-agnostic — frontend doesn't track the original ext).

This replaces the alpha.23 GridFS-based ingestion. The change unblocks
two long-standing failures:
  1. `_find_cover_image()` (which the PPTX generator calls) walks
     UPLOAD_DIR by stem and never knew how to read GridFS. Imported
     covers were skipped in the generated PPTX.
  2. The Round Maker editor had no UI endpoint to preview a GridFS
     cover. The host's bundled title image silently disappeared.
"""
from __future__ import annotations

import asyncio
import io
import shutil
import uuid
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

mongomock_motor = pytest.importorskip("mongomock_motor")

from backend.routes import bighat_files as bf
from backend.routes import roundmaker as rm


@pytest.fixture
def isolated_upload_dir(tmp_path, monkeypatch):
    """Redirect UPLOAD_DIR to a tmp tree so the test never touches the
    real `backend/roundmaker_uploads/` (which is shared with the running
    backend in dev)."""
    fake_uploads = tmp_path / "uploads"
    fake_uploads.mkdir()
    monkeypatch.setattr(rm, "UPLOAD_DIR", fake_uploads)
    return fake_uploads


@pytest.fixture
def fake_db(monkeypatch):
    client = mongomock_motor.AsyncMongoMockClient()
    db = client["bighat_test"]
    bf.set_database(db)
    rm.db = db
    return db


def _make_bighat_with_cover(blob: bytes, asset_name: str = "cover.png") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", '{"format":"bighat","version":2,"type":"round","round_name":"Test","round_type":"REG"}')
        zf.writestr("payload.json", '{"name":"Test","questions":[{"n":1,"prompt":"q?","answer":"a"}],"round_type":"REG"}')
        zf.writestr(f"assets/{asset_name}", blob)
    return buf.getvalue()


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_ingest_cover_writes_to_upload_dir(isolated_upload_dir, fake_db):
    payload = b"\x89PNG\r\n\x1a\nfake-png-bytes-here-not-real"
    bighat = _make_bighat_with_cover(payload, "cover.png")
    res = _run(bf._import_zip_bytes(bighat))
    doc = _run(fake_db.rounds.find_one({"id": res.id}, {"_id": 0}))

    file_id = doc.get("cover_image_id")
    assert file_id, "cover_image_id should be populated"
    # File on disk, name == <uuid>.png
    matches = list(isolated_upload_dir.glob(f"{file_id}.*"))
    assert len(matches) == 1, f"expected one file with stem {file_id}, got {matches}"
    assert matches[0].suffix == ".png"
    assert matches[0].read_bytes() == payload


def test_ingest_cover_handles_jpg_extension(isolated_upload_dir, fake_db):
    payload = b"\xff\xd8\xff\xe0fake-jpeg"
    bighat = _make_bighat_with_cover(payload, "cover.jpg")
    res = _run(bf._import_zip_bytes(bighat))
    doc = _run(fake_db.rounds.find_one({"id": res.id}, {"_id": 0}))
    file_id = doc.get("cover_image_id")
    matches = list(isolated_upload_dir.glob(f"{file_id}.*"))
    assert matches[0].suffix == ".jpg"


def test_ingest_cover_recognises_title_card_stem(isolated_upload_dir, fake_db):
    bighat = _make_bighat_with_cover(b"png-bytes", "title_card.png")
    res = _run(bf._import_zip_bytes(bighat))
    doc = _run(fake_db.rounds.find_one({"id": res.id}, {"_id": 0}))
    assert doc.get("cover_image_id")


def test_ingest_cover_skips_unrelated_assets(isolated_upload_dir, fake_db):
    """Random extra assets (e.g. per-question media gifs) must NOT be
    treated as the cover image."""
    bighat = _make_bighat_with_cover(b"some-bytes", "q1.gif")
    res = _run(bf._import_zip_bytes(bighat))
    doc = _run(fake_db.rounds.find_one({"id": res.id}, {"_id": 0}))
    assert not doc.get("cover_image_id"), "non-cover asset should not have been ingested"


def test_cover_image_endpoint_serves_imported_bytes(isolated_upload_dir, fake_db):
    """Round-trip: import a .bighat with a cover image, then fetch the
    `/cover-image/{id}` URL the frontend uses for the editor preview."""
    payload = b"\x89PNG-real-image-bytes-here"
    bighat = _make_bighat_with_cover(payload, "cover.png")
    res = _run(bf._import_zip_bytes(bighat))
    doc = _run(fake_db.rounds.find_one({"id": res.id}, {"_id": 0}))
    file_id = doc["cover_image_id"]

    # Use the FastAPI router directly so we don't depend on the live
    # supervisor. Build a minimal app that mounts just the roundmaker router.
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(rm.router, prefix="/api")
    client = TestClient(app)
    r = client.get(f"/api/roundmaker/cover-image/{file_id}")
    assert r.status_code == 200
    assert r.content == payload


def test_cover_image_endpoint_404s_unknown_id(isolated_upload_dir, fake_db):
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(rm.router, prefix="/api")
    client = TestClient(app)
    r = client.get(f"/api/roundmaker/cover-image/{uuid.uuid4()}")
    assert r.status_code == 404


def test_cover_image_endpoint_rejects_path_traversal(isolated_upload_dir, fake_db):
    """Defensive: a malicious caller must not be able to read files
    outside UPLOAD_DIR via the {file_id} path component."""
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(rm.router, prefix="/api")
    client = TestClient(app)
    r = client.get("/api/roundmaker/cover-image/..%2F..%2Fetc%2Fpasswd")
    # FastAPI URL-decodes path params, so this lands as `..` in the
    # handler; either 400 (rejected) or 404 (no match) is acceptable.
    assert r.status_code in (400, 404)
