"""v32.0.0-alpha.37 LIVE backend integration tests (HTTP against preview).

Covers the two headline merchant bugs:
  1) Presentations vanishing after wizard Confirm (import-trivia writes
     to trivia_presentations; list endpoint must merge both collections).
  2) Files tool Locations/Hosts tabs empty (must list branded subfolders
     with branding+overlay counts).
"""
from __future__ import annotations
import io
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL", "https://standalone-tools.preview.emergentagent.com"
).rstrip("/")
EMAIL = "Sellards@bighat.live"
PASSWORD = "BigHat2024!"

TAG = uuid.uuid4().hex[:8]


@pytest.fixture(scope="module")
def token() -> str:
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": EMAIL, "password": PASSWORD},
        timeout=20,
    )
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    tok = r.json().get("token")
    assert tok, r.text
    return tok


@pytest.fixture(scope="module")
def auth_headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def user_name(token) -> str:
    """Unique per-run createdBy so listing is deterministic."""
    return f"TEST_alpha37_{TAG}"


# ---------- native mode sanity ----------
def test_native_mode_active():
    r = requests.get(f"{BASE_URL}/api/native/info", timeout=15)
    assert r.status_code == 200, r.text
    assert r.json().get("native_mode") is True


# ---------- Bug 1: presentations import & list ----------
def test_import_trivia_and_list_returns_new_presentation(auth_headers, user_name):
    payload = {
        "userName": user_name,
        "host": "01_Trivia/Web App/01_Hosts/Nick.pptx",
        "location": "01_Trivia/Web App/02_Locations/01_TestBar",
        "numRounds": 5,
        "rounds": [
            "01_Trivia/Web App/03_Rounds/01_MC_test1.pptx",
            "01_Trivia/Web App/03_Rounds/02_REG_test1.pptx",
            "01_Trivia/Web App/03_Rounds/03_MISC_test1.pptx",
            "01_Trivia/Web App/03_Rounds/04_MYS_test1.pptx",
            "01_Trivia/Web App/03_Rounds/05_BIG_test1.pptx",
        ],
        "roundTypes": ["MC", "REG", "MISC", "MYS", "BIG"],
        "roundNames": ["R1", "R2", "R3", "R4", "R5"],
        "presentationName": f"TEST_pres_{TAG}",
        "nativeManifest": {
            "host": {"id": "h1", "name": "Nick"},
            "location": {
                "id": "l1",
                "name": "TestBar",
                "slug": f"testbar-{TAG}",
                "branding_images": [],
                "overlay_images": [],
            },
        },
    }
    r = requests.post(
        f"{BASE_URL}/api/presentations/import-trivia",
        json=payload,
        headers=auth_headers,
        timeout=60,
    )
    assert r.status_code == 200, f"{r.status_code}: {r.text[:500]}"
    data = r.json()
    assert "id" in data and "name" in data, data
    assert data["name"] == payload["presentationName"], data
    pytest.imported_id = data["id"]  # type: ignore[attr-defined]
    pytest.imported_name = data["name"]  # type: ignore[attr-defined]


def test_get_presentations_returns_wizard_saved(auth_headers, user_name):
    """The core bug: after import-trivia, LIST must include it."""
    imported_id = getattr(pytest, "imported_id", None)
    assert imported_id, "prior import test failed to record id"
    r = requests.get(
        f"{BASE_URL}/api/presentations",
        params={"userName": user_name},
        headers=auth_headers,
        timeout=20,
    )
    assert r.status_code == 200, r.text
    lst = r.json()
    assert isinstance(lst, list), lst
    ids = [p.get("id") for p in lst]
    assert imported_id in ids, f"imported presentation missing from list: {ids}"
    # createdBy case-insensitive match
    for p in lst:
        assert (p.get("createdBy") or "").lower() == user_name.lower(), p


