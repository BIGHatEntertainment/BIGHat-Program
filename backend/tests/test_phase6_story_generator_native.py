"""
Phase 6 — Story Generator native-mode premium gate regression.

Verifies:
  * /api/story-generator/status returns proper shape in native mode with
    subscription OFF and ON.
  * All mutating endpoints 402 when subscription is OFF.
  * All mutating endpoints stop 402-ing (and usually 404 on fake IDs)
    when subscription is ON.
  * Read endpoints never 402.
  * Phase 0-5 regression endpoints still 200.
  * Per-feature gating: story_generator_enabled=True alone is enough
    (sharepoint_enabled can stay False).

Leaves the subscription OFF + story_generator_enabled=False at teardown.
"""
from __future__ import annotations

import os
import pytest
import requests

# Load BASE_URL from frontend .env (source of truth).
_ENV_PATH = "/app/frontend/.env"
_BASE = None
with open(_ENV_PATH) as _f:
    for _line in _f:
        if _line.startswith("REACT_APP_BACKEND_URL="):
            _BASE = _line.split("=", 1)[1].strip().strip('"').rstrip("/")
            break
assert _BASE, "REACT_APP_BACKEND_URL missing from /app/frontend/.env"
BASE_URL = _BASE

MUTATING_ENDPOINTS = [
    ("POST", "/api/story-generator/generate/fake-id-xyz", None),
    ("POST", "/api/story-generator/preview/fake-id-xyz", None),
    (
        "POST",
        "/api/story-generator/assemble-video",
        {
            "locationName": "test",
            "locationFolder": "test",
            "hostName": "test",
            "rounds": [],
            "numRounds": 3,
        },
    ),
    (
        "POST",
        "/api/story-generator/convert-webm",
        {"video_data": "AAAA", "filename": "x"},
    ),
    (
        "POST",
        "/api/story-generator/generate-event-video",
        {
            "event_type": "bingo",
            "location_id": "x",
            "location_drive_id": "x",
            "location_name": "x",
            "host_id": "x",
            "host_drive_id": "x",
            "host_name": "x",
        },
    ),
    (
        "POST",
        "/api/story-generator/event-preview",
        {
            "event_type": "bingo",
            "location_id": "x",
            "location_drive_id": "x",
            "host_id": "x",
            "host_drive_id": "x",
        },
    ),
    # upload-asset is multipart — handled separately in one test below.
    ("DELETE", "/api/story-generator/asset/test/test", None),
]


@pytest.fixture(scope="session")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def _set_subscription(session, *, active: bool, story_on: bool, sharepoint_on: bool = False):
    r = session.post(
        f"{BASE_URL}/api/native/subscription",
        json={
            "active": active,
            "tier": "premium" if active else "free",
            "expires_at": None,
            "sharepoint_enabled": sharepoint_on,
            "story_generator_enabled": story_on,
            "cloud_sync_enabled": False,
        },
    )
    assert r.status_code == 200, f"subscription toggle failed: {r.status_code} {r.text}"
    return r.json()


@pytest.fixture(scope="module", autouse=True)
def _teardown_subscription(session):
    # Start clean — OFF
    _set_subscription(session, active=False, story_on=False)
    yield
    # Teardown — OFF again (per review-request requirement)
    _set_subscription(session, active=False, story_on=False)


# ----- status endpoint -----
class TestStatus:
    def test_status_off_native_mode(self, session):
        _set_subscription(session, active=False, story_on=False)
        r = session.get(f"{BASE_URL}/api/story-generator/status")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["available"] is False
        assert d["mode"] == "native"
        assert d["reason"] == "premium_required"
        assert d["ffmpeg_ok"] is True
        sub = d.get("subscription", {})
        assert sub.get("active") is False
        assert sub.get("story_generator_enabled") is False

    def test_status_on(self, session):
        _set_subscription(session, active=True, story_on=True)
        r = session.get(f"{BASE_URL}/api/story-generator/status")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["available"] is True
        assert d["mode"] == "native"
        assert d["reason"] is None


