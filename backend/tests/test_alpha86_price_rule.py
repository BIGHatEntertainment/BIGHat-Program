"""alpha.86: the Schedule's venues are the source of truth; a venue is on for a game only when that game's price is above $0."""
import importlib, sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


class Coll:
    def __init__(self): self.rows = []
    def _m(self, r, q):
        for k, v in q.items():
            if isinstance(v, dict) and "$ne" in v:
                if r.get(k) == v["$ne"]: return False
            elif r.get(k) != v: return False
        return True
    async def insert_one(self, d): self.rows.append(dict(d))
    async def find_one(self, q, proj=None, *a, **k):
        for r in self.rows:
            if self._m(r, q): return dict(r)
    def find(self, q, proj=None):
        coll = self
        class C:
            def __init__(s): s.m = [dict(r) for r in coll.rows if coll._m(r, q)]
            def sort(s, k, d=1): s.m.sort(key=lambda r: (r.get(k) or "").lower() if isinstance(r.get(k), str) else r.get(k, 0), reverse=d < 0); return s
            async def to_list(s, n): return s.m[:n]
        return C()


class DB:
    def __init__(self): self.venues, self.venue_pricing, self.locations = Coll(), Coll(), Coll()


@pytest.fixture
def vs(monkeypatch):
    from native import venue_sync
    importlib.reload(venue_sync)
    return venue_sync, DB()


async def add(db, vid, name, t=0, b=0, k=0, loc=True):
    await db.venues.insert_one({"id": vid, "name": name, "location_id": f"L-{vid}" if loc else None})
    if loc: await db.locations.insert_one({"id": f"L-{vid}", "name": name})
    await db.venue_pricing.insert_one({"venue_id": vid, "trivia_price": t, "music_bingo_price": b, "karaoke_price": k})


@pytest.mark.asyncio
async def test_each_game_uses_only_its_own_price(vs):
    v, db = vs
    await add(db, "1", "Trivia Only", t=100); await add(db, "2", "Bingo Only", b=90); await add(db, "3", "Karaoke Only", k=75); await add(db, "4", "All Three", 1, 1, 1); await add(db, "5", "Nothing")
    async def n(g): return [x["name"] for x in await v.venues_for_game(db, g)]
    assert await n("trivia") == ["All Three", "Nothing", "Trivia Only"]      # alpha.92: "Nothing" has no prices at all, so it shows everywhere
    assert await n("bingo") == ["All Three", "Bingo Only", "Nothing"]
    assert await n("karaoke") == ["All Three", "Karaoke Only", "Nothing"]


@pytest.mark.asyncio
async def test_zero_and_missing_prices_hide_a_venue_but_a_cent_shows_it(vs):
    v, db = vs
    await add(db, "1", "Zero", 0, 0, 0); await add(db, "2", "A Cent", 0.01, 0, 0)
    await db.venues.insert_one({"id": "3", "name": "No Pricing Row At All", "location_id": None})              # never priced
    await db.venue_pricing.insert_one({"venue_id": "3", "trivia_price": None, "music_bingo_price": "", "karaoke_price": 0})      # blank values count as $0, not a crash
    # alpha.92: a venue with no prices entered at all (all $0, blank, or no row) is listed everywhere until a game is priced
    assert [x["name"] for x in await v.venues_for_game(db, "trivia")] == ["A Cent", "No Pricing Row At All", "Zero"]
    assert [x["name"] for x in await v.venues_for_game(db, "bingo")] == ["No Pricing Row At All", "Zero"]   # "A Cent" is priced for trivia only
    assert await v.venues_for_game(db, "nonsense") == []


@pytest.mark.asyncio
async def test_location_ids_follow_the_same_rule_and_find_unlinked_places_by_name(vs):
    v, db = vs
    await add(db, "1", "Linked", t=50)
    await db.venues.insert_one({"id": "2", "name": "Unlinked Venue", "location_id": None})
    await db.venue_pricing.insert_one({"venue_id": "2", "trivia_price": 20, "music_bingo_price": 0, "karaoke_price": 0})
    await db.locations.insert_one({"id": "L-found", "name": "Unlinked Venue"})
    assert await v.location_ids_for_game(db, "trivia") == {"L-1", "L-found"}
    assert await v.location_ids_for_game(db, "karaoke") == set()


def test_story_list_with_only_venues_never_adds_unmatched_pictures(monkeypatch, tmp_path):
    from native import story_images
    importlib.reload(story_images)
    fake = [{"variant": "location", "name": "Old Closed Bar", "filename": "Old Closed Bar.png"}, {"variant": "location", "name": "Open Bar", "filename": "Open Bar.png"}]
    monkeypatch.setattr(story_images, "list_files", lambda kind: fake)
    out = story_images.locations("Karaoke", ["Open Bar", "New Bar"], only_venues=True)
    assert [(x["name"], x["has_image"]) for x in out] == [("New Bar", False), ("Open Bar", True)]
    older = story_images.locations("Karaoke", ["Open Bar"])                                       # the old behavior is unchanged without the flag
    assert "Old Closed Bar" in [x["name"] for x in older]
