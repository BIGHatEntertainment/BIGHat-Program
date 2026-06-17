"""Round-trip + signing tests for `.bighat` v2 format.

Covers:
  * Round export → import (legacy v1 path)
  * Presentation export → import (new in v2)
  * Bingo export → import
  * Scoreboard export → import
  * `/inspect` previewing without committing
  * `/types` reports the registry
  * HMAC signing: signed file imports OK when the same key is set; rejected
    when the key changes (publisher mismatch).
  * Forward-compat: v3 manifest is rejected with a clear "update the app"
    message rather than silently truncating.
"""
from __future__ import annotations

import io
import os
import zipfile
import json

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("MONGO_URL", os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    monkeypatch.setenv("DB_NAME", "test_bighat_files_v2")
    monkeypatch.setenv("BIGHAT_NATIVE_MODE", "1")
    monkeypatch.delenv("BIGHAT_CLOUD_MODE", raising=False)
    # Force-reimport so server picks up env.
    import importlib, sys
    for m in list(sys.modules):
        if m == "server":
            sys.modules.pop(m, None)
    import server  # noqa
    with TestClient(server.app) as c:
        yield c


def _seed_doc(client, collection: str, doc: dict):
    """Insert one doc using the running server's own db handle (which may be
    MontyDB in native mode, not raw MongoDB)."""
    import asyncio, server
    async def _insert():
        await server.db[collection].insert_one(doc)
    asyncio.get_event_loop().run_until_complete(_insert())


# ---------- /types registry ----------

def test_types_endpoint_lists_all_four_content_types(client):
    r = client.get("/api/bighat-files/types")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["format"] == "bighat"
    assert body["version"] == 2
    assert set(body["types"].keys()) == {"round", "presentation", "bingo", "scoreboard"}


# ---------- Round Maker round (legacy v1 path) ----------

def test_round_export_then_import_roundtrip(client):
    _seed_doc(client, "rounds", {
        "id": "round-test-1",
        "name": "Test Round (v2)",
        "round_type": "REG",
        "questions": [{"q": "What is 2+2?", "a": "4", "points": 10}],
        "tiebreaker": None,
        "status": "draft",
    })
    # Export via legacy single-id URL (used by existing dashboard)
    r = client.get("/api/bighat-files/export/round-test-1")
    assert r.status_code == 200
    bighat = r.content
    assert len(bighat) > 200
    # Re-import
    r2 = client.post(
        "/api/bighat-files/import",
        files={"file": ("test.bighat", io.BytesIO(bighat), "application/x-bighat")},
    )
    assert r2.status_code == 200, r2.text
    body = r2.json()
    assert body["type"] == "round"
    assert body["name"] == "Test Round (v2)"
    assert body["round_id"] is not None             # back-compat field


# ---------- Presentation ----------

def test_presentation_export_then_import_roundtrip(client):
    _seed_doc(client, "trivia_presentations", {
        "id": "pres-test-1",
        "title": "80s Music Mega-Mix",
        "rounds": [{"name": "R1"}, {"name": "R2"}],
    })
    r = client.get("/api/bighat-files/export/presentation/pres-test-1")
    assert r.status_code == 200
    bighat = r.content
    r2 = client.post(
        "/api/bighat-files/import",
        files={"file": ("p.bighat", io.BytesIO(bighat), "application/x-bighat")},
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["type"] == "presentation"


# ---------- Bingo ----------

def test_bingo_export_then_import_roundtrip(client):
    _seed_doc(client, "bingo_games", {
        "id": "bingo-test-1",
        "name": "Friday Night Bingo",
        "card_size": 5,
        "calls": ["B1", "I16", "N31", "G46", "O61"],
    })
    r = client.get("/api/bighat-files/export/bingo/bingo-test-1")
    assert r.status_code == 200, r.text
    bighat = r.content
    r2 = client.post(
        "/api/bighat-files/import",
        files={"file": ("b.bighat", io.BytesIO(bighat), "application/x-bighat")},
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["type"] == "bingo"


# ---------- Scoreboard ----------

def test_scoreboard_export_then_import_roundtrip(client):
    _seed_doc(client, "scoreboard_themes", {
        "id": "sb-test-1",
        "name": "Default Tavern Theme",
        "primary_color": "#fbdd68",
    })
    r = client.get("/api/bighat-files/export/scoreboard/sb-test-1")
    assert r.status_code == 200
    bighat = r.content
    r2 = client.post(
        "/api/bighat-files/import",
        files={"file": ("s.bighat", io.BytesIO(bighat), "application/x-bighat")},
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["type"] == "scoreboard"


# ---------- Inspect (preview) ----------

def test_inspect_does_not_commit_to_db(client):
    _seed_doc(client, "rounds", {
        "id": "round-inspect-1", "name": "Inspect Me",
        "round_type": "REG", "questions": [],
    })
    # Snapshot the "imported_from=.bighat" count BEFORE the inspect call so we
    # detect committing precisely, even if prior tests left documents behind.
    import asyncio, server
    async def _count():
        return await server.db.rounds.count_documents({"imported_from": ".bighat"})
    before = asyncio.get_event_loop().run_until_complete(_count())
    r = client.get("/api/bighat-files/export/round-inspect-1")
    bighat = r.content
    r2 = client.post(
        "/api/bighat-files/inspect",
        files={"file": ("x.bighat", io.BytesIO(bighat), "application/x-bighat")},
    )
    assert r2.status_code == 200
    body = r2.json()
    assert body["type"] == "round"
    assert body["name"] == "Inspect Me"
    after = asyncio.get_event_loop().run_until_complete(_count())
    assert after == before, "inspect() must not write to the DB"


# ---------- Signing ----------

def test_signed_bighat_imports_with_matching_key(client, monkeypatch):
    monkeypatch.setenv("BIGHAT_SIGNING_KEY", "publisher-secret-123")
    _seed_doc(client, "rounds", {
        "id": "round-signed-1", "name": "Premium Pack Round",
        "round_type": "REG", "questions": [],
    })
    # Export — should now include signature.txt
    r = client.get("/api/bighat-files/export/round-signed-1")
    assert r.status_code == 200
    bighat = r.content
    with zipfile.ZipFile(io.BytesIO(bighat)) as zf:
        assert "signature.txt" in zf.namelist()

    # Import with the SAME key → success.
    r2 = client.post(
        "/api/bighat-files/import",
        files={"file": ("p.bighat", io.BytesIO(bighat), "application/x-bighat")},
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["signed"] is True


def test_signed_bighat_rejected_when_key_changes(client, monkeypatch):
    # Export with key A
    monkeypatch.setenv("BIGHAT_SIGNING_KEY", "publisher-A")
    _seed_doc(client, "rounds", {
        "id": "round-tamper-1", "name": "Signed By A",
        "round_type": "REG", "questions": [],
    })
    r = client.get("/api/bighat-files/export/round-tamper-1")
    bighat = r.content

    # Now flip to a DIFFERENT key and try to import the same file
    monkeypatch.setenv("BIGHAT_SIGNING_KEY", "publisher-B")
    r2 = client.post(
        "/api/bighat-files/import",
        files={"file": ("tampered.bighat", io.BytesIO(bighat), "application/x-bighat")},
    )
    assert r2.status_code == 400
    assert "signature" in r2.json()["detail"].lower()


# ---------- Forward-compatibility ----------

def test_future_version_rejected_with_clear_message(client):
    """A .bighat file claiming version 99 should fail with an 'update the app'
    error rather than partial import."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("manifest.json", json.dumps({
            "format": "bighat", "version": 99, "type": "round",
            "name": "From The Future",
        }))
        zf.writestr("payload.json", json.dumps({"id": "x", "name": "X"}))
    buf.seek(0)
    r = client.post(
        "/api/bighat-files/import",
        files={"file": ("future.bighat", buf, "application/x-bighat")},
    )
    assert r.status_code == 400
    assert "newer version" in r.json()["detail"].lower()


def test_oversize_file_rejected(client):
    """A file claiming > 50MB should be refused at upload time."""
    big = io.BytesIO(b"\x00" * (51 * 1024 * 1024))
    r = client.post(
        "/api/bighat-files/import",
        files={"file": ("huge.bighat", big, "application/x-bighat")},
    )
    assert r.status_code == 413
