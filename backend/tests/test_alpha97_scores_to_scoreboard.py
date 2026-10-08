"""alpha.97: a night saved by Trivia 'Save & Exit' is found by the Scoreboard (same folder), with no SharePoint."""
import json, sys
from pathlib import Path
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

NIGHT = {"locationName": "Test Venue", "presentationName": "Test Venue - 10/7/2026", "presentationDate": "10/07/2026",
         "teams": [{"name": "Quiz Whiz", "swag": "", "roundScores": [5, 6], "total": 11},
                   {"name": "Brain Trust", "swag": "", "roundScores": [4, 4], "total": 8}],
         "rounds": [{"label": "R1", "multiplier": 1}, {"label": "R2", "multiplier": 1}]}


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("BIGHAT_NATIVE_MODE", "1")
    monkeypatch.setenv("BIGHAT_FILES_DIR", str(tmp_path / "Documents" / "BIG Hat Entertainment"))
    monkeypatch.setenv("BIGHAT_DATA_ROOT", str(tmp_path / "AppData" / "BIGHat" / "data"))
    monkeypatch.setenv("BIGHAT_DB_DIR", str(tmp_path / "db")); (tmp_path / "db").mkdir()
    monkeypatch.delenv("BIGHAT_SHAREPOINT_COPY", raising=False)
    # even a PC that still has the old cloud keys in its environment must not go to Microsoft
    monkeypatch.setenv("AZURE_TENANT_ID", "t"); monkeypatch.setenv("AZURE_CLIENT_ID", "c"); monkeypatch.setenv("AZURE_CLIENT_SECRET", "s")
    import importlib
    from native import db_factory
    db_factory._native_client = None
    importlib.reload(db_factory)
    from routes import scores, scoreboard
    importlib.reload(scores); importlib.reload(scoreboard)
    # a fresh install: the configured assets folder is empty (never the repo's sample "Demo Pub")
    from native.config import config_manager
    (tmp_path / "assets").mkdir()
    monkeypatch.setitem(config_manager.config.setdefault("paths", {}), "assets", str(tmp_path / "assets"))
    db = db_factory.get_db(); scores.set_database(db); scoreboard.set_database(db)
    app = FastAPI(); app.include_router(scores.router, prefix="/api"); app.include_router(scoreboard.router, prefix="/api")
    yield TestClient(app), tmp_path, scoreboard
    db_factory.close_all()


def _no_internet(monkeypatch):
    import httpx
    def boom(*a, **k): raise AssertionError("the program tried to reach the internet")
    monkeypatch.setattr(httpx.AsyncClient, "post", boom, raising=True)
    monkeypatch.setattr(httpx.AsyncClient, "get", boom, raising=True)
    monkeypatch.setattr(httpx.AsyncClient, "put", boom, raising=True)


def test_save_writes_to_documents_and_a_copy_to_appdata_and_never_calls_microsoft(api, monkeypatch):
    c, tmp, _ = api
    _no_internet(monkeypatch)
    r = c.post("/api/scores/save", json=NIGHT)
    assert r.status_code == 200 and r.json()["success"] is True and r.json()["sharedToSharePoint"] is False
    docs = tmp / "Documents" / "BIG Hat Entertainment" / "Files" / "Trivia" / "Scores" / "Test_Venue"
    assert [f.name for f in docs.glob("*.json")] == [r.json()["filename"]]
    safety = tmp / "AppData" / "BIGHat" / "data" / "backups" / "scores" / "Test_Venue" / r.json()["filename"]
    assert safety.is_file()
    assert json.loads(safety.read_text())["teams"][0]["name"] == "Quiz Whiz"


def test_the_scoreboard_finds_the_night_that_trivia_just_saved(api, monkeypatch):
    c, _, _ = api
    _no_internet(monkeypatch)
    saved = c.post("/api/scores/save", json=NIGHT).json()
    listed = c.get("/api/scoreboard/sharepoint/files").json()
    assert listed["source"] == "local" and listed["count"] == 1
    f = listed["files"][0]
    assert f["file_name"] == saved["filename"] and f["venue"] == "Test_Venue"
    content = c.get("/api/scoreboard/sharepoint/file/" + f["file_id"]).json()
    assert [t["name"] for t in content["teams"]] == ["Quiz Whiz", "Brain Trust"] and content["teams"][0]["total"] == 11


def test_sync_copies_the_night_into_the_scoreboard_database(api, monkeypatch):
    c, _, _ = api
    _no_internet(monkeypatch)
    c.post("/api/scores/save", json=NIGHT)
    s = c.post("/api/scoreboard/sharepoint/sync").json()
    assert s["count"] == 1 and s["source"] == "local"
    files = c.get("/api/scoreboard/scores").json()["files"]
    assert len(files) == 1 and files[0]["data"]["teams"][0]["name"] == "Quiz Whiz"


def test_a_file_lost_from_documents_is_still_found_in_the_appdata_copy(api, monkeypatch):
    c, tmp, _ = api
    _no_internet(monkeypatch)
    saved = c.post("/api/scores/save", json=NIGHT).json()
    (tmp / "Documents" / "BIG Hat Entertainment" / "Files" / "Trivia" / "Scores" / "Test_Venue" / saved["filename"]).unlink()
    listed = c.get("/api/scoreboard/sharepoint/files").json()
    assert listed["count"] == 1
    assert c.get("/api/scoreboard/sharepoint/file/" + listed["files"][0]["file_id"]).status_code == 200


def test_the_same_night_is_listed_once_not_twice(api, monkeypatch):
    c, _, _ = api
    _no_internet(monkeypatch)
    c.post("/api/scores/save", json=NIGHT)
    assert c.get("/api/scoreboard/sharepoint/files").json()["count"] == 1      # Documents copy + AppData copy = one entry


def test_two_nights_for_the_same_venue_are_both_kept_and_listed(api, monkeypatch):
    c, _, _ = api
    _no_internet(monkeypatch)
    a = c.post("/api/scores/save", json=NIGHT).json()["filename"]
    b = c.post("/api/scores/save", json=NIGHT).json()["filename"]
    assert a != b
    assert c.get("/api/scoreboard/sharepoint/files").json()["count"] == 2


def test_scoreboard_status_counts_the_same_files(api, monkeypatch):
    c, _, _ = api
    _no_internet(monkeypatch)
    c.post("/api/scores/save", json=NIGHT)
    st = c.get("/api/scoreboard/status").json()
    blob = json.dumps(st)
    assert '"local_files": 1' in blob or '"files": 1' in blob or '"local_venues": 1' in blob, blob[:300]


def test_a_path_outside_the_score_folders_is_refused(api):
    c, _, _ = api
    assert c.get("/api/scoreboard/sharepoint/file/..%2F..%2Fsecret.json").status_code in (400, 404)


def test_sharepoint_is_used_only_when_switched_on_on_purpose(api, monkeypatch):
    c, _, scoreboard = api
    import routes.scores as scores
    calls = []
    async def fake_token(): calls.append(1); return None
    monkeypatch.setattr(scores, "_get_sp_token", fake_token)
    c.post("/api/scores/save", json=NIGHT)
    assert calls == []                                                  # standalone: never even asks for a token
    monkeypatch.setenv("BIGHAT_SHAREPOINT_COPY", "1")
    c.post("/api/scores/save", json=NIGHT)
    assert calls == [1]                                                 # only when someone sets the switch
