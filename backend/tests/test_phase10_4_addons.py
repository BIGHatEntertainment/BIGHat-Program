"""Phase 10.4 — Music Bingo + Karaoke add-on licensing tests.

Covers:
  * SKU-clean rename (`BHE-STANDALONE`, `BHE-CLOUD-LIBRARY`,
    `BHE-MUSIC-BINGO`, `BHE-KARAOKE`)
  * `mint_addon_purchase` for both add-ons (idempotent, fresh customer,
    upgrade-existing-key)
  * Webhook dispatch for the two new SKUs
  * License model new fields (`owns_music_bingo`, `owns_karaoke`,
    `squarespace_*_order_id`)
  * `is_premium_active()` standalone-tier gating logic for the new flags:
    `music_bingo_enabled`, `karaoke_enabled`, `bingo_story_enabled`,
    `karaoke_story_enabled`. All require `owns_standalone=True`.
  * `_apply_cloud_response_to_local_state` correctly mirrors all 4
    feature flags + 2 ownership keys into `system_config.json`.
"""
from __future__ import annotations

import shutil
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


# ---------- DB fixture ----------
@pytest.fixture
def tmp_db():
    from native.async_monty import AsyncMontyClient
    from montydb import MontyClient, set_storage

    tmpdir = Path(tempfile.mkdtemp(prefix="bighat-license-addon-"))
    repo = tmpdir / "repo"
    repo.mkdir()
    set_storage(repository=str(repo), storage="sqlite")
    sync = MontyClient(str(repo))
    client = AsyncMontyClient(sync)
    yield client["test_addons"]
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

    async def send_license_key_email(self, *, to, key, owns_standalone,
                                     cloud_library_active,
                                     owns_music_bingo=False,
                                     owns_karaoke=False):
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


# ===================================================================
# 1. SKU constants are clean (price-decoupled)
# ===================================================================
class TestSkuConstants:
    def test_no_price_in_sku_strings(self):
        from cloud import config
        for sku in (config.SKU_STANDALONE, config.SKU_CLOUD_LIBRARY,
                    config.SKU_MUSIC_BINGO, config.SKU_KARAOKE):
            # No "2499" / "4999" / "5MO" suffixes
            assert not any(c.isdigit() for c in sku.split("-")[-1]), \
                f"SKU contains price: {sku}"
        assert config.SKU_STANDALONE == "BHE-STANDALONE"
        assert config.SKU_CLOUD_LIBRARY == "BHE-CLOUD-LIBRARY"
        assert config.SKU_MUSIC_BINGO == "BHE-MUSIC-BINGO"
        assert config.SKU_KARAOKE == "BHE-KARAOKE"


# ===================================================================
# 2. mint_addon_purchase
# ===================================================================
class TestMintAddon:
    @pytest.mark.asyncio
    async def test_music_bingo_addon_for_existing_customer(self, tmp_db):
        from cloud.license_service import LicenseService
        from cloud.license_store import LicenseStore
        store = LicenseStore(tmp_db)
        await store.ensure_indexes()
        email = FakeEmail()
        svc = LicenseService(store, email)
        # Customer first buys the standalone
        base = await svc.mint_standalone_purchase(
            email="alice@e.com", order_id="ord_base",
        )
        assert base.owns_music_bingo is False
        # Then adds the music bingo add-on
        upgraded = await svc.mint_addon_purchase(
            addon="music_bingo", email="alice@e.com",
            order_id="ord_mb",
        )
        assert upgraded.key == base.key
        assert upgraded.owns_standalone is True
        assert upgraded.owns_music_bingo is True
        assert upgraded.squarespace_music_bingo_order_id == "ord_mb"
        # Email sent for the upgrade
        addon_emails = [e for e in email.sent if e["kind"] == "key"
                        and e["owns_music_bingo"]]
        assert len(addon_emails) == 1

    @pytest.mark.asyncio
    async def test_karaoke_addon_idempotent_replay(self, tmp_db):
        from cloud.license_service import LicenseService
        from cloud.license_store import LicenseStore
        store = LicenseStore(tmp_db)
        svc = LicenseService(store, FakeEmail())
        await svc.mint_standalone_purchase(email="b@e.com", order_id="ob")
        a = await svc.mint_addon_purchase(addon="karaoke", email="b@e.com",
                                           order_id="ord_k")
        b = await svc.mint_addon_purchase(addon="karaoke", email="b@e.com",
                                           order_id="ord_k")
        assert a.key == b.key
        assert a.owns_karaoke is True
        # Replay must NOT toggle anything off or send a duplicate email
        # (mint_addon_purchase short-circuits on order_id replay)

    @pytest.mark.asyncio
    async def test_addon_only_no_standalone_yet(self, tmp_db):
        """Customer might buy the add-on first by accident. Cloud records
        the ownership; desktop will gate access until they also buy the base."""
        from cloud.license_service import LicenseService
        from cloud.license_store import LicenseStore
        store = LicenseStore(tmp_db)
        svc = LicenseService(store, FakeEmail())
        lic = await svc.mint_addon_purchase(
            addon="music_bingo", email="early@e.com", order_id="ord_e",
        )
        assert lic.owns_standalone is False
        assert lic.owns_music_bingo is True

    @pytest.mark.asyncio
    async def test_unknown_addon_raises(self, tmp_db):
        from cloud.license_service import LicenseService
        from cloud.license_store import LicenseStore
        store = LicenseStore(tmp_db)
        svc = LicenseService(store, FakeEmail())
        with pytest.raises(ValueError):
            await svc.mint_addon_purchase(
                addon="dance_party", email="d@e.com", order_id="o",
            )

    @pytest.mark.asyncio
    async def test_buying_both_addons(self, tmp_db):
        """Same customer buys standalone + both add-ons in three orders."""
        from cloud.license_service import LicenseService
        from cloud.license_store import LicenseStore
        store = LicenseStore(tmp_db)
        svc = LicenseService(store, FakeEmail())
        await svc.mint_standalone_purchase(email="combo@e.com", order_id="o1")
        await svc.mint_addon_purchase(addon="music_bingo", email="combo@e.com",
                                       order_id="o2")
        final = await svc.mint_addon_purchase(addon="karaoke", email="combo@e.com",
                                               order_id="o3")
        assert final.owns_standalone is True
        assert final.owns_music_bingo is True
        assert final.owns_karaoke is True
        assert final.squarespace_standalone_order_id == "o1"
        assert final.squarespace_music_bingo_order_id == "o2"
        assert final.squarespace_karaoke_order_id == "o3"


