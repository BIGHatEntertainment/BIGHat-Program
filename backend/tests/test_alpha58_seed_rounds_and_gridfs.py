"""v32.0.0-alpha.58 — ship pre-embedded seed rounds; MontyDB GridFS short-circuit.

Merchant directives (verbatim intent):
  * Disk remains the source of truth — render-time resolution UNCHANGED.
  * `_extract_gridfs_covers_to_disk()` must short-circuit under standalone
    MontyDB with {'skipped': True, 'reason': 'native_mode_no_gridfs'}.
  * Seed .bighat files bundled with the installer MUST carry their cover
    image bytes embedded (`cover_image_data_url`) — a fresh install has
    no uploads dir, no GridFS, no assets library to recover from.
  * First-boot seeding NEVER overwrites an existing user file.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_gridfs_extract_short_circuits_on_montydb(monkeypatch):
    import routes.roundmaker as rm
    from native.async_monty import AsyncMontyDatabase

    class _Fake(AsyncMontyDatabase):
        def __init__(self):  # skip real Monty init
            pass

    monkeypatch.setattr(rm, "db", _Fake())
    out = asyncio.get_event_loop().run_until_complete(
        rm._extract_gridfs_covers_to_disk())
    assert out == {"skipped": True, "reason": "native_mode_no_gridfs"}


def test_gridfs_extract_skips_when_db_missing(monkeypatch):
    import routes.roundmaker as rm
    monkeypatch.setattr(rm, "db", None)
    out = asyncio.get_event_loop().run_until_complete(
        rm._extract_gridfs_covers_to_disk())
    assert out == {"skipped": True, "reason": "db_not_ready"}


def test_repo_seed_rounds_are_self_contained():
    seed = Path(__file__).resolve().parents[1] / "seed_rounds"
    files = sorted(seed.rglob("*.bighat"))
    assert files, "seed_rounds/ must ship at least one round"
    for f in files:
        doc = json.loads(f.read_text(encoding="utf-8"))
        assert doc.get("cover_image_data_url", "").startswith("data:image/"), \
            f"{f.name} is not self-contained"
        assert len(doc.get("questions") or []) >= 1


def test_launcher_seeds_without_overwriting(tmp_path, monkeypatch):
    import launcher
    docs = tmp_path / "docs"
    monkeypatch.setenv("BIGHAT_FILES_DIR", str(docs))
    # Pre-existing user file must NOT be overwritten.
    seed_src = Path(launcher.BACKEND_DIR) / "seed_rounds"
    first = sorted(seed_src.rglob("*.bighat"))[0]
    rtype = first.parent.name
    user_file = docs / "Files" / "Trivia" / rtype / first.name
    user_file.parent.mkdir(parents=True)
    user_file.write_text('{"id": "user-owned"}', encoding="utf-8")

    launcher._seed_bundled_rounds()

    assert json.loads(user_file.read_text())["id"] == "user-owned"
    seeded = [p for p in (docs / "Files" / "Trivia").rglob("*.bighat")
              if p != user_file]
    assert len(seeded) == len(list(seed_src.rglob("*.bighat"))) - 1
    for p in seeded:
        assert json.loads(p.read_text())["cover_image_data_url"].startswith("data:image/")
