"""
Phase 2 - Trivia Core native mode backend tests.

Validates:
- Native mode boot (no SharePoint).
- Master admin auth + /auth/me.
- Trivia local asset endpoints (hosts/locations/sponsors/rounds variants/round-files).
- Presentation CRUD (SQLite persistence).
- GridFS shim round-trip via Python API + HTTP endpoints.
- Premium subscription gate (local-vs-cloud).
- Schedule routes regression (/api/venues, /api/events).
- Native foundation endpoints regression.

Run with: pytest /app/backend/tests/test_phase2_trivia_native.py -v --tb=short \
    --junitxml=/app/test_reports/pytest/phase2_results.xml
"""
import os
import sys
import uuid
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv

# Load /app/backend/.env to match runtime config (BIGHAT_NATIVE_MODE=1)
load_dotenv("/app/backend/.env")
os.environ.setdefault("BIGHAT_NATIVE_MODE", "1")

# Allow importing backend modules for the direct GridFS shim test
sys.path.insert(0, "/app/backend")

# REACT_APP_BACKEND_URL from the frontend .env (public preview URL)
with open("/app/frontend/.env") as _fh:
    for _line in _fh:
        if _line.startswith("REACT_APP_BACKEND_URL="):
            BASE_URL = _line.split("=", 1)[1].strip().rstrip("/")
            break

MASTER_EMAIL = "master@bighat.local"
MASTER_PASSWORD = "BigHat2024!"

SQLITE_DB_DIR = Path("/app/backend/native/data/bighat_db/test_database")


# ---------- Shared fixtures ----------
@pytest.fixture(scope="session")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session")
def auth_token(api):
    r = api.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": MASTER_EMAIL, "password": MASTER_PASSWORD},
        timeout=15,
    )
    if r.status_code != 200:
        pytest.skip(f"Auth failed (status={r.status_code}): {r.text[:200]}")
    data = r.json()
    token = data.get("token") or data.get("access_token")
    if not token:
        # cookie-only auth; session already has the cookie
        return None
    return token


@pytest.fixture(scope="session")
def auth(api, auth_token):
    if auth_token:
        api.headers.update({"Authorization": f"Bearer {auth_token}"})
    return api


# ---------- 1. Native boot + master login ----------
class TestAuthAndNativeBoot:
    def test_native_info_reports_native_mode(self, api):
        r = api.get(f"{BASE_URL}/api/native/info", timeout=10)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["native_mode"] is True
        assert data["setup_complete"] is True
        assert "settings" in data and data["settings"]["trivia_source"] == "local"

    def test_login_master_admin(self, api):
        r = api.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": MASTER_EMAIL, "password": MASTER_PASSWORD},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert "token" in body or "access_token" in body or r.cookies

    def test_auth_me_returns_master_admin(self, auth):
        r = auth.get(f"{BASE_URL}/api/auth/me", timeout=10)
        assert r.status_code == 200, r.text
        me = r.json()
        # role might live on user sub-object or top-level
        role = me.get("role") or (me.get("user") or {}).get("role")
        assert role == "master_admin", f"Expected master_admin, got {role}: {me}"


# ---------- 2. Trivia local asset endpoints ----------
class TestTriviaLocalAssets:
    ENDPOINTS_NONEMPTY = [
        "/api/trivia/hosts",
        "/api/trivia/locations",
        "/api/trivia/sponsors",
        "/api/trivia/rounds/mc",
        "/api/trivia/rounds/reg",
        "/api/trivia/round-files/mc",
        "/api/trivia/round-files/reg",
    ]
    ENDPOINTS_ALLOW_EMPTY = [
        "/api/trivia/rounds",          # union of all rounds; must include MC+REG items
        "/api/trivia/rounds/misc",
        "/api/trivia/rounds/mys",
        "/api/trivia/rounds/big",
    ]

    @pytest.mark.parametrize("endpoint", ENDPOINTS_NONEMPTY)
    def test_endpoint_returns_nonempty_array(self, auth, endpoint):
        r = auth.get(f"{BASE_URL}{endpoint}", timeout=20)
        assert r.status_code == 200, f"{endpoint} -> {r.status_code}: {r.text[:300]}"
        data = r.json()
        assert isinstance(data, list), f"{endpoint} did not return a list: {data!r}"
        assert len(data) >= 1, f"{endpoint} returned empty (seeded data expected): {data}"

    @pytest.mark.parametrize("endpoint", ENDPOINTS_ALLOW_EMPTY)
    def test_endpoint_returns_array_maybe_empty(self, auth, endpoint):
        r = auth.get(f"{BASE_URL}{endpoint}", timeout=20)
        assert r.status_code == 200, f"{endpoint} -> {r.status_code}: {r.text[:300]}"
        assert isinstance(r.json(), list)

    def test_rounds_union_contains_mc_and_reg(self, auth):
        r = auth.get(f"{BASE_URL}/api/trivia/rounds", timeout=20)
        assert r.status_code == 200
        rounds = r.json()
        types = {item.get("type") for item in rounds}
        assert "MC" in types and "REG" in types, f"types={types}"


