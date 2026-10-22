"""v32.1.8: scoreboard Fetch. Trivia "Save & Exit" writes a score file; the Scoreboard's Fetch lists every night in ONE GET (no POST),
reports unreadable files, finds a venue by the name the host sees, and gives every night a unique id for the dropdown."""
import asyncio, json, os, sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture
def sb(tmp_path, monkeypatch):
    monkeypatch.setenv("BIGHAT_FILES_DIR", str(tmp_path))
    monkeypatch.setenv("BIGHAT_DATA_ROOT", str(tmp_path / "appdata"))
    monkeypatch.setenv("BIGHAT_NATIVE_MODE", "1")
    from routes import scoreboard
    scoreboard.db = None
    return scoreboard, tmp_path


def night(venue_dir, name, location, date, teams=2, root=None):
    d = Path(root) / "Files" / "Trivia" / "Scores" / venue_dir
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(json.dumps({"location": location, "date": date, "savedAt": f"2026-10-2{teams}T10:00:00Z",
                                      "teams": [{"name": f"T{i}", "total": 10 - i, "roundScores": [5, 5 - i]} for i in range(teams)], "rounds": []}))


def fetch(sb_mod):
    return asyncio.run(sb_mod.get_local_scores())


def test_fetch_lists_every_night_with_a_unique_id(sb):
    m, root = sb
    night("Test_Venue", "Test_Venue_10-20-2026.json", "Test Venue", "10/20/2026", root=root)
    night("Test_Venue", "Test_Venue_10-27-2026.json", "Test Venue", "10/27/2026", root=root)
    night("Other_Bar", "Test_Venue_10-20-2026.json", "Other Bar", "10/20/2026", root=root)         # SAME file name, other venue
    r = fetch(m)
    assert r["count"] == 3 and r["unreadable"] == 0
    ids = [f["id"] for f in r["files"]]
    assert len(set(ids)) == 3                                                                      # no collision in the dropdown
    assert {"Test_Venue/Test_Venue_10-20-2026.json", "Other_Bar/Test_Venue_10-20-2026.json"} <= set(ids)


def test_a_damaged_or_empty_file_is_reported_and_does_not_hide_the_rest(sb):
    m, root = sb
    night("V", "ok.json", "V", "10/20/2026", root=root)
    d = root / "Files" / "Trivia" / "Scores" / "V"
    (d / "broken.json").write_text("{ nope")
    (d / "noteams.json").write_text(json.dumps({"location": "V"}))
    r = fetch(m)
    assert r["count"] == 1 and r["unreadable"] == 2
    bad = {f["file_name"]: f["error"] for f in r["files"] if f["data"] is None}
    assert set(bad) == {"broken.json", "noteams.json"} and all(bad.values())


def test_no_files_is_an_empty_list_not_an_error(sb):
    r = fetch(sb[0])
    assert r["count"] == 0 and r["files"] == [] and r["unreadable"] == 0


def test_newest_night_comes_first(sb):
    m, root = sb
    night("V", "a.json", "V", "10/20/2026", teams=2, root=root)
    night("V", "b.json", "V", "10/27/2026", teams=3, root=root)       # savedAt is later for b
    assert [f["file_name"] for f in fetch(m)["files"]][0] == "b.json"


def test_the_app_copy_is_read_when_the_documents_copy_is_gone(sb, tmp_path):
    m, root = sb
    from native import scores_store
    night("V", "a.json", "V", "10/20/2026", root=root)
    import shutil
    appcopy = Path(os.environ["BIGHAT_DATA_ROOT"]) / "backups" / "scores" / "V"
    appcopy.mkdir(parents=True, exist_ok=True)
    shutil.copy(root / "Files" / "Trivia" / "Scores" / "V" / "a.json", appcopy / "a.json")
    shutil.rmtree(root / "Files" / "Trivia" / "Scores")
    assert fetch(m)["count"] == 1


@pytest.mark.parametrize("asked", ["Test Venue", "Test_Venue", "test venue", "TEST-VENUE"])
def test_a_venue_is_found_by_the_name_a_host_sees(sb, asked):
    m, root = sb
    night("Test_Venue", "n.json", "Test Venue", "10/20/2026", root=root)
    fetch_and_store(m)
    assert asyncio.run(m.get_venue_scores(asked))["count"] == 1


def test_a_venue_with_dots_and_brackets_is_plain_text_not_a_pattern(sb):
    m, root = sb
    night("Cornish_Pasty_Co._Glendale", "n.json", "Cornish Pasty Co. (Glendale)", "10/21/2026", root=root)
    night("Other", "n.json", "Cornish Pasty Co Glendale Annex", "10/21/2026", root=root)
    fetch_and_store(m)
    assert asyncio.run(m.get_venue_scores("Cornish Pasty Co. (Glendale)"))["count"] == 1
    assert asyncio.run(m.get_venue_scores("Co."))["count"] == 0       # used to match as a regex
    assert asyncio.run(m.get_venue_scores("("))["count"] == 0         # used to raise a regex error


def test_the_local_route_is_declared_before_the_venue_route(sb):
    m, _ = sb
    paths = [r.path for r in m.router.routes if r.path.startswith("/scoreboard/scores")]
    assert paths.index("/scoreboard/scores/local") < paths.index("/scoreboard/scores/{venue}")


class _Col:
    def __init__(self): self.rows = {}
    async def update_one(self, q, u, upsert=False): self.rows[(q["venue"], q["file_name"])] = {**q, **u["$set"]}
    def find(self, *a, **k):
        rows = list(self.rows.values())
        class C:
            async def to_list(_, n): return rows
        return C()


def fetch_and_store(m):
    class DB: score_files = _Col()
    m.db = DB()
    asyncio.run(m.get_local_scores())


# ---- v32.1.9: importing the same night twice must not list it twice ----
def test_importing_a_night_that_is_already_here_adds_no_copy(sb):
    m, root = sb
    from native import scores_store
    body = {"location": "Test Venue", "date": "10/20/2026", "teams": [{"name": "A", "total": 11, "roundScores": [5, 6]}, {"name": "B", "total": 7, "roundScores": [3, 4]}]}
    first = scores_store.import_json(json.dumps(body).encode())
    again = scores_store.import_json(json.dumps({**body, "savedAt": "later", "presentationId": "other"}).encode())
    assert again.get("duplicate") and again["filename"] == first["filename"]
    assert len(list((scores_store.primary_root() / "Test_Venue").glob("*.json"))) == 1


def test_a_different_night_with_the_same_name_and_date_still_gets_its_own_file(sb):
    m, root = sb
    from native import scores_store
    a = {"location": "Test Venue", "date": "10/20/2026", "teams": [{"name": "A", "total": 11, "roundScores": [5, 6]}]}
    b = {"location": "Test Venue", "date": "10/20/2026", "teams": [{"name": "A", "total": 9, "roundScores": [4, 5]}]}
    scores_store.import_json(json.dumps(a).encode())
    second = scores_store.import_json(json.dumps(b).encode())
    assert not second.get("duplicate")
    assert len(list((scores_store.primary_root() / "Test_Venue").glob("*.json"))) == 2          # nothing is ever overwritten
