"""v32.0.0-alpha.41 regression suite.

Merchant install feedback on alpha.40:
  1. Round Maker list shows DUPLICATES (a draft row + a generated row
     for the same round eat visual space). Fix: dedupe by (type, slug);
     prefer `generated` over `draft`.
  2. BIG rounds render the entire multi-item answer on ONE LINE. Fix:
     split comma/newline into individual items and render each on its
     own line during playback. Also add a dedicated tiebreaker slide.
  3. Trivia Presenter shows "No trivia presentations found" even when
     the wizard just dropped a `.bighat` in `Files/Trivia/Rounds/`.
     Root cause: the on-disk scan depended on `from native.files_router
     import _docs_root`, which silently fails in the PyInstaller frozen
     Windows build (module resolution shifts). Fix: inline the path
     resolver; add a `/api/trivia-viewer/debug/state` endpoint the
     merchant can hit to confirm what the backend sees.
"""
from __future__ import annotations
import asyncio
import json
import sys
from pathlib import Path


RM = Path("/app/backend/routes/roundmaker.py").read_text()
TV = Path("/app/backend/routes/trivia_viewer.py").read_text()


# ─────────────── static asserts ───────────────

def test_trivia_viewer_has_inline_docs_root():
    """Frozen build must not rely on cross-module import."""
    assert "_native_docs_root" in TV
    # The disk scan branch must exist inside list_trivia_presentations
    idx = TV.index("async def list_trivia_presentations(")
    end = TV.index("@router.get(", idx + 1)
    body = TV[idx:end]
    assert "docs_root" in body
    assert "BIG Hat Entertainment" in body


def test_debug_state_endpoint_exists():
    assert "/debug/state" in TV
    assert "docs_root_exists" in TV
    assert "rounds_files" in TV


def test_bigquestion_slide_and_tiebreaker_wired():
    idx = TV.index("def _slides_for_round(")
    body = TV[idx:idx + 5000]
    assert "big_question" in body
    assert "big_answers" in body
    assert "tiebreaker" in body


def test_list_rounds_dedupes_by_status():
    idx = RM.index("async def list_rounds(")
    body = RM[idx:idx + 2500]
    assert "generated" in body
    assert "draft" in body


# ─────────────── functional tests ───────────────

def _reload(monkeypatch, tmp_path):
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
    async def insert_one(self, doc): self.docs.append(doc)
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


def test_list_rounds_dedup_draft_vs_generated(tmp_path, monkeypatch):
    """Two DB rows with same name — one draft, one generated. Only the
    generated one should be returned."""
    rm, _tv, _pres = _reload(monkeypatch, tmp_path)
    rm.db = _DB()
    asyncio.run(rm.db.rounds.insert_one({
        "id": "draft-1", "round_type": "MC", "name": "Same Name",
        "questions": [], "status": "draft",
        "created_at": "2026-07-04T00:00:00+00:00",
    }))
    asyncio.run(rm.db.rounds.insert_one({
        "id": "gen-1", "round_type": "MC", "name": "Same Name",
        "questions": [{"number": 1, "question": "q", "answer": "a"}],
        "status": "generated", "created_at": "2026-07-04T00:01:00+00:00",
    }))
    result = asyncio.run(rm.list_rounds())
    assert len(result) == 1
    assert result[0].id == "gen-1"
    assert result[0].status == "generated"


def test_list_rounds_dedup_two_drafts_keeps_newer(tmp_path, monkeypatch):
    rm, _tv, _pres = _reload(monkeypatch, tmp_path)
    rm.db = _DB()
    asyncio.run(rm.db.rounds.insert_one({
        "id": "old", "round_type": "REG", "name": "Same",
        "questions": [], "status": "draft",
        "created_at": "2026-07-01T00:00:00+00:00",
    }))
    asyncio.run(rm.db.rounds.insert_one({
        "id": "new", "round_type": "REG", "name": "Same",
        "questions": [], "status": "draft",
        "created_at": "2026-07-03T00:00:00+00:00",
    }))
    result = asyncio.run(rm.list_rounds())
    assert len(result) == 1
    assert result[0].id == "new"


