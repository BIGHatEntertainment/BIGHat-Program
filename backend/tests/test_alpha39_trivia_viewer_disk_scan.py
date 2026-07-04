"""v32.0.0-alpha.39 regression suite.

Merchant follow-up on alpha.38:

  alpha.38 wrote the `.bighat` file to disk successfully, but the
  Trivia Presenter dashboard still showed "No trivia presentations
  found" because the dashboard hits `GET /api/trivia-viewer/list`,
  NOT `GET /api/presentations`. The disk scan I added in alpha.38
  only patched `presentations.py`; `trivia_viewer.py` was untouched.

  This is a P0 blocker on the desktop app — the merchant can build
  a presentation but can't play it.

Fixes locked in by this test:

  * `GET /api/trivia-viewer/list` now also scans
    `<Documents>/BIG Hat Entertainment/Files/Trivia/Rounds/*.bighat`
    and merges those entries into the returned list.
  * `GET /api/trivia-viewer/{id}` falls back to reading the manifest
    off disk when the DB row is missing.
"""
from __future__ import annotations
import asyncio
import json
import sys
from pathlib import Path


TV = Path("/app/backend/routes/trivia_viewer.py").read_text()


def test_trivia_viewer_list_reads_disk():
    idx = TV.index("async def list_trivia_presentations(")
    end = TV.index("@router.get(", idx + 1)
    body = TV[idx:end]
    assert "Files" in body and "Trivia" in body and "Rounds" in body, (
        "list_trivia_presentations must scan Files/Trivia/Rounds/ on disk"
    )
    assert ".bighat" in body
    assert "_docs_root" in body


def test_trivia_viewer_getter_reads_disk_fallback():
    idx = TV.index("async def get_trivia_presentation(")
    end = TV.index("@router.get(", idx + 1)
    body = TV[idx:end]
    assert ".bighat" in body, (
        "get_trivia_presentation must fall back to disk when DB row missing"
    )


def test_end_to_end_wizard_writes_then_presenter_lists(tmp_path, monkeypatch):
    """Real end-to-end: wizard writes a .bighat → presenter list surfaces it
    even when the DB row was never written (mimicking pymongo swap failure)."""
    monkeypatch.setenv("BIGHAT_FILES_DIR", str(tmp_path))
    sys.path.insert(0, "/app/backend")

    import importlib
    from routes import presentations as pres
    from routes import trivia_viewer as tv
    importlib.reload(pres)
    importlib.reload(tv)

    class _Coll:
        def __init__(self, name):
            self.name = name
            self.docs = []
        async def insert_one(self, doc):
            self.docs.append(doc)
        def find(self, q=None):
            if q is None:
                q = {}
            docs = list(self.docs)
            class _C:
                def sort(self, k, d): return self
                async def to_list(self, n): return docs
            return _C()
        async def find_one(self, q):
            for d in self.docs:
                if all(d.get(k) == v for k, v in q.items()):
                    return d
            return None

    class _DB:
        def __init__(self):
            self.presentations = _Coll("presentations")
            self.trivia_presentations = _Coll("trivia_presentations")
            self.users = _Coll("users")
            self.employees = _Coll("employees")

    db = _DB()
    pres.db = db
    tv.db = db

    from models import TriviaImportRequest
    req = TriviaImportRequest(
        userName="Sellards", host="", location="Monkey Pants Bar Grill",
        rounds=["MC/mc-01-a.bighat", "REG/1980s-1.bighat", "MISC/arizona-1.bighat",
                "MYS/mystery-apples.bighat", "BIG/big-cactus-league-easy.bighat"],
        roundTypes=["MC", "REG", "MISC", "MYS", "BIG"],
        roundNames=["mc-01-a", "1980s-1", "arizona-1", "mystery-apples", "big-cactus-league-easy"],
        numRounds=5,
        presentationName="Monkey Pants Bar Grill - 7/4",
    )

    import_result = asyncio.run(pres._import_trivia_native(req))
    assert Path(import_result["disk_path"]).exists()

    # Now simulate DB wipe — clear the trivia_presentations collection
    db.trivia_presentations.docs.clear()

    # Presenter dashboard hits trivia-viewer/list with viewAll=True (admin)
    listed = asyncio.run(tv.list_trivia_presentations(
        userName="sellards", viewAll=True, hostName="Sellards"
    ))
    assert len(listed) >= 1, f"Presenter must surface the on-disk .bighat: got {listed!r}"
    entry = next((p for p in listed if p.get("name") == "Monkey Pants Bar Grill - 7/4"), None)
    assert entry is not None, f"Missing wizard-built entry: {[p.get('name') for p in listed]}"
    # Check the shape the frontend expects
    assert entry.get("roundTypes") == ["MC", "REG", "MISC", "MYS", "BIG"]
    assert entry.get("numRounds") == 5


def test_trivia_viewer_getter_disk_fallback_e2e(tmp_path, monkeypatch):
    """Clicking a presentation → getter reads it off disk."""
    monkeypatch.setenv("BIGHAT_FILES_DIR", str(tmp_path))
    sys.path.insert(0, "/app/backend")

    import importlib
    from routes import trivia_viewer as tv
    importlib.reload(tv)

    class _Coll:
        def __init__(self): self.docs = []
        async def find_one(self, q): return None
        def find(self, q=None):
            class _C:
                def sort(self, k, d): return self
                async def to_list(self, n): return []
            return _C()

    class _DB:
        def __init__(self):
            self.trivia_presentations = _Coll()
            self.presentations = _Coll()
    tv.db = _DB()

    rounds_dir = tmp_path / "Files" / "Trivia" / "Rounds"
    rounds_dir.mkdir(parents=True)
    manifest = {
        "schema": "bighat-presentation/v1",
        "id": "disk-only-123",
        "name": "Disk Only Night",
        "createdBy": "Sellards",
        "host": "Sellards",
        "location": "Test Bar",
        "totalSlides": 60,
        "numRounds": 5,
        "roundTypes": ["MC","REG","MISC","MYS","BIG"],
        "roundNames": ["a","b","c","d","e"],
        "roundFiles": [],
        "hostFile": "",
        "locationFile": "",
    }
    (rounds_dir / "disk-only-night.bighat").write_text(json.dumps(manifest), encoding="utf-8")

    result = asyncio.run(tv.get_trivia_presentation("disk-only-123"))
    assert result["id"] == "disk-only-123"
    assert result["name"] == "Disk Only Night"
    assert result["numRounds"] == 5
    assert result["roundTypes"] == ["MC","REG","MISC","MYS","BIG"]
