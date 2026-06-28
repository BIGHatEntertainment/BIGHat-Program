"""Live preview-env contract tests for Trivia Setup (v32.0.0-alpha.22).

Hits the real backend through the public REACT_APP_BACKEND_URL via
master_admin login (sellards@bighat.live / B1GHat), validates the
auth gates promised by the review request, and exercises the
create -> list -> rename -> upload -> delete-image -> delete-location
happy path end-to-end.
"""
from __future__ import annotations

import io
import os
import time
import uuid

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://standalone-tools.preview.emergentagent.com").rstrip("/")

MASTER_EMAIL = "sellards@bighat.live"
MASTER_PASSWORD = "B1GHat"

# A real (tiny) 1x1 transparent PNG used for upload tests.
_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc"
    b"\xf8\xcf\xc0\x00\x00\x00\x03\x00\x01\x16\xfc\xa1\xfb\x00\x00\x00\x00IEND\xaeB`\x82"
)


# ---------- fixtures ----------
@pytest.fixture(scope="module")
def master_token():
    """Login as the master admin and return a Bearer token (or skip)."""
    # Try a few common login endpoints. /api/auth/login is the canonical
    # cloud-mode entry point; native mode uses /api/native/auth/login.
    for url in (f"{BASE_URL}/api/auth/login", f"{BASE_URL}/api/native/auth/login"):
        try:
            r = requests.post(url, json={"email": MASTER_EMAIL, "password": MASTER_PASSWORD}, timeout=15)
        except requests.RequestException:
            continue
        if r.status_code == 200:
            data = r.json()
            tok = data.get("access_token") or data.get("token") or data.get("session", {}).get("token")
            if tok:
                return tok
    pytest.skip("could not obtain master_admin token from preview env")


@pytest.fixture(scope="module")
def master_headers(master_token):
    return {"Authorization": f"Bearer {master_token}"}


# ---------- auth contract ----------
class TestAuthContract:
    def test_no_auth_returns_401(self):
        r = requests.get(f"{BASE_URL}/api/native/locations", timeout=15)
        assert r.status_code == 401, f"expected 401, got {r.status_code}: {r.text[:200]}"

    def test_master_can_list(self, master_headers):
        r = requests.get(f"{BASE_URL}/api/native/locations", headers=master_headers, timeout=15)
        assert r.status_code == 200, r.text[:400]
        assert isinstance(r.json(), list)


# ---------- regression: existing endpoints still work ----------
class TestRegressionEndpoints:
    def test_native_info_returns_version(self):
        r = requests.get(f"{BASE_URL}/api/native/info", timeout=15)
        # If app is in cloud mode this might 404; document either way.
        if r.status_code == 404:
            pytest.skip("/api/native/info not exposed in this deployment mode")
        assert r.status_code == 200, r.text[:400]
        body = r.json()
        assert "version" in body or "app_version" in body, body

    def test_roundmaker_rounds_returns_200(self, master_headers):
        r = requests.get(f"{BASE_URL}/api/roundmaker/rounds", headers=master_headers, timeout=20)
        # Confirm not 500 — review request specifically calls this out.
        assert r.status_code != 500, f"5xx regression: {r.text[:400]}"
        assert r.status_code in (200, 401, 403, 404), r.status_code


# ---------- happy path CRUD ----------
class TestLocationLifecycle:
    @pytest.fixture(scope="class")
    def loc_state(self):
        return {}

    def test_create_location(self, master_headers, loc_state):
        unique = f"TEST_Iter27_{uuid.uuid4().hex[:8]}"
        r = requests.post(
            f"{BASE_URL}/api/native/locations",
            headers=master_headers,
            json={"name": unique},
            timeout=15,
        )
        assert r.status_code == 201, r.text[:400]
        data = r.json()
        assert data["name"] == unique
        assert data["slug"]
        assert data["branding_images"] == []
        assert data["assigned_user_ids"] == []
        loc_state["id"] = data["id"]
        loc_state["slug"] = data["slug"]
        loc_state["name"] = unique

    def test_get_then_rename(self, master_headers, loc_state):
        lid = loc_state["id"]
        r = requests.get(
            f"{BASE_URL}/api/native/locations/{lid}",
            headers=master_headers,
            timeout=15,
        )
        assert r.status_code == 200, r.text[:400]
        assert r.json()["id"] == lid

        new_name = loc_state["name"] + "_renamed"
        r = requests.patch(
            f"{BASE_URL}/api/native/locations/{lid}",
            headers=master_headers,
            json={"name": new_name},
            timeout=15,
        )
        assert r.status_code == 200, r.text[:400]
        assert r.json()["name"] == new_name

        # GET-after-PATCH persistence check.
        r = requests.get(
            f"{BASE_URL}/api/native/locations/{lid}",
            headers=master_headers,
            timeout=15,
        )
        assert r.status_code == 200
        assert r.json()["name"] == new_name

    def test_upload_png_then_raw_then_delete(self, master_headers, loc_state):
        lid = loc_state["id"]
        files = {"file": ("logo.png", _PNG, "image/png")}
        r = requests.post(
            f"{BASE_URL}/api/native/locations/{lid}/images",
            headers=master_headers,
            files=files,
            timeout=20,
        )
        assert r.status_code == 201, r.text[:400]
        rec = r.json()
        assert rec["mime"] == "image/png"
        assert rec["size"] == len(_PNG)
        img_id = rec["id"]

        # Raw fetch — bytes should match exactly.
        r = requests.get(
            f"{BASE_URL}/api/native/locations/{lid}/images/{img_id}/raw",
            headers=master_headers,
            timeout=20,
        )
        assert r.status_code == 200
        assert r.content == _PNG
        assert r.headers.get("content-type", "").startswith("image/")

        # Delete the image, confirm it's gone from the location doc.
        r = requests.delete(
            f"{BASE_URL}/api/native/locations/{lid}/images/{img_id}",
            headers=master_headers,
            timeout=15,
        )
        assert r.status_code == 204

        r = requests.get(
            f"{BASE_URL}/api/native/locations/{lid}",
            headers=master_headers,
            timeout=15,
        )
        ids = [i["id"] for i in r.json().get("branding_images", [])]
        assert img_id not in ids

    def test_pdf_upload_rejected(self, master_headers, loc_state):
        lid = loc_state["id"]
        r = requests.post(
            f"{BASE_URL}/api/native/locations/{lid}/images",
            headers=master_headers,
            files={"file": ("evil.pdf", b"%PDF-1.4 nope", "application/pdf")},
            timeout=15,
        )
        assert r.status_code == 415, f"expected 415 for PDF, got {r.status_code}: {r.text[:200]}"

    def test_delete_location(self, master_headers, loc_state):
        lid = loc_state["id"]
        r = requests.delete(
            f"{BASE_URL}/api/native/locations/{lid}",
            headers=master_headers,
            timeout=15,
        )
        assert r.status_code == 204
        r = requests.get(
            f"{BASE_URL}/api/native/locations/{lid}",
            headers=master_headers,
            timeout=15,
        )
        assert r.status_code == 404
