"""alpha.80: the Schedule's venues are the single list of places (venue <-> location sync)."""
import asyncio, os, sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from native import venue_sync as vs


class Coll:
    def __init__(self): self.rows = []
    def _match(self, r, q):
        for k, v in q.items():
            if isinstance(v, dict) and "$ne" in v:
                if r.get(k) == v["$ne"]: return False
            elif r.get(k) != v: return False
        return True
    async def find_one(self, q, proj=None): return next((dict(r) for r in self.rows if self._match(r, q)), None)
    def find(self, q=None, proj=None):
        outer = self
        class Cur:
            async def to_list(self, n): return [{k: v for k, v in r.items() if k != "_id"} for r in outer.rows if outer._match(r, q or {})]
        return Cur()
    async def insert_one(self, d): self.rows.append(dict(d))
    async def update_one(self, q, upd):
        for r in self.rows:
            if self._match(r, q): r.update(upd.get("$set", {})); return
    async def count_documents(self, q): return len([r for r in self.rows if self._match(r, q)])


class Db:
    def __init__(self): self.venues, self.locations = Coll(), Coll()


@pytest.fixture(autouse=True)
def _no_disk(monkeypatch):
    monkeypatch.setattr(vs, "_persist", lambda loc: None)         # disk mirroring is covered by the real-app run


def run(c): return asyncio.run(c)
def venue(db, name, **kw):
    v = {"id": f"v-{len(db.venues.rows)+1}", "name": name, "address": "1 Main", **kw}; db.venues.rows.append(v); return v


def test_name_key_ignores_case_spacing_and_punctuation():
    assert vs.name_key("Monkey  Pants") == vs.name_key("monkey_pants") == vs.name_key("MONKEY-PANTS!") == "monkeypants"
    assert vs.name_key("") == vs.name_key(None) == ""


def test_a_new_venue_gets_a_location_linked_both_ways():
    db = Db(); v = venue(db, "Monkey Pants")
    loc = run(vs.ensure_location(db, v))
    assert loc["name"] == "Monkey Pants" and loc["slug"] == "monkey-pants" and loc["venue_id"] == v["id"] and loc["branding_images"] == []
    assert db.venues.rows[0]["location_id"] == loc["id"] and len(db.locations.rows) == 1


def test_running_it_twice_never_duplicates():
    db = Db(); v = venue(db, "Monkey Pants")
    a = run(vs.ensure_location(db, v)); v2 = db.venues.rows[0]; b = run(vs.ensure_location(db, v2))
    assert a["id"] == b["id"] and len(db.locations.rows) == 1


def test_an_existing_location_with_the_same_name_is_linked_not_copied():
    db = Db(); db.locations.rows.append({"id": "L1", "name": "monkey pants", "slug": "monkey-pants", "branding_images": [{"id": "i1"}]})
    v = venue(db, "Monkey Pants"); loc = run(vs.ensure_location(db, v))
    assert loc["id"] == "L1" and len(db.locations.rows) == 1 and db.locations.rows[0]["branding_images"] == [{"id": "i1"}]
    assert db.locations.rows[0]["venue_id"] == v["id"] and db.locations.rows[0]["name"] == "Monkey Pants"


def test_two_venues_whose_names_match_loosely_never_share_one_location():
    db = Db()
    a = venue(db, "Zed's"); la = run(vs.ensure_location(db, a))
    b = venue(db, "Zed S"); lb = run(vs.ensure_location(db, b))                          # a second, different venue
    assert la["id"] != lb["id"] and la["slug"] != lb["slug"] and len(db.locations.rows) == 2
    assert {r["venue_id"] for r in db.locations.rows} == {a["id"], b["id"]}


def test_an_old_location_with_no_venue_is_adopted_by_the_matching_venue():
    db = Db(); db.locations.rows.append({"id": "L-old", "name": "Zeds", "slug": "zeds", "branding_images": [{"id": "pic"}]})
    v = venue(db, "Zed's"); loc = run(vs.ensure_location(db, v))
    assert loc["id"] == "L-old" and len(db.locations.rows) == 1 and db.locations.rows[0]["branding_images"] == [{"id": "pic"}]


