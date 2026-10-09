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
class _Resp:
    def __init__(self, code, data): self.status_code, self._d = code, data
    def json(self): return self._d


def _item(vid, embeddable=True, privacy="public", upload="processed", rating=None, blocked=None, allowed=None, dur="PT3M"):
    cd = {"duration": dur}
    if rating: cd["contentRating"] = {"ytRating": rating}
    if blocked is not None or allowed is not None:
        cd["regionRestriction"] = {k: v for k, v in (("blocked", blocked), ("allowed", allowed)) if v is not None}
    return {"id": vid, "contentDetails": cd, "status": {"embeddable": embeddable, "privacyStatus": privacy, "uploadStatus": upload}}


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


# ---------------------------------------------------------------------------------------------------------------
# alpha.104: the prototype's YouTube search (yt-dlp, no key, no daily quota), ported as written.
# yt-dlp is replaced by a fake that returns what yt-dlp's extract_flat really returns (id, title, channel, duration).
# ---------------------------------------------------------------------------------------------------------------
def _yt_entries(*rows):
    return [{"id": i, "title": t, "channel": ch, "duration": d} for (i, t, ch, d) in rows]


def _fake_ytdlp(monkeypatch, entries, boom_times=0):
    import sys, types
    state = {"calls": [], "boom": boom_times}
    class YDL:
        def __init__(self, opts): state["opts"] = opts
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def extract_info(self, q, download=False):
            state["calls"].append(q)
            if state["boom"] > 0:
                state["boom"] -= 1
                raise RuntimeError("yt-dlp hiccup")
            return {"entries": entries}
    mod = types.ModuleType("yt_dlp"); mod.YoutubeDL = YDL
    monkeypatch.setitem(sys.modules, "yt_dlp", mod)
    return state


def test_alpha104_search_uses_ytdlp_with_no_key_and_the_prototype_fields(client, monkeypatch):
    c, _ = client
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    st = _fake_ytdlp(monkeypatch, _yt_entries(("aaaaaaaaaaa", "Africa - Karaoke", "Some Guy", 245)))
    r = c.get("/api/karaoke/youtube/search", params={"q": "africa"})
    assert r.status_code == 200, r.text                                   # NO key needed (the old search answered 400)
    res = r.json()["results"]
    assert st["calls"] == ["ytsearch12:africa karaoke"], st["calls"]      # "{q} karaoke", up to 12 results
    assert res[0]["id"] == "aaaaaaaaaaa" and res[0]["artist"] == "Some Guy" and res[0]["duration_seconds"] == 245
    assert res[0]["embed_url"] == "https://www.youtube.com/embed/aaaaaaaaaaa?autoplay=1&controls=0&rel=0&modestbranding=1"
    assert res[0]["thumbnail"] == "https://i.ytimg.com/vi/aaaaaaaaaaa/mqdefault.jpg" and res[0]["source"] == "youtube"
    assert st["opts"]["extract_flat"] is True and st["opts"]["noplaylist"] is True


def test_alpha104_second_search_comes_from_the_24h_cache(client, monkeypatch):
    c, _ = client
    st = _fake_ytdlp(monkeypatch, _yt_entries(("aaaaaaaaaaa", "Africa", "X", 100)))
    c.get("/api/karaoke/youtube/search", params={"q": "Africa"})
    again = c.get("/api/karaoke/youtube/search", params={"q": "africa"}).json()
    assert again.get("cached") is True and len(st["calls"]) == 1, (again, st["calls"])


def test_alpha104_provider_channels_are_ranked_first_and_nothing_is_dropped(client, monkeypatch):
    c, _ = client
    _fake_ytdlp(monkeypatch, _yt_entries(("o1o1o1o1o1o", "Song (Cover)", "Some Guy", 10), ("p1p1p1p1p1p", "Song", "PARTY TYME KARAOKE CHANNEL", 20),
                                         ("s1s1s1s1s1s", "Song", "Sing King", 30), ("o2o2o2o2o2o", "Song 2", "Another", 40)))
    ids = [x["id"] for x in c.get("/api/karaoke/youtube/search", params={"q": "song"}).json()["results"]]
    assert ids == ["p1p1p1p1p1p", "s1s1s1s1s1s", "o1o1o1o1o1o", "o2o2o2o2o2o"], ids       # providers first, order kept, none dropped


