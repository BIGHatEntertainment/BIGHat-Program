"""Contract test for the v32.0.0-alpha.18 native-files redesign.

The Files tool now has typed subfolders + a one-shot migration of any
flat .bighat files into the correct subfolder. These tests pin the
contract by exercising the real router against a temp filesystem
override — `BIGHAT_FILES_DIR` is honoured by `_base_root()`.

Why an integration test rather than a unit test:
  • The migration only runs once per install (it writes a marker file).
  • The folder routing depends on parsing the actual .bighat archive
    `manifest.json` — mocking that out is more code than just building
    a real zip.
"""
from __future__ import annotations

import io
import json
import os
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI

from backend.native.files_router import router as files_router


@pytest.fixture
def tmp_store(tmp_path, monkeypatch):
    """Point the files store at a fresh temp dir for this test."""
    monkeypatch.setenv("BIGHAT_FILES_DIR", str(tmp_path / "Files"))
    yield tmp_path / "Files"


@pytest.fixture
def client(tmp_store):
    app = FastAPI()
    app.include_router(files_router)
    return TestClient(app)


def _make_bighat(content_type: str, **manifest_extras) -> bytes:
    """Build a minimal .bighat zip with the given manifest type."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        manifest = {"type": content_type, **manifest_extras}
        zf.writestr("manifest.json", json.dumps(manifest))
        if content_type in ("round", "presentation", "pack"):
            payload = {"questions": [{"category": "test"} for _ in range(10)]}
            zf.writestr("payload.json", json.dumps(payload))
    return buf.getvalue()


def test_folder_endpoint_lists_subfolders(client):
    r = client.get("/api/native/files/folder")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert "Rounds" in body["subfolders"]
    assert "Bingo" in body["subfolders"]
    assert "Karaoke" in body["subfolders"]
    assert "Other" in body["subfolders"]
    assert "hosts_folder" in body


def test_upload_routes_round_to_rounds_subfolder(client, tmp_store):
    """A round .bighat must land in Files/Rounds/ without an explicit
    folder hint."""
    blob = _make_bighat("round", round_name="Test round")
    r = client.post(
        "/api/native/files/upload",
        files={"file": ("test.bighat", blob, "application/octet-stream")},
    )
    assert r.status_code == 200, r.text
    assert r.json()["folder"] == "Rounds"
    assert (tmp_store / "Rounds" / "test.bighat").exists()


def test_upload_routes_bingo_to_bingo(client, tmp_store):
    blob = _make_bighat("bingo")
    r = client.post(
        "/api/native/files/upload",
        files={"file": ("bingo-pack.bighat", blob, "application/octet-stream")},
    )
    assert r.status_code == 200, r.text
    assert r.json()["folder"] == "Bingo"
    assert (tmp_store / "Bingo" / "bingo-pack.bighat").exists()


def test_upload_unknown_type_falls_back_to_other(client, tmp_store):
    blob = _make_bighat("unknown_thing")
    r = client.post(
        "/api/native/files/upload",
        files={"file": ("mystery.bighat", blob, "application/octet-stream")},
    )
    assert r.status_code == 200, r.text
    assert r.json()["folder"] == "Other"


def test_upload_with_explicit_folder_hint_overrides_autoroute(client, tmp_store):
    """If the user has the Bingo tab open, dropping a round.bighat in it
    must land in Bingo/ (the user's explicit intent wins)."""
    blob = _make_bighat("round")
    r = client.post(
        "/api/native/files/upload",
        data={"folder": "Bingo"},
        files={"file": ("manual.bighat", blob, "application/octet-stream")},
    )
    assert r.status_code == 200, r.text
    assert r.json()["folder"] == "Bingo"
    assert (tmp_store / "Bingo" / "manual.bighat").exists()


def test_upload_rejects_bad_folder(client):
    blob = _make_bighat("round")
    r = client.post(
        "/api/native/files/upload",
        data={"folder": "../../etc"},
        files={"file": ("hax.bighat", blob, "application/octet-stream")},
    )
    assert r.status_code == 400
    assert "invalid_folder" in r.json()["detail"]


def test_flat_layout_migration(client, tmp_store):
    """Files that landed in the flat Files/ root pre-alpha.18 get moved
    into the right typed subfolder on the next list call."""
    # Simulate a pre-migration flat layout: write a round.bighat directly
    # in the base dir, bypassing the API.
    tmp_store.mkdir(parents=True, exist_ok=True)
    flat = tmp_store / "legacy-round.bighat"
    flat.write_bytes(_make_bighat("round"))
    assert flat.exists()

    # First list call triggers the migration.
    r = client.get("/api/native/files")
    assert r.status_code == 200
    # The file should now be in Rounds/, not at the base.
    assert not flat.exists()
    assert (tmp_store / "Rounds" / "legacy-round.bighat").exists()
    # Listing should surface it under Rounds.
    files = r.json()["files"]
    legacy = [f for f in files if f["name"] == "legacy-round.bighat"]
    assert legacy and legacy[0]["folder"] == "Rounds"


def test_filtered_listing(client, tmp_store):
    """`?folder=Rounds` only returns files in Rounds/."""
    client.post("/api/native/files/upload",
                files={"file": ("a.bighat", _make_bighat("round"), "application/octet-stream")})
    client.post("/api/native/files/upload",
                files={"file": ("b.bighat", _make_bighat("bingo"), "application/octet-stream")})
    r = client.get("/api/native/files", params={"folder": "Rounds"})
    assert r.status_code == 200
    names = [f["name"] for f in r.json()["files"]]
    assert "a.bighat" in names
    assert "b.bighat" not in names


def test_delete_with_folder_hint(client, tmp_store):
    client.post("/api/native/files/upload",
                files={"file": ("del.bighat", _make_bighat("round"), "application/octet-stream")})
    assert (tmp_store / "Rounds" / "del.bighat").exists()
    r = client.delete("/api/native/files/del.bighat", params={"folder": "Rounds"})
    assert r.status_code == 200
    assert not (tmp_store / "Rounds" / "del.bighat").exists()


def test_delete_without_folder_falls_back_to_search(client, tmp_store):
    """Backwards-compat: pre-alpha.18 clients call DELETE /name without
    a folder param. We should find the file in whichever subfolder it
    landed in."""
    client.post("/api/native/files/upload",
                files={"file": ("fallback.bighat", _make_bighat("round"), "application/octet-stream")})
    r = client.delete("/api/native/files/fallback.bighat")
    assert r.status_code == 200


def test_hosts_dir_created_alongside_files(client, tmp_store):
    """Sibling Hosts/ folder for host-scoped working data."""
    r = client.get("/api/native/files/folder")
    hosts_folder = Path(r.json()["hosts_folder"])
    assert hosts_folder.exists()
    # And lives next to Files/, not inside it.
    assert hosts_folder.parent == tmp_store.parent
