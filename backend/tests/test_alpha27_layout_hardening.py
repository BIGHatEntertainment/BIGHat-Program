"""alpha.27 layout hardening tests.

Two new behaviours from merchant feedback on alpha.26:

  1. Whitelist guard on the legacy-folder merger — a stray `backend/`,
     `python/`, or other engine-data subfolder living in a legacy
     `BIGHat Entertainment` / `BH Entertainment` Documents folder
     MUST NOT be carried into the canonical "BIG Hat Entertainment"
     folder. Only the known data children (`Files/`, `Backups/`) are
     allowed to migrate. Everything else is quarantined into
     `.legacy-unknown/<alias>/` so the merchant can decide what to do
     with it.

  2. `Hosts/`, `Locations/`, and `Scoreboard/` are now first-class
     children of `Files/`, alongside the existing `Trivia/Bingo/
     Karaoke/Other` content folders. The merchant asked for the whole
     user-visible tree to live under one `Files/` umbrella.
"""
from __future__ import annotations

import io
import json
import os
import shutil
import zipfile
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


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


def test_subfolders_includes_hosts_locations_scoreboard(client):
    """Files tool needs to surface ALL the user-visible content
    categories the merchant asked for. The /folder endpoint is the
    source of truth — anything that ships here ends up as a tab in
    the Files tool UI."""
    r = client.get("/api/native/files/folder")
    body = r.json()
    assert "Trivia" in body["subfolders"]
    assert "Bingo" in body["subfolders"]
    assert "Karaoke" in body["subfolders"]
    assert "Hosts" in body["subfolders"]
    assert "Locations" in body["subfolders"]
    assert "Scoreboard" in body["subfolders"]
    assert "Other" in body["subfolders"]
    # Round-type buckets are surfaced separately so Build Wizard +
    # Round Roulette can ask the right question.
    assert set(body["trivia_round_types"]) == {"MC", "REG", "MISC", "MYS", "BIG"}


def test_hosts_root_now_lives_under_files(isolated_files_dir, client):
    """alpha.27 moved Hosts/ from a sibling of Files/ to a child of
    Files/. The /folder endpoint reports the post-move path so the
    rest of the app reads/writes host data inside the unified
    Files/ tree."""
    files_dir, _ = isolated_files_dir
    r = client.get("/api/native/files/folder")
    body = r.json()
    hosts_path = Path(body["hosts_folder"])
    assert hosts_path.parent == files_dir
    assert hosts_path.name == "Hosts"


def test_legacy_hosts_directory_is_migrated_under_files(isolated_files_dir, client):
    """If a pre-alpha.27 user has data in
    `BIG Hat Entertainment/Hosts/<host>/notes.txt`, the first call to
    /folder must move that data to
    `BIG Hat Entertainment/Files/Hosts/<host>/notes.txt`."""
    files_dir, _ = isolated_files_dir
    # Simulate the pre-alpha.27 layout: Hosts/ at the same level as Files/.
    legacy_hosts = files_dir.parent / "Hosts"
    legacy_hosts.mkdir(parents=True)
    (legacy_hosts / "nicholas").mkdir()
    (legacy_hosts / "nicholas" / "notes.txt").write_text("midweek trivia notes")

    client.get("/api/native/files/folder")

    assert not legacy_hosts.exists() or not any(legacy_hosts.iterdir()), (
        "legacy Hosts/ at the BIG Hat Entertainment root should be moved or empty"
    )
    new_path = files_dir / "Hosts" / "nicholas" / "notes.txt"
    assert new_path.is_file(), f"expected migrated file at {new_path}"
    assert new_path.read_text() == "midweek trivia notes"


def test_legacy_merger_quarantines_unknown_subfolders(tmp_path, monkeypatch):
    """A stray `backend/` directory living in the legacy
    `Documents/BIGHat Entertainment/` MUST NOT be carried into the
    canonical "BIG Hat Entertainment" folder during the alpha.26
    merge. It gets quarantined into `.legacy-unknown/<alias>/backend/`
    so the merchant can manually decide what to do with it."""
    # Build a fake Documents tree containing both the canonical
    # folder + a legacy alias with mixed content.
    fake_home = tmp_path / "home"
    docs = fake_home / "Documents"
    (docs / "BIG Hat Entertainment").mkdir(parents=True)        # empty canonical
    legacy = docs / "BIGHat Entertainment"                       # legacy alias
    (legacy / "Files" / "Trivia" / "MC").mkdir(parents=True)
    (legacy / "Files" / "Trivia" / "MC" / "round1.bighat").write_text("data")
    (legacy / "Backups").mkdir()
    (legacy / "Backups" / "snap1.zip").write_text("zipdata")
    (legacy / "backend").mkdir()                                 # the stray
    (legacy / "backend" / "main.py").write_text("# python")
    (legacy / "backend" / "VERSION.txt").write_text("32.0.0")
    (legacy / "python").mkdir()                                  # another stray
    (legacy / "python" / "interpreter.exe").write_text("binary")

    monkeypatch.delenv("BIGHAT_FILES_DIR", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))

    import importlib
    from backend.native import files_router
    importlib.reload(files_router)

    # Trigger the merger.
    files_router._base_root()

    canonical = docs / "BIG Hat Entertainment"
    # Allowed children moved in.
    assert (canonical / "Files" / "Trivia" / "MC" / "round1.bighat").is_file()
    assert (canonical / "Backups" / "snap1.zip").is_file()
    # Disallowed children quarantined, NOT exposed in the canonical root.
    assert not (canonical / "backend").exists()
    assert not (canonical / "python").exists()
    # Quarantine has the strays.
    quarantine = canonical / ".legacy-unknown" / "BIGHat Entertainment"
    assert (quarantine / "backend" / "main.py").is_file()
    assert (quarantine / "python" / "interpreter.exe").is_file()


def test_upload_locations_image_lands_in_locations_folder(isolated_files_dir, client):
    """A future endpoint can upload location media into the canonical
    place by passing `?folder=Locations`. This test just guards the
    folder resolves correctly and is creatable."""
    files_dir, _ = isolated_files_dir
    # Locations folder is created lazily by _ensure_subfolders on /folder
    client.get("/api/native/files/folder")
    assert (files_dir / "Locations").is_dir()
    assert (files_dir / "Scoreboard").is_dir()
    assert (files_dir / "Hosts").is_dir()


def test_scoreboard_folder_is_separate_from_other_buckets(isolated_files_dir, client):
    """`Files/Scoreboard/` holds scoreboard JSON files — they are
    NOT .bighat archives, so they don't go into Other/ and they don't
    mix with the round library. The folder exists and resolves on its
    own slug."""
    files_dir, _ = isolated_files_dir
    (files_dir / "Scoreboard").mkdir(exist_ok=True)
    (files_dir / "Scoreboard" / "2026-06-28-mainstreet.json").write_text("{}")

    r = client.get("/api/native/files?folder=Scoreboard")
    assert r.status_code == 200
    body = r.json()
    assert body["selected_folder"] == "Scoreboard"
