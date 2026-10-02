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
