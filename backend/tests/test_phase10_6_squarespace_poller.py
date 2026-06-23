"""Phase 10.6 — Squarespace Orders poller regression tests.

Locks in the architecture decision to switch from webhooks → polling,
because Squarespace's webhook subscriptions API requires building a full
OAuth Extension (not feasible for a single-merchant setup).

Tests cover:
  * `resolve_tier()` — productId map + name-substring fallback
  * `process_order()` — mints + idempotency on repeat calls
  * `run_once()` — full poll cycle with a mocked Squarespace HTTP API
  * State persistence (`load_state` / `save_state`)
  * High-water mark advancement and pagination
"""
from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
import pytest

from cloud import squarespace_poller as poller


# ---- shared infra ----
@pytest.fixture
def tmp_db():
    from native.async_monty import AsyncMontyClient
    from montydb import MontyClient, set_storage

    tmpdir = Path(tempfile.mkdtemp(prefix="bighat-phase10_6-"))
    repo = tmpdir / "repo"
    repo.mkdir()
    set_storage(repository=str(repo), storage="sqlite")
    sync = MontyClient(str(repo))
    client = AsyncMontyClient(sync)
    db = client["test_phase10_6"]
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
def svc(tmp_db):
    from cloud.license_service import LicenseService
    from cloud.license_store import LicenseStore
    store = LicenseStore(tmp_db)
    email = FakeEmail()
    return LicenseService(store, email), store, email


# ---------------------------------------------------------------
# resolve_tier
# ---------------------------------------------------------------
class TestResolveTier:
    def test_productid_map_wins_over_name(self, monkeypatch):
        monkeypatch.setenv("LICENSE_PRODUCT_MAP",
                           '{"prod-123":"music_bingo"}')
        # name says standalone, but map says music_bingo → map wins
        assert poller.resolve_tier(
            product_id="prod-123",
            product_name="BIG Hat Entertainment",
        ) == "music_bingo"

    def test_name_fallback_when_id_not_mapped(self, monkeypatch):
        monkeypatch.setenv("LICENSE_PRODUCT_MAP", "{}")
        assert poller.resolve_tier(
            product_id="unknown",
            product_name="Music Bingo Add-on",
        ) == "music_bingo"
        assert poller.resolve_tier(
            product_id="unknown",
            product_name="Karaoke Subscription",
        ) == "karaoke"
        assert poller.resolve_tier(
            product_id="unknown",
            product_name="Cloud Library Monthly",
        ) == "cloud_library"
        assert poller.resolve_tier(
            product_id="unknown",
            product_name="BIG Hat Entertainment",
        ) == "standalone"

    def test_returns_none_for_merch(self, monkeypatch):
        monkeypatch.setenv("LICENSE_PRODUCT_MAP", "{}")
        # Physical merch products should NOT trigger a license mint.
        assert poller.resolve_tier(
            product_id="prod-tshirt",
            product_name="BIG Hat All Star Jersey",
        ) is None

    def test_default_map_includes_live_standalone_productid(self, monkeypatch):
        # The user's real Squarespace product ID. Defaults must work even
        # without LICENSE_PRODUCT_MAP being set in env.
        monkeypatch.delenv("LICENSE_PRODUCT_MAP", raising=False)
        assert poller.resolve_tier(
            product_id="69f95125f691fe20c13aef37",
            product_name="anything",
        ) == "standalone"


# ---------------------------------------------------------------
# process_order
# ---------------------------------------------------------------
class TestProcessOrder:
    @pytest.mark.asyncio
    async def test_mints_standalone_and_idempotent(self, svc, monkeypatch):
        monkeypatch.delenv("LICENSE_PRODUCT_MAP", raising=False)
        service, store, email = svc
        order = {
            "id": "order-abc",
            "customerEmail": "buyer@example.com",
            "customerId": "cust-1",
            "modifiedOn": "2026-06-22T05:37:48.149Z",
            "lineItems": [{
                "productId": "69f95125f691fe20c13aef37",
                "productName": "BIG Hat Entertainment",
                "sku": None,
            }],
        }
        r1 = await poller.process_order(order=order, service=service, store=store)
        r2 = await poller.process_order(order=order, service=service, store=store)
        assert r1["status"] == "minted"
        assert any("standalone:" in m for m in r1["minted"])
        assert r2["status"] == "duplicate"
        # exactly one email
        assert len(email.sent) == 1
        assert email.sent[0]["to"] == "buyer@example.com"

    @pytest.mark.asyncio
    async def test_skips_merch_only_orders(self, svc, monkeypatch):
        monkeypatch.delenv("LICENSE_PRODUCT_MAP", raising=False)
        service, store, email = svc
        order = {
            "id": "order-merch",
            "customerEmail": "tshirt-fan@example.com",
            "modifiedOn": "2026-06-22T05:37:48.149Z",
            "lineItems": [{
                "productId": "prod-tshirt",
                "productName": "BIG Hat All Star Jersey",
                "sku": "TSHIRT-001",
            }],
        }
        r = await poller.process_order(order=order, service=service, store=store)
        assert r["status"] == "skipped"
        assert len(email.sent) == 0

    @pytest.mark.asyncio
    async def test_mixed_cart_mints_only_software(self, svc, monkeypatch):
        monkeypatch.delenv("LICENSE_PRODUCT_MAP", raising=False)
        service, store, email = svc
        order = {
            "id": "order-mix",
            "customerEmail": "mix@example.com",
            "modifiedOn": "2026-06-22T05:37:48.149Z",
            "lineItems": [
                {"productId": "prod-tshirt", "productName": "All Star Jersey"},
                {"productId": "69f95125f691fe20c13aef37",
                 "productName": "BIG Hat Entertainment"},
            ],
        }
        r = await poller.process_order(order=order, service=service, store=store)
        assert r["status"] == "minted"
        assert len(r["minted"]) == 1
        assert "standalone:" in r["minted"][0]
        assert len(r["skipped"]) == 1


