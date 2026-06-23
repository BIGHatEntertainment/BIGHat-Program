"""
Post-merge verification (iteration 14)
======================================

Verifies that the recent session work (Files tool, downloads resolver,
native setup, VERSION bump to 32.0.0-alpha.11) is still intact after
the user resolved a GitHub conflict via a pull request.

Scope is intentionally narrow — see /app/test_reports/iteration_14.json.
"""
from __future__ import annotations

import io
import json
import os
import uuid
import zipfile
from pathlib import Path

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE_URL:
    # Fall back to frontend/.env so the file works when invoked from CI.
    env_path = Path(__file__).resolve().parents[2] / "frontend" / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip()
                break
assert BASE_URL, "REACT_APP_BACKEND_URL is required"
BASE_URL = BASE_URL.rstrip("/")

EXPECTED_VERSION = "32.0.0-alpha.11"
ACCEPTABLE_VERSIONS = {"32.0.0-alpha.11", "32.0.0-alpha.10"}


# ---------- shared fixtures ----------
@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    sess.headers.update({"Accept": "application/json"})
    return sess


def _make_bighat_zip(content_type: str = "round", name: str = "Post-merge round") -> bytes:
    """Build a minimal but valid .bighat archive for upload tests."""
    buf = io.BytesIO()
    manifest = {
        "format": "bighat/round",
        "version": 1,
        "type": content_type,
        "round_name": name,
    }
    payload = {
        "name": name,
        "questions": [
            {"number": 1, "question": "Q1?", "answer": "A1", "category": "Trivia"},
            {"number": 2, "question": "Q2?", "answer": "A2", "category": "Trivia"},
        ],
        "tiebreaker": {"question": "How many?", "answer": "42"},
    }
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest))
        zf.writestr("payload.json", json.dumps(payload))
    return buf.getvalue()


# ---------- basic health ----------
class TestBackendHealth:
    def test_root_api_returns_200(self, s):
        r = s.get(f"{BASE_URL}/api/")
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data, dict)
        assert data.get("status") in {"running", "ok"} or "BIG Hat" in (data.get("message") or "")


# ---------- VERSION sanity ----------
class TestVersionSanity:
    def test_version_txt_matches_expected(self):
        p = Path("/app/backend/VERSION.txt")
        assert p.exists(), "/app/backend/VERSION.txt missing"
        assert p.read_text().strip() == EXPECTED_VERSION

    def test_tauri_conf_version_matches_expected(self):
        p = Path("/app/src-tauri/tauri.conf.json")
        assert p.exists()
        conf = json.loads(p.read_text())
        assert conf["version"] == EXPECTED_VERSION, (
            f"tauri.conf.json reports {conf['version']!r}, expected {EXPECTED_VERSION!r}"
        )

    def test_native_info_reports_acceptable_version(self, s):
        r = s.get(f"{BASE_URL}/api/native/info")
        assert r.status_code == 200, r.text
        v = r.json().get("version")
        assert v in ACCEPTABLE_VERSIONS, (
            f"/api/native/info reported version {v!r} — expected one of {ACCEPTABLE_VERSIONS}"
        )

    def test_version_files_internally_consistent(self):
        """VERSION.txt and tauri.conf.json must agree."""
        v_txt = Path("/app/backend/VERSION.txt").read_text().strip()
        v_tauri = json.loads(Path("/app/src-tauri/tauri.conf.json").read_text())["version"]
        assert v_txt == v_tauri, f"VERSION.txt={v_txt} vs tauri.conf.json={v_tauri}"


# ---------- Files tool ----------
class TestFilesFolder:
    def test_folder_endpoint(self, s):
        r = s.get(f"{BASE_URL}/api/native/files/folder")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["ok"] is True
        assert isinstance(data.get("folder"), str) and data["folder"]
        assert "platform" in data
        assert isinstance(data.get("exists"), bool)


