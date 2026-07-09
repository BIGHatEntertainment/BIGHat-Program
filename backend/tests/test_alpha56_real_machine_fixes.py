"""v32.0.0-alpha.56 — the merchant's debug log (bighat-debug 07-09) exposed
FOUR real-machine failures that dev never hit:

  1. `POST /api/native/presentations/build` 400'd on EVERY install:
     `Files/Hosts/` folders are named by EMAIL-SLUG (files_router.host_folder)
     but the wizard passes the user's UUID → `_load_host` never found
     host.json → the hardcoded 17-step pipeline NEVER ran; every show fell
     back to the legacy `import-trivia` path.
  2. `import-trivia` stores round refs under `path` (absolute), but
     `load_round_from_disk` only read `file` → exact-file trust was skipped
     and name-scanning could pick a STALE duplicate .bighat (slug-suffix
     copies) without the embedded cover.
  3. Pre-alpha.55 rounds carry only `cover_image_id`; the upload file
     evaporated with the _MEI temp dir. Fix: boot-time backfill embeds the
     cover INTO each .bighat while a source still exists, and the legacy
     read path SELF-HEALS (writes the inlined cover back to disk).
  4. Tauri ACL blocked `window.confirm` (dialog plugin) so the merchant
     never saw the build-failure dialog (frontend fix + capability).
"""
from __future__ import annotations

import json
import sys
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

_QS = [{"number": i, "question": f"Q{i}?", "answer": f"A{i}"} for i in range(1, 11)]


@pytest.fixture
def docs(tmp_path, monkeypatch):
    root = tmp_path / "docs"
    (root / "Files" / "Trivia" / "REG").mkdir(parents=True)
    monkeypatch.setenv("BIGHAT_FILES_DIR", str(root))
    # Isolate cover lookups from the dev repo's real uploads/assets.
    up = tmp_path / "uploads"
    up.mkdir()
    monkeypatch.setenv("BIGHAT_ROUNDMAKER_UPLOADS", str(up))
    monkeypatch.setattr(ns, "_assets_root", lambda: tmp_path / "no-assets")
    return root


def _write_round(root: Path, fname: str, **extra) -> Path:
    p = root / "Files" / "Trivia" / "REG" / fname
    p.write_text(json.dumps({
        "schema": "bighat-round/v1", "id": extra.pop("id", "r1"),
        "round_type": "REG", "name": extra.pop("name", "Animals_1"),
        "questions": _QS, **extra,
    }), encoding="utf-8")
    return p


# ── Fix 2: `path` key + absolute path honored, beats stale duplicates ──

def test_load_round_honors_absolute_path_key(docs):
    stale = _write_round(docs, "animals-1.bighat", id="old-stale")
    fresh = _write_round(docs, "animals-1-abcd1234.bighat", id="new-fresh",
                         cover_image_data_url="data:image/jpeg;base64,FRESH")
    doc = ns.load_round_from_disk({
        "order": 1, "type": "REG", "name": "animals-1",
        "path": str(fresh),   # wizard/import-trivia shape — no `file` key
    })
    assert doc["id"] == "new-fresh", "exact `path` must win over stale name match"
    assert doc["cover_image_data_url"] == "data:image/jpeg;base64,FRESH"
    assert stale.exists()


def test_load_round_still_falls_back_to_name_scan(docs):
    _write_round(docs, "animals-1.bighat", id="only-one")
    doc = ns.load_round_from_disk({
        "order": 1, "type": "REG", "name": "Animals_1",
        "path": "C:/no/such/machine/path.bighat",
    })
    assert doc is not None and doc["id"] == "only-one"


# ── Fix 3: self-heal on read + boot backfill ──

def test_read_bighat_self_heals_cover_into_file(docs, tmp_path):
    up = Path(json.loads(json.dumps(str(tmp_path / "uploads"))))
    (up / "cov-123.jpg").write_bytes(_TINY_JPEG)
    p = _write_round(docs, "animals-1.bighat", cover_image_id="cov-123")
    doc = ns._read_bighat_round(p)
    assert doc["cover_image_data_url"].startswith("data:image/jpeg;base64,")
    # The embed must now be persisted INSIDE the file...
    on_disk = json.loads(p.read_text(encoding="utf-8"))
    assert on_disk["cover_image_data_url"].startswith("data:image/jpeg;base64,")
    # ...so it survives the source image disappearing.
    (up / "cov-123.jpg").unlink()
    doc2 = ns._read_bighat_round(p)
    assert doc2["cover_image_data_url"].startswith("data:image/jpeg;base64,")


def test_boot_backfill_embeds_covers(docs, tmp_path):
    up = tmp_path / "uploads"
    (up / "cov-777.png").write_bytes(_TINY_JPEG)
    p = _write_round(docs, "history-1.bighat", id="r-hist",
                     name="History_1", cover_image_id="cov-777")
    lost = _write_round(docs, "lost-1.bighat", id="r-lost",
                        name="Lost_1", cover_image_id="gone-forever")
    import routes.roundmaker as rm
    stats = rm.backfill_round_covers()
    assert stats["embedded"] >= 1
    assert stats["missing_source"] >= 1
    healed = json.loads(p.read_text(encoding="utf-8"))
    assert healed["cover_image_data_url"].startswith("data:image/png;base64,")
    untouched = json.loads(lost.read_text(encoding="utf-8"))
    assert "cover_image_data_url" not in untouched
    # Idempotent second run
    stats2 = rm.backfill_round_covers()
    assert stats2["embedded"] == 0


# ── Fix 1: host lookup by id/email across email-slug folders ──

def test_load_host_matches_by_id_and_email(docs, monkeypatch):
    import presentation_builder as pb
    hosts = docs / "Files" / "Hosts" / "sellards-bighat.live"
    hosts.mkdir(parents=True)
    (hosts / "host.json").write_text(json.dumps({
        "id": "aeb9d99a-0d6d-44c1-9c06-0a1b45073e3a",
        "email": "Sellards@bighat.live", "display_name": "Sellards",
    }), encoding="utf-8")
    by_id = pb._load_host("aeb9d99a-0d6d-44c1-9c06-0a1b45073e3a")
    assert by_id["display_name"] == "Sellards"
    by_email = pb._load_host("sellards@bighat.live")
    assert by_email["id"] == "aeb9d99a-0d6d-44c1-9c06-0a1b45073e3a"
    with pytest.raises(pb.BuildValidationError):
        pb._load_host("nope-never-existed")
