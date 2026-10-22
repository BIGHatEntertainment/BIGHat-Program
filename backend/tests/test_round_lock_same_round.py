"""v32.1.8: a round is ONE round whatever its file is called (the File Creator gives every export a new random id, so a re-uploaded
round comes back as TYPE__name, name, or name-<8 hex>), the lists hide ALL of them while it is locked, and an admin release frees ALL
of them and is never undone by an older saved show."""
import json, os, sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
LID, LN = "loc-1", "Test Venue"


@pytest.fixture
def ru(tmp_path, monkeypatch):
    monkeypatch.setenv("BIGHAT_FILES_DIR", str(tmp_path))
    monkeypatch.setenv("BIGHAT_DATA_ROOT", str(tmp_path / "appdata"))
    for n in list(sys.modules):
        if n in ("round_usage", "native_slides") or n.startswith("native.data_map"):
            sys.modules.pop(n, None)
    import round_usage
    return round_usage


def build(ru, pid, files, loc=(LID, LN)):
    ru.record_usage(location_id=loc[0], location_name=loc[1], used_by="n", presentation_id=pid, presentation_name=pid,
                    round_files=[{"order": i + 1, "type": "MC", "file": f} for i, f in enumerate(files)])


SPELLINGS = ["mystery-apples.bighat", "MYS__mystery-apples.bighat", "mystery-apples-3f9a1b2c.bighat",
             "Files/Trivia/MYS/mystery-apples.bighat", r"C:\Users\N\Documents\BIG Hat Entertainment\Files\Trivia\MYS\MYS__Mystery-Apples.bighat"]


@pytest.mark.parametrize("built_as", SPELLINGS)
@pytest.mark.parametrize("listed_as", SPELLINGS)
def test_every_spelling_of_a_locked_round_is_hidden(ru, built_as, listed_as):
    build(ru, "p1", [built_as])
    assert ru.is_locked(listed_as, ru.locked_names(LN))


def test_a_different_round_is_never_hidden(ru):
    build(ru, "p1", ["mystery-apples.bighat"])
    locked = ru.locked_names(LN)
    for other in ("mystery-oranges.bighat", "apples.bighat", "mystery-apples-2.bighat", "MYS__mystery-pears.bighat", "mc-01-a.bighat"):
        assert not ru.is_locked(other, locked), other


def test_a_numbered_round_never_hides_its_neighbour(ru):
    build(ru, "p2", ["dragon-ball-z-1.bighat", "1960s-1.bighat"])
    locked = ru.locked_names(LN)
    assert not ru.is_locked("dragon-ball-z-2.bighat", locked) and not ru.is_locked("1960s-2.bighat", locked)
    assert not ru.is_locked("dragon-ball-z.bighat", locked)


def test_known_limit_a_plain_round_whose_name_ends_in_8_hex_is_treated_as_a_stamped_copy(ru):
    """Honest limit of treating `name-<8 hex>` as a stamp (the same rule alpha.90 already uses for duplicates): locking
    `big-deadbeef` also hides a different round called `big`. It only ever hides MORE, never lets a locked round through."""
    build(ru, "p1", ["big-deadbeef.bighat"])
    assert ru.is_locked("big.bighat", ru.locked_names(LN))


def test_release_frees_every_spelling_at_that_venue_but_not_another_venue(ru):
    build(ru, "p1", ["mystery-apples.bighat", "mc-01-a.bighat"])
    build(ru, "p2", ["MYS__mystery-apples.bighat"])
    build(ru, "p3", ["mystery-apples.bighat"], loc=("loc-2", "Other Bar"))
    rid = [r for r in ru.list_records() if r["presentationId"] == "p1" and "apples" in r["roundFileName"]][0]["id"]
    assert ru.release(rid) == 2                                    # the p1 record AND the p2 spelling
    here = ru.locked_names(LN)
    assert not ru.is_locked("mystery-apples-3f9a1b2c.bighat", here) and not ru.is_locked("MYS__mystery-apples.bighat", here)
    assert ru.is_locked("mc-01-a.bighat", here)                    # untouched
    assert ru.is_locked("mystery-apples.bighat", ru.locked_names("Other Bar"))       # another venue keeps its lock


def test_releasing_a_whole_show_frees_its_rounds_even_if_another_show_used_them(ru):
    build(ru, "p1", ["a.bighat", "b.bighat"])
    build(ru, "p2", ["MC__a.bighat", "c.bighat"])
    build(ru, "p3", ["a.bighat"], loc=("loc-2", "Other Bar"))
    assert ru.release_presentation("p1") == 3                          # p1's two + p2's other spelling of a
    here = ru.locked_names(LN)
    assert not ru.is_locked("a", here) and not ru.is_locked("b", here) and ru.is_locked("c", here)
    assert ru.is_locked("a", ru.locked_names("Other Bar"))             # another venue keeps its own lock