# ---------------------------------------------------------------
# run_once — full poll cycle with mocked HTTP
# ---------------------------------------------------------------
def _mock_transport(orders: list[dict], pagination: dict | None = None) -> httpx.MockTransport:
    """httpx mock that returns the given orders as Squarespace would."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "result": orders,
            "pagination": pagination or {"hasNextPage": False},
        })
    return httpx.MockTransport(handler)


class TestRunOnce:
    @pytest.mark.asyncio
    async def test_full_cycle_against_real_shaped_payload(self, svc, monkeypatch):
        monkeypatch.delenv("LICENSE_PRODUCT_MAP", raising=False)
        service, store, email = svc

        # Real-shape Squarespace order from your actual order #38.
        real_order = {
            "id": "6a38ca2c69bad66b65cca5fc",
            "orderNumber": "38",
            "createdOn": "2026-06-22T05:37:47.800Z",
            "modifiedOn": "2026-06-22T05:37:48.149Z",
            "customerEmail": "sellards@bighat.live",
            "customerId": "6908eb678a9f9839d439d08f",
            "fulfillmentStatus": "FULFILLED",
            "lineItems": [{
                "id": "6a38c9f39be3601e701b5c44",
                "productId": "69f95125f691fe20c13aef37",
                "productName": "BIG Hat Entertainment",
                "sku": None,
                "quantity": 1,
                "unitPricePaid": {"currency": "USD", "value": "49.99"},
            }],
        }
        client = httpx.AsyncClient(transport=_mock_transport([real_order]))
        try:
            summary = await poller.run_once(
                service=service, store=store, api_key="fake", client=client,
            )
        finally:
            await client.aclose()

        assert summary["ok"] is True
        assert summary["fetched"] == 1
        assert summary["minted"] == 1
        assert summary["duplicate"] == 0
        assert summary["results"][0]["email"] == "sellards@bighat.live"
        assert "2026-06-22" in summary["high_water"]
        # State was persisted
        state = await poller.load_state(store)
        assert state["total_fetched_lifetime"] == 1
        assert state["total_minted_lifetime"] == 1
        # Email was sent
        assert len(email.sent) == 1

    @pytest.mark.asyncio
    async def test_second_run_picks_up_high_water_and_skips_old(self, svc, monkeypatch):
        monkeypatch.delenv("LICENSE_PRODUCT_MAP", raising=False)
        service, store, _ = svc
        order = {
            "id": "ord-X", "customerEmail": "x@example.com",
            "modifiedOn": "2026-06-22T05:00:00.000Z",
            "lineItems": [{"productId": "69f95125f691fe20c13aef37",
                           "productName": "BIG Hat Entertainment"}],
        }
        c1 = httpx.AsyncClient(transport=_mock_transport([order]))
        try:
            await poller.run_once(service=service, store=store, api_key="x", client=c1)
        finally:
            await c1.aclose()

        # Second run returns the same order again (Squarespace will keep
        # returning recently-modified orders) — must be deduped.
        c2 = httpx.AsyncClient(transport=_mock_transport([order]))
        try:
            r2 = await poller.run_once(service=service, store=store, api_key="x", client=c2)
        finally:
            await c2.aclose()
        assert r2["minted"] == 0
        assert r2["duplicate"] == 1

    @pytest.mark.asyncio
    async def test_no_api_key_returns_error(self, svc, monkeypatch):
        monkeypatch.delenv("SQUARESPACE_API_KEY", raising=False)
        service, store, _ = svc
        r = await poller.run_once(service=service, store=store, api_key="")
        assert r["ok"] is False
        assert "SQUARESPACE_API_KEY" in r["error"]

    @pytest.mark.asyncio
    async def test_http_error_persists_last_error(self, svc, monkeypatch):
        monkeypatch.delenv("LICENSE_PRODUCT_MAP", raising=False)
        service, store, _ = svc

        def boom(request):
            return httpx.Response(500, json={"err": "boom"})
        c = httpx.AsyncClient(transport=httpx.MockTransport(boom))
        try:
            r = await poller.run_once(service=service, store=store,
                                      api_key="x", client=c)
        finally:
            await c.aclose()
        assert r["ok"] is False
        state = await poller.load_state(store)
        assert "last_error" in state
        assert state["last_error"]


# ---------------------------------------------------------------
# State persistence (MontyDB _id immutability regression)
# ---------------------------------------------------------------
class TestStatePersistence:
    @pytest.mark.asyncio
    async def test_save_state_is_idempotent_under_montydb(self, svc):
        _, store, _ = svc
        # First call inserts; subsequent calls must NOT raise the MontyDB
        # `WriteError: Performing an update on the path '_id' ...` regression.
        await poller.save_state(store, {"last_modified_at": "2026-06-22T00:00:00Z",
                                         "total_fetched_lifetime": 1})
        await poller.save_state(store, {"last_modified_at": "2026-06-23T00:00:00Z",
                                         "total_fetched_lifetime": 2})
        loaded = await poller.load_state(store)
        assert loaded["last_modified_at"] == "2026-06-23T00:00:00Z"
        assert loaded["total_fetched_lifetime"] == 2
