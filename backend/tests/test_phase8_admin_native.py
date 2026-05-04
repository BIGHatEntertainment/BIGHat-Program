"""Phase 8 — master-admin user management, license seat admin,
and reviewer-flagged tournament hardening (TournamentCreate +
TournamentAdvance pydantic validation).
"""
import os
import uuid

import pytest
import requests

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL",
    open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].splitlines()[0],
).rstrip("/")

MASTER_EMAIL = "master@bighat.local"
MASTER_PASSWORD = "BigHat2024!"


# ------------------------ Fixtures ------------------------
@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def master_token(api):
    r = api.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": MASTER_EMAIL, "password": MASTER_PASSWORD},
    )
    if r.status_code != 200:
        pytest.skip(f"Master login failed ({r.status_code}): {r.text}")
    data = r.json()
    token = data.get("token") or data.get("access_token")
    assert token, f"No token in login response: {data}"
    return token


@pytest.fixture(scope="module")
def master_headers(master_token):
    return {"Authorization": f"Bearer {master_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def created_user_ids(api, master_headers):
    """Track ids created during tests; cleanup at module teardown."""
    ids: list[str] = []
    yield ids
    for uid in ids:
        try:
            api.delete(f"{BASE_URL}/api/native/admin/users/{uid}", headers=master_headers)
        except Exception:
            pass


# ------------------------ Route mount sanity ------------------------
class TestRouterMounted:
    def test_unauth_returns_401_not_404(self, api):
        r = api.get(f"{BASE_URL}/api/native/admin/users")
        assert r.status_code == 401, f"Expected 401, got {r.status_code} body={r.text}"


# ------------------------ Master admin GET /users ------------------------
class TestListUsers:
    def test_master_can_list_users(self, api, master_headers):
        r = api.get(f"{BASE_URL}/api/native/admin/users", headers=master_headers)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "users" in data and isinstance(data["users"], list)
        assert "count" in data
        roles = {u.get("email"): u.get("role") for u in data["users"]}
        assert MASTER_EMAIL in roles, f"master email missing from listing: {roles}"
        assert roles[MASTER_EMAIL] == "master_admin"

    def test_whoami(self, api, master_headers):
        r = api.get(f"{BASE_URL}/api/native/admin/whoami", headers=master_headers)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("email") == MASTER_EMAIL
        assert d.get("role") == "master_admin"


# ------------------------ Validation errors ------------------------
class TestValidation:
    def test_invalid_role_422(self, api, master_headers):
        r = api.post(
            f"{BASE_URL}/api/native/admin/users",
            headers=master_headers,
            json={
                "email": f"TEST_invalidrole_{uuid.uuid4().hex[:6]}@bighat.local",
                "password": "ValidPwd1",
                "first_name": "Bad",
                "role": "god",
            },
        )
        assert r.status_code == 422, r.text

    def test_invalid_email_422(self, api, master_headers):
        r = api.post(
            f"{BASE_URL}/api/native/admin/users",
            headers=master_headers,
            json={
                "email": "not-an-email",
                "password": "ValidPwd1",
                "first_name": "Bad",
                "role": "host",
            },
        )
        assert r.status_code == 422, r.text

    def test_short_password_422(self, api, master_headers):
        r = api.post(
            f"{BASE_URL}/api/native/admin/users",
            headers=master_headers,
            json={
                "email": f"TEST_shortpwd_{uuid.uuid4().hex[:6]}@bighat.local",
                "password": "abc",
                "first_name": "Bad",
                "role": "host",
            },
        )
        assert r.status_code == 422, r.text


# ------------------------ Sub-admin creation, auth, role gating ------------------------
class TestSubAdminFlow:
    def test_create_subadmin_and_role_gating(self, api, master_headers, created_user_ids):
        email = f"TEST_subadmin_p8_{uuid.uuid4().hex[:6]}@bighat.local"
        r = api.post(
            f"{BASE_URL}/api/native/admin/users",
            headers=master_headers,
            json={
                "email": email,
                "password": "SubAdmin123",
                "first_name": "Sub",
                "last_name": "Admin",
                "role": "admin",
            },
        )
        assert r.status_code == 200, r.text
        u = r.json()["user"]
        assert u["role"] == "admin"
        assert u["is_admin"] is True
        created_user_ids.append(u["id"])

        # Login as sub-admin via /api/auth/login (mirror to db.users worked)
        lr = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": email, "password": "SubAdmin123"},
        )
        assert lr.status_code == 200, lr.text
        sub_token = lr.json().get("token") or lr.json().get("access_token")
        assert sub_token

        # Sub-admin must be rejected from admin endpoint with 403 master_admin_required
        rr = requests.get(
            f"{BASE_URL}/api/native/admin/users",
            headers={"Authorization": f"Bearer {sub_token}"},
        )
        assert rr.status_code == 403, rr.text
        assert rr.json().get("detail") == "master_admin_required"

    def test_duplicate_email_409(self, api, master_headers, created_user_ids):
        email = f"TEST_dup_{uuid.uuid4().hex[:6]}@bighat.local"
        body = {
            "email": email,
            "password": "ValidPwd1",
            "first_name": "Dup",
            "role": "host",
        }
        r1 = api.post(f"{BASE_URL}/api/native/admin/users", headers=master_headers, json=body)
        assert r1.status_code == 200, r1.text
        created_user_ids.append(r1.json()["user"]["id"])
        r2 = api.post(f"{BASE_URL}/api/native/admin/users", headers=master_headers, json=body)
        assert r2.status_code == 409, r2.text
        assert r2.json().get("detail") == "email_already_exists"


