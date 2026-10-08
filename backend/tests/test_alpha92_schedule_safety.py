"""alpha.92: Schedule data survives a wiped database, and an empty database never erases the copy."""
import asyncio, json, os, tempfile
import pytest

def run(c): return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(c)

class Col:
    def __init__(s): s.rows = []
    def find(s, *a, **k):
        o = s
        class C:
            async def to_list(self, n): return [dict(r) for r in o.rows]
        return C()
    async def count_documents(s, q): return len(s.rows)
    async def insert_one(s, d): s.rows.append(dict(d))

class Db:
    def __init__(s):
        from native import schedule_safety as ss
        for n in ss.COLLECTIONS: setattr(s, n, Col())

@pytest.fixture
def ss(tmp_path, monkeypatch):
    monkeypatch.setenv("BIGHAT_DATA_ROOT", str(tmp_path))
    from native import schedule_safety as m
    return m

def test_every_schedule_tab_is_covered(ss):
    for need in ("employees", "venues", "venue_pricing", "venue_roles", "events", "blackout_dates"):
        assert need in ss.COLLECTIONS

def test_wiped_database_is_restored_from_the_copy(ss):
    db = Db()
    db.venues.rows += [{"id": "v1", "name": "Roses"}, {"id": "v2", "name": "Monkey Pants"}]
    db.venue_pricing.rows += [{"venue_id": "v1", "trivia_price": 100, "music_bingo_price": 90, "karaoke_price": 80}]
    db.venue_roles.rows += [{"venue_id": "v1", "role": "host", "pay": 50}]
    db.events.rows += [{"id": "e1", "venue_id": "v1"}]
    db.employees.rows += [{"id": "p1", "name": "Sam"}]
    out = run(ss.snapshot(db)); assert out["venue_pricing"] == 1 and out["venues"] == 2
    db2 = Db()                                                          # a brand-new, empty database (the "update wiped it" case)
    back = run(ss.restore_if_empty(db2))
    assert db2.venue_pricing.rows[0]["trivia_price"] == 100 and db2.venue_pricing.rows[0]["karaoke_price"] == 80
    assert [v["name"] for v in db2.venues.rows] == ["Roses", "Monkey Pants"]
    assert db2.venue_roles.rows and db2.events.rows and db2.employees.rows and back["venues"] == 2

def test_empty_database_never_erases_the_copy(ss):
    db = Db(); db.venues.rows.append({"id": "v1", "name": "Roses"}); run(ss.snapshot(db))
    run(ss.snapshot(Db()))                                              # a snapshot of an EMPTY database
    assert json.loads((ss.folder() / "venues.json").read_text())[0]["name"] == "Roses"

def test_restore_never_touches_a_collection_that_has_data(ss):
    db = Db(); db.venues.rows.append({"id": "v1", "name": "Roses"}); run(ss.snapshot(db))
    db2 = Db(); db2.venues.rows.append({"id": "v9", "name": "Newer Bar"})
    run(ss.restore_if_empty(db2))
    assert [v["name"] for v in db2.venues.rows] == ["Newer Bar"]

def test_changes_are_copied_and_history_is_kept(ss):
    db = Db(); db.venue_pricing.rows.append({"venue_id": "v1", "trivia_price": 100}); run(ss.snapshot(db))
    db.venue_pricing.rows[0]["trivia_price"] = 125; run(ss.snapshot(db))
    assert json.loads((ss.folder() / "venue_pricing.json").read_text())[0]["trivia_price"] == 125
    assert len(list((ss.folder() / "history" / "venue_pricing").glob("*.json"))) == 1
    assert run(ss.snapshot(db)) == {}                                   # nothing changed, nothing written


