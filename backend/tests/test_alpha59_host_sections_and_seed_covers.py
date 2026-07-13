"""v32.0.0-alpha.59 — build-doc host/location sections + bundled cover library.

Merchant reports on alpha.58:
  1. title cards still empty on his PC → his cover bytes live in the round
     GENERATOR tool's uploads library (he sent the source zip). We now ship
     that library as `backend/seed_covers/` and copy it into the persistent
     uploads dir on first boot (never overwriting) so cover_image_id lookups
     + boot backfill resolve to REAL bytes.
  2. host slides didn't populate → schema-v2 build docs carry
     host_name/host_id but the section gates read host/hostName, so the
     HOST (and LOCATION) sections were silently dropped. `_normalize_v2_pres`
     coalesces; `load_host_asset` also matches host_id/email/display_name.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import native_slides as ns  # noqa: E402
from routes.slide_fetcher import _normalize_v2_pres  # noqa: E402

_TINY_JPEG = bytes.fromhex(
    "ffd8ffe000104a46494600010100000100010000ffdb0043"
    "0008060607060508070707090908080a0c140d0c0b0b0c19"
    "12130f141d1a1f1e1d1a1c1c20242e2720222c231c1c283727"
    "2c30313434341f27393d38323c2e333432ffd9"
)


def test_normalize_v2_maps_builder_keys():
    pres = {"host_name": "Sellards", "host_id": "uuid-1",
            "location_name": "Monkey Pants", "round_count": 5}
    out = _normalize_v2_pres(pres)
    assert out["host"] == "Sellards"
    assert out["hostId"] == "uuid-1"
    assert out["location"] == "Monkey Pants"
    assert out["numRounds"] == 5


def test_normalize_v2_never_clobbers_legacy_keys():
    pres = {"host": "Legacy Guy", "host_name": "Other", "location": "L1",
            "location_name": "L2", "numRounds": 3, "round_count": 6}
    out = _normalize_v2_pres(pres)
    assert out["host"] == "Legacy Guy"
    assert out["location"] == "L1"
    assert out["numRounds"] == 3


def test_load_host_asset_matches_by_display_name_and_id(tmp_path, monkeypatch):
    docs = tmp_path / "docs"
    hostdir = docs / "Files" / "Hosts" / "sellards@bighat.live"
    hostdir.mkdir(parents=True)
    (hostdir / "host.json").write_text(json.dumps({
        "id": "uuid-abc", "email": "Sellards@bighat.live",
        "display_name": "Sellards",
    }), encoding="utf-8")
    (hostdir / "host-16x9.jpg").write_bytes(_TINY_JPEG)
    monkeypatch.setenv("BIGHAT_FILES_DIR", str(docs))

    # v2 build doc: host_name = display_name (folder is email-slug) → scan match
    a = ns.load_host_asset(_normalize_v2_pres({"host_name": "Sellards"}))
    assert a and a.get("image_url"), "display_name scan must find the host asset"
    # match by host_id
    b = ns.load_host_asset(_normalize_v2_pres({"host_name": "Nope", "host_id": "uuid-abc"}))
    assert b and b.get("image_url"), "host_id scan must find the host asset"
    # total miss
    c = ns.load_host_asset({"host": "Stranger"})
    assert not (c and c.get("image_url"))


def test_seed_covers_shipped_and_real():
    seed = Path(__file__).resolve().parents[1] / "seed_covers"
    files = sorted(p for p in seed.iterdir() if p.is_file())
    assert len(files) >= 6, "generator cover library must ship"
    for p in files:
        assert p.stat().st_size > 1000, f"{p.name} is a placeholder, not real bytes"
    stems = {p.stem for p in files}
    assert {"1960s", "1970s", "1980s", "Music", "Sports"} <= stems


def test_launcher_seeds_covers_without_overwriting(tmp_path, monkeypatch):
    import launcher
    dest = tmp_path / "uploads"
    dest.mkdir()
    (dest / "1970s.jpg").write_bytes(b"user-custom")
    monkeypatch.setenv("BIGHAT_ROUNDMAKER_UPLOADS", str(dest))
    launcher._seed_bundled_covers()
    assert (dest / "1970s.jpg").read_bytes() == b"user-custom", "never overwrite"
    seed_count = len([p for p in (Path(launcher.BACKEND_DIR) / "seed_covers").iterdir() if p.is_file()])
    assert len(list(dest.iterdir())) == seed_count  # 1 kept + rest seeded


def test_seeded_cover_resolves_round_cover(tmp_path, monkeypatch):
    """End-to-end: seeded library + legacy round referencing '1970s' →
    renderer inlines the REAL seeded image."""
    import launcher
    up = tmp_path / "uploads"
    monkeypatch.setenv("BIGHAT_ROUNDMAKER_UPLOADS", str(up))
    monkeypatch.setattr(ns, "_assets_root", lambda: tmp_path / "no-assets")
    monkeypatch.setenv("BIGHAT_FILES_DIR", str(tmp_path / "docs"))
    launcher._seed_bundled_covers()
    url = ns._inline_roundmaker_upload("1970s")
    assert url and url.startswith("data:image/jpeg;base64,")
    assert len(url) > 10000, "must be the real artwork, not a stub"