def test_big_round_answers_split_on_comma(tmp_path, monkeypatch):
    """BIG round with `answer: "Dodgers, White Sox, Guardians, Reds..."`
    must expand into a `big_answers` slide with individual items."""
    rm, tv, pres = _reload(monkeypatch, tmp_path)
    db = _DB()
    rm.db = db
    tv.db = db
    pres.db = db

    # Create a BIG round with the merchant's real-world example.
    big = asyncio.run(rm.create_round(rm.RoundCreate(
        round_type="BIG",
        name="Cactus League Easy",
        questions=[rm.QuestionItem(
            number=1,
            question="Name the 10 teams that share a stadium",
            answer="Dodgers, White Sox, Guardians, Reds, D-Backs, Rockies, Mariners, Padres, Rangers, Royals",
        )],
        tiebreaker=rm.TiebreakerItem(
            question="What is the capacity of Peoria Sports Complex?",
            answer="12,882",
        ),
    )))

    from models import TriviaImportRequest
    manifest = asyncio.run(pres._import_trivia_native(TriviaImportRequest(
        userName="Sellards", host="", location="",
        rounds=["BIG/cactus-league-easy.bighat"],
        roundTypes=["BIG"], roundNames=["Cactus League Easy"],
        numRounds=1, presentationName="BIG Test",
    )))

    result = asyncio.run(tv.get_presentation_slides(manifest["id"]))
    slides = result["slides"]
    types = [s["type"] for s in slides]

    assert "big_question" in types
    assert "big_answers" in types
    assert "tiebreaker" in types

    # The BIG answers slide has the split list
    ba = next(s for s in slides if s["type"] == "big_answers")
    assert len(ba["answers"]) == 10
    assert ba["answers"][0] == "Dodgers"
    assert ba["answers"][1] == "White Sox"
    assert ba["answers"][-1] == "Royals"

    # BIG question slide advertises the answer count
    bq = next(s for s in slides if s["type"] == "big_question")
    assert bq["answerCount"] == 10

    # Tiebreaker fields carry through
    tb = next(s for s in slides if s["type"] == "tiebreaker")
    assert "Peoria Sports Complex" in tb["question"]
    assert tb["answer"] == "12,882"


def test_big_round_answers_split_on_newline(tmp_path, monkeypatch):
    """If the merchant enters answers separated by newlines instead of
    commas, the split still produces individual items."""
    rm, tv, pres = _reload(monkeypatch, tmp_path)
    db = _DB()
    rm.db = db
    tv.db = db
    pres.db = db

    asyncio.run(rm.create_round(rm.RoundCreate(
        round_type="BIG", name="Newline BIG",
        questions=[rm.QuestionItem(
            number=1, question="q?",
            answer="First\nSecond\nThird\nFourth",
        )],
    )))

    from models import TriviaImportRequest
    manifest = asyncio.run(pres._import_trivia_native(TriviaImportRequest(
        userName="X", host="", location="",
        rounds=["BIG/newline-big.bighat"],
        roundTypes=["BIG"], roundNames=["Newline BIG"],
        numRounds=1, presentationName="NL Test",
    )))
    result = asyncio.run(tv.get_presentation_slides(manifest["id"]))
    ba = next(s for s in result["slides"] if s["type"] == "big_answers")
    assert ba["answers"] == ["First", "Second", "Third", "Fourth"]


def test_debug_state_returns_paths(tmp_path, monkeypatch):
    _rm, tv, _pres = _reload(monkeypatch, tmp_path)
    tv.db = _DB()

    # Drop a .bighat on disk
    rounds_dir = tmp_path / "Files" / "Trivia" / "Rounds"
    rounds_dir.mkdir(parents=True)
    (rounds_dir / "wizard.bighat").write_text(json.dumps({
        "schema": "bighat-presentation/v1",
        "id": "wiz-1", "name": "Wizard Pres", "createdBy": "Sellards",
        "host": "Nick", "roundFiles": [{"type": "MC", "name": "R1"}],
    }))

    result = asyncio.run(tv.debug_state())
    assert result["docs_root_exists"] is True
    assert result["rounds_dir_exists"] is True
    assert len(result["rounds_files"]) == 1
    assert result["rounds_files"][0]["id"] == "wiz-1"
    assert result["rounds_files"][0]["roundFiles"] == 1


def test_list_surfaces_disk_manifest_without_createdBy(tmp_path, monkeypatch):
    """Alpha.41 relaxation: a disk .bighat without `createdBy` should
    surface for any user (not filtered out silently)."""
    _rm, tv, _pres = _reload(monkeypatch, tmp_path)
    tv.db = _DB()

    rounds_dir = tmp_path / "Files" / "Trivia" / "Rounds"
    rounds_dir.mkdir(parents=True)
    (rounds_dir / "anon.bighat").write_text(json.dumps({
        "schema": "bighat-presentation/v1",
        "id": "anon-1", "name": "Anon Pres",
        # NO createdBy, NO host — must still appear
        "roundFiles": [],
    }))

    listed = asyncio.run(tv.list_trivia_presentations(
        userName="somebody-else", viewAll=False, hostName="Nick",
    ))
    ids = [p.get("id") for p in listed]
    assert "anon-1" in ids
