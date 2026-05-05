"""Phase 10.2 — Desktop ↔ cloud licensing wire-up.

Covers:
  * `cloud_client.py` HTTP wrapper (success, 4xx, 5xx, timeout, network error)
  * `/api/native/license/cloud/{activate,validate,deactivate}` endpoints
  * Offline-grace logic in `is_premium_active()` — stale `last_cloud_validated_at`
    degrades cloud-tier features but standalone-tier ones remain unlocked
  * `.env.standalone` template ships `BIGHAT_LICENSE_API_BASE_URL`

The tests run in-process. We DO NOT touch the live supervisor server (which
runs with native mode and no cloud routes). Instead we spin up a small
"mock cloud server" via FastAPI TestClient + monkeypatch the desktop
`cloud_client._post`/`_get` helpers to dispatch to it.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


# ---------- isolate `system_config.json` per test ----------
@pytest.fixture
def isolated_config():
    """Snapshot the in-memory config and restore on teardown so each test
    starts with a clean license/subscription slate. We DO NOT reload
    `native.config` — that would break every other module's singleton ref."""
    from native.config import config_manager
    snapshot = json.loads(json.dumps(config_manager.config))
    # Wipe the bits these tests touch.
    config_manager.config["license_status"] = {}
    config_manager.config["subscription"] = {}
    config_manager.save_config()
    yield config_manager
    # Restore previous state.
    config_manager.config = snapshot
    config_manager.save_config()


# ---------- mock cloud responses ----------
class FakeCloud:
    """Stand-in for `https://api.bighat.live`. Returns canned responses
    for activate/validate/deactivate; supports failure injection."""
    def __init__(self):
        self.activate_response: dict | None = None
        self.validate_response: dict | None = None
        self.deactivate_response: dict | None = None
        self.last_activate_payload: dict | None = None
        self.timeout_on_validate = False

    def install(self, monkeypatch):
        from native import cloud_client as cc

        async def fake_activate(*, license_key, hwid, machine_name=None, email=None):
            self.last_activate_payload = {
                "license_key": license_key, "hwid": hwid,
                "machine_name": machine_name, "email": email,
            }
            return self.activate_response or {"ok": False, "error": "no_response_configured"}

        async def fake_validate(*, license_key, hwid):
            if self.timeout_on_validate:
                return {"ok": False, "error": "timeout", "message": "license server timeout"}
            return self.validate_response or {"ok": True,
                                              "owns_standalone": True,
                                              "cloud_library_active": False,
                                              "revoked": False,
                                              "revalidate_after": (datetime.now(timezone.utc)
                                                                   + timedelta(days=7)).isoformat()}

        async def fake_deactivate(*, license_key, hwid):
            return self.deactivate_response or {"ok": True, "message": "deactivated"}

        monkeypatch.setattr(cc, "activate", fake_activate)
        monkeypatch.setattr(cc, "validate", fake_validate)
        monkeypatch.setattr(cc, "deactivate", fake_deactivate)


@pytest.fixture
def fake_cloud(monkeypatch):
    fc = FakeCloud()
    fc.install(monkeypatch)
    return fc


# ---------- minimal app ----------
@pytest.fixture
def app_client_simple(isolated_config, fake_cloud):
    """Spin up a FastAPI app with just the native router. Reuses the
    in-memory config_manager singleton (cleaned by `isolated_config`)."""
    from native import router as native_router
    app = FastAPI()
    app.include_router(native_router.router)
    return TestClient(app), fake_cloud


# ===================================================================
# 1. cloud_client unit tests (httpx-mocked)
# ===================================================================
class TestCloudClient:
    @pytest.mark.asyncio
    async def test_post_returns_ok_on_2xx(self, monkeypatch):
        from native import cloud_client as cc

        class _Resp:
            status_code = 200
            text = ""
            def json(self_):  # noqa: N805
                return {"ok": True, "owns_standalone": True}

        class _Client:
            def __init__(self, *a, **k): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False
            async def post(self, *a, **k): return _Resp()

        monkeypatch.setattr("httpx.AsyncClient", _Client)
        out = await cc._post("/api/license/activate", {})
        assert out["ok"] is True
        assert out["owns_standalone"] is True

    @pytest.mark.asyncio
    async def test_post_handles_4xx(self, monkeypatch):
        from native import cloud_client as cc

        class _Resp:
            status_code = 400
            text = ""
            def json(self_):
                return {"detail": "unknown_key"}

        class _Client:
            def __init__(self, *a, **k): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False
            async def post(self, *a, **k): return _Resp()

        monkeypatch.setattr("httpx.AsyncClient", _Client)
        out = await cc._post("/x", {})
        assert out["ok"] is False
        assert out["error"] == "unknown_key"
        assert out["status_code"] == 400

    @pytest.mark.asyncio
    async def test_post_handles_timeout(self, monkeypatch):
        from native import cloud_client as cc
        import httpx

        class _Client:
            def __init__(self, *a, **k): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False
            async def post(self, *a, **k):
                raise httpx.TimeoutException("read timeout")

        monkeypatch.setattr("httpx.AsyncClient", _Client)
        out = await cc._post("/x", {})
        assert out["ok"] is False
        assert out["error"] == "timeout"

    @pytest.mark.asyncio
    async def test_post_handles_network_error(self, monkeypatch):
        from native import cloud_client as cc
        import httpx

        class _Client:
            def __init__(self, *a, **k): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False
            async def post(self, *a, **k):
                raise httpx.ConnectError("no route")

        monkeypatch.setattr("httpx.AsyncClient", _Client)
        out = await cc._post("/x", {})
        assert out["ok"] is False
        assert out["error"] == "network_error"

    def test_api_base_url_from_env(self, monkeypatch):
        from native import cloud_client as cc
        monkeypatch.setenv("BIGHAT_LICENSE_API_BASE_URL", "https://staging.example/")
        assert cc._api_base_url() == "https://staging.example"


