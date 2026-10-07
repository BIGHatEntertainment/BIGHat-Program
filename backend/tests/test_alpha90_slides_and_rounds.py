"""alpha.90: BIG answers, Mystery never leaks its theme, pills are 28, one file per round."""
import asyncio, json, os, sys, tempfile, glob
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import native_slides as ns


def texts(slide): return [str(e.get("content")) for e in slide["elements"] if e["type"] == "text"]
def find(slides, key): return [s for s in slides if s["metadata"].get(key)]


def big(qs): return ns.render_round_section({"name": "BIG_Spices", "round_type": "BIG", "questions": qs, "tiebreaker": None},
                                           {"type": "BIG", "name": "BIG_Spices"})


SPICES = ["Allspice", "Cinnamon", "Nutmeg", "Cloves", "Ginger"]


def test_big_answers_all_show_when_the_generator_saved_one_question_per_answer():
    sl = big([{"number": i + 1, "question": "Name the spice", "answer": a} for i, a in enumerate(SPICES)])
    ans = find(sl, "isAnswers")[0]
    body = " ".join(texts(ans))
    for i, a in enumerate(SPICES, 1):
        assert f"{i}. {a}" in body, body
    q = " ".join(texts(find(sl, "questionNumber")[0]))
    assert "For 15 Points" in q, q                        # five answers at 3 points each (it said "For 3 Points")


def test_big_older_shapes_still_work():
    for ans in ("Allspice\nCinnamon\nNutmeg", "Allspice, Cinnamon, Nutmeg"):
        sl = big([{"number": 1, "question": "Q", "answer": ans}])
        body = " ".join(texts(find(sl, "isAnswers")[0]))
        assert "1. Allspice" in body and "2. Cinnamon" in body and "3. Nutmeg" in body, body
    one = " ".join(texts(find(big([{"number": 1, "question": "Q", "answer": "Allspice"}]), "isAnswers")[0]))
    assert "1. Allspice" in one and "2." not in one


def test_big_review_slide_points_match_all_answers():
    sl = big([{"number": i + 1, "question": "Q", "answer": a} for i, a in enumerate(SPICES)])
    rev = find(sl, "isReview")
    if rev:
        assert "15" in " ".join(texts(rev[0]))


def test_mystery_review_and_title_never_show_the_theme():
    qs = [{"number": i + 1, "question": f"Q{i}", "answer": f"A{i}"} for i in range(12)]
    sl = ns.render_round_section({"name": "Mystery_Cryptids", "round_type": "MYS", "questions": qs, "tiebreaker": None},
                                 {"type": "MYS", "name": "Mystery_Cryptids"})
    everything = " ".join(" ".join(texts(s)) for s in sl)
    assert "Cryptids" not in everything and "Mystery_Cryptids" not in everything, everything[:300]
    rev = " ".join(" ".join(texts(s)) for s in find(sl, "isReview"))
    assert "Mystery Round" in rev


def test_other_rounds_still_show_their_name_in_review():
    qs = [{"number": i + 1, "question": f"Q{i}", "answer": f"A{i}"} for i in range(12)]
    sl = ns.render_round_section({"name": "Animals_1", "round_type": "REG", "questions": qs, "tiebreaker": None},
                                 {"type": "REG", "name": "Animals_1"})
    rev = " ".join(" ".join(texts(s)) for s in find(sl, "isReview"))
    assert "Animals_1" in rev


def test_pills_are_28_and_a_very_long_theme_steps_down_not_overflows():
    for t, n in (("MC", ""), ("REG", "Animals_1"), ("MISC", "Movies_2"), ("MYS", "Mystery_Cryptids"), ("BIG", "BIG_Spices")):
        assert ns.pill_font_size(ns.format_pill_label(t, n, True), 530) == 28, (t, n)
    long = ns.format_pill_label("REG", "The_Extraordinary_Adventures_Of_Tiny_Garden_Gnomes_9", True)
    assert 22 <= ns.pill_font_size(long, 530) < 28


@pytest.fixture
def rounds_env(monkeypatch):
    tmp = tempfile.mkdtemp()
    monkeypatch.setenv("BIGHAT_FILES_DIR", tmp); monkeypatch.setenv("BIGHAT_DB_DIR", tmp + "/db")
    monkeypatch.setenv("BIGHAT_DATA_DIR", tmp + "/data"); monkeypatch.setenv("BIGHAT_NATIVE_MODE", "1")
    os.makedirs(tmp + "/db", exist_ok=True)
    from native import db_factory
    db_factory._native_client = None
    from routes import roundmaker as rm
    rm.set_database(db_factory.get_db())
    yield tmp, rm
    db_factory.close_all()


