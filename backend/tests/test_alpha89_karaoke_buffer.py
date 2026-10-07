"""alpha.89: the audience screen reports REAL buffer progress for the next singer's song."""
import sys
from pathlib import Path
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("BIGHAT_NATIVE_MODE", "1")
    (tmp_path / "db").mkdir()
    monkeypatch.setenv("BIGHAT_DB_DIR", str(tmp_path / "db"))
    monkeypatch.setenv("BIGHAT_KARAOKE_SETTINGS", str(tmp_path / "k.json"))
    import importlib
    from native import db_factory
    db_factory._native_client = None
    importlib.reload(db_factory)
    from routes import karaoke
    importlib.reload(karaoke)
    karaoke.set_database(db_factory.get_db())
    app = FastAPI(); app.include_router(karaoke.router, prefix="/api")
    c = TestClient(app)
    assert c.post("/api/karaoke/session/create", json={"location": "Pub One", "host": "Pat"}).status_code == 200
    yield c
    db_factory.close_all()


def pre(c):
    return c.get("/api/karaoke/session/playback").json()["preload"]


def test_host_names_the_next_song_and_it_starts_at_zero(client):
    client.post("/api/karaoke/session/preload", json={"singer_id": "s1", "embed_url": "https://www.youtube.com/embed/AAA?autoplay=1"})
    p = pre(client)
    assert p["singer_id"] == "s1" and p["ready"] is False and p["percent"] == 0


def test_progress_is_saved_and_never_goes_backwards_while_loading(client):
    client.post("/api/karaoke/session/preload", json={"singer_id": "s1", "embed_url": "u"})
    client.post("/api/karaoke/session/preload-report", json={"singer_id": "s1", "percent": 40, "buffered_seconds": 18})
    assert pre(client)["percent"] == 40 and pre(client)["buffered_seconds"] == 18.0
    client.post("/api/karaoke/session/preload-report", json={"singer_id": "s1", "percent": 25})
    assert pre(client)["percent"] == 40                      # a wobble in YouTube's number does not move the bar back
    client.post("/api/karaoke/session/preload-report", json={"singer_id": "s1", "percent": 70})
    assert pre(client)["percent"] == 70 and pre(client)["ready"] is False


def test_ready_sets_everything_to_done(client):
    client.post("/api/karaoke/session/preload", json={"singer_id": "s1", "embed_url": "u"})
    client.post("/api/karaoke/session/preload-report", json={"singer_id": "s1", "percent": 100, "ready": True})
    p = pre(client)
    assert p["ready"] is True and p["percent"] == 100


def test_a_report_for_a_different_singer_is_ignored(client):
    client.post("/api/karaoke/session/preload", json={"singer_id": "s2", "embed_url": "u"})
    r = client.post("/api/karaoke/session/preload-report", json={"singer_id": "s1", "percent": 90, "ready": True})
    assert r.json()["success"] is False
    p = pre(client)
    assert p["singer_id"] == "s2" and p["percent"] == 0 and p["ready"] is False


def test_naming_a_new_next_song_resets_the_bar(client):
    client.post("/api/karaoke/session/preload", json={"singer_id": "s1", "embed_url": "u"})
    client.post("/api/karaoke/session/preload-report", json={"singer_id": "s1", "percent": 100, "ready": True})
    client.post("/api/karaoke/session/preload", json={"singer_id": "s2", "embed_url": "u2"})
    p = pre(client)
    assert p["singer_id"] == "s2" and p["percent"] == 0 and p["ready"] is False
    client.post("/api/karaoke/session/preload", json={})
    assert pre(client) is None


def test_bad_numbers_never_break_it(client):
    client.post("/api/karaoke/session/preload", json={"singer_id": "s1", "embed_url": "u"})
    for bad in ("abc", None, -50, 999):
        assert client.post("/api/karaoke/session/preload-report", json={"singer_id": "s1", "percent": bad}).status_code == 200
    assert 0 <= pre(client)["percent"] <= 100


def test_an_error_is_recorded_and_clears_on_a_new_song(client):
    client.post("/api/karaoke/session/preload", json={"singer_id": "s1", "embed_url": "u"})
    client.post("/api/karaoke/session/preload-report", json={"singer_id": "s1", "error": "youtube_error"})
    assert pre(client)["error"] == "youtube_error"
    client.post("/api/karaoke/session/preload", json={"singer_id": "s1", "embed_url": "u"})
    assert "error" not in pre(client)


# ---------------------------------------------------------------- alpha.93: a failed load is never permanent
def test_retry_stamp_from_the_host_is_stored_so_the_audience_starts_afresh(client):
    client.post("/api/karaoke/session/preload", json={"singer_id": "s1", "embed_url": "u"})
    assert "retry" not in pre(client)
    client.post("/api/karaoke/session/preload", json={"singer_id": "s1", "embed_url": "u", "retry": 12345})
    p = pre(client)
    assert p["singer_id"] == "s1" and p["retry"] == 12345 and p["percent"] == 0 and p["ready"] is False


def test_an_error_is_cleared_once_the_retry_makes_progress(client):
    client.post("/api/karaoke/session/preload", json={"singer_id": "s1", "embed_url": "u"})
    client.post("/api/karaoke/session/preload-report", json={"singer_id": "s1", "error": "no_holder"})
    assert pre(client)["error"] == "no_holder"
    client.post("/api/karaoke/session/preload-report", json={"singer_id": "s1", "percent": 30, "buffered_seconds": 12})
    p = pre(client)
    assert "error" not in p and p["percent"] == 30


def test_an_error_stays_until_there_is_progress(client):
    client.post("/api/karaoke/session/preload", json={"singer_id": "s1", "embed_url": "u"})
    client.post("/api/karaoke/session/preload-report", json={"singer_id": "s1", "error": "youtube_error"})
    client.post("/api/karaoke/session/preload-report", json={"singer_id": "s1", "error": "youtube_error"})
    assert pre(client)["error"] == "youtube_error"
    client.post("/api/karaoke/session/preload-report", json={"singer_id": "s1", "percent": 100, "ready": True})
    p = pre(client)
    assert p["ready"] is True and "error" not in p
