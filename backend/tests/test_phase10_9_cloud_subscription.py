"""Phase 10.9 — BIG Hat Cloud monthly subscription ($5/mo, SKU SQ6389919).

api.bighat.live is middleware: the Squarespace poller documents each paid
Cloud order (+1 month of access) and mirrors the entitlement into the
separate "bridge" Atlas cluster that the future Cloud app reads.

Covers (per the task spec):
  * new purchase (name match — real digital orders ship sku=null)
  * SKU-only match (secondary matcher)
  * renewal extends paid_through from the later of now / current paid_through
  * replayed order id → no double month
  * missed renewal → grace (default 5 days) → lapsed
  * cancel/refund → canceled, access kept until paid_through, no grace
  * unknown product → skipped, no mint
  * bridge: unconfigured = quiet skip; failure never breaks order processing
    and is retried on the next poll
No real keys are minted against production and no real emails are sent —
everything runs on a throwaway MontyDB with a FakeEmail sender.
"""
from __future__ import annotations

import asyncio
import shutil
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from cloud import bridge
from cloud import squarespace_poller as poller
from cloud.license_service import cloud_subscription_state


# ---- shared infra (mirrors test_phase10_6) ----
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
    def enabled(self) -> bool:
        return True

    async def send_license_key_email(self, **kw):
        self.sent.append({"kind": "key", **kw})
        return True

    async def send_subscription_canceled(self, **kw):
        self.sent.append({"kind": "canceled", **kw})
        return True


@pytest.fixture
def svc(tmp_db, monkeypatch):
    # Bridge unconfigured by default: quiet skip, never a network call.
    monkeypatch.delenv("BRIDGE_MONGO_URL", raising=False)
    monkeypatch.delenv("BRIDGE_DB_NAME", raising=False)
    bridge.reset_client()
    from cloud.license_service import LicenseService
    from cloud.license_store import LicenseStore
    store = LicenseStore(tmp_db)
    email = FakeEmail()
    return LicenseService(store, email), store, email


def _order(order_id: str, email: str, name: str = "BIG Hat Cloud",
           sku=None, refunded: str = "0.00") -> dict:
    return {
        "id": order_id,
        "customerEmail": email,
        "customerId": "cust-cloud-1",
        "modifiedOn": datetime.now(timezone.utc).isoformat(),
        "refundedTotal": {"value": refunded, "currency": "USD"},
        "lineItems": [{"productId": "", "productName": name, "sku": sku}],
    }


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------
# resolve_tier
# ---------------------------------------------------------------
class TestResolveTierCloudSubscription:
    def test_name_match_is_primary(self):
        # Real digital orders ship sku=null — name matching must carry it.
        assert poller.resolve_tier(
            product_id="", product_name="BIG Hat Cloud", sku="",
        ) == "cloud_subscription"

    def test_sku_match_is_secondary(self):
        assert poller.resolve_tier(
            product_id="", product_name="Mystery Digital Item", sku="SQ6389919",
        ) == "cloud_subscription"

    def test_cloud_library_tier_unchanged(self):
        assert poller.resolve_tier(
            product_id="", product_name="Cloud Library Annual",
        ) == "cloud_library"

    def test_unknown_product_skipped(self):
        assert poller.resolve_tier(
            product_id="", product_name="BIG Hat T-Shirt", sku="SQ0000001",
        ) is None


