"""v32.0.0-alpha.38 regression suite.

Merchant bug on alpha.37:

  When the Trivia Build Wizard confirms a presentation:
    - Nothing landed in `Files/Trivia/Rounds/` on disk.
    - Nothing was recallable in the Presenter tool.

Merchant spec (locked 2026-07-03): the built presentation MUST land as
a single `.bighat` JSON manifest inside
`<Documents>/BIG Hat Entertainment/Files/Trivia/Rounds/`. That JSON
file is the authoritative artefact — the merchant should be able to
back it up / share it / hand-edit it — and the Presenter tool must
read it directly (so a DB wipe never loses shipped presentations).

Fixes locked in by this test suite:

  * `POST /api/presentations/import-trivia` in native mode ALWAYS
    writes a `<slug>.bighat` JSON file to the rounds folder.
  * The disk write is durable — if the DB mirror insert errors, the
    file still exists.
  * `GET /api/presentations?userName=X` also scans that folder and
    surfaces the on-disk file even if the DB row is missing.
"""
from __future__ import annotations
import asyncio
import json
import re
import sys
from pathlib import Path


PRES = Path("/app/backend/routes/presentations.py").read_text()


def test_import_trivia_has_native_branch():
    """The endpoint must short-circuit to a native, disk-first path."""
    idx = PRES.index("async def import_trivia(")
    body = PRES[idx:idx + 2500]
    assert "_import_trivia_native" in body, (
        "import_trivia must delegate to _import_trivia_native in native mode"
    )
    assert "native_mode" in body


def test_native_writer_targets_files_trivia_rounds():
    idx = PRES.index("def _rounds_dir(")
    body = PRES[idx:idx + 600]
    assert '"Files"' in body and '"Trivia"' in body and '"Rounds"' in body


def test_native_writer_actually_writes_bighat_file(tmp_path, monkeypatch):
    """End-to-end: call `_import_trivia_native` → assert a `.bighat`
    JSON file lands on disk with the expected schema."""
    monkeypatch.setenv("BIGHAT_FILES_DIR", str(tmp_path))
    sys.path.insert(0, "/app/backend")

    from models import TriviaImportRequest
    import importlib
    from routes import presentations as pres
    importlib.reload(pres)

    class _Coll:
        def __init__(self):
            self.docs = []
        async def insert_one(self, doc):
            self.docs.append(doc)
        def find(self, q, projection=None):
            docs = list(self.docs)
            class _C:
                async def to_list(self, n): return docs
            return _C()

    class _DB:
        def __init__(self):
            self.presentations = _Coll()
            self.trivia_presentations = _Coll()
    db = _DB()
    pres.db = db

    req = TriviaImportRequest(
        userName="Sellards",
        host="/some/host/Sellards.pptx",
        location="/some/location/Vegas Lounge",
        rounds=[
            "/rounds/MC/mc-01.bighat",
            "/rounds/REG/reg-01.bighat",
            "/rounds/BIG/big-01.bighat",
        ],
        roundTypes=["MC", "REG", "BIG"],
        roundNames=["MC Round 1", "Regular Round 1", "BIG Question"],
        numRounds=3,
        presentationName="Vegas Lounge — Test Night",
    )

    result = asyncio.run(pres._import_trivia_native(req))

    # Result payload
    assert result["name"] == "Vegas Lounge — Test Night"
    assert result["rounds"] == 3
    assert result["disk_path"], "must return the on-disk path"

    disk = Path(result["disk_path"])
    assert disk.exists(), f"expected .bighat at {disk}"
    assert disk.suffix == ".bighat"

    parent = disk.parent
    assert parent.name == "Rounds"
    assert parent.parent.name == "Trivia"
    assert parent.parent.parent.name == "Files"

    # File contents
    payload = json.loads(disk.read_text(encoding="utf-8"))
    assert payload["schema"] == "bighat-presentation/v1"
    assert payload["name"] == "Vegas Lounge — Test Night"
    assert payload["createdBy"] == "Sellards"
    assert len(payload["roundFiles"]) == 3
    assert payload["roundFiles"][0]["type"] == "MC"
    assert payload["roundFiles"][2]["name"] == "BIG Question"

    # DB mirror also succeeded
    assert len(db.trivia_presentations.docs) == 1


