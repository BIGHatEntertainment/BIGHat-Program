"""v32.0.0-alpha.40 regression suite — Path A (disk-first rounds + native playback).

Locks in three feature groups:

  * Round Maker writes `.bighat` files to `Files/Trivia/<TYPE>/` on
    create/duplicate/generate/delete. Delete removes the file.
  * `list_rounds` merges disk + db (disk-only rounds surface).
  * The boot migration reconciles DB ↔ disk without dupes.
  * `GET /api/trivia-viewer/{id}/slides` in native mode assembles a
    canonical slide list from the manifest + round `.bighat` files:
      host → location → rounds (cover + Q + review + answers) →
      sponsor-before-BIG → final_scores.
"""
from __future__ import annotations
import asyncio
import json
import sys
from pathlib import Path


ROUND_SRC = Path("/app/backend/routes/roundmaker.py").read_text()
TV_SRC = Path("/app/backend/routes/trivia_viewer.py").read_text()


# ────────────────────────── static assertions ──────────────────────────

def test_roundmaker_has_write_bighat_helper():
    assert "_write_round_bighat" in ROUND_SRC
    assert "_delete_round_bighat" in ROUND_SRC
    assert "migrate_rounds_disk_and_db" in ROUND_SRC
    assert "_read_all_disk_rounds" in ROUND_SRC


def test_create_round_writes_disk():
    idx = ROUND_SRC.index("async def create_round(")
    body = ROUND_SRC[idx:idx + 1500]
    assert "_write_round_bighat" in body


def test_delete_round_wipes_disk():
    idx = ROUND_SRC.index("async def delete_round(")
    body = ROUND_SRC[idx:idx + 700]
    assert "_delete_round_bighat" in body


def test_duplicate_round_writes_disk():
    idx = ROUND_SRC.index("async def duplicate_round(")
    body = ROUND_SRC[idx:idx + 1500]
    assert "_write_round_bighat" in body


def test_trivia_viewer_has_native_assembler():
    assert "_assemble_slides_native" in TV_SRC
    assert "_slides_for_round" in TV_SRC
    assert "_slide_host" in TV_SRC
    assert "_slide_location" in TV_SRC
    assert "_slide_sponsor" in TV_SRC
    assert "_slide_final" in TV_SRC
    assert "_lookup_round" in TV_SRC


# ────────────────────────── functional tests ──────────────────────────

def _reload(monkeypatch, tmp_path):
    """Force _docs_root to point at tmp for hermetic tests."""
    monkeypatch.setenv("BIGHAT_FILES_DIR", str(tmp_path))
    sys.path.insert(0, "/app/backend")
    import importlib
    from routes import roundmaker as rm
    from routes import trivia_viewer as tv
    from routes import presentations as pres
    importlib.reload(rm)
    importlib.reload(tv)
    importlib.reload(pres)
    return rm, tv, pres


class _Coll:
    def __init__(self):
        self.docs = []
    async def insert_one(self, doc):
        self.docs.append(doc)
    async def find_one(self, q, projection=None):
        for d in self.docs:
            if all(d.get(k) == v for k, v in q.items()):
                return d
        return None
    async def update_one(self, q, upd):
        target = None
        for d in self.docs:
            if all(d.get(k) == v for k, v in q.items()):
                target = d
                break
        if target and "$set" in upd:
            target.update(upd["$set"])
    async def delete_one(self, q):
        for i, d in enumerate(self.docs):
            if all(d.get(k) == v for k, v in q.items()):
                del self.docs[i]
                class _R: deleted_count = 1
                return _R()
        class _R: deleted_count = 0
        return _R()
    def find(self, q=None, projection=None):
        docs = list(self.docs)
        class _C:
            def sort(self, k, d): return self
            async def to_list(self, n): return docs
        return _C()


class _DB:
    def __init__(self):
        self.rounds = _Coll()
        self.presentations = _Coll()
        self.trivia_presentations = _Coll()


