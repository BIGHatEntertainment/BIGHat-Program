"""Iteration 24 — License-key recovery after a cloud data-wipe.

Tests for:
  * `mint_manual(key=...)` accepts a caller-provided key (preserving the
    email-key contract from the original purchase email).
  * `mint_manual(key=None)` still generates a fresh key (regression).
  * `mint_manual(key=...)` with an existing email merges (existing-by-email
    update path is preserved).
  * `POST /api/license/admin/keys/restore` admin endpoint:
      - requires admin auth
      - inserts the row with the EXACT provided key (no email by default)
      - idempotent: same key already in DB returns the row unchanged
      - 409 when the email exists under a DIFFERENT key
      - default note contains "restored"
      - entitlement flags (owns_standalone, owns_music_bingo, owns_karaoke,
        cloud_library_months) are persisted
  * Existing /keys/mint, /keys/{key}/revoke, /keys/{key}/resend-email still
    work — regression.
  * Backend smoke: GET /api/ returns 200.
  * PRD.md sanity (LICENSE-KEY RECOVERY section present + RELEASE FLOW
    section still present below it).
"""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import pytest
import requests


# ---------- shared fixtures ----------
@pytest.fixture
def tmp_db():
    from native.async_monty import AsyncMontyClient
    from montydb import MontyClient, set_storage

    tmpdir = Path(tempfile.mkdtemp(prefix="bighat-iter24-"))
    repo = tmpdir / "repo"
    repo.mkdir()
    set_storage(repository=str(repo), storage="sqlite")
    sync = MontyClient(str(repo))
    client = AsyncMontyClient(sync)
    db = client["test_license_restore_iter24"]
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
    def enabled(self):
        return True

    async def send_license_key_email(self, **kw):
        self.sent.append({"kind": "key", **kw})
        return True

    async def send_subscription_canceled(self, **kw):
        self.sent.append({"kind": "canceled", **kw})
        return True


# ====================================================================
# UNIT TESTS — mint_manual signature/behavior
# ====================================================================
class TestMintManualKeyParam:
    """`mint_manual` must accept an optional `key` parameter without
    breaking any existing call sites."""

    @pytest.mark.asyncio
    async def test_signature_accepts_optional_key(self):
        import inspect
        from cloud.license_service import LicenseService
        sig = inspect.signature(LicenseService.mint_manual)
        assert "key" in sig.parameters, "mint_manual must expose `key` kwarg"
        param = sig.parameters["key"]
        assert param.default is None, "`key` must default to None"

    @pytest.mark.asyncio
    async def test_key_none_generates_fresh(self, tmp_db):
        """Regression: existing call sites (no `key` arg) must continue to
        mint a freshly-generated BHE-... key."""
        from cloud.license_service import LicenseService
        from cloud.license_store import LicenseStore
        svc = LicenseService(LicenseStore(tmp_db), FakeEmail())
        lic = await svc.mint_manual(
            email="fresh@example.com",
            owns_standalone=True,
            cloud_library_months=0,
            send_email=False,
        )
        assert lic.key.startswith("BHE-")
        # Format: BHE-XXXX-XXXX-XXXX-XXXX (5 dash-separated groups)
        assert len(lic.key.split("-")) == 5

    @pytest.mark.asyncio
    async def test_key_provided_is_inserted_verbatim(self, tmp_db):
        from cloud.license_service import LicenseService
        from cloud.license_store import LicenseStore
        svc = LicenseService(LicenseStore(tmp_db), FakeEmail())
        target = "BHE-E7GX-VGTT-TGGP-8S2G"
        lic = await svc.mint_manual(
            email="sellards@bighat.live",
            owns_standalone=True,
            cloud_library_months=0,
            send_email=False,
            key=target,
        )
        assert lic.key == target, "license must use the EXACT provided key"
        # Verify persisted
        fetched = await svc.store.get_by_key(target)
        assert fetched is not None
        assert fetched.key == target
        assert fetched.email == "sellards@bighat.live"
        assert fetched.owns_standalone is True

    @pytest.mark.asyncio
    async def test_existing_email_merge_path_preserved(self, tmp_db):
        """If email already exists, mint_manual updates that row (does not
        try to insert a new one with the provided key)."""
        from cloud.license_service import LicenseService
        from cloud.license_store import LicenseStore
        svc = LicenseService(LicenseStore(tmp_db), FakeEmail())
        # First mint creates the row with an auto-generated key
        first = await svc.mint_manual(
            email="merge@example.com",
            owns_standalone=True,
            cloud_library_months=0,
            send_email=False,
        )
        # Second call passes a different key — but should hit the
        # existing-by-email update branch and KEEP the original key.
        second = await svc.mint_manual(
            email="merge@example.com",
            owns_standalone=True,
            owns_music_bingo=True,
            cloud_library_months=0,
            send_email=False,
            key="BHE-FAKE-FAKE-FAKE-FAKE",
        )
        assert second.key == first.key, (
            "existing-email path must keep the original key, not the new one"
        )
        assert second.owns_music_bingo is True


