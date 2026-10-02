"""alpha.70: Karaoke session, queue, audience clock, QR requests, YouTube search (mocked)."""
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
    yield TestClient(app), karaoke
    db_factory.close_all()


def start(c, **kw):
    return c.post("/api/karaoke/session/create", json={"location": "Pub One", "host": "Pat", **kw}).json()["session"]


def add(c, name, song="", **kw):
    return c.post("/api/karaoke/queue/add", json={"singer_name": name, "song_title": song, **kw}).json()["entry"]


def test_session_create_active_end(client):
    c, _ = client
    assert c.get("/api/karaoke/session/active").json()["session"] is None
    s = start(c, qr_enabled=True)
    a = c.get("/api/karaoke/session/active").json()["session"]
    assert a["id"] == s["id"] and a["location"] == "Pub One" and a["mode"] == "filler" and a["qr_enabled"] is True
    assert c.post("/api/karaoke/session/end").json()["success"]
    assert c.get("/api/karaoke/session/active").json()["session"] is None


def test_a_new_night_starts_clean(client):
    c, _ = client
    start(c); add(c, "Old Singer", "Old Song")
    c.post("/api/karaoke/request-song", json={"singer_name": "Old", "song_title": "x"})
    start(c)
    assert c.get("/api/karaoke/queue").json()["queue"] == []
    assert c.get("/api/karaoke/requests/pending").json()["requests"] == []


def test_queue_add_assign_reorder_remove(client):
    c, _ = client
    start(c)
    a, b, d = add(c, "Ann"), add(c, "Bob"), add(c, "Cy")
    assert [e["singer_name"] for e in c.get("/api/karaoke/queue").json()["queue"]] == ["Ann", "Bob", "Cy"]
    c.post("/api/karaoke/queue/add", json={"assign_to": b["id"], "song_title": "Wonderwall", "embed_url": "https://www.youtube.com/embed/abc", "duration_seconds": 240})
    bob = next(e for e in c.get("/api/karaoke/queue").json()["queue"] if e["id"] == b["id"])
    assert bob["song_title"] == "Wonderwall" and bob["duration_seconds"] == 240
    c.post("/api/karaoke/queue/reorder", json={"order": [d["id"], a["id"], b["id"]]})
    assert [e["singer_name"] for e in c.get("/api/karaoke/queue").json()["queue"]] == ["Cy", "Ann", "Bob"]
    c.delete(f"/api/karaoke/queue/{a['id']}")
    assert [e["singer_name"] for e in c.get("/api/karaoke/queue").json()["queue"]] == ["Cy", "Bob"]


def test_next_singer_rotation_and_song_cleared(client):
    c, _ = client
    start(c)
    a = add(c, "Ann", "Song A", embed_url="https://www.youtube.com/embed/aaa")
    add(c, "Bob", "Song B"); add(c, "Cy", "Song C")
    cur = c.post("/api/karaoke/queue/next").json()["current"]
    assert cur["singer_name"] == "Ann" and cur["status"] == "current"
    nxt = c.post("/api/karaoke/queue/next").json()["current"]
    assert nxt["singer_name"] == "Bob"
    q = c.get("/api/karaoke/queue").json()["queue"]
    ann = next(e for e in q if e["id"] == a["id"])
    assert ann["status"] == "waiting" and ann["song_title"] == "" and ann["embed_url"] == ""      # back in line, song cleared
    assert [e["singer_name"] for e in q if e["status"] == "waiting"] == ["Cy", "Ann"]


def test_finish_current_does_not_start_the_next_singer(client):
    c, _ = client
    start(c); add(c, "Ann", "A"); add(c, "Bob", "B")
    c.post("/api/karaoke/queue/next")
    c.post("/api/karaoke/queue/finish-current")
    q = c.get("/api/karaoke/queue").json()["queue"]
    assert not any(e["status"] == "current" for e in q)
    assert [e["singer_name"] for e in q] == ["Bob", "Ann"]


def test_next_on_empty_queue(client):
    c, _ = client
    start(c)
    r = c.post("/api/karaoke/queue/next").json()
    assert r["success"] and r["current"] is None


