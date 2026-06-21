"""Locked contract for the v32.0.0 Tauri chromeless title bar.

The user explicitly approved a LYRX-style chromeless window (2026-06-21):
no Windows OS chrome, custom drag region, custom min/max/close buttons.
Three things MUST hold for that experience to work:

  1. `tauri.conf.json` MUST set `decorations: false` on the main window.
     If a future change flips it back to `true`, the user gets the
     Windows title bar AND our custom one stacked.

  2. The React `<TitleBar />` component MUST render unconditionally
     `data-tauri-drag-region` on its root. Without that attribute, the
     window can't be moved — there are no other drag affordances.

  3. The React `<TitleBar />` MUST expose three buttons by their
     `data-testid` attributes so smoke tests can drive them:
       - `tauri-titlebar-minimize`
       - `tauri-titlebar-maximize`
       - `tauri-titlebar-close`

This test pins all three by static inspection — no Tauri runtime needed.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TAURI_CONF = ROOT / "src-tauri" / "tauri.conf.json"
TITLEBAR_JSX = ROOT / "frontend" / "src" / "components" / "TitleBar.jsx"


def test_tauri_conf_decorations_disabled():
    cfg = json.loads(TAURI_CONF.read_text(encoding="utf-8"))
    windows = cfg["app"]["windows"]
    assert len(windows) >= 1, "tauri.conf.json must declare at least one window"
    main = windows[0]
    assert main["label"] == "main", \
        "first window in tauri.conf.json must be label='main' (Rust shell looks it up by name)"
    assert main["decorations"] is False, (
        "tauri.conf.json windows[0].decorations MUST stay false. "
        "Flipping it on stacks the Windows OS chrome on top of our custom "
        "TitleBar.jsx — see CHANGELOG v32.0.0 Phase 2."
    )


def test_titlebar_jsx_has_drag_region():
    text = TITLEBAR_JSX.read_text(encoding="utf-8")
    assert "data-tauri-drag-region" in text, (
        "<TitleBar /> must mark its root with `data-tauri-drag-region` — "
        "without that the chromeless window cannot be moved."
    )


def test_titlebar_jsx_exposes_window_control_testids():
    text = TITLEBAR_JSX.read_text(encoding="utf-8")
    missing = [
        tid for tid in (
            "tauri-titlebar",
            "tauri-titlebar-minimize",
            "tauri-titlebar-maximize",
            "tauri-titlebar-close",
        )
        if f'"{tid}"' not in text and f"'{tid}'" not in text
    ]
    assert not missing, (
        f"<TitleBar /> is missing required data-testid attributes: {missing}. "
        "Browser smoke tests rely on these to drive window controls."
    )


def test_titlebar_jsx_only_renders_inside_tauri():
    """The React app runs both in the dev preview (browser) AND inside
    the Tauri shell. The title bar MUST be a no-op in the browser, else
    every dev session shows two title bars stacked."""
    text = TITLEBAR_JSX.read_text(encoding="utf-8")
    # Either guard form is acceptable — but at least one must be present.
    has_guard = (
        "if (!isTauri)" in text
        or "isTauri ?" in text
        or "__TAURI_INTERNALS__" in text
    )
    assert has_guard, (
        "<TitleBar /> must guard its render on a runtime Tauri detection "
        "(e.g. `window.__TAURI_INTERNALS__`) so dev-preview browsers don't "
        "show the custom chrome."
    )