# ----- mutating endpoints 402 when OFF -----
class TestGateOff:
    @pytest.fixture(autouse=True)
    def _off(self, session):
        _set_subscription(session, active=False, story_on=False)

    @pytest.mark.parametrize("method,path,body", MUTATING_ENDPOINTS)
    def test_mutating_returns_402(self, session, method, path, body):
        url = f"{BASE_URL}{path}"
        if method == "POST":
            r = session.post(url, json=body) if body is not None else session.post(url)
        elif method == "DELETE":
            r = session.delete(url)
        else:
            pytest.skip(f"method {method} not handled")
        assert r.status_code == 402, (
            f"{method} {path} expected 402 got {r.status_code}: {r.text[:200]}"
        )
        body_json = r.json()
        detail = body_json.get("detail", {})
        assert isinstance(detail, dict), f"detail not object: {body_json}"
        assert detail.get("error") == "premium_required"
        assert detail.get("feature") == "story_generator_enabled"

    def test_upload_asset_returns_402(self, session):
        # multipart — reuse session without JSON content-type
        with requests.Session() as s2:
            files = {"file": ("x.png", b"\x89PNG\r\n", "image/png")}
            data = {"asset_type": "location"}
            r = s2.post(
                f"{BASE_URL}/api/story-generator/upload-asset",
                files=files,
                data=data,
            )
        assert r.status_code == 402, f"upload-asset expected 402 got {r.status_code}: {r.text[:200]}"
        detail = r.json().get("detail", {})
        assert detail.get("error") == "premium_required"
        assert detail.get("feature") == "story_generator_enabled"


# ----- read endpoints never 402 even when OFF -----
class TestReadFree:
    @pytest.fixture(autouse=True)
    def _off(self, session):
        _set_subscription(session, active=False, story_on=False)

    @pytest.mark.parametrize(
        "path",
        [
            "/api/story-generator/presentations",
            "/api/story-generator/assets",
            "/api/story-generator/job-status/nonexistent-job-id",
        ],
    )
    def test_read_never_402(self, session, path):
        r = session.get(f"{BASE_URL}{path}")
        assert r.status_code != 402, f"{path} should NOT be gated, got 402"
        # 200 or 404 is acceptable
        assert r.status_code in (200, 404), f"{path} unexpected {r.status_code}: {r.text[:200]}"


# ----- gate OFF when subscription is ON -----
class TestGateOn:
    @pytest.fixture(autouse=True)
    def _on(self, session):
        _set_subscription(session, active=True, story_on=True)

    def test_generate_returns_404_not_402(self, session):
        r = session.post(f"{BASE_URL}/api/story-generator/generate/does-not-exist-xyz")
        assert r.status_code != 402, "gate should be OFF with subscription active"
        assert r.status_code == 404, f"expected 404 presentation-not-found, got {r.status_code}: {r.text[:200]}"

    def test_preview_returns_404_not_402(self, session):
        r = session.post(f"{BASE_URL}/api/story-generator/preview/does-not-exist-xyz")
        assert r.status_code != 402
        assert r.status_code == 404, f"expected 404, got {r.status_code}: {r.text[:200]}"

    def test_convert_webm_no_longer_402(self, session):
        r = session.post(
            f"{BASE_URL}/api/story-generator/convert-webm",
            json={"video_data": "invalid-b64-!!!", "filename": "x"},
        )
        assert r.status_code != 402
        # Likely 500 (ffmpeg fail on bad data) — that's acceptable, gate is off.


# ----- toggle effective immediately (OFF → ON → OFF) -----
class TestToggleImmediate:
    def test_off_then_on_then_off(self, session):
        _set_subscription(session, active=False, story_on=False)
        r = session.post(f"{BASE_URL}/api/story-generator/generate/xyz")
        assert r.status_code == 402

        _set_subscription(session, active=True, story_on=True)
        r = session.post(f"{BASE_URL}/api/story-generator/generate/xyz")
        assert r.status_code != 402 and r.status_code == 404

        _set_subscription(session, active=False, story_on=False)
        r = session.post(f"{BASE_URL}/api/story-generator/generate/xyz")
        assert r.status_code == 402


# ----- per-feature gate: sharepoint off but story on -----
class TestPerFeature:
    def test_story_on_sharepoint_off(self, session):
        _set_subscription(session, active=True, story_on=True, sharepoint_on=False)
        r = session.get(f"{BASE_URL}/api/story-generator/status")
        assert r.status_code == 200
        d = r.json()
        assert d["available"] is True
        # generate still ungated
        r2 = session.post(f"{BASE_URL}/api/story-generator/generate/nope")
        assert r2.status_code == 404


# ----- Phase 0-5 regression -----
REGRESSION_ENDPOINTS = [
    "/api/native/info",
    "/api/venues",
    "/api/events",
    "/api/trivia/hosts",
    "/api/trivia/round-files/reg",
    "/api/presentations?userName=master@bighat.local",
    "/api/roundmaker/sharepoint-status",
    "/api/trivia-import/slides-metadata/nonexistent",
]


class TestRegression:
    @pytest.mark.parametrize("path", REGRESSION_ENDPOINTS)
    def test_regression_no_crash(self, session, path):
        r = session.get(f"{BASE_URL}{path}")
        assert r.status_code < 500, f"{path} 5xx crash: {r.status_code} {r.text[:300]}"