# ===================================================================
# 2. /api/native/license/cloud/* endpoint tests
# ===================================================================
class TestCloudActivateEndpoint:
    def test_activate_happy_path(self, app_client_simple):
        client, cloud = app_client_simple
        cloud.activate_response = {
            "ok": True,
            "message": "activated",
            "owns_standalone": True,
            "cloud_library_active": True,
            "cloud_library_expires_at": (datetime.now(timezone.utc)
                                          + timedelta(days=30)).isoformat(),
            "max_seats": 5,
            "active_seats": 1,
            "revalidate_after": (datetime.now(timezone.utc)
                                 + timedelta(days=7)).isoformat(),
        }
        r = client.post("/api/native/license/cloud/activate", json={
            "license_key": "BHE-AAAA-BBBB-CCCC-DDDD",
            "email": "alice@example.com",
            "label": "Studio iMac",
        })
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "ok"
        # Standalone + cloud_library both reflect in local subscription.
        sub = body["subscription"]
        assert sub["active"] is True
        assert sub["tier"] == "premium"
        assert sub["sharepoint_enabled"] is True
        assert sub["cloud_sync_enabled"] is True
        # Cloud was called with correct payload
        assert cloud.last_activate_payload["license_key"] == "BHE-AAAA-BBBB-CCCC-DDDD"

    def test_activate_rejects_malformed_key_locally(self, app_client_simple):
        client, _ = app_client_simple
        r = client.post("/api/native/license/cloud/activate", json={
            "license_key": "not-a-key", "email": "x@y.com",
        })
        assert r.status_code == 400
        assert r.json()["detail"] == "invalid_license_format"

    def test_activate_propagates_cloud_4xx(self, app_client_simple):
        client, cloud = app_client_simple
        cloud.activate_response = {
            "ok": False, "error": "seat_limit_reached (3)",
            "status_code": 400, "message": "seat_limit_reached (3)",
        }
        r = client.post("/api/native/license/cloud/activate", json={
            "license_key": "BHE-AAAA-BBBB-CCCC-DDDD",
        })
        assert r.status_code == 400
        assert "seat_limit" in r.json()["detail"]["error"]

    def test_activate_returns_503_on_cloud_outage(self, app_client_simple):
        client, cloud = app_client_simple
        cloud.activate_response = {
            "ok": False, "error": "timeout", "message": "license server timeout",
        }
        r = client.post("/api/native/license/cloud/activate", json={
            "license_key": "BHE-AAAA-BBBB-CCCC-DDDD",
        })
        assert r.status_code == 503


class TestCloudValidateEndpoint:
    def _seed_active_license(self, client, cloud) -> None:
        cloud.activate_response = {
            "ok": True, "message": "activated",
            "owns_standalone": True, "cloud_library_active": True,
            "cloud_library_expires_at": (datetime.now(timezone.utc)
                                         + timedelta(days=30)).isoformat(),
            "max_seats": 5, "active_seats": 1,
            "revalidate_after": (datetime.now(timezone.utc)
                                 + timedelta(days=7)).isoformat(),
        }
        r = client.post("/api/native/license/cloud/activate", json={
            "license_key": "BHE-AAAA-BBBB-CCCC-DDDD",
        })
        assert r.status_code == 200, r.text

    def test_validate_refreshes_local_state(self, app_client_simple):
        client, cloud = app_client_simple
        self._seed_active_license(client, cloud)
        # Cloud now reports the subscription as canceled
        cloud.validate_response = {
            "ok": True,
            "owns_standalone": True, "cloud_library_active": False,
            "cloud_library_expires_at": None, "revoked": False,
            "revalidate_after": (datetime.now(timezone.utc)
                                 + timedelta(days=7)).isoformat(),
        }
        r = client.post("/api/native/license/cloud/validate")
        assert r.status_code == 200, r.text
        sub = r.json()["subscription"]
        # Cloud-only feature off, but standalone tier preserved
        assert sub["cloud_sync_enabled"] is False
        assert sub["sharepoint_enabled"] is False
        assert sub["story_generator_enabled"] is True

    def test_validate_offline_keeps_cached_state(self, app_client_simple):
        client, cloud = app_client_simple
        self._seed_active_license(client, cloud)
        cloud.timeout_on_validate = True
        r = client.post("/api/native/license/cloud/validate")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "offline"
        # Subscription still reflects the last successful cloud snapshot
        assert body["subscription"]["cloud_sync_enabled"] is True

    def test_validate_400_when_no_key_set(self, app_client_simple):
        client, _ = app_client_simple
        r = client.post("/api/native/license/cloud/validate")
        assert r.status_code == 400


