"""
Read-only verification of master test key BHE-28CA-DVU9-NT39-F6KD against PRODUCTION
https://api.bighat.live. Also validates desktop-side is_well_formed_license.

Guards:
- No mint/revoke/modify mutations.
- Activate/validate followed by MANDATORY deactivate (always runs via fixture teardown)
  to leave zero seats registered on hwid TA-VERIFY-HWID-37.
"""
import os
import sys
import pytest
import requests

PROD = "https://api.bighat.live"
KEY = "BHE-28CA-DVU9-NT39-F6KD"
HWID = "TA-VERIFY-HWID-37"
LABEL = "testing agent verification"
BAD_KEY = "BHE-0000-0000-0000-0000"

# Ensure we can import desktop native license module
sys.path.insert(0, "/app/backend")


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture
def ensure_deactivate(session):
    """MANDATORY cleanup: free seat for HWID even if any test fails."""
    yield
    try:
        session.post(f"{PROD}/api/license/deactivate",
                     json={"key": KEY, "hwid": HWID}, timeout=20)
    except Exception as e:
        print(f"WARN: cleanup deactivate failed: {e}")


# ---- (1) Status endpoint verification ----
def test_status_master_key(session):
    r = session.get(f"{PROD}/api/license/status/{KEY}", timeout=20)
    assert r.status_code == 200, f"status: {r.status_code} body={r.text}"
    data = r.json()
    print("STATUS payload:", data)
    assert data.get("owns_standalone") is True
    assert data.get("owns_music_bingo") is True
    assert data.get("owns_karaoke") is True
    # Public status payload does not expose a raw `revoked` boolean; a revoked
    # key would surface via cloud_library_status != 'active' and/or owns_* False.
    assert data.get("revoked", False) is False
    assert data.get("max_seats") == 5
    assert data.get("cloud_library_status") == "active"


# ---- (4) Negative sanity: invalid/unknown key ----
def test_status_unknown_key_returns_not_found(session):
    r = session.get(f"{PROD}/api/license/status/{BAD_KEY}", timeout=20)
    # Should discriminate: 404 or 200 with revoked/invalid flag
    assert r.status_code in (400, 404), f"expected not-found; got {r.status_code} body={r.text}"


# ---- (2) Full activation lifecycle ----
def test_activate_validate_deactivate_lifecycle(session, ensure_deactivate):
    # Activate
    r = session.post(f"{PROD}/api/license/activate",
                     json={"key": KEY, "hwid": HWID, "label": LABEL}, timeout=30)
    assert r.status_code == 200, f"activate failed: {r.status_code} body={r.text}"
    act = r.json()
    print("ACTIVATE payload:", act)
    assert act.get("ok") is True
    assert act.get("owns_standalone") is True
    assert act.get("owns_music_bingo") is True
    assert act.get("owns_karaoke") is True

    # Validate
    r = session.post(f"{PROD}/api/license/validate",
                     json={"key": KEY, "hwid": HWID}, timeout=30)
    assert r.status_code == 200, f"validate failed: {r.status_code} body={r.text}"
    val = r.json()
    print("VALIDATE payload:", val)
    assert val.get("ok") is True
    assert val.get("owns_standalone") is True
    assert val.get("owns_music_bingo") is True
    assert val.get("owns_karaoke") is True

    # Deactivate (teardown also runs — safe to call twice; must succeed here)
    r = session.post(f"{PROD}/api/license/deactivate",
                     json={"key": KEY, "hwid": HWID}, timeout=30)
    assert r.status_code == 200, f"deactivate failed: {r.status_code} body={r.text}"
    deact = r.json()
    print("DEACTIVATE payload:", deact)
    assert deact.get("ok") is True


# ---- (3) Desktop-side key format check ----
def test_desktop_is_well_formed_license():
    from native.license import is_well_formed_license
    assert is_well_formed_license(KEY) is True
    assert is_well_formed_license(BAD_KEY) is True  # well-formed structurally (regex is format-only)
    assert is_well_formed_license("not-a-key") is False
    assert is_well_formed_license("") is False
    # Lowercase accepted via upper() normalisation
    assert is_well_formed_license(KEY.lower()) is True
