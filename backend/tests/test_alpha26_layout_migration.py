"""Alpha.26 file-store layout migration tests.

Covers three behaviours that the merchant signed off on for alpha.26:

  1. The legacy `Files/Rounds/` directory is renamed to `Files/Trivia/`
     on first launch after upgrade, with every .bighat round file
     bucketed into the right `MC/`/`REG/`/`MISC/`/`MYS/`/`BIG/`
     subdirectory by inspecting the archive's `round_type`.

  2. `_resolve_folder` accepts BOTH the top-level `Trivia` form and
     the round-type-specific `Trivia/MC` (or `Trivia-MC`) form so
     Build Wizard / Round Roulette can request scoped scans without
     reaching past the API.

  3. Uploads honour the same bucketing on the way in — a fresh `.bighat`
     posted to `/upload` lands in the correct round-type subfolder
     automatically based on its manifest.

Both migrations are guarded by marker files so they only run once;
the tests use `BIGHAT_FILES_DIR` to point the router at a temp tree
and the markers stay scoped to each test run.
"""
from __future__ import annotations

import io
import json
import os
import zipfile
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def isolated_files_dir(tmp_path, monkeypatch):
    """Point the native files router at a tmp directory so we never
    touch real `~/Documents/BIG Hat Entertainment/`."""
    files_dir = tmp_path / "files"
    files_dir.mkdir()
    monkeypatch.setenv("BIGHAT_FILES_DIR", str(files_dir))
    # files_router caches nothing — but force a re-import in case
    # other tests stashed a module-level binding.
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


def _make_bighat(round_type: str | None, content_type: str = "round") -> bytes:
    """Construct a minimal .bighat archive for testing."""
    buf = io.BytesIO()
    manifest = {"format": "bighat", "version": 2, "type": content_type}
    if round_type:
        manifest["round_type"] = round_type
        manifest["round_name"] = f"Test {round_type}"
    payload = {"name": f"Test {round_type or content_type}", "type": content_type}
    if round_type:
        payload["round_type"] = round_type
        payload["questions"] = [{"n": 1, "prompt": "q?", "answer": "a"}]
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest))
        zf.writestr("payload.json", json.dumps(payload))
    return buf.getvalue()


def test_legacy_rounds_dir_renamed_to_trivia(isolated_files_dir, client):
    """A pre-alpha.26 install has `Files/Rounds/*.bighat` (all round
    types lumped together). After the migration runs, the `Rounds/`
    directory is gone and every file lives in `Files/Trivia/<type>/`."""
    files_dir, files_router = isolated_files_dir
    legacy_rounds = files_dir / "Rounds"
    legacy_rounds.mkdir()
    (legacy_rounds / "mc-round.bighat").write_bytes(_make_bighat("MC"))
    (legacy_rounds / "reg-round.bighat").write_bytes(_make_bighat("REG"))
    (legacy_rounds / "untyped.bighat").write_bytes(_make_bighat(None, "round"))

    # Trigger migration via the list endpoint.
    r = client.get("/api/native/files")
    assert r.status_code == 200

    assert not legacy_rounds.exists(), "legacy Rounds/ should be removed"
    assert (files_dir / "Trivia" / "MC" / "mc-round.bighat").is_file()
    assert (files_dir / "Trivia" / "REG" / "reg-round.bighat").is_file()
    # Untyped round → catchall bucket.
    assert (files_dir / "Trivia" / "_Other" / "untyped.bighat").is_file()


def test_resolve_folder_handles_trivia_round_type_buckets(isolated_files_dir, client):
    """`?folder=Trivia/MC` should list only the MC bucket; the slash-
    less `Trivia-MC` form is also accepted for URL-friendliness."""
    files_dir, _ = isolated_files_dir
    (files_dir / "Trivia" / "MC").mkdir(parents=True)
    (files_dir / "Trivia" / "REG").mkdir(parents=True)
    (files_dir / "Trivia" / "MC" / "a.bighat").write_bytes(_make_bighat("MC"))
    (files_dir / "Trivia" / "MC" / "b.bighat").write_bytes(_make_bighat("MC"))
    (files_dir / "Trivia" / "REG" / "c.bighat").write_bytes(_make_bighat("REG"))

    r = client.get("/api/native/files?folder=Trivia/MC")
    body = r.json()
    assert body["selected_folder"] == "Trivia/MC"
    assert body["count"] == 2
    assert {f["name"] for f in body["files"]} == {"a.bighat", "b.bighat"}

    r2 = client.get("/api/native/files?folder=Trivia-MC")
    assert r2.json()["count"] == 2

    r3 = client.get("/api/native/files?folder=Trivia/REG")
    assert r3.json()["count"] == 1


