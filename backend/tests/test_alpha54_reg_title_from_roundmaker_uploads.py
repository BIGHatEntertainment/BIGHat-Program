"""v32.0.0-alpha.54 — REG round title card MUST come from the round-maker's
`cover_image_id` upload.

Merchant charge (2026-02-06, hard-stop):
> "the title images are still not being grabbed and loaded into the
>  presentations. i know they are there because they show up in the
>  round generators preview area. that image is the title card for
>  that round so when that round is used in a presentation that same
>  exact image in that rounds preview better in that rounds title
>  card slide"

Root cause:
The round-generator writes bare-JSON `.bighat` files with `cover_image_id`
pointing to a UUID stem in `backend/roundmaker_uploads/`. The presentation
renderer was never reading that folder, so slide 0 fell through to the
"REGULAR ROUND" text placeholder.

Fix:
`native_slides._inline_roundmaker_upload(cover_image_id)` looks up the
matching file (any of .jpg/.jpeg/.png/.gif/.webp) in the round-maker's
upload dir, base64-encodes it as a `data:` URL, and returns it. The
bare-JSON branch of `_read_bighat_round` now writes that URL into
`cover_image_data_url`, which slide 0 was already programmed to prefer.

This test proves that:
  1. Given a bare-JSON `.bighat` with a valid `cover_image_id`,
     `_read_bighat_round` inlines the upload.
  2. Slide 0 of the rendered round carries that data URL as a
     full-bleed 1920x1080 image element (NOT the text placeholder).
  3. `_title_card_source` metadata is stamped `bighat-embedded-cover`.
  4. Missing / broken cover_image_id falls back gracefully.
  5. Path-traversal attempts on the cover_image_id are rejected.
"""
from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import native_slides as ns  # noqa: E402


# Minimal valid JPEG bytes (SOI + APP0 + EOI) — enough for `read_bytes()`
# to succeed and the mime sniff to work.
_TINY_JPEG = bytes.fromhex(
    "ffd8ffe000104a46494600010100000100010000ffdb0043"
    "0008060607060508070707090908080a0c140d0c0b0b0c19"
    "12130f141d1a1f1e1d1a1c1c20242e2720222c231c1c283727"
    "2c30313434341f27393d38323c2e333432ffd9"
)


@pytest.fixture
def roundmaker_uploads(tmp_path, monkeypatch):
    """Point `_inline_roundmaker_upload` at a fake `roundmaker_uploads/`
    directory populated with one real image file."""
    upload_dir = tmp_path / "roundmaker_uploads"
    upload_dir.mkdir()
    # Real-user shape: <uuid>.jpg
    cover_uuid = "75fc7283-26a4-4e21-87a3-5fa00a028d92"
    (upload_dir / f"{cover_uuid}.jpg").write_bytes(_TINY_JPEG)
    monkeypatch.setenv("BIGHAT_ROUNDMAKER_UPLOADS", str(upload_dir))
    return {"dir": upload_dir, "uuid": cover_uuid}


# ---------------------------------------------------------------------------
# 1. `_inline_roundmaker_upload` finds the image and returns a data URL
# ---------------------------------------------------------------------------

def test_inline_roundmaker_upload_returns_jpeg_data_url(roundmaker_uploads):
    url = ns._inline_roundmaker_upload(roundmaker_uploads["uuid"])
    assert url is not None
    assert url.startswith("data:image/jpeg;base64,")
    # Round-trip the payload
    payload = url.split(",", 1)[1]
    decoded = base64.b64decode(payload)
    assert decoded == _TINY_JPEG


def test_inline_returns_none_for_unknown_uuid(roundmaker_uploads):
    assert ns._inline_roundmaker_upload("00000000-0000-0000-0000-000000000000") is None


def test_inline_rejects_path_traversal(roundmaker_uploads):
    """A malicious cover_image_id MUST NOT be able to read outside
    the uploads folder."""
    for bad in ("../etc/passwd", "..\\..\\Windows\\System32", "foo/../bar",
                "sub\\dir\\file"):
        assert ns._inline_roundmaker_upload(bad) is None