class TestFilesList:
    def test_list_returns_expected_shape(self, s):
        r = s.get(f"{BASE_URL}/api/native/files")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["ok"] is True
        assert isinstance(data.get("folder"), str)
        assert isinstance(data.get("count"), int)
        assert isinstance(data.get("files"), list)
        assert data["count"] == len(data["files"])

    def test_listed_files_have_required_fields(self, s):
        """Each file entry must surface name/size_bytes/modified_at/type/summary."""
        r = s.get(f"{BASE_URL}/api/native/files")
        data = r.json()
        for entry in data["files"]:
            assert "name" in entry and entry["name"].endswith(".bighat")
            assert isinstance(entry.get("size_bytes"), int)
            assert isinstance(entry.get("modified_at"), str)
            assert isinstance(entry.get("type"), str)
            # summary is added by _summarise_bighat — should exist except for
            # truly unparseable archives (rare).
            assert "summary" in entry, f"missing summary on {entry['name']}"


class TestFilesUploadDownloadDelete:
    """Full round-trip: upload → list-includes → download → delete → 404."""

    test_name = f"TEST_postmerge_{uuid.uuid4().hex[:8]}.bighat"

    def test_01_upload(self, s):
        blob = _make_bighat_zip()
        files = {"file": (self.test_name, blob, "application/octet-stream")}
        r = s.post(f"{BASE_URL}/api/native/files/upload", files=files)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is True
        assert body["name"] == self.test_name
        assert body["size_bytes"] == len(blob)
        assert isinstance(body["path"], str)

    def test_02_listed_after_upload(self, s):
        r = s.get(f"{BASE_URL}/api/native/files")
        data = r.json()
        names = [f["name"] for f in data["files"]]
        assert self.test_name in names, f"{self.test_name} missing from {names}"
        entry = next(f for f in data["files"] if f["name"] == self.test_name)
        # We uploaded a "round" archive — summary should mention "Round".
        assert entry["type"] == "round"
        assert "Round" in (entry.get("summary") or "")

    def test_03_download(self, s):
        r = s.get(f"{BASE_URL}/api/native/files/download/{self.test_name}")
        assert r.status_code == 200, r.text
        # Bytes should be a valid zip.
        assert r.content[:2] == b"PK", "downloaded file is not a zip"
        with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
            assert "manifest.json" in zf.namelist()
            assert "payload.json" in zf.namelist()

    def test_04_delete(self, s):
        r = s.delete(f"{BASE_URL}/api/native/files/{self.test_name}")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is True
        assert body["deleted"] == self.test_name

    def test_05_download_after_delete_is_404(self, s):
        r = s.get(f"{BASE_URL}/api/native/files/download/{self.test_name}")
        assert r.status_code == 404


class TestFilesValidation:
    def test_upload_rejects_non_bighat_extension(self, s):
        files = {"file": ("nope.txt", b"hello", "text/plain")}
        r = s.post(f"{BASE_URL}/api/native/files/upload", files=files)
        assert r.status_code == 400
        assert "bighat" in r.json().get("detail", "").lower()

    def test_download_path_traversal_rejected(self, s):
        r = s.get(f"{BASE_URL}/api/native/files/download/..%2Fetc%2Fpasswd")
        assert r.status_code in (400, 404)


# ---------- Downloads resolver ----------
class TestDownloadsResolver:
    GH_PREFIX = "https://github.com/BIGHatEntertainment/BIGHat-Program/releases"

    def test_latest_returns_valid_payload(self, s):
        r = s.get(f"{BASE_URL}/api/downloads/latest")
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data.get("version"), str) and data["version"]
        platforms = data.get("platforms") or {}
        # All three OS keys must be present (canonical resolver naming uses
        # `macos_*`; review request referenced `mac_*` informally).
        for key in ("windows", "macos_apple", "macos_intel"):
            assert key in platforms, f"missing platforms.{key} in {list(platforms)}"

    def test_latest_urls_point_at_github_release(self, s):
        r = s.get(f"{BASE_URL}/api/downloads/latest")
        platforms = r.json()["platforms"]
        # `windows` and `macos_apple` URLs MUST be live (these are the
        # actively-published assets). `macos_intel.url` is allowed to be
        # null when no Intel .dmg has been published for this release —
        # see test_phase10_8b_downloads_precision.py for why we prefer
        # null over a mis-routed binary.
        for key in ("windows", "macos_apple"):
            url = platforms[key].get("url")
            assert isinstance(url, str) and url, f"platforms.{key}.url empty"
            assert url.startswith(self.GH_PREFIX), (
                f"platforms.{key}.url {url!r} does not point at the BIG Hat GH releases"
            )
        # macos_intel may be null OR a github release URL — never anything else.
        intel_url = platforms["macos_intel"].get("url")
        assert intel_url is None or intel_url.startswith(self.GH_PREFIX), (
            f"platforms.macos_intel.url {intel_url!r} is neither null nor a GH release URL"
        )

    def test_latest_version_is_acceptable(self, s):
        v = s.get(f"{BASE_URL}/api/downloads/latest").json()["version"]
        # The downloads resolver reports the latest *published* GitHub release,
        # which may legitimately lag VERSION.txt by one alpha (e.g. alpha.11
        # bumped in repo but only alpha.10 published). Both are OK.
        assert v in ACCEPTABLE_VERSIONS, (
            f"/api/downloads/latest reports {v!r} — expected one of {ACCEPTABLE_VERSIONS}"
        )


