"""
Iteration 19 — Launcher persistence fix for PyInstaller-frozen builds.

ROOT CAUSE (covered by these tests):
  In frozen mode, BACKEND_DIR is a per-launch _MEIxxxx temp dir extracted by
  PyInstaller and wiped by Windows when the process exits. The launcher
  already pinned the DB / JWT_SECRET / admin passwords into USER_DATA_DIR
  (%LOCALAPPDATA%\\BIGHat\\data), but did NOT set BIGHAT_CONFIG_PATH or
  BIGHAT_DATA_ROOT — so `native.config.ConfigManager` wrote
  `system_config.json` (setup_complete=True, license key, master admin users,
  paths) into the temp _MEIxxxx dir. Every relaunch found no
  system_config.json → defaulted setup_complete=False → re-ran the Setup
  Wizard. Customers had to enter the key + reset password on every reopen.

FIX:
  launcher._load_env() now has an `if getattr(sys, "frozen", False):` block at
  the TOP that calls USER_DATA_DIR.mkdir(parents=True, exist_ok=True) and
  os.environ.setdefault for BIGHAT_CONFIG_PATH + BIGHAT_DATA_ROOT — BEFORE
  any native.* import. setdefault preserves explicit overrides.

These tests:
  1. FROZEN mode + no env -> launcher sets BIGHAT_CONFIG_PATH and
     BIGHAT_DATA_ROOT under USER_DATA_DIR.
  2. FROZEN mode + explicit env override -> launcher preserves it (setdefault).
  3. DEV mode (sys.frozen unset) -> launcher does NOT set those env vars.
  4. FROZEN mode -> USER_DATA_DIR is created on disk before env vars are set.
  5. END-TO-END persistence simulation: setup_complete=True survives a
     simulated process restart (ConfigManager reload).
"""
from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

import pytest


# Make `import launcher` and `import native.config` work.
sys.path.insert(0, "/app/backend")

import launcher  # noqa: E402


@pytest.fixture
def clean_env(monkeypatch):
    """Strip any pre-existing BIGHAT_CONFIG_PATH / BIGHAT_DATA_ROOT so tests
    are deterministic. Other env vars (MONGO_URL etc.) are scoped per-test
    via monkeypatch too, so the live FastAPI process is unaffected."""
    monkeypatch.delenv("BIGHAT_CONFIG_PATH", raising=False)
    monkeypatch.delenv("BIGHAT_DATA_ROOT", raising=False)
    return monkeypatch


@pytest.fixture
def temp_user_data_dir(tmp_path, monkeypatch):
    """Point launcher.USER_DATA_DIR at a hermetic tmp path so we never touch
    the real %LOCALAPPDATA% / ~/.local/share. Returns the tmp path."""
    udd = tmp_path / "BIGHat" / "data"
    # Note: USER_DATA_DIR is referenced as `USER_DATA_DIR` inside
    # launcher._load_env() (module global), so patching the attribute is
    # sufficient.
    monkeypatch.setattr(launcher, "USER_DATA_DIR", udd, raising=True)
    return udd


@pytest.fixture
def frozen(monkeypatch):
    """Simulate PyInstaller-frozen mode."""
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    yield
    # monkeypatch automatically restores; nothing else to do.


# ---------------------------------------------------------------------------
# 1. FROZEN mode + clean env -> launcher sets both env vars under USER_DATA_DIR
# ---------------------------------------------------------------------------
class TestFrozenSetsConfigEnv:
    def test_sets_bighat_config_path(self, frozen, clean_env, temp_user_data_dir):
        launcher._load_env()
        assert os.environ.get("BIGHAT_CONFIG_PATH") == str(
            temp_user_data_dir / "system_config.json"
        )

    def test_sets_bighat_data_root(self, frozen, clean_env, temp_user_data_dir):
        launcher._load_env()
        assert os.environ.get("BIGHAT_DATA_ROOT") == str(temp_user_data_dir / "app")

    def test_config_path_is_outside_backend_dir(
        self, frozen, clean_env, temp_user_data_dir
    ):
        """The whole point of the fix: config must NOT land in BACKEND_DIR
        (which is _MEIxxxx in frozen mode and gets wiped on close)."""
        launcher._load_env()
        cfg_path = Path(os.environ["BIGHAT_CONFIG_PATH"])
        assert not str(cfg_path).startswith(str(launcher.BACKEND_DIR))
        assert str(cfg_path).startswith(str(temp_user_data_dir))