def test_inline_supports_multiple_extensions(tmp_path, monkeypatch):
    up = tmp_path / "roundmaker_uploads"
    up.mkdir()
    monkeypatch.setenv("BIGHAT_ROUNDMAKER_UPLOADS", str(up))
    # PNG magic bytes
    png = bytes.fromhex("89504e470d0a1a0a") + b"\x00" * 32
    (up / "abc.png").write_bytes(png)
    (up / "def.gif").write_bytes(b"GIF89a" + b"\x00" * 32)
    (up / "ghi.webp").write_bytes(b"RIFF" + b"\x00" * 32 + b"WEBP")

    assert (ns._inline_roundmaker_upload("abc") or "").startswith("data:image/png;")
    assert (ns._inline_roundmaker_upload("def") or "").startswith("data:image/gif;")
    assert (ns._inline_roundmaker_upload("ghi") or "").startswith("data:image/webp;")


# ---------------------------------------------------------------------------
# 2. `_read_bighat_round` inlines the cover on bare-JSON .bighat files
# ---------------------------------------------------------------------------

def test_bare_json_bighat_with_cover_image_id_gets_data_url(
    tmp_path, roundmaker_uploads,
):
    """This is THE regression the merchant is complaining about.
    A bare-JSON .bighat file written by the round-maker points to
    `cover_image_id: <uuid>`; the presentation renderer MUST inline
    that file so slide 0 shows the exact image the round-generator
    preview showed."""
    bighat = tmp_path / "animals-1.bighat"
    bighat.write_text(json.dumps({
        "id": "reg-animals-1",
        "round_type": "REG",
        "name": "Animals_1",
        "cover_image_id": roundmaker_uploads["uuid"],
        "questions": [
            {"number": i, "question": f"Q{i}?", "answer": "A"}
            for i in range(1, 11)
        ],
    }))
    doc = ns._read_bighat_round(bighat)
    assert doc is not None
    assert doc["cover_image_data_url"].startswith("data:image/jpeg;base64,")
    assert doc["_title_card_source_hint"] == "roundmaker-upload"


def test_bare_json_bighat_without_matching_upload_returns_no_url(tmp_path, monkeypatch):
    monkeypatch.setenv("BIGHAT_ROUNDMAKER_UPLOADS", str(tmp_path / "empty"))
    (tmp_path / "empty").mkdir()
    bighat = tmp_path / "bad-cover.bighat"
    bighat.write_text(json.dumps({
        "id": "r1", "round_type": "REG", "name": "Nope",
        "cover_image_id": "0000deadbeef0000deadbeef",  # id that exists NOWHERE on disk
        "questions": [{"number": 1, "question": "Q?", "answer": "A"}],
    }))
    doc = ns._read_bighat_round(bighat)
    assert doc is not None
    assert not doc.get("cover_image_data_url")


# ---------------------------------------------------------------------------
# 3. Slide 0 of the rendered round IS the inlined image, NOT text
# ---------------------------------------------------------------------------

def test_reg_slide0_is_the_roundmaker_uploaded_image(tmp_path, roundmaker_uploads):
    bighat = tmp_path / "pop-culture-1.bighat"
    bighat.write_text(json.dumps({
        "id": "reg-pop-culture-1", "round_type": "REG", "name": "Pop-Culture_1",
        "cover_image_id": roundmaker_uploads["uuid"],
        "questions": [
            {"number": i, "question": f"Q{i}?", "answer": "A"}
            for i in range(1, 11)
        ],
    }))
    doc = ns._read_bighat_round(bighat)
    slides = ns.render_round_section(
        doc, {"type": "REG", "name": doc["name"], "order": 2},
    )
    title = slides[0]
    md = title["metadata"]
    imgs = [e for e in title["elements"] if e["type"] == "image"]

    # Slide 0 is a title card
    assert md.get("isRoundTitle") is True
    assert md.get("isTitleCard") is True

    # The title-card source MUST be the embedded cover (from the upload
    # inline), NOT a "text-fallback-no-image" placeholder.
    assert md.get("_title_card_source") == "bighat-embedded-cover", (
        f"Expected slide 0 title card to be the roundmaker upload. "
        f"Got _title_card_source={md.get('_title_card_source')!r}"
    )

    # And the image element MUST be a data: URL sized to full-bleed 1920x1080
    assert len(imgs) >= 1
    assert imgs[0]["src"].startswith("data:image/"), imgs[0]["src"][:60]
    assert imgs[0]["width"] == 1920
    assert imgs[0]["height"] == 1080

    # Belt-and-suspenders: there must be NO "REGULAR ROUND" text element
    # on the title slide (the placeholder the merchant hates).
    texts = [(e.get("content") or "").upper() for e in title["elements"]
             if e["type"] == "text"]
    assert "REGULAR" not in " ".join(texts), (
        f"Slide 0 must NOT show 'REGULAR ROUND' text placeholder; got: {texts}"
    )
