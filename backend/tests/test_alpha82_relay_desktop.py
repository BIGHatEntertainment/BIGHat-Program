"""alpha.82: desktop side of the QR relay (client never raises; karaoke bridge dedupes and reports answers)."""
import asyncio, importlib
import pytest


class Coll:
    def __init__(self): self.rows = []
    async def find_one(self, q, *a, **k):
        for r in self.rows:
            if all(r.get(k) == v for k, v in q.items()): return r
    async def insert_one(self, d): self.rows.append(dict(d))


class DB:
    def __init__(self): self.karaoke_requests = Coll()


@pytest.fixture
def kr(monkeypatch):
    from native import relay_client, karaoke_relay
    importlib.reload(karaoke_relay)
    calls = {"open": 0, "pull": [], "close": 0}
    queue = {"requests": [], "fail": False}

    async def open_night(venue):
        calls["open"] += 1
        return {"ok": True, "session": "S1", "url": "https://api.example/k/S1"}
    async def pull(sid, answers=None):
        calls["pull"].append(list(answers or []))
        if queue["fail"]: return {"ok": False, "error": "offline"}
        out, queue["requests"] = queue["requests"], []
        return {"ok": True, "requests": out}
    async def close_night(sid): calls["close"] += 1; return {"ok": True}
    monkeypatch.setattr(karaoke_relay.relay_client, "open_night", open_night)
    monkeypatch.setattr(karaoke_relay.relay_client, "pull", pull)
    monkeypatch.setattr(karaoke_relay.relay_client, "close_night", close_night)
    return karaoke_relay, calls, queue


def req(i, title="Africa"):
    return {"id": f"remote-{i}-abcdefghij", "singer_name": "Sam", "song_title": title, "song_artist": "Toto", "created_at": "t"}


@pytest.mark.asyncio
async def test_requests_are_added_once_and_marked_as_relay(kr):
    k, calls, q = kr; db = DB()
    r = await k.start(db, "Pub"); assert r["ok"] and k.current_url() == "https://api.example/k/S1"
    q["requests"] = [req(1)]; assert await k._pull_once() == 1
    q["requests"] = [req(1)]; assert await k._pull_once() == 0          # same request delivered again -> ignored
    assert len(db.karaoke_requests.rows) == 1 and db.karaoke_requests.rows[0]["source"] == "relay"
    await k.stop()


@pytest.mark.asyncio
async def test_host_answers_go_back_on_next_pull_and_survive_a_failed_pull(kr):
    k, calls, q = kr; db = DB()
    await k.start(db, "Pub")
    k.note_answer("remote-1-abcdefghij", "accepted", 2)
    q["fail"] = True; await k._pull_once()                              # internet down: answer must be kept
    q["fail"] = False; await k._pull_once()
    assert calls["pull"][-1] == [{"id": "remote-1-abcdefghij", "status": "accepted", "position": 2}]
    await k._pull_once(); assert calls["pull"][-1] == []                # and sent only once
    k.note_answer("x", "weird"); k.note_answer("", "accepted"); await k._pull_once(); assert calls["pull"][-1] == []
    await k.stop()


@pytest.mark.asyncio
async def test_offline_start_is_reported_not_raised_and_stop_closes_the_night(kr, monkeypatch):
    k, calls, q = kr
    async def down(venue): return {"ok": False, "error": "offline", "message": "no internet"}
    monkeypatch.setattr(k.relay_client, "open_night", down)
    r = await k.start(DB(), "Pub"); assert r["ok"] is False and k.status()["online"] is False and k.current_url() is None
    await k.stop()
    monkeypatch.undo()


@pytest.mark.asyncio
async def test_stop_closes_remote_night(kr):
    k, calls, q = kr
    await k.start(DB(), "Pub"); await k.stop(); assert calls["close"] == 1 and k.current_url() is None


@pytest.mark.asyncio
async def test_relay_client_never_raises_when_the_internet_is_down(monkeypatch, tmp_path):
    from native import relay_client
    monkeypatch.setenv("BIGHAT_LICENSE_API_BASE_URL", "http://127.0.0.1:1")
    monkeypatch.setattr(relay_client, "_auth", lambda: {"license_key": "BHE-AAAA-BBBB-CCCC-DDDD", "hwid": "h"})
    f = tmp_path / "a.png"; f.write_bytes(b"x" * 10)
    r = await relay_client.publish_file(str(f)); assert r["ok"] is False and r["error"] == "offline" and r["message"]
    assert (await relay_client.open_night("x"))["ok"] is False
    assert (await relay_client.publish_file(str(tmp_path / "gone.png")))["error"] == "missing_file"
    monkeypatch.setattr(relay_client, "_auth", lambda: None)
    assert (await relay_client.publish_file(str(f)))["error"] == "no_license"


def test_qr_links_always_use_the_path_that_reaches_the_relay(monkeypatch):
    from native import relay_client
    monkeypatch.setenv("BIGHAT_LICENSE_API_BASE_URL", "https://api.bighat.live")
    assert relay_client.public_url("/d/ABC") == "https://api.bighat.live/api/relay/d/ABC"          # old relay answer
    assert relay_client.public_url("/k/ABC") == "https://api.bighat.live/api/relay/k/ABC"
    assert relay_client.public_url("/api/relay/k/ABC") == "https://api.bighat.live/api/relay/k/ABC"  # new relay answer: untouched