def test_release_by_show_and_release_all_remember_the_rounds(ru):
    build(ru, "p1", ["a.bighat", "b.bighat"])
    assert ru.release_presentation("p1") == 2
    doc = json.loads(ru._path().read_text())
    assert doc["records"] == [] and len(doc["released_rounds"]) >= 2
    build(ru, "p2", ["c.bighat"])
    assert ru.release_all() == 1


def _saved_show(tmp_path, pid, files, when="2026-10-20T10:00:00+00:00"):
    d = tmp_path / "Files" / "Trivia" / "Rounds"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{pid}.bighat").write_text(json.dumps({"id": pid, "name": pid, "location_id": LID, "location_name": LN, "created_at": when,
                                                  "roundFiles": [{"order": i + 1, "type": "MC", "file": f} for i, f in enumerate(files)]}))


def test_an_old_saved_show_cannot_relock_a_released_round_under_any_spelling(ru, tmp_path):
    _saved_show(tmp_path, "showA", ["Files/Trivia/MC/mc-01-a.bighat"])
    _saved_show(tmp_path, "showB", ["Files/Trivia/MC/MC__mc-01-a.bighat"], "2026-10-21T10:00:00+00:00")
    assert ru.is_locked("mc-01-a", ru.locked_names(LN))
    for r in [x for x in ru.list_records() if "mc-01-a" in x["roundFileName"]][:1]:
        ru.release(r["id"])
    ru._save(ru._load())                                           # a later save must keep the memory too
    assert not ru.is_locked("mc-01-a", ru.locked_names(LN))
    assert not ru.is_locked("MC__mc-01-a", ru.locked_names(LN))
    assert not ru.is_locked("mc-01-a", ru.locked_names(LID))


def test_a_saved_show_the_release_never_saw_cannot_relock_a_released_round(ru, tmp_path):
    """The real case: the admin released the round, but ANOTHER saved show (older, or re-created when files were cleared and
    re-uploaded) used it under a different file name. The per-show tombstones know nothing about that show."""
    _saved_show(tmp_path, "showA", ["Files/Trivia/MC/mc-01-a.bighat"])
    assert ru.is_locked("mc-01-a", ru.locked_names(LN))
    ru.release(ru.list_records()[0]["id"])
    assert not ru.is_locked("mc-01-a", ru.locked_names(LN))
    _saved_show(tmp_path, "showLater", ["Files/Trivia/MC/MC__mc-01-a.bighat"], "2026-10-21T10:00:00+00:00")
    _saved_show(tmp_path, "showLater2", ["Files/Trivia/MC/mc-01-a-3f9a1b2c.bighat"], "2026-10-22T10:00:00+00:00")
    here = ru.locked_names(LN)
    assert not ru.is_locked("mc-01-a", here) and not ru.is_locked("MC__mc-01-a", here) and not ru.is_locked("mc-01-a-3f9a1b2c", here)


def test_building_again_after_a_release_locks_the_round_again(ru):
    build(ru, "p1", ["mc-01-a.bighat"])
    ru.release(ru.list_records()[0]["id"])
    assert not ru.is_locked("mc-01-a", ru.locked_names(LN))
    build(ru, "p2", ["mc-01-a.bighat"])
    assert ru.is_locked("mc-01-a", ru.locked_names(LN))


def test_the_released_memory_survives_other_saves(ru, tmp_path):
    build(ru, "p1", ["mc-01-a.bighat"])
    ru.release(ru.list_records()[0]["id"])
    build(ru, "p2", ["memes-3.bighat"])                            # an ordinary later save
    ru.cleanup_expired()
    assert json.loads(ru._path().read_text())["released_rounds"]
    _saved_show(tmp_path, "showLater", ["Files/Trivia/MC/mc-01-a.bighat"], "2026-10-22T10:00:00+00:00")
    assert not ru.is_locked("mc-01-a", ru.locked_names(LN))


def test_release_survives_a_damaged_file_restore(ru):
    build(ru, "p1", ["mc-01-a.bighat", "memes-3.bighat"])
    ru.release([r for r in ru.list_records() if r["roundFileName"] == "mc-01-a"][0]["id"])
    ru._path().write_text("{ broken", encoding="utf-8")
    here = ru.locked_names(LN)
    assert not ru.is_locked("mc-01-a", here) and ru.is_locked("memes-3", here)


def test_the_wizard_list_route_hides_every_spelling(ru, tmp_path, monkeypatch):
    import asyncio
    d = tmp_path / "Files" / "Trivia" / "MYS"
    d.mkdir(parents=True)
    for n in ("mystery-apples", "MYS__mystery-apples", "mystery-oranges"):
        (d / f"{n}.bighat").write_text(json.dumps({"schema": "bighat-round/v1", "round_type": "MYS", "name": n, "questions": [{"question": "q"}]}))
    build(ru, "p1", ["Files/Trivia/MYS/mystery-apples.bighat"])
    from routes import trivia
    monkeypatch.setattr(trivia, "_is_local_mode", lambda: True)
    names = [r["name"] for r in asyncio.run(trivia.get_round_files_by_type("mys", f"location:{LID}"))]
    assert names == ["mystery-oranges"]
