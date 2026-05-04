"""Phase 9 — packaging / launcher / SPA static bundle / build orchestrator tests."""
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
import requests

REPO_ROOT = Path("/app")
BACKEND_DIR = REPO_ROOT / "backend"
STATIC_DIR = BACKEND_DIR / "static"
PACKAGING_DIR = REPO_ROOT / "packaging"
SCRIPTS_DIR = REPO_ROOT / "scripts"
LAUNCHER = BACKEND_DIR / "launcher.py"
BUILD_ORCH = SCRIPTS_DIR / "build_standalone.py"

SUPERVISOR_BACKEND = "http://127.0.0.1:8001"  # supervisor-managed
INSTALL_ROOT_LITERAL = r"C:\BIG Hat\BIGHatStandalone"


# ---------- Launcher --check ----------
class TestLauncherCheck:
    def test_check_exits_zero_and_prints_expected_lines(self):
        result = subprocess.run(
            [sys.executable, str(LAUNCHER), "--check"],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0, f"stderr={result.stderr}\nstdout={result.stdout}"
        out = result.stdout
        for token in [
            "backend_dir",
            "listen",
            "native_mode",
            "setup_complete",
            "instance_id",
            "paths",
            "static_bundle",
        ]:
            assert token in out, f"missing token {token!r} in --check output:\n{out}"
        # Must not have started uvicorn (no Uvicorn running banner)
        assert "Uvicorn running on" not in out
        assert "Uvicorn running on" not in result.stderr

    def test_check_custom_port_appears_in_output(self):
        result = subprocess.run(
            [sys.executable, str(LAUNCHER), "--check", "--port", "19999"],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0
        assert "127.0.0.1:19999" in result.stdout


# ---------- Launcher --no-browser boot on alt port ----------
def _wait_for(url: str, timeout: float = 8.0) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        try:
            r = requests.get(url, timeout=1.5)
            if r.status_code < 500:
                return True
        except Exception:
            pass
        time.sleep(0.3)
    return False


class TestLauncherBoot:
    PORT = 18102

    def test_launcher_serves_health_native_info_then_dies(self):
        env = os.environ.copy()
        proc = subprocess.Popen(
            [sys.executable, str(LAUNCHER), "--no-browser",
             "--port", str(self.PORT)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
            cwd=str(BACKEND_DIR),
        )
        try:
            base = f"http://127.0.0.1:{self.PORT}"
            assert _wait_for(f"{base}/health", timeout=15.0), (
                f"launcher never responded on {base}/health; "
                f"stderr={proc.stderr.peek(2000) if proc.stderr else ''}"
            )

            r = requests.get(f"{base}/health", timeout=3)
            assert r.status_code == 200
            assert r.json().get("status") == "healthy"

            r = requests.get(f"{base}/api/native/info", timeout=3)
            assert r.status_code == 200, r.text
            j = r.json()
            assert j.get("native_mode") is True, j
            assert "version" in j, j
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)

    def test_launcher_with_port_already_in_use_fails_fast(self):
        """Bind a socket on a port, then ask the launcher to use it; uvicorn
        must exit non-zero rather than silently fall through."""
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.listen(1)
        try:
            proc = subprocess.Popen(
                [sys.executable, str(LAUNCHER), "--no-browser", "--port", str(port)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                cwd=str(BACKEND_DIR),
            )
            try:
                rc = proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
                pytest.fail("launcher did not exit when port was busy")
            assert rc != 0, "launcher should fail when port is in use"
        finally:
            s.close()


# ---------- SPA static bundle served via supervisor backend ----------
class TestSpaStaticBundle:
    def test_root_returns_index_html_with_title(self):
        r = requests.get(f"{SUPERVISOR_BACKEND}/", timeout=5)
        assert r.status_code == 200, r.text[:200]
        assert "<title>BIG Hat | Host</title>" in r.text

    def test_spa_deep_link_returns_index_html(self):
        r = requests.get(f"{SUPERVISOR_BACKEND}/some/spa/deep-link", timeout=5)
        assert r.status_code == 200
        assert "<title>BIG Hat | Host</title>" in r.text

    def test_api_route_not_shadowed_by_spa(self):
        r = requests.get(f"{SUPERVISOR_BACKEND}/api/native/info", timeout=5)
        assert r.status_code == 200
        ct = r.headers.get("content-type", "")
        assert "json" in ct, f"content-type={ct} body[:200]={r.text[:200]}"
        assert r.json().get("native_mode") is True

    def test_health_still_json(self):
        r = requests.get(f"{SUPERVISOR_BACKEND}/health", timeout=5)
        assert r.status_code == 200
        assert r.json() == {"status": "healthy"}

    def test_unknown_api_route_returns_404_not_index(self):
        r = requests.get(f"{SUPERVISOR_BACKEND}/api/__definitely_not_an_endpoint__", timeout=5)
        assert r.status_code == 404
        # Must be JSON 404 (not the SPA fallback)
        ct = r.headers.get("content-type", "")
        assert "html" not in ct.lower(), f"unknown api route fell through to SPA! ct={ct}"


# ---------- SPA static asset files ----------
class TestStaticAssets:
    def test_css_asset_served_200(self):
        css_dir = STATIC_DIR / "static" / "css"
        files = [f for f in css_dir.iterdir() if f.suffix == ".css"]
        assert files, f"no .css files in {css_dir}"
        name = files[0].name
        r = requests.get(f"{SUPERVISOR_BACKEND}/static/css/{name}", timeout=5)
        assert r.status_code == 200, r.text[:200]
        ct = r.headers.get("content-type", "")
        assert "css" in ct or "text" in ct, f"unexpected content-type {ct}"

    def test_js_asset_served_200(self):
        js_dir = STATIC_DIR / "static" / "js"
        files = [f for f in js_dir.iterdir() if f.suffix == ".js" and "LICENSE" not in f.name]
        assert files, f"no .js files in {js_dir}"
        name = files[0].name
        r = requests.get(f"{SUPERVISOR_BACKEND}/static/js/{name}", timeout=5)
        assert r.status_code == 200
        ct = r.headers.get("content-type", "")
        assert "javascript" in ct or "text" in ct or "application" in ct


# ---------- build_manifest.json ----------
class TestBuildManifest:
    def test_manifest_present_and_well_formed(self):
        f = STATIC_DIR / "build_manifest.json"
        assert f.exists(), f"{f} missing"
        m = json.loads(f.read_text())
        for k in ("built_at", "git_sha", "frontend_included",
                  "file_count", "python_version", "platform"):
            assert k in m, f"missing key {k} in manifest: {m}"
        assert m["frontend_included"] is True
        assert isinstance(m["file_count"], int)
        assert m["file_count"] >= 10, m


# ---------- Build orchestrator semantics ----------
class TestBuildOrchestrator:
    def test_help_lists_three_flags(self):
        r = subprocess.run(
            [sys.executable, str(BUILD_ORCH), "--help"],
            capture_output=True, text=True, timeout=15,
        )
        assert r.returncode == 0, r.stderr
        for flag in ("--skip-install", "--clean", "--no-frontend"):
            assert flag in r.stdout, f"missing flag {flag} in --help output:\n{r.stdout}"

    def test_no_frontend_preserves_index_html(self):
        index = STATIC_DIR / "index.html"
        manifest_path = STATIC_DIR / "build_manifest.json"
        assert index.exists(), "precondition: index.html must already exist"
        before = index.read_bytes()
        manifest_before = manifest_path.read_text()

        try:
            r = subprocess.run(
                [sys.executable, str(BUILD_ORCH), "--no-frontend"],
                capture_output=True, text=True, timeout=60,
            )
            assert r.returncode == 0, f"stderr={r.stderr}\nstdout={r.stdout}"
            assert index.exists(), "index.html was deleted by --no-frontend!"
            assert index.read_bytes() == before, "index.html was overwritten by --no-frontend"
            # Manifest must still be valid JSON afterwards
            new_manifest = json.loads(manifest_path.read_text())
            assert new_manifest.get("frontend_included") in (True, False)
            # `--no-frontend` must NOT lie about a present bundle. When
            # backend/static/index.html exists at run time the orchestrator
            # preserves the prior `frontend_included=True` flag (see
            # CHANGELOG Phase 9 reviewer follow-up). The launcher's static-
            # bundle-present check would otherwise flip false on every
            # incremental backend-only build.
            assert new_manifest.get("frontend_included") is True, new_manifest
            assert new_manifest.get("file_count", 0) >= 10, new_manifest
        finally:
            # Restore the as-shipped manifest so other tests (and follow-up
            # runs) see the bundled state, not a --no-frontend artifact.
            manifest_path.write_text(manifest_before)


# ---------- Phase 8 carry-over: scoreboard /advance match_not_found ----------
def _login_master() -> str:
    r = requests.post(
        f"{SUPERVISOR_BACKEND}/api/auth/login",
        json={"email": "master@bighat.local", "password": "BigHat2024!"},
        timeout=5,
    )
    assert r.status_code == 200, r.text
    j = r.json()
    return j.get("access_token") or j.get("token")


@pytest.fixture(scope="module")
def master_headers():
    tok = _login_master()
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def tournament_id(master_headers):
    """Create a 4-team tournament; yield its id; delete on teardown."""
    payload = {
        "name": "TEST_phase9_tournament",
        "description": "phase9 advance match_not_found test",
        "tournament_type": "single_elimination",
        "total_teams": 4,
        "bye_count": 0,
        "teams": [
            {"name": "TEST_T1"},
            {"name": "TEST_T2"},
            {"name": "TEST_T3"},
            {"name": "TEST_T4"},
        ],
    }
    r = requests.post(
        f"{SUPERVISOR_BACKEND}/api/scoreboard/tournaments",
        json=payload, headers=master_headers, timeout=10,
    )
    assert r.status_code in (200, 201), r.text
    tid = r.json().get("id") or r.json().get("tournament_id")
    assert tid, r.json()
    yield tid
    try:
        requests.delete(
            f"{SUPERVISOR_BACKEND}/api/scoreboard/tournaments/{tid}",
            headers=master_headers, timeout=5,
        )
    except Exception:
        pass


class TestAdvanceMatchNotFound:
    def test_unknown_match_id_returns_404_with_prefix(self, master_headers, tournament_id):
        r = requests.post(
            f"{SUPERVISOR_BACKEND}/api/scoreboard/tournaments/{tournament_id}/advance",
            json={"match_id": "definitely_unknown", "winner_seed": 1},
            headers=master_headers, timeout=5,
        )
        assert r.status_code == 404, r.text
        detail = r.json().get("detail", "")
        assert isinstance(detail, str) and detail.startswith("match_not_found:"), detail

    def test_real_match_id_advances_200(self, master_headers, tournament_id):
        # Tournament create does NOT auto-generate matches; seed bracket_state
        # via PUT so we have a known match_id to advance.
        seeded_match_id = "qf_1"
        seed_bracket = {
            "matches": {
                seeded_match_id: {
                    "round": 1,
                    "team_a": {"seed": 1, "name": "TEST_T1"},
                    "team_b": {"seed": 2, "name": "TEST_T2"},
                    "completed": False,
                }
            }
        }
        rput = requests.put(
            f"{SUPERVISOR_BACKEND}/api/scoreboard/tournaments/{tournament_id}",
            json={"bracket_state": seed_bracket},
            headers=master_headers, timeout=5,
        )
        assert rput.status_code == 200, rput.text

        pick = seeded_match_id
        r = requests.post(
            f"{SUPERVISOR_BACKEND}/api/scoreboard/tournaments/{tournament_id}/advance",
            json={"match_id": pick, "winner_seed": 1},
            headers=master_headers, timeout=5,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        bs = body.get("bracket_state") or {}
        m = (bs.get("matches") or {}).get(pick) or {}
        assert m.get("completed") is True, m
        assert m.get("winner_seed") == 1, m


# ---------- Phase 8 carry-over: admin_router setter + resolver ----------
class TestAdminRouterResolver:
    def test_module_attrs(self):
        sys.path.insert(0, str(BACKEND_DIR))
        import importlib
        ar = importlib.import_module("native.admin_router")
        # Public setter
        assert callable(getattr(ar, "set_current_user_resolver", None)), \
            "set_current_user_resolver missing or not callable"
        # Default resolver coroutine
        default_resolver = getattr(ar, "_default_resolver", None)
        assert default_resolver is not None
        import inspect
        assert inspect.iscoroutinefunction(default_resolver), \
            "_default_resolver must be async"
        # Initial state
        assert getattr(ar, "_user_resolver") is None, \
            "_user_resolver should start as None"

    def test_setter_round_trip(self):
        sys.path.insert(0, str(BACKEND_DIR))
        import importlib
        ar = importlib.import_module("native.admin_router")

        async def stub(token):  # pragma: no cover - just identity check
            return {"email": "stub"}

        original = ar._user_resolver
        try:
            ar.set_current_user_resolver(stub)
            assert ar._user_resolver is stub
        finally:
            ar.set_current_user_resolver(original)
            assert ar._user_resolver is original


# ---------- Packaging artifacts ----------
class TestPackagingArtifacts:
    def test_files_exist_and_non_empty(self):
        for name in ("start_bighat.vbs", "install_shortcut.vbs", "README.md"):
            p = PACKAGING_DIR / name
            assert p.exists(), f"{p} missing"
            assert p.stat().st_size > 0, f"{p} is empty"

    def test_vbs_headers_and_install_root_literal(self):
        for name in ("start_bighat.vbs", "install_shortcut.vbs"):
            text = (PACKAGING_DIR / name).read_text(errors="ignore")
            first = text.lstrip().splitlines()[0]
            assert first.startswith("'") or first.lower().startswith("option explicit"), \
                f"{name} first line is not comment / Option Explicit: {first!r}"
            assert INSTALL_ROOT_LITERAL in text, \
                f"{name} missing INSTALL_ROOT literal"


# ---------- Public regression endpoints ----------
class TestPublicRegression:
    @pytest.mark.parametrize("path,allowed", [
        ("/api/native/info", {200}),
        ("/api/native/sync/status", {200, 401, 403}),
        ("/api/native/admin/whoami", {401, 403}),
        ("/api/story-generator/status", {200}),
        ("/api/scoreboard/status", {200}),
        ("/api/trivia/hosts", {200}),
        ("/api/venues", {200}),
        ("/api/events", {200}),
        ("/api/roundmaker/sharepoint-status", {200, 401, 403}),
    ])
    def test_endpoint_status(self, path, allowed):
        r = requests.get(f"{SUPERVISOR_BACKEND}{path}", timeout=10)
        assert r.status_code in allowed, \
            f"{path} -> {r.status_code} body={r.text[:200]}"