def test_rename_changes_the_name_but_not_the_image_folder():
    db = Db(); v = venue(db, "Monkey Pants"); loc = run(vs.ensure_location(db, v))
    v = db.venues.rows[0]; v["name"] = "Monkey Pants Tavern"
    run(vs.rename(db, v))
    row = db.locations.rows[0]
    assert row["name"] == "Monkey Pants Tavern" and row["slug"] == "monkey-pants" and len(db.locations.rows) == 1


def test_delete_retires_the_location_and_keeps_its_images():
    db = Db(); v = venue(db, "Roses"); run(vs.ensure_location(db, v)); db.locations.rows[0]["branding_images"] = [{"id": "i"}]
    run(vs.retire(db, db.venues.rows[0]))
    assert db.locations.rows[0]["retired"] is True and db.locations.rows[0]["branding_images"] == [{"id": "i"}]
    assert run(db.locations.find({"retired": {"$ne": True}}).to_list(10)) == []          # hidden from every list


def test_adding_the_venue_back_revives_the_same_location_with_its_images():
    db = Db(); v = venue(db, "Roses"); run(vs.ensure_location(db, v)); db.locations.rows[0]["branding_images"] = [{"id": "i"}]
    run(vs.retire(db, db.venues.rows[0])); db.venues.rows.clear()
    v2 = venue(db, "roses"); loc = run(vs.ensure_location(db, v2))
    assert len(db.locations.rows) == 1 and loc["retired"] is False and loc["branding_images"] == [{"id": "i"}] and loc["venue_id"] == v2["id"]


def test_reconcile_never_creates_a_schedule_venue_from_a_location():
    """alpha.92 (user): venues are entered in the Schedule ONLY. A location with no venue is just not listed."""
    db = Db()
    db.locations.rows += [{"id": "L1", "name": "Old Town Pub", "slug": "old-town-pub"}]
    venue(db, "Brand New Bar")
    out = run(vs.reconcile(db))
    assert [v["name"] for v in db.venues.rows] == ["Brand New Bar"]                    # no venue made from "Old Town Pub"
    assert {l["name"] for l in db.locations.rows} == {"Old Town Pub", "Brand New Bar"}  # the venue still gets its folder
    assert out["venues_created"] == 0 and out["locations_created"] == 1


def test_reconcile_is_safe_to_run_again_and_again():
    db = Db(); db.locations.rows.append({"id": "L1", "name": "Old Town Pub", "slug": "old-town-pub"}); venue(db, "Bar")
    run(vs.reconcile(db)); snap = (len(db.venues.rows), len(db.locations.rows))
    for _ in range(3):
        out = run(vs.reconcile(db))
    assert (len(db.venues.rows), len(db.locations.rows)) == snap and out["venues_created"] == out["locations_created"] == 0


def test_a_venue_with_no_name_is_ignored():
    db = Db(); assert run(vs.ensure_location(db, {"id": "x", "name": "  "})) is None and db.locations.rows == []


def test_a_broken_database_never_raises():
    class Boom:
        def __getattr__(self, n): raise RuntimeError("db down")
    assert run(vs.ensure_location(Boom(), {"id": "x", "name": "A"})) is None
    run(vs.retire(Boom(), {"id": "x", "name": "A"}))
    assert run(vs.reconcile(Boom()))["venues"] == 0


