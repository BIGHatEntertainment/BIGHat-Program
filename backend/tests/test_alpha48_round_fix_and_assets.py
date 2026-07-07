"""
Regression tests for v32.0.0-alpha.48.

Bugs from merchant's alpha.47 install:
  1. **Round-file mismatch**: selecting MC-02-A rendered MC-01-A's
     questions because our `load_round_from_disk` fell back to the first
     same-type round when the internal `id`/`name` fields didn't match
     the manifest ref. Alpha.48 makes the `file` path the source of
     truth and removes the last-resort random return.
  2. **Audience window doesn't open**: `window.__TAURI__` global isn't
     injected by default in Tauri v2. Alpha.48 switches to a dynamic
     `import('@tauri-apps/api/webviewWindow')` — works whether or not
     the global is set, resolves cleanly in browser/preview builds too.
  3. **Host slide is text-only**: should be the host's 9:16 image.
  4. **Location slide is text-only**: should be branding/overlay images.
  5. **No title cards**: each round should prepend its title-card asset.
  6. **Round order not enforced**: sections-list should sort
     MC → REG → MISC → MYS → BIG regardless of the wizard's ordering.
  7. **Final scores should CSS-scroll like end credits.**
"""
from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ---- Bug 1: MC-02-A must NOT render MC-01-A's questions -----------------

def test_round_file_path_is_source_of_truth(tmp_path, monkeypatch):
    """The merchant reports: copied MC-01-A to MC-02-A, forgot to update
    the internal `name` field. Wizard selected MC-02-A. We must return
    MC-02-A's questions — not MC-01-A's."""
    monkeypatch.setenv("BIGHAT_FILES_DIR", str(tmp_path))
    mc_dir = tmp_path / "Files" / "Trivia" / "MC"
    mc_dir.mkdir(parents=True)

    # Both files have `name: "MC_01_A"` internally (merchant forgot to
    # rename after copying). Only the FILENAMES on disk differ.
    (mc_dir / "MC-01-A.bighat").write_text(json.dumps({
        "id": "round-01", "name": "MC_01_A", "round_type": "MC",
        "questions": [{"number": 1, "question": "Q from MC-01-A?",
                       "options": ["a", "b", "c", "d"], "answer": "a"}],
    }), encoding="utf-8")
    (mc_dir / "MC-02-A.bighat").write_text(json.dumps({
        "id": "round-02", "name": "MC_01_A", "round_type": "MC",  # stale name!
        "questions": [{"number": 1, "question": "Q from MC-02-A?",
                       "options": ["w", "x", "y", "z"], "answer": "w"}],
    }), encoding="utf-8")

    for name in list(sys.modules):
        if name.startswith("native_slides"):
            sys.modules.pop(name, None)
    from native_slides import load_round_from_disk

    # Manifest references MC-02-A explicitly via `file`.
    round_ref = {
        "id": "round-02", "name": "MC-02-A", "type": "MC", "order": 1,
        "file": "MC/MC-02-A.bighat",
    }
    doc = load_round_from_disk(round_ref)
    assert doc is not None
    assert doc["questions"][0]["question"] == "Q from MC-02-A?", (
        "alpha.48 regression: we must render MC-02-A's questions when the "
        "manifest points to MC-02-A.bighat, even if that file's internal "
        "`name` field is stale"
    )


def test_round_no_last_resort_random(tmp_path, monkeypatch):
    """If we truly can't identify the round, return None — NEVER return
    a random same-type file. Wrong questions is worse than a placeholder."""
    monkeypatch.setenv("BIGHAT_FILES_DIR", str(tmp_path))
    mc_dir = tmp_path / "Files" / "Trivia" / "MC"
    mc_dir.mkdir(parents=True)
    (mc_dir / "MC-01-A.bighat").write_text(json.dumps({
        "id": "round-01", "name": "MC_01_A", "round_type": "MC",
        "questions": [],
    }), encoding="utf-8")

    for name in list(sys.modules):
        if name.startswith("native_slides"):
            sys.modules.pop(name, None)
    from native_slides import load_round_from_disk

    # Ref points to a non-existent file, ID doesn't match, name doesn't match.
    doc = load_round_from_disk({
        "id": "no-such-round", "name": "MC-99-Z", "type": "MC", "order": 5,
        "file": "MC/MC-99-Z.bighat",
    })
    assert doc is None, "alpha.48: never last-resort a random same-type round"


