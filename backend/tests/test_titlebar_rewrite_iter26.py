"""
iter-26 — Static validation of the alpha.15 TitleBar.jsx rewrite.

Customer report (after iter-25 alpha.14 ship): the min/max/close buttons in
the chromeless Tauri title bar STILL do nothing on real Windows. iter-25 was
not enough. This iter rewrote /app/frontend/src/components/TitleBar.jsx from
scratch with:
  (a) console.error / console.log on every click + every error path
      so DevTools shows exactly what's failing,
  (b) onMouseDown -> e.stopPropagation() on each button (defensive against
      Tauri's JS drag-region handler eating the click),
  (c) lazy `dynamic import('@tauri-apps/api/window')` to avoid races with
      window.__TAURI__ global injection,
  (d) direct (non-wrapped) IPC calls .minimize() / .toggleMaximize() / .close()
      with try/catch + stringified error logging.

The dev sandbox browser cannot exercise this code path (window.__TAURI__ is
undefined), so this is STATIC VALIDATION ONLY — we lock the file invariants
in pytest so they survive future refactors. Real verification happens on a
Windows alpha.15 install with DevTools open.

Plus one live smoke against the public backend URL.
"""

import json
import os
import re
from pathlib import Path

import pytest
import requests

REPO = Path("/app")
TITLEBAR_JSX = REPO / "frontend" / "src" / "components" / "TitleBar.jsx"
INDEX_CSS = REPO / "frontend" / "src" / "index.css"
CAPS_JSON = REPO / "src-tauri" / "capabilities" / "default.json"
LIB_RS = REPO / "src-tauri" / "src" / "lib.rs"
VERSION_TXT = REPO / "backend" / "VERSION.txt"
TAURI_CONF = REPO / "src-tauri" / "tauri.conf.json"
FRONTEND_ENV = REPO / "frontend" / ".env"

EXPECTED_VERSION = "32.0.0-alpha.15"


# --- helpers ---------------------------------------------------------------

@pytest.fixture(scope="module")
def titlebar_src() -> str:
    assert TITLEBAR_JSX.exists(), f"missing {TITLEBAR_JSX}"
    return TITLEBAR_JSX.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def index_css_src() -> str:
    assert INDEX_CSS.exists(), f"missing {INDEX_CSS}"
    return INDEX_CSS.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def lib_rs_src() -> str:
    assert LIB_RS.exists(), f"missing {LIB_RS}"
    return LIB_RS.read_text(encoding="utf-8")


def _read_env_value(env_path: Path, key: str) -> str:
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip()
    raise AssertionError(f"{key} not found in {env_path}")


# --- TitleBar.jsx file-level contract --------------------------------------

class TestTitleBarFileContract:
    """alpha.15 rewrite — locks the rewritten file structure."""

    def test_file_exists_and_default_exports_titlebar(self, titlebar_src):
        assert "export default TitleBar" in titlebar_src, \
            "TitleBar.jsx must default-export a component named TitleBar"
        # also confirm the component is actually defined
        assert re.search(r"function\s+TitleBar\s*\(", titlebar_src) \
            or re.search(r"const\s+TitleBar\s*=", titlebar_src), \
            "TitleBar component definition missing"

    def test_dynamic_import_of_tauri_window_api(self, titlebar_src):
        # Must dynamic-import, not static-import, to dodge the global-injection
        # race. We accept either single or double quotes around the module id.
        pattern = re.compile(
            r"""import\s*\(\s*['"]@tauri-apps/api/window['"]\s*\)"""
        )
        assert pattern.search(titlebar_src), \
            "TitleBar.jsx must contain `import('@tauri-apps/api/window')` (dynamic)"

    def test_uses_getCurrentWindow_or_getCurrent(self, titlebar_src):
        assert ("getCurrentWindow" in titlebar_src
                or "getCurrent" in titlebar_src), \
            "TitleBar.jsx must reference getCurrentWindow or getCurrent"

    def test_calls_all_three_ipc_methods(self, titlebar_src):
        for method in (".minimize(", ".toggleMaximize(", ".close("):
            assert method in titlebar_src, \
                f"TitleBar.jsx missing IPC call {method!r}"

    @pytest.mark.parametrize("testid", [
        "tauri-titlebar-minimize",
        "tauri-titlebar-maximize",
        "tauri-titlebar-close",
    ])
    def test_data_testids_present(self, titlebar_src, testid):
        # Allow either a static `data-testid="..."` literal OR a template
        # literal of the form `data-testid={`tauri-titlebar-${id}`}` since
        # the rewrite uses the latter with id ∈ {minimize,maximize,close}.
        suffix = testid.rsplit("-", 1)[-1]
        literal = f'data-testid="{testid}"'
        templated_pat = re.compile(
            r"data-testid\s*=\s*\{\s*`tauri-titlebar-\$\{\s*id\s*\}`\s*\}"
        )
        has_literal = literal in titlebar_src
        has_template = bool(templated_pat.search(titlebar_src)) and (
            f'id="{suffix}"' in titlebar_src
            or f"id={{'{suffix}'}}" in titlebar_src
            or f'id={{"{suffix}"}}' in titlebar_src
            or f'id="{suffix}"' in titlebar_src
        )
        # Final fallback: just confirm the literal string appears somewhere
        # the renderer can produce it.
        has_any = has_literal or has_template or testid in titlebar_src
        assert has_any, f"data-testid for {testid!r} not detected in TitleBar.jsx"

    def test_onmousedown_stoppropagation_present(self, titlebar_src):
        # Defensive guard so any stray drag-region attribute up-tree cannot
        # eat the click on mousedown.
        pattern = re.compile(
            r"onMouseDown\s*=\s*\{\s*\(\s*e\s*\)\s*=>\s*e\.stopPropagation\(\s*\)\s*\}"
        )
        assert pattern.search(titlebar_src), \
            "TitleBar.jsx must have `onMouseDown={(e) => e.stopPropagation()}`"

    def test_console_logging_present(self, titlebar_src):
        # Customer-facing diagnostic — needed because we cannot reproduce
        # the bug locally; the only signal is what DevTools prints.
        assert "console.error" in titlebar_src, \
            "TitleBar.jsx must contain console.error(...) for DevTools diagnosis"
        assert "console.log" in titlebar_src, \
            "TitleBar.jsx must contain console.log(...) for DevTools diagnosis"

    def test_returns_null_when_not_in_tauri(self, titlebar_src):
        # Renders nothing in the browser dev sandbox.
        assert "inTauri" in titlebar_src, "expected an inTauri() guard helper"
        # accept either `if (!inTauri()) return null;` or equivalent JSX-return form
        guard_re = re.compile(r"if\s*\(\s*!\s*inTauri\s*\(\s*\)\s*\)\s*return\s+null")
        assert guard_re.search(titlebar_src), \
            "TitleBar.jsx must early-return null when not inside Tauri"

    def test_no_drag_region_on_outer_wrapper(self, titlebar_src):
        """iter-25 regression guard — the outer .tauri-titlebar div MUST NOT
        carry data-tauri-drag-region. Tauri's JS handler would otherwise
        start a window drag on mousedown over the buttons' SVGs and eat
        the click."""
        outer_re = re.compile(
            r"""<div\s+className\s*=\s*["']tauri-titlebar["'][^>]*>"""
        )
        m = outer_re.search(titlebar_src)
        assert m, "outer .tauri-titlebar wrapper <div> not found"
        outer_tag = m.group(0)
        assert "data-tauri-drag-region" not in outer_tag, (
            "REGRESSION: data-tauri-drag-region is back on the outer "
            ".tauri-titlebar wrapper. This re-introduces the iter-25 bug."
        )

    def test_drag_region_preserved_on_brand(self, titlebar_src):
        """The brand <div> (logo + wordmark) is the legitimate drag handle
        and MUST keep data-tauri-drag-region."""
        brand_re = re.compile(
            r"""<div[^>]*className\s*=\s*["']tauri-titlebar__brand["'][^>]*>"""
        )
        m = brand_re.search(titlebar_src)
        assert m, ".tauri-titlebar__brand wrapper not found"
        assert "data-tauri-drag-region" in m.group(0), (
            "REGRESSION: drag handle lost — .tauri-titlebar__brand must "
            "carry data-tauri-drag-region or the window cannot be dragged."
        )