def test_audience_is_the_clock_for_the_current_song(client):
    c, _ = client
    start(c); add(c, "Ann", "A")
    cur = c.post("/api/karaoke/queue/next").json()["current"]
    c.post("/api/karaoke/session/playback", json={"song_playing": True, "current_singer": cur, "mode": "karaoke"})
    pb = c.get("/api/karaoke/session/playback").json()["playback"]
    assert pb["audience_started"] is False and pb["audience_time"] == 0
    c.post("/api/karaoke/session/audience-report", json={"singer_id": cur["id"], "started": True, "duration": 200})
    c.post("/api/karaoke/session/audience-report", json={"singer_id": cur["id"], "time": 37.5})
    pb = c.get("/api/karaoke/session/playback").json()["playback"]
    assert pb["audience_started"] is True and pb["audience_time"] == 37.5 and pb["audience_duration"] == 200
    # the host re-sending the same song keeps the audience's clock (no reset, no jump)
    c.post("/api/karaoke/session/playback", json={"song_playing": True, "song_ending": True, "current_singer": cur, "mode": "karaoke"})
    pb = c.get("/api/karaoke/session/playback").json()["playback"]
    assert pb["audience_time"] == 37.5 and pb["song_ending"] is True
    c.post("/api/karaoke/session/audience-report", json={"singer_id": cur["id"], "ended": True})
    assert c.get("/api/karaoke/session/playback").json()["playback"]["video_ended"] is True


def test_a_new_song_resets_the_audience_clock_and_stale_reports_are_ignored(client):
    c, _ = client
    start(c); add(c, "Ann", "A"); add(c, "Bob", "B")
    ann = c.post("/api/karaoke/queue/next").json()["current"]
    c.post("/api/karaoke/session/playback", json={"song_playing": True, "current_singer": ann, "mode": "karaoke"})
    c.post("/api/karaoke/session/audience-report", json={"singer_id": ann["id"], "started": True, "time": 99})
    bob = c.post("/api/karaoke/queue/next").json()["current"]
    c.post("/api/karaoke/session/playback", json={"song_playing": True, "current_singer": bob, "mode": "karaoke"})
    pb = c.get("/api/karaoke/session/playback").json()["playback"]
    assert pb["audience_started"] is False and pb["audience_time"] == 0 and pb["video_ended"] is False
    late = c.post("/api/karaoke/session/audience-report", json={"singer_id": ann["id"], "ended": True}).json()
    assert late["success"] is False                                                   # Ann's late 'ended' must not end Bob's song
    assert c.get("/api/karaoke/session/playback").json()["playback"]["video_ended"] is False


def test_qr_request_flow(client):
    c, _ = client
    start(c); add(c, "Ann", "A"); add(c, "Bob", "B")
    r = c.post("/api/karaoke/request-song", json={"singer_name": "Zed", "song_title": "Africa", "song_artist": "Toto"}).json()
    rid = r["request_id"]
    assert c.get(f"/api/karaoke/request-status/{rid}").json()["status"] == "pending"
    pend = c.get("/api/karaoke/requests/pending").json()["requests"]
    assert len(pend) == 1 and pend[0]["singer_name"] == "Zed"
    c.post(f"/api/karaoke/requests/{rid}/accept")
    st = c.get(f"/api/karaoke/request-status/{rid}").json()
    assert st["status"] == "accepted" and st["position"] == 2                         # two singers were ahead
    q = c.get("/api/karaoke/queue").json()["queue"]
    zed = next(e for e in q if e["singer_name"] == "Zed")
    assert zed["song_title"] == "Africa" and zed["song_artist"] == "Toto" and zed["source"] == "qr"
    assert c.get("/api/karaoke/requests/pending").json()["requests"] == []
    r2 = c.post("/api/karaoke/request-song", json={"singer_name": "Yan", "song_title": "Creep"}).json()["request_id"]
    c.post(f"/api/karaoke/requests/{r2}/reject")
    assert c.get(f"/api/karaoke/request-status/{r2}").json()["status"] == "rejected"
    assert not any(e["singer_name"] == "Yan" for e in c.get("/api/karaoke/queue").json()["queue"])


def test_qr_request_validation(client):
    c, _ = client
    start(c)
    assert c.post("/api/karaoke/request-song", json={"singer_name": "", "song_title": "x"}).status_code == 400
    assert c.post("/api/karaoke/request-song", json={"singer_name": "A", "song_title": ""}).status_code == 400
    assert c.post("/api/karaoke/request-song", json={"singer_name": "A" * 61, "song_title": "x"}).status_code == 400
    assert c.get("/api/karaoke/request-status/nope").status_code == 404
    assert c.post("/api/karaoke/requests/nope/accept").status_code == 404


