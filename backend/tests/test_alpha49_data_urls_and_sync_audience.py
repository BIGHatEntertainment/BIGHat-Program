"""
Regression tests for v32.0.0-alpha.49.

Bugs from merchant's alpha.48 install:
  1. **Host GIF not rendering** despite `host-9x16.gif` being on disk.
     Root cause: my URL was `/api/native/files/raw?path=...` (relative)
     but the Tauri webview origin ≠ backend origin, so the `<img>` 404s.
  2. **Location images not rendering** — same origin-mismatch bug.
  3. **Title cards absent** — merchant hadn't uploaded any per-round
     assets AND my code had no fallback to the bundled `public/*.jpg`.
  4. **Audience view button "please allow pop-ups"** — my alpha.48
     `openAudienceView` was `async` with an `await import(...)` BEFORE
     `window.open`. That awaited-import loses the user-gesture context
     that the pop-up blocker requires.

Alpha.49 fixes:
  A. Backend inlines file bytes as `data:` URLs (works in any origin).
  B. Bundled title-card fallbacks (`public/MC_Title_Card.jpg`, etc.).
  C. `openAudienceView` is now synchronous — `window.open` called
     inside the click gesture with no `await` before it.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_data_url_encoder_handles_png(tmp_path, monkeypatch):
    monkeypatch.setenv("BIGHAT_FILES_DIR", str(tmp_path))
    (tmp_path / "Files").mkdir()
    p = tmp_path / "Files" / "sample.png"
    p.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00")

    for name in list(sys.modules):
        if name.startswith("native_slides"):
            sys.modules.pop(name, None)
    from native_slides import _to_data_url

    url = _to_data_url("Files/sample.png")
    assert url is not None
    assert url.startswith("data:image/png;base64,")


def test_data_url_encoder_handles_gif(tmp_path, monkeypatch):
    monkeypatch.setenv("BIGHAT_FILES_DIR", str(tmp_path))
    (tmp_path / "Files").mkdir()
    p = tmp_path / "Files" / "anim.gif"
    p.write_bytes(b"GIF89a\x01\x00\x01\x00")

    for name in list(sys.modules):
        if name.startswith("native_slides"):
            sys.modules.pop(name, None)
    from native_slides import _to_data_url

    url = _to_data_url("Files/anim.gif")
    assert url is not None
    assert url.startswith("data:image/gif;base64,")


def test_data_url_encoder_returns_none_on_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("BIGHAT_FILES_DIR", str(tmp_path))
    for name in list(sys.modules):
        if name.startswith("native_slides"):
            sys.modules.pop(name, None)
    from native_slides import _to_data_url
    assert _to_data_url("Files/does-not-exist.png") is None


def test_to_api_url_prefers_data_url_when_possible(tmp_path, monkeypatch):
    monkeypatch.setenv("BIGHAT_FILES_DIR", str(tmp_path))
    (tmp_path / "Files").mkdir()
    (tmp_path / "Files" / "img.png").write_bytes(b"\x89PNG")

    for name in list(sys.modules):
        if name.startswith("native_slides"):
            sys.modules.pop(name, None)
    from native_slides import _to_api_url

    assert _to_api_url("Files/img.png").startswith("data:image/png;base64,")


def test_bundled_title_cards_ship_in_public_folder():
    """The frontend's public folder MUST include title-card assets for
    every canonical round type — otherwise `load_round_title_card`
    returns URLs that 404 on the frontend origin."""
    public = ROOT.parent / "frontend" / "public"
    assert (public / "MC_Title_Card.jpg").exists(), (
        "alpha.49: MC_Title_Card.jpg must ship in frontend/public/"
    )
    assert (public / "BIG_Title_Card.jpg").exists()
    assert (public / "MYS_Title_Card.jpg").exists()
    # REG and MISC ship as SVGs (created by alpha.49)
    assert (public / "REG_Title_Card.svg").exists()
    assert (public / "MISC_Title_Card.svg").exists()


def test_load_round_title_card_falls_back_to_bundled(tmp_path, monkeypatch):
    """Merchant hasn't uploaded any title cards to disk — we still need
    to return SOMETHING for MC/REG/MISC/MYS/BIG."""
    monkeypatch.setenv("BIGHAT_FILES_DIR", str(tmp_path))

    for name in list(sys.modules):
        if name.startswith("native_slides"):
            sys.modules.pop(name, None)
    from native_slides import load_round_title_card

    for rt in ("MC", "REG", "MISC", "MYS", "BIG", "NONSENSE"):
        url = load_round_title_card(rt, f"{rt}-01-A")
        assert url is not None, f"alpha.49: expected bundled fallback for {rt}, got None"
        assert url.startswith("/") and "Title_Card" in url, (
            f"alpha.49: {rt} bundled URL should be frontend-relative, got {url}"
        )


def test_load_round_title_card_prefers_disk_over_bundled(tmp_path, monkeypatch):
    """When the merchant DOES upload a per-round title card to disk, it
    wins over the bundled fallback."""
    monkeypatch.setenv("BIGHAT_FILES_DIR", str(tmp_path))
    tc_dir = tmp_path / "Files" / "Trivia" / "MC" / "title-cards"
    tc_dir.mkdir(parents=True)
    (tc_dir / "MC.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    for name in list(sys.modules):
        if name.startswith("native_slides"):
            sys.modules.pop(name, None)
    from native_slides import load_round_title_card

    url = load_round_title_card("MC", "MC-01-A")
    assert url.startswith("data:image/png;base64,"), (
        "alpha.49: disk asset must win over the bundled /MC_Title_Card.jpg"
    )


# ---- Audience view pop-up: sync-first spawn -----------------------------

def test_open_audience_view_is_sync_no_await_before_window_open():
    """The pop-up blocker requires window.open to be called SYNCHRONOUSLY
    inside the user-gesture click. Any `await` before it loses the
    gesture context. Alpha.48 was async → alpha.49 must be sync."""
    src = (ROOT.parent / "frontend" / "src" / "components" / "trivia"
           / "editor" / "PresentationMode.jsx").read_text()

    # Locate the openAudienceView function
    fn_start = src.index("const openAudienceView = ")
    fn_end = src.index("const closeAudienceView", fn_start)
    fn_body = src[fn_start:fn_end]

    # Must be a plain function, not `async`
    assert "const openAudienceView = async" not in fn_body, (
        "alpha.49 regression: openAudienceView must be sync so `window.open` "
        "runs inside the user-gesture stack"
    )
    # Must call window.open
    assert "window.open(" in fn_body
    # No `await` should appear BEFORE the first window.open call
    pre_open = fn_body[:fn_body.index("window.open(")]
    assert "await " not in pre_open, (
        "alpha.49 regression: no `await` allowed before `window.open()` — "
        "it strips the user-gesture context and the pop-up gets blocked"
    )