# ===================================================================
# 3. Webhook dispatch handles the new SKUs
# ===================================================================
class TestWebhookDispatchAddons:
    @pytest.mark.asyncio
    async def test_order_with_all_four_skus(self, tmp_db):
        """One Squarespace order containing the base + both add-ons +
        cloud library — all four mints should fire."""
        from cloud.license_service import LicenseService
        from cloud.license_store import LicenseStore
        from cloud.squarespace_webhook import WebhookHandler
        store = LicenseStore(tmp_db)
        await store.ensure_indexes()
        email = FakeEmail()
        svc = LicenseService(store, email)
        h = WebhookHandler(svc, store)

        result = await h.handle({
            "id": "evt_combo", "topic": "order.create",
            "data": {"order": {
                "id": "ord_combo", "customerEmail": "all@example.com",
                "lineItems": [
                    {"sku": "BHE-STANDALONE"},
                    {"sku": "BHE-MUSIC-BINGO"},
                    {"sku": "BHE-KARAOKE"},
                    {"sku": "BHE-CLOUD-LIBRARY"},
                ],
            }},
        })
        assert result["ok"] is True
        assert result["status"] == "minted"
        # 4 mints reported
        results = result["results"]
        kinds = sorted({r.split(":")[0] for r in results})
        assert kinds == ["cloud", "karaoke", "music_bingo", "standalone"]

        lic = await store.get_by_email("all@example.com")
        assert lic.owns_standalone is True
        assert lic.owns_music_bingo is True
        assert lic.owns_karaoke is True
        assert lic.cloud_library_status == "active"

    @pytest.mark.asyncio
    async def test_addon_only_webhook(self, tmp_db):
        from cloud.license_service import LicenseService
        from cloud.license_store import LicenseStore
        from cloud.squarespace_webhook import WebhookHandler
        store = LicenseStore(tmp_db)
        svc = LicenseService(store, FakeEmail())
        h = WebhookHandler(svc, store)
        r = await h.handle({
            "id": "evt_kar", "topic": "order.create",
            "data": {"order": {
                "id": "ord_kar", "customerEmail": "kar@e.com",
                "lineItems": [{"sku": "BHE-KARAOKE"}],
            }},
        })
        assert r["status"] == "minted"
        lic = await store.get_by_email("kar@e.com")
        assert lic.owns_karaoke is True
        assert lic.owns_standalone is False  # no base yet


