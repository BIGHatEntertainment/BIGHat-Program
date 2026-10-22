"""Scoreboard: Fetch finds score JSON wherever it sits under Files, and Import accepts a plain .json score file.

Reported: Fetch showed nothing, Import only offered .bighat and refused a .json with "please choose a .bighat file".
The program saves score nights as plain JSON, so the Scoreboard must read them.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

NIGHT = {
    "location": "Cornish Pasty Co. (Glendale)", "presentationName": "Cornish Pasty Co. (Glendale) - 10/13/2026",
    "date": "10/13/2026", "presentationId": "abb68cc6",
    "rounds": [{"label": "MC", "multiplier": 1}, {"label": "BIG", "multiplier": 3}],
    "rankings": [{"place": 1, "team": "the 5 D's", "score": 68}],
    "teams": [{"name": "the 5 D's", "swag": "", "roundScores": [10, 26], "total": 68, "rank": 1},
              {"name": "Bread & Butter", "swag": "", "roundScores": [9, 25], "total": 63, "rank": 2}],
}


@pytest.fixture()
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("BIGHAT_NATIVE_MODE", "1")
    monkeypatch.setenv("BIGHAT_FILES_DIR", str(tmp_path / "Documents" / "BIG Hat Entertainment"))
    monkeypatch.setenv("BIGHAT_DATA_ROOT", str(tmp_path / "AppData" / "BIGHat" / "data"))
    monkeypatch.setenv("BIGHAT_DB_DIR", str(tmp_path / "db"))
    (tmp_path / "db").mkdir()
    monkeypatch.delenv("BIGHAT_SHAREPOINT_COPY", raising=False)
    import importlib
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from native import db_factory
    db_factory._native_client = None
    importlib.reload(db_factory)
    from routes import scoreboard
    importlib.reload(scoreboard)
    from native.config import config_manager
    (tmp_path / "assets").mkdir()
    monkeypatch.setitem(config_manager.config.setdefault("paths", {}), "assets", str(tmp_path / "assets"))
    scoreboard.set_database(db_factory.get_db())
    app = FastAPI()
    app.include_router(scoreboard.router, prefix="/api")
    yield TestClient(app), tmp_path
    db_factory.close_all()


def _files(tmp_path):
    return tmp_path / "Documents" / "BIG Hat Entertainment" / "Files"


def _put(tmp_path, sub, venue, name, data=NIGHT):
    d = _files(tmp_path) / sub / venue
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(json.dumps(data, indent=2), encoding="utf-8")


def test_fetch_finds_a_score_file_in_files_scoreboard(api):
    """The reporter's file lived in Files\\Scoreboard\\<venue>\\ and Fetch read only Files\\Trivia\\Scores."""
    c, tmp = api
    _put(tmp, "Scoreboard", "Cornish Pasty Co. Glendale", "Cornish_Pasty_Co._Glendale_10-13-2026.json")
    r = c.post("/api/scoreboard/sharepoint/sync")
    assert r.status_code == 200 and r.json()["count"] == 1
    files = c.get("/api/scoreboard/scores").json()["files"]
    assert len(files) == 1 and files[0]["venue"] == "Cornish Pasty Co. Glendale"
    assert [t["name"] for t in files[0]["data"]["teams"]] == ["the 5 D's", "Bread & Butter"]


def test_fetch_still_finds_files_in_trivia_scores(api):
    c, tmp = api
    _put(tmp, "Trivia/Scores", "Some_Bar", "Some_Bar_10-20-2026.json")
    assert c.post("/api/scoreboard/sharepoint/sync").json()["count"] == 1


def test_same_file_name_in_two_venues_is_kept_twice(api):
    c, tmp = api
    _put(tmp, "Trivia/Scores", "Bar_A", "Night_10-20-2026.json")
    _put(tmp, "Trivia/Scores", "Bar_B", "Night_10-20-2026.json")
    assert c.post("/api/scoreboard/sharepoint/sync").json()["count"] == 2
    assert len(c.get("/api/scoreboard/scores").json()["files"]) == 2


def test_a_broken_json_file_is_skipped_and_the_rest_still_load(api):
    c, tmp = api
    _put(tmp, "Trivia/Scores", "Bar_A", "good_10-20-2026.json")
    d = _files(tmp) / "Trivia" / "Scores" / "Bar_A"
    (d / "broken.json").write_text('{"teams": [', encoding="utf-8")
    r = c.post("/api/scoreboard/sharepoint/sync")
    assert r.status_code == 200 and r.json()["count"] == 1


def test_import_accepts_a_plain_json_score_file(api):
    c, tmp = api
    r = c.post("/api/scoreboard/scores/import", files={"file": ("night.json", json.dumps(NIGHT), "application/json")})
    assert r.status_code == 200, r.text
    assert r.json()["ok"] and r.json()["count"] == 1
    saved = list((_files(tmp) / "Trivia" / "Scores").rglob("*.json"))
    assert len(saved) == 1                                         # saved like any Trivia night
    assert c.get("/api/scoreboard/scores").json()["count"] == 1    # and now shows up in Fetch


def test_importing_the_same_night_twice_never_overwrites(api):
    """v32.1.9 (owner rule: no copies of the same file): the identical night imported again adds NOTHING and says so.
    It used to leave a _2 copy, which showed the same night twice in the dropdown. Nothing is ever overwritten."""
    c, tmp = api
    first = c.post("/api/scoreboard/scores/import", files={"file": ("n.json", json.dumps(NIGHT), "application/json")})
    again = c.post("/api/scoreboard/scores/import", files={"file": ("n.json", json.dumps(NIGHT), "application/json")})
    assert first.status_code == 200 and again.status_code == 200
    assert again.json()["duplicate"] is True and again.json()["filename"] == first.json()["filename"]
    assert len(list((_files(tmp) / "Trivia" / "Scores").rglob("*.json"))) == 1


def test_a_different_night_with_the_same_venue_and_date_is_kept_beside_it_never_overwriting(api):
    c, tmp = api
    other = {**NIGHT, "teams": [{**NIGHT["teams"][0], "total": 999}] + NIGHT["teams"][1:]}
    for body in (NIGHT, other):
        assert c.post("/api/scoreboard/scores/import", files={"file": ("n.json", json.dumps(body), "application/json")}).status_code == 200
    assert len(list((_files(tmp) / "Trivia" / "Scores").rglob("*.json"))) == 2


@pytest.mark.parametrize("body, words", [
    (b"not json at all", "not valid JSON"),
    (json.dumps({"hello": "world"}).encode(), "no list of teams"),
    (json.dumps({"teams": []}).encode(), "no list of teams"),
    (json.dumps({"teams": [{"total": 5}]}).encode(), "needs a name"),
    (json.dumps([1, 2, 3]).encode(), "no list of teams"),
])
def test_import_refuses_files_that_are_not_score_nights_with_a_plain_message(api, body, words):
    c, tmp = api
    r = c.post("/api/scoreboard/scores/import", files={"file": ("x.json", body, "application/json")})
    assert r.status_code == 400 and words in r.json()["detail"]    # a plain STRING, never an object
    assert list(_files(tmp).rglob("*.json")) == []


def test_delete_never_removes_files_from_the_read_only_scoreboard_folder(api):
    from native import scores_store
    c, tmp = api
    _put(tmp, "Scoreboard", "Bar_X", "keep_me.json")
    assert scores_store.delete("Bar_X/keep_me.json") is False
    assert (_files(tmp) / "Scoreboard" / "Bar_X" / "keep_me.json").exists()
