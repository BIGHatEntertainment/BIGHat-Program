"""v32.0.0-alpha.35 — kill the `admin@example.com` phantom master admin.

Merchant report on alpha.34:
  After completing setup with email `sellards@bighat.live`, the admin
  panel Users tab showed TWO master admins — the one they just created
  AND a bogus `admin@example.com` / "Nick Sellards" row.

  Requirement: exactly ONE master admin per install (the one from setup).
  Additional admins are OK; extra MASTER admins are never OK.

Root cause: `server.py :: seed_data()` fell back to
  ADMIN_EMAIL=admin@example.com when the env var wasn't set. That seed
  ran unconditionally on every boot — including on standalone native
  installs where the setup wizard is the sole authority.

Fixes locked in by this test suite:
  1. `seed_data()` short-circuits when running in native mode.
  2. `seed_data()` refuses to seed `admin@example.com` / placeholder emails
     even in cloud mode when the env is missing.
  3. Boot-time invariant scrubs `admin@example.com` from `db.users` on
     every native start so upgrades from alpha.31..34 self-heal.
  4. `list_users` prunes `db.users` rows whose email is NOT present in
     `system_config.json → users[]` so the wizard's user list stays
     locked to the authoritative source.
"""
from __future__ import annotations
from pathlib import Path


SERVER = Path("/app/backend/server.py").read_text()


def test_seed_short_circuits_in_native_mode():
    idx = SERVER.index("async def seed_data(")
    end = SERVER.index("@asynccontextmanager", idx)
    body = SERVER[idx:end]
    assert "is_native" in body, (
        "seed_data() must import is_native() and skip when True"
    )
    assert "skipping cloud env master_admin seed" in body


def test_seed_refuses_placeholder_admin_email():
    idx = SERVER.index("async def seed_data(")
    end = SERVER.index("@asynccontextmanager", idx)
    body = SERVER[idx:end]
    assert '"admin@example.com"' in body
    assert "placeholder admin email" in body
    # And the fallback default must be gone — used to be
    # os.environ.get("ADMIN_EMAIL", "admin@example.com").
    assert 'os.environ.get("ADMIN_EMAIL")' in body
    assert 'os.environ.get("ADMIN_EMAIL", "admin@example.com")' not in body


def test_boot_time_purge_and_invariant_present():
    # Both should live inside the lifespan context manager.
    idx = SERVER.index("@asynccontextmanager")
    end = SERVER.index("app = FastAPI(", idx) if "app = FastAPI(" in SERVER[idx:] else idx + 8000
    body = SERVER[idx:end]
    assert "boot-purge" in body, "startup must purge legacy admin@example.com"
    assert "boot-invariant" in body, "startup must enforce one master_admin"
    assert "master_admin" in body


def test_list_users_prunes_rows_outside_config():
    src = SERVER
    idx = src.index("async def list_users(")
    end = src.index("@api_router", idx + 1)
    body = src[idx:end]
    assert "pruned" in body or "$nin" in body, (
        "list_users must prune db.users rows not in system_config.users[]"
    )
    assert "allowed_emails" in body


def test_no_placeholder_default_arg_remains():
    """The old bug was `os.environ.get("ADMIN_EMAIL", "admin@example.com")`
    supplying a default that seeded a bogus row on every dev box. That
    exact call site must never come back."""
    txt = SERVER
    assert 'os.environ.get("ADMIN_EMAIL", "admin@example.com")' not in txt
    assert "'ADMIN_EMAIL', 'admin@example.com'" not in txt
    # Also make sure the "admin123" fallback default is gone.
    assert 'os.environ.get("ADMIN_PASSWORD", "admin123")' not in txt
