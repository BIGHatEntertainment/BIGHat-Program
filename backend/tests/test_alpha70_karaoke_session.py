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


# ---------------------------------------------------------------- alpha.95: the overlay and the request QR are ALWAYS on
def test_the_qr_is_always_on_even_if_a_screen_asks_for_it_off(client):
    c, _ = client
    s = start(c, qr_enabled=False)                                   # an old screen asking for "QR off" is ignored
    assert s["qr_enabled"] is True
    assert c.get("/api/karaoke/session/active").json()["session"]["qr_enabled"] is True


def test_the_overlay_cannot_be_switched_off(client):
    c, _ = client
    start(c)
    r = c.post("/api/karaoke/session/overlay", json={"overlay_enabled": False, "qr_enabled": False}).json()
    assert r["overlay_enabled"] is True and r["qr_enabled"] is True
    pb = c.get("/api/karaoke/session/playback").json()
    assert pb["overlay_enabled"] is True and pb["qr_enabled"] is True


def test_an_old_session_saved_with_the_qr_off_still_reports_it_on(client):
    c, k = client
    start(c)
    import asyncio
    asyncio.get_event_loop_policy().new_event_loop().run_until_complete(
        k.db.karaoke_sessions.update_one({"is_active": True}, {"$set": {"qr_enabled": False, "overlay_enabled": False}}))
    pb = c.get("/api/karaoke/session/playback").json()
    assert pb["overlay_enabled"] is True and pb["qr_enabled"] is True


# ---------------------------------------------------------------- alpha.96: why a song could not play is reported to the host
def _playing(c, name="Ann"):
    start(c); add(c, name, "A")
    cur = c.post("/api/karaoke/queue/next").json()["current"]
    c.post("/api/karaoke/session/playback", json={"song_playing": True, "current_singer": cur, "mode": "karaoke"})
    return cur


def test_the_tv_reports_why_a_song_could_not_play(client):
    c, _ = client
    cur = _playing(c)
    assert c.get("/api/karaoke/session/playback").json()["playback"]["video_error"] == ""
    c.post("/api/karaoke/session/audience-report", json={"singer_id": cur["id"], "error": "101"})
    assert c.get("/api/karaoke/session/playback").json()["playback"]["video_error"] == "101"


def test_the_error_survives_the_host_resending_the_same_song_but_not_a_new_song(client):
    c, _ = client
    cur = _playing(c)
    c.post("/api/karaoke/session/audience-report", json={"singer_id": cur["id"], "error": "150"})
    c.post("/api/karaoke/session/playback", json={"song_playing": True, "song_ending": True, "current_singer": cur, "mode": "karaoke"})
    assert c.get("/api/karaoke/session/playback").json()["playback"]["video_error"] == "150"       # same song: kept
    b = add(c, "Bob", "B")
    c.post("/api/karaoke/queue/finish-current")
    cur2 = c.post("/api/karaoke/queue/next").json()["current"]
    c.post("/api/karaoke/session/playback", json={"song_playing": True, "current_singer": cur2, "mode": "karaoke"})
    assert c.get("/api/karaoke/session/playback").json()["playback"]["video_error"] == ""         # a different song starts clean


def test_a_stale_error_for_an_old_song_is_ignored_and_an_empty_error_clears_it(client):
    c, _ = client
    cur = _playing(c)
    assert c.post("/api/karaoke/session/audience-report", json={"singer_id": "someone-else", "error": "100"}).json()["success"] is False
    assert c.get("/api/karaoke/session/playback").json()["playback"]["video_error"] == ""
    c.post("/api/karaoke/session/audience-report", json={"singer_id": cur["id"], "error": "5"})
    c.post("/api/karaoke/session/audience-report", json={"singer_id": cur["id"], "error": ""})
    assert c.get("/api/karaoke/session/playback").json()["playback"]["video_error"] == ""


# ---------------------------------------------------------------- alpha.98: the TV plays the song in a plain iframe and times it from the song's length
def test_the_song_length_and_video_reach_the_tv_exactly_as_the_host_sent_them(client):
    c, _ = client
    start(c)
    a = add(c, "Ann", "A")
    c.post("/api/karaoke/queue/add", json={"assign_to": a["id"], "song_title": "Africa", "song_artist": "Toto",
                                           "embed_url": "https://www.youtube.com/embed/AAA111?autoplay=1", "source": "youtube", "duration_seconds": 295})
    cur = c.post("/api/karaoke/queue/next").json()["current"]
    assert cur["duration_seconds"] == 295 and "AAA111" in cur["embed_url"]
    c.post("/api/karaoke/session/playback", json={"song_playing": True, "current_singer": cur, "mode": "karaoke"})
    seen = c.get("/api/karaoke/session/playback").json()["playback"]               # this is what the TV window reads
    assert seen["song_playing"] is True and seen["current_singer"]["duration_seconds"] == 295
    assert "AAA111" in seen["current_singer"]["embed_url"] and seen["current_singer"]["song_title"] == "Africa"


def test_a_singer_added_from_the_phone_page_has_no_length_so_the_host_ends_the_song(client):
    c, _ = client
    start(c)
    a = add(c, "Bob", "B")
    c.post("/api/karaoke/queue/add", json={"assign_to": a["id"], "song_title": "Creep", "embed_url": "https://www.youtube.com/embed/BBB222", "source": "youtube"})
    cur = c.post("/api/karaoke/queue/next").json()["current"]
    assert not cur.get("duration_seconds")                                           # 0: the TV never ends it by itself
    assert "BBB222" in cur["embed_url"]