def test_norm_helper_fuzzy_matching():
    for name in list(sys.modules):
        if name.startswith("native_slides"):
            sys.modules.pop(name, None)
    from native_slides import _norm
    assert _norm("MC-02-A") == _norm("mc_02_a") == _norm("MC 02 A") == "mc02a"


# ---- Bug 6: round order sort MC→REG→MISC→MYS→BIG -----------------------

def test_sections_list_enforces_round_type_order(tmp_path, monkeypatch):
    """sections-list must reorder round_files by canonical priority."""
    monkeypatch.setenv("BIGHAT_FILES_DIR", str(tmp_path))
    (tmp_path / "Files" / "Trivia" / "Rounds").mkdir(parents=True)

    pres_id = f"pres-order-{uuid.uuid4().hex[:8]}"
    # Merchant/wizard wrote them out-of-order: BIG first, MC last!
    pres = {
        "id": pres_id, "name": "Order Test", "type": "trivia-imported",
        "host": "H", "location": "Locations/x", "createdBy": "t",
        "numRounds": 5,
        "roundFiles": [
            {"id": "b", "name": "B", "type": "BIG", "order": 1, "file": "BIG/B.bighat"},
            {"id": "mys", "name": "Y", "type": "MYS", "order": 2, "file": "MYS/Y.bighat"},
            {"id": "misc", "name": "I", "type": "MISC", "order": 3, "file": "MISC/I.bighat"},
            {"id": "reg", "name": "R", "type": "REG", "order": 4, "file": "REG/R.bighat"},
            {"id": "mc", "name": "M", "type": "MC", "order": 5, "file": "MC/M.bighat"},
        ],
    }
    (tmp_path / "Files" / "Trivia" / "Rounds" / "order.bighat").write_text(
        json.dumps(pres), encoding="utf-8",
    )

    # Force server module reload with fresh env
    for name in list(sys.modules):
        if name.startswith(("server", "routes", "native", "native_slides")):
            sys.modules.pop(name, None)
    import server as _server  # noqa: F401
    from fastapi.testclient import TestClient
    client = TestClient(_server.app)

    r = client.get(f"/api/slide-fetcher/sections-list/{pres_id}")
    assert r.status_code == 200, r.text
    round_sections = [s for s in r.json()["sections"] if s.get("type") == "round"]
    order = [s["roundType"] for s in round_sections]
    assert order == ["MC", "REG", "MISC", "MYS", "BIG"], (
        f"alpha.48: expected MC→REG→MISC→MYS→BIG, got {order}"
    )


# ---- Bug 3 + 4: host + location image slides ---------------------------

def test_host_asset_lookup_from_host_json(tmp_path, monkeypatch):
    monkeypatch.setenv("BIGHAT_FILES_DIR", str(tmp_path))
    hosts = tmp_path / "Files" / "Hosts" / "sellards@bighat.live"
    hosts.mkdir(parents=True)
    # Only 9:16 available — should still be found (fallback path in alpha.51)
    (hosts / "host-9x16.gif").write_bytes(b"GIF89a\x01\x00")
    (hosts / "host.json").write_text(json.dumps({
        "email": "sellards@bighat.live", "name": "Nick Sellards",
        "host_image_9x16": "/api/native/files/raw?path=Files/Hosts/sellards@bighat.live/host-9x16.gif",
    }), encoding="utf-8")

    for name in list(sys.modules):
        if name.startswith("native_slides"):
            sys.modules.pop(name, None)
    from native_slides import load_host_asset

    pres = {"host": "Nick Sellards", "hostEmail": "sellards@bighat.live"}
    asset = load_host_asset(pres)
    assert asset["image_url"] is not None
    # v32.0.0-alpha.51: 16:9 preferred, but 9:16-only fallback still works.
    assert asset["aspect"] in ("9:16", "16:9")
    assert asset["image_url"].startswith("data:image/gif;base64,")