# ====================================================================
# UNIT TESTS — admin restore_key endpoint logic (via TestClient)
# ====================================================================
@pytest.fixture
def admin_client(tmp_db, monkeypatch):
    """Build a FastAPI TestClient with the admin router wired against
    `tmp_db`. Patches admin auth env so we can mint a token in-process."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from cloud import admin_router
    from cloud.license_service import LicenseService
    from cloud.license_store import LicenseStore

    monkeypatch.setenv("ADMIN_EMAIL", "admin@example.com")
    monkeypatch.setenv("ADMIN_PASSWORD", "test-admin-pw")
    monkeypatch.setenv("LICENSE_ADMIN_SECRET", "unit-test-secret")
    monkeypatch.setenv("JWT_SECRET", "unit-test-secret")

    svc = LicenseService(LicenseStore(tmp_db), FakeEmail())
    admin_router.set_service(svc)
    app = FastAPI()
    app.include_router(admin_router.router)
    client = TestClient(app)

    # Acquire admin token
    r = client.post("/api/license/admin/login",
                    json={"email": "admin@example.com", "password": "test-admin-pw"})
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client, svc


class TestRestoreEndpoint:
    def test_restore_requires_admin_auth(self, admin_client):
        client, _svc = admin_client
        # Strip auth header and verify endpoint rejects
        unauth = requests.Session()
        # We can't easily detach via TestClient; instead use a copy without header
        r = client.post(
            "/api/license/admin/keys/restore",
            json={
                "key": "BHE-AAAA-BBBB-CCCC-DDDD",
                "email": "x@example.com",
                "owns_standalone": True,
            },
            headers={"Authorization": "Bearer not-a-real-token"},
        )
        assert r.status_code == 401, r.text

    def test_restore_inserts_new_key_and_email(self, admin_client):
        client, svc = admin_client
        target = "BHE-E7GX-VGTT-TGGP-8S2G"
        r = client.post(
            "/api/license/admin/keys/restore",
            json={
                "key": target,
                "email": "sellards@bighat.live",
                "owns_standalone": True,
                "owns_music_bingo": False,
                "owns_karaoke": False,
                "cloud_library_months": 0,
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["key"] == target
        assert body["email"] == "sellards@bighat.live"
        assert body["owns_standalone"] is True

        # Verify persisted via store.get_by_key
        import asyncio
        fetched = asyncio.get_event_loop().run_until_complete(
            svc.store.get_by_key(target)
        )
        assert fetched is not None
        assert fetched.key == target

    def test_restore_idempotent_when_key_already_in_db(self, admin_client):
        client, svc = admin_client
        target = "BHE-IDEM-IDEM-IDEM-IDEM"
        payload = {
            "key": target,
            "email": "idem@example.com",
            "owns_standalone": True,
            "cloud_library_months": 0,
        }
        r1 = client.post("/api/license/admin/keys/restore", json=payload)
        assert r1.status_code == 200, r1.text
        r2 = client.post("/api/license/admin/keys/restore", json=payload)
        assert r2.status_code == 200, r2.text
        assert r1.json()["key"] == r2.json()["key"] == target
        assert r1.json()["email"] == r2.json()["email"]

        # Confirm only one row exists in DB
        import asyncio
        rows = asyncio.get_event_loop().run_until_complete(
            svc.store.list_all(limit=100, offset=0)
        )
        matching = [r for r in rows if r.key == target]
        assert len(matching) == 1, f"expected 1 row, got {len(matching)}"

    def test_restore_409_when_email_has_different_key(self, admin_client):
        client, _svc = admin_client
        # First mint via /keys/mint generates a fresh key for the email
        r0 = client.post("/api/license/admin/keys/mint", json={
            "email": "conflict@example.com",
            "owns_standalone": True,
            "cloud_library_months": 0,
            "send_email": False,
        })
        assert r0.status_code == 200, r0.text
        original_key = r0.json()["key"]
        assert original_key.startswith("BHE-")

        # Now try to restore the SAME email with a DIFFERENT key
        r = client.post("/api/license/admin/keys/restore", json={
            "key": "BHE-DIFF-DIFF-DIFF-DIFF",
            "email": "conflict@example.com",
            "owns_standalone": True,
            "cloud_library_months": 0,
        })
        assert r.status_code == 409, r.text
        # Message should reference the existing key
        detail = r.json().get("detail", "")
        assert original_key in detail, (
            f"409 detail should mention existing key {original_key}, got: {detail}"
        )

    def test_restore_sends_no_email(self, admin_client, monkeypatch):
        """The restore endpoint passes send_email=False to mint_manual —
        verify by checking the FakeEmail attached to the service."""
        client, svc = admin_client
        # Replace service email with a fresh FakeEmail we can inspect
        fresh_email = FakeEmail()
        svc.email = fresh_email
        r = client.post("/api/license/admin/keys/restore", json={
            "key": "BHE-NOEM-NOEM-NOEM-NOEM",
            "email": "noemail@example.com",
            "owns_standalone": True,
            "cloud_library_months": 0,
        })
        assert r.status_code == 200, r.text
        assert len(fresh_email.sent) == 0, (
            f"restore must not send email; sent={fresh_email.sent}"
        )

    def test_restore_default_note_contains_restored(self, admin_client):
        """When no note is provided in the request, the row should be
        tagged with a note that contains the word 'restored' (per spec).

        Note isn't stored on the LicenseKey model directly — it's logged.
        We verify by capturing the logger output."""
        import logging
        client, _svc = admin_client
        logs: list[str] = []

        class _Capture(logging.Handler):
            def emit(self, record):
                logs.append(record.getMessage())

        handler = _Capture()
        lic_logger = logging.getLogger("bighat-license")
        adm_logger = logging.getLogger("bighat-license-admin")
        prev_levels = (lic_logger.level, adm_logger.level)
        lic_logger.setLevel(logging.INFO)
        adm_logger.setLevel(logging.INFO)
        lic_logger.addHandler(handler)
        adm_logger.addHandler(handler)
        try:
            r = client.post("/api/license/admin/keys/restore", json={
                "key": "BHE-NOTE-NOTE-NOTE-NOTE",
                "email": "note@example.com",
                "owns_standalone": True,
                "cloud_library_months": 0,
            })
            assert r.status_code == 200, r.text
        finally:
            lic_logger.removeHandler(handler)
            adm_logger.removeHandler(handler)
            lic_logger.setLevel(prev_levels[0])
            adm_logger.setLevel(prev_levels[1])
        joined = " | ".join(logs).lower()
        assert "restored" in joined, (
            f"expected 'restored' in logs, got: {joined}"
        )

    def test_restore_preserves_entitlement_flags(self, admin_client):
        client, _svc = admin_client
        r = client.post("/api/license/admin/keys/restore", json={
            "key": "BHE-FULL-FULL-FULL-FULL",
            "email": "full@example.com",
            "owns_standalone": True,
            "owns_music_bingo": True,
            "owns_karaoke": True,
            "cloud_library_months": 12,
        })
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["owns_standalone"] is True
        assert body["owns_music_bingo"] is True
        assert body["owns_karaoke"] is True
        assert body["cloud_library_status"] == "active"
        assert body["cloud_library_expires_at"] is not None


# ====================================================================
# REGRESSION — existing admin endpoints still work
# ====================================================================
class TestExistingAdminEndpointsStillWork:
    def test_keys_mint_still_generates_new_key(self, admin_client):
        client, _svc = admin_client
        r = client.post("/api/license/admin/keys/mint", json={
            "email": "regress-mint@example.com",
            "owns_standalone": True,
            "cloud_library_months": 0,
            "send_email": False,
        })
        assert r.status_code == 200, r.text
        assert r.json()["key"].startswith("BHE-")

    def test_keys_revoke_still_works(self, admin_client):
        client, _svc = admin_client
        r0 = client.post("/api/license/admin/keys/mint", json={
            "email": "regress-rev@example.com",
            "owns_standalone": True,
            "cloud_library_months": 0,
            "send_email": False,
        })
        key = r0.json()["key"]
        r = client.post(f"/api/license/admin/keys/{key}/revoke")
        assert r.status_code == 200, r.text
        assert r.json()["revoked"] is True

    def test_keys_resend_email_still_works(self, admin_client):
        client, svc = admin_client
        fresh_email = FakeEmail()
        svc.email = fresh_email
        r0 = client.post("/api/license/admin/keys/mint", json={
            "email": "regress-resend@example.com",
            "owns_standalone": True,
            "cloud_library_months": 0,
            "send_email": False,
        })
        key = r0.json()["key"]
        r = client.post(f"/api/license/admin/keys/{key}/resend-email")
        assert r.status_code == 200, r.text
        assert r.json()["ok"] is True
        assert len(fresh_email.sent) == 1
        assert fresh_email.sent[0]["key"] == key


# ====================================================================
# LIVE BACKEND SMOKE
# ====================================================================
class TestBackendSmoke:
    def test_api_root_returns_200(self):
        base = os.environ.get("REACT_APP_BACKEND_URL")
        if not base:
            # Fall back to frontend .env
            envfile = Path("/app/frontend/.env")
            if envfile.exists():
                for line in envfile.read_text().splitlines():
                    if line.startswith("REACT_APP_BACKEND_URL="):
                        base = line.split("=", 1)[1].strip()
                        break
        assert base, "REACT_APP_BACKEND_URL not configured"
        r = requests.get(f"{base.rstrip('/')}/api/", timeout=10)
        assert r.status_code == 200, r.text


# ====================================================================
# PRD sanity (recovery section present + release flow section preserved)
# ====================================================================
class TestPRDSections:
    def test_recovery_section_present(self):
        prd = Path("/app/memory/PRD.md").read_text()
        assert "LICENSE-KEY RECOVERY AFTER A CLOUD DATA-WIPE" in prd
        # JSON example payload markers
        assert '"key": "BHE-XXXX-XXXX-XXXX-XXXX"' in prd
        assert '"send_email": false' in prd
        # The "Don't call /keys/mint" rule
        assert "Don't call `/keys/mint`" in prd or "Don't call /keys/mint" in prd

    def test_release_flow_section_preserved(self):
        prd = Path("/app/memory/PRD.md").read_text()
        # Match the actual ## section headers (not in-text refs).
        recovery_header = "## 🛑 LICENSE-KEY RECOVERY AFTER A CLOUD DATA-WIPE"
        release_header = "## 🛑 RELEASE FLOW — MANUAL, ONE-CLICK FROM MAIN AGENT"
        assert recovery_header in prd
        assert release_header in prd
        rec_idx = prd.find(recovery_header)
        rel_idx = prd.find(release_header)
        assert rec_idx > 0 and rel_idx > rec_idx, (
            f"RELEASE FLOW section ({rel_idx}) must remain below "
            f"LICENSE-KEY RECOVERY section ({rec_idx})"
        )