# ---------------------------------------------------------------- alpha.97: a visible venue-data.json per venue
class FindCol(Col):
    def find(s, q=None, *a, **k):
        o = s
        class C:
            async def to_list(self, n): return [dict(r) for r in o.rows if all(r.get(k2) == v2 for k2, v2 in (q or {}).items() if k2 != "$and")]
        return C()
    async def count_documents(s, q): return len([r for r in s.rows if all(r.get(k2) == v2 for k2, v2 in (q or {}).items())])


class Db2:
    def __init__(s):
        from native import schedule_safety as ss
        for n in ss.COLLECTIONS: setattr(s, n, FindCol())


def _venue_db():
    db = Db2()
    db.venues.rows.append({"id": "v1", "name": "Test Venue", "address": "1 Main St", "city": "Mesa"})
    db.venues.rows.append({"id": "v2", "name": "Empty Bar"})
    db.venue_pricing.rows.append({"venue_id": "v1", "trivia_price": 100, "music_bingo_price": 90, "karaoke_price": 80})
    db.venue_roles.rows.append({"venue_id": "v1", "role_category": "trivia", "pay": 50})
    db.events.rows.append({"id": "e1", "venue_id": "v1"})
    return db


@pytest.fixture
def ss2(tmp_path, monkeypatch):
    monkeypatch.setenv("BIGHAT_DATA_ROOT", str(tmp_path / "AppData"))
    monkeypatch.setenv("BIGHAT_FILES_DIR", str(tmp_path / "Documents" / "BIG Hat Entertainment"))
    from native import schedule_safety as m
    return m, tmp_path


def test_each_venue_gets_a_readable_file_in_its_documents_folder(ss2):
    ss, tmp = ss2
    out = run(ss.snapshot(_venue_db()))
    f = tmp / "Documents" / "BIG Hat Entertainment" / "Files" / "Locations" / "test-venue" / "venue-data.json"
    assert f.is_file() and out["venue_files"] == 1
    d = json.loads(f.read_text())
    assert d["venue"]["name"] == "Test Venue" and d["pricing"][0]["trivia_price"] == 100 and d["pricing"][0]["karaoke_price"] == 80
    assert d["roles"][0]["pay"] == 50 and d["events"][0]["id"] == "e1"


def test_a_venue_with_nothing_entered_gets_no_empty_file(ss2):
    ss, tmp = ss2
    run(ss.snapshot(_venue_db()))
    assert not (tmp / "Documents" / "BIG Hat Entertainment" / "Files" / "Locations" / "empty-bar" / "venue-data.json").exists()


def test_unchanged_data_is_not_rewritten(ss2):
    ss, _ = ss2
    db = _venue_db()
    run(ss.snapshot(db))
    assert "venue_files" not in run(ss.snapshot(db))


def test_prices_come_back_from_the_venue_file_when_the_database_lost_them(ss2):
    ss, _ = ss2
    run(ss.snapshot(_venue_db()))
    db2 = Db2()                                                          # venues survived, prices were lost
    db2.venues.rows.append({"id": "v1", "name": "Test Venue"})
    assert run(ss.restore_venue_files(db2)) == 3
    assert db2.venue_pricing.rows[0]["trivia_price"] == 100 and db2.venue_pricing.rows[0]["venue_id"] == "v1"


def test_restoring_never_overwrites_prices_that_are_there_and_never_doubles_them(ss2):
    ss, _ = ss2
    run(ss.snapshot(_venue_db()))
    db2 = Db2(); db2.venues.rows.append({"id": "v1", "name": "Test Venue"})
    db2.venue_pricing.rows.append({"venue_id": "v1", "trivia_price": 555})
    run(ss.restore_venue_files(db2))
    assert [r["trivia_price"] for r in db2.venue_pricing.rows] == [555]
    # the whole database empty: the combined restore fills it, then the venue restore must not add a second copy
    db3 = Db2(); run(ss.restore_if_empty(db3)); run(ss.restore_venue_files(db3))
    assert len(db3.venue_pricing.rows) == 1 and len(db3.venue_roles.rows) == 1 and len(db3.events.rows) == 1
