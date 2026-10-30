"""v32.2.5: the host can rearrange the singer queue. Real karaoke router + real database; the singer on stage must never move,
the next singer is always the first WAITING one, and a short/stale/odd list can never duplicate or drop a position."""
import sys
from pathlib import Path
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("BIGHAT_NATIVE_MODE", "1")
    (tmp_path / "db").mkdir()
    monkeypatch.setenv("BIGHAT_DB_DIR", str(tmp_path / "db"))
    monkeypatch.setenv("BIGHAT_KARAOKE_SETTINGS", str(tmp_path / "k.json"))
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    import importlib
    from native import db_factory
    db_factory._native_client = None
    importlib.reload(db_factory)
    from routes import karaoke
    importlib.reload(karaoke)
    karaoke.set_database(db_factory.get_db())
    app = FastAPI(); app.include_router(karaoke.router, prefix="/api")
    yield TestClient(app)
    db_factory.close_all()


def night(c, names, on_stage=True):
    c.post("/api/karaoke/session/create", json={"location": "Pub", "host": "Pat"})
    ids = {}
    for n in names:
        ids[n] = c.post("/api/karaoke/queue/add", json={"singer_name": n, "song_title": "S " + n,
                                                          "embed_url": "https://www.youtube.com/embed/" + n}).json()["entry"]["id"]
    if on_stage:
        c.post("/api/karaoke/queue/next")                      # the first singer goes on stage
    return ids


def order(c): return [(e["singer_name"], e["status"], e["position"]) for e in c.get("/api/karaoke/queue").json()["queue"]]
def names(c): return [n for n, _, _ in order(c)]


def save(c, ids, wanted): return c.post("/api/karaoke/queue/reorder", json={"order": [ids[n] for n in wanted]})


def test_drag_up_with_a_singer_on_stage_moves_only_that_singer(client):
    c = client; ids = night(c, ["CUR", "A", "B", "C", "D"])
    assert [s for _, s, _ in order(c)][0] == "current"
    save(c, ids, ["CUR", "C", "A", "B", "D"])                  # what the fixed screen sends
    assert names(c) == ["CUR", "C", "A", "B", "D"]
    assert [s for _, s, _ in order(c)] == ["current", "waiting", "waiting", "waiting", "waiting"]


def test_positions_are_unique_and_gapless_after_any_move(client):
    c = client; ids = night(c, ["CUR", "A", "B", "C", "D"])
    for wanted in (["CUR", "D", "A", "B", "C"], ["CUR", "B", "C", "D", "A"], ["CUR", "A", "B", "C", "D"]):
        save(c, ids, wanted)
        assert [p for _, _, p in order(c)] == [0, 1, 2, 3, 4] and names(c) == wanted


def test_a_short_list_cannot_drop_or_duplicate_anyone(client):
    c = client; ids = night(c, ["CUR", "A", "B", "C", "D"])
    save(c, ids, ["C", "A"])                                   # only two named: the rest keep their order after them
    got = order(c)
    assert [n for n, _, _ in got] == ["C", "A", "CUR", "B", "D"] and [p for _, _, p in got] == [0, 1, 2, 3, 4]


def test_unknown_and_repeated_ids_are_ignored(client):
    c = client; ids = night(c, ["CUR", "A", "B"])
    r = c.post("/api/karaoke/queue/reorder", json={"order": [ids["B"], "ghost", ids["B"], ids["A"], None]})
    assert r.json()["success"] and names(c) == ["B", "A", "CUR"]


def test_the_next_singer_is_the_first_waiting_one_and_still_loads(client):
    c = client; ids = night(c, ["CUR", "A", "B", "C"])
    save(c, ids, ["CUR", "C", "A", "B"])
    first_waiting = next(n for n, s, _ in order(c) if s == "waiting")
    assert first_waiting == "C"
    nxt = c.post("/api/karaoke/queue/next").json()
    assert nxt["current"]["singer_name"] == "C" and nxt["current"]["embed_url"].endswith("/C")      # same song, ready to preload


def test_no_singer_on_stage_still_works(client):
    c = client; ids = night(c, ["A", "B", "C"], on_stage=False)
    save(c, ids, ["C", "B", "A"])
    assert names(c) == ["C", "B", "A"]


def test_an_empty_or_missing_order_changes_nothing(client):
    c = client; ids = night(c, ["CUR", "A", "B"])
    before = order(c)
    assert c.post("/api/karaoke/queue/reorder", json={"order": []}).json()["success"]
    assert c.post("/api/karaoke/queue/reorder", json={}).json()["success"]
    assert order(c) == before
