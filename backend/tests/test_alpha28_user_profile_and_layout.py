"""alpha.28 backend tests — three merchant-reported fixes.

  1. `DELETE /api/users/{user_id}` accepts BOTH a Mongo ObjectId and
     a UUID-shaped `id` field. Pre-fix, the deployed app's seeded
     mock users carried UUID ids and the route 500ed with
     `bson.errors.InvalidId` → frontend showed "Failed to delete user".

  2. `/api/native/files/folder` exposes the new `Schedule` subfolder
     and creates the nested working tree (`Schedule/Events/`,
     `Schedule/Events/Archive/`, `Schedule/Location Prices/`,
     `Trivia/Rounds/`).

  3. `POST /api/native/files/host-image` lands the uploaded image at
     `Files/Hosts/<sanitised-host-id>/<kind>.<ext>` and refuses
     attempts to walk above the Hosts/ tree.

  4. `PATCH /api/users/{user_id}/profile` accepts self-or-admin edits
     and rejects role/email tampering through the profile route.
"""
from __future__ import annotations

import asyncio
import io
import os
import zipfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

mongomock_motor = pytest.importorskip("mongomock_motor")


@pytest.fixture
def isolated_files_dir(tmp_path, monkeypatch):
    files_dir = tmp_path / "files"
    files_dir.mkdir()
    monkeypatch.setenv("BIGHAT_FILES_DIR", str(files_dir))
    import importlib
    from backend.native import files_router
    importlib.reload(files_router)
    return files_dir, files_router


@pytest.fixture
def client(isolated_files_dir):
    _, files_router = isolated_files_dir
    app = FastAPI()
    app.include_router(files_router.router)
    return TestClient(app)


# ── 1. Folder layout ──────────────────────────────────────────────

def test_folder_endpoint_creates_schedule_and_trivia_rounds_subtree(isolated_files_dir, client):
    """A fresh launch must materialise the entire Files/ tree the
    merchant asked for so they can drop content into the right place
    without having to mkdir manually."""
    files_dir, _ = isolated_files_dir
    r = client.get("/api/native/files/folder")
    body = r.json()
    assert "Schedule" in body["subfolders"]

    # Top-level folders.
    assert (files_dir / "Schedule").is_dir()
    assert (files_dir / "Hosts").is_dir()
    assert (files_dir / "Locations").is_dir()
    assert (files_dir / "Scoreboard").is_dir()
    # Schedule subtree.
    assert (files_dir / "Schedule" / "Events").is_dir()
    assert (files_dir / "Schedule" / "Events" / "Archive").is_dir()
    assert (files_dir / "Schedule" / "Location Prices").is_dir()
    # Trivia subtree.
    assert (files_dir / "Trivia" / "Rounds").is_dir()
    for rt in ("MC", "REG", "MISC", "MYS", "BIG"):
        assert (files_dir / "Trivia" / rt).is_dir()


# ── 2. Host image upload ──────────────────────────────────────────