def test_youtube_needs_a_key_then_searches_caches_and_sorts(client, monkeypatch):
    c, k = client
    assert c.get("/api/karaoke/youtube/search", params={"q": "africa"}).status_code == 400          # no key yet
    from native import karaoke_library as kl
    kl.save_settings(youtube_api_key="TESTKEY123456789")
    calls = []

    class Resp:
        def __init__(self, code, data): self.status_code, self._d = code, data
        def json(self): return self._d

    class FakeClient:
        def __init__(self, *a, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url, params=None):
            calls.append((url, dict(params)))
            if url.endswith("/search"):
                return Resp(200, {"items": [
                    {"id": {"videoId": "v_other"}, "snippet": {"title": "Africa (Cover)", "channelTitle": "Some Guy", "thumbnails": {}}},
                    {"id": {"videoId": "v_kf"}, "snippet": {"title": "Africa", "channelTitle": "KaraFun Karaoke", "thumbnails": {}}}]})
            return Resp(200, {"items": [{"id": "v_kf", "contentDetails": {"duration": "PT4M5S"}}, {"id": "v_other", "contentDetails": {"duration": "PT1H1M1S"}}]})

    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    r = c.get("/api/karaoke/youtube/search", params={"q": "africa"}).json()
    assert [x["id"] for x in r["results"]] == ["v_kf", "v_other"]                                    # trusted karaoke channel first
    assert r["results"][0]["duration_seconds"] == 245 and r["results"][1]["duration_seconds"] == 3661
    assert r["results"][0]["embed_url"].startswith("https://www.youtube.com/embed/v_kf")
    assert calls[0][1]["key"] == "TESTKEY123456789" and calls[0][1]["q"] == "africa karaoke"
    n = len(calls)
    again = c.get("/api/karaoke/youtube/search", params={"q": "Africa"}).json()
    assert again["cached"] is True and len(calls) == n                                               # second search costs no quota
    assert c.get("/api/karaoke/youtube/search", params={"q": "a"}).json() == {"results": []}


def test_preload_is_only_ready_when_the_audience_says_so(client):
    c, _ = client
    start(c)
    assert c.get("/api/karaoke/session/playback").json()["preload"] is None
    c.post("/api/karaoke/session/preload", json={"singer_id": "s9", "embed_url": "https://www.youtube.com/embed/ZZZ"})
    pre = c.get("/api/karaoke/session/playback").json()["preload"]
    assert pre["singer_id"] == "s9" and pre["ready"] is False                      # asked for, not loaded yet
    assert c.post("/api/karaoke/session/preload-report", json={"singer_id": "someone_else", "ready": True}).json()["success"] is False
    assert c.get("/api/karaoke/session/playback").json()["preload"]["ready"] is False   # a report for a different song is ignored
    assert c.post("/api/karaoke/session/preload-report", json={"singer_id": "s9", "ready": True}).json()["success"] is True
    assert c.get("/api/karaoke/session/playback").json()["preload"]["ready"] is True
    c.post("/api/karaoke/session/preload", json={})                                  # nobody next -> cleared
    assert c.get("/api/karaoke/session/playback").json()["preload"] is None


def test_pause_and_play_do_not_lose_the_audience_clock_or_duration(client):
    """The host can only start the fade if it still knows the song length after a pause / play."""
    c, _ = client
    start(c); add(c, "Ann", "A")
    ann = c.post("/api/karaoke/queue/next").json()["current"]
    c.post("/api/karaoke/session/playback", json={"song_playing": True, "current_singer": ann, "mode": "karaoke"})
    c.post("/api/karaoke/session/audience-report", json={"singer_id": ann["id"], "started": True, "duration": 200})
    c.post("/api/karaoke/session/audience-report", json={"singer_id": ann["id"], "time": 61})
    for playing in (False, True, False, True):                                   # pause, play, pause, play
        c.post("/api/karaoke/session/playback", json={"song_playing": playing, "current_singer": ann, "mode": "karaoke"})
    pb = c.get("/api/karaoke/session/playback").json()["playback"]
    assert pb["audience_duration"] == 200 and pb["audience_time"] == 61 and pb["audience_started"] is True
    # but a DIFFERENT singer starts from zero, including the duration
    c.post("/api/karaoke/session/playback", json={"song_playing": True, "current_singer": {"id": "other", "singer_name": "Z"}, "mode": "karaoke"})
    pb = c.get("/api/karaoke/session/playback").json()["playback"]
    assert pb["audience_duration"] == 0 and pb["audience_time"] == 0 and pb["audience_started"] is False
