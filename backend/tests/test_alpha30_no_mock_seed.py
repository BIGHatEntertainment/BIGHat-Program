"""v32.0.0-alpha.30 regression suite — proves:

  1. The cloud `seed_data()` no longer inserts the mock employee roster
     (Alex Rivera, Jordan Blake, Casey Morgan, Taylor Reed) or any of
     the six fake venues / four-weeks-of-events seed.

  2. `write_host_profile_json()` writes a sanitised host.json blob into
     `BIG Hat Entertainment/Files/Hosts/<slug>/` with the full profile
     payload and NEVER leaks `password_hash`.

  3. The slug derived from an email never contains path separators.

Run with: pytest backend/tests/test_alpha30_no_mock_seed.py -v
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


# ---------------------------------------------------------------------
# (1) Mock seed data is gone from server.py
# ---------------------------------------------------------------------
def test_server_py_has_no_mock_employee_roster():
    """The fake host roster + fake venues + recurring events seed must
    be stripped. We grep the source file directly because the seed lives
    inside an async startup hook that is non-trivial to invoke from a
    sync pytest."""
    src = Path("/app/backend/server.py").read_text(encoding="utf-8")
    forbidden = [
        '"Alex Rivera"',
        '"Jordan Blake"',
        '"Casey Morgan"',
        '"Taylor Reed"',
        '"The Tap House"',
        '"Rusty Nail Bar"',
        '"Desert Ridge Tavern"',
        '"Cactus Jack\'s"',
        '"The Pint House"',
        '"Copper Blues"',
        '"Tuesday Trivia Night"',
        '"Wednesday Bingo Bash"',
        '"Thursday Trivia"',
        '"Friday Night Karaoke"',
        '"Saturday Bingo Bonanza"',
        '"Sunday Funday Trivia"',
    ]
    leaks = [s for s in forbidden if s in src]
    assert not leaks, f"Mock seed data still present in server.py: {leaks}"


def test_server_py_still_seeds_env_driven_master_admin():
    """We intentionally KEEP the env-gated Nick Sellards master_admin
    row — it's used by the cloud SaaS hub. Make sure the refactor
    didn't accidentally delete it too."""
    src = Path("/app/backend/server.py").read_text(encoding="utf-8")
    assert 'ADMIN_EMAIL' in src
    assert '"master_admin"' in src
    assert 'Nick Sellards' in src


# ---------------------------------------------------------------------
# (2) host.json writer round-trips the full profile
# ---------------------------------------------------------------------
@pytest.fixture
def host_recall_sandbox(tmp_path, monkeypatch):
    """Point the files_router at a throw-away Documents folder so the
    test doesn't touch the dev box's real BIG Hat Entertainment tree."""
    docs = tmp_path / "Documents"
    docs.mkdir()
    monkeypatch.setenv("BIGHAT_DOCS_OVERRIDE", str(docs))
    # The router caches its base root by env probe at call time, so as
    # long as we set the override BEFORE importing the writer we're OK.
    import importlib
    import native.files_router as fr  # type: ignore
    importlib.reload(fr)
    yield fr, docs


def test_write_host_profile_json_persists_full_profile(host_recall_sandbox):
    fr, docs = host_recall_sandbox
    user = {
        "id": "user-001",
        "email": "Sellards@BigHat.Live",  # mixed case → must lowercase
        "first_name": "Nick",
        "last_name": "Sellards",
        "display_name": "Nick Sellards",
        "phone": "+1-602-555-0100",
        "role": "master_admin",
        "home_city": "Phoenix, AZ",
        "profile_picture": "/api/native/files/raw/Hosts/sellards@bighat.live/avatar.png",
        "host_image_16x9": "/api/native/files/raw/Hosts/sellards@bighat.live/loop_16x9.gif",
        "host_image_9x16": "/api/native/files/raw/Hosts/sellards@bighat.live/loop_9x16.gif",
        "created_at": "2026-06-30T00:00:00+00:00",
        "password_hash": "$2b$12$NEVER_LEAK_THIS",  # must NOT appear on disk
    }
    out = fr.write_host_profile_json(user)
    assert out is not None
    assert out.exists()
    assert out.name == "host.json"
    # Folder slug = sanitised lowercased email
    assert out.parent.name == "sellards@bighat.live"

    blob = json.loads(out.read_text(encoding="utf-8"))
    # password_hash must NEVER make it to disk
    assert "password_hash" not in blob
    # Full profile present
    assert blob["email"] == "Sellards@BigHat.Live"  # raw value preserved
    assert blob["display_name"] == "Nick Sellards"
    assert blob["home_city"] == "Phoenix, AZ"
    assert blob["role"] == "master_admin"
    assert blob["profile_picture"].endswith("avatar.png")
    # Metadata stamped
    assert blob["_source"] == "bighat-native-host-recall"
    assert blob["_written_at"].startswith("20")


def test_write_host_profile_json_no_email_falls_back_to_id(host_recall_sandbox):
    fr, docs = host_recall_sandbox
    out = fr.write_host_profile_json({"id": "abc-123", "display_name": "Anon"})
    assert out is not None
    assert out.parent.name == "abc-123"


def test_write_host_profile_json_empty_user_is_noop(host_recall_sandbox):
    fr, docs = host_recall_sandbox
    assert fr.write_host_profile_json({}) is None
    assert fr.write_host_profile_json(None) is None  # type: ignore[arg-type]


# ---------------------------------------------------------------------
# (3) Slug sanitisation defends against directory traversal
# ---------------------------------------------------------------------
def test_host_slug_strips_path_separators(host_recall_sandbox):
    fr, _ = host_recall_sandbox
    # The dot-dot must collapse into a single safe character
    assert "/" not in fr.host_slug("../etc/passwd")
    assert "\\" not in fr.host_slug("..\\windows\\system32")
    assert fr.host_slug("") == ""
    assert fr.host_slug("   ") == ""