# ---------------------------------------------------------------------------
# 2. FROZEN mode + explicit override -> launcher preserves it (setdefault)
# ---------------------------------------------------------------------------
class TestFrozenRespectsOverride:
    def test_explicit_config_path_wins(
        self, frozen, clean_env, temp_user_data_dir, tmp_path
    ):
        override = tmp_path / "custom" / "my_config.json"
        clean_env.setenv("BIGHAT_CONFIG_PATH", str(override))
        launcher._load_env()
        assert os.environ["BIGHAT_CONFIG_PATH"] == str(override)

    def test_explicit_data_root_wins(
        self, frozen, clean_env, temp_user_data_dir, tmp_path
    ):
        override = tmp_path / "custom" / "data"
        clean_env.setenv("BIGHAT_DATA_ROOT", str(override))
        launcher._load_env()
        assert os.environ["BIGHAT_DATA_ROOT"] == str(override)

    def test_partial_override_other_var_still_defaulted(
        self, frozen, clean_env, temp_user_data_dir, tmp_path
    ):
        """Overriding only ONE of the two env vars must still default the
        other to USER_DATA_DIR (setdefault is per-key)."""
        override_cfg = tmp_path / "only_cfg.json"
        clean_env.setenv("BIGHAT_CONFIG_PATH", str(override_cfg))
        launcher._load_env()
        assert os.environ["BIGHAT_CONFIG_PATH"] == str(override_cfg)
        assert os.environ["BIGHAT_DATA_ROOT"] == str(temp_user_data_dir / "app")


# ---------------------------------------------------------------------------
# 3. DEV mode -> launcher MUST NOT set those env vars
# ---------------------------------------------------------------------------
class TestDevModeUnchanged:
    def test_dev_mode_does_not_set_config_path(
        self, clean_env, temp_user_data_dir, monkeypatch
    ):
        # Ensure sys.frozen is False/absent.
        monkeypatch.delattr(sys, "frozen", raising=False)
        launcher._load_env()
        assert "BIGHAT_CONFIG_PATH" not in os.environ

    def test_dev_mode_does_not_set_data_root(
        self, clean_env, temp_user_data_dir, monkeypatch
    ):
        monkeypatch.delattr(sys, "frozen", raising=False)
        launcher._load_env()
        assert "BIGHAT_DATA_ROOT" not in os.environ

    def test_dev_mode_sys_frozen_false_explicit(
        self, clean_env, temp_user_data_dir, monkeypatch
    ):
        """sys.frozen explicitly False (not just absent) is also dev mode."""
        monkeypatch.setattr(sys, "frozen", False, raising=False)
        launcher._load_env()
        assert "BIGHAT_CONFIG_PATH" not in os.environ
        assert "BIGHAT_DATA_ROOT" not in os.environ


# ---------------------------------------------------------------------------
# 4. FROZEN mode -> USER_DATA_DIR is created BEFORE env vars are set
# ---------------------------------------------------------------------------
class TestUserDataDirCreated:
    def test_user_data_dir_created_in_frozen_mode(
        self, frozen, clean_env, temp_user_data_dir
    ):
        assert not temp_user_data_dir.exists()  # sanity: starts fresh
        launcher._load_env()
        assert temp_user_data_dir.is_dir(), (
            "USER_DATA_DIR must be created on disk before BIGHAT_CONFIG_PATH "
            "is exported — otherwise ConfigManager.save_config() would race "
            "with the directory not existing."
        )

    def test_config_path_parent_writable(
        self, frozen, clean_env, temp_user_data_dir
    ):
        """The parent of BIGHAT_CONFIG_PATH must exist and be writable so
        ConfigManager's atomic write (tempfile.mkstemp + os.replace) works."""
        launcher._load_env()
        cfg_path = Path(os.environ["BIGHAT_CONFIG_PATH"])
        assert cfg_path.parent.is_dir()
        # Smoke-test write
        probe = cfg_path.parent / ".probe"
        probe.write_text("ok", encoding="utf-8")
        assert probe.read_text(encoding="utf-8") == "ok"
        probe.unlink()


