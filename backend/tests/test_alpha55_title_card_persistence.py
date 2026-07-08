"""v32.0.0-alpha.55 — title cards must survive app restarts on end-user PCs.

ROOT CAUSE of the recurring "title images are still not being grabbed"
complaint: in PyInstaller-frozen builds, `routes/roundmaker.py`'s
`UPLOAD_DIR = BACKEND_DIR / "roundmaker_uploads"` resolved into the
per-launch `_MEIxxxx` temp dir. Cover images copied there by
`/reg-download-title-image` and `/upload-cover` EVAPORATED when the app
closed. The round-maker *preview* kept working (it reads the original
artwork straight out of the local assets folder), but the presentation
renderer scanned the now-empty uploads dir → slide 0 fell back to text.

Fixes proven here:
  1. `UPLOAD_DIR` honors `BIGHAT_ROUNDMAKER_UPLOADS` (launcher pins it to
     the persistent per-user data dir in frozen mode).
  2. `_write_round_bighat` embeds the cover as `cover_image_data_url`
     inside the .bighat — the file is fully self-contained.
  3. RECOVERY: `_inline_roundmaker_upload` falls back to a stem match in
     the local assets TitleCards tree, resurrecting title cards for
     rounds whose upload copy already evaporated (ALL round types).
  4. ZIP-format .bighat with `cover_image_id` but no bundled asset also
     resolves through the same lookup.
"""
from __future__ import annotations


import json
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import native_slides as ns  # noqa: E402

_TINY_JPEG = bytes.fromhex(
    "ffd8ffe000104a46494600010100000100010000ffdb0043"
    "0008060607060508070707090908080a0c140d0c0b0b0c19"
    "12130f141d1a1f1e1d1a1c1c20242e2720222c231c1c283727"
    "2c30313434341f27393d38323c2e333432ffd9"
)


@pytest.fixture
def empty_uploads(tmp_path, monkeypatch):
    """Simulate the post-restart frozen build: uploads dir exists but is
    EMPTY (the _MEI temp copy evaporated)."""
    up = tmp_path / "uploads"
    up.mkdir()
    monkeypatch.setenv("BIGHAT_ROUNDMAKER_UPLOADS", str(up))
    return up


@pytest.fixture
def title_cards_assets(tmp_path, monkeypatch):
    """Persistent local-assets TitleCards tree with per-type artwork."""
    assets = tmp_path / "assets"
    tc = assets / "01_Trivia" / "Web App" / "00_Builder" / "04_TitleCards"
    for rt, stem in (("REG", "1970s"), ("MC", "mc-vol-3"), ("MISC", "grab-bag"),
                     ("MYS", "mystery-9"), ("BIG", "big-finale")):
        d = tc / rt
        d.mkdir(parents=True)
        (d / f"{stem}.jpg").write_bytes(_TINY_JPEG)
    monkeypatch.setattr(ns, "_assets_root", lambda: assets)
    return assets


def test_upload_dir_honors_env(tmp_path, monkeypatch):
    """UPLOAD_DIR resolution must come from BIGHAT_ROUNDMAKER_UPLOADS
    (this is how frozen builds get a persistent dir)."""
    up = tmp_path / "persistent-uploads"
    gen = tmp_path / "persistent-generated"
    monkeypatch.setenv("BIGHAT_ROUNDMAKER_UPLOADS", str(up))
    monkeypatch.setenv("BIGHAT_ROUNDMAKER_GENERATED", str(gen))
    import routes.roundmaker as rm
    assert rm._resolve_upload_dir() == up
    assert rm._resolve_generated_dir() == gen
    monkeypatch.delenv("BIGHAT_ROUNDMAKER_UPLOADS")
    monkeypatch.delenv("BIGHAT_ROUNDMAKER_GENERATED")
    assert rm._resolve_upload_dir() == rm.BACKEND_DIR / "roundmaker_uploads"
    assert rm._resolve_generated_dir() == rm.BACKEND_DIR / "roundmaker_generated"


@pytest.mark.parametrize("rt,stem", [
    ("REG", "1970s"), ("MC", "mc-vol-3"), ("MISC", "grab-bag"),
    ("MYS", "mystery-9"), ("BIG", "big-finale"),
])
def test_recovery_from_title_cards_assets(empty_uploads, title_cards_assets, rt, stem):
    """Upload copy gone → stem match in TitleCards assets recovers the
    EXACT artwork, for every round type."""
    url = ns._inline_roundmaker_upload(stem)
    assert url is not None, f"{rt} cover {stem!r} must be recovered from assets"
    assert url.startswith("data:image/jpeg;base64,")