def test_alpha104_blocked_videos_are_dropped_when_a_key_is_saved(client, monkeypatch):
    c, _ = client
    monkeypatch.setenv("YOUTUBE_API_KEY", "KEY123456789")
    _fake_ytdlp(monkeypatch, _yt_entries(("good1good1g", "A", "X", 0), ("blck1blck1b", "B", "X", 0), ("priv1priv1p", "C", "X", 0)))
    _fake_httpx(monkeypatch, items=[_item("good1good1g"), _item("blck1blck1b", embeddable=False), _item("priv1priv1p", privacy="private")])
    res = c.get("/api/karaoke/youtube/search", params={"q": "mix"}).json()["results"]
    assert [x["id"] for x in res] == ["good1good1g"], res
    assert res[0]["duration_seconds"] == 180                              # the API's exact duration replaces the scraped one


def test_alpha104_if_every_result_is_blocked_the_original_list_is_returned(client, monkeypatch):
    c, _ = client                                                         # prototype: "never hand back an empty list purely due to filtering"
    monkeypatch.setenv("YOUTUBE_API_KEY", "KEY123456789")
    _fake_ytdlp(monkeypatch, _yt_entries(("blck1blck1b", "B", "X", 0), ("blck2blck2b", "C", "X", 0)))
    _fake_httpx(monkeypatch, items=[_item("blck1blck1b", embeddable=False), _item("blck2blck2b", embeddable=False)])
    res = c.get("/api/karaoke/youtube/search", params={"q": "allblocked"}).json()["results"]
    assert [x["id"] for x in res] == ["blck1blck1b", "blck2blck2b"], res


def test_alpha104_a_failed_embeddable_check_returns_the_unfiltered_list(client, monkeypatch):
    c, _ = client
    monkeypatch.setenv("YOUTUBE_API_KEY", "KEY123456789")
    _fake_ytdlp(monkeypatch, _yt_entries(("aaaaaaaaaaa", "A", "X", 5)))
    _fake_httpx(monkeypatch, items=[], code=403)                          # quota used up / bad key
    res = c.get("/api/karaoke/youtube/search", params={"q": "nocheck"}).json()["results"]
    assert [x["id"] for x in res] == ["aaaaaaaaaaa"], res


def test_alpha104_ytdlp_gets_one_retry_then_the_similar_cached_search_is_used(client, monkeypatch):
    import asyncio
    c, k = client
    st = _fake_ytdlp(monkeypatch, _yt_entries(("aaaaaaaaaaa", "A", "X", 5)), boom_times=1)
    ok = c.get("/api/karaoke/youtube/search", params={"q": "retry me"}).json()
    assert [x["id"] for x in ok["results"]] == ["aaaaaaaaaaa"] and len(st["calls"]) == 2          # first call failed, the retry worked
    st2 = _fake_ytdlp(monkeypatch, [], boom_times=5)
    fz = c.get("/api/karaoke/youtube/search", params={"q": "retry other"}).json()                 # new query, yt-dlp down: fuzzy cache on the first word
    assert fz.get("fuzzy") is True and [x["id"] for x in fz["results"]] == ["aaaaaaaaaaa"], fz


def test_alpha104_only_the_60_most_recent_searches_are_kept(client, monkeypatch):
    import asyncio
    c, k = client
    _fake_ytdlp(monkeypatch, _yt_entries(("aaaaaaaaaaa", "A", "X", 5)))
    for n in range(65):
        c.get("/api/karaoke/youtube/search", params={"q": f"song number {n:03d}"})
    total = asyncio.get_event_loop_policy().new_event_loop().run_until_complete(k.db.youtube_search_cache.count_documents({}))
    assert total == 60, total


def test_alpha104_pre_warm_does_nothing(client):
    c, _ = client
    assert c.post("/api/karaoke/youtube/pre-warm").json() == {"success": True, "skipped": True, "reason": "yt-dlp search is unlimited; pre-warm not needed"}