def test_create_round_lands_on_disk(tmp_path, monkeypatch):
    rm, _tv, _pres = _reload(monkeypatch, tmp_path)
    rm.db = _DB()

    req = rm.RoundCreate(
        round_type="MC",
        name="Alpha40 Test Round",
        questions=[
            rm.QuestionItem(number=1, question="What TV show?", answer="Cheers"),
            rm.QuestionItem(number=2, question="What year?", answer="1985"),
        ],
    )
    result = asyncio.run(rm.create_round(req))
    disk_path = tmp_path / "Files" / "Trivia" / "MC" / "alpha40-test-round.bighat"
    assert disk_path.exists(), f"expected {disk_path}"
    payload = json.loads(disk_path.read_text())
    assert payload["schema"] == "bighat-round/v1"
    assert payload["name"] == "Alpha40 Test Round"
    assert payload["id"] == result.id
    assert len(payload["questions"]) == 2


def test_two_rounds_same_name_get_unique_files(tmp_path, monkeypatch):
    rm, _tv, _pres = _reload(monkeypatch, tmp_path)
    rm.db = _DB()

    for _ in range(2):
        req = rm.RoundCreate(round_type="REG", name="Same Name",
                             questions=[rm.QuestionItem(number=1, question="q", answer="a")])
        asyncio.run(rm.create_round(req))

    reg = tmp_path / "Files" / "Trivia" / "REG"
    files = list(reg.glob("*.bighat"))
    assert len(files) == 2, f"expected 2 files, got {[f.name for f in files]}"


def test_delete_round_removes_disk(tmp_path, monkeypatch):
    rm, _tv, _pres = _reload(monkeypatch, tmp_path)
    rm.db = _DB()

    req = rm.RoundCreate(round_type="MC", name="Deletable",
                         questions=[rm.QuestionItem(number=1, question="q", answer="a")])
    created = asyncio.run(rm.create_round(req))
    disk_path = tmp_path / "Files" / "Trivia" / "MC" / "deletable.bighat"
    assert disk_path.exists()

    asyncio.run(rm.delete_round(created.id))
    assert not disk_path.exists()


def test_list_rounds_merges_disk_only(tmp_path, monkeypatch):
    """A `.bighat` on disk with no matching DB row surfaces in list."""
    rm, _tv, _pres = _reload(monkeypatch, tmp_path)
    rm.db = _DB()

    d = tmp_path / "Files" / "Trivia" / "MYS"
    d.mkdir(parents=True)
    (d / "orphan.bighat").write_text(json.dumps({
        "schema": "bighat-round/v1",
        "id": "orphan-1",
        "round_type": "MYS",
        "name": "Orphan Mystery",
        "questions": [{"number": 1, "question": "q", "answer": "a"}],
        "status": "draft",
        "created_at": "2026-07-04T00:00:00+00:00",
    }))

    result = asyncio.run(rm.list_rounds())
    names = [r.name for r in result]
    assert "Orphan Mystery" in names, names


def test_migration_two_way(tmp_path, monkeypatch):
    rm, _tv, _pres = _reload(monkeypatch, tmp_path)
    rm.db = _DB()
    # Put a Mongo-only round
    asyncio.run(rm.db.rounds.insert_one({
        "id": "mongo-only-1",
        "round_type": "BIG",
        "name": "From Mongo",
        "questions": [{"number": 1, "question": "?", "answer": "!"}],
        "status": "draft",
        "created_at": "2026-07-04T00:00:00+00:00",
    }))
    # Put a disk-only round
    d = tmp_path / "Files" / "Trivia" / "MC"
    d.mkdir(parents=True)
    (d / "from-disk.bighat").write_text(json.dumps({
        "schema": "bighat-round/v1",
        "id": "disk-only-1",
        "round_type": "MC",
        "name": "From Disk",
        "questions": [],
        "status": "draft",
        "created_at": "2026-07-04T00:00:00+00:00",
    }))

    stats = asyncio.run(rm.migrate_rounds_disk_and_db())
    assert stats["wrote_to_disk"] == 1
    assert stats["inserted_to_db"] == 1
    # Confirm the disk file for the Mongo round now exists
    assert (tmp_path / "Files" / "Trivia" / "BIG" / "from-mongo.bighat").exists()


