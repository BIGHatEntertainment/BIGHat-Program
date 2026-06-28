"""Ground-truth fixture test against the 5 real `.bighat` files the
merchant attached for v32.0.0-alpha.23 verification.

Files are in `backend/tests/fixtures/bighat/`:
  • mc-01-a.bighat                 — MC round, 10 questions, cover.jpg
  • animals-1.bighat               — REG round, no options
  • arizona-1.bighat               — REG round
  • mystery-apples.bighat          — MYS round, single-answer clues
  • big-cactus-league-easy.bighat  — BIG round, multi-answer `answers[]`

Each test imports the file via `_import_zip_bytes`, then asserts the
resulting `db.rounds` doc both:
  (1) validates against `RoundResponse`
  (2) renders the way the dashboard expects (question text non-empty,
      correctOption set when MC, cover_image_id present)
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

mongomock_motor = pytest.importorskip("mongomock_motor")
from backend.routes import bighat_files as bf
from backend.routes.roundmaker import RoundResponse


FIXT = Path(__file__).parent / "fixtures" / "bighat"


@pytest.fixture
def fake_db(monkeypatch):
    client = mongomock_motor.AsyncMongoMockClient()
    db = client["bighat_test"]
    bf.set_database(db)
    # mongomock-motor doesn't ship a working `AsyncIOMotorGridFSBucket`,
    # so stub the cover-image uploader to return a fake id. Production
    # uses the real motor bucket; this stub just confirms the import
    # path WOULD have called the uploader with a non-empty asset blob.
    async def _stub(assets):
        for path in (assets or {}):
            stem = Path(path).stem.lower()
            if stem in {"cover", "cover_image", "title", "title_card"}:
                return "stub-cover-image-id"
        return None
    monkeypatch.setattr(bf, "_ingest_cover_image", _stub)
    return db


from pathlib import Path


def _import(path: Path):
    return asyncio.get_event_loop().run_until_complete(
        bf._import_zip_bytes(path.read_bytes())
    )


def _load_doc(db, round_id: str) -> dict:
    return asyncio.get_event_loop().run_until_complete(
        db.rounds.find_one({"id": round_id}, {"_id": 0})
    )


# ---------- MC ----------
def test_mc_round_imports_with_correct_option_and_cover(fake_db):
    res = _import(FIXT / "mc-01-a.bighat")
    assert res.type == "round"
    doc = _load_doc(fake_db, res.id)
    # Sanity / schema
    assert RoundResponse(**doc).round_type == "MC"
    assert doc["name"].startswith("MC_01_A")
    # Cover was bundled at assets/cover.jpg → should have landed in
    # GridFS and `cover_image_id` should be populated.
    assert doc.get("cover_image_id"), "title card / cover_image_id missing"
    # First question: prompt, options, correct_index → translated fields
    q0 = doc["questions"][0]
    assert q0["number"] == 1
    assert q0["question"].startswith("What TV series")
    assert q0["options"][:4] == ["M*A*S*H", "Seinfeld", "Cheers", "Friends"]
    assert q0["correctOption"] == 0
    assert q0["answer"] == "M*A*S*H"


# ---------- REG (no options) ----------
@pytest.mark.parametrize("fname,expected_prefix", [
    ("animals-1.bighat",  "What land animal"),
    ("arizona-1.bighat",  "Since 1910"),
])
def test_reg_round_imports_with_plain_answer_no_options(fake_db, fname, expected_prefix):
    res = _import(FIXT / fname)
    doc = _load_doc(fake_db, res.id)
    rr = RoundResponse(**doc)
    assert rr.round_type == "REG"
    assert doc.get("cover_image_id"), "cover_image_id missing"
    q0 = doc["questions"][0]
    assert q0["question"].startswith(expected_prefix)
    # REG rounds carry an `answer` string but no options + no correctOption.
    assert q0["answer"]
    assert q0.get("options") in (None, [])      # nothing meaningful
    assert q0.get("correctOption") is None or q0.get("correctOption") == None  # explicit


# ---------- MYS ----------
def test_mys_round_imports_with_clue_prompts(fake_db):
    res = _import(FIXT / "mystery-apples.bighat")
    doc = _load_doc(fake_db, res.id)
    rr = RoundResponse(**doc)
    assert rr.round_type == "MYS"
    assert doc.get("cover_image_id"), "cover_image_id missing"
    qs = doc["questions"]
    # 9 clues with answers + 1 "What is the theme of this round?" with
    # a blank answer (merchant fills the theme in by hand later).
    assert len(qs) == 10
    for i, q in enumerate(qs[:9]):
        assert q["question"], f"clue {i} missing prompt"
        assert q["answer"], f"clue {i} missing answer"
    # The 10th clue: prompt present, answer intentionally blank.
    assert "theme" in qs[9]["question"].lower()
    assert qs[9]["answer"] == ""


# ---------- BIG (multi-answer) ----------
def test_big_round_imports_preserves_answers_array(fake_db):
    res = _import(FIXT / "big-cactus-league-easy.bighat")
    doc = _load_doc(fake_db, res.id)
    rr = RoundResponse(**doc)
    assert rr.round_type == "BIG"
    assert doc.get("cover_image_id"), "cover_image_id missing"
    q0 = doc["questions"][0]
    assert q0["question"].startswith("There are 15 MLB teams")
    # BIG rounds bundle a multi-answer array AND a single comma-joined
    # answer string; translator must preserve BOTH so downstream tools
    # (PPTX generator, scoreboard) can pick whichever they need.
    assert isinstance(q0.get("answers"), list)
    assert len(q0["answers"]) >= 10
    assert "Dodgers" in q0["answers"]
    assert q0["answer"].startswith("Dodgers,")


# ---------- List endpoint sanity ----------
def test_all_five_show_up_in_list_rounds(fake_db, monkeypatch):
    """After importing all 5, GET /api/roundmaker/rounds must list all
    five with non-empty question text on Q1 (the very symptom alpha.22
    regressed on)."""
    from backend.routes.roundmaker import list_rounds
    from backend.routes import roundmaker as rm
    rm.db = fake_db

    for f in FIXT.glob("*.bighat"):
        _import(f)

    rounds = asyncio.get_event_loop().run_until_complete(list_rounds())
    assert len(rounds) == 5
    for r in rounds:
        # RoundResponse declares `questions: List[dict]` so they stay
        # as dicts (not coerced into QuestionItem). Access via subscript.
        assert r.questions, f"{r.name} has no questions"
        assert r.questions[0].get("question"), f"{r.name} Q1 question text is blank"
