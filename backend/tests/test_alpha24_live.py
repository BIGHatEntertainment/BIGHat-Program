"""Alpha.24 live regression: cover image ingest, override, backup folder name."""
import os
import re
import io
import pytest
import requests
from pathlib import Path

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://standalone-tools.preview.emergentagent.com").rstrip("/")
FIXTURES = Path("/app/backend/tests/fixtures/bighat")
EMAIL = "Sellards@bighat.live"
PASSWORD = "BigHat2024!"


@pytest.fixture(scope="module")
def auth_token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": EMAIL, "password": PASSWORD},
                      timeout=20)
    if r.status_code != 200:
        pytest.skip(f"auth failed {r.status_code}: {r.text[:200]}")
    data = r.json()
    return data.get("access_token") or data.get("token")


@pytest.fixture(scope="module")
def headers(auth_token):
    return {"Authorization": f"Bearer {auth_token}"}


def _import_bighat(fixture_name, headers):
    fp = FIXTURES / fixture_name
    assert fp.exists(), f"missing fixture {fp}"
    with open(fp, "rb") as f:
        files = {"file": (fixture_name, f.read(), "application/octet-stream")}
    r = requests.post(f"{BASE_URL}/api/bighat-files/import",
                      headers=headers, files=files, timeout=60)
    return r


# ---------- MC import: cover, correct option, normalised question shape ----------
def test_mc_import_returns_round_with_normalised_questions(headers):
    r = _import_bighat("mc-01-a.bighat", headers)
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    round_id = body.get("round_id") or body.get("id") or (body.get("round") or {}).get("id")
    assert round_id, f"no round id in response: {body}"

    g = requests.get(f"{BASE_URL}/api/roundmaker/rounds/{round_id}",
                     headers=headers, timeout=20)
    assert g.status_code == 200, g.text[:300]
    rnd = g.json()
    assert rnd.get("cover_image_id"), "cover_image_id missing"

    qs = rnd.get("questions") or []
    assert qs, "no questions returned"
    for q in qs:
        assert q.get("question"), f"question missing: {q}"
        assert q.get("options"), f"options missing: {q}"
        assert "correctOption" in q, f"correctOption missing: {q}"
        assert q.get("answer"), f"answer missing: {q}"

    # Q1 - M*A*S*H is option A (index 0)
    q1 = qs[0]
    assert q1["correctOption"] == 0, f"Q1 correctOption expected 0, got {q1.get('correctOption')}"
    assert "M*A*S*H" in str(q1.get("answer")) or "MASH" in str(q1.get("answer")).upper()

    # cache for later tests
    pytest.mc_round_id = round_id
    pytest.mc_cover_id = rnd["cover_image_id"]


def test_cover_image_endpoint_returns_bytes():
    cover_id = getattr(pytest, "mc_cover_id", None)
    if not cover_id:
        pytest.skip("no cover id from prior test")
    r = requests.get(f"{BASE_URL}/api/roundmaker/cover-image/{cover_id}", timeout=20)
    assert r.status_code == 200, f"{r.status_code}: {r.text[:200]}"
    assert r.headers.get("content-type", "").startswith("image/")
    assert len(r.content) > 100


def test_cover_image_endpoint_404_on_random():
    r = requests.get(f"{BASE_URL}/api/roundmaker/cover-image/00000000-0000-0000-0000-000000000000",
                     timeout=20)
    assert r.status_code == 404


def test_cover_image_endpoint_rejects_traversal():
    for bad in ["..%2F..%2Fetc%2Fpasswd", "../../etc/passwd", "..\\..\\windows"]:
        r = requests.get(f"{BASE_URL}/api/roundmaker/cover-image/{bad}", timeout=20,
                         allow_redirects=False)
        assert r.status_code in (400, 404, 422), f"{bad} -> {r.status_code}"


# ---------- REG import: animals-1 ----------
def test_reg_import_animals(headers):
    r = _import_bighat("animals-1.bighat", headers)
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    round_id = body.get("round_id") or body.get("id") or (body.get("round") or {}).get("id")
    g = requests.get(f"{BASE_URL}/api/roundmaker/rounds/{round_id}",
                     headers=headers, timeout=20)
    assert g.status_code == 200
    rnd = g.json()
    qs = rnd.get("questions") or []
    assert len(qs) >= 2
    q1 = qs[0]
    assert "teeth" in (q1.get("question") or "").lower(), q1
    assert "armadillo" in (q1.get("answer") or "").lower(), q1
    q2 = qs[1]
    assert "cancer" in (q2.get("question") or "").lower(), q2
    assert "naked mole" in (q2.get("answer") or "").lower(), q2


# ---------- Backup folder name ----------
def test_backup_folder_canonical_name(headers):
    r = requests.post(f"{BASE_URL}/api/native/backup/run", headers=headers, timeout=60)
    # may not exist in preview env -> tolerate 404/501/403
    if r.status_code in (404, 501, 403):
        pytest.skip(f"backup endpoint unavailable in preview ({r.status_code})")
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    path = str(body.get("path") or body.get("backup_path") or body)
    assert "BIGHat Entertainment" in path or "bighat" in path.lower(), path
    assert "BIG Hat Entertainment" not in path, f"old folder name leaked: {path}"


# ---------- Round-type override available on round payload ----------
def test_round_payload_round_code_present(headers):
    rid = getattr(pytest, "mc_round_id", None)
    if not rid:
        pytest.skip("no round id")
    g = requests.get(f"{BASE_URL}/api/roundmaker/rounds/{rid}", headers=headers, timeout=20)
    rnd = g.json()
    # the round must expose its type so the override dropdown can preselect.
    code = (rnd.get("round_type") or rnd.get("type") or rnd.get("category") or "").upper()
    assert code in ("MC", "REG", "MISC", "MYS", "BIG"), f"unexpected code: {code} | rnd keys: {list(rnd.keys())}"