def test_host_asset_prefers_16x9_landscape(tmp_path, monkeypatch):
    """v32.0.0-alpha.51: 16:9 landscape is slide 1's preferred aspect.
    Was 9:16 in alpha.49; merchant reversed the spec on alpha.50."""
    monkeypatch.setenv("BIGHAT_FILES_DIR", str(tmp_path))
    hosts = tmp_path / "Files" / "Hosts" / "sellards@bighat.live"
    hosts.mkdir(parents=True)
    (hosts / "host-9x16.gif").write_bytes(b"GIF89a\x01\x00")
    (hosts / "host-16x9.gif").write_bytes(b"GIF89a\x01\x00")
    (hosts / "host.json").write_text(json.dumps({
        "email": "sellards@bighat.live", "name": "Nick Sellards",
        "host_image_16x9": "/api/native/files/raw?path=Files/Hosts/sellards@bighat.live/host-16x9.gif",
        "host_image_9x16": "/api/native/files/raw?path=Files/Hosts/sellards@bighat.live/host-9x16.gif",
    }), encoding="utf-8")

    for name in list(sys.modules):
        if name.startswith("native_slides"):
            sys.modules.pop(name, None)
    from native_slides import load_host_asset

    asset = load_host_asset({"host": "Nick Sellards", "hostEmail": "sellards@bighat.live"})
    assert asset["aspect"] == "16:9", (
        f"alpha.51: 16:9 must win — got {asset['aspect']}"
    )