# ---------------------------------------------------------------------------
# 5. END-TO-END: setup persists across a simulated process restart
# ---------------------------------------------------------------------------
class TestEndToEndPersistence:
    """Simulate the exact customer scenario:
        1. App launches frozen, fresh USER_DATA_DIR with NO system_config.json.
        2. User completes Setup Wizard -> setup_complete=True saved.
        3. App closes (PyInstaller wipes _MEIxxxx).
        4. App relaunches -> ConfigManager reads from USER_DATA_DIR ->
           setup_complete=True, same instance_id -> Setup Wizard does NOT run.
    """

    def test_setup_state_survives_restart(
        self, frozen, clean_env, temp_user_data_dir
    ):
        # ----- LAUNCH 1: fresh install -----
        launcher._load_env()
        cfg_path = Path(os.environ["BIGHAT_CONFIG_PATH"])
        assert not cfg_path.exists(), "must start with no system_config.json"

        # Import ConfigManager AFTER env is set so DEFAULT_CONFIG_PATH picks
        # up the new value.
        import native.config as native_config
        importlib.reload(native_config)

        cm1 = native_config.ConfigManager()
        assert cm1.is_setup_required() is True
        assert cm1.config["setup_complete"] is False
        original_instance_id = cm1.config["instance_id"]

        # Simulate Setup Wizard completion.
        cm1.save_config(
            {
                "setup_complete": True,
                "license_status": {
                    "key": "TEST-LICENSE-KEY-IT19",
                    "master_admin_email": "owner@example.com",
                    "is_active": True,
                },
                "users": [
                    {
                        "email": "owner@example.com",
                        "role": "master_admin",
                        "password_hash": "$2b$12$dummybcrypthashforiter19xxxxxxxxxxxxxxx",
                    }
                ],
            }
        )

        # File must exist on disk in USER_DATA_DIR (NOT BACKEND_DIR).
        assert cfg_path.is_file()
        assert cfg_path.parent == temp_user_data_dir

        # ----- SIMULATE PROCESS EXIT + RELAUNCH -----
        # Critical: in real frozen mode BACKEND_DIR (_MEIxxxx) would be gone
        # here. We delete the in-memory references and reload native.config
        # from scratch so it re-reads DEFAULT_CONFIG_PATH from env.
        del cm1
        importlib.reload(native_config)

        cm2 = native_config.ConfigManager()
        # THE FIX: setup state must have survived.
        assert cm2.is_setup_required() is False, (
            "Setup Wizard would re-run on relaunch — fix is NOT working. "
            "Either BIGHAT_CONFIG_PATH wasn't exported before ConfigManager "
            "import, or it points outside USER_DATA_DIR."
        )
        assert cm2.config["setup_complete"] is True
        assert cm2.config["instance_id"] == original_instance_id, (
            "instance_id changed across restart — config wasn't loaded from "
            "disk, defaults were regenerated."
        )
        assert cm2.config["license_status"]["key"] == "TEST-LICENSE-KEY-IT19"
        assert (
            cm2.config["license_status"]["master_admin_email"]
            == "owner@example.com"
        )
        assert len(cm2.config["users"]) == 1
        assert cm2.config["users"][0]["email"] == "owner@example.com"

    def test_paths_under_data_root_use_user_data_dir(
        self, frozen, clean_env, temp_user_data_dir
    ):
        """paths.data_root + paths.local_trivia / assets / generated must
        default under USER_DATA_DIR/app — not BACKEND_DIR — so generated
        bundles, trivia packs, etc. persist across launches too."""
        launcher._load_env()
        import native.config as native_config
        importlib.reload(native_config)

        cm = native_config.ConfigManager()
        paths = cm.config["paths"]
        expected_root = str(temp_user_data_dir / "app")
        assert paths["data_root"] == expected_root
        for key in ("local_trivia", "assets", "generated"):
            assert paths[key].startswith(expected_root), (
                f"paths.{key}={paths[key]!r} is NOT under USER_DATA_DIR/app; "
                "would not survive _MEIxxxx wipe."
            )


# ---------------------------------------------------------------------------
# 6. Static check: PRD documents the invariant
# ---------------------------------------------------------------------------
class TestPRDDocumentation:
    def test_prd_contains_new_section(self):
        prd = Path("/app/memory/PRD.md")
        assert prd.is_file(), "PRD.md missing"
        text = prd.read_text(encoding="utf-8")
        assert (
            "INSTALLER STATE MUST PERSIST IN USER_DATA_DIR — NEVER IN _MEIxxxx"
            in text
        ), "PRD must document the persistence invariant for future agents."


# ---------------------------------------------------------------------------
# 7. Live backend health (sanity that hot-reload didn't break the dev server)
# ---------------------------------------------------------------------------
class TestBackendHealthy:
    def test_api_root_200(self):
        import requests
        base = os.environ.get("REACT_APP_BACKEND_URL")
        if not base:
            # Fallback: read from frontend/.env
            for line in Path("/app/frontend/.env").read_text().splitlines():
                if line.startswith("REACT_APP_BACKEND_URL="):
                    base = line.split("=", 1)[1].strip()
                    break
        assert base, "REACT_APP_BACKEND_URL not set"
        r = requests.get(f"{base.rstrip('/')}/api/", timeout=10)
        assert r.status_code == 200, r.text