# ------------------------ Promote / demote / password reset ------------------------
class TestUpdateUser:
    def test_promote_demote_and_password_reset(self, api, master_headers, created_user_ids):
        email = f"TEST_host_promo_{uuid.uuid4().hex[:6]}@bighat.local"
        r = api.post(
            f"{BASE_URL}/api/native/admin/users",
            headers=master_headers,
            json={
                "email": email,
                "password": "OrigPass1",
                "first_name": "Promo",
                "role": "host",
            },
        )
        assert r.status_code == 200, r.text
        uid = r.json()["user"]["id"]
        created_user_ids.append(uid)

        # Promote host -> admin
        rp = api.put(
            f"{BASE_URL}/api/native/admin/users/{uid}",
            headers=master_headers,
            json={"role": "admin"},
        )
        assert rp.status_code == 200, rp.text
        u = rp.json()["user"]
        assert u["role"] == "admin"
        assert u["is_admin"] is True

        # Demote admin -> host
        rd = api.put(
            f"{BASE_URL}/api/native/admin/users/{uid}",
            headers=master_headers,
            json={"role": "host"},
        )
        assert rd.status_code == 200, rd.text
        u2 = rd.json()["user"]
        assert u2["role"] == "host"
        assert u2["is_admin"] is False

        # Password reset propagates: change password, then login with new value
        new_pwd = "NewPass789"
        rpw = api.put(
            f"{BASE_URL}/api/native/admin/users/{uid}",
            headers=master_headers,
            json={"password": new_pwd},
        )
        assert rpw.status_code == 200, rpw.text
        login = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": email, "password": new_pwd},
        )
        assert login.status_code == 200, login.text
        assert login.json().get("token") or login.json().get("access_token")

    def test_cannot_delete_master(self, api, master_headers):
        r = api.get(f"{BASE_URL}/api/native/admin/users", headers=master_headers)
        master_id = next(u["id"] for u in r.json()["users"] if u["email"] == MASTER_EMAIL)
        rd = api.delete(
            f"{BASE_URL}/api/native/admin/users/{master_id}",
            headers=master_headers,
        )
        assert rd.status_code == 400, rd.text
        assert rd.json().get("detail") == "cannot_delete_master_admin"

    def test_cannot_demote_master(self, api, master_headers):
        r = api.get(f"{BASE_URL}/api/native/admin/users", headers=master_headers)
        master_id = next(u["id"] for u in r.json()["users"] if u["email"] == MASTER_EMAIL)
        rp = api.put(
            f"{BASE_URL}/api/native/admin/users/{master_id}",
            headers=master_headers,
            json={"role": "admin"},
        )
        assert rp.status_code == 400, rp.text
        assert rp.json().get("detail") == "cannot_demote_master_admin"


# ------------------------ License seats ------------------------
class TestLicenseSeats:
    def test_list_seats_shape(self, api, master_headers):
        r = api.get(f"{BASE_URL}/api/native/admin/license/seats", headers=master_headers)
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("seats", "total_allowed", "used", "remaining", "current_hwid"):
            assert k in d, f"missing key {k} in {d}"
        assert isinstance(d["seats"], list)

    def test_rename_seat_label(self, api, master_headers):
        r = api.get(f"{BASE_URL}/api/native/admin/license/seats", headers=master_headers)
        seats = r.json().get("seats", [])
        if not seats:
            pytest.skip("No seats present to rename")
        target_hwid = seats[0]["hwid"]
        new_label = f"TEST_seat_{uuid.uuid4().hex[:6]}"
        rp = api.put(
            f"{BASE_URL}/api/native/admin/license/seats/{target_hwid}/label",
            headers=master_headers,
            json={"label": new_label},
        )
        assert rp.status_code == 200, rp.text
        assert rp.json()["seat"]["label"] == new_label

    def test_revoke_current_device_blocked(self, api, master_headers):
        r = api.get(f"{BASE_URL}/api/native/admin/license/seats", headers=master_headers)
        current = r.json().get("current_hwid")
        if not current:
            pytest.skip("No current_hwid")
        rd = api.delete(
            f"{BASE_URL}/api/native/admin/license/seats/{current}",
            headers=master_headers,
        )
        assert rd.status_code == 400, rd.text
        assert rd.json().get("detail") == "cannot_revoke_current_device"

    def test_revoke_unknown_seat_404(self, api, master_headers):
        rd = api.delete(
            f"{BASE_URL}/api/native/admin/license/seats/deadbeefnotaseat",
            headers=master_headers,
        )
        assert rd.status_code == 404, rd.text


