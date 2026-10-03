"""alpha.73: trivia scores are stored on the PC (Documents + AppData copy), SharePoint optional."""
import asyncio, json, shutil, sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("BIGHAT_DATA_ROOT", str(tmp_path / "AppData"))
    monkeypatch.setenv("BIGHAT_FILES_DIR", str(tmp_path / "Docs"))
    import importlib
    from native import data_map, scores_store
    importlib.reload(data_map); importlib.reload(scores_store)
    return tmp_path, scores_store


def _req():
    from routes.scores import SaveScoresRequest, TeamScore, RoundConfig
    return SaveScoresRequest(locationName="The Pub / Main", presentationName="Fri", presentationDate="10/03/2026",
        teams=[TeamScore(name="Quizzly Bears", roundScores=[5, 7], total=12), TeamScore(name="B", total=3)],
        rounds=[RoundConfig(label="R1"), RoundConfig(label="R2", multiplier=2)])


def test_save_works_with_no_sharepoint_and_writes_two_copies(env):
    t, ss = env
    import routes.scores as sc
    async def no_token(): return None
    sc._get_sp_token = no_token
    out = asyncio.run(sc.save_scores(_req()))
    assert out["success"] and out["topTeam"] == "Quizzly Bears" and out["sharedToSharePoint"] is False
    rel = out["path"]
    assert (ss.primary_root() / rel).is_file() and (ss.backup_root() / rel).is_file()
    data = json.loads((ss.primary_root() / rel).read_text())
    assert data["rankings"][0] == {"place": 1, "team": "Quizzly Bears", "score": 12} and len(data["teams"]) == 2
    assert ".." not in rel and "/" not in rel.split("/")[0]                      # folder name was cleaned


def test_sharepoint_error_never_loses_the_scores(env):
    t, ss = env
    import routes.scores as sc
    async def boom(): raise RuntimeError("login failed")
    sc._get_sp_token = boom
    out = asyncio.run(sc.save_scores(_req()))
    assert out["success"] and (ss.primary_root() / out["path"]).is_file()


def test_two_nights_same_day_do_not_overwrite(env):
    t, ss = env
    a = ss.save({"location": "Pub", "date": "10/03/2026", "n": 1})
    b = ss.save({"location": "Pub", "date": "10/03/2026", "n": 2})
    assert a["filename"] != b["filename"]
    assert json.loads((ss.primary_root() / a["path"]).read_text())["n"] == 1


def test_list_shape_and_survives_lost_documents_folder(env):
    t, ss = env
    ss.save({"location": "Pub", "date": "d1"}); ss.save({"location": "Bar", "date": "d2"})
    got = ss.list_files()
    assert [g["location"] for g in got] == ["Bar", "Pub"] and got[1]["fileCount"] == 1
    f = got[1]["files"][0]; assert set(f) == {"name", "id", "size", "modified"} and f["id"] == "Pub/" + f["name"]
    shutil.rmtree(ss.primary_root())                                             # Documents lost
    assert [g["fileCount"] for g in ss.list_files()] == [1, 1]
    assert ss.read(f["id"])["location"] == "Pub"                                 # still readable from the safety copy


def test_delete_removes_both_copies_and_rejects_bad_ids(env):
    t, ss = env
    r = ss.save({"location": "Pub", "date": "d"})
    assert ss.delete("../x/y.json") is False and ss.delete("Pub/../../a.json") is False and ss.delete("Pub/notjson.txt") is False
    assert ss.delete(r["path"]) is True
    assert not (ss.primary_root() / r["path"]).exists() and not (ss.backup_root() / r["path"]).exists()
    assert ss.list_files() == [] and ss.delete(r["path"]) is False


def test_a_disk_error_is_reported_not_hidden(env, monkeypatch):
    t, ss = env
    import routes.scores as sc
    from fastapi import HTTPException
    monkeypatch.setattr(ss, "save", lambda p: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(HTTPException) as e:
        asyncio.run(sc.save_scores(_req()))
    assert e.value.status_code == 500 and "disk full" in e.value.detail
