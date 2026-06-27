"""Contract test for v32.0.0-alpha.19 — offline_mode setup grants
`owns_standalone=true` optimistically.

The bug being prevented:
  alpha.17 / alpha.18 routed offline_mode=true through `pending_cloud`
  but never called `_apply_cloud_response_to_local_state(...)`, so the
  subscription block stayed default (owns_standalone=false). The
  customer walked out of the wizard with a syntactically-valid key
  saved locally but a permanently-locked dashboard.

After alpha.19 we grant `owns_standalone=true` immediately, mark
`pending_cloud_activation=true` so the 4-hour refresh job knows to
reconcile, and the customer can actually use Trivia while the cloud
catches up.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


# The native router imports config_manager at module-import time and
# expects a writeable filesystem. Point it at a temp dir BEFORE the
# import so nothing escapes the test sandbox.
@pytest.fixture
def native_app(tmp_path, monkeypatch):
    monkeypatch.setenv("BIGHAT_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("BIGHAT_CONFIG_PATH", str(tmp_path / "system_config.json"))

    # Reset the cached module so config_manager re-reads from env.
    for mod in list(sys.modules):
        if mod.startswith("backend.native"):
            del sys.modules[mod]

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from fastapi import FastAPI
    from backend.native.router import router as native_router
    from backend.native.config import config_manager

    app = FastAPI()
    app.include_router(native_router)
    return app, config_manager


def _payload(offline: bool):
    return {
        "license_key": "BHE-E7GX-VGTT-TGGP-8S2G",
        "offline_mode": offline,
        "master_admin": {
            "email": "sellards@bighat.live",
            "first_name": "Owner",
            "last_name": "User",
            "display_name": "Owner",
            "phone": "",
            "password": "Pa55w0rd!23",
        },
        "settings": {"location_name": "Test Bar"},
    }


def test_offline_setup_grants_owns_standalone(native_app):
    """The whole point of alpha.19: Continue offline must unlock Trivia."""
    app, config_manager = native_app
    with TestClient(app) as client:
        r = client.post("/api/native/setup/initialize", json=_payload(offline=True))
        assert r.status_code == 200, r.text
        body = r.json()
        sub = body["subscription"]
        assert sub["owns_standalone"] is True, (
            "Continue offline must grant owns_standalone=true so Trivia "
            "(gated on this flag) unlocks immediately. See PRD "
            "'OFFLINE-FIRST ENTITLEMENT' and CHANGELOG v32.0.0-alpha.19."
        )
        assert sub["tier"] == "standalone"
        # And the pending flag is set so the 4h refresh job knows to
        # reconcile.
        cfg = config_manager.config
        lic = cfg.get("license_status", {})
        assert lic.get("pending_cloud_activation") is True


def test_offline_setup_persists_pending_flag(native_app):
    """The pending_cloud_activation flag must survive across reads — the
    refresh job reads it from system_config.json at boot."""
    app, config_manager = native_app
    with TestClient(app) as client:
        r = client.post("/api/native/setup/initialize", json=_payload(offline=True))
        assert r.status_code == 200
    # Reload config from disk (simulate restart).
    config_manager.load_config()
    assert config_manager.config["license_status"]["pending_cloud_activation"] is True
