"""Phase 10.7 — `offline_mode` Setup Wizard regression.

Locks in the fix for the v32.0.0-alpha.9 bug where the desktop Setup
Wizard's "Continue offline" button still failed with `unknown_key`
because the backend's `/api/native/setup/initialize` endpoint re-called
the cloud's authoritative activate path and bubbled up its 400.

Contract:
  * When the request body includes `offline_mode: true`, the endpoint
    MUST skip the cloud activate call entirely and complete setup
    locally with `pending_cloud_activation: True`.
  * When `offline_mode` is omitted/false, behaviour is unchanged:
    the cloud is called and authoritative rejections (`unknown_key`,
    `revoked`, `seat_limit_exceeded`) still surface as 400.
"""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def native_client(tmp_path, monkeypatch):
    """Spin up a FastAPI test client with only the native router mounted
    and the config + DB pointed at a per-test temp dir. This guarantees
    each test starts from a fresh `setup_complete = False` config so the
    /setup/initialize endpoint will actually run."""
    monkeypatch.setenv("BIGHAT_NATIVE_MODE", "1")
    monkeypatch.delenv("BIGHAT_CLOUD_MODE", raising=False)
    monkeypatch.setenv("BIGHAT_DB_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("JWT_SECRET", "j" * 64)
    # Point the config module's module-level DEFAULT_CONFIG_PATH at our
    # tmp dir BEFORE we re-import — the constant is evaluated at import
    # time, so setting this after import has no effect.
    cfg_path = tmp_path / "system_config.json"
    monkeypatch.setenv("BIGHAT_CONFIG_PATH", str(cfg_path))

    # Force the native modules to re-import so the test-local config
    # singleton + DEFAULT_CONFIG_PATH constant are both fresh.
    import sys
    for mod in [m for m in list(sys.modules) if m.startswith("native.")]:
        del sys.modules[mod]

    from native import config as native_config
    from native.router import router as native_router

    # Defensive double-check: even with the env var, hammer the singleton
    # state to make absolutely sure setup_complete is False at test start.
    native_config.config_manager.config_path = cfg_path
    native_config.config_manager.config = native_config._default_config()
    native_config.config_manager.config["setup_complete"] = False

    app = FastAPI()
    app.include_router(native_router)
    return TestClient(app)

    app = FastAPI()
    app.include_router(native_router)
    return TestClient(app)


def _valid_body(**overrides) -> dict:
    body = {
        "license_key": "BHE-D6P3-8UM2-VS3E-AK69",
        "master_admin": {
            "email": "owner@example.com",
            "password": "SuperSecret#1",
            "first_name": "Owner",
            "last_name": "Test",
            "phone": "+15555550100",
        },
        "settings": {
            "company_name": "BIG Hat Entertainment",
            "location_name": "HQ",
            "city": "Phoenix",
            "state": "AZ",
            "trivia_content_source": "local",
        },
    }
    body.update(overrides)
    return body


class TestOfflineModeSetup:
    """The v32.0.0-alpha.9 regression: "Continue offline" must succeed
    even when the cloud rejects the key as unknown."""

    def test_offline_mode_skips_cloud_and_completes(self, native_client):
        # If the test ever DOES reach cloud_client.activate, it'd 503 against
        # the unreachable api.bighat.live. Patch it to a sentinel that the
        # test asserts is NEVER called.
        with patch("native.router.cloud_client.activate",
                   new=AsyncMock(side_effect=AssertionError(
                       "cloud_client.activate must NOT be called in offline_mode"))):
            r = native_client.post(
                "/api/native/setup/initialize",
                json=_valid_body(offline_mode=True),
            )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["status"] == "ok"
        # The response surfaces a synthetic cloud block flagging the skip,
        # so the frontend Success screen can render an "offline activation
        # pending" banner.
        assert data["cloud"]["ok"] is False
        assert data["cloud"]["pending"] is True
        # License is persisted locally and marked for retry.
        assert data["license"]["pending_cloud_activation"] is True

    def test_offline_mode_persists_even_when_cloud_would_have_returned_unknown_key(
        self, native_client,
    ):
        # Simulate the exact production scenario: cloud DB was wiped on
        # redeploy and now returns `unknown_key` for an otherwise-real key.
        # offline_mode MUST override this and let the customer in.
        with patch("native.router.cloud_client.activate",
                   new=AsyncMock(return_value={
                       "ok": False, "error": "unknown_key", "status_code": 400,
                       "message": "unknown_key",
                   })):
            r = native_client.post(
                "/api/native/setup/initialize",
                json=_valid_body(offline_mode=True),
            )
        assert r.status_code == 200, r.text
        assert r.json()["license"]["pending_cloud_activation"] is True


class TestOnlineModeStillAuthoritative:
    """The fix must NOT silently let bad keys through in normal (online)
    mode — that path is the one that protects revenue."""

    def test_unknown_key_in_online_mode_still_400(self, native_client):
        with patch("native.router.cloud_client.activate",
                   new=AsyncMock(return_value={
                       "ok": False, "error": "unknown_key", "status_code": 400,
                       "message": "unknown_key",
                   })):
            r = native_client.post(
                "/api/native/setup/initialize",
                json=_valid_body(),       # offline_mode defaults to False
            )
        assert r.status_code == 400
        assert r.json()["detail"]["error"] == "unknown_key"

    def test_network_error_in_online_mode_is_offline_tolerant(self, native_client):
        # Transport-layer failures (timeout, network_error) should still
        # behave as "pending" without requiring the explicit offline_mode flag.
        with patch("native.router.cloud_client.activate",
                   new=AsyncMock(return_value={
                       "ok": False, "error": "network_error",
                   })):
            r = native_client.post(
                "/api/native/setup/initialize",
                json=_valid_body(),
            )
        assert r.status_code == 200
        assert r.json()["license"]["pending_cloud_activation"] is True


class TestDbFactoryCloudWins:
    """Phase 10.7 also fixes the silent prod data loss bug where prod
    had BIGHAT_NATIVE_MODE=1 set and lost every minted license on each
    redeploy (because MontyDB SQLite lived in the ephemeral container).

    Cloud-mode MUST win over native-mode for DB selection so the cloud
    pod always uses MongoDB."""

    def test_cloud_mode_overrides_native_mode_for_db_selection(self, monkeypatch):
        monkeypatch.setenv("BIGHAT_CLOUD_MODE", "1")
        monkeypatch.setenv("BIGHAT_NATIVE_MODE", "1")
        # Reimport the factory module so the new env state is picked up.
        import importlib, sys
        sys.modules.pop("native.db_factory", None)
        from native import db_factory
        assert db_factory._is_native_mode() is False, (
            "BIGHAT_NATIVE_MODE must be ignored when BIGHAT_CLOUD_MODE=1 — "
            "otherwise the cloud pod stores licenses in ephemeral SQLite "
            "and loses every key on each Kubernetes redeploy."
        )

    def test_native_mode_alone_still_uses_montydb(self, monkeypatch):
        monkeypatch.delenv("BIGHAT_CLOUD_MODE", raising=False)
        monkeypatch.setenv("BIGHAT_NATIVE_MODE", "1")
        import sys
        sys.modules.pop("native.db_factory", None)
        from native import db_factory
        assert db_factory._is_native_mode() is True

    def test_cloud_mode_alone_uses_mongodb(self, monkeypatch):
        monkeypatch.setenv("BIGHAT_CLOUD_MODE", "1")
        monkeypatch.delenv("BIGHAT_NATIVE_MODE", raising=False)
        import sys
        sys.modules.pop("native.db_factory", None)
        from native import db_factory
        assert db_factory._is_native_mode() is False