# ------------------------ Tournament hardening ------------------------
class TestTournamentValidation:
    def test_team_count_mismatch_422(self, api):
        r = api.post(
            f"{BASE_URL}/api/scoreboard/tournaments",
            json={
                "name": "TEST_Bad_Bracket",
                "total_teams": 8,
                "bye_count": 0,
                "teams": [{"name": "A"}, {"name": "B"}],
            },
        )
        assert r.status_code == 422, r.text
        body_text = r.text
        assert "total_teams must equal len(teams) + bye_count" in body_text, body_text

    def test_valid_tournament_4_teams(self, api):
        name = f"TEST_Valid_{uuid.uuid4().hex[:6]}"
        r = api.post(
            f"{BASE_URL}/api/scoreboard/tournaments",
            json={
                "name": name,
                "total_teams": 4,
                "bye_count": 0,
                "teams": [{"name": "A"}, {"name": "B"}, {"name": "C"}, {"name": "D"}],
            },
        )
        assert r.status_code == 200, r.text
        tid = r.json().get("id")
        assert tid
        # cleanup
        api.delete(f"{BASE_URL}/api/scoreboard/tournaments/{tid}")

    def test_empty_teams_preseeded_ok(self, api):
        name = f"TEST_Empty_{uuid.uuid4().hex[:6]}"
        r = api.post(
            f"{BASE_URL}/api/scoreboard/tournaments",
            json={
                "name": name,
                "total_teams": 12,
                "bye_count": 0,
                "teams": [],
            },
        )
        assert r.status_code == 200, r.text
        tid = r.json().get("id")
        if tid:
            api.delete(f"{BASE_URL}/api/scoreboard/tournaments/{tid}")


class TestTournamentAdvance:
    def test_empty_body_422(self, api):
        r = api.post(
            f"{BASE_URL}/api/scoreboard/tournaments/nonexistent/advance",
            json={},
        )
        assert r.status_code == 422, r.text
        body = r.json()
        # Pydantic v2 lists missing fields under 'detail'
        detail = body.get("detail", [])
        missing_fields = {
            tuple(err.get("loc", []))[-1]
            for err in detail
            if err.get("type") == "missing"
        }
        assert "match_id" in missing_fields, f"match_id not flagged missing: {detail}"
        assert "winner_seed" in missing_fields, f"winner_seed not flagged missing: {detail}"

    def test_advance_real_tournament_200(self, api):
        # Create a small tournament
        name = f"TEST_Adv_{uuid.uuid4().hex[:6]}"
        r = api.post(
            f"{BASE_URL}/api/scoreboard/tournaments",
            json={
                "name": name,
                "total_teams": 4,
                "bye_count": 0,
                "teams": [{"name": "A", "seed": 1}, {"name": "B", "seed": 2},
                          {"name": "C", "seed": 3}, {"name": "D", "seed": 4}],
            },
        )
        assert r.status_code == 200, r.text
        t = r.json()
        tid = t["id"]
        # Find a match id from bracket_state
        matches = (t.get("bracket_state") or {}).get("matches", {})
        match_id = next(iter(matches.keys()), "qf1")

        adv = api.post(
            f"{BASE_URL}/api/scoreboard/tournaments/{tid}/advance",
            json={"match_id": match_id, "winner_seed": 3},
        )
        assert adv.status_code == 200, adv.text
        body = adv.json()
        assert body.get("bracket_state", {}).get("last_updated"), body
        api.delete(f"{BASE_URL}/api/scoreboard/tournaments/{tid}")


# ------------------------ Regression on public endpoints ------------------------
class TestRegression:
    @pytest.mark.parametrize("path", [
        "/api/native/info",
        "/api/native/sync/status",
        "/api/story-generator/status",
        "/api/scoreboard/status",
        "/api/trivia/hosts",
        "/api/trivia/round-files/reg",
        "/api/roundmaker/sharepoint-status",
        "/api/venues",
        "/api/events",
    ])
    def test_public_endpoint_200(self, api, path):
        r = api.get(f"{BASE_URL}{path}")
        assert r.status_code == 200, f"{path} -> {r.status_code} {r.text[:200]}"


# ------------------------ Final cleanup verification ------------------------
class TestZCleanupVerification:
    """Module-final teardown sanity: after fixture teardown, only master remains."""

    def test_no_extra_users_left(self, api, master_headers, created_user_ids):
        # Force cleanup of any lingering ids first (idempotent)
        for uid in list(created_user_ids):
            api.delete(f"{BASE_URL}/api/native/admin/users/{uid}", headers=master_headers)
        r = api.get(f"{BASE_URL}/api/native/admin/users", headers=master_headers)
        assert r.status_code == 200, r.text
        d = r.json()
        # Allow only master_admin remaining
        non_test = [u for u in d["users"] if not (u.get("email") or "").startswith("TEST_")]
        # There should be exactly one master remaining (ignoring any pre-existing non-TEST users
        # — but per request, count should be 1)
        assert d["count"] == 1, f"Expected 1 user (master only), got {d['count']}: {d['users']}"
        assert non_test[0]["role"] == "master_admin"