# --- iter-25 regression invariants (kept from previous fix) ----------------

class TestIter25RegressionInvariants:
    """The iter-25 changes are still required — alpha.15 only ADDS on top."""

    def test_capability_includes_core_window_default(self):
        data = json.loads(CAPS_JSON.read_text(encoding="utf-8"))
        perms = data.get("permissions", [])
        assert "core:window:default" in perms, (
            "REGRESSION: 'core:window:default' missing from "
            "src-tauri/capabilities/default.json — window IPC will be denied."
        )

    def test_lib_rs_exit_requested_kills_sidecar(self, lib_rs_src):
        # The sidecar cleanup path on window close.
        assert "RunEvent::ExitRequested" in lib_rs_src, \
            "REGRESSION: ExitRequested arm missing from lib.rs"
        # Find the ExitRequested block and confirm child.kill() is inside it.
        idx = lib_rs_src.index("RunEvent::ExitRequested")
        snippet = lib_rs_src[idx: idx + 600]
        assert "child.kill()" in snippet, (
            "REGRESSION: ExitRequested no longer calls child.kill() — "
            "the Python sidecar will be orphaned on app close."
        )

    def test_index_css_pointer_events_none_on_btn_svgs(self, index_css_src):
        # Locks the iter-25 CSS fix: SVG icons must not receive pointer events,
        # otherwise event.target becomes the <svg> and Tauri's drag handler
        # eats the click.
        pattern = re.compile(
            r"\.tauri-titlebar__btn\s+svg[^{}]*\{[^}]*pointer-events\s*:\s*none",
            re.DOTALL,
        )
        assert pattern.search(index_css_src), (
            "REGRESSION: `.tauri-titlebar__btn svg { pointer-events: none }` "
            "rule missing from index.css — iter-25 fix lost."
        )


# --- version stamping ------------------------------------------------------

class TestVersionStamping:

    def test_backend_version_txt(self):
        assert VERSION_TXT.read_text(encoding="utf-8").strip() == EXPECTED_VERSION

    def test_tauri_conf_version(self):
        data = json.loads(TAURI_CONF.read_text(encoding="utf-8"))
        assert data.get("version") == EXPECTED_VERSION, \
            f"tauri.conf.json version = {data.get('version')!r}, expected {EXPECTED_VERSION!r}"


# --- backend smoke ---------------------------------------------------------

class TestBackendSmoke:
    """Live smoke against the public REACT_APP_BACKEND_URL."""

    def test_api_root_returns_200(self):
        base = _read_env_value(FRONTEND_ENV, "REACT_APP_BACKEND_URL").rstrip("/")
        url = f"{base}/api/"
        resp = requests.get(url, timeout=15)
        assert resp.status_code == 200, (
            f"GET {url} -> {resp.status_code}\nbody: {resp.text[:300]}"
        )
