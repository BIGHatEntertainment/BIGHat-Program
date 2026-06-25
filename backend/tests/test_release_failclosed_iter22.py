"""
iter22 — Static validation of the fail-closed release pipeline.

Scope (static-only — no Rust toolchain, no GitHub runners here):
1. /app/src-tauri/src/lib.rs — Windows Job Object HANDLE checks use `== 0`
   (NOT `.is_null()`); CreateJobObjectW uses `ptr::null()` (NOT null_mut()).
2. /app/src-tauri/Cargo.toml — windows-sys = 0.59 + correct features list.
3. /app/.github/workflows/release.yml — job-level timeout-minutes: 75 on
   build-tauri; verify-release-assets gate job present with proper config
   and the three OS-binary regex checks + draft toggling PATCH calls.
4. /app/.github/workflows/ci-tauri-check.yml — exists, valid YAML, matrix,
   cargo check command, rust-cache, timeout-minutes 25.
5. /app/memory/PRD.md — RELEASE PIPELINE MUST BE FAIL-CLOSED section.
6. Backend smoke: GET REACT_APP_BACKEND_URL/api/ -> 200.
"""

import os
import re
from pathlib import Path

import pytest
import requests
import yaml

REPO_ROOT = Path("/app")
LIB_RS = REPO_ROOT / "src-tauri" / "src" / "lib.rs"
CARGO_TOML = REPO_ROOT / "src-tauri" / "Cargo.toml"
RELEASE_YML = REPO_ROOT / ".github" / "workflows" / "release.yml"
CI_CHECK_YML = REPO_ROOT / ".github" / "workflows" / "ci-tauri-check.yml"
PRD_MD = REPO_ROOT / "memory" / "PRD.md"


# PyYAML 1.1 parses bare `on:` as boolean True. Normalize.
def _on(cfg):
    if "on" in cfg:
        return cfg["on"]
    if True in cfg:
        return cfg[True]
    raise KeyError("no on: trigger in workflow")


# --------------------------------------------------------------------------
# 1. lib.rs — Windows Job Object HANDLE checks
# --------------------------------------------------------------------------
class TestLibRsJobObject:
    @pytest.fixture(scope="class")
    def src(self):
        return LIB_RS.read_text()

    def test_assign_pid_function_exists(self, src):
        assert "fn assign_pid_to_kill_on_close_job(pid: u32)" in src

    def test_handle_checks_use_eq_zero_not_is_null(self, src):
        # Extract just the Windows job object function body
        match = re.search(
            r"fn assign_pid_to_kill_on_close_job.*?\n\}\n",
            src,
            re.DOTALL,
        )
        assert match, "assign_pid_to_kill_on_close_job function not found"
        body = match.group(0)
        # The three HANDLE checks (job, proc_handle, ok variants) must all
        # compare to 0, never call .is_null()
        assert "if job == 0" in body
        assert "if proc_handle == 0" in body
        # Bug guard: HANDLE is `isize` in windows-sys; .is_null() doesn't compile
        assert ".is_null()" not in body, (
            "HANDLE is isize in windows-sys — .is_null() is the alpha.12 bug"
        )

    def test_create_job_object_uses_ptr_null_not_null_mut(self, src):
        # *const PCWSTR + *const SECURITY_ATTRIBUTES signatures in 0.59
        # require ptr::null(), not ptr::null_mut()
        # Nested parens: match the full statement on its line.
        m = re.search(r"CreateJobObjectW\([^;]*\);", src)
        assert m, "CreateJobObjectW call not found"
        call = m.group(0)
        assert call.count("ptr::null()") == 2, (
            f"Expected both args to be ptr::null(); got: {call}"
        )
        assert "null_mut" not in call


# --------------------------------------------------------------------------
# 2. Cargo.toml — windows-sys 0.59 + feature list
# --------------------------------------------------------------------------
class TestCargoToml:
    @pytest.fixture(scope="class")
    def text(self):
        return CARGO_TOML.read_text()

    def test_windows_target_section_present(self, text):
        assert '[target.\'cfg(target_os = "windows")\'.dependencies]' in text

    def test_windows_sys_version_059(self, text):
        m = re.search(r'windows-sys\s*=\s*\{\s*version\s*=\s*"([^"]+)"', text)
        assert m, "windows-sys dependency not found"
        assert m.group(1) == "0.59", f"Expected 0.59, got {m.group(1)}"

    def test_windows_sys_features_exact(self, text):
        # Extract the features = [ ... ] block on the windows-sys line block
        m = re.search(
            r'windows-sys\s*=\s*\{[^}]*features\s*=\s*\[([^\]]+)\]',
            text,
            re.DOTALL,
        )
        assert m, "windows-sys features block not found"
        feats = {f.strip().strip('"') for f in m.group(1).split(",") if f.strip()}
        expected = {
            "Win32_Foundation",
            "Win32_System_JobObjects",
            "Win32_System_Threading",
        }
        assert feats == expected, f"Expected {expected}, got {feats}"


