"""Static-validation tests for iteration 20: window controls capability +
Job-Object sidecar lifecycle. Linux sandbox — only file/string presence,
JSON/TOML validity, ordering invariants and a live backend smoke."""

import json
import os
import re
from pathlib import Path

import pytest
import requests

try:
    import tomllib  # Python 3.11+
except ImportError:  # pragma: no cover
    import tomli as tomllib  # type: ignore

REPO = Path("/app")
CAP_FILE = REPO / "src-tauri/capabilities/default.json"
CARGO = REPO / "src-tauri/Cargo.toml"
LIB_RS = REPO / "src-tauri/src/lib.rs"
TITLEBAR = REPO / "frontend/src/components/TitleBar.jsx"
PRD = REPO / "memory/PRD.md"

BACKEND_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BACKEND_URL:
    env_path = REPO / "frontend/.env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("REACT_APP_BACKEND_URL="):
                BACKEND_URL = line.split("=", 1)[1].strip().rstrip("/")
                break


# --- Capability JSON --------------------------------------------------------
class TestCapabilities:
    def test_capability_file_valid_json(self):
        data = json.loads(CAP_FILE.read_text())
        assert isinstance(data, dict)
        assert "permissions" in data

    def test_capability_permissions_exact_set(self):
        data = json.loads(CAP_FILE.read_text())
        expected = {
            "core:default",
            "core:window:default",
            "shell:default",
            "process:default",
            "dialog:default",
        }
        assert set(data["permissions"]) == expected, (
            f"unexpected permissions: got {data['permissions']}, want {expected}"
        )

    def test_capability_window_main(self):
        data = json.loads(CAP_FILE.read_text())
        assert "main" in data.get("windows", [])


# --- Cargo.toml -------------------------------------------------------------
class TestCargoToml:
    def test_cargo_toml_valid(self):
        with CARGO.open("rb") as f:
            data = tomllib.load(f)
        assert data["package"]["name"] == "bighat-tauri"

    def test_cargo_windows_target_block_has_windows_sys_with_features(self):
        with CARGO.open("rb") as f:
            data = tomllib.load(f)
        target = data.get("target", {})
        # cfg target key in TOML preserves the original cfg(...) string
        win_key = None
        for k in target.keys():
            if 'cfg(target_os = "windows")' in k:
                win_key = k
                break
        assert win_key is not None, f"missing windows cfg target block; got {list(target.keys())}"
        deps = target[win_key]["dependencies"]
        assert "windows-sys" in deps
        features = deps["windows-sys"].get("features", [])
        for required in (
            "Win32_Foundation",
            "Win32_System_JobObjects",
            "Win32_System_Threading",
        ):
            assert required in features, f"missing feature {required}: got {features}"


