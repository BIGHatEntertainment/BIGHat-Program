"""Phase 10.0 — Cloud Licensing Service tests.

In-process tests:
  * Pure-function unit tests (key generation, masking, signature verification,
    payload parsing) with no DB/HTTP.
  * Service-level integration tests using MontyDB (SQLite) as the store —
    no need to spin up MongoDB; matches the `native/` test infrastructure.
  * Router-level integration tests via FastAPI's TestClient with a minimal
    app that mounts `/api/license/*` + `/api/squarespace/webhook` + admin.

The cloud routes are gated by `BIGHAT_CLOUD_MODE=1` in `server.py`, so we
DO NOT touch the live supervisor-managed server in these tests. Everything
runs in-process against an isolated temp DB.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import shutil
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


# ---------- DB fixture (MontyDB SQLite — isolated per test) ----------
@pytest.fixture
def tmp_db():
    """Returns a fresh AsyncMontyDatabase rooted in a temp dir."""
    from native.async_monty import AsyncMontyClient
    from montydb import MontyClient, set_storage

    tmpdir = Path(tempfile.mkdtemp(prefix="bighat-license-test-"))
    repo = tmpdir / "repo"
    repo.mkdir()
    set_storage(repository=str(repo), storage="sqlite")
    sync = MontyClient(str(repo))
    client = AsyncMontyClient(sync)
    db = client["test_license"]
    yield db
    try:
        client.close()
    except Exception:
        pass
    shutil.rmtree(tmpdir, ignore_errors=True)


# ---------- Capturing fake email sender ----------
class FakeEmail:
    def __init__(self):
        self.sent: list[dict] = []

    @property
    def enabled(self) -> bool:  # mirror real interface
        return True

    async def send_license_key_email(self, *, to, key, owns_standalone, cloud_library_active):
        self.sent.append({"kind": "key", "to": to, "key": key,
                          "owns_standalone": owns_standalone,
                          "cloud_library_active": cloud_library_active})
        return True

    async def send_subscription_canceled(self, *, to, key):
        self.sent.append({"kind": "canceled", "to": to, "key": key})
        return True


# ===================================================================
# 1. Pure function unit tests
# ===================================================================
class TestKeyGeneration:
    def test_format_is_BHE_dash_4x4(self):
        from cloud.license_service import generate_key
        for _ in range(50):
            k = generate_key()
            parts = k.split("-")
            assert parts[0] == "BHE"
            assert len(parts) == 5
            assert all(len(p) == 4 for p in parts[1:])

    def test_keys_are_unique(self):
        from cloud.license_service import generate_key
        keys = {generate_key() for _ in range(500)}
        assert len(keys) == 500  # 80 bits of entropy — collisions infeasible

    def test_alphabet_excludes_ambiguous_chars(self):
        from cloud import config
        from cloud.license_service import generate_key
        for _ in range(50):
            k = generate_key()
            body = k.replace("-", "")
            for ch in body[3:]:  # skip 'BHE' prefix
                assert ch in config.LICENSE_KEY_ALPHABET
                assert ch not in "01OIL"


class TestKeyMasking:
    def test_masks_middle_groups_only(self):
        from cloud.license_service import mask_key
        m = mask_key("BHE-ABCD-EFGH-JKMN-PQRS")
        assert m == "BHE-****-****-****-PQRS"

    def test_handles_short_input(self):
        from cloud.license_service import mask_key
        assert mask_key("") == "****"
        assert mask_key("BHE") == "****"


class TestSignatureVerification:
    def test_accepts_valid_raw_hex(self):
        from cloud.squarespace_webhook import verify_signature
        body = b'{"hello":"world"}'
        secret = "supersekret"
        sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        assert verify_signature(body=body, signature_header=sig, secret=secret) is True

    def test_accepts_t_v1_format(self):
        from cloud.squarespace_webhook import verify_signature
        body = b'{"hello":"world"}'
        secret = "s3cr3t"
        sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        header = f"t=1700000000,v1={sig}"
        assert verify_signature(body=body, signature_header=header, secret=secret) is True

    def test_rejects_bad_signature(self):
        from cloud.squarespace_webhook import verify_signature
        assert verify_signature(body=b"x", signature_header="deadbeef", secret="s") is False

    def test_rejects_missing_secret(self):
        from cloud.squarespace_webhook import verify_signature
        assert verify_signature(body=b"x", signature_header="abc", secret="") is False

    def test_rejects_missing_header(self):
        from cloud.squarespace_webhook import verify_signature
        assert verify_signature(body=b"x", signature_header="", secret="s") is False


class TestPayloadParsing:
    def test_extract_event_id_prefers_squarespace_id(self):
        from cloud.squarespace_webhook import _extract_event_id
        assert _extract_event_id({"id": "evt_123"}) == "evt_123"
        assert _extract_event_id({"eventId": "evt_xyz"}) == "evt_xyz"

    def test_extract_event_id_falls_back_to_hash(self):
        from cloud.squarespace_webhook import _extract_event_id
        eid = _extract_event_id({"foo": 1, "bar": 2})
        assert eid.startswith("sha_")
        assert len(eid) > 10
        # Same payload → same id (idempotency)
        assert eid == _extract_event_id({"bar": 2, "foo": 1})

    def test_extract_order_handles_nesting(self):
        from cloud.squarespace_webhook import _extract_order
        assert _extract_order({"data": {"order": {"id": "o1"}}}) == {"id": "o1"}
        assert _extract_order({"order": {"id": "o2"}}) == {"id": "o2"}
        assert _extract_order({"id": "o3", "lineItems": []}) == {"id": "o3", "lineItems": []}
        assert _extract_order({}) is None

    def test_iter_skus_and_email(self):
        from cloud.squarespace_webhook import _iter_skus, _customer_email, _order_id
        order = {
            "id": "ord-99",
            "customerEmail": "alice@example.com",
            "lineItems": [{"sku": "BHE-STANDALONE-2499"}, {"sku": "EXTRA"}],
        }
        assert _iter_skus(order) == ["BHE-STANDALONE-2499", "EXTRA"]
        assert _customer_email(order) == "alice@example.com"
        assert _order_id(order) == "ord-99"


# ===================================================================
# 2. Service-level integration tests (against MontyDB)
# ===================================================================
class TestLicenseServiceMint:
    @pytest.mark.asyncio
    async def test_mint_standalone_creates_key_and_emails_customer(self, tmp_db):
        from cloud.license_service import LicenseService
        from cloud.license_store import LicenseStore
        store = LicenseStore(tmp_db)
        await store.ensure_indexes()
        email = FakeEmail()
        svc = LicenseService(store, email)

        lic = await svc.mint_standalone_purchase(
            email="alice@example.com", order_id="ord_001", customer_id="cust_a"
        )
        assert lic.owns_standalone is True
        assert lic.cloud_library_status == "inactive"
        assert lic.email == "alice@example.com"
        assert lic.key.startswith("BHE-")
        assert lic.squarespace_standalone_order_id == "ord_001"

        assert email.sent and email.sent[0]["kind"] == "key"
        assert email.sent[0]["owns_standalone"] is True
        assert email.sent[0]["cloud_library_active"] is False

    @pytest.mark.asyncio
    async def test_mint_standalone_is_idempotent_on_replay(self, tmp_db):
        from cloud.license_service import LicenseService
        from cloud.license_store import LicenseStore
        store = LicenseStore(tmp_db)
        email = FakeEmail()
        svc = LicenseService(store, email)

        a = await svc.mint_standalone_purchase(email="bob@e.com", order_id="ord_b")
        b = await svc.mint_standalone_purchase(email="bob@e.com", order_id="ord_b")
        assert a.key == b.key
        # Email sent only once (the replay should not re-send)
        assert sum(1 for e in email.sent if e["kind"] == "key") == 1

    @pytest.mark.asyncio
    async def test_mint_subscription_then_standalone_unifies_under_one_key(self, tmp_db):
        from cloud.license_service import LicenseService
        from cloud.license_store import LicenseStore
        store = LicenseStore(tmp_db)
        svc = LicenseService(store, FakeEmail())

        sub = await svc.mint_cloud_subscription(
            email="carol@e.com", subscription_id="sub_c", months=1,
        )
        std = await svc.mint_standalone_purchase(
            email="carol@e.com", order_id="ord_c",
        )
        assert sub.key == std.key
        assert std.owns_standalone is True
        assert std.cloud_library_status == "active"

    @pytest.mark.asyncio
    async def test_subscription_extends_expiration(self, tmp_db):
        from cloud.license_service import LicenseService
        from cloud.license_store import LicenseStore
        store = LicenseStore(tmp_db)
        svc = LicenseService(store, FakeEmail())

        first = await svc.mint_cloud_subscription(
            email="dan@e.com", subscription_id="sub_d", months=1,
        )
        second = await svc.mint_cloud_subscription(
            email="dan@e.com", subscription_id="sub_d", months=1,
        )
        # Same subscription_id replay → no-op (idempotent)
        assert first.cloud_library_expires_at == second.cloud_library_expires_at

    @pytest.mark.asyncio
    async def test_cancel_subscription(self, tmp_db):
        from cloud.license_service import LicenseService
        from cloud.license_store import LicenseStore
        store = LicenseStore(tmp_db)
        email = FakeEmail()
        svc = LicenseService(store, email)

        await svc.mint_cloud_subscription(
            email="erin@e.com", subscription_id="sub_e", months=1,
        )
        canceled = await svc.cancel_cloud_subscription(subscription_id="sub_e")
        assert canceled is not None
        assert canceled.cloud_library_status == "canceled"
        # cancellation email fired
        assert any(e["kind"] == "canceled" for e in email.sent)

    @pytest.mark.asyncio
    async def test_cancel_unknown_subscription_returns_none(self, tmp_db):
        from cloud.license_service import LicenseService
        from cloud.license_store import LicenseStore
        store = LicenseStore(tmp_db)
        svc = LicenseService(store, FakeEmail())
        assert await svc.cancel_cloud_subscription(subscription_id="ghost") is None


class TestLicenseServiceActivation:
    @pytest.mark.asyncio
    async def test_activate_binds_first_hwid(self, tmp_db):
        from cloud.license_service import LicenseService
        from cloud.license_store import LicenseStore
        store = LicenseStore(tmp_db)
        svc = LicenseService(store, FakeEmail())
        lic = await svc.mint_standalone_purchase(email="f@e.com", order_id="o1")
        ok, msg, updated = await svc.activate(
            key=lic.key, hwid="hw-1", machine_name="laptop",
        )
        assert ok and msg == "activated"
        assert updated and len(updated.active_hwids) == 1

    @pytest.mark.asyncio
    async def test_activate_replay_same_hwid(self, tmp_db):
        from cloud.license_service import LicenseService
        from cloud.license_store import LicenseStore
        store = LicenseStore(tmp_db)
        svc = LicenseService(store, FakeEmail())
        lic = await svc.mint_standalone_purchase(email="g@e.com", order_id="o2")
        await svc.activate(key=lic.key, hwid="hw-1")
        ok, msg, updated = await svc.activate(key=lic.key, hwid="hw-1")
        assert ok and msg == "already_activated"
        assert updated and len(updated.active_hwids) == 1

    @pytest.mark.asyncio
    async def test_activate_seat_limit_enforced(self, tmp_db):
        from cloud.license_service import LicenseService
        from cloud.license_store import LicenseStore
        store = LicenseStore(tmp_db)
        svc = LicenseService(store, FakeEmail())
        lic = await svc.mint_standalone_purchase(email="h@e.com", order_id="o3")
        for i in range(lic.max_seats):
            ok, _, _ = await svc.activate(key=lic.key, hwid=f"hw-{i}")
            assert ok
        # Next one over the limit must fail
        ok, msg, _ = await svc.activate(key=lic.key, hwid="hw-overflow")
        assert ok is False
        assert "seat_limit" in msg

    @pytest.mark.asyncio
    async def test_validate_returns_correct_status(self, tmp_db):
        from cloud.license_service import LicenseService
        from cloud.license_store import LicenseStore
        store = LicenseStore(tmp_db)
        svc = LicenseService(store, FakeEmail())
        lic = await svc.mint_standalone_purchase(email="i@e.com", order_id="o4")
        await svc.activate(key=lic.key, hwid="hw-X")
        ok, msg, updated = await svc.validate(key=lic.key, hwid="hw-X")
        assert ok and msg == "ok"
        # Wrong HWID → fail
        ok2, msg2, _ = await svc.validate(key=lic.key, hwid="hw-not-bound")
        assert ok2 is False and msg2 == "hwid_not_activated"

    @pytest.mark.asyncio
    async def test_revoked_key_blocks_activate_and_validate(self, tmp_db):
        from cloud.license_service import LicenseService
        from cloud.license_store import LicenseStore
        store = LicenseStore(tmp_db)
        svc = LicenseService(store, FakeEmail())
        lic = await svc.mint_standalone_purchase(email="j@e.com", order_id="o5")
        await svc.revoke(key=lic.key, reason="chargeback")
        ok, msg, _ = await svc.activate(key=lic.key, hwid="hw-z")
        assert ok is False and "revoked" in msg

    @pytest.mark.asyncio
    async def test_deactivate_removes_seat(self, tmp_db):
        from cloud.license_service import LicenseService
        from cloud.license_store import LicenseStore
        store = LicenseStore(tmp_db)
        svc = LicenseService(store, FakeEmail())
        lic = await svc.mint_standalone_purchase(email="k@e.com", order_id="o6")
        await svc.activate(key=lic.key, hwid="hw-1")
        ok, msg = await svc.deactivate(key=lic.key, hwid="hw-1")
        assert ok and msg == "deactivated"
        # Now there's room for a new seat
        ok2, _, updated = await svc.activate(key=lic.key, hwid="hw-2")
        assert ok2 and updated and len(updated.active_hwids) == 1


class TestWebhookHandler:
    @pytest.mark.asyncio
    async def test_order_create_with_standalone_sku_mints_key(self, tmp_db, monkeypatch):
        from cloud.license_service import LicenseService
        from cloud.license_store import LicenseStore
        from cloud.squarespace_webhook import WebhookHandler
        store = LicenseStore(tmp_db)
        await store.ensure_indexes()
        email = FakeEmail()
        svc = LicenseService(store, email)
        h = WebhookHandler(svc, store)

        result = await h.handle({
            "id": "evt_001",
            "topic": "order.create",
            "data": {"order": {
                "id": "ord_1",
                "customerEmail": "alice@example.com",
                "lineItems": [{"sku": "BHE-STANDALONE-2499"}],
            }},
        })
        assert result["ok"] is True
        assert result["status"] == "minted"
        assert any(e["kind"] == "key" for e in email.sent)

    @pytest.mark.asyncio
    async def test_replay_same_event_id_is_idempotent(self, tmp_db):
        from cloud.license_service import LicenseService
        from cloud.license_store import LicenseStore
        from cloud.squarespace_webhook import WebhookHandler
        store = LicenseStore(tmp_db)
        await store.ensure_indexes()
        svc = LicenseService(store, FakeEmail())
        h = WebhookHandler(svc, store)

        payload = {
            "id": "evt_dup",
            "topic": "order.create",
            "data": {"order": {
                "id": "ord_dup",
                "customerEmail": "bob@e.com",
                "lineItems": [{"sku": "BHE-STANDALONE-2499"}],
            }},
        }
        r1 = await h.handle(payload)
        r2 = await h.handle(payload)
        assert r1["status"] == "minted"
        assert r2["status"] == "duplicate"
        # only one license created
        assert (await store.count()) == 1

    @pytest.mark.asyncio
    async def test_unknown_topic_returns_ignored(self, tmp_db):
        from cloud.license_service import LicenseService
        from cloud.license_store import LicenseStore
        from cloud.squarespace_webhook import WebhookHandler
        store = LicenseStore(tmp_db)
        svc = LicenseService(store, FakeEmail())
        h = WebhookHandler(svc, store)
        result = await h.handle({"id": "evt_x", "topic": "site.deploy"})
        assert result["status"] == "ignored"

    @pytest.mark.asyncio
    async def test_subscription_cancel_topic_flips_status(self, tmp_db):
        from cloud.license_service import LicenseService
        from cloud.license_store import LicenseStore
        from cloud.squarespace_webhook import WebhookHandler
        store = LicenseStore(tmp_db)
        svc = LicenseService(store, FakeEmail())
        h = WebhookHandler(svc, store)
        # Seed: an active subscription
        await svc.mint_cloud_subscription(
            email="z@e.com", subscription_id="sub_z", months=1,
        )
        result = await h.handle({
            "id": "evt_cancel",
            "topic": "subscription.cancel",
            "data": {"subscription": {"id": "sub_z"}},
        })
        assert result["status"] == "subscription_canceled"
        lic = await store.get_by_email("z@e.com")
        assert lic.cloud_library_status == "canceled"


# ===================================================================
# 3. Router-level integration via TestClient
# ===================================================================
@pytest.fixture
def app_client(tmp_db, monkeypatch):
    """Spin up a minimal FastAPI app with the cloud routers mounted."""
    monkeypatch.setenv("SQUARESPACE_WEBHOOK_SECRET", "")  # accept unsigned in tests
    monkeypatch.setenv("ADMIN_EMAIL", "admin@bighat.live")
    monkeypatch.setenv("ADMIN_PASSWORD", "admintest")
    monkeypatch.setenv("JWT_SECRET", "test-jwt-secret-32chars-aaaaaaaaaa")
    monkeypatch.setenv("DOWNLOAD_URL_WINDOWS", "https://bighat.live/dl/setup.exe")
    monkeypatch.setenv("DOWNLOAD_URL_MACOS", "https://bighat.live/dl/standalone.dmg")

    from cloud.license_store import LicenseStore
    from cloud.license_service import LicenseService
    from cloud.squarespace_webhook import WebhookHandler
    from cloud.license_router import router as cr, set_runtime
    from cloud.admin_router import router as ar, set_service

    store = LicenseStore(tmp_db)
    email = FakeEmail()
    svc = LicenseService(store, email)
    h = WebhookHandler(svc, store)
    set_runtime(store=store, service=svc, webhook=h)
    set_service(svc)

    app = FastAPI()
    app.include_router(cr)
    app.include_router(ar)
    return TestClient(app), svc, email


class TestPublicRoutes:
    def test_activate_validates_seat_and_returns_payload(self, app_client):
        client, svc, _ = app_client
        # Seed a key via the webhook endpoint (true end-to-end).
        seed = client.post("/api/squarespace/webhook", json={
            "id": "evt_seed_route", "topic": "order.create",
            "data": {"order": {"id": "oR", "customerEmail": "route@e.com",
                               "lineItems": [{"sku": "BHE-STANDALONE-2499"}]}},
        })
        assert seed.status_code == 200, seed.text
        # Pull the key out via admin (cleaner than poking the DB).
        token = client.post("/api/license/admin/login", json={
            "email": "admin@bighat.live", "password": "admintest"}).json()["access_token"]
        rows = client.get("/api/license/admin/keys",
                          headers={"Authorization": f"Bearer {token}"}).json()
        key = next(r["key"] for r in rows if r["email"] == "route@e.com")

        r = client.post("/api/license/activate", json={
            "key": key, "hwid": "hw-route", "machine_name": "MBP",
        })
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["ok"] is True
        assert data["owns_standalone"] is True
        assert data["active_seats"] == 1
        assert data["max_seats"] >= 1
        assert "revalidate_after" in data

    def test_activate_unknown_key_returns_400(self, app_client):
        client, _, _ = app_client
        r = client.post("/api/license/activate", json={"key": "BHE-DEAD-BEEF-DEAD-BEEF", "hwid": "h"})
        assert r.status_code == 400
        assert r.json()["detail"] == "unknown_key"

    def test_validate_returns_negative_for_unknown(self, app_client):
        client, _, _ = app_client
        r = client.post("/api/license/validate", json={"key": "BHE-NOPE-NOPE-NOPE-NOPE", "hwid": "h"})
        assert r.status_code == 200
        assert r.json()["ok"] is False
        assert r.json()["owns_standalone"] is False

    def test_status_404_when_key_unknown(self, app_client):
        client, _, _ = app_client
        r = client.get("/api/license/status/BHE-XXXX-XXXX-XXXX-XXXX")
        assert r.status_code == 404

    def test_downloads_returns_url(self, app_client):
        client, _, _ = app_client
        r = client.get("/api/downloads/windows")
        assert r.status_code == 200
        assert r.json()["url"].startswith("https://")
        assert r.json()["platform"] == "windows"

    def test_downloads_invalid_platform_422(self, app_client):
        client, _, _ = app_client
        r = client.get("/api/downloads/linux")
        assert r.status_code == 422  # pydantic regex rejection

    def test_squarespace_webhook_full_round_trip(self, app_client):
        client, svc, email_capture = app_client
        body = {
            "id": "evt_route_1",
            "topic": "order.create",
            "data": {"order": {
                "id": "ord_R",
                "customerEmail": "webhook@e.com",
                "lineItems": [{"sku": "BHE-STANDALONE-2499"}],
            }},
        }
        r = client.post("/api/squarespace/webhook", json=body)
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "minted"
        # Verify the email "would have" been sent
        assert any(e["kind"] == "key" and e["to"] == "webhook@e.com"
                   for e in email_capture.sent)


class TestAdminRoutes:
    def _login(self, client) -> str:
        r = client.post("/api/license/admin/login", json={
            "email": "admin@bighat.live", "password": "admintest",
        })
        assert r.status_code == 200, r.text
        return r.json()["access_token"]

    def test_login_rejects_wrong_password(self, app_client):
        client, _, _ = app_client
        r = client.post("/api/license/admin/login", json={
            "email": "admin@bighat.live", "password": "wrong",
        })
        assert r.status_code == 401

    def test_keys_endpoint_requires_auth(self, app_client):
        client, _, _ = app_client
        r = client.get("/api/license/admin/keys")
        assert r.status_code == 401

    def test_keys_list_after_mint(self, app_client):
        client, svc, _ = app_client
        # Seed via mint endpoint (admin)
        token = self._login(client)
        h = {"Authorization": f"Bearer {token}"}
        m = client.post("/api/license/admin/keys/mint",
                        json={"email": "comp@e.com", "owns_standalone": True,
                              "cloud_library_months": 0, "note": "comp"},
                        headers=h)
        assert m.status_code == 200, m.text
        minted = m.json()
        assert minted["owns_standalone"] is True
        assert minted["email"] == "comp@e.com"

        l = client.get("/api/license/admin/keys", headers=h)
        assert l.status_code == 200
        rows = l.json()
        assert any(r["email"] == "comp@e.com" for r in rows)

    def test_revoke_marks_key_revoked(self, app_client):
        client, svc, _ = app_client
        # Seed via webhook
        client.post("/api/squarespace/webhook", json={
            "id": "evt_seed_rv", "topic": "order.create",
            "data": {"order": {"id": "orv", "customerEmail": "rv@e.com",
                               "lineItems": [{"sku": "BHE-STANDALONE-2499"}]}},
        })
        token = self._login(client)
        h = {"Authorization": f"Bearer {token}"}
        rows = client.get("/api/license/admin/keys", headers=h).json()
        key = next(r["key"] for r in rows if r["email"] == "rv@e.com")
        r = client.post(
            f"/api/license/admin/keys/{key}/revoke?reason=chargeback",
            headers=h,
        )
        assert r.status_code == 200, r.text
        assert r.json()["revoked"] is True
