"""
Phase 3 - Round Maker native-mode backend tests.

Validates the BIG Hat Standalone V31 round-maker endpoints when
BIGHAT_NATIVE_MODE=1 (no SharePoint). Premium subscription is OFF -
the round-maker must still operate in local mode because subscription
only gates real cloud SharePoint, not local disk persistence.

Coverage:
- /api/roundmaker/sharepoint-status     -> mode=local, configured=true,
                                            token_valid=true, has subscription block
- /api/roundmaker/reg-title-images      -> includes seeded History/Geography/Music
- /api/roundmaker/reg-title-image-preview/<itemId> -> non-zero PNG bytes
- /api/roundmaker/reg-download-title-image -> copies into roundmaker_uploads
- /api/roundmaker/mc-next-name          -> 200 (no 5xx) without SP creds
- /api/roundmaker/reg-next-number/{cat} -> increments after a round is published
- POST /rounds + GET /rounds + /rounds/{id}/generate
  + /rounds/{id}/upload-sharepoint (master admin) -> file:// web_url + on-disk PPTX
  + appears in /api/trivia/round-files/reg
  + cleanup via DELETE /rounds/{id} and unlink .pptx
- Phase 1 + Phase 2 regression sanity sweep.

Run:
    pytest /app/backend/tests/test_phase3_roundmaker_native.py -v --tb=short \
        --junitxml=/app/test_reports/pytest/phase3_results.xml
"""
import os
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
os.environ.setdefault("BIGHAT_NATIVE_MODE", "1")

with open("/app/frontend/.env") as _fh:
    for _line in _fh:
        if _line.startswith("REACT_APP_BACKEND_URL="):
            BASE_URL = _line.split("=", 1)[1].strip().rstrip("/")
            break

MASTER_EMAIL = "master@bighat.local"
MASTER_PASSWORD = "BigHat2024!"

LOCAL_REG_OUT = Path(
    "/app/backend/native/data/assets/01_Trivia/Web App/00_Builder/01_Rounds/02_REG"
)
LOCAL_TITLECARDS_REG = Path(
    "/app/backend/native/data/assets/01_Trivia/Web App/00_Builder/04_TitleCards/REG"
)


# ---------- fixtures ----------
@pytest.fixture(scope="session")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session")
def auth(api):
    r = api.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": MASTER_EMAIL, "password": MASTER_PASSWORD},
        timeout=15,
    )
    if r.status_code != 200:
        pytest.skip(f"Auth failed: {r.status_code} {r.text[:200]}")
    body = r.json()
    token = body.get("token") or body.get("access_token")
    if token:
        api.headers.update({"Authorization": f"Bearer {token}"})
    return api