# ---------- 3. Presentation CRUD on SQLite ----------
class TestPresentationCRUD:
    def test_full_crud_cycle(self, auth):
        user = "TEST_Phase2"
        name = f"TEST_pres_{uuid.uuid4().hex[:8]}"

        # CREATE
        payload = {
            "name": name,
            "createdBy": user,
            "slides": [
                {
                    "order": 0,
                    "background": "#000",
                    "elements": [
                        {
                            "type": "text",
                            "content": "hello",
                            "x": 10, "y": 10, "width": 100, "height": 40,
                        }
                    ],
                }
            ],
        }
        rc = auth.post(f"{BASE_URL}/api/presentations", json=payload, timeout=20)
        assert rc.status_code == 200, rc.text
        created = rc.json()
        pid = created["id"]
        assert created["name"] == name
        assert created["createdBy"] == user

        # Persistence on disk (MontyDB SQLite)
        assert (SQLITE_DB_DIR / "presentations.collection").exists()

        # LIST by userName
        rl = auth.get(f"{BASE_URL}/api/presentations?userName={user}", timeout=20)
        assert rl.status_code == 200, rl.text
        listed = rl.json()
        assert any(p.get("id") == pid for p in listed)

        # UPDATE
        updated_payload = dict(payload)
        updated_payload["name"] = name + "_upd"
        ru = auth.put(
            f"{BASE_URL}/api/presentations/{pid}", json=updated_payload, timeout=20
        )
        assert ru.status_code == 200, ru.text
        assert ru.json()["name"] == name + "_upd"

        # DELETE
        rd = auth.delete(f"{BASE_URL}/api/presentations/{pid}", timeout=20)
        assert rd.status_code in (200, 204), rd.text

        rl2 = auth.get(f"{BASE_URL}/api/presentations?userName={user}", timeout=20)
        assert rl2.status_code == 200
        assert not any(p.get("id") == pid for p in rl2.json())


# ---------- 4. Trivia viewer list ----------
class TestTriviaViewerList:
    def test_viewer_list_returns_array(self, auth):
        r = auth.get(
            f"{BASE_URL}/api/trivia-viewer/list?viewAll=true", timeout=20
        )
        assert r.status_code == 200, r.text
        assert isinstance(r.json(), list)