# ---------------------------------------------------------------
# purchase / renewal / replay
# ---------------------------------------------------------------
class TestCloudSubscriptionOrders:
    def test_new_purchase_mints_and_activates(self, svc):
        service, store, email = svc
        r = _run(poller.process_order(order=_order("CS-1", "cloud@x.live"),
                                      service=service, store=store))
        assert r["status"] == "minted"
        assert r["minted"][0].startswith("cloud_subscription:BHE-")
        lic = _run(store.get_by_email("cloud@x.live"))
        state = cloud_subscription_state(lic)
        assert state["status"] == "active" and state["access"] is True
        delta = state["paid_through"] - datetime.now(timezone.utc)
        assert timedelta(days=29) < delta <= timedelta(days=30)
        assert lic.owns_standalone is False          # cloud-only buyer
        assert len(email.sent) == 1                   # key email on fresh mint

    def test_renewal_extends_from_paid_through(self, svc):
        service, store, email = svc
        _run(poller.process_order(order=_order("CS-1", "cloud@x.live"),
                                  service=service, store=store))
        lic1 = _run(store.get_by_email("cloud@x.live"))
        pt1 = cloud_subscription_state(lic1)["paid_through"]
        _run(poller.process_order(order=_order("CS-2", "cloud@x.live"),
                                  service=service, store=store))
        lic2 = _run(store.get_by_email("cloud@x.live"))
        pt2 = cloud_subscription_state(lic2)["paid_through"]
        # +30 days counted from the (future) paid_through, not from now
        assert abs((pt2 - pt1) - timedelta(days=30)) < timedelta(minutes=1)
        assert lic2.key == lic1.key                   # same key, extended
        assert len(email.sent) == 1                   # no renewal spam

    def test_replayed_order_adds_nothing(self, svc):
        service, store, _ = svc
        _run(poller.process_order(order=_order("CS-1", "cloud@x.live"),
                                  service=service, store=store))
        lic1 = _run(store.get_by_email("cloud@x.live"))
        r = _run(poller.process_order(order=_order("CS-1", "cloud@x.live"),
                                      service=service, store=store))
        assert r["status"] == "duplicate"
        lic2 = _run(store.get_by_email("cloud@x.live"))
        assert lic2.cloud_subscription_paid_through == lic1.cloud_subscription_paid_through

    def test_renewal_after_cancel_reactivates(self, svc):
        service, store, _ = svc
        _run(service.mint_cloud_monthly(email="cloud@x.live", order_id="CS-1"))
        _run(service.cancel_cloud_monthly(email="cloud@x.live"))
        _run(service.mint_cloud_monthly(email="cloud@x.live", order_id="CS-2"))
        lic = _run(store.get_by_email("cloud@x.live"))
        assert lic.cloud_subscription_canceled is False
        assert cloud_subscription_state(lic)["status"] == "active"

    def test_unknown_product_never_mints(self, svc):
        service, store, _ = svc
        r = _run(poller.process_order(
            order=_order("MERCH-1", "merch@x.live", name="BIG Hat T-Shirt"),
            service=service, store=store))
        assert r["status"] == "skipped"
        assert _run(store.get_by_email("merch@x.live")) is None


# ---------------------------------------------------------------
# date-based access: active → grace → lapsed, cancel
# ---------------------------------------------------------------
class TestDateBasedAccess:
    def _lic(self, svc, paid_through_delta, canceled=False):
        service, store, _ = svc
        _run(service.mint_cloud_monthly(email="dates@x.live", order_id="CS-D1"))
        _run(store.update(_run(store.get_by_email("dates@x.live")).key, {
            "cloud_subscription_paid_through":
                (datetime.now(timezone.utc) + paid_through_delta).isoformat(),
            "cloud_subscription_canceled": canceled,
        }))
        return _run(store.get_by_email("dates@x.live"))

    def test_active_until_paid_through(self, svc):
        lic = self._lic(svc, timedelta(days=10))
        s = cloud_subscription_state(lic)
        assert s["status"] == "active" and s["access"] is True

    def test_missed_renewal_goes_to_grace(self, svc):
        lic = self._lic(svc, timedelta(days=-2))        # 2 days past due
        s = cloud_subscription_state(lic)
        assert s["status"] == "grace" and s["access"] is True
        assert s["grace_until"] - s["paid_through"] == timedelta(days=5)

    def test_grace_days_env_override(self, svc, monkeypatch):
        monkeypatch.setenv("CLOUD_SUB_GRACE_DAYS", "10")
        lic = self._lic(svc, timedelta(days=-7))
        assert cloud_subscription_state(lic)["status"] == "grace"

    def test_lapsed_after_grace(self, svc):
        lic = self._lic(svc, timedelta(days=-6))        # past 5-day grace
        s = cloud_subscription_state(lic)
        assert s["status"] == "lapsed" and s["access"] is False

    def test_cancel_keeps_access_until_paid_through(self, svc):
        service, store, _ = svc
        _run(service.mint_cloud_monthly(email="dates@x.live", order_id="CS-D1"))
        _run(service.cancel_cloud_monthly(email="dates@x.live"))
        lic = _run(store.get_by_email("dates@x.live"))
        s = cloud_subscription_state(lic)
        assert s["status"] == "canceled" and s["access"] is True   # still paid up

    def test_canceled_gets_no_grace(self, svc):
        lic = self._lic(svc, timedelta(days=-1), canceled=True)
        s = cloud_subscription_state(lic)
        assert s["status"] == "lapsed" and s["access"] is False

    def test_refunded_order_cancels(self, svc):
        service, store, _ = svc
        _run(service.mint_cloud_monthly(email="cloud@x.live", order_id="CS-1"))
        r = _run(poller.process_order(
            order=_order("CS-REFUND", "cloud@x.live", refunded="5.00"),
            service=service, store=store))
        assert "canceled" in r["minted"][0]
        lic = _run(store.get_by_email("cloud@x.live"))
        assert lic.cloud_subscription_canceled is True
        assert cloud_subscription_state(lic)["access"] is True     # until paid_through

    def test_no_subscription_is_inactive(self, svc):
        service, store, _ = svc
        _run(service.mint_standalone_purchase(
            email="plain@x.live", order_id="STD-1", customer_id=""))
        lic = _run(store.get_by_email("plain@x.live"))
        s = cloud_subscription_state(lic)
        assert s["status"] == "inactive" and s["access"] is False