def test_get_presentations_viewAll_includes_wizard_saved(auth_headers, user_name):
    imported_id = getattr(pytest, "imported_id", None)
    assert imported_id
    r = requests.get(
        f"{BASE_URL}/api/presentations",
        params={"userName": user_name, "viewAll": "true"},
        headers=auth_headers,
        timeout=30,
    )
    assert r.status_code == 200, r.text
    ids = [p.get("id") for p in r.json()]
    assert imported_id in ids, f"viewAll missed imported id {imported_id}"


# ---------- Bug 2: Files Locations/Hosts tabs list subfolders ----------
_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xcf"
    b"\xc0\x00\x00\x00\x03\x00\x01\x9a\xa8\x8e\x1f\x00\x00\x00\x00IEND\xaeB`\x82"
)


@pytest.fixture(scope="module")
def created_location(token):
    """Create a location + upload 1 branding + 1 overlay."""
    hdrs_json = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    loc_name = f"TEST_Loc_{TAG}"
    r = requests.post(
        f"{BASE_URL}/api/native/locations",
        json={"name": loc_name},
        headers=hdrs_json,
        timeout=20,
    )
    assert r.status_code == 201, f"create_location: {r.status_code} {r.text}"
    loc = r.json()
    loc_id = loc["id"]
    slug = loc["slug"]

    hdrs_upload = {"Authorization": f"Bearer {token}"}
    files = {"file": ("brand.png", io.BytesIO(_PNG_BYTES), "image/png")}
    rb = requests.post(
        f"{BASE_URL}/api/native/locations/{loc_id}/images",
        files=files,
        headers=hdrs_upload,
        timeout=30,
    )
    assert rb.status_code == 201, f"branding upload: {rb.status_code} {rb.text}"

    files = {"file": ("ov.png", io.BytesIO(_PNG_BYTES), "image/png")}
    ro = requests.post(
        f"{BASE_URL}/api/native/locations/{loc_id}/overlays",
        files=files,
        headers=hdrs_upload,
        timeout=30,
    )
    assert ro.status_code == 201, f"overlay upload: {ro.status_code} {ro.text}"

    yield {"id": loc_id, "slug": slug, "name": loc_name}

    # Best-effort teardown.
    try:
        requests.delete(
            f"{BASE_URL}/api/native/locations/{loc_id}", headers=hdrs_upload, timeout=15,
        )
    except Exception:
        pass


def test_files_locations_lists_subfolder_with_counts(created_location):
    r = requests.get(f"{BASE_URL}/api/native/files", params={"folder": "Locations"}, timeout=20)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("selected_folder") == "Locations", body
    assert body.get("count", 0) >= 1, body
    entries = body.get("files") or []
    match = next((e for e in entries if e.get("name") == created_location["slug"]), None)
    assert match, f"slug {created_location['slug']} missing from {entries}"
    assert match.get("type") == "location", match
    summary = match.get("summary") or ""
    assert "1 branding" in summary, summary
    assert "1 overlays" in summary, summary


def test_files_hosts_lists_subfolders():
    r = requests.get(f"{BASE_URL}/api/native/files", params={"folder": "Hosts"}, timeout=20)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("selected_folder") == "Hosts", body
    # All entries (if any) must be type=host and have expected shape.
    for e in body.get("files") or []:
        assert e.get("type") == "host", e
        for field in ("name", "folder", "path", "summary"):
            assert field in e, e


def test_files_top_level_aggregate_no_location_bleed():
    """No folder param → aggregate .bighat listing. Location subfolders
    must NOT leak into this list."""
    r = requests.get(f"{BASE_URL}/api/native/files", timeout=20)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("selected_folder") == "all", body
    for e in body.get("files") or []:
        assert e.get("type") not in ("location", "host"), (
            f"location/host entry leaked into aggregate: {e}"
        )
        # Aggregate entries are .bighat files.
        assert str(e.get("name", "")).endswith(".bighat"), e
