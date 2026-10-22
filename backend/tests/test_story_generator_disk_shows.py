"""v32.1.10: the Story Generator LISTED shows from the disk (/trivia-viewer/list) but every action on one (details, images, preview, generate)
answered "Presentation not found", because those routes read only the in-memory database (empty after each launch; a Build Wizard show only
exists as a file in Files/Trivia/Rounds). They now fall back to the file and map the Wizard's v2 field names to the ones they read."""
import asyncio, json, os, sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
PID = "11111111-aaaa-bbbb-cccc-222222222222"


class _Coll:
    def __init__(self, rows=None): self.rows = rows or []
    async def find_one(self, q): return next((r for r in self.rows if r.get("id") == q.get("id")), None)


class _DB:
    def __init__(self, trivia=None, pres=None):
        self.trivia_presentations = _Coll(trivia); self.presentations = _Coll(pres)


@pytest.fixture
def sg(tmp_path, monkeypatch):
    home = tmp_path
    monkeypatch.setenv("HOME", str(home)); monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("BIGHAT_DATA_ROOT", str(home / "appdata"))
    monkeypatch.setenv("BIGHAT_FILES_DIR", str(home / "Documents" / "BIG Hat Entertainment" / "Files"))
    for n in list(sys.modules):
        if n.startswith("native.data_map") or n in ("native.files_router", "native_slides"):
            sys.modules.pop(n, None)
    from routes import story_generator as m
    m.db = _DB()
    from native.files_router import _docs_root
    rd = _docs_root() / "Files" / "Trivia" / "Rounds"
    rd.mkdir(parents=True)
    show = {"id": PID, "type": "trivia-presentation", "name": "Cornish - 10/20", "created_at": "2026-10-20T18:00:00+00:00",
            "created_by": "sellards@bighat.live", "host_name": "Nick Sellards", "location_name": "Cornish Pasty Co. (Glendale)", "round_count": 6,
            "roundFiles": [{"order": i + 1, "type": t, "file": f"Files/Trivia/{t}/{n}.bighat"} for i, (t, n) in enumerate(
                [("MC", "mc-16-a"), ("REG", "memes-3"), ("MISC", "dragon-ball-z-1"), ("MISC", "simpsons-1"), ("MYS", "mystery-harrypotter2"), ("BIG", "big-most-abundant-elements")])]}
    (rd / "cornish-111111.bighat").write_text(json.dumps(show), encoding="utf-8")
    return m


def run(c): return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(c)


def test_a_show_that_only_exists_on_disk_is_found(sg):
    p = run(sg._find_presentation(PID))
    assert p and p["id"] == PID


def test_an_unknown_id_is_still_not_found(sg):
    assert run(sg._find_presentation("nope")) is None


def test_the_database_wins_when_it_has_the_show(sg):
    sg.db = _DB(trivia=[{"id": PID, "name": "From DB", "location": "DB Bar", "host": "Dee", "roundFiles": []}])
    p = run(sg._find_presentation(PID))
    assert p["name"] == "From DB" and p["host"] == "Dee" and p["location"] == "DB Bar"


def test_wizard_names_are_mapped_to_the_names_the_routes_read(sg):
    p = run(sg._find_presentation(PID))
    assert (p["host"], p["location"], p["createdBy"], p["numRounds"]) == ("Nick Sellards", "Cornish Pasty Co. (Glendale)", "sellards@bighat.live", 6)
    assert p["createdAt"] == "2026-10-20T18:00:00+00:00" and p["roundTypes"] == ["MC", "REG", "MISC", "MISC", "MYS", "BIG"]


def test_old_names_are_never_overwritten(sg):
    d = sg._normalise_saved_show({"id": "x", "host": "Old Host", "host_name": "New Host", "location": "Old Loc", "location_name": "New Loc", "createdBy": "a", "created_by": "b"})
    assert (d["host"], d["location"], d["createdBy"]) == ("Old Host", "Old Loc", "a")


@pytest.mark.parametrize("ref,want", [({"file": "Files/Trivia/REG/memes-3.bighat"}, "Memes 3"),
                                      ({"file": "Files/Trivia/MISC/dragon-ball-z-1.bighat"}, "Dragon Ball Z 1"),
                                      ({"file": "Files/Trivia/BIG/big__fall-favorite-flavors-1a2b3c4d.bighat"}, "Fall Favorite Flavors"),
                                      ({"name": "Shown Name", "file": "x/y.bighat"}, "Shown Name"),
                                      ({}, "REG Round")])
def test_round_names_are_readable(sg, ref, want):
    assert sg._round_display_name(ref, "REG Round") == want


def test_the_detail_route_returns_host_location_and_round_names(sg):
    d = run(sg.get_presentation_details(PID))
    assert d["host"] == "Nick Sellards" and d["location"] == "Cornish Pasty Co. (Glendale)" and d["numRounds"] == 6
    assert [r["name"] for r in d["rounds"]] == ["Multiple Choice", "Memes 3", "Dragon Ball Z 1", "Simpsons 1", "Mystery", "Big Most Abundant Elements"]


def test_every_story_route_uses_the_one_lookup():
    src = (Path(__file__).resolve().parents[1] / "routes" / "story_generator.py").read_text(encoding="utf-8")
    assert src.count("await _find_presentation(presentation_id)") == 4
    assert "db.trivia_presentations.find_one({'id': presentation_id})" not in src.split("async def _find_presentation")[1].split("\n@router")[0].replace(
        "getattr(db, coll).find_one({'id': presentation_id})", "")


def test_the_asset_route_looks_for_the_host_by_name_when_there_is_no_host_file(sg):
    src = (Path(__file__).resolve().parents[1] / "routes" / "story_generator.py").read_text(encoding="utf-8")
    assert "_normalize_host_name(host_path or presentation.get('host', ''))" in src