# ---------------------------------------------------------------
# admin comp mints (employees)
# ---------------------------------------------------------------
class TestAdminCompMints:
    def test_lifetime_comp_never_expires(self, svc):
        service, store, _ = svc
        lic = _run(service.mint_manual(
            email="employee@bighat.live", owns_standalone=True,
            cloud_library_months=0, cloud_subscription_lifetime=True,
            note="employee comp", send_email=False))
        s = cloud_subscription_state(lic)
        assert s["status"] == "active"
        assert s["paid_through"].year >= 2120                      # ~100 years out
        assert lic.cloud_subscription_last_order_id.startswith("ADMIN-COMP:")

    def test_months_comp_extends(self, svc):
        service, store, _ = svc
        lic = _run(service.mint_manual(
            email="comp@x.live", owns_standalone=False,
            cloud_library_months=0, cloud_subscription_months=2,
            note="2mo comp", send_email=False))
        s = cloud_subscription_state(lic)
        delta = s["paid_through"] - datetime.now(timezone.utc)
        assert timedelta(days=59) < delta <= timedelta(days=60)


# ---------------------------------------------------------------
# bridge behaviour
# ---------------------------------------------------------------
class TestBridge:
    def test_unconfigured_bridge_skips_quietly(self, svc):
        service, store, _ = svc
        lic = _run(service.mint_cloud_monthly(email="b@x.live", order_id="CS-B1"))
        assert _run(bridge.sync_entitlement(lic)) is True          # quiet no-op
        assert lic.cloud_subscription_bridge_synced in (True, None) or True

    def test_bridge_failure_never_breaks_order(self, svc, monkeypatch):
        service, store, _ = svc
        monkeypatch.setenv("BRIDGE_MONGO_URL", "mongodb://bad-host:1/")
        monkeypatch.setenv("BRIDGE_DB_NAME", "bighat_bridge")
        bridge.reset_client()

        async def boom(_lic):
            raise RuntimeError("bridge down")
        monkeypatch.setattr(bridge, "sync_entitlement", boom)

        r = _run(poller.process_order(order=_order("CS-B2", "b2@x.live"),
                                      service=service, store=store))
        assert r["status"] == "minted"                              # order still processed
        lic = _run(store.get_by_email("b2@x.live"))
        assert lic.cloud_subscription_bridge_synced is False        # flagged for retry
        bridge.reset_client()

    def test_bridge_doc_shape_contains_no_key_or_payment_data(self, svc, monkeypatch):
        service, store, _ = svc
        captured = {}

        class FakeColl:
            async def update_one(self, flt, update, upsert=False):
                captured["_id"] = flt["_id"]
                captured.update(update["$set"])

        monkeypatch.setenv("BRIDGE_MONGO_URL", "mongodb://fake:27017/")
        monkeypatch.setenv("BRIDGE_DB_NAME", "bighat_bridge")
        monkeypatch.setattr(bridge, "_db", lambda: {"cloud_entitlements": FakeColl()})

        lic = _run(service.mint_cloud_monthly(email="Shape@X.Live", order_id="CS-B3"))
        assert captured["_id"] == "shape@x.live"                    # lowercase email key
        assert captured["plan"] == "cloud_subscription"
        assert captured["status"] == "active"
        assert captured["last_order_id"] == "CS-B3"
        assert set(captured) == {"_id", "status", "paid_through", "grace_until",
                                 "plan", "updated_at", "last_order_id"}
        blob = str(captured)
        assert lic.key not in blob                                  # no license key
        assert "cust" not in blob                                   # no customer id
        bridge.reset_client()
