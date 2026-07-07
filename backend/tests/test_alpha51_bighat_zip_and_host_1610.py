"""v32.0.0-alpha.51 — `.bighat` ZIP extraction + 16:9 host image priority.

Locks in the fact that:
  1. `_read_bighat_round(path)` on a real ZIP `.bighat` returns a dict with
     normalised question fields (`question`, `answer`, `options`,
     `correctOption`) and an inlined `cover_image_data_url`.
  2. `render_round_section` picks up that data URL and puts it on slide 0
     (the round title-card slide).
  3. `_rank_asset` prefers a 16:9 asset over a 9:16 asset when both exist
     for the same host.
  4. Legacy bare-JSON `.bighat` files still work (backwards compat).

The fixtures in /app/backend/tests/fixtures/bighat/ are real files
produced by the round generator — same magic bytes / same payload
keys the merchant is uploading.
"""
from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import native_slides as ns  # noqa: E402  (path insert above)


FIXTURES = Path(__file__).parent / "fixtures" / "bighat"
MC_FIX = FIXTURES / "mc-01-a.bighat"
BIG_FIX = FIXTURES / "big-cactus-league-easy.bighat"


# ---------------------------------------------------------------------------
# 1. ZIP extraction + payload key normalisation
# ---------------------------------------------------------------------------

def test_bighat_zip_is_extracted_and_keys_normalised():
    assert MC_FIX.exists(), "fixture missing"
    # Sanity: fixture really is a ZIP with the expected members.
    with zipfile.ZipFile(MC_FIX) as z:
        names = z.namelist()
    assert "payload.json" in names
    assert "manifest.json" in names
    assert any(n.startswith("assets/cover.") for n in names)

    doc = ns._read_bighat_round(MC_FIX)
    assert doc is not None
    assert doc["_source_format"] == "bighat-zip"
    assert doc["round_type"] == "MC"

    qs = doc["questions"]
    assert len(qs) >= 1
    q0 = qs[0]
    # Normalised keys are present and non-empty for a real fixture.
    assert q0["question"], "prompt → question mapping missing"
    assert q0["answer"], "answer key missing"
    assert isinstance(q0["options"], list) and len(q0["options"]) == 4
    assert isinstance(q0["correctOption"], int)
    assert q0["number"] == 1


def test_bighat_zip_inlines_cover_image_as_data_url():
    doc = ns._read_bighat_round(MC_FIX)
    assert doc is not None
    url = doc["cover_image_data_url"]
    assert url and url.startswith("data:image/"), (
        f"cover_image not inlined as data URL: {url!r}"
    )
    assert ";base64," in url


def test_bighat_zip_inlines_per_question_media():
    """The BIG fixture has an `assets/q1.gif` referenced by question 1."""
    doc = ns._read_bighat_round(BIG_FIX)
    assert doc is not None
    q0 = doc["questions"][0]
    assert q0.get("media_url"), "per-question media not inlined"
    assert q0["media_url"].startswith("data:image/gif;")


def test_legacy_bare_json_bighat_still_works(tmp_path: Path):
    legacy = tmp_path / "legacy.bighat"
    legacy.write_text(json.dumps({
        "id": "legacy-1",
        "round_type": "REG",
        "name": "Legacy Round",
        "questions": [{"number": 1, "question": "Q?", "answer": "A"}],
    }), encoding="utf-8")
    doc = ns._read_bighat_round(legacy)
    assert doc is not None
    # Legacy path: returned as-is (no _source_format tag)
    assert doc["round_type"] == "REG"
    assert doc["questions"][0]["question"] == "Q?"


# ---------------------------------------------------------------------------
# 2. Title-card slide picks up the embedded cover
# ---------------------------------------------------------------------------

def test_render_round_uses_embedded_cover_for_slide_0():
    doc = ns._read_bighat_round(MC_FIX)
    assert doc is not None
    round_ref = {"type": doc["round_type"], "name": doc["name"], "order": 1}
    slides = ns.render_round_section(doc, round_ref)
    assert slides, "no slides produced"
    title_slide = slides[0]
    md = title_slide.get("metadata") or {}
    assert md.get("isRoundTitle") is True
    assert md.get("isTitleCard") is True, "isTitleCard not marked True"
    imgs = [e for e in title_slide["elements"] if e["type"] == "image"]
    assert imgs, "no image element on title slide"
    assert imgs[0]["src"].startswith("data:image/"), (
        "title-card image should be an inlined data: URL"
    )


# ---------------------------------------------------------------------------
# 3. Host image asset ranking prefers 16:9 over 9:16
# ---------------------------------------------------------------------------

def test_host_rank_prefers_16x9_over_9x16(tmp_path: Path):
    # Locate `_rank_asset` and drive it directly on a synthesised
    # host folder that has BOTH a 16x9 and a 9x16 file.
    docs = tmp_path
    host_dir = docs / "Files" / "Hosts" / "test-host"
    host_dir.mkdir(parents=True)
    (host_dir / "host-16x9.jpg").write_bytes(b"\xff\xd8\xff\xe0" + b"0" * 32)
    (host_dir / "host-9x16.jpg").write_bytes(b"\xff\xd8\xff\xe0" + b"0" * 32)
    host_json = host_dir / "host.json"
    host_json.write_text(json.dumps({
        "name": "Test Host",
        "host_image_16x9": "Files/Hosts/test-host/host-16x9.jpg",
        "host_image_9x16": "Files/Hosts/test-host/host-9x16.jpg",
    }), encoding="utf-8")

    # We call the public API — load_host_asset — with a fabricated
    # presentation dict. It routes through _rank_asset.
    import unittest.mock as um
    with um.patch.object(ns, "_docs_root", return_value=docs):
        result = ns.load_host_asset({"host": "Test Host"})
    assert result["image_url"], "host asset not found"
    assert result["aspect"] == "16:9", (
        f"expected 16:9 to win over 9:16, got {result['aspect']}"
    )


def test_host_rank_falls_back_to_9x16_when_only_portrait_exists(tmp_path: Path):
    docs = tmp_path
    host_dir = docs / "Files" / "Hosts" / "portrait-only"
    host_dir.mkdir(parents=True)
    (host_dir / "host-9x16.jpg").write_bytes(b"\xff\xd8\xff\xe0" + b"0" * 32)
    (host_dir / "host.json").write_text(json.dumps({
        "name": "Portrait Only",
        "host_image_9x16": "Files/Hosts/portrait-only/host-9x16.jpg",
    }), encoding="utf-8")

    import unittest.mock as um
    with um.patch.object(ns, "_docs_root", return_value=docs):
        result = ns.load_host_asset({"host": "Portrait Only"})
    assert result["aspect"] == "9:16"
