"""Locks the audience-window contract (trivia / bingo / karaoke)."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _cap():
    return json.loads((ROOT / "src-tauri/capabilities/default.json").read_text())


def test_capability_trusts_local_sidecar_origin():
    # Main window is navigated to http://127.0.0.1:<port>/ => REMOTE in Tauri 2.
    urls = _cap()["remote"]["urls"]
    assert any("127.0.0.1" in u for u in urls)
    assert any("localhost" in u for u in urls)


def test_capability_lists_audience_windows():
    w = _cap()["windows"]
    for label in ("main", "trivia-audience", "bingo-audience"):
        assert label in w


def test_trivia_presenter_never_falls_back_to_popup_in_desktop():
    src = (ROOT / "frontend/src/components/trivia/editor/PresentationMode.jsx").read_text()
    assert "openNativeAudience" in src
    # inside the isTauri() branch the code must return before window.open
    branch = src[src.index("if (isTauri()) {"):src.index("window.open(audienceUrl")]
    assert "return;" in branch
    assert "window.open(" not in branch


def test_native_opener_uses_absolute_same_origin_url():
    src = (ROOT / "frontend/src/lib/audienceWindow.js").read_text()
    assert "window.location.origin" in src
