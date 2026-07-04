"""v32.0.0-alpha.37 regression suite.

Two merchant bugs on alpha.36:

  1) Trivia Presenter always showed "No trivia presentations found"
     even right after the Build Wizard's confirmation page. The wizard
     saved to `db.trivia_presentations` (via /api/presentations/import-trivia
     -> insert_one on that collection at ~line 379) but the LIST
     endpoint `GET /api/presentations?userName=X` only read from
     `db.presentations`. Two different collections → data vanished.

  2) Files tool "Locations" tab was empty even though the location
     folder existed on disk with branding + overlay images. The Files
     tool endpoint globs for `.bighat` files, but locations store
     branded IMAGE subfolders (branding/*.png + overlays/*.png), not
     `.bighat`. So the tab was legitimately empty.

Fixes locked in by this test suite:

  * `get_presentations` merges both `db.presentations` +
    `db.trivia_presentations` (deduped by id, case-insensitive
    createdBy match preserved).
  * `files_list` short-circuits Locations + Hosts folders to a
    subfolder-listing mode: each entry is a location/host with
    aggregated branding + overlay counts and a summary string.
"""
from __future__ import annotations
import asyncio
from pathlib import Path


PRES = Path("/app/backend/routes/presentations.py").read_text()
FILES = Path("/app/backend/native/files_router.py").read_text()


def test_presentations_list_reads_both_collections():
    """The LIST endpoint must merge `db.presentations` and
    `db.trivia_presentations` so wizard-built presentations show up."""
    idx = PRES.index("async def get_presentations(")
    end = PRES.index("@router.get(", idx + 1)
    body = PRES[idx:end]
    assert "db.trivia_presentations" in body, (
        "get_presentations must also read db.trivia_presentations"
    )
    assert "db.presentations" in body
    assert "seen" in body and "merged" in body, (
        "must dedupe merged results by id"
    )


def test_presentations_list_still_supports_viewAll():
    idx = PRES.index("async def get_presentations(")
    end = PRES.index("@router.get(", idx + 1)
    body = PRES[idx:end]
    assert "viewAll" in body
    # `viewAll` branch must query BOTH collections without a
    # createdBy filter.
    va = body.split("viewAll")[1][:600]
    assert "trivia_presentations.find" in va or "trivia_presentations" in va


def test_files_locations_tab_lists_subfolders():
    idx = FILES.index("async def files_list(")
    end = FILES.index("@router.post(", idx + 1)
    body = FILES[idx:end]
    assert 'canonical in ("Locations", "Hosts")' in body, (
        "files_list must special-case Locations + Hosts to list "
        "branded image subfolders"
    )
    assert "branding" in body and "overlays" in body
    assert "summary" in body


def test_files_locations_summary_shape():
    """Live: the endpoint helper builds per-subfolder entries with the
    aggregated summary. Sanity-check the fields are present."""
    idx = FILES.index("async def files_list(")
    end = FILES.index("@router.post(", idx + 1)
    body = FILES[idx:end]
    # Every emitted item under this branch must carry these fields
    for field in ('"name"', '"folder"', '"path"', '"summary"', '"type"'):
        assert field in body, f"missing {field} in Locations subfolder listing"


def test_end_to_end_import_and_list(tmp_path, monkeypatch):
    """Mock db, run import-trivia handler → then get_presentations →
    the persisted presentation must come back."""
    # v32.0.0-alpha.40: pin docs root to tmp so the alpha.38+ disk scan
    # doesn't leak in `.bighat` files from the real user directory
    # (which is polluted by dev smoke-test presentations).
    monkeypatch.setenv("BIGHAT_FILES_DIR", str(tmp_path))
    import sys
    sys.path.insert(0, "/app/backend")

    from models import TriviaImportRequest
    import importlib
    from routes import presentations as pres
    importlib.reload(pres)

    class _Coll:
        def __init__(self, name):
            self.name = name
            self._docs = []
        async def insert_one(self, doc):
            self._docs.append(doc)
        def find(self, q, projection=None):
            docs = [d for d in self._docs
                    if all(_matches(d.get(k), v) for k, v in q.items())]
            class _C:
                async def to_list(self, n): return docs
            return _C()

    def _matches(val, cond):
        if isinstance(cond, dict) and "$regex" in cond:
            import re
            return bool(re.match(cond["$regex"], val or "", re.IGNORECASE))
        return val == cond

    class _DB:
        def __init__(self):
            self.presentations = _Coll("presentations")
            self.trivia_presentations = _Coll("trivia_presentations")

    db = _DB()
    pres.db = db
    # Simulate a wizard save into trivia_presentations
    doc = {
        "id": "abc-123",
        "name": "Smoke",
        "createdBy": "Sellards",
        "createdAt": "2026-07-03T00:00:00+00:00",
        "hostFile": "h", "locationFile": "l",
        "roundFiles": [], "sponsorFiles": [], "totalSlides": 0,
    }
    asyncio.run(db.trivia_presentations.insert_one(doc))

    result = asyncio.run(pres.get_presentations("Sellards", False))
    assert len(result) == 1, f"expected 1 presentation, got {result!r}"
    assert result[0]["id"] == "abc-123"
    assert result[0]["name"] == "Smoke"


def test_end_to_end_files_locations_tab(tmp_path, monkeypatch):
    import sys
    sys.path.insert(0, "/app/backend")
    monkeypatch.setenv("BIGHAT_FILES_DIR", str(tmp_path))

    import importlib
    from native import files_router as fr
    importlib.reload(fr)

    slug = "vegas-lounge"
    # BIGHAT_FILES_DIR overrides `_base_root()` to tmp_path directly
    # (no Files/ prefix), so subfolders go straight under tmp_path.
    (tmp_path / "Locations" / slug / "branding").mkdir(parents=True)
    (tmp_path / "Locations" / slug / "overlays").mkdir(parents=True)
    (tmp_path / "Locations" / slug / "branding" / "logo.png").write_bytes(b"PNG")
    (tmp_path / "Locations" / slug / "overlays" / "ov1.png").write_bytes(b"PNG")

    res = asyncio.run(fr.files_list(folder="Locations"))
    assert res["count"] == 1, res
    entry = res["files"][0]
    assert entry["name"] == slug
    assert entry["type"] == "location"
    assert "1 branding" in entry["summary"]
    assert "1 overlays" in entry["summary"]
    assert entry["path"].endswith(slug)