def test_story_dropdown_lists_every_venue_and_marks_the_missing_pictures(tmp_path, monkeypatch):
    monkeypatch.setenv("BIGHAT_DATA_ROOT", str(tmp_path / "A")); monkeypatch.setenv("BIGHAT_FILES_DIR", str(tmp_path / "D"))
    import importlib
    from native import data_map, story_images as si
    importlib.reload(data_map); importlib.reload(si)
    si.save("bingo", "Monkey Pants", b"\xff\xd8\xff" + b"0" * 50)
    si.save("bingo", "Old Picture Only", b"\xff\xd8\xff" + b"0" * 50)             # a picture whose venue was never made
    got = {l["name"]: l for l in si.locations("bingo", ["Monkey Pants", "Roses", "monkey_pants"])}
    assert got["Monkey Pants"]["has_image"] is True and got["Monkey Pants"]["id"] == "Monkey Pants.jpg"
    assert got["Roses"]["has_image"] is False and got["Roses"]["id"] == ""            # shows up at once, marked "needs a picture"
    assert "Old Picture Only" in got and got["Old Picture Only"]["has_image"] is True  # an earlier upload is never hidden
    assert len([n for n in got if "onkey" in n]) == 1                                  # a name written two ways is one place
    assert [l["name"] for l in si.locations("bingo")] == ["Monkey Pants", "Old Picture Only"]   # no database: pictures only


def test_renaming_a_place_moves_its_story_pictures_so_they_stay_attached(tmp_path, monkeypatch):
    monkeypatch.setenv("BIGHAT_DATA_ROOT", str(tmp_path / "A")); monkeypatch.setenv("BIGHAT_FILES_DIR", str(tmp_path / "D"))
    import importlib
    from native import data_map, story_images as si
    importlib.reload(data_map); importlib.reload(si)
    jpg = b"\xff\xd8\xff" + b"0" * 50
    si.save("trivia", "Roses", jpg); si.save("trivia", "Roses", jpg, variant="background"); si.save("bingo", "Roses", jpg); si.save("karaoke", "Other Bar", jpg)
    assert si.rename_place("Roses", "Roses By The Stairs") == 6        # 3 pictures x (Documents + AppData copy)
    names = lambda k: sorted(f["filename"] for f in si.list_files(k))
    assert names("trivia") == ["Roses By The Stairs.jpg", "Roses By The Stairs_background.jpg"]
    assert names("bingo") == ["Roses By The Stairs.jpg"] and names("karaoke") == ["Other Bar.jpg"]      # other places untouched
    assert si.find("Bingo", "roses by the stairs") is not None and si.find("Bingo", "Roses") is None
    assert (si.backup_root() / "Bingo" / "Roses By The Stairs.jpg").is_file()                         # the safety copy moved too


def test_renaming_never_overwrites_a_picture_that_already_has_the_new_name(tmp_path, monkeypatch):
    monkeypatch.setenv("BIGHAT_DATA_ROOT", str(tmp_path / "A")); monkeypatch.setenv("BIGHAT_FILES_DIR", str(tmp_path / "D"))
    import importlib
    from native import data_map, story_images as si
    importlib.reload(data_map); importlib.reload(si)
    si.save("bingo", "Old Name", b"\xff\xd8\xff" + b"1" * 20)
    (si.root() / "Bingo" / "New Name.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"2" * 20)            # a different file already uses it
    assert si.rename_place("Old Name", "New Name") == 0                      # the new name already has a picture: nothing moves
    assert (si.root() / "Bingo" / "New Name.png").read_bytes().endswith(b"2" * 20)
    assert (si.root() / "Bingo" / "Old Name.jpg").is_file()                  # and the old picture is NOT lost


def test_rename_place_handles_empty_and_unknown_names(tmp_path, monkeypatch):
    monkeypatch.setenv("BIGHAT_DATA_ROOT", str(tmp_path / "A")); monkeypatch.setenv("BIGHAT_FILES_DIR", str(tmp_path / "D"))
    import importlib
    from native import data_map, story_images as si
    importlib.reload(data_map); importlib.reload(si)
    assert si.rename_place("", "X") == 0 and si.rename_place("X", "") == 0 and si.rename_place("Nobody", "Somebody") == 0
    assert si.rename_place("Same Name", "Same Name") == 0
