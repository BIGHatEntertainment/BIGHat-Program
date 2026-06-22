"""Contract tests for the v32.0.0-alpha.10 405-deception fix.

The Setup Wizard rendered "Method Not Allowed" on the desktop installer
because:
  1. The PyInstaller sidecar failed to import `native/router.py`
     (missing hidden imports: bcrypt / email_validator / dnspython / httpx).
  2. With the native router absent, the SPA GET-only catch-all at the
     bottom of server.py matched POST /api/native/setup/initialize via
     method mismatch → 405 with `Allow: GET`.

These tests lock in the fixes so the regression never returns:

  * `/api/native/__status` is always-on and reports the load state.
  * POST to /api/* paths that don't exist returns a structured 404/503
    with a `hint` field, never a generic 405.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
import requests

BACKEND_URL = "http://localhost:8001"


def _bk_running() -> bool:
    try:
        return requests.get(f"{BACKEND_URL}/api/native/__status", timeout=2).ok
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _bk_running(),
    reason="local backend not running on :8001",
)


class TestNativeStatusDiagnostic:
    def test_status_endpoint_always_returns_200(self):
        r = requests.get(f"{BACKEND_URL}/api/native/__status")
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert "native_router_loaded" in data
        assert "native_router_error" in data
        assert "hint" in data

    def test_status_reports_router_loaded_on_preview_pod(self):
        # In the preview/dev container the native router MUST load —
        # if this test fails, the dev DB/bcrypt/email_validator stack
        # is broken locally too and would also break the bundled build.
        r = requests.get(f"{BACKEND_URL}/api/native/__status")
        data = r.json()
        assert data["native_router_loaded"] is True, (
            f"Native router failed to import locally — bundled sidecar "
            f"will also fail. Error: {data['native_router_error']}"
        )


class TestApiCatchAllNeverReturns405:
    """The exact symptom from the Setup Wizard screenshots."""

    def test_post_to_missing_api_path_returns_structured_404_not_405(self):
        r = requests.post(
            f"{BACKEND_URL}/api/this/route/does/not/exist",
            json={},
        )
        assert r.status_code in (404, 503), (
            f"Expected structured 404/503, got {r.status_code}. "
            f"If this is 405 the SPA catch-all is back to swallowing POSTs."
        )
        body = r.json()
        assert body["detail"]["error"] == "api_route_not_found"
        assert "hint" in body["detail"]

    def test_put_delete_patch_also_handled(self):
        for method in ("PUT", "DELETE", "PATCH"):
            r = requests.request(method, f"{BACKEND_URL}/api/missing", json={})
            assert r.status_code != 405, f"{method} got 405 — catch-all regressed"

    def test_existing_post_endpoint_still_works(self):
        # /api/native/setup/initialize must still accept POST (returns 422
        # for invalid body — proves the route exists and the catch-all
        # didn't shadow it).
        r = requests.post(
            f"{BACKEND_URL}/api/native/setup/initialize",
            json={"license_key": "BHE-TEST-XXXX-YYYY-ZZZZ"},
        )
        # Whatever the response shape, it must NOT be 405 ("method not allowed").
        assert r.status_code != 405, (
            "Catch-all is shadowing real POST routes — Setup Wizard will break."
        )


class TestSidecarBuildHasHiddenImports:
    """If the sidecar build script loses these `--collect-all` flags, the
    next bundle will silently regress to the alpha.9 Setup Wizard bug.
    Locks the contract."""

    REQUIRED_COLLECT_ALL = (
        "bcrypt",
        "email_validator",
        "dns",         # dnspython
        "httpx",
        "httpcore",
        "h11",
    )

    REQUIRED_HIDDEN_IMPORT = (
        "email_validator",
        "bcrypt",
        "httpx",
    )

    def test_build_sidecar_script_has_required_collect_all_flags(self):
        script = Path(__file__).resolve().parents[2] / "scripts" / "build_sidecar.py"
        text = script.read_text()
        for mod in self.REQUIRED_COLLECT_ALL:
            assert f'"--collect-all", "{mod}"' in text, (
                f"build_sidecar.py is missing --collect-all {mod}; the next "
                f"alpha bundle will regress to the Setup Wizard 405 bug."
            )

    def test_build_sidecar_script_has_required_hidden_imports(self):
        script = Path(__file__).resolve().parents[2] / "scripts" / "build_sidecar.py"
        text = script.read_text()
        for mod in self.REQUIRED_HIDDEN_IMPORT:
            assert f'"--hidden-import", "{mod}"' in text, (
                f"build_sidecar.py is missing --hidden-import {mod}"
            )