def test_get_presentations_scans_disk_when_db_empty(tmp_path, monkeypatch):
    """If a `.bighat` exists on disk but the DB doesn't have a row for
    it (e.g. DB wipe), the Presenter list must still surface it."""
    monkeypatch.setenv("BIGHAT_FILES_DIR", str(tmp_path))
    sys.path.insert(0, "/app/backend")

    import importlib
    from routes import presentations as pres
    importlib.reload(pres)

    # Force is_native to True regardless of BIGHAT_NATIVE_MODE
    monkeypatch.setattr("native.db_factory.is_native", lambda: True)

    class _Coll:
        def __init__(self):
            self.docs = []
        async def insert_one(self, doc):
            self.docs.append(doc)
        def find(self, q, projection=None):
            docs = [d for d in self.docs
                    if all(_matches(d.get(k), v) for k, v in q.items())]
            class _C:
                async def to_list(self, n): return docs
            return _C()

    def _matches(val, cond):
        if isinstance(cond, dict) and "$regex" in cond:
            return bool(re.match(cond["$regex"], val or "", re.IGNORECASE))
        return val == cond

    class _DB:
        def __init__(self):
            self.presentations = _Coll()
            self.trivia_presentations = _Coll()
    db = _DB()
    pres.db = db

    # Manually drop a .bighat manifest on disk without any DB row.
    rounds_dir = tmp_path / "Files" / "Trivia" / "Rounds"
    rounds_dir.mkdir(parents=True)
    (rounds_dir / "orphan.bighat").write_text(json.dumps({
        "schema": "bighat-presentation/v1",
        "id": "orphan-1",
        "name": "Orphan Presentation",
        "createdBy": "Sellards",
        "createdAt": "2026-07-03T00:00:00+00:00",
        "hostFile": "", "locationFile": "",
        "roundFiles": [], "sponsorFiles": [], "totalSlides": 0,
    }), encoding="utf-8")

    result = asyncio.run(pres.get_presentations("Sellards", False))
    assert len(result) == 1, f"expected disk scan to surface orphan, got {result!r}"
    assert result[0]["id"] == "orphan-1"
    assert result[0]["name"] == "Orphan Presentation"


def test_import_then_list_roundtrip(tmp_path, monkeypatch):
    """The wizard flow end-to-end: import → immediately list → the new
    presentation is returned."""
    monkeypatch.setenv("BIGHAT_FILES_DIR", str(tmp_path))
    sys.path.insert(0, "/app/backend")

    from models import TriviaImportRequest
    import importlib
    from routes import presentations as pres
    importlib.reload(pres)

    monkeypatch.setattr("native.db_factory.is_native", lambda: True)

    class _Coll:
        def __init__(self):
            self.docs = []
        async def insert_one(self, doc):
            self.docs.append(doc)
        def find(self, q, projection=None):
            docs = [d for d in self.docs
                    if all(_matches(d.get(k), v) for k, v in q.items())]
            class _C:
                async def to_list(self, n): return docs
            return _C()

    def _matches(val, cond):
        if isinstance(cond, dict) and "$regex" in cond:
            return bool(re.match(cond["$regex"], val or "", re.IGNORECASE))
        return val == cond

    class _DB:
        def __init__(self):
            self.presentations = _Coll()
            self.trivia_presentations = _Coll()
    db = _DB()
    pres.db = db

    req = TriviaImportRequest(
        userName="Sellards",
        host="", location="Test Bar",
        rounds=["r1.bighat"],
        roundTypes=["MC"], roundNames=["MC 1"],
        numRounds=1,
        presentationName="Round-trip Night",
    )
    import_result = asyncio.run(pres._import_trivia_native(req))
    assert Path(import_result["disk_path"]).exists()

    list_result = asyncio.run(pres.get_presentations("Sellards", False))
    names = [p["name"] for p in list_result]
    assert "Round-trip Night" in names, names


def test_no_overwrite_when_same_slug_reused(tmp_path, monkeypatch):
    """Two presentations with the same name must both persist — the
    second gets a unique suffix so the first isn't overwritten."""
    monkeypatch.setenv("BIGHAT_FILES_DIR", str(tmp_path))
    sys.path.insert(0, "/app/backend")

    from models import TriviaImportRequest
    import importlib
    from routes import presentations as pres
    importlib.reload(pres)

    class _Coll:
        def __init__(self): self.docs = []
        async def insert_one(self, doc): self.docs.append(doc)
        def find(self, q, projection=None):
            docs = list(self.docs)
            class _C:
                async def to_list(self, n): return docs
            return _C()

    class _DB:
        def __init__(self):
            self.presentations = _Coll()
            self.trivia_presentations = _Coll()
    db = _DB()
    pres.db = db

    req = TriviaImportRequest(
        userName="Sellards", host="", location="X",
        rounds=["r.bighat"], roundTypes=["MC"], roundNames=["MC"],
        numRounds=1,
        presentationName="Same Name Night",
    )
    r1 = asyncio.run(pres._import_trivia_native(req))
    r2 = asyncio.run(pres._import_trivia_native(req))
    p1, p2 = Path(r1["disk_path"]), Path(r2["disk_path"])
    assert p1 != p2, "second write must not overwrite the first"
    assert p1.exists() and p2.exists()
