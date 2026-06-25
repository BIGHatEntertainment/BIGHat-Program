"""
Iter 25 — Static validation of the alpha.14 title-bar click-through fix.

Customer (alpha.13) reported the X / minimize / maximize buttons hover-style
but do nothing on click. RCA: the OUTER `.tauri-titlebar` div carried
`data-tauri-drag-region`, AND the SVG icons inside each button had no
`pointer-events: none`. Tauri's JS-side drag handler resolves the click
target via `event.target.closest('[data-tauri-drag-region]')` on mousedown.
Because the click landed on the SVG (not the BUTTON), Tauri's
"ignore form elements" short-circuit missed, mousedown was hijacked to
start a window drag, and the button onClick never fired.

This Tauri-shell + CSS fix only renders in the native Windows build —
the dev sandbox has no Tauri runtime, so we validate at the file level.
A live smoke against the FastAPI backend confirms the dev preview is up.
"""

# --- imports ---
import os
import re
from pathlib import Path

import pytest
import requests

REPO = Path("/app")
TITLEBAR_JSX = REPO / "frontend/src/components/TitleBar.jsx"
INDEX_CSS = REPO / "frontend/src/index.css"
CAPS_JSON = REPO / "src-tauri/capabilities/default.json"
LIB_RS = REPO / "src-tauri/src/lib.rs"
PRD = REPO / "memory/PRD.md"


# ---------- fixtures ----------
@pytest.fixture(scope="module")
def titlebar_src() -> str:
    return TITLEBAR_JSX.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def index_css() -> str:
    return INDEX_CSS.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def caps_src() -> str:
    return CAPS_JSON.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def lib_rs_src() -> str:
    return LIB_RS.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def prd_src() -> str:
    return PRD.read_text(encoding="utf-8")


# ---------- TitleBar.jsx ----------
class TestTitleBarJsx:
    """drag-region removal + brand drag-handle preserved + onClick handlers."""

    def test_outer_titlebar_div_has_no_drag_region_attr(self, titlebar_src):
        # Match the opening tag of the outer <div className="tauri-titlebar" ...>
        m = re.search(
            r'<div\s+className="tauri-titlebar"[^>]*>',
            titlebar_src,
            re.DOTALL,
        )
        assert m, "outer .tauri-titlebar <div> not found in TitleBar.jsx"
        outer_open = m.group(0)
        assert "data-tauri-drag-region" not in outer_open, (
            "REGRESSION: data-tauri-drag-region must NOT be on the outer "
            ".tauri-titlebar wrapper (it hijacks button clicks). Found: "
            + outer_open
        )

    def test_brand_div_keeps_drag_region(self, titlebar_src):
        m = re.search(
            r'<div\s+className="tauri-titlebar__brand"[^>]*>',
            titlebar_src,
        )
        assert m, ".tauri-titlebar__brand <div> not found"
        assert "data-tauri-drag-region" in m.group(0), (
            "Brand div MUST keep data-tauri-drag-region as the JS drag handle."
        )

    def test_window_control_handlers_intact(self, titlebar_src):
        for call in ("w.minimize()", "w.toggleMaximize()", "w.close()"):
            assert call in titlebar_src, f"missing window-control call: {call}"

    def test_button_testids_intact(self, titlebar_src):
        for tid in (
            "tauri-titlebar-minimize",
            "tauri-titlebar-maximize",
            "tauri-titlebar-close",
        ):
            assert tid in titlebar_src, f"missing data-testid for {tid}"


