"""Phase 10.9 — Admin mint MUST email by default + resend endpoint.

Customer-impact bug: `mint_manual()` was the only mint path that did NOT
send an email after creating the key. Support tickets like "I minted a
test key for them, but they didn't get the email" all trace back here.
Squarespace-poller mints (mint_standalone_purchase / mint_addon_purchase
/ mint_cloud_subscription) all email; only the support comp path did not.

Contract:
  * `mint_manual()` defaults to `send_email=True` and calls the email
    sender exactly once on success.
  * Passing `send_email=False` skips the email (for hand-delivered comps).
  * `resend_license_email(key=...)` looks up the key and re-fires the
    standard email — used by support for "I lost my key" tickets.
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def tmp_db():
    from native.async_monty import AsyncMontyClient
    from montydb import MontyClient, set_storage

    tmpdir = Path(tempfile.mkdtemp(prefix="bighat-phase10_9-"))
    repo = tmpdir / "repo"
    repo.mkdir()
    set_storage(repository=str(repo), storage="sqlite")
    sync = MontyClient(str(repo))
    client = AsyncMontyClient(sync)
    db = client["test_phase10_9"]
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


@pytest.fixture
def svc(tmp_db):
    from cloud.license_service import LicenseService
    from cloud.license_store import LicenseStore
    return LicenseService(LicenseStore(tmp_db), FakeEmail()), FakeEmail()


class TestAdminMintEmailsByDefault:
    @pytest.mark.asyncio
    async def test_fresh_mint_sends_email(self, tmp_db):
        from cloud.license_service import LicenseService
        from cloud.license_store import LicenseStore
        email = FakeEmail()
        svc = LicenseService(LicenseStore(tmp_db), email)
        lic = await svc.mint_manual(
            email="test1@example.com", owns_standalone=True,
            cloud_library_months=0, note="test",
        )
        assert lic.owns_standalone is True
        assert len(email.sent) == 1
        assert email.sent[0]["to"] == "test1@example.com"
        assert email.sent[0]["key"] == lic.key

    @pytest.mark.asyncio
    async def test_update_existing_also_sends_email(self, tmp_db):
        from cloud.license_service import LicenseService
        from cloud.license_store import LicenseStore
        email = FakeEmail()
        svc = LicenseService(LicenseStore(tmp_db), email)
        # First mint
        await svc.mint_manual(
            email="test2@example.com", owns_standalone=True,
            cloud_library_months=0, send_email=False,
        )
        email.sent.clear()
        # Second admin call upgrades the existing key (adds music_bingo)
        await svc.mint_manual(
            email="test2@example.com", owns_standalone=True, owns_music_bingo=True,
            cloud_library_months=0,
        )
        assert len(email.sent) == 1
        assert email.sent[0]["owns_music_bingo"] is True

    @pytest.mark.asyncio
    async def test_send_email_false_skips_email(self, tmp_db):
        from cloud.license_service import LicenseService
        from cloud.license_store import LicenseStore
        email = FakeEmail()
        svc = LicenseService(LicenseStore(tmp_db), email)
        await svc.mint_manual(
            email="silent@example.com", owns_standalone=True,
            cloud_library_months=0, send_email=False,
        )
        assert len(email.sent) == 0


class TestResendLicenseEmail:
    @pytest.mark.asyncio
    async def test_resend_existing_key(self, tmp_db):
        from cloud.license_service import LicenseService
        from cloud.license_store import LicenseStore
        email = FakeEmail()
        svc = LicenseService(LicenseStore(tmp_db), email)
        lic = await svc.mint_manual(
            email="lost@example.com", owns_standalone=True,
            cloud_library_months=0, send_email=False,
        )
        ok, msg = await svc.resend_license_email(key=lic.key)
        assert ok is True
        assert msg == "sent"
        assert len(email.sent) == 1
        assert email.sent[0]["key"] == lic.key

    @pytest.mark.asyncio
    async def test_resend_unknown_key_returns_false(self, tmp_db):
        from cloud.license_service import LicenseService
        from cloud.license_store import LicenseStore
        email = FakeEmail()
        svc = LicenseService(LicenseStore(tmp_db), email)
        ok, msg = await svc.resend_license_email(key="BHE-NOPE-NOPE-NOPE-NOPE")
        assert ok is False
        assert msg == "unknown_key"
        assert len(email.sent) == 0

    @pytest.mark.asyncio
    async def test_resend_includes_full_tier_info(self, tmp_db):
        """The resent email must reflect every flag the key has — Cloud
        Library status, every add-on. Otherwise customers think their
        add-ons were dropped."""
        from cloud.license_service import LicenseService
        from cloud.license_store import LicenseStore
        email = FakeEmail()
        svc = LicenseService(LicenseStore(tmp_db), email)
        lic = await svc.mint_manual(
            email="full@example.com",
            owns_standalone=True, owns_music_bingo=True, owns_karaoke=True,
            cloud_library_months=12,
            send_email=False,
        )
        ok, _ = await svc.resend_license_email(key=lic.key)
        assert ok
        assert email.sent[0]["owns_music_bingo"] is True
        assert email.sent[0]["owns_karaoke"] is True
        assert email.sent[0]["cloud_library_active"] is True
        assert email.sent[0]["owns_standalone"] is True