# ---------- 5. GridFS shim round-trip ----------
class TestGridFSShim:
    """Store slides via python API (direct), then read them back via HTTP."""

    @pytest.fixture(scope="class")
    def seeded(self, auth):
        """Create a presentation row, then seed slides via gridfs shim."""
        import asyncio
        from native import db_factory
        import gridfs_service

        pid = f"TEST_gridfs_{uuid.uuid4().hex[:8]}"

        # Create the presentation document so metadata endpoint has a row
        create_payload = {
            "name": pid,
            "createdBy": "TEST_Phase2",
            "slides": [],
        }
        rc = auth.post(f"{BASE_URL}/api/presentations", json=create_payload, timeout=20)
        assert rc.status_code == 200, rc.text
        created = rc.json()
        real_pid = created["id"]

        async def _seed():
            db = db_factory.get_db()
            svc = gridfs_service.init_gridfs_service(db)
            slides = [
                {"order": 0, "background": "#111", "elements": []},
                {"order": 1, "background": "#222", "elements": []},
                {"order": 2, "background": "#333", "elements": []},
            ]
            meta = await svc.store_slides(real_pid, slides, metadata={"test": True})
            return meta, slides

        meta, slides = asyncio.run(_seed())
        yield {"pid": real_pid, "meta": meta, "slides": slides}

        # Teardown
        try:
            auth.delete(
                f"{BASE_URL}/api/trivia-import/clear-cache/{real_pid}", timeout=20
            )
            auth.delete(f"{BASE_URL}/api/presentations/{real_pid}", timeout=20)
        except Exception:
            pass

    def test_slides_metadata_endpoint(self, auth, seeded):
        r = auth.get(
            f"{BASE_URL}/api/trivia-import/slides-metadata/{seeded['pid']}", timeout=20
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("hasGridFSSlides") is True, data
        assert data.get("totalSlides") == len(seeded["slides"])

    def test_slides_endpoint_returns_original(self, auth, seeded):
        r = auth.get(
            f"{BASE_URL}/api/trivia-import/slides/{seeded['pid']}", timeout=30
        )
        assert r.status_code == 200, r.text
        data = r.json()
        slides = data.get("slides") if isinstance(data, dict) else data
        assert isinstance(slides, list)
        assert len(slides) == len(seeded["slides"])

    def test_chunk_endpoint(self, auth, seeded):
        r = auth.get(
            f"{BASE_URL}/api/trivia-import/chunk/{seeded['pid']}/0", timeout=30
        )
        assert r.status_code == 200, r.text

    def test_clear_cache_resets_metadata(self, auth, seeded):
        r = auth.delete(
            f"{BASE_URL}/api/trivia-import/clear-cache/{seeded['pid']}", timeout=20
        )
        assert r.status_code in (200, 204), r.text
        r2 = auth.get(
            f"{BASE_URL}/api/trivia-import/slides-metadata/{seeded['pid']}", timeout=20
        )
        # After clear, metadata endpoint must report no GridFS slides
        assert r2.status_code == 200, r2.text
        data = r2.json()
        assert data.get("hasGridFSSlides") in (False, None), data


# ---------- 6. Premium subscription toggle (local-vs-cloud gate) ----------
class TestPremiumGate:
    def test_toggle_on_then_off_and_local_still_served(self, auth):
        # Enable premium + sharepoint
        r_on = auth.post(
            f"{BASE_URL}/api/native/subscription",
            json={"active": True, "tier": "premium", "sharepoint_enabled": True},
            timeout=15,
        )
        assert r_on.status_code == 200, r_on.text
        info = auth.get(f"{BASE_URL}/api/native/info", timeout=10).json()
        sub = info.get("subscription") or {}
        assert sub.get("active") is True
        assert sub.get("sharepoint_enabled") is True
        # trivia_source remains "local" (default) so hosts must still be local
        assert info["settings"]["trivia_source"] == "local"

        r_hosts = auth.get(f"{BASE_URL}/api/trivia/hosts", timeout=20)
        assert r_hosts.status_code == 200
        hosts = r_hosts.json()
        assert isinstance(hosts, list) and len(hosts) >= 1

        # Turn off subscription
        r_off = auth.post(
            f"{BASE_URL}/api/native/subscription",
            json={"active": False, "tier": "premium", "sharepoint_enabled": False},
            timeout=15,
        )
        assert r_off.status_code == 200, r_off.text


# ---------- 7. Schedule regression ----------
class TestScheduleRegression:
    def test_get_venues(self, auth):
        r = auth.get(f"{BASE_URL}/api/venues", timeout=20)
        assert r.status_code == 200, r.text
        assert isinstance(r.json(), list)

    def test_event_crud(self, auth):
        # Read existing venues to pick one
        venues = auth.get(f"{BASE_URL}/api/venues", timeout=15).json()
        assert venues, "No venues seeded"
        venue_id = venues[0].get("id") or venues[0].get("_id")

        # GET events
        r_list = auth.get(f"{BASE_URL}/api/events", timeout=20)
        assert r_list.status_code == 200
        assert isinstance(r_list.json(), list)

        # POST a new event
        payload = {
            "title": "TEST_phase2_event",
            "event_type": "trivia",
            "venue_id": venue_id,
            "date": "2026-08-10",
            "time": "19:00",
            "duration": 120,
        }
        r_create = auth.post(f"{BASE_URL}/api/events", json=payload, timeout=20)
        assert r_create.status_code in (200, 201), r_create.text
        evt = r_create.json()
        eid = evt.get("id") or evt.get("_id")
        assert eid

        # PUT (update)
        upd = {"title": "TEST_phase2_event_upd"}
        r_upd = auth.put(f"{BASE_URL}/api/events/{eid}", json=upd, timeout=20)
        assert r_upd.status_code in (200, 204), r_upd.text

        # DELETE
        r_del = auth.delete(f"{BASE_URL}/api/events/{eid}", timeout=20)
        assert r_del.status_code in (200, 204), r_del.text


# ---------- 8. Native foundation regression ----------
class TestNativeFoundation:
    @pytest.mark.parametrize(
        "endpoint",
        [
            "/api/native/info",
            "/api/native/setup/status",
            "/api/native/license",
            "/api/native/hwid",
            "/api/native/subscription",
        ],
    )
    def test_endpoint_ok(self, auth, endpoint):
        r = auth.get(f"{BASE_URL}{endpoint}", timeout=15)
        assert r.status_code == 200, f"{endpoint} -> {r.status_code}: {r.text[:200]}"


# ---------- 9. Disk layout (SQLite collections exist) ----------
class TestSQLiteCollectionsOnDisk:
    REQUIRED = [
        "events.collection",
        "venues.collection",
        "employees.collection",
        "users.collection",
        "login_attempts.collection",
        "venue_pricing.collection",
        "presentations.collection",
    ]

    @pytest.mark.parametrize("coll", REQUIRED)
    def test_collection_file_exists(self, coll):
        assert (SQLITE_DB_DIR / coll).exists(), f"Missing SQLite file: {coll}"

    def test_gridfs_collections_exist_after_seed(self):
        # Either slides_files or slides.files (depending on shim naming) should exist
        candidates = [
            "slides_files.collection",
            "slides.files.collection",
            "slides_metadata.collection",
            "slides.metadata.collection",
        ]
        found = [c for c in candidates if (SQLITE_DB_DIR / c).exists()]
        assert found, (
            f"No GridFS SQLite collections found in {SQLITE_DB_DIR}; "
            f"candidates checked: {candidates}"
        )
