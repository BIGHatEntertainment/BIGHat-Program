"""Locked contract for the v32.0.0-alpha.17+ Tauri window shell.

Original chromeless design (alpha.4 → alpha.16) was abandoned after two
rounds of customer-reported "double title bar" + unresponsive window
controls on Windows. We now run with native OS chrome and NO custom
React titlebar.

These tests pin the new invariants by static inspection — no Tauri
runtime needed. If you flip any of these, **read the explanation in
the matching CHANGELOG entry (v32.0.0-alpha.17) and PRD section
"WINDOW CHROME = NATIVE OS" before changing this test**.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TAURI_CONF = ROOT / "src-tauri" / "tauri.conf.json"
TITLEBAR_JSX = ROOT / "frontend" / "src" / "components" / "TitleBar.jsx"
APP_JS = ROOT / "frontend" / "src" / "App.js"
SPLASH_HTML = ROOT / "frontend" / "public" / "splash.html"
LIB_RS = ROOT / "src-tauri" / "src" / "lib.rs"


def test_tauri_conf_decorations_enabled():
    cfg = json.loads(TAURI_CONF.read_text(encoding="utf-8"))
    windows = cfg["app"]["windows"]
    assert len(windows) >= 1, "tauri.conf.json must declare at least one window"
    main = windows[0]
    assert main["label"] == "main"
    assert main["decorations"] is True, (
        "tauri.conf.json windows[0].decorations MUST stay true. "
        "Chromeless mode + Webview2 produces a double titlebar on "
        "Windows — see CHANGELOG v32.0.0-alpha.17."
    )


def test_custom_titlebar_jsx_removed():
    assert not TITLEBAR_JSX.exists(), (
        "frontend/src/components/TitleBar.jsx must NOT exist. The "
        "custom React titlebar was removed in v32.0.0-alpha.17. If "
        "you need to bring it back, read the PRD section "
        "'WINDOW CHROME = NATIVE OS' first."
    )


def test_app_js_does_not_mount_titlebar():
    text = APP_JS.read_text(encoding="utf-8")
    assert "<TitleBar" not in text, (
        "App.js must NOT mount <TitleBar />. We rely on native OS chrome."
    )
    assert "components/TitleBar" not in text, (
        "App.js must NOT import the deleted TitleBar component."
    )


def test_page_header_component_exists():
    """v32.0.0-alpha.18 unified sub-page nav. <PageHeader /> is the only
    sanctioned header for sub-pages (Files, Round Generator, Schedule,
    Update Tool, …) — gives every page a Back arrow top-left and a Home
    button top-right at identical positions, so muscle memory holds.

    Presenter views (Trivia/Bingo/Karaoke live shows) opt out of the
    Home button via `showHome={false}` so a host can't accidentally
    close the show mid-event — see PRD 'WINDOW CHROME' for the related
    safety constraint."""
    p = ROOT / "frontend" / "src" / "components" / "PageHeader.jsx"
    assert p.exists(), "PageHeader.jsx must exist (sub-page nav contract)"
    txt = p.read_text(encoding="utf-8")
    assert "page-header-back" in txt
    assert "page-header-home" in txt
    assert "showHome" in txt, "PageHeader must accept a `showHome` prop for presenter views"


def test_splash_html_has_no_custom_titlebar():
    text = SPLASH_HTML.read_text(encoding="utf-8")
    # The custom splash titlebar used these markers — none may remain.
    forbidden = (".titlebar {", "titlebar__brand", "titlebar__controls",
                 "titlebar__btn", 'id="btn-min"', 'id="btn-max"',
                 'id="btn-close"')
    leaks = [m for m in forbidden if m in text]
    assert not leaks, (
        f"splash.html still contains custom titlebar markup: {leaks}. "
        "It was stripped in v32.0.0-alpha.17 to let native chrome show."
    )


def test_lib_rs_treekills_sidecar_on_windows():
    text = LIB_RS.read_text(encoding="utf-8")
    assert "RunEvent::ExitRequested" in text
    assert "taskkill" in text, (
        "src-tauri/src/lib.rs must run `taskkill /F /T /PID <pid>` on "
        "Windows in the ExitRequested arm. PyInstaller --onefile spawns "
        "a child python.exe that survives a plain CommandChild.kill() — "
        "see CHANGELOG v32.0.0-alpha.17."
    )
    # The bootloader PID is captured BEFORE child.kill() consumes the child.
    assert 'child.pid()' in text, (
        "lib.rs must capture child.pid() BEFORE calling child.kill(); "
        "kill() consumes the CommandChild."
    )