# --------------------------------------------------------------------------
# 3. release.yml — build-tauri timeout + verify-release-assets gate
# --------------------------------------------------------------------------
class TestReleaseYml:
    @pytest.fixture(scope="class")
    def cfg(self):
        return yaml.safe_load(RELEASE_YML.read_text())

    @pytest.fixture(scope="class")
    def raw(self):
        return RELEASE_YML.read_text()

    def test_build_tauri_has_job_level_timeout_75(self, cfg):
        build = cfg["jobs"]["build-tauri"]
        # job-level (sibling of `strategy`), NOT inside matrix
        assert build.get("timeout-minutes") == 75
        # Make sure it's not buried in matrix.include[]
        for entry in build["strategy"]["matrix"]["include"]:
            assert "timeout-minutes" not in entry

    def test_verify_release_assets_job_exists(self, cfg):
        assert "verify-release-assets" in cfg["jobs"]

    def test_verify_release_assets_metadata(self, cfg):
        j = cfg["jobs"]["verify-release-assets"]
        assert j["needs"] == "build-tauri"
        # `if: always()` → YAML parses to the string "always()"
        assert j["if"] == "always()"
        assert j["runs-on"] == "ubuntu-latest"
        assert j["timeout-minutes"] == 5
        assert j["permissions"]["contents"] == "write"

    def test_verify_release_assets_has_three_regex_checks(self, raw):
        # Strings live inside a shell heredoc; assert as raw text.
        # 1) Windows .exe (Setup or just .exe)
        assert "BIG.*Hat.*Entertainment.*Setup.*\\.exe$" in raw
        assert "BIG.*Hat.*Entertainment.*\\.exe$" in raw
        # 2) macOS Apple Silicon
        assert "aarch64" in raw and "arm64" in raw
        assert re.search(r"aarch64.*\\\.dmg\$\|arm64.*\\\.dmg\$", raw) or (
            "aarch64.*\\.dmg$" in raw and "arm64.*\\.dmg$" in raw
        )
        # 3) macOS Intel
        assert "x64" in raw and ("x86_64" in raw or "intel" in raw)
        assert re.search(r"x64.*\\\.dmg\$", raw) or "x64.*\\.dmg$" in raw

    def test_verify_release_assets_patches_draft_on_failure(self, raw):
        # Failure path PATCHes draft=true
        assert '"draft":true' in raw or '"draft": true' in raw

    def test_verify_release_assets_patches_public_on_success(self, raw):
        # Success path PATCHes draft=false, prerelease=false, make_latest=true
        # Implementation packs them as one JSON body
        assert '"draft":false' in raw
        assert '"prerelease":false' in raw
        assert '"make_latest":"true"' in raw or '"make_latest": "true"' in raw


# --------------------------------------------------------------------------
# 4. ci-tauri-check.yml — pre-tag cargo check gate
# --------------------------------------------------------------------------
class TestCiTauriCheckYml:
    @pytest.fixture(scope="class")
    def cfg(self):
        return yaml.safe_load(CI_CHECK_YML.read_text())

    @pytest.fixture(scope="class")
    def raw(self):
        return CI_CHECK_YML.read_text()

    def test_file_exists_and_parses(self, cfg):
        assert cfg is not None
        assert "jobs" in cfg

    def test_triggers_push_main_master_with_src_tauri_paths(self, cfg):
        trig = _on(cfg)
        push = trig["push"]
        assert "main" in push["branches"]
        assert "master" in push["branches"]
        assert any("src-tauri" in p for p in push["paths"])

    def test_triggers_pull_request_with_src_tauri_paths(self, cfg):
        trig = _on(cfg)
        pr = trig["pull_request"]
        assert any("src-tauri" in p for p in pr["paths"])

    def test_cargo_check_job_three_target_matrix(self, cfg):
        job = cfg["jobs"]["cargo-check"]
        include = job["strategy"]["matrix"]["include"]
        triples = {e["target"]: e["os"] for e in include}
        assert triples["x86_64-pc-windows-msvc"] == "windows-latest"
        assert triples["aarch64-apple-darwin"] == "macos-14"
        assert triples["x86_64-apple-darwin"] == "macos-13"

    def test_cargo_check_timeout_and_cache(self, cfg, raw):
        job = cfg["jobs"]["cargo-check"]
        assert job["timeout-minutes"] == 25
        assert "Swatinem/rust-cache@v2" in raw

    def test_cargo_check_command(self, raw):
        # cargo check --target <triple> --locked --all-targets, from src-tauri/
        assert "cargo check --target ${{ matrix.target }} --locked --all-targets" in raw
        assert "working-directory: src-tauri" in raw


# --------------------------------------------------------------------------
# 5. PRD.md — fail-closed section
# --------------------------------------------------------------------------
class TestPrdFailClosedSection:
    @pytest.fixture(scope="class")
    def text(self):
        return PRD_MD.read_text()

    def test_section_header_present(self, text):
        assert "RELEASE PIPELINE MUST BE FAIL-CLOSED" in text
        assert "NEVER SHIP A HALF-BAKED RELEASE" in text

    def test_documents_three_layers(self, text):
        # Layer 1 — pre-tag cargo check
        assert "ci-tauri-check.yml" in text
        assert "cargo check" in text
        # Layer 2 — per-leg timeout
        assert "timeout-minutes: 75" in text
        # Layer 3 — post-build verification gate
        assert "verify-release-assets" in text

    def test_documents_customer_fallback(self, text):
        # Resolver walks back to previous release for missing platform asset
        assert "downloads_resolver" in text or "downloads resolver" in text


# --------------------------------------------------------------------------
# 6. Backend smoke
# --------------------------------------------------------------------------
class TestBackendSmoke:
    def test_api_root_200(self):
        base = os.environ.get(
            "REACT_APP_BACKEND_URL",
            "https://standalone-tools.preview.emergentagent.com",
        ).rstrip("/")
        r = requests.get(f"{base}/api/", timeout=15)
        assert r.status_code == 200, f"Got {r.status_code}: {r.text[:200]}"
