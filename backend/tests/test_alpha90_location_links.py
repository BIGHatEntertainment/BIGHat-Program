"""alpha.90: a priced venue always finds its place; the list never fails open and never fails."""
import asyncio, sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
pytest.importorskip("montydb")
from native import venue_sync as vs


class Coll:
    def __init__(self, rows): self.rows = rows
    def find(self, q=None, proj=None):
        rows = [dict(r) for r in self.rows if all(r.get(k) == v for k, v in (q or {}).items() if not isinstance(v, dict))]
        class C:
            def __init__(s, r): s.r = r
            async def to_list(s, n): return s.r
            def sort(s, *a, **k): return s
        return C(rows)
    async def find_one(self, q, proj=None):
        for r in self.rows:
            if all(r.get(k) == v for k, v in q.items()): return dict(r)


class DB:
    def __init__(self, venues, pricing, locations):
        self.venues, self.venue_pricing, self.locations = Coll(venues), Coll(pricing), Coll(locations)


def ids(db, game): return asyncio.run(vs.location_ids_for_game(db, game))


def test_venue_pointing_at_a_deleted_location_still_finds_the_place_by_name():
    db = DB([{"id": "v1", "name": "Pub One", "location_id": "GONE"}],
            [{"venue_id": "v1", "trivia_price": 50}],
            [{"id": "L1", "name": "Pub One", "venue_id": "v1"}])
    assert ids(db, "trivia") == {"L1"}


def test_place_that_points_back_at_the_venue_is_found():
    db = DB([{"id": "v1", "name": "Pub One"}], [{"venue_id": "v1", "karaoke_price": 20}],
            [{"id": "L9", "name": "Different Name", "venue_id": "v1"}])
    assert ids(db, "karaoke") == {"L9"}


def test_unpriced_and_other_game_prices_never_show():
    db = DB([{"id": "v1", "name": "A", "location_id": "L1"}, {"id": "v2", "name": "B", "location_id": "L2"}],
            [{"venue_id": "v1", "trivia_price": 50, "music_bingo_price": 0, "karaoke_price": 0}],
            [{"id": "L1", "name": "A", "venue_id": "v1"}, {"id": "L2", "name": "B", "venue_id": "v2"}])
    assert ids(db, "trivia") == {"L1"} and ids(db, "bingo") == set() and ids(db, "karaoke") == set()


def test_a_retired_place_is_never_offered():
    db = DB([{"id": "v1", "name": "A", "location_id": "L1"}], [{"venue_id": "v1", "trivia_price": 50}],
            [{"id": "L1", "name": "A", "venue_id": "v1", "retired": True}])
    assert ids(db, "trivia") == set()


def test_price_zero_point_zero_one_counts():
    db = DB([{"id": "v1", "name": "A", "location_id": "L1"}], [{"venue_id": "v1", "trivia_price": 0.01}],
            [{"id": "L1", "name": "A"}])
    assert ids(db, "trivia") == {"L1"}
