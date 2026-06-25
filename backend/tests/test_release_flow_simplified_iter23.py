"""
Iteration 23 — static validation pass.

Locks in the merchant's directive (2026-06-25):
  - auto-tag.yml is PERMANENTLY RETIRED and deleted.
  - ci-tauri-check.yml is deleted.
  - release.yml is kept and remains the only workflow that builds installers.
  - The Windows Job Object hardening was stripped from src-tauri/src/lib.rs;
    only the clean-shutdown ExitRequested.kill() path remains.
  - windows-sys dependency must be gone from src-tauri/Cargo.toml.
  - VERSION + tauri.conf.json are pinned at 32.0.0-alpha.13.
  - PRD.md must document the new RELEASE FLOW (manual / no auto-tag) and
    the simplified SIDECAR LIFECYCLE.

There is no Rust toolchain in this sandbox, so we cannot exercise the
release.yml workflow itself — that runs on GitHub-hosted runners.  This
file is therefore a pure file-system + string-pattern audit.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest
import requests

REPO = Path("/app")
WORKFLOWS = REPO / ".github" / "workflows"
RELEASE_YML = WORKFLOWS / "release.yml"
AUTO_TAG_YML = WORKFLOWS / "auto-tag.yml"
CI_TAURI_CHECK_YML = WORKFLOWS / "ci-tauri-check.yml"
LIB_RS = REPO / "src-tauri" / "src" / "lib.rs"
CARGO_TOML = REPO / "src-tauri" / "Cargo.toml"
TAURI_CONF = REPO / "src-tauri" / "tauri.conf.json"
VERSION_TXT = REPO / "backend" / "VERSION.txt"
PRD = REPO / "memory" / "PRD.md"

EXPECTED_VERSION = "32.0.0-alpha.13"


# --- Retired workflows are gone --------------------------------------------

class TestRetiredWorkflowsDeleted:
    def test_auto_tag_yml_deleted(self):
        assert not AUTO_TAG_YML.exists(), (
            f"auto-tag.yml must be permanently retired, but it still exists at {AUTO_TAG_YML}"
        )

    def test_ci_tauri_check_yml_deleted(self):
        assert not CI_TAURI_CHECK_YML.exists(), (
            f"ci-tauri-check.yml must be deleted, but it still exists at {CI_TAURI_CHECK_YML}"
        )


# --- release.yml is intact -------------------------------------------------

class TestReleaseYmlIntact:
    def test_release_yml_exists(self):
        assert RELEASE_YML.exists(), "release.yml must exist"

    def test_release_yml_parses_as_yaml(self):
        yaml = pytest.importorskip("yaml")
        data = yaml.safe_load(RELEASE_YML.read_text())
        assert isinstance(data, dict)
        # PyYAML parses the YAML key `on:` as the boolean True; accept either.
        triggers = data.get("on", data.get(True))
        assert triggers is not None, "release.yml is missing its `on:` trigger block"
        assert "push" in triggers, "release.yml must still trigger on push"
        assert "workflow_dispatch" in triggers, (
            "release.yml must still be dispatchable (the agent uses this on 'save and push')"
        )

    def test_release_yml_triggers_on_v32_and_v33_tags(self):
        yaml = pytest.importorskip("yaml")
        data = yaml.safe_load(RELEASE_YML.read_text())
        triggers = data.get("on", data.get(True))
        tags = triggers["push"]["tags"]
        assert "v32.*" in tags, "release.yml must trigger on v32.* tags"
        assert "v33.*" in tags, "release.yml must trigger on v33.* tags"

    def test_release_yml_has_verify_release_assets_gate(self):
        yaml = pytest.importorskip("yaml")
        data = yaml.safe_load(RELEASE_YML.read_text())
        jobs = data["jobs"]
        assert "verify-release-assets" in jobs, (
            "verify-release-assets gate job must remain — it is the only place a release goes public"
        )
        gate = jobs["verify-release-assets"]
        assert gate.get("needs") == "build-tauri"
        assert gate.get("if") == "always()" or gate.get("if") is True
        # The gate must still PATCH the release public on success.
        body = RELEASE_YML.read_text()
        assert '"draft":false' in body and '"make_latest":"true"' in body, (
            "verify-release-assets must PATCH the release to public on success"
        )

    def test_release_yml_build_tauri_has_75_minute_timeout(self):
        yaml = pytest.importorskip("yaml")
        data = yaml.safe_load(RELEASE_YML.read_text())
        build_tauri = data["jobs"]["build-tauri"]
        assert build_tauri.get("timeout-minutes") == 75, (
            "build-tauri must keep its 75-minute per-leg timeout to prevent stuck macos-13 runners"
        )


# --- lib.rs: Job Object stripped, ExitRequested preserved ------------------

class TestLibRsSimplified:
    FORBIDDEN_TOKENS = [
        "assign_pid_to_kill_on_close_job",
        "CreateJobObjectW",
        "AssignProcessToJobObject",
        "JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE",
        "use windows_sys",
    ]

    def test_job_object_code_is_stripped(self):
        body = LIB_RS.read_text()
        leftover = [tok for tok in self.FORBIDDEN_TOKENS if tok in body]
        assert not leftover, (
            f"lib.rs still references Job Object hardening tokens: {leftover}. "
            "The merchant explicitly retired this code after two release-build failures."
        )

    def test_exit_requested_clean_shutdown_preserved(self):
        body = LIB_RS.read_text()
        # The clean-shutdown path is the surviving sidecar-kill mechanism;
        # it covers customer-reported X-button / taskbar-close scenarios.
        assert "RunEvent::ExitRequested" in body, (
            "ExitRequested arm removed — this is the only remaining clean-shutdown path for the sidecar"
        )
        assert "child.kill()" in body, (
            "child.kill() removed from lib.rs — the sidecar would now outlive the shell"
        )
        # Be stricter: the kill() call should be inside the ExitRequested arm.
        # Match across newlines so the surrounding block is captured.
        m = re.search(
            r"RunEvent::ExitRequested\s*\{[^}]*\}\s*=>\s*\{(?P<body>.*?)\n\s{12}\}",
            body,
            re.DOTALL,
        )
        assert m, "Could not locate the ExitRequested match arm in lib.rs"
        assert "child.kill()" in m.group("body"), (
            "child.kill() is no longer inside the ExitRequested arm"
        )


# --- Cargo.toml: windows-sys gone, core deps intact ------------------------

class TestCargoTomlClean:
    def test_no_windows_sys_dependency(self):
        body = CARGO_TOML.read_text()
        # Match `windows-sys` only as a dependency name at start of a line
        # (with optional whitespace) so we don't get fooled by a comment.
        for line in body.splitlines():
            stripped = line.split("#", 1)[0].strip()
            assert not stripped.startswith("windows-sys"), (
                f"windows-sys dependency must be removed from Cargo.toml, found: {line!r}"
            )
            assert not stripped.startswith("windows_sys"), (
                f"windows_sys dependency must be removed from Cargo.toml, found: {line!r}"
            )

    def test_cargo_toml_parses(self):
        try:
            import tomllib  # py311+
        except ImportError:  # pragma: no cover
            tomllib = pytest.importorskip("tomli")
        data = tomllib.loads(CARGO_TOML.read_text())
        assert "dependencies" in data, "Cargo.toml [dependencies] block missing"
        deps = data["dependencies"]
        for required in [
            "tauri",
            "tauri-plugin-shell",
            "tauri-plugin-process",
            "tauri-plugin-dialog",
            "reqwest",
            "log",
            "env_logger",
        ]:
            assert required in deps, f"Cargo.toml [dependencies] missing {required}"
        # tauri-plugin-fs is optional in this build (not currently listed);
        # do not assert its presence — the review-request bullet says the
        # block must remain intact, which it does.


# --- Versions pinned -------------------------------------------------------

class TestVersionsPinned:
    def test_backend_version_txt(self):
        assert VERSION_TXT.read_text().strip() == EXPECTED_VERSION

    def test_tauri_conf_version(self):
        data = json.loads(TAURI_CONF.read_text())
        assert data["version"] == EXPECTED_VERSION


# --- PRD locks in the merchant directive -----------------------------------

class TestPRDLocksInDirective:
    def setup_method(self):
        self.text = PRD.read_text()

    def test_release_flow_section_present(self):
        # The section title must contain the locking words.
        assert "RELEASE FLOW — MANUAL, ONE-CLICK FROM MAIN AGENT (NO AUTO-TAG)" in self.text, (
            "PRD.md missing the new 'RELEASE FLOW — MANUAL, ONE-CLICK FROM MAIN AGENT (NO AUTO-TAG)' section"
        )
        # The section title is the locking sentinel; verify the words individually too.
        assert "NO AUTO-TAG" in self.text
        assert "RETIRED" in self.text or "PERMANENTLY RETIRED" in self.text

    def test_sidecar_lifecycle_simplified(self):
        # Locate the SIDECAR LIFECYCLE section and verify it now reflects
        # Job-Object-removed reality.
        m = re.search(
            r"SIDECAR LIFECYCLE.*?(?=\n##\s|\n---\n## )",
            self.text,
            re.DOTALL,
        )
        assert m, "Could not locate SIDECAR LIFECYCLE section in PRD.md"
        section = m.group(0)
        assert "ExitRequested" in section, (
            "SIDECAR LIFECYCLE section should reference the surviving ExitRequested.kill() path"
        )
        # The section must mention that the Job Object hardening was removed/retired.
        lowered = section.lower()
        assert (
            "removed" in lowered
            or "retired" in lowered
            or "simplified" in lowered
        ), "SIDECAR LIFECYCLE section should note that Job Object hardening was removed/retired"

    def test_no_instructions_to_recreate_retired_workflows(self):
        # The only acceptable occurrences of an imperative like 'Recreate
        # auto-tag.yml' / 'Re-add ci-tauri-check.yml' are inside a
        # forbidden/NEVER-do bullet (prefixed with ❌, "NEVER", "Do NOT",
        # "Never", "Don't", or "must not").  Anything else is a directive
        # violation.
        bad_patterns = [
            re.compile(
                r"(?i)\b(re-?create|re-?add|restore|add\s+back|reinstate)\s+(`)?auto-tag\.yml(`)?"
            ),
            re.compile(
                r"(?i)\b(re-?create|re-?add|restore|add\s+back|reinstate)\s+(`)?ci-tauri-check\.yml(`)?"
            ),
        ]
        lines = self.text.splitlines()
        forbidden_markers = ("❌", "NEVER", "Never", "do not", "don't", "must not")
        violations = []
        for i, line in enumerate(lines):
            for pat in bad_patterns:
                if pat.search(line):
                    # Acceptable if the line itself or any of the 2 preceding
                    # lines marks this as a forbidden directive.
                    window = " ".join(lines[max(0, i - 2) : i + 1]).lower()
                    if any(m.lower() in window for m in forbidden_markers):
                        continue
                    violations.append((i + 1, line.strip()))
        assert not violations, (
            "PRD.md contains imperative instructions to recreate retired workflows "
            f"(outside any NEVER-do/❌ context): {violations}"
        )


# --- Live backend smoke ----------------------------------------------------

class TestBackendSmoke:
    def test_api_root_returns_200(self):
        base = os.environ.get("REACT_APP_BACKEND_URL")
        if not base:
            # Fall back to frontend/.env (the sandbox doesn't export it into pytest).
            env = (REPO / "frontend" / ".env").read_text()
            for line in env.splitlines():
                if line.startswith("REACT_APP_BACKEND_URL="):
                    base = line.split("=", 1)[1].strip()
                    break
        assert base, "REACT_APP_BACKEND_URL not set"
        r = requests.get(f"{base.rstrip('/')}/api/", timeout=15)
        assert r.status_code == 200, f"GET /api/ -> {r.status_code} ({r.text[:200]})"