# ---------- Native setup ----------
class TestNativeSetup:
    """Verify the offline_mode:true path. Because this environment already
    has setup_complete=true, the endpoint returns 409 setup_already_complete
    — that IS the correct idempotent response and proves the route is
    wired and reachable. We also exercise the path with a fresh payload to
    confirm the validation order (well-formedness) when not already setup."""

    def test_setup_status_reports_complete(self, s):
        r = s.get(f"{BASE_URL}/api/native/setup/status")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["setup_complete"] is True
        assert data["native_mode"] is True

    def test_initialize_offline_mode_is_idempotent_409(self, s):
        payload = {
            "license_key": "BHAT-AAAA-BBBB-CCCC-DDDD-EEEE",
            "master_admin": {
                "email": "postmerge@bighat.local",
                "first_name": "PostMerge",
                "last_name": "Verifier",
                "password": "PostMerge2026!",
            },
            "settings": {"company_name": "Post-merge Test", "location_name": "Test Venue"},
            "offline_mode": True,
        }
        r = s.post(f"{BASE_URL}/api/native/setup/initialize", json=payload)
        # Already complete → 409 (proves the route is wired and the
        # offline_mode field is accepted by the SetupInitRequest schema).
        # A 200 would only be possible from a wiped environment; treat
        # anything else as a regression.
        assert r.status_code == 409, (
            f"expected 409 setup_already_complete, got {r.status_code}: {r.text[:300]}"
        )
        detail = r.json().get("detail")
        assert detail == "setup_already_complete"


# ---------- Reference-file existence (post-merge integrity) ----------
class TestReferenceFilesPresent:
    def test_squarespace_poller_present(self):
        assert Path("/app/backend/cloud/squarespace_poller.py").exists()

    def test_auto_tag_workflow_present_and_watches_version(self):
        p = Path("/app/.github/workflows/auto-tag.yml")
        assert p.exists()
        assert "backend/VERSION.txt" in p.read_text()

    def test_files_router_helpers_present(self):
        src = Path("/app/backend/native/files_router.py").read_text()
        assert "def _summarise_bighat" in src
        assert "def _trivia_summary" in src
        for route in ('@router.get("/folder")', '@router.get("")',
                      '@router.post("/upload")', '@router.get("/download/{name}")',
                      '@router.delete("/{name}")'):
            assert route in src, f"missing route decorator: {route}"

    def test_tauri_lib_has_apple_event_and_route_for_bighat(self):
        src = Path("/app/src-tauri/src/lib.rs").read_text()
        assert "route_for_bighat" in src
        # Apple Event handling for .bighat files
        assert "bighat" in src.lower()
        assert "Apple Event" in src or "apple_event" in src.lower()

    def test_frontend_files_and_update_tool_present_no_sponsor_portal(self):
        assert Path("/app/frontend/src/pages/FilesTool.jsx").exists()
        assert Path("/app/frontend/src/pages/UpdateTool.jsx").exists()
        assert not Path("/app/frontend/src/pages/SponsorPortal.jsx").exists()
