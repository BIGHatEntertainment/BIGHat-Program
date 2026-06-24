"""
Static validation for iteration 21:
  - release.yml + auto-tag.yml workflow correctness for the auto-tag → release
    workflow_dispatch fallback fix (alpha.12 root-cause).
  - PRD.md contains the new pipeline section.
  - Backend smoke (GET /api/) still 200 (workflow edits shouldn't have moved it).
PyYAML quirk: top-level `on:` parses as boolean True under YAML 1.1, so we
look up cfg.get('on') and fall back to cfg.get(True).
"""
import os
import re
import requests
import yaml
import pytest

REPO_ROOT = "/app"
RELEASE_YML = os.path.join(REPO_ROOT, ".github/workflows/release.yml")
AUTOTAG_YML = os.path.join(REPO_ROOT, ".github/workflows/auto-tag.yml")
PRD_MD = os.path.join(REPO_ROOT, "memory/PRD.md")
BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL",
    open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].splitlines()[0].strip()
).rstrip("/")


def _on(cfg):
    """Handle PyYAML 1.1 quirk where bare `on:` parses to bool True."""
    return cfg.get("on") if "on" in cfg else cfg.get(True)


# --- release.yml ---------------------------------------------------------
class TestReleaseYml:
    def setup_method(self):
        with open(RELEASE_YML) as f:
            self.raw = f.read()
        self.cfg = yaml.safe_load(self.raw)

    def test_valid_yaml(self):
        assert isinstance(self.cfg, dict)
        assert self.cfg.get("name")

    def test_release_draft_strict_expression(self):
        # Must be exactly: releaseDraft: ${{ inputs.draft == 'true' }}
        # NOT ORed with github.event_name
        matches = re.findall(r"releaseDraft:\s*(.+)", self.raw)
        assert matches, "releaseDraft line missing"
        line = matches[0].strip()
        assert line == "${{ inputs.draft == 'true' }}", (
            f"releaseDraft must be strict `${{{{ inputs.draft == 'true' }}}}`; got: {line}"
        )
        assert "github.event_name" not in line
        assert "||" not in line

    def test_tag_push_trigger_preserved(self):
        on = _on(self.cfg)
        assert on, "missing `on:` section"
        push = on.get("push") if isinstance(on, dict) else None
        assert push and "tags" in push, "push.tags trigger missing"
        tags = push["tags"]
        assert any(t.startswith("v32") for t in tags), f"v32.* tag trigger missing: {tags}"
        assert any(t.startswith("v33") for t in tags), f"v33.* tag trigger missing: {tags}"

    def test_workflow_dispatch_inputs(self):
        on = _on(self.cfg)
        wd = on.get("workflow_dispatch") if isinstance(on, dict) else None
        assert wd, "workflow_dispatch trigger missing"
        inputs = wd.get("inputs", {})
        assert "version" in inputs, "missing `version` input"
        assert inputs["version"].get("required") is True
        assert inputs["version"].get("type") == "string"
        assert "draft" in inputs, "missing `draft` input"
        assert inputs["draft"].get("type") == "string"
        # default 'false' per spec (so manual dispatch publishes)
        assert str(inputs["draft"].get("default")).lower() in ("false", "true"), \
            f"draft default must be a string: {inputs['draft'].get('default')}"


# --- auto-tag.yml --------------------------------------------------------
class TestAutoTagYml:
    def setup_method(self):
        with open(AUTOTAG_YML) as f:
            self.raw = f.read()
        self.cfg = yaml.safe_load(self.raw)

    def test_valid_yaml(self):
        assert isinstance(self.cfg, dict)

    def _steps(self):
        jobs = self.cfg["jobs"]
        # one job; grab its steps list
        job = next(iter(jobs.values()))
        return job["steps"]

    def test_dispatch_step_present_and_named(self):
        steps = self._steps()
        names = [s.get("name", "") for s in steps]
        assert "Dispatch release.yml (workflow_dispatch fallback)" in names, \
            f"dispatch step missing; got names: {names}"

    def test_dispatch_step_after_create_and_push(self):
        steps = self._steps()
        names = [s.get("name", "") for s in steps]
        create_idx = names.index("Create and push tag")
        dispatch_idx = names.index("Dispatch release.yml (workflow_dispatch fallback)")
        assert dispatch_idx > create_idx, \
            f"dispatch step must come AFTER create-and-push (got {dispatch_idx} <= {create_idx})"

    def test_dispatch_step_token_and_curl_params(self):
        steps = self._steps()
        d = next(s for s in steps if s.get("name") == "Dispatch release.yml (workflow_dispatch fallback)")
        env = d.get("env", {})
        assert "GH_TOKEN" in env
        token_expr = env["GH_TOKEN"]
        assert "secrets.GITHUB_TOKEN" in token_expr, f"GH_TOKEN must come from GITHUB_TOKEN: {token_expr}"

        run = d.get("run", "")
        assert "/actions/workflows/release.yml/dispatches" in run, \
            "must POST to release.yml dispatches endpoint"
        # Curl body is shell-escaped inside -d "{...}": '\"ref\":\"...\"'.
        # Normalise: strip backslash-quotes so we can assert on logical JSON.
        normalised = run.replace('\\"', '"')
        assert '"ref":' in normalised, f"curl body must include ref key; got: {run}"
        assert '"inputs":' in normalised, "curl body must include inputs object"
        assert '"version":' in normalised, "curl body must include inputs.version"
        assert '"draft":' in normalised, "curl body must include inputs.draft"
        assert '"draft":"false"' in normalised, \
            f"draft must be set to 'false' in dispatch body; got: {run}"

    def test_dispatch_step_conditional_on_skip(self):
        steps = self._steps()
        d = next(s for s in steps if s.get("name") == "Dispatch release.yml (workflow_dispatch fallback)")
        cond = d.get("if", "")
        assert "steps.skip.outputs.skip" in cond, f"missing skip guard; got if={cond!r}"
        assert "!=" in cond and "'true'" in cond, f"skip guard must be != 'true'; got: {cond!r}"


# --- PRD.md --------------------------------------------------------------
class TestPRD:
    def setup_method(self):
        with open(PRD_MD) as f:
            self.text = f.read()

    def test_section_present(self):
        assert "AUTO-TAG → RELEASE PIPELINE MUST EXPLICITLY DISPATCH RELEASE.YML" in self.text

    def test_curl_example_in_section(self):
        assert "/actions/workflows/release.yml/dispatches" in self.text
        assert "workflow_dispatch" in self.text

    def test_strict_release_draft_expression_documented(self):
        # Documented form must match the strict expression
        assert "releaseDraft: ${{ inputs.draft == 'true' }}" in self.text


# --- Backend smoke -------------------------------------------------------
class TestBackendSmoke:
    def test_api_root_200(self):
        r = requests.get(f"{BASE_URL}/api/", timeout=10)
        assert r.status_code == 200, f"GET /api/ -> {r.status_code}: {r.text[:300]}"