def test_resolve_folder_trivia_top_level_aggregates_all_round_types(isolated_files_dir, client):
    """`?folder=Trivia` (without a round-type suffix) should aggregate
    every round file across every round-type bucket. Used by the
    'browse all trivia rounds' view in the file picker."""
    files_dir, _ = isolated_files_dir
    (files_dir / "Trivia" / "MC").mkdir(parents=True)
    (files_dir / "Trivia" / "REG").mkdir(parents=True)
    (files_dir / "Trivia" / "BIG").mkdir(parents=True)
    (files_dir / "Trivia" / "MC" / "m.bighat").write_bytes(_make_bighat("MC"))
    (files_dir / "Trivia" / "REG" / "r.bighat").write_bytes(_make_bighat("REG"))
    (files_dir / "Trivia" / "BIG" / "b.bighat").write_bytes(_make_bighat("BIG"))

    r = client.get("/api/native/files?folder=Trivia")
    body = r.json()
    assert body["count"] == 3
    folders = {f["folder"] for f in body["files"]}
    assert folders == {"Trivia/MC", "Trivia/REG", "Trivia/BIG"}


def test_invalid_round_type_bucket_rejected(client):
    """Don't let raw input walk us into an arbitrary path under
    Trivia/. Only the known TRIVIA_ROUND_TYPES + the `_Other` catchall
    are accepted as bucket names."""
    r = client.get("/api/native/files?folder=Trivia/PWNED")
    assert r.status_code == 400


def test_upload_routes_round_bighat_to_correct_round_type_bucket(isolated_files_dir, client):
    """Uploading a fresh .bighat with `round_type=MISC` lands it in
    `Files/Trivia/MISC/`, not the top-level Trivia/ or _Other."""
    files_dir, _ = isolated_files_dir
    payload = _make_bighat("MISC")
    r = client.post(
        "/api/native/files/upload",
        files={"file": ("imported.bighat", payload, "application/x-bighat")},
    )
    assert r.status_code == 200, r.text
    assert r.json()["folder"] == "Trivia/MISC"
    assert (files_dir / "Trivia" / "MISC" / "imported.bighat").is_file()


def test_upload_routes_unknown_round_type_to_other_bucket(isolated_files_dir, client):
    """A round .bighat with a round_type the app doesn't recognise
    (e.g. an experimental future round type) goes to `_Other/` so the
    merchant can still see it and re-classify manually if needed."""
    files_dir, _ = isolated_files_dir
    payload = _make_bighat("LIGHTNING")  # not in TRIVIA_ROUND_TYPES
    r = client.post(
        "/api/native/files/upload",
        files={"file": ("future.bighat", payload, "application/x-bighat")},
    )
    assert r.status_code == 200
    assert r.json()["folder"] == "Trivia/_Other"
    assert (files_dir / "Trivia" / "_Other" / "future.bighat").is_file()


def test_upload_bingo_bighat_lands_in_bingo_folder_not_trivia(isolated_files_dir, client):
    """Non-trivia content types still flow to their own top-level
    subfolders unchanged — the round-type bucketing only applies to
    trivia content."""
    files_dir, _ = isolated_files_dir
    payload = _make_bighat(None, content_type="bingo")
    r = client.post(
        "/api/native/files/upload",
        files={"file": ("game-1.bighat", payload, "application/x-bighat")},
    )
    assert r.status_code == 200
    assert r.json()["folder"] == "Bingo"
    assert (files_dir / "Bingo" / "game-1.bighat").is_file()
    # And specifically NOT in Trivia/.
    assert not list((files_dir / "Trivia").rglob("game-1.bighat"))


def test_migration_is_idempotent(isolated_files_dir, client):
    """Calling the list endpoint a second time after migration must
    not re-shuffle anything (guarded by the marker file)."""
    files_dir, _ = isolated_files_dir
    (files_dir / "Rounds").mkdir()
    (files_dir / "Rounds" / "stable.bighat").write_bytes(_make_bighat("MC"))

    client.get("/api/native/files")
    first_mtime = (files_dir / "Trivia" / "MC" / "stable.bighat").stat().st_mtime

    # A second invocation: the marker should short-circuit migration.
    client.get("/api/native/files")
    second_mtime = (files_dir / "Trivia" / "MC" / "stable.bighat").stat().st_mtime
    assert first_mtime == second_mtime, "file was unexpectedly touched on re-list"


def test_folder_endpoint_exposes_round_types_to_frontend(client):
    """Build Wizard + Round Roulette use `/folder` to discover which
    round-type sub-buckets to scan when assembling presentations."""
    r = client.get("/api/native/files/folder")
    body = r.json()
    assert body["ok"] is True
    # alpha.27 added Hosts/Locations/Scoreboard alongside the original
    # content-type folders. Assert the trivia-related entries exist
    # without locking the test to the exact set (so future additions
    # like "Music" or "Polls" don't have to update this assertion).
    assert {"Trivia", "Bingo", "Karaoke", "Other"} <= set(body["subfolders"])
    assert set(body["trivia_round_types"]) == {"MC", "REG", "MISC", "MYS", "BIG"}


def test_backups_dir_uses_spaced_canonical_brand_name(monkeypatch):
    """alpha.26 changed the backups root from `BIGHat Entertainment`
    (no space) to `BIG Hat Entertainment` (with space) to match the
    productName everywhere else in the app. Guard against an
    accidental revert."""
    monkeypatch.delenv("BIGHAT_BACKUPS_DIR", raising=False)
    from backend.native import backup_service
    p = backup_service.default_backups_dir()
    assert p.name == "Backups"
    assert p.parent.name == "BIG Hat Entertainment", (
        f"backups landed under {p.parent.name!r}, expected 'BIG Hat Entertainment'"
    )