# ---------- 1. sharepoint-status ----------
class TestSharepointStatus:
    def test_local_mode_status(self, auth):
        r = auth.get(f"{BASE_URL}/api/roundmaker/sharepoint-status", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("mode") == "local", data
        assert data.get("configured") is True, data
        assert data.get("token_valid") is True, data
        assert "subscription" in data, data
        assert isinstance(data["subscription"], dict)


# ---------- 2. reg-title-images ----------
class TestRegTitleImages:
    @pytest.fixture(scope="class")
    def images_payload(self, auth):
        r = auth.get(f"{BASE_URL}/api/roundmaker/reg-title-images", timeout=15)
        assert r.status_code == 200, r.text
        return r.json()

    def test_payload_shape(self, images_payload):
        assert "images" in images_payload
        assert isinstance(images_payload["images"], list)

    def test_seeded_titles_present(self, images_payload):
        names = {img.get("name") for img in images_payload["images"]}
        # The seeded files are History.png, Geography.png, Music.png
        assert {"History", "Geography", "Music"}.issubset(names), (
            f"expected seeded title cards, got {names}"
        )

    def test_item_ids_are_relative_local_paths(self, images_payload):
        for img in images_payload["images"]:
            iid = img.get("itemId", "")
            assert iid, img
            assert "04_TitleCards/REG/" in iid, iid


# ---------- 3. reg-title-image-preview ----------
class TestRegTitleImagePreview:
    def test_preview_returns_png_bytes(self, auth):
        listing = auth.get(
            f"{BASE_URL}/api/roundmaker/reg-title-images", timeout=15
        ).json()["images"]
        history = next((i for i in listing if i["name"] == "History"), None)
        assert history is not None, listing
        item_id = history["itemId"]

        r = auth.get(
            f"{BASE_URL}/api/roundmaker/reg-title-image-preview/{item_id}",
            timeout=15,
        )
        assert r.status_code == 200, r.text
        assert r.headers.get("content-type", "").startswith("image/")
        assert len(r.content) > 0
        # PNG magic
        assert r.content[:4] == b"\x89PNG", "expected PNG magic bytes"


# ---------- 4. reg-download-title-image ----------
class TestRegDownloadTitleImage:
    def test_download_copies_to_uploads(self, auth):
        listing = auth.get(
            f"{BASE_URL}/api/roundmaker/reg-title-images", timeout=15
        ).json()["images"]
        history = next((i for i in listing if i["name"] == "History"), None)
        assert history is not None

        body = {"item_id": history["itemId"], "filename": "title_test.png"}
        r = auth.post(
            f"{BASE_URL}/api/roundmaker/reg-download-title-image",
            json=body,
            timeout=20,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("filename") == "title_test.png"
        assert "file_id" in data
        # file actually exists
        assert Path(data["path"]).exists()


# ---------- 5. mc-next-name ----------
class TestMcNextName:
    def test_returns_200_in_local_mode(self, auth):
        r = auth.get(f"{BASE_URL}/api/roundmaker/mc-next-name", timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        # must contain a candidate name field
        assert any(k in data for k in ("next_name", "round_name", "name")), data


# ---------- 6+7. round-maker round-trip + reg-next-number increment ----------
class TestRoundTrip:
    CATEGORY = "TestPhase3"
    ROUND_NAME = "TestPhase3_1"

    @pytest.fixture(scope="class")
    def created_round(self, auth):
        # baseline next-number for this synthetic category
        r0 = auth.get(
            f"{BASE_URL}/api/roundmaker/reg-next-number/{self.CATEGORY}",
            timeout=15,
        )
        assert r0.status_code == 200, r0.text
        baseline = r0.json().get("next_number")
        assert isinstance(baseline, int)

        payload = {
            "round_type": "REG",
            "name": self.ROUND_NAME,
            "questions": [
                {"number": 1, "question": "Capital of France?", "answer": "Paris"},
                {"number": 2, "question": "2 + 2 = ?", "answer": "4"},
            ],
        }
        rc = auth.post(
            f"{BASE_URL}/api/roundmaker/rounds", json=payload, timeout=20
        )
        assert rc.status_code == 200, rc.text
        doc = rc.json()
        rid = doc["id"]
        yield {"id": rid, "baseline": baseline}

        # Teardown: delete round + remove pptx file if it landed on disk
        try:
            auth.delete(f"{BASE_URL}/api/roundmaker/rounds/{rid}", timeout=15)
        except Exception:
            pass
        try:
            (LOCAL_REG_OUT / f"{self.ROUND_NAME}.pptx").unlink(missing_ok=True)
        except Exception:
            pass

    def test_get_rounds_includes_created(self, auth, created_round):
        rl = auth.get(f"{BASE_URL}/api/roundmaker/rounds", timeout=15)
        assert rl.status_code == 200, rl.text
        ids = [r.get("id") for r in rl.json()]
        assert created_round["id"] in ids

    def test_generate_returns_pptx(self, auth, created_round):
        r = auth.post(
            f"{BASE_URL}/api/roundmaker/rounds/{created_round['id']}/generate",
            timeout=60,
        )
        assert r.status_code == 200, r.text[:300]
        ct = r.headers.get("content-type", "")
        assert "presentation" in ct or "pptx" in ct or "octet-stream" in ct, ct
        assert len(r.content) > 100 * 1024, (
            f"PPTX smaller than 100KB: {len(r.content)} bytes"
        )

    def test_upload_sharepoint_publishes_locally(self, auth, created_round):
        r = auth.post(
            f"{BASE_URL}/api/roundmaker/rounds/{created_round['id']}/upload-sharepoint",
            timeout=60,
        )
        assert r.status_code == 200, r.text[:400]
        data = r.json()
        assert data.get("status") == "success", data
        web_url = data.get("web_url", "")
        assert web_url.startswith("file://"), f"expected file:// URL, got {web_url}"
        # File is on disk
        target = LOCAL_REG_OUT / f"{self.ROUND_NAME}.pptx"
        assert target.exists(), f"missing published file at {target}"
        assert target.stat().st_size > 100 * 1024

    def test_round_files_reg_includes_published(self, auth, created_round):
        r = auth.get(f"{BASE_URL}/api/trivia/round-files/reg", timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data, list)
        # entries may be strings or dicts; flatten to names
        names = []
        for entry in data:
            if isinstance(entry, str):
                names.append(entry)
            elif isinstance(entry, dict):
                names.append(entry.get("name") or entry.get("filename") or "")
        assert any(self.ROUND_NAME in n for n in names), (
            f"{self.ROUND_NAME} not in REG round-files: {names[:25]}..."
        )

    def test_reg_next_number_increments_for_synthetic_category(
        self, auth, created_round
    ):
        # Drop a synthetic file to verify the local-folder scan increments
        synth = LOCAL_REG_OUT / f"{self.CATEGORY}_{created_round['baseline']}.pptx"
        try:
            synth.write_bytes(b"PK\x03\x04synthetic")
            r = auth.get(
                f"{BASE_URL}/api/roundmaker/reg-next-number/{self.CATEGORY}",
                timeout=15,
            )
            assert r.status_code == 200, r.text
            after = r.json().get("next_number")
            assert after == created_round["baseline"] + 1, (
                f"expected increment from {created_round['baseline']} "
                f"to {created_round['baseline'] + 1}, got {after}"
            )
        finally:
            synth.unlink(missing_ok=True)


# ---------- 8. Premium gate sanity (subscription off, local still works) ----------
class TestPremiumGateSanity:
    def test_subscription_default_off_then_local_still_serves(self, auth):
        # Force subscription OFF
        r_off = auth.post(
            f"{BASE_URL}/api/native/subscription",
            json={"active": False, "tier": "premium", "sharepoint_enabled": False},
            timeout=15,
        )
        assert r_off.status_code == 200, r_off.text

        # sharepoint-status still reports local + token_valid
        r = auth.get(f"{BASE_URL}/api/roundmaker/sharepoint-status", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert data.get("mode") == "local"
        assert data.get("token_valid") is True

        # title images endpoint still works
        ri = auth.get(f"{BASE_URL}/api/roundmaker/reg-title-images", timeout=15)
        assert ri.status_code == 200


# ---------- 9. Phase 1+2 regression sanity ----------
class TestRegression:
    @pytest.mark.parametrize(
        "endpoint",
        [
            "/api/trivia/hosts",
            "/api/trivia/locations",
            "/api/trivia/sponsors",
            "/api/trivia/rounds",
            "/api/venues",
            "/api/events",
        ],
    )
    def test_endpoint_200_list(self, auth, endpoint):
        r = auth.get(f"{BASE_URL}{endpoint}", timeout=20)
        assert r.status_code == 200, f"{endpoint} -> {r.status_code}: {r.text[:200]}"
        assert isinstance(r.json(), list)

    def test_slides_metadata_for_unknown_id(self, auth):
        # Phase 2 endpoint; should return JSON (not 5xx) for unknown id
        r = auth.get(
            f"{BASE_URL}/api/trivia-import/slides-metadata/UNKNOWN_TEST_ID",
            timeout=15,
        )
        assert r.status_code in (200, 404), r.text[:200]

    def test_presentations_list_endpoint(self, auth):
        r = auth.get(
            f"{BASE_URL}/api/presentations?userName=TEST_NoUser", timeout=20
        )
        assert r.status_code == 200
        assert isinstance(r.json(), list)
