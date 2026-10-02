"""alpha.67: Music Bingo game survives a restart (state saved to the desktop DB)
and the local-mode song code is still present."""
import os, sys, asyncio
from pathlib import Path
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("BIGHAT_NATIVE_MODE", "1")
    monkeypatch.setenv("BIGHAT_DB_DIR", str(tmp_path / "db"))
    import importlib
    from native import db_factory
    db_factory._native_client = None
    importlib.reload(db_factory)
    from routes import bingo
    importlib.reload(bingo)
    bingo.set_database(db_factory.get_db())
    app = FastAPI()
    app.include_router(bingo.router, prefix="/api")
    yield TestClient(app), bingo
    db_factory.close_all()


def _make(c):
    r = c.post("/api/bingo/game/create", json={"bingo_type": "music", "game_type": "lightning",
              "round_type": "traditional", "call_interval": 10, "music_decade": "1990s"})
    assert r.status_code == 200, r.text
    assert c.post("/api/bingo/game/start").status_code == 200


def test_music_game_survives_restart(client):
    c, bingo = client
    _make(c)
    for n, title in ((7, "Song A"), (23, "Song B")):
        r = c.post("/api/bingo/game/call-song", json={"number": n, "title": title, "artist": "X"})
        assert r.status_code == 200, r.text
    before = c.get("/api/bingo/game/state").json()["game"]
    assert before["settings"]["bingo_type"] == "music" and before["settings"]["game_type"] == "lightning"

    bingo.current_game = None            # simulate the app closing and reopening
    bingo.available_numbers = []
    after = c.get("/api/bingo/game/state").json()["game"]
    assert after is not None, "game was not restored after restart"
    assert after["settings"]["music_decade"] == "1990s"
    assert after["settings"]["game_type"] == "lightning"
    assert after["called_songs"] == before["called_songs"] and len(after["called_songs"]) == 2
    assert after["is_active"] is True


def test_no_game_means_no_game(client):
    c, bingo = client
    assert c.get("/api/bingo/game/state").json() == {"game": None}


def test_local_mode_song_code_is_still_here():
    src = (ROOT / "routes" / "bingo.py").read_text()
    for marker in ("_is_local_mode", "_local_bingo_root", "_parse_bingo_xlsx"):
        assert marker in src, marker + " was lost"


def test_new_round_keeps_counting_and_can_switch_theme(client):
    """alpha.68: End Round -> 'next round' keeps the round count and can use a fresh theme."""
    c, bingo = client
    _make(c)                                                     # round 1, 1990s, lightning
    c.post("/api/bingo/game/call-song", json={"number": 5, "title": "Old Song", "artist": "X"})
    assert c.post("/api/bingo/game/end-round").status_code == 200

    r = c.post("/api/bingo/game/new-round", json={"music_decade": "Emo", "game_type": "regular"})
    assert r.status_code == 200 and r.json()["round_number"] == 2
    g = c.get("/api/bingo/game/state").json()["game"]
    assert g["round_number"] == 2
    assert g["settings"]["music_decade"] == "Emo" and g["settings"]["game_type"] == "regular"
    assert g["called_songs"] == [] and g["current_song"] is None and g["called_numbers"] == []
    assert g["is_active"] is False and g["bingo_claimed"] is False

    # the new theme + round survive an app restart
    bingo.current_game = None
    bingo.available_numbers = []
    g2 = c.get("/api/bingo/game/state").json()["game"]
    assert g2["round_number"] == 2 and g2["settings"]["music_decade"] == "Emo"


def test_new_round_without_options_keeps_the_theme(client):
    c, bingo = client
    _make(c)
    c.post("/api/bingo/game/call-song", json={"number": 9, "title": "S", "artist": "A"})
    r = c.post("/api/bingo/game/new-round")                      # no body (Traditional Bingo does this)
    assert r.status_code == 200 and r.json()["round_number"] == 2
    g = c.get("/api/bingo/game/state").json()["game"]
    assert g["settings"]["music_decade"] == "1990s" and g["settings"]["game_type"] == "lightning"
    assert g["called_songs"] == []                               # but songs from round 1 are cleared
    r3 = c.post("/api/bingo/game/new-round", json={"game_type": "nonsense"})
    assert r3.json()["game_type"] == "lightning"                 # a bad value is ignored, not saved


def test_finalizing_the_night_clears_it_for_good(client):
    c, bingo = client
    _make(c)
    c.post("/api/bingo/game/end-round")
    c.post("/api/bingo/game/new-round", json={"music_decade": "Emo"})
    r = c.post("/api/bingo/game/finalize")
    assert r.status_code == 200 and r.json()["summary"]["rounds_played"] == 2
    assert c.get("/api/bingo/game/state").json() == {"game": None}
    bingo.current_game = None                                   # even after a restart it does not come back
    assert c.get("/api/bingo/game/state").json() == {"game": None}


def test_a_night_between_rounds_is_restored_after_restart(client):
    c, bingo = client
    _make(c)
    c.post("/api/bingo/game/end-round")                         # round over, game not active
    bingo.current_game = None
    bingo.available_numbers = []
    g = c.get("/api/bingo/game/state").json()["game"]
    assert g is not None and g["is_active"] is False and g["round_number"] == 1