def test_uploads_dir_still_wins_over_assets(tmp_path, monkeypatch, title_cards_assets):
    """When the upload copy DOES exist it takes priority (it may be a
    custom crop, not the stock artwork)."""
    up = tmp_path / "uploads"
    up.mkdir()
    custom = _TINY_JPEG + b"custom"
    (up / "1970s.png").write_bytes(custom)
    monkeypatch.setenv("BIGHAT_ROUNDMAKER_UPLOADS", str(up))
    url = ns._inline_roundmaker_upload("1970s")
    assert url.startswith("data:image/png;base64,")


def test_missing_everywhere_returns_none(empty_uploads, title_cards_assets):
    assert ns._inline_roundmaker_upload("does-not-exist") is None


def test_traversal_rejected(empty_uploads, title_cards_assets):
    assert ns._inline_roundmaker_upload("../1970s") is None
    assert ns._inline_roundmaker_upload("REG/1970s") is None


def test_legacy_json_round_recovers_cover(tmp_path, empty_uploads, title_cards_assets):
    """End-to-end: legacy bare-JSON .bighat + evaporated uploads → slide 0
    still gets the full-bleed cover from the assets fallback."""
    f = tmp_path / "seventies.bighat"
    f.write_text(json.dumps({
        "schema": "bighat-round/v1", "id": "r-70s", "round_type": "REG",
        "name": "1970s_4", "cover_image_id": "1970s",
        "questions": [{"number": i, "question": f"Q{i}?", "answer": f"A{i}"}
                      for i in range(1, 11)],
    }), encoding="utf-8")
    doc = ns._read_bighat_round(f)
    assert doc["cover_image_data_url"].startswith("data:image/jpeg;base64,")

    slides = ns.render_round_section(doc, {"type": "REG", "name": "1970s_4", "order": 2})
    title = slides[0]
    md = title["metadata"]
    assert md["isTitleCard"] is True
    assert md["_title_card_source"] == "bighat-embedded-cover"
    img = title["elements"][0]
    assert img["type"] == "image"
    assert img["src"].startswith("data:image/jpeg;base64,")
    assert (img["width"], img["height"]) == (1920, 1080)


def test_zip_bighat_with_cover_image_id_only(tmp_path, empty_uploads, title_cards_assets):
    """ZIP .bighat that references a cover by id (no bundled asset) resolves
    through the same lookup."""
    f = tmp_path / "mystery.bighat"
    with zipfile.ZipFile(f, "w") as zf:
        zf.writestr("manifest.json", json.dumps({"format_version": 1}))
        zf.writestr("payload.json", json.dumps({
            "name": "Mystery 9", "round_type": "MYS",
            "cover_image_id": "mystery-9",
            "questions": [{"n": i, "prompt": f"Q{i}?", "answer": f"A{i}"}
                          for i in range(1, 10)],
        }))
    doc = ns._read_bighat_round(f)
    assert doc is not None
    assert (doc.get("cover_image_data_url") or "").startswith("data:image/jpeg;base64,")


def test_write_round_bighat_embeds_cover(tmp_path, monkeypatch, title_cards_assets):
    """_write_round_bighat must persist cover_image_data_url INSIDE the
    .bighat so the file is self-contained forever."""
    up = tmp_path / "uploads"
    up.mkdir()
    (up / "abc-uuid.jpg").write_bytes(_TINY_JPEG)
    monkeypatch.setenv("BIGHAT_ROUNDMAKER_UPLOADS", str(up))
    monkeypatch.setenv("BIGHAT_FILES_DIR", str(tmp_path / "docs"))

    import routes.roundmaker as rm
    path = rm._write_round_bighat({
        "id": "r-embed", "round_type": "MC", "name": "MC_01_A",
        "questions": [], "cover_image_id": "abc-uuid",
    })
    assert path is not None
    saved = json.loads(Path(path).read_text(encoding="utf-8"))
    assert saved["cover_image_id"] == "abc-uuid"
    assert saved["cover_image_data_url"].startswith("data:image/jpeg;base64,")

    # And the renderer prefers the embedded copy even with uploads gone.
    for e in up.iterdir():
        e.unlink()
    doc = ns._read_bighat_round(Path(path))
    assert doc["cover_image_data_url"].startswith("data:image/jpeg;base64,")