def test_slide_assembly_end_to_end(tmp_path, monkeypatch):
    """Full flow: create rounds → build manifest → assemble slides."""
    rm, tv, pres = _reload(monkeypatch, tmp_path)
    db = _DB()
    rm.db = db
    tv.db = db
    pres.db = db

    # Create 3 rounds (MC, REG, BIG) via the API path
    mc = asyncio.run(rm.create_round(rm.RoundCreate(
        round_type="MC", name="MC A",
        questions=[rm.QuestionItem(number=i, question=f"MC Q{i}", answer=f"MC A{i}")
                   for i in range(1, 4)],
    )))
    reg = asyncio.run(rm.create_round(rm.RoundCreate(
        round_type="REG", name="REG A",
        questions=[rm.QuestionItem(number=i, question=f"REG Q{i}", answer=f"REG A{i}")
                   for i in range(1, 3)],
    )))
    big = asyncio.run(rm.create_round(rm.RoundCreate(
        round_type="BIG", name="BIG A",
        questions=[rm.QuestionItem(number=1, question="BIG Q1", answer="BIG A1")],
    )))

    from models import TriviaImportRequest
    manifest = asyncio.run(pres._import_trivia_native(TriviaImportRequest(
        userName="Sellards", host="Sellards", location="Test Bar",
        rounds=["MC/mc-a.bighat", "REG/reg-a.bighat", "BIG/big-a.bighat"],
        roundTypes=["MC", "REG", "BIG"],
        roundNames=["MC A", "REG A", "BIG A"],
        numRounds=3,
        presentationName="E2E Alpha40",
    )))

    result = asyncio.run(tv.get_presentation_slides(manifest["id"]))
    assert result["source"] == "native-disk"
    slides = result["slides"]
    types = [s["type"] for s in slides]

    # Host, Location, MC round (cover+3q+review+answers), REG round (cover+2q+review+answers),
    # BIG round (cover+1q+review+answers), final_scores
    assert types[0] == "host"
    assert types[1] == "location"
    assert "round_cover" in types
    # Should have exactly 3 covers (one per round)
    assert types.count("round_cover") == 3
    # Should have 3 review + (2 non-BIG answers + 1 big_answers) slides
    assert types.count("review") == 3
    # BIG round emits big_answers, MC + REG emit answers
    assert types.count("answers") == 2
    assert types.count("big_answers") == 1
    # Final slide is final_scores
    assert types[-1] == "final_scores"
    # Question count: MC(3) + REG(2) as `question`, BIG(1) as `big_question`
    assert types.count("question") == 3 + 2
    assert types.count("big_question") == 1


def test_slide_assembly_placeholder_on_missing_round(tmp_path, monkeypatch):
    """If a manifest references a round `.bighat` that doesn't exist,
    the assembler emits a placeholder cover slide instead of crashing."""
    _rm, tv, pres = _reload(monkeypatch, tmp_path)
    db = _DB()
    _rm.db = db
    tv.db = db
    pres.db = db

    from models import TriviaImportRequest
    manifest = asyncio.run(pres._import_trivia_native(TriviaImportRequest(
        userName="X", host="", location="",
        rounds=["MC/does-not-exist.bighat"],
        roundTypes=["MC"], roundNames=["Ghost Round"],
        numRounds=1,
        presentationName="Broken Refs",
    )))
    result = asyncio.run(tv.get_presentation_slides(manifest["id"]))
    slides = result["slides"]
    # Should have placeholder cover + final_scores at minimum
    placeholders = [s for s in slides if s.get("subtitle", "").startswith("(round data not found")]
    assert len(placeholders) == 1
    assert result["slides"][-1]["type"] == "final_scores"