def test_location_asset_lookup_scans_branding_and_overlays(tmp_path, monkeypatch):
    monkeypatch.setenv("BIGHAT_FILES_DIR", str(tmp_path))
    loc = tmp_path / "Files" / "Locations" / "monkey-pants-bar-grill"
    (loc / "branding").mkdir(parents=True)
    (loc / "overlays").mkdir(parents=True)
    (loc / "branding" / "welcome.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (loc / "overlays" / "sponsor.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    for name in list(sys.modules):
        if name.startswith("native_slides"):
            sys.modules.pop(name, None)
    from native_slides import load_location_assets

    assets = load_location_assets({"location": "Locations/monkey-pants-bar-grill"})
    assert len(assets) == 2
    kinds = [a["kind"] for a in assets]
    assert kinds == ["branding", "overlay"], "branding must come first"
    # v32.0.0-alpha.49: image URLs are data URLs (not network URLs)
    for a in assets:
        assert a["image_url"].startswith("data:image/"), (
            f"alpha.49: expected data URL, got {a['image_url'][:80]}"
        )


def test_host_slide_renders_image_when_asset_present(tmp_path, monkeypatch):
    monkeypatch.setenv("BIGHAT_FILES_DIR", str(tmp_path))
    hosts = tmp_path / "Files" / "Hosts" / "sellards@bighat.live"
    hosts.mkdir(parents=True)
    (hosts / "host-9x16.gif").write_bytes(b"GIF89a")
    (hosts / "host.json").write_text(json.dumps({
        "email": "sellards@bighat.live", "name": "Nick Sellards",
        "host_image_9x16": "/api/native/files/raw?path=Files/Hosts/sellards@bighat.live/host-9x16.gif",
    }), encoding="utf-8")

    for name in list(sys.modules):
        if name.startswith("native_slides"):
            sys.modules.pop(name, None)
    from native_slides import render_host_section

    slides = render_host_section({
        "host": "Nick Sellards", "hostEmail": "sellards@bighat.live",
        "name": "Test Show",
    })
    assert len(slides) == 1
    # Must include at least one image element
    kinds = [e["type"] for e in slides[0]["elements"]]
    assert "image" in kinds, "alpha.48: host slide must be an image when 9:16 exists"


def test_location_slide_renders_image_per_asset(tmp_path, monkeypatch):
    monkeypatch.setenv("BIGHAT_FILES_DIR", str(tmp_path))
    loc = tmp_path / "Files" / "Locations" / "monkey-pants-bar-grill"
    (loc / "branding").mkdir(parents=True)
    (loc / "branding" / "welcome-01.png").write_bytes(b"PNG")
    (loc / "branding" / "welcome-02.png").write_bytes(b"PNG")

    for name in list(sys.modules):
        if name.startswith("native_slides"):
            sys.modules.pop(name, None)
    from native_slides import render_location_section

    slides = render_location_section({"location": "Locations/monkey-pants-bar-grill"})
    assert len(slides) == 2, "one slide per branding asset"
    for s in slides:
        kinds = [e["type"] for e in s["elements"]]
        assert kinds == ["image"], "each location slide is a single full-bleed image"


# ---- Bug 5: title cards --------------------------------------------------

def test_title_card_loader_per_type(tmp_path, monkeypatch):
    monkeypatch.setenv("BIGHAT_FILES_DIR", str(tmp_path))
    tc = tmp_path / "Files" / "Trivia" / "MC" / "title-cards"
    tc.mkdir(parents=True)
    (tc / "MC.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    for name in list(sys.modules):
        if name.startswith("native_slides"):
            sys.modules.pop(name, None)
    from native_slides import load_round_title_card
    url = load_round_title_card("MC", "MC-02-A")
    assert url is not None
    # v32.0.0-alpha.49: disk assets return data URLs (works in any origin)
    assert url.startswith("data:image/png;base64,")


def test_round_section_prepends_title_card_when_available(tmp_path, monkeypatch):
    monkeypatch.setenv("BIGHAT_FILES_DIR", str(tmp_path))
    (tmp_path / "Files" / "Trivia" / "MC" / "title-cards").mkdir(parents=True)
    (tmp_path / "Files" / "Trivia" / "MC" / "title-cards" / "MC.png").write_bytes(b"PNG")

    for name in list(sys.modules):
        if name.startswith("native_slides"):
            sys.modules.pop(name, None)
    from native_slides import render_round_section

    round_data = {
        "id": "r", "name": "MC-02-A", "round_type": "MC",
        "questions": [{"number": 1, "question": "Q?",
                       "options": ["a", "b", "c", "d"], "answer": "a"}],
    }
    round_ref = {"id": "r", "name": "MC-02-A", "type": "MC", "order": 1}
    slides = render_round_section(round_data, round_ref)
    # First slide must be the title-card image, second the text cover.
    assert slides[0]["metadata"].get("isTitleCard") is True
    assert slides[0]["elements"][0]["type"] == "image"


# ---- Bug 2: audience view uses proper Tauri API -------------------------

def test_open_audience_view_is_sync_window_open():
    """v32.0.0-alpha.49 revision: openAudienceView must be SYNC so the
    pop-up blocker doesn't strip the user gesture. The alpha.48 dynamic-
    import version blocked in Tauri; alpha.49 uses sync window.open."""
    src = (Path(__file__).resolve().parents[2] / "frontend" / "src"
           / "components" / "trivia" / "editor" / "PresentationMode.jsx").read_text()
    assert "const openAudienceView = async" not in src, (
        "alpha.49: openAudienceView must be sync (see alpha.49 CHANGELOG)"
    )
    assert "window.open(" in src


def test_capabilities_permit_webview_creation():
    caps = json.loads((Path(__file__).resolve().parents[2] / "src-tauri"
                       / "capabilities" / "default.json").read_text())
    perms = caps.get("permissions", [])
    assert "core:webview:allow-create-webview-window" in perms, (
        "alpha.48: capability must permit WebviewWindow creation"
    )
    # New window label must be allowed.
    assert "trivia-audience" in caps.get("windows", [])


# ---- Bug 7: final scores CSS scroll --------------------------------------

def test_audience_view_final_scores_uses_css_scroll():
    src = (Path(__file__).resolve().parents[2] / "frontend" / "src" / "pages"
           / "trivia" / "TriviaAudienceView.jsx").read_text()
    # Must include the keyframe animation for the scrolling credits.
    assert "@keyframes bighat-scroll-credits" in src
    assert "animation: `bighat-scroll-credits" in src