# --- lib.rs -----------------------------------------------------------------
class TestLibRs:
    @pytest.fixture(scope="class")
    def src(self):
        return LIB_RS.read_text()

    def test_function_defined_under_windows_cfg(self, src):
        # Verify the cfg attr immediately precedes the fn definition.
        pattern = re.compile(
            r'#\[cfg\(target_os\s*=\s*"windows"\)\]\s*\nfn\s+assign_pid_to_kill_on_close_job\s*\(',
            re.MULTILINE,
        )
        assert pattern.search(src), "assign_pid_to_kill_on_close_job not gated by #[cfg(target_os = \"windows\")]"

    def test_uses_required_win32_apis(self, src):
        for required in (
            "CreateJobObjectW",
            "SetInformationJobObject",
            "JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE",
            "OpenProcess",
            "AssignProcessToJobObject",
        ):
            assert required in src, f"missing Win32 API substring: {required}"

    def test_job_assignment_happens_after_child_is_stashed(self, src):
        stash_marker = "*state.child.lock().unwrap() = Some(child);"
        match_marker = "match assign_pid_to_kill_on_close_job(pid)"
        assert stash_marker in src, "could not find child-stash line"
        assert match_marker in src, "could not find assign_pid_to_kill_on_close_job match"
        assert src.index(match_marker) > src.index(stash_marker), (
            "assign_pid_to_kill_on_close_job(pid) must be called AFTER child is stashed in BackendState"
        )

    def test_exit_requested_handler_still_kills_child(self, src):
        # Both mechanisms must coexist. Find the actual match arm (not a comment).
        m = re.search(
            r"RunEvent::ExitRequested\s*\{[^}]*\}\s*=>\s*\{(.+?)\n\s{12}\}",
            src,
            re.DOTALL,
        )
        assert m, "RunEvent::ExitRequested match arm not found in lib.rs"
        body = m.group(1)
        assert "child.kill()" in body, (
            f"child.kill() not in ExitRequested match arm body: {body[:300]}"
        )

    def test_no_closehandle_on_job_success_path(self, src):
        """CloseHandle(job) must NOT be called on the success path — the kernel
        reference must persist to trigger KILL_ON_JOB_CLOSE on parent exit.
        CloseHandle may appear on error/cleanup paths and for proc_handle."""
        # Extract just the function body
        m = re.search(
            r'fn\s+assign_pid_to_kill_on_close_job[^{]*\{(.+?)\n\}\s*$',
            src,
            re.DOTALL | re.MULTILINE,
        )
        assert m, "could not extract assign_pid_to_kill_on_close_job body"
        body = m.group(1)
        # Find the last 'Ok(())' (success return)
        success_idx = body.rfind("Ok(())")
        assert success_idx != -1, "no Ok(()) success return found"
        # Walk back from Ok(()) and confirm no CloseHandle(job) appears
        # between AssignProcessToJobObject success branch and Ok(()).
        assign_idx = body.rfind("AssignProcessToJobObject")
        success_tail = body[assign_idx:success_idx]
        # In the success path (after AssignProcessToJobObject returned non-zero),
        # there should be no CloseHandle(job) call.
        # Look for explicit "CloseHandle(job)" patterns AFTER the failure branch.
        # Failure branch ends with `return Err(...)`; find its closing.
        # Simpler: ensure the literal "CloseHandle(job)" doesn't appear after
        # the line containing `let _ = job;` comment / before Ok(()) in success.
        # The committed code uses `let _ = job;` as the deliberate leak marker.
        assert "let _ = job;" in body, "intentional job-handle leak marker missing"
        # The success-path slice between `let _ = job;` and `Ok(())` must not
        # call CloseHandle(job).
        leak_idx = body.rfind("let _ = job;")
        success_window = body[leak_idx:success_idx]
        assert "CloseHandle(job)" not in success_window, (
            "CloseHandle(job) found on success path — would defeat KILL_ON_JOB_CLOSE"
        )


# --- TitleBar.jsx unchanged contract ---------------------------------------
class TestTitleBar:
    @pytest.fixture(scope="class")
    def src(self):
        return TITLEBAR.read_text()

    def test_minimize_handler_wired(self, src):
        assert "w.minimize()" in src

    def test_togglemaximize_handler_wired(self, src):
        assert "w.toggleMaximize()" in src

    def test_close_handler_wired(self, src):
        assert "w.close()" in src

    def test_testids_present(self, src):
        for tid in (
            "tauri-titlebar-minimize",
            "tauri-titlebar-maximize",
            "tauri-titlebar-close",
        ):
            assert tid in src


# --- PRD.md docs ------------------------------------------------------------
class TestPrdDocs:
    @pytest.fixture(scope="class")
    def src(self):
        return PRD.read_text()

    def test_window_controls_section_present(self, src):
        assert "WINDOW CONTROLS REQUIRE `core:window:default` CAPABILITY" in src

    def test_sidecar_lifecycle_section_present(self, src):
        assert "SIDECAR LIFECYCLE MUST BE TIED TO THE TAURI SHELL" in src


# --- Backend smoke ----------------------------------------------------------
class TestBackendSmoke:
    def test_api_root_returns_200(self):
        assert BACKEND_URL, "REACT_APP_BACKEND_URL not configured"
        r = requests.get(f"{BACKEND_URL}/api/", timeout=15)
        assert r.status_code == 200, f"GET /api/ -> {r.status_code}: {r.text[:200]}"
