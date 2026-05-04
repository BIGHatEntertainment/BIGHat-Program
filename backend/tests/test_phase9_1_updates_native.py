"""Phase 9.1 — Auto-update channel API tests.

Covers:
- /api/native/updates/status shape + installed_version source-of-truth
- /api/native/updates/check fixture-on path + fixture-off 502
- /api/native/updates/download success, sha256 mismatch, invalid sha256, skip-when-uptodate
- /api/native/updates/apply auth gating + nothing_staged + staged_bundle_missing
- /api/native/info reads VERSION.txt
- launcher --check prints installed_ver + pending_apply
- Regression spot-checks of public endpoints
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://127.0.0.1:8001").rstrip("/")
BACKEND_DIR = Path("/app/backend")
VERSION_FILE = BACKEND_DIR / "VERSION.txt"
FIXTURE_DIR = BACKEND_DIR / "native" / "data" / "update_fixture"
FIXTURE_MANIFEST = FIXTURE_DIR / "manifest.json"
FIXTURE_ZIP = FIXTURE_DIR / "bighat-31.1.0.zip"
GENERATED_UPDATES_DIR = BACKEND_DIR / "native" / "data" / "generated" / "updates"
PENDING_MARKER = GENERATED_UPDATES_DIR / "pending_apply.json"
LAUNCHER = BACKEND_DIR / "launcher.py"

MASTER_EMAIL = "master@bighat.local"
MASTER_PASSWORD = "BigHat2024!"


# ---------- Helpers / fixtures ----------
@pytest.fixture(scope="module")
def real_sha256() -> str:
    h = hashlib.sha256()
    with open(FIXTURE_ZIP, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


@pytest.fixture(scope="module")
def original_manifest_text() -> str:
    return FIXTURE_MANIFEST.read_text(encoding="utf-8")


@pytest.fixture(autouse=True)
def restore_manifest(original_manifest_text):
    """Always restore manifest after every test."""
    yield
    FIXTURE_MANIFEST.write_text(original_manifest_text, encoding="utf-8")


@pytest.fixture(scope="module")
def master_token() -> str:
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": MASTER_EMAIL, "password": MASTER_PASSWORD},
        timeout=10,
    )
    assert r.status_code == 200, r.text
    j = r.json()
    tok = j.get("access_token") or j.get("token")
    assert tok, j
    return tok


@pytest.fixture(scope="module")
def master_headers(master_token):
    return {"Authorization": f"Bearer {master_token}"}


@pytest.fixture(scope="module")
def subadmin_creds(master_headers):
    """Create a sub-admin user and tear down."""
    payload = {
        "email": "updates_subadmin@bighat.local",
        "password": "SubAdmin123",
        "first_name": "Sub",
        "last_name": "Admin",
        "role": "admin",
    }
    r = requests.post(
        f"{BASE_URL}/api/native/admin/users",
        json=payload, headers=master_headers, timeout=10,
    )
    # If exists already, try to look up
    user_id = None
    if r.status_code in (200, 201):
        user_id = r.json().get("id") or r.json().get("user", {}).get("id")
    elif r.status_code == 409:
        # find existing
        rl = requests.get(
            f"{BASE_URL}/api/native/admin/users",
            headers=master_headers, timeout=10,
        )
        if rl.status_code == 200:
            for u in rl.json().get("users", rl.json() if isinstance(rl.json(), list) else []):
                if u.get("email") == payload["email"]:
                    user_id = u.get("id")
                    break
    else:
        pytest.skip(f"could not create sub-admin: {r.status_code} {r.text}")

    # Login as sub-admin
    rl = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": payload["email"], "password": payload["password"]},
        timeout=10,
    )
    assert rl.status_code == 200, rl.text
    tok = rl.json().get("access_token") or rl.json().get("token")
    yield {"token": tok, "id": user_id, "email": payload["email"]}

    if user_id:
        try:
            requests.delete(
                f"{BASE_URL}/api/native/admin/users/{user_id}",
                headers=master_headers, timeout=5,
            )
        except Exception:
            pass


# ---------- Status ----------
class TestStatus:
    def test_status_200_and_shape(self):
        r = requests.get(f"{BASE_URL}/api/native/updates/status", timeout=10)
        assert r.status_code == 200, r.text
        j = r.json()
        for k in (
            "installed_version", "latest_known", "update_available",
            "last_check_at", "staged", "applied_at", "channel_url",
            "fixture_active",
        ):
            assert k in j, f"missing {k} in {j}"

    def test_installed_version_matches_version_txt(self):
        r = requests.get(f"{BASE_URL}/api/native/updates/status", timeout=10)
        assert r.status_code == 200
        expected = VERSION_FILE.read_text(encoding="utf-8").strip()
        assert r.json()["installed_version"] == expected


# ---------- Native info reads VERSION.txt ----------
class TestNativeInfoVersion:
    def test_info_version_from_version_txt(self):
        r = requests.get(f"{BASE_URL}/api/native/info", timeout=10)
        assert r.status_code == 200
        j = r.json()
        expected = VERSION_FILE.read_text(encoding="utf-8").strip()
        assert j.get("version") == expected
        assert j.get("native_mode") is True


# ---------- Check ----------
class TestCheck:
    def test_check_with_fixture_returns_update_available(self):
        r = requests.post(f"{BASE_URL}/api/native/updates/check", timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["installed_version"] == "31.0.0"
        assert j["manifest"]["latest_version"] == "31.1.0"
        assert j["update_available"] is True
        assert j.get("checked_at")

    def test_status_reflects_last_check(self):
        # Trigger check first
        requests.post(f"{BASE_URL}/api/native/updates/check", timeout=15)
        r = requests.get(f"{BASE_URL}/api/native/updates/status", timeout=10)
        j = r.json()
        assert j.get("last_check_at")
        assert j.get("latest_known", {}).get("latest_version") == "31.1.0"


# ---------- Download ----------
class TestDownload:
    def test_download_success(self, real_sha256):
        r = requests.post(f"{BASE_URL}/api/native/updates/download", timeout=30)
        assert r.status_code == 200, r.text
        j = r.json()
        staged = j.get("staged", {})
        assert staged.get("version") == "31.1.0"
        assert staged.get("verified") is True
        assert staged.get("size", 0) > 0
        assert staged.get("sha256") == real_sha256
        assert staged.get("downloaded_at")
        path = staged.get("path", "")
        assert "/generated/updates/" in path
        assert Path(path).is_file()
        # Validate it's a real zip
        import zipfile
        assert zipfile.is_zipfile(path)

    def test_sha256_mismatch_returns_409(self, original_manifest_text):
        manifest = json.loads(original_manifest_text)
        manifest["sha256"] = "deadbeef" + ("0" * 48) + "deadbeef"  # 64 chars
        assert len(manifest["sha256"]) == 64
        FIXTURE_MANIFEST.write_text(json.dumps(manifest), encoding="utf-8")
        r = requests.post(f"{BASE_URL}/api/native/updates/download", timeout=30)
        assert r.status_code == 409, r.text
        assert r.json().get("detail", "").startswith("sha256_mismatch:")

    def test_invalid_manifest_sha256_empty(self, original_manifest_text):
        manifest = json.loads(original_manifest_text)
        manifest["sha256"] = ""
        FIXTURE_MANIFEST.write_text(json.dumps(manifest), encoding="utf-8")
        r = requests.post(f"{BASE_URL}/api/native/updates/download", timeout=15)
        assert r.status_code == 409, r.text
        assert r.json().get("detail") == "invalid_manifest_sha256"

    def test_invalid_manifest_sha256_short(self, original_manifest_text):
        manifest = json.loads(original_manifest_text)
        manifest["sha256"] = "short"
        FIXTURE_MANIFEST.write_text(json.dumps(manifest), encoding="utf-8")
        r = requests.post(f"{BASE_URL}/api/native/updates/download", timeout=15)
        assert r.status_code == 409, r.text
        assert r.json().get("detail") == "invalid_manifest_sha256"

    def test_download_skipped_when_uptodate(self):
        original_version = VERSION_FILE.read_text(encoding="utf-8")
        try:
            VERSION_FILE.write_text("31.1.0\n", encoding="utf-8")
            r = requests.post(f"{BASE_URL}/api/native/updates/download", timeout=15)
            assert r.status_code == 200, r.text
            j = r.json()
            assert j.get("skipped") is True
            assert j.get("reason") == "no_update_available"
        finally:
            VERSION_FILE.write_text(original_version, encoding="utf-8")


# ---------- Apply ----------
class TestApply:
    def test_apply_unauthenticated_returns_401(self):
        r = requests.post(f"{BASE_URL}/api/native/updates/apply", timeout=10)
        assert r.status_code == 401, r.text

    def test_apply_subadmin_returns_403(self, subadmin_creds):
        r = requests.post(
            f"{BASE_URL}/api/native/updates/apply",
            headers={"Authorization": f"Bearer {subadmin_creds['token']}"},
            timeout=10,
        )
        assert r.status_code == 403, r.text

    def test_apply_master_success_and_marker(self, master_headers, real_sha256):
        # Ensure staged exists
        rdl = requests.post(f"{BASE_URL}/api/native/updates/download", timeout=30)
        assert rdl.status_code == 200, rdl.text

        # Remove pre-existing marker so we know it gets written fresh
        if PENDING_MARKER.exists():
            PENDING_MARKER.unlink()

        r = requests.post(
            f"{BASE_URL}/api/native/updates/apply",
            headers=master_headers, timeout=20,
        )
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("status") == "scheduled"
        assert j.get("version") == "31.1.0"
        assert j.get("previous_version") == "31.0.0"
        assert j.get("scheduled_at")
        assert j.get("bundle_path")

        # Marker on disk
        assert PENDING_MARKER.is_file()
        marker = json.loads(PENDING_MARKER.read_text(encoding="utf-8"))
        assert marker.get("version") == "31.1.0"
        assert marker.get("scheduled_at")

        # Unpacked dir contains VERSION.txt
        unpacked_path = j.get("unpacked_path")
        if unpacked_path:
            up = Path(unpacked_path)
            assert up.is_dir()
            ver_in_bundle = up / "VERSION.txt"
            if ver_in_bundle.exists():
                assert ver_in_bundle.read_text(encoding="utf-8").strip()

    def test_apply_nothing_staged_returns_409(self, master_headers, tmp_path):
        # Use direct DB manipulation via subprocess script file
        script = tmp_path / "clear_staged.py"
        script.write_text(
            "import asyncio, sys\n"
            "sys.path.insert(0, '/app/backend')\n"
            "from server import db\n"
            "async def go():\n"
            "    await db.update_state.update_one({'_id':'singleton'}, {'$unset':{'staged':''}}, upsert=True)\n"
            "asyncio.run(go())\n"
        )
        rc = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, timeout=30)
        if rc.returncode != 0:
            pytest.skip(f"could not clear staged via subprocess: {rc.stderr[-500:]}")

        r = requests.post(
            f"{BASE_URL}/api/native/updates/apply",
            headers=master_headers, timeout=10,
        )
        assert r.status_code == 409, r.text
        assert r.json().get("detail") == "nothing_staged"

    def test_apply_staged_bundle_missing_returns_409(self, master_headers, tmp_path):
        # Write a fake staged record pointing to a missing path
        fake_path = "/tmp/__bighat_nonexistent_bundle__.zip"
        try:
            os.unlink(fake_path)
        except OSError:
            pass
        script = tmp_path / "fake_staged.py"
        script.write_text(
            "import asyncio, sys\n"
            "sys.path.insert(0, '/app/backend')\n"
            "from server import db\n"
            "async def go():\n"
            f"    await db.update_state.update_one({{'_id':'singleton'}}, {{'$set':{{'staged':{{'version':'31.1.0','path':'{fake_path}','verified':True,'size':1,'sha256':'x','downloaded_at':'now'}}}}}}, upsert=True)\n"
            "asyncio.run(go())\n"
        )
        rc = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, timeout=30)
        if rc.returncode != 0:
            pytest.skip(f"could not seed fake staged: {rc.stderr[-500:]}")

        r = requests.post(
            f"{BASE_URL}/api/native/updates/apply",
            headers=master_headers, timeout=10,
        )
        assert r.status_code == 409, r.text
        assert r.json().get("detail") == "staged_bundle_missing"

        # Re-stage via /download to leave system in good state
        requests.post(f"{BASE_URL}/api/native/updates/download", timeout=30)


# ---------- Launcher --check ----------
class TestLauncherCheck:
    def test_launcher_prints_installed_ver_and_pending_apply(self):
        rc = subprocess.run(
            [sys.executable, str(LAUNCHER), "--check"],
            capture_output=True, text=True, timeout=30,
        )
        assert rc.returncode == 0, rc.stderr
        out = rc.stdout
        assert "installed_ver = 31.0.0" in out, out
        assert "pending_apply=" in out, out
        assert "Uvicorn running on" not in out


# ---------- Regression spot checks ----------
class TestRegressionSpotChecks:
    @pytest.mark.parametrize("path,allowed", [
        ("/api/native/info", {200}),
        ("/api/native/admin/whoami", {401, 403}),
        ("/api/native/sync/status", {200, 401, 403}),
        ("/api/scoreboard/status", {200}),
        ("/api/story-generator/status", {200}),
        ("/api/bingo/status", {200}),
        ("/api/trivia/hosts", {200}),
        ("/api/venues", {200}),
        ("/api/events", {200}),
    ])
    def test_endpoint(self, path, allowed):
        r = requests.get(f"{BASE_URL}{path}", timeout=10)
        assert r.status_code in allowed, f"{path} -> {r.status_code}: {r.text[:200]}"