class TestCloudDeactivateEndpoint:
    def test_deactivate_requires_confirm(self, app_client_simple):
        client, _ = app_client_simple
        r = client.post("/api/native/license/cloud/deactivate", json={"confirm": False})
        assert r.status_code == 400
        assert r.json()["detail"] == "confirmation_required"

    def test_deactivate_clears_subscription_locally(self, app_client_simple):
        client, cloud = app_client_simple
        cloud.activate_response = {
            "ok": True, "message": "activated",
            "owns_standalone": True, "cloud_library_active": True,
            "cloud_library_expires_at": (datetime.now(timezone.utc)
                                         + timedelta(days=30)).isoformat(),
            "max_seats": 5, "active_seats": 1,
            "revalidate_after": (datetime.now(timezone.utc)
                                 + timedelta(days=7)).isoformat(),
        }
        client.post("/api/native/license/cloud/activate",
                    json={"license_key": "BHE-AAAA-BBBB-CCCC-DDDD"})
        r = client.post("/api/native/license/cloud/deactivate", json={"confirm": True})
        assert r.status_code == 200
        body = r.json()
        assert body["status"] in ("ok", "offline")
        # Local subscription cleared
        from native.subscription import is_premium_active
        assert is_premium_active() is False


# ===================================================================
# 3. is_premium_active offline-grace logic
# ===================================================================
class TestOfflineGrace:
    def test_recent_validation_keeps_premium_active(self, isolated_config):
        from native import subscription as sub_mod
        sub_mod.set_subscription(active=True, tier="premium",
                                 expires_at=(datetime.now(timezone.utc)
                                              + timedelta(days=30)).isoformat(),
                                 feature_flags={"cloud_sync_enabled": True,
                                                "sharepoint_enabled": True})
        # Stamp a recent cloud validation
        c = isolated_config.config.setdefault("subscription", {})
        c["last_cloud_validated_at"] = datetime.now(timezone.utc).isoformat()
        isolated_config.save_config()
        assert sub_mod.is_premium_active("cloud_sync_enabled") is True

    def test_stale_validation_degrades_premium(self, isolated_config, monkeypatch):
        from native import subscription as sub_mod
        sub_mod.set_subscription(active=True, tier="premium",
                                 expires_at=(datetime.now(timezone.utc)
                                              + timedelta(days=30)).isoformat(),
                                 feature_flags={"cloud_sync_enabled": True})
        # Stamp a 60-day-old cloud validation (well past 30-day grace)
        c = isolated_config.config.setdefault("subscription", {})
        c["last_cloud_validated_at"] = (datetime.now(timezone.utc)
                                        - timedelta(days=60)).isoformat()
        isolated_config.save_config()
        assert sub_mod.is_premium_active("cloud_sync_enabled") is False

    def test_standalone_tier_immune_to_offline_grace(self, isolated_config):
        """One-time-purchase features must NEVER lock out — even after
        years offline, story_generator_enabled stays unlocked."""
        from native import subscription as sub_mod
        sub_mod.set_subscription(active=True, tier="standalone",
                                 expires_at=None,
                                 feature_flags={"story_generator_enabled": True})
        c = isolated_config.config.setdefault("subscription", {})
        c["owns_standalone"] = True
        c["last_cloud_validated_at"] = (datetime.now(timezone.utc)
                                         - timedelta(days=365)).isoformat()
        isolated_config.save_config()
        assert sub_mod.is_premium_active("story_generator_enabled") is True


# ===================================================================
# 4. .env.standalone ships license API URL
# ===================================================================
class TestEnvTemplateLicenseUrl:
    def test_template_includes_license_api_base_url(self):
        text = Path("/app/packaging/.env.standalone").read_text(encoding="utf-8")
        assert "BIGHAT_LICENSE_API_BASE_URL=" in text
        assert "https://api.bighat.live" in text