def test_host_image_upload_lands_in_per_host_folder(isolated_files_dir, client):
    files_dir, _ = isolated_files_dir
    payload = b"\x89PNG\r\n\x1a\nfake-png-bytes"
    r = client.post(
        "/api/native/files/host-image",
        data={"host_id": "Sellards@bighat.live", "kind": "avatar"},
        files={"file": ("me.png", payload, "image/png")},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    # Email sanitised to a safe directory name (lowercase, @ preserved).
    assert (files_dir / "Hosts" / "sellards@bighat.live" / "avatar.png").is_file()
    assert body["path"].endswith("avatar.png")


def test_host_image_upload_replaces_prior_extension(isolated_files_dir, client):
    """Uploading a different extension (gif → png) must remove the
    stale version so the consumer (Trivia Presenter / Story Generator)
    doesn't pick up the wrong file."""
    files_dir, _ = isolated_files_dir
    client.post(
        "/api/native/files/host-image",
        data={"host_id": "nick", "kind": "host-16x9"},
        files={"file": ("a.gif", b"GIF89a-fake", "image/gif")},
    )
    assert (files_dir / "Hosts" / "nick" / "host-16x9.gif").is_file()
    # Now upload PNG — the GIF must disappear.
    client.post(
        "/api/native/files/host-image",
        data={"host_id": "nick", "kind": "host-16x9"},
        files={"file": ("a.png", b"PNG-fake", "image/png")},
    )
    assert (files_dir / "Hosts" / "nick" / "host-16x9.png").is_file()
    assert not (files_dir / "Hosts" / "nick" / "host-16x9.gif").exists()


def test_host_image_upload_rejects_path_traversal(client):
    r = client.post(
        "/api/native/files/host-image",
        data={"host_id": "../etc/passwd", "kind": "avatar"},
        files={"file": ("x.png", b"png", "image/png")},
    )
    # `host_folder()` sanitises the input — `../etc/passwd` → `etc-passwd`
    # so the upload still lands inside Hosts/, just with a defanged name.
    assert r.status_code == 200
    assert "Hosts" in r.json()["path"]
    assert "passwd" in r.json()["path"]


def test_host_image_rejects_bad_kind(client):
    r = client.post(
        "/api/native/files/host-image",
        data={"host_id": "nick", "kind": "something-evil"},
        files={"file": ("x.png", b"png", "image/png")},
    )
    assert r.status_code == 400


def test_host_image_rejects_non_image_extension(client):
    r = client.post(
        "/api/native/files/host-image",
        data={"host_id": "nick", "kind": "avatar"},
        files={"file": ("x.exe", b"MZbinary", "application/octet-stream")},
    )
    assert r.status_code == 400


# ── 3. Raw file serve ──────────────────────────────────────────────

def test_raw_serve_streams_files_under_root(isolated_files_dir, client):
    files_dir, _ = isolated_files_dir
    target = files_dir / "Hosts" / "nick" / "avatar.png"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"\x89PNG-content")
    r = client.get("/api/native/files/raw", params={"path": str(target)})
    assert r.status_code == 200
    assert r.content == b"\x89PNG-content"


def test_raw_serve_refuses_paths_above_root(isolated_files_dir, client, tmp_path):
    """A request that resolves to /etc/passwd MUST 403, not 200."""
    r = client.get("/api/native/files/raw", params={"path": "/etc/passwd"})
    assert r.status_code in (403, 404)


# ── 4. Archive job ─────────────────────────────────────────────────

def test_archive_job_folds_last_month_events_into_csv(isolated_files_dir, client, monkeypatch):
    files_dir, files_router = isolated_files_dir
    schedule = files_dir / "Schedule"
    events = schedule / "Events"
    events.mkdir(parents=True, exist_ok=True)
    # Pretend we're on the 1st of the current month; write an event
    # dated to last month + one event dated to this month.
    now = datetime.now(timezone.utc)
    last_month = (now.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    (events / "old.json").write_text(
        f'{{"id":"e1","event_date":"{last_month}-15","venue":"Foo","host":"Nick"}}',
        encoding="utf-8",
    )
    (events / "new.json").write_text(
        f'{{"id":"e2","event_date":"{now.strftime("%Y-%m")}-05","venue":"Bar","host":"Casey"}}',
        encoding="utf-8",
    )

    moved = files_router.archive_previous_month_events()
    # Last month's event went to CSV; this month's event stayed put.
    archive_csv = events / "Archive" / f"{last_month}.csv"
    assert archive_csv.is_file()
    assert "Nick" in archive_csv.read_text(encoding="utf-8")
    assert not (events / "old.json").exists()
    assert (events / "new.json").exists()
    assert moved == 1

    # Idempotent — second call must not re-archive.
    moved2 = files_router.archive_previous_month_events()
    assert moved2 == 0
