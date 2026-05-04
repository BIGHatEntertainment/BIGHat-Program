"""
Phase 7 — SharePoint Hybrid Sync tests.

Covers /api/native/sync/{status,plan,pull,push} with:
  - premium gate (402 when off, 200 when on)
  - fixture-backed pull/push round trip + convergence
  - sync state persistence
  - delete_missing behaviour
  - path traversal safety
  - subscription flip on/off without restart
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE_URL:
    # Fall back to frontend .env (mirrors docs)
    with open("/app/frontend/.env") as fh:
        for line in fh:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip()
                break
BASE_URL = (BASE_URL or "").rstrip("/")

FIXTURE_ROOT = Path("/app/backend/native/data/cloud_fixture")
LOCAL_ROOT = Path("/app/backend/native/data/assets")
SYNC_ROOT = "01_Trivia/Web App/00_Builder"
TEST_REL_DIR = "01_Hosts"
UNIQ = uuid.uuid4().hex[:8]
TEST_FIXTURE_FILE = f"TEST_sync_{UNIQ}.pptx"
TEST_FIXTURE_CONTENT = b"PK\x03\x04TEST_FIXTURE_" + UNIQ.encode()
TEST_LOCAL_ONLY_FILE = f"TEST_local_only_{UNIQ}.pptx"
TEST_LOCAL_ONLY_CONTENT = b"PK\x03\x04LOCAL_ONLY_" + UNIQ.encode()


def _set_sub(active: bool, cloud_sync_enabled: bool = False):
    body = {
        "active": active,
        "tier": "premium" if active else "free",
        "cloud_sync_enabled": cloud_sync_enabled,
    }
    r = requests.post(f"{BASE_URL}/api/native/subscription", json=body, timeout=15)
    assert r.status_code == 200, f"subscription toggle failed: {r.status_code} {r.text}"
    return r.json()


@pytest.fixture(scope="module", autouse=True)
def _fixture_setup_and_teardown():
    """Seed a unique file into the cloud fixture + remove any old local copy.

    Teardown removes any test files from both local + fixture trees and
    forces subscription OFF.
    """
    # Seed fixture with a unique file so plan has real work.
    fix_file = FIXTURE_ROOT / SYNC_ROOT / TEST_REL_DIR / TEST_FIXTURE_FILE
    fix_file.parent.mkdir(parents=True, exist_ok=True)
    fix_file.write_bytes(TEST_FIXTURE_CONTENT)

    # Ensure no stale local copy of the test file (so it appears in to_add).
    local_copy = LOCAL_ROOT / SYNC_ROOT / TEST_REL_DIR / TEST_FIXTURE_FILE
    if local_copy.exists():
        local_copy.unlink()

    yield

    # Teardown: clean any test artefacts on either side
    for base in (FIXTURE_ROOT, LOCAL_ROOT):
        tgt_dir = base / SYNC_ROOT / TEST_REL_DIR
        if tgt_dir.exists():
            for f in tgt_dir.glob("TEST_*"):
                try:
                    f.unlink()
                except OSError:
                    pass

    # Always leave subscription OFF
    try:
        _set_sub(False, False)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 1. /status route is always free
# ---------------------------------------------------------------------------
class TestStatusEndpoint:
    def test_status_200_free(self):
        # Ensure OFF first
        _set_sub(False, False)
        r = requests.get(f"{BASE_URL}/api/native/sync/status", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        for key in (
            "native_mode", "subscription", "cloud_available",
            "cloud_sync_enabled", "available", "remote_mode",
            "remote_fixture", "local_root", "last_pull", "last_push",
        ):
            assert key in data, f"missing field {key}: {data}"
        # fixture env configured at /app/backend/.env
        assert data["remote_fixture"] == "/app/backend/native/data/cloud_fixture"
        assert data["remote_mode"] == "fixture"


# ---------------------------------------------------------------------------
# 2. Premium gate — OFF → 402 for plan/pull/push
# ---------------------------------------------------------------------------
class TestPremiumGateOff:
    def setup_method(self):
        _set_sub(False, False)

    @pytest.mark.parametrize("endpoint", ["plan", "pull", "push"])
    def test_endpoint_402_when_off(self, endpoint):
        r = requests.post(f"{BASE_URL}/api/native/sync/{endpoint}", json={}, timeout=15)
        assert r.status_code == 402, f"{endpoint}: {r.status_code} {r.text}"
        detail = r.json().get("detail", {})
        assert detail.get("error") == "premium_required"
        assert detail.get("feature") == "cloud_sync_enabled"

    def test_status_200_when_off(self):
        r = requests.get(f"{BASE_URL}/api/native/sync/status", timeout=15)
        assert r.status_code == 200
        assert r.json().get("cloud_sync_enabled") is False
        assert r.json().get("available") is False  # native_mode=1 + no premium


# ---------------------------------------------------------------------------
# 3. Turn subscription ON
# ---------------------------------------------------------------------------
class TestPremiumOn:
    def test_enable_premium_flips_status(self):
        _set_sub(True, True)
        r = requests.get(f"{BASE_URL}/api/native/sync/status", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert data["available"] is True
        assert data["cloud_sync_enabled"] is True
        assert data["remote_mode"] == "fixture"
        assert data["remote_fixture"] == "/app/backend/native/data/cloud_fixture"


# ---------------------------------------------------------------------------
# 4. Pull / Push round-trip
# ---------------------------------------------------------------------------
class TestPullPushRoundTrip:
    def setup_method(self):
        _set_sub(True, True)

    def test_plan_reports_add_for_seeded_fixture(self):
        body = {"sync_root": SYNC_ROOT}
        r = requests.post(f"{BASE_URL}/api/native/sync/plan", json=body, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "pull" in data and "push" in data
        pull = data["pull"]
        # Seeded test file should be in pull.to_add (fixture has it, local doesn't)
        expected_rel = f"{TEST_REL_DIR}/{TEST_FIXTURE_FILE}"
        assert expected_rel in pull["to_add"], (
            f"Expected {expected_rel} in pull.to_add, got {pull['to_add']}"
        )
        for k in ("to_add", "to_update", "to_delete", "unchanged_count", "total_changes"):
            assert k in pull

    def test_pull_creates_file_locally(self):
        body = {"sync_root": SYNC_ROOT}
        r = requests.post(f"{BASE_URL}/api/native/sync/pull", json=body, timeout=60)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["direction"] == "pull"
        expected_rel = f"{TEST_REL_DIR}/{TEST_FIXTURE_FILE}"
        assert expected_rel in data["added"], f"added missing file: {data}"
        local_path = LOCAL_ROOT / SYNC_ROOT / TEST_REL_DIR / TEST_FIXTURE_FILE
        assert local_path.exists(), f"file not written: {local_path}"
        assert local_path.read_bytes() == TEST_FIXTURE_CONTENT

    def test_push_mirrors_local_only_to_fixture(self):
        # Create a local-only file to exercise push.to_add
        local_only = LOCAL_ROOT / SYNC_ROOT / TEST_REL_DIR / TEST_LOCAL_ONLY_FILE
        local_only.parent.mkdir(parents=True, exist_ok=True)
        local_only.write_bytes(TEST_LOCAL_ONLY_CONTENT)

        body = {"sync_root": SYNC_ROOT}
        r = requests.post(f"{BASE_URL}/api/native/sync/push", json=body, timeout=60)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["direction"] == "push"
        expected_rel = f"{TEST_REL_DIR}/{TEST_LOCAL_ONLY_FILE}"
        assert expected_rel in data["added"], f"push.added missing: {data}"

        fix_path = FIXTURE_ROOT / SYNC_ROOT / TEST_REL_DIR / TEST_LOCAL_ONLY_FILE
        assert fix_path.exists()
        assert fix_path.read_bytes() == TEST_LOCAL_ONLY_CONTENT

    def test_plan_converges_after_round_trip(self):
        body = {"sync_root": SYNC_ROOT}
        r = requests.post(f"{BASE_URL}/api/native/sync/plan", json=body, timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert data["pull"]["total_changes"] == 0, f"pull not converged: {data['pull']}"
        assert data["push"]["total_changes"] == 0, f"push not converged: {data['push']}"


# ---------------------------------------------------------------------------
# 5. Sync state persistence via /status
# ---------------------------------------------------------------------------
class TestSyncStatePersistence:
    def test_status_has_last_pull_and_push(self):
        _set_sub(True, True)
        r = requests.get(f"{BASE_URL}/api/native/sync/status", timeout=15)
        assert r.status_code == 200
        data = r.json()
        for kind in ("last_pull", "last_push"):
            st = data.get(kind)
            assert st is not None, f"{kind} should be populated after pull/push"
            for k in ("added", "updated", "deleted", "errors", "unchanged", "finished_at", "kind"):
                assert k in st, f"{kind} missing field {k}: {st}"


# ---------------------------------------------------------------------------
# 6. delete_missing
# ---------------------------------------------------------------------------
class TestDeleteMissing:
    def test_pull_to_delete_lists_local_only_file(self):
        _set_sub(True, True)
        # Add a local-only file that doesn't exist in fixture
        delete_name = f"TEST_to_delete_{uuid.uuid4().hex[:8]}.pptx"
        local_file = LOCAL_ROOT / SYNC_ROOT / TEST_REL_DIR / delete_name
        local_file.parent.mkdir(parents=True, exist_ok=True)
        local_file.write_bytes(b"delete-me")
        expected_rel = f"{TEST_REL_DIR}/{delete_name}"
        try:
            body = {"sync_root": SYNC_ROOT, "delete_missing": True}
            r = requests.post(f"{BASE_URL}/api/native/sync/plan", json=body, timeout=30)
            assert r.status_code == 200, r.text
            data = r.json()
            assert expected_rel in data["pull"]["to_delete"], (
                f"expected {expected_rel} in pull.to_delete: {data['pull']}"
            )
        finally:
            if local_file.exists():
                local_file.unlink()


# ---------------------------------------------------------------------------
# 7. Path traversal safety
# ---------------------------------------------------------------------------
class TestPathTraversalSafety:
    def test_traversal_does_not_leak_filesystem(self):
        _set_sub(True, True)
        body = {"sync_root": "../../etc"}
        r = requests.post(f"{BASE_URL}/api/native/sync/plan", json=body, timeout=20)
        # Accept either clean 500 OR 200 with empty lists; NOT a crash leaking /etc
        assert r.status_code in (200, 500), f"unexpected: {r.status_code} {r.text}"
        if r.status_code == 200:
            data = r.json()
            # Must NOT include anything under /etc
            combined = (
                data["pull"]["to_add"] + data["pull"]["to_update"]
                + data["push"]["to_add"] + data["push"]["to_update"]
            )
            for p in combined:
                assert "passwd" not in p and "shadow" not in p, f"leaked path: {p}"


# ---------------------------------------------------------------------------
# 8. Subscription OFF re-engages gate without restart
# ---------------------------------------------------------------------------
class TestGateReengages:
    def test_off_blocks_pull_after_having_been_on(self):
        _set_sub(True, True)
        # Verify on: 200 plan
        r = requests.post(
            f"{BASE_URL}/api/native/sync/plan", json={"sync_root": SYNC_ROOT}, timeout=20,
        )
        assert r.status_code == 200
        # Flip off
        _set_sub(False, False)
        r = requests.post(f"{BASE_URL}/api/native/sync/pull", json={}, timeout=15)
        assert r.status_code == 402
        assert r.json()["detail"]["error"] == "premium_required"


# ---------------------------------------------------------------------------
# 9. Previous-phase endpoint spot check (regression)
# ---------------------------------------------------------------------------
class TestPreviousPhasesSpotCheck:
    @pytest.mark.parametrize("path", [
        "/api/native/info",
        "/api/native/hwid",
        "/api/native/license",
        "/api/trivia/hosts",
        "/api/trivia/round-files/reg",
        "/api/roundmaker/sharepoint-status",
        "/api/story-generator/status",
        "/api/scoreboard/status",
    ])
    def test_endpoint_200(self, path):
        r = requests.get(f"{BASE_URL}{path}", timeout=20)
        assert r.status_code == 200, f"{path}: {r.status_code} {r.text[:200]}"