# ===================================================================
# 4. Desktop gating — is_premium_active() new flags
# ===================================================================
class TestDesktopAddonGating:
    @pytest.fixture
    def isolated_config(self):
        from native.config import config_manager
        import json
        snap = json.loads(json.dumps(config_manager.config))
        config_manager.config["license_status"] = {}
        config_manager.config["subscription"] = {}
        config_manager.save_config()
        yield config_manager
        config_manager.config = snap
        config_manager.save_config()

    def _seed_subscription(self, cfg, **overrides):
        sub = {
            "active": True, "tier": "standalone",
            "owns_standalone": True,
            "owns_music_bingo": False,
            "owns_karaoke": False,
            "story_generator_enabled": True,
            "music_bingo_enabled": False,
            "karaoke_enabled": False,
            "bingo_story_enabled": False,
            "karaoke_story_enabled": False,
        }
        sub.update(overrides)
        cfg.config["subscription"] = sub
        cfg.save_config()

    def test_music_bingo_blocked_without_addon_purchase(self, isolated_config):
        from native.subscription import is_premium_active
        self._seed_subscription(isolated_config)
        assert is_premium_active("story_generator_enabled") is True
        assert is_premium_active("music_bingo_enabled") is False
        assert is_premium_active("bingo_story_enabled") is False

    def test_music_bingo_unlocked_with_both_owns_flags(self, isolated_config):
        from native.subscription import is_premium_active
        self._seed_subscription(isolated_config,
                                 owns_music_bingo=True,
                                 music_bingo_enabled=True,
                                 bingo_story_enabled=True)
        assert is_premium_active("music_bingo_enabled") is True
        assert is_premium_active("bingo_story_enabled") is True

    def test_addon_blocked_without_standalone_base(self, isolated_config):
        """Customer who only bought the add-on (no base): gating blocks."""
        from native.subscription import is_premium_active
        self._seed_subscription(isolated_config,
                                 active=False, tier="free",
                                 owns_standalone=False,
                                 owns_music_bingo=True,
                                 music_bingo_enabled=False,
                                 story_generator_enabled=False)
        assert is_premium_active("music_bingo_enabled") is False
        assert is_premium_active("bingo_story_enabled") is False
        assert is_premium_active("story_generator_enabled") is False

    def test_karaoke_independent_of_music_bingo(self, isolated_config):
        from native.subscription import is_premium_active
        self._seed_subscription(isolated_config,
                                 owns_karaoke=True,
                                 karaoke_enabled=True,
                                 karaoke_story_enabled=True)
        # Owns karaoke ≠ owns music bingo
        assert is_premium_active("karaoke_enabled") is True
        assert is_premium_active("music_bingo_enabled") is False

    def test_addon_features_immune_to_offline_grace(self, isolated_config):
        """Add-ons are one-time purchases — never expire over offline window."""
        from native.subscription import is_premium_active
        # Stale validation 365 days old
        self._seed_subscription(
            isolated_config,
            owns_music_bingo=True, music_bingo_enabled=True,
            bingo_story_enabled=True,
            last_cloud_validated_at=(
                datetime.now(timezone.utc) - timedelta(days=365)
            ).isoformat(),
        )
        assert is_premium_active("music_bingo_enabled") is True
        assert is_premium_active("bingo_story_enabled") is True


# ===================================================================
# 5. _apply_cloud_response_to_local_state mirrors all 4 feature flags
# ===================================================================
class TestCloudResponseMirror:
    @pytest.fixture
    def isolated_config(self):
        from native.config import config_manager
        import json
        snap = json.loads(json.dumps(config_manager.config))
        config_manager.config["license_status"] = {}
        config_manager.config["subscription"] = {}
        config_manager.save_config()
        yield config_manager
        config_manager.config = snap
        config_manager.save_config()

    def test_full_owner_unlocks_all_addon_flags(self, isolated_config):
        from native.router import _apply_cloud_response_to_local_state
        resp = {
            "ok": True,
            "owns_standalone": True,
            "owns_music_bingo": True,
            "owns_karaoke": True,
            "cloud_library_active": True,
            "cloud_library_expires_at": (datetime.now(timezone.utc)
                                         + timedelta(days=30)).isoformat(),
            "max_seats": 5, "active_seats": 1,
            "revalidate_after": (datetime.now(timezone.utc)
                                 + timedelta(days=7)).isoformat(),
        }
        _apply_cloud_response_to_local_state(
            resp, license_key="BHE-AAAA-BBBB-CCCC-DDDD", email="owner@e.com",
        )
        sub = isolated_config.config["subscription"]
        assert sub["owns_standalone"] is True
        assert sub["owns_music_bingo"] is True
        assert sub["owns_karaoke"] is True
        assert sub["music_bingo_enabled"] is True
        assert sub["karaoke_enabled"] is True
        assert sub["bingo_story_enabled"] is True
        assert sub["karaoke_story_enabled"] is True
        assert sub["sharepoint_enabled"] is True
        assert sub["story_generator_enabled"] is True

    def test_addon_owner_without_base_gets_no_addon_flags(self, isolated_config):
        from native.router import _apply_cloud_response_to_local_state
        resp = {
            "ok": True,
            "owns_standalone": False,
            "owns_music_bingo": True,    # owned but useless without base
            "owns_karaoke": False,
            "cloud_library_active": False,
            "max_seats": 3, "active_seats": 1,
            "revalidate_after": (datetime.now(timezone.utc)
                                 + timedelta(days=7)).isoformat(),
        }
        _apply_cloud_response_to_local_state(
            resp, license_key="BHE-EEEE-FFFF-AAAA-BBBB", email="early@e.com",
        )
        sub = isolated_config.config["subscription"]
        assert sub["owns_music_bingo"] is True
        assert sub["music_bingo_enabled"] is False  # gated on owns_standalone
        assert sub["bingo_story_enabled"] is False