QS = [{"number": i + 1, "question": "Q", "answer": f"A{i}"} for i in range(12)]


def files(tmp): return sorted(os.path.basename(p) for p in glob.glob(tmp + "/**/*.bighat", recursive=True) if "_duplicates_removed" not in p)


def test_saving_the_same_round_again_updates_it_and_makes_no_stamped_copy(rounds_env):
    tmp, rm = rounds_env
    for _ in range(3):
        asyncio.run(rm.create_round(rm.RoundCreate(round_type="REG", name="Animals_1", questions=QS, tiebreaker=None, cover_image_id=None)))
    assert files(tmp) == ["animals-1.bighat"]
    from routes.trivia import _list_local_round_files
    assert [r["name"] for r in _list_local_round_files("reg")] == ["animals-1"]


def test_editing_a_saved_round_keeps_one_file_with_the_new_questions(rounds_env):
    tmp, rm = rounds_env
    asyncio.run(rm.create_round(rm.RoundCreate(round_type="REG", name="Animals_1", questions=QS, tiebreaker=None, cover_image_id=None)))
    q2 = [dict(q, answer="NEW") for q in QS]
    asyncio.run(rm.create_round(rm.RoundCreate(round_type="REG", name="Animals_1", questions=q2, tiebreaker=None, cover_image_id=None)))
    assert files(tmp) == ["animals-1.bighat"]
    p = glob.glob(tmp + "/**/animals-1.bighat", recursive=True)[0]
    assert json.loads(Path(p).read_text())["questions"][0]["answer"] == "NEW"


def test_same_name_in_a_different_round_type_is_a_different_round(rounds_env):
    tmp, rm = rounds_env
    asyncio.run(rm.create_round(rm.RoundCreate(round_type="REG", name="Movies_1", questions=QS, tiebreaker=None, cover_image_id=None)))
    asyncio.run(rm.create_round(rm.RoundCreate(round_type="MISC", name="Movies_1", questions=QS, tiebreaker=None, cover_image_id=None)))
    assert len(files(tmp)) == 2


def _write(tmp, rtype, fname, name, qs):
    d = Path(tmp) / "Files" / "Trivia" / rtype; d.mkdir(parents=True, exist_ok=True)
    (d / fname).write_text(json.dumps({"schema": "bighat-round/v1", "id": fname, "round_type": rtype, "name": name, "questions": qs, "tiebreaker": None}))
    return d


def test_existing_stamped_copies_are_moved_aside_and_never_deleted(rounds_env):
    tmp, rm = rounds_env
    d = _write(tmp, "REG", "animals-1.bighat", "Animals_1", QS)
    _write(tmp, "REG", "animals-1-19a86b85.bighat", "Animals_1", QS)          # exact copy
    r = rm.tidy_duplicate_rounds()
    assert r["moved"] == 1 and r["moved_names"] == ["animals-1-19a86b85.bighat"]
    assert (d / "animals-1.bighat").is_file() and not (d / "animals-1-19a86b85.bighat").exists()
    assert (d / "_duplicates_removed" / "animals-1-19a86b85.bighat").is_file()     # recoverable


def test_a_stamped_file_that_differs_is_left_alone_and_still_offered(rounds_env):
    tmp, rm = rounds_env
    d = _write(tmp, "REG", "animals-1.bighat", "Animals_1", QS)
    _write(tmp, "REG", "animals-1-19a86b85.bighat", "Animals_1", [dict(q, answer="DIFFERENT") for q in QS])
    r = rm.tidy_duplicate_rounds()
    assert r["moved"] == 0 and r["kept_different"] == 1
    assert (d / "animals-1-19a86b85.bighat").is_file()
    from routes.trivia import _list_local_round_files
    assert len(_list_local_round_files("reg")) == 2                         # real differences are never hidden


def test_a_round_whose_real_name_ends_in_eight_hex_is_not_touched(rounds_env):
    tmp, rm = rounds_env
    d = _write(tmp, "REG", "pop.bighat", "Pop", QS)
    _write(tmp, "REG", "pop-deadbeef.bighat", "Pop-deadbeef", [dict(q, answer="X") for q in QS])
    assert rm.tidy_duplicate_rounds()["moved"] == 0 and (d / "pop-deadbeef.bighat").is_file()