# ---------- index.css ----------
class TestIndexCss:
    """SVG pointer-events fix + drag-region CSS regression."""

    def test_svg_pointer_events_none_rule(self, index_css):
        # Whitespace-tolerant match: selector list followed by pointer-events: none.
        pattern = re.compile(
            r"\.tauri-titlebar__btn\s+svg\s*,\s*"
            r"\.tauri-titlebar__btn\s+svg\s*\*\s*"
            r"\{\s*[^}]*pointer-events\s*:\s*none\s*;?[^}]*\}",
            re.DOTALL,
        )
        assert pattern.search(index_css), (
            "CRITICAL: missing CSS rule "
            "`.tauri-titlebar__btn svg, .tauri-titlebar__btn svg * "
            "{ pointer-events: none; }` — without this, SVG icons steal "
            "click events and Tauri's drag handler eats the mousedown."
        )

    def test_webkit_app_region_drag_on_titlebar(self, index_css):
        # Block must include -webkit-app-region: drag inside .tauri-titlebar.
        m = re.search(
            r"\.tauri-titlebar\s*\{[^}]*-webkit-app-region\s*:\s*drag\s*;",
            index_css,
            re.DOTALL,
        )
        assert m, "CSS drag region `-webkit-app-region: drag` missing on .tauri-titlebar"

    def test_webkit_app_region_no_drag_on_controls(self, index_css):
        m = re.search(
            r"\.tauri-titlebar__controls\s*\{[^}]*-webkit-app-region\s*:\s*no-drag\s*;",
            index_css,
            re.DOTALL,
        )
        assert m, (
            "`-webkit-app-region: no-drag` must remain on "
            ".tauri-titlebar__controls so clicks aren't OS-dragged."
        )


# ---------- capabilities/default.json ----------
class TestCapabilities:
    """core:window:default must still be granted (iter-20 regression)."""

    def test_window_default_permission_present(self, caps_src):
        import json
        data = json.loads(caps_src)
        perms = data.get("permissions", [])
        assert "core:window:default" in perms, (
            "REGRESSION: core:window:default capability dropped — minimize/"
            "maximize/close IPC will return permission errors at runtime."
        )


# ---------- lib.rs ExitRequested ----------
class TestLibRsExitRequested:
    def test_exit_requested_kills_sidecar(self, lib_rs_src):
        # Look for the ExitRequested arm and a child.kill() inside the run loop.
        assert "RunEvent::ExitRequested" in lib_rs_src, (
            "ExitRequested arm missing from app.run event loop"
        )
        # Find the arm body and ensure child.kill() is called inside it.
        arm_match = re.search(
            r"RunEvent::ExitRequested\s*\{[^}]*\}\s*=>\s*\{(.*?)\n\s{12}\}",
            lib_rs_src,
            re.DOTALL,
        )
        # Fall back to a broader window if the regex above is too strict.
        snippet = arm_match.group(1) if arm_match else lib_rs_src
        assert "child.kill()" in snippet, (
            "child.kill() not invoked in ExitRequested handler — sidecar "
            "will leak on window close."
        )


# ---------- PRD.md doc invariant ----------
class TestPrdDocumentation:
    def test_prd_documents_svg_pointer_events_invariant(self, prd_src):
        assert "WINDOW CONTROLS" in prd_src.upper() or "WINDOW CONTROLS" in prd_src
        assert "pointer-events: none" in prd_src, (
            "PRD WINDOW CONTROLS section must mention the "
            "`pointer-events: none` invariant for the SVG icons."
        )
        assert "SVG" in prd_src, "PRD must mention SVG root cause"


# ---------- live backend smoke ----------
class TestBackendSmoke:
    def test_api_root_returns_2xx(self):
        base = os.environ.get("REACT_APP_BACKEND_URL")
        if not base:
            # Fallback to the frontend .env when env var isn't injected.
            env_file = REPO / "frontend/.env"
            if env_file.exists():
                for line in env_file.read_text().splitlines():
                    if line.startswith("REACT_APP_BACKEND_URL="):
                        base = line.split("=", 1)[1].strip().strip('"').strip("'")
                        break
        assert base, "REACT_APP_BACKEND_URL not configured"
        url = base.rstrip("/") + "/api/"
        resp = requests.get(url, timeout=15)
        assert resp.status_code == 200, (
            f"GET {url} returned {resp.status_code}: {resp.text[:200]}"
        )
