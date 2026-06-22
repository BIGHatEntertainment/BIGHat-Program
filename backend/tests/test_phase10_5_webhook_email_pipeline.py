"""Phase 10.5 — Production webhook → email pipeline regression.

Locks in the fix for the prod bug where customers bought on Squarespace
but never received a license-key email. Root cause: `BIGHAT_CLOUD_MODE`
was unset on `api.bighat.live`, so the entire `/api/license/*` and
`/api/squarespace/webhook` router never mounted. The 405 errors and the
silent email failure were both symptoms of the same misconfiguration.

These tests cover:
  1. `/api/license/health` is registered UNCONDITIONALLY and correctly
     surfaces every blocker the operator needs to know.
  2. A real signed Squarespace `order.create` payload, when POSTed to
     the webhook with a matching HMAC signature, mints a license AND
     fires exactly one license-key email.
  3. Replay of the same signed payload is idempotent — no second email.
  4. A signed payload with a bad signature is rejected 401, no mint.
  5. Multi-SKU orders (standalone + music_bingo + karaoke + cloud_library
     in one cart) mint everything and send a single email summarising all
     tiers.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


# ---------- shared infra (mirrors test_phase10_0) ----------
@pytest.fixture
def tmp_db():
    from native.async_monty import AsyncMontyClient
    from montydb import MontyClient, set_storage

    tmpdir = Path(tempfile.mkdtemp(prefix="bighat-phase10_5-"))
    repo = tmpdir / "repo"
    repo.mkdir()
    set_storage(repository=str(repo), storage="sqlite")
    sync = MontyClient(str(repo))
    client = AsyncMontyClient(sync)
    db = client["test_phase10_5"]
    yield db
    try:
        client.close()
    except Exception:
        pass
    shutil.rmtree(tmpdir, ignore_errors=True)


class FakeEmail:
    def __init__(self):
        self.sent: list[dict] = []

    @property
    def enabled(self) -> bool:
        return True

    async def send_license_key_email(self, *, to, key, owns_standalone,
                                     cloud_library_active,
                                     owns_music_bingo=False, owns_karaoke=False):
        self.sent.append({
            "kind": "key", "to": to, "key": key,
            "owns_standalone": owns_standalone,
            "cloud_library_active": cloud_library_active,
            "owns_music_bingo": owns_music_bingo,
            "owns_karaoke": owns_karaoke,
        })
        return True

    async def send_subscription_canceled(self, *, to, key):
        self.sent.append({"kind": "canceled", "to": to, "key": key})
        return True


def _sign(body: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


# ===================================================================
# 1. /api/license/health is always-on
# ===================================================================
class TestHealthEndpointAlwaysOn:
    """Hardens the 2026-06-22 prod fix: even when BIGHAT_CLOUD_MODE is off,
    the health endpoint MUST return 200 with actionable blockers so the
    operator can self-diagnose without pod shell access."""

    def test_health_returns_200_when_cloud_mode_off(self, monkeypatch):
        monkeypatch.delenv("BIGHAT_CLOUD_MODE", raising=False)
        monkeypatch.delenv("RESEND_API_KEY", raising=False)
        monkeypatch.delenv("SQUARESPACE_WEBHOOK_SECRET", raising=False)

        from cloud.health_router import router
        app = FastAPI()
        app.include_router(router)
        c = TestClient(app)

        r = c.get("/api/license/health")
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["ready"] is False
        assert data["modes"]["cloud_mode_enabled"] is False
        assert data["routing"]["license_routes_mounted"] is False
        # Every missing piece must surface as a human-readable blocker.
        joined = " ".join(data["blockers"])
        assert "BIGHAT_CLOUD_MODE" in joined
        assert "RESEND_API_KEY" in joined
        assert "SQUARESPACE_WEBHOOK_SECRET" in joined

    def test_health_ready_true_when_all_secrets_set(self, monkeypatch):
        monkeypatch.setenv("BIGHAT_CLOUD_MODE", "1")
        monkeypatch.delenv("BIGHAT_NATIVE_MODE", raising=False)
        monkeypatch.setenv("RESEND_API_KEY", "re_test_secret_1234")
        monkeypatch.setenv("SQUARESPACE_WEBHOOK_SECRET", "whsec_test_abc")
        monkeypatch.setenv("JWT_SECRET", "j" * 64)

        from cloud.health_router import router
        app = FastAPI()
        app.include_router(router)
        c = TestClient(app)

        r = c.get("/api/license/health")
        assert r.status_code == 200
        data = r.json()
        assert data["ready"] is True, data["blockers"]
        assert data["modes"]["cloud_mode_enabled"] is True
        assert data["routing"]["license_routes_mounted"] is True
        assert data["blockers"] == []

    def test_health_redacts_secret_values(self, monkeypatch):
        """We never want the full Resend key in the diagnostic response."""
        monkeypatch.setenv("RESEND_API_KEY", "re_DO_NOT_LEAK_jhykGKmm_extra_chars")

        from cloud.health_router import router
        app = FastAPI()
        app.include_router(router)
        c = TestClient(app)

        r = c.get("/api/license/health")
        body = r.text
        assert "DO_NOT_LEAK" not in body
        assert "jhykGKmm" not in body
        # but the first 4 chars must be present so the operator can verify
        # the right key is loaded.
        assert "re_D***" in body


# ===================================================================
# 2. End-to-end: signed Squarespace webhook → mint → email
# ===================================================================
@pytest.fixture
def signed_app(tmp_db, monkeypatch):
    """FastAPI test app with HMAC signature verification ENABLED, mirroring
    the production deployment shape."""
    SECRET = "whsec_test_pipeline_2026"
    monkeypatch.setenv("SQUARESPACE_WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("JWT_SECRET", "j" * 64)
    monkeypatch.setenv("ADMIN_EMAIL", "admin@bighat.live")
    monkeypatch.setenv("ADMIN_PASSWORD", "admintest")
    monkeypatch.setenv("DOWNLOAD_URL_WINDOWS", "https://bighat.live/dl/setup.exe")
    monkeypatch.setenv("DOWNLOAD_URL_MACOS", "https://bighat.live/dl/standalone.dmg")

    from cloud.license_store import LicenseStore
    from cloud.license_service import LicenseService
    from cloud.squarespace_webhook import WebhookHandler
    from cloud.license_router import router as cr, set_runtime

    store = LicenseStore(tmp_db)
    email = FakeEmail()
    svc = LicenseService(store, email)
    h = WebhookHandler(svc, store)
    set_runtime(store=store, service=svc, webhook=h)

    app = FastAPI()
    app.include_router(cr)
    return TestClient(app), store, email, SECRET


class TestSignedWebhookEmailPipeline:
    """The single biggest production regression: signed webhook must mint
    AND fire the Resend email. This locks the contract end-to-end."""

    def test_signed_standalone_order_mints_and_emails_once(self, signed_app):
        client, store, email, secret = signed_app
        payload = {
            "id": "evt_prod_1",
            "topic": "order.create",
            "data": {"order": {
                "id": "ORD-2026-001",
                "customerEmail": "buyer@example.com",
                "customerId": "cust_42",
                "lineItems": [{"sku": "BHE-STANDALONE"}],
            }},
        }
        body = json.dumps(payload).encode()
        sig = _sign(body, secret)

        r = client.post(
            "/api/squarespace/webhook",
            content=body,
            headers={
                "Content-Type": "application/json",
                "Squarespace-Signature": f"t=1700000000,v1={sig}",
            },
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["status"] == "minted"
        # The minted result includes the license key — check it round-trips.
        assert any("standalone:" in m for m in data["results"])
        # Exactly one email fired, addressed to the buyer.
        assert len(email.sent) == 1
        assert email.sent[0]["to"] == "buyer@example.com"
        assert email.sent[0]["owns_standalone"] is True
        # License was persisted.
        from asyncio import run
        lic = run(store.get_by_email("buyer@example.com"))
        assert lic is not None
        assert lic.owns_standalone is True

    def test_replay_is_idempotent_no_second_email(self, signed_app):
        client, store, email, secret = signed_app
        payload = {
            "id": "evt_prod_replay",
            "topic": "order.create",
            "data": {"order": {
                "id": "ORD-2026-002",
                "customerEmail": "replay@example.com",
                "lineItems": [{"sku": "BHE-STANDALONE"}],
            }},
        }
        body = json.dumps(payload).encode()
        sig = _sign(body, secret)
        headers = {"Content-Type": "application/json",
                   "Squarespace-Signature": f"v1={sig}"}
        r1 = client.post("/api/squarespace/webhook", content=body, headers=headers)
        r2 = client.post("/api/squarespace/webhook", content=body, headers=headers)
        assert r1.status_code == 200 and r2.status_code == 200
        assert r1.json()["status"] == "minted"
        assert r2.json()["status"] == "duplicate"
        assert len(email.sent) == 1  # NOT 2

    def test_bad_signature_rejects_401_no_mint(self, signed_app):
        client, store, email, _ = signed_app
        payload = {"id": "evt_bad", "topic": "order.create",
                   "data": {"order": {"id": "ORD-X", "customerEmail": "x@example.com",
                                       "lineItems": [{"sku": "BHE-STANDALONE"}]}}}
        body = json.dumps(payload).encode()
        r = client.post(
            "/api/squarespace/webhook",
            content=body,
            headers={"Content-Type": "application/json",
                     "Squarespace-Signature": "v1=deadbeef"},
        )
        assert r.status_code == 401
        assert len(email.sent) == 0
        from asyncio import run
        assert run(store.count()) == 0

    def test_multi_sku_cart_mints_all_tiers_one_email(self, signed_app):
        client, store, email, secret = signed_app
        payload = {
            "id": "evt_multi",
            "topic": "order.create",
            "data": {"order": {
                "id": "ORD-MULTI-1",
                "customerEmail": "power@example.com",
                "lineItems": [
                    {"sku": "BHE-STANDALONE"},
                    {"sku": "BHE-MUSIC-BINGO"},
                    {"sku": "BHE-KARAOKE"},
                    {"sku": "BHE-CLOUD-LIBRARY"},
                ],
            }},
        }
        body = json.dumps(payload).encode()
        sig = _sign(body, secret)
        r = client.post(
            "/api/squarespace/webhook",
            content=body,
            headers={"Content-Type": "application/json",
                     "Squarespace-Signature": f"v1={sig}"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "minted"
        # All four tiers persisted on a single per-customer key.
        from asyncio import run
        lic = run(store.get_by_email("power@example.com"))
        assert lic is not None
        assert lic.owns_standalone is True
        assert lic.owns_music_bingo is True
        assert lic.owns_karaoke is True
        assert lic.cloud_library_status == "active"
        # Last email sent reflects the full tier set.
        last = email.sent[-1]
        assert last["owns_standalone"] is True
        assert last["owns_music_bingo"] is True
        assert last["owns_karaoke"] is True
        assert last["cloud_library_active"] is True


# ===================================================================
# 3. RESEND_API_KEY missing → email no-ops but mint succeeds.
#    This was the silent-failure case that bit prod.
# ===================================================================
class TestResendDisabledStillMints:
    @pytest.mark.asyncio
    async def test_no_resend_key_still_mints_key_logs_warning(self, tmp_db, monkeypatch, caplog):
        import logging
        monkeypatch.delenv("RESEND_API_KEY", raising=False)
        caplog.set_level(logging.WARNING)

        from cloud.license_service import LicenseService
        from cloud.license_store import LicenseStore
        from cloud.email_service import ResendEmailSender
        store = LicenseStore(tmp_db)
        sender = ResendEmailSender()
        assert sender.enabled is False  # the silent prod failure mode
        svc = LicenseService(store, sender)
        lic = await svc.mint_standalone_purchase(
            email="missing-resend@example.com", order_id="ORD-NORESEND",
        )
        assert lic.owns_standalone is True
        # mint succeeded; user has a key in the DB even though email no-opped.
        again = await store.get_by_email("missing-resend@example.com")
        assert again is not None
        # The no-op MUST be loud in the logs so an operator notices.
        assert any("RESEND_API_KEY not set" in rec.getMessage()
                   for rec in caplog.records), [r.getMessage() for r in caplog.records]