def test_the_next_song_is_still_handed_to_the_tv_to_warm(client):
    c, _ = client
    start(c)
    c.post("/api/karaoke/session/preload", json={"singer_id": "s2", "embed_url": "https://www.youtube.com/embed/BBB222?autoplay=1"})
    pre = c.get("/api/karaoke/session/playback").json().get("preload") or c.get("/api/karaoke/session/active").json()["session"].get("preload")
    assert pre and pre["singer_id"] == "s2" and "BBB222" in pre["embed_url"]


# ---------------------------------------------------------------- alpha.99: never offer, or silently start, a video YouTube will not embed
def _item(vid, embeddable=True, privacy="public", upload="processed", rating=None, blocked=None, allowed=None, dur="PT3M"):
    cd = {"duration": dur}
    if rating: cd["contentRating"] = {"ytRating": rating}
    if blocked is not None or allowed is not None:
        cd["regionRestriction"] = {k: v for k, v in (("blocked", blocked), ("allowed", allowed)) if v is not None}
    return {"id": vid, "contentDetails": cd, "status": {"embeddable": embeddable, "privacyStatus": privacy, "uploadStatus": upload}}


def test_the_rules_for_a_video_that_can_play_in_an_embed():
    from routes import karaoke as k
    assert k.playable_in_embed(_item("a")) and k.why_not_playable(_item("a")) == ""
    assert k.playable_in_embed(_item("a", privacy="unlisted"))
    cases = {
        "owner blocked embedding": (_item("a", embeddable=False), "does not allow"),
        "private": (_item("a", privacy="private"), "private"),
        "still processing": (_item("a", upload="uploaded"), "not available yet"),
        "age restricted": (_item("a", rating="ytAgeRestricted"), "age-restricted"),
        "blocked in the US": (_item("a", blocked=["US", "DE"]), "blocked in the United States"),
        "only allowed elsewhere": (_item("a", allowed=["DE", "FR"]), "blocked in the United States"),
    }
    for name, (item, words) in cases.items():
        assert not k.playable_in_embed(item), name
        assert words in k.why_not_playable(item), name
    assert k.playable_in_embed(_item("a", blocked=["DE"])) and k.playable_in_embed(_item("a", allowed=["US", "CA"]))


class _Resp:
    def __init__(self, code, data): self.status_code, self._d = code, data
    def json(self): return self._d


def _fake_httpx(monkeypatch, items=None, search_ids=(), code=200, boom=False):
    import httpx
    class C:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url, params=None, **k):
            if boom: raise httpx.ConnectError("no internet")
            if url.endswith("/search"):
                return _Resp(200, {"items": [{"id": {"videoId": i}, "snippet": {"title": "Song - Karaoke", "channelTitle": "KARAOKE CH", "thumbnails": {}}} for i in search_ids]})
            return _Resp(code, {"items": items if items is not None else []})
    monkeypatch.setattr(httpx, "AsyncClient", C)


def test_search_drops_videos_youtube_says_cannot_be_embedded(client, monkeypatch):
    c, _ = client
    monkeypatch.setenv("YOUTUBE_API_KEY", "KEY123456789")
    _fake_httpx(monkeypatch, search_ids=["good1", "blocked1", "gone1", "age1"],
                items=[_item("good1"), _item("blocked1", embeddable=False), _item("age1", rating="ytAgeRestricted")])   # gone1 is unknown to YouTube
    r = c.get("/api/karaoke/youtube/search", params={"q": "toto africa"}).json()
    assert [x["id"] for x in r["results"]] == ["good1"], r
    assert r["results"][0]["duration_seconds"] == 180


def test_old_cached_searches_from_before_the_check_are_not_reused(client, monkeypatch):
    import asyncio
    c, k = client
    monkeypatch.setenv("YOUTUBE_API_KEY", "KEY123456789")
    asyncio.get_event_loop_policy().new_event_loop().run_until_complete(k.db.youtube_search_cache.insert_one(
        {"query": "toto africa karaoke", "results": [{"id": "blocked-old"}], "cached_at": "2999-01-01T00:00:00+00:00"}))
    _fake_httpx(monkeypatch, search_ids=["good1"], items=[_item("good1")])
    r = c.get("/api/karaoke/youtube/search", params={"q": "toto africa"}).json()
    assert [x["id"] for x in r["results"]] == ["good1"] and not r.get("cached")


def test_check_one_video_says_playable_or_why_not(client, monkeypatch):
    c, _ = client
    monkeypatch.setenv("YOUTUBE_API_KEY", "KEY123456789")
    _fake_httpx(monkeypatch, items=[_item("v1")])
    assert c.get("/api/karaoke/youtube/check/v1").json() == {"known": True, "playable": True, "reason": ""}
    _fake_httpx(monkeypatch, items=[_item("v2", embeddable=False)])
    r = c.get("/api/karaoke/youtube/check/v2").json()
    assert r["known"] is True and r["playable"] is False and "does not allow" in r["reason"]
    _fake_httpx(monkeypatch, items=[])                                                   # YouTube has never heard of it
    r = c.get("/api/karaoke/youtube/check/v3").json()
    assert r["playable"] is False and "removed" in r["reason"]


def test_a_failed_check_never_blocks_the_show(client, monkeypatch):
    c, _ = client
    monkeypatch.setenv("YOUTUBE_API_KEY", "KEY123456789")
    for kwargs in ({"boom": True}, {"code": 403}, {"code": 500}):
        _fake_httpx(monkeypatch, items=[], **kwargs)
        assert c.get("/api/karaoke/youtube/check/v1").json() == {"known": False, "playable": True, "reason": ""}, kwargs
    assert c.get("/api/karaoke/youtube/check/").status_code in (404, 405, 307)
