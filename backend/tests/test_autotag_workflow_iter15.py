"""
Iteration 15 — Static validation of .github/workflows/auto-tag.yml + backend smoke.

Scope (narrow):
  1. auto-tag.yml is valid YAML
  2. on.push.branches == {main, master, main-v2} (set equality, no extras)
  3. on.push.paths contains 'backend/VERSION.txt'
  4. Job tag-and-release: runs-on ubuntu-latest, permissions.contents=write,
     and contains "Read version", "Skip if tag exists", "Create and push tag" steps
  5. release.yml is tag-triggered on v32.*/v33.* and branch-agnostic
  6. Backend smoke: GET /api/ -> 200, GET /api/native/files -> 200

Note on YAML 1.1 quirk: pyyaml parses bare `on:` as the boolean True.
Use cfg.get('on') or cfg.get(True) when reading.
"""
import os
import pathlib
import yaml
import requests
import pytest

REPO = pathlib.Path("/app")
AUTO_TAG = REPO / ".github/workflows/auto-tag.yml"
RELEASE  = REPO / ".github/workflows/release.yml"

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE_URL:
    # Fall back to reading frontend/.env directly (testing env may not export it)
    env_path = REPO / "frontend/.env"
    for line in env_path.read_text().splitlines():
        if line.startswith("REACT_APP_BACKEND_URL="):
            BASE_URL = line.split("=", 1)[1].strip()
            break
BASE_URL = (BASE_URL or "").rstrip("/")


def _load_yaml(p: pathlib.Path):
    with p.open() as f:
        return yaml.safe_load(f)


def _get_on(cfg):
    # YAML 1.1: bare `on` becomes True under pyyaml
    return cfg.get("on") if cfg.get("on") is not None else cfg.get(True)


# ---------- auto-tag.yml ----------
class TestAutoTagWorkflow:
    def test_file_exists_and_parses(self):
        assert AUTO_TAG.exists(), f"{AUTO_TAG} missing"
        cfg = _load_yaml(AUTO_TAG)
        assert isinstance(cfg, dict), "auto-tag.yml didn't parse to a mapping"
        assert cfg.get("name") == "Auto-tag on VERSION.txt change"

    def test_on_push_branches_exact_set(self):
        cfg = _load_yaml(AUTO_TAG)
        on = _get_on(cfg)
        assert on and "push" in on, "missing on.push trigger"
        branches = on["push"].get("branches")
        assert branches is not None, "missing on.push.branches"
        assert set(branches) == {"main", "master", "main-v2"}, (
            f"branches mismatch: {branches!r}"
        )
        # no duplicates
        assert len(branches) == len(set(branches)), f"duplicate branches: {branches}"

    def test_on_push_paths_contains_version_txt(self):
        cfg = _load_yaml(AUTO_TAG)
        on = _get_on(cfg)
        paths = on["push"].get("paths") or []
        assert "backend/VERSION.txt" in paths, f"paths missing VERSION.txt: {paths}"

    def test_job_structure(self):
        cfg = _load_yaml(AUTO_TAG)
        jobs = cfg.get("jobs") or {}
        assert "tag-and-release" in jobs, f"missing job tag-and-release: {list(jobs)}"
        job = jobs["tag-and-release"]
        assert job.get("runs-on") == "ubuntu-latest"
        # permissions can live at top level or job level — accept either
        top_perms = (cfg.get("permissions") or {}).get("contents")
        job_perms = (job.get("permissions") or {}).get("contents")
        assert "write" in (top_perms, job_perms), (
            f"contents:write not set (top={top_perms}, job={job_perms})"
        )

    def test_required_steps_present(self):
        cfg = _load_yaml(AUTO_TAG)
        steps = cfg["jobs"]["tag-and-release"].get("steps") or []
        names = [s.get("name", "") for s in steps]
        for required in ("Read version", "Skip if tag already exists", "Create and push tag"):
            assert any(required in n for n in names), (
                f"missing step '{required}' in {names}"
            )


# ---------- release.yml ----------
class TestReleaseWorkflow:
    def test_release_tag_triggered_and_branch_agnostic(self):
        cfg = _load_yaml(RELEASE)
        on = _get_on(cfg)
        assert on and "push" in on, "release.yml missing on.push"
        push = on["push"]
        # Must NOT be branch-filtered
        assert "branches" not in push, (
            "release.yml should be branch-agnostic; found on.push.branches"
        )
        tags = push.get("tags") or []
        assert "v32.*" in tags and "v33.*" in tags, f"tag patterns wrong: {tags}"


# ---------- backend smoke ----------
@pytest.fixture(scope="module")
def http():
    s = requests.Session()
    s.headers.update({"Accept": "application/json"})
    return s


class TestBackendSmoke:
    def test_root_health(self, http):
        assert BASE_URL, "REACT_APP_BACKEND_URL not resolved"
        r = http.get(f"{BASE_URL}/api/", timeout=20)
        assert r.status_code == 200, f"GET /api/ -> {r.status_code} body={r.text[:200]}"

    def test_native_files_list(self, http):
        r = http.get(f"{BASE_URL}/api/native/files", timeout=30)
        assert r.status_code == 200, (
            f"GET /api/native/files -> {r.status_code} body={r.text[:300]}"
        )
        # Loose structural check — endpoint should return a JSON object/list
        data = r.json()
        assert data is not None
