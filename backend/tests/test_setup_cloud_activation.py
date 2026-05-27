"""Setup wizard's `/api/native/setup/initialize` now calls the cloud
license authority. Verify:

  1. Cloud success → setup completes, subscription mirrors cloud flags.
  2. Cloud 4xx (bad key)  → setup is rejected, no master admin written.
  3. Cloud transport error → setup completes with `pending_cloud_activation`
     set to True, master admin written, retry job will pick it up.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def fresh_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Reset the global ConfigManager to a fresh path so each test starts clean."""
    cfg_path = tmp_path / "system_config.json"
    monkeypatch.setenv("BIGHAT_CONFIG_PATH", str(cfg_path))
    monkeypatch.setenv("BIGHAT_NATIVE_MODE", "1")
    monkeypatch.setenv("BIGHAT_DATA_ROOT", str(tmp_path / "data"))

    from native import config as native_config
    mgr = native_config.config_manager
    saved_path, saved_cfg = mgr.config_path, mgr.config
    mgr.config_path = cfg_path
    mgr.config = native_config._default_config()
    try:
        yield mgr
    finally:
        mgr.config_path = saved_path
        mgr.config = saved_cfg


@pytest.fixture()
def client():
    # Import here so the env-var monkeypatch above is in effect first.
    os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
    os.environ.setdefault("DB_NAME", "test_database")
    os.environ.setdefault("BIGHAT_NATIVE_MODE", "1")
    from server import app
    return TestClient(app)


VALID_KEY = "BHE-AAAA-BBBB-CCCC-DDDD"

GOOD_PAYLOAD = {
    "license_key": VALID_KEY,
    "master_admin": {
        "email": "owner@customer.com",
        "password": "ownerpw",
        "first_name": "Olive",
        "last_name": "Owner",
    },
    "settings": {"location_name": "Main HQ", "state": "AZ", "trivia_source": "local"},
}


def test_cloud_success_completes_setup(fresh_config, client):
    cloud_resp = {
        "ok": True,
        "message": "activated",
        "owns_standalone": True,
        "owns_music_bingo": False,
        "owns_karaoke": False,
        "cloud_library_active": True,
        "cloud_library_expires_at": datetime.now(timezone.utc).isoformat(),
        "max_seats": 5,
        "active_seats": 1,
        "revalidate_after": datetime.now(timezone.utc).isoformat(),
    }
    with patch("native.router.cloud_client.activate",
               new_callable=AsyncMock, return_value=cloud_resp):
        r = client.post("/api/native/setup/initialize", json=GOOD_PAYLOAD)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ok"
    assert body["master_admin_email"] == "owner@customer.com"
    # Cloud flags mirrored into subscription
    sub = body["subscription"]
    assert sub["active"] is True
    assert sub["story_generator_enabled"] is True
    assert sub["sharepoint_enabled"] is True
    # No pending flag — cloud was authoritative.
    lic = body["license"]
    assert lic.get("pending_cloud_activation") in (False, None)


def test_cloud_4xx_rejects_setup(fresh_config, client):
    cloud_resp = {
        "ok": False, "error": "unknown_key", "status_code": 400,
        "message": "unknown_key",
    }
    with patch("native.router.cloud_client.activate",
               new_callable=AsyncMock, return_value=cloud_resp):
        r = client.post("/api/native/setup/initialize", json=GOOD_PAYLOAD)
    assert r.status_code == 400, r.text
    detail = r.json()["detail"]
    assert detail["error"] == "unknown_key"
    # Setup must NOT be marked complete on a bad cloud response.
    assert fresh_config.config.get("setup_complete") is False
    assert fresh_config.config.get("users") == []


def test_cloud_offline_completes_setup_with_pending_flag(fresh_config, client):
    cloud_resp = {"ok": False, "error": "network_error", "message": "no route"}
    with patch("native.router.cloud_client.activate",
               new_callable=AsyncMock, return_value=cloud_resp):
        r = client.post("/api/native/setup/initialize", json=GOOD_PAYLOAD)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ok"
    assert body["license"]["pending_cloud_activation"] is True
    # Master admin still written so the customer can log in offline.
    assert fresh_config.config["setup_complete"] is True
    assert fresh_config.config["users"][0]["email"] == "owner@customer.com"


def test_cloud_timeout_treated_as_offline(fresh_config, client):
    cloud_resp = {"ok": False, "error": "timeout", "message": "deadline"}
    with patch("native.router.cloud_client.activate",
               new_callable=AsyncMock, return_value=cloud_resp):
        r = client.post("/api/native/setup/initialize", json=GOOD_PAYLOAD)
    assert r.status_code == 200, r.text
    assert r.json()["license"]["pending_cloud_activation"] is True
