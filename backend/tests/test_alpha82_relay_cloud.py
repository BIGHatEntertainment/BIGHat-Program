"""alpha.82: the cloud QR relay (file drop + karaoke requests)."""
import io, time, importlib
from datetime import datetime, timezone, timedelta
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

KEY, HW = "BHE-AAAA-BBBB-CCCC-DDDD", "hw-1"


class FakeColl:
    def __init__(self): self.rows = []
    def _m(self, r, q):
        for k, v in q.items():
            if isinstance(v, dict):
                x = r.get(k)
                if "$lt" in v and not (x is not None and x < v["$lt"]): return False
            elif r.get(k) != v: return False
        return True
    async def insert_one(self, d): self.rows.append(dict(d))
    async def find_one(self, q, proj=None, sort=None):
        m = [r for r in self.rows if self._m(r, q)]
        if sort: m.sort(key=lambda r: r.get(sort[0][0], 0), reverse=sort[0][1] < 0)
        return dict(m[0]) if m else None
    def find(self, q, proj=None):
        coll = self
        class C:
            def __init__(s): s.m = [dict(r) for r in coll.rows if coll._m(r, q)]
            def sort(s, k, d=1): s.m.sort(key=lambda r: r.get(k, 0), reverse=d < 0); return s
            async def to_list(s, n): return s.m[:n]
        return C()
    async def update_one(self, q, u):
        for r in self.rows:
            if self._m(r, q): r.update(u.get("$set", {})); return
    async def delete_one(self, q):
        for i, r in enumerate(self.rows):
            if self._m(r, q): del self.rows[i]; return
    async def delete_many(self, q): self.rows = [r for r in self.rows if not self._m(r, q)]
    async def count_documents(self, q): return len([r for r in self.rows if self._m(r, q)])


class FakeDB:
    def __init__(self): self.relay_files, self.relay_sessions, self.relay_requests = FakeColl(), FakeColl(), FakeColl()


class FakeService:
    revoked = False
    calls = 0
    async def validate(self, *, key, hwid):
        self.calls += 1
        if key != KEY: return False, "unknown_key", None
        if self.revoked: return False, "revoked", None
        if hwid != HW: return False, "hwid_not_activated", None
        return True, "ok", object()


@pytest.fixture
def env(tmp_path, monkeypatch):
    from cloud import relay_router as rr
    importlib.reload(rr)
    svc, db = FakeService(), FakeDB()
    rr.set_runtime(service=svc, db=db, files_dir=str(tmp_path / "files"))
    app = FastAPI(); app.include_router(rr.router)
    return TestClient(app), rr, svc, db


def up(c, data=b"x" * 100, name="story.mp4", key=KEY, hw=HW):
    return c.post("/api/relay/files", data={"license_key": key, "hwid": hw}, files={"file": (name, io.BytesIO(data))})


def test_upload_then_phone_can_download(env):
    c, rr, svc, db = env
    r = up(c); assert r.status_code == 200, r.text
    url = r.json()["url"]; assert url.startswith("/api/relay/d/")      # the path that reaches the relay behind the website ingress
    assert c.get("/d/" + url.rsplit("/", 1)[1]).status_code == 200  # the short form keeps working
    g = c.get(url); assert g.status_code == 200 and g.content == b"x" * 100
    assert g.headers["content-type"] == "video/mp4"


def test_only_real_licenses_can_upload(env):
    c, rr, svc, db = env
    assert up(c, key="BHE-ZZZZ-ZZZZ-ZZZZ-ZZZZ").status_code == 401
    assert up(c, hw="other-pc").status_code == 401
    svc.revoked = True
    assert up(c).status_code == 401
    assert db.relay_files.rows == []


def test_bad_types_big_files_and_quota(env, monkeypatch):
    c, rr, svc, db = env
    assert up(c, name="evil.exe").status_code == 400
    assert up(c, name="noext").status_code == 400
    monkeypatch.setattr(rr, "MAX_FILE_MB", 0)
    big = up(c, data=b"y" * 10); assert big.status_code == 413
    assert list((rr._files_dir).glob("*")) == []                # nothing left on disk
    monkeypatch.setattr(rr, "MAX_FILE_MB", 150); monkeypatch.setattr(rr, "MAX_FILES_PER_LICENSE", 2)
    assert up(c).status_code == 200 and up(c).status_code == 200
    assert up(c).status_code == 429


def test_expired_and_unknown_links_are_dead(env):
    c, rr, svc, db = env
    url = up(c).json()["url"]
    db.relay_files.rows[0]["expires_at"] = "2000-01-01T00:00:00+00:00"
    r = c.get(url); assert r.status_code == 404 and "expired" in r.text.lower()
    assert c.get("/d/not-a-real-id-aaaaaaaa").status_code == 404
    assert c.get("/api/relay/d/not-a-real-id-aaaaaaaa").status_code == 404
    assert c.get("/d/..%2f..%2fetc%2fpasswd").status_code == 404


def test_expired_files_are_deleted_from_disk_on_next_upload(env):
    c, rr, svc, db = env
    up(c); path = db.relay_files.rows[0]["path"]
    db.relay_files.rows[0]["expires_at"] = "2000-01-01T00:00:00+00:00"
    up(c)
    import os; assert not os.path.exists(path) and len(db.relay_files.rows) == 1


def _open(c, venue="Monkey Pants"):
    return c.post("/api/relay/karaoke/sessions", json={"license_key": KEY, "hwid": HW, "venue": venue}).json()


def test_karaoke_full_round_trip(env):
    c, rr, svc, db = env
    s = _open(c); sid = s["session"]
    assert _open(c)["session"] == sid                                  # re-open = same QR
    assert s["url"].startswith("/api/relay/k/")
    page = c.get(s["url"]); assert page.status_code == 200 and "Request this song" in page.text and "Monkey Pants" in page.text
    r = c.post(f"/api/relay/karaoke/{sid}/request", json={"singer_name": "Sam", "song_title": "Africa", "song_artist": "Toto"})
    assert r.status_code == 200; rid = r.json()["request_id"]
    p = c.post(f"/api/relay/karaoke/sessions/{sid}/pull", json={"license_key": KEY, "hwid": HW}).json()
    assert [x["song_title"] for x in p["requests"]] == ["Africa"]
    again = c.post(f"/api/relay/karaoke/sessions/{sid}/pull", json={"license_key": KEY, "hwid": HW}).json()
    assert again["requests"] == []                                    # each request is delivered once
    assert c.get(f"/api/relay/karaoke/{sid}/status/{rid}").json()["status"] == "pending"
    c.post(f"/api/relay/karaoke/sessions/{sid}/pull", json={"license_key": KEY, "hwid": HW, "answers": [{"id": rid, "status": "accepted", "position": 3}]})
    assert c.get(f"/api/relay/karaoke/{sid}/status/{rid}").json() == {"status": "accepted", "position": 3}


def test_phone_rules_cooldown_limits_and_cleaning(env, monkeypatch):
    c, rr, svc, db = env
    sid = _open(c)["session"]; u = f"/api/relay/karaoke/{sid}/request"
    assert c.post(u, json={"singer_name": "", "song_title": "x"}).status_code == 400
    assert c.post(u, json={"singer_name": "Sam", "song_title": "<script>alert(1)</script>Africa"}).status_code == 200
    # text is kept as typed (screens escape it); only control characters are removed
    assert db.relay_requests.rows[0]["song_title"] == "<script>alert(1)</script>Africa"
    assert c.post(u, json={"singer_name": "Sam\x00\x07", "song_title": "ok\n\n  title"}).status_code in (200, 429)
    assert c.post(u, json={"singer_name": "Sam", "song_title": "again"}).status_code == 429      # same phone, too fast
    monkeypatch.setattr(rr, "PHONE_MIN_SECONDS_BETWEEN_REQUESTS", 0); monkeypatch.setattr(rr, "MAX_REQUESTS_PER_SESSION", 2)
    assert c.post(u, json={"singer_name": "Sam", "song_title": "two"}).status_code == 200
    assert c.post(u, json={"singer_name": "Sam", "song_title": "three"}).status_code == 429       # night is full
    assert len(db.relay_requests.rows[0]["singer_name"]) <= 40


def test_closed_night_and_other_owners_cannot_touch_it(env):
    c, rr, svc, db = env
    s = _open(c); sid = s["session"]
    assert c.post(f"/api/relay/karaoke/sessions/{sid}/pull", json={"license_key": "BHE-ZZZZ-ZZZZ-ZZZZ-ZZZZ", "hwid": HW}).status_code == 401
    assert c.post(f"/api/relay/karaoke/sessions/{sid}/close", json={"license_key": KEY, "hwid": HW}).json() == {"closed": True}
    assert c.get(s["url"]).status_code == 404
    assert c.post(f"/api/relay/karaoke/{sid}/request", json={"singer_name": "Sam", "song_title": "x"}).status_code == 404
    assert db.relay_sessions.rows == [] and db.relay_requests.rows == []



# ---------------- alpha.84: scale-up changes ----------------
def test_license_check_is_cached_so_busy_nights_do_not_hit_the_license_database(env):
    c, rr, svc, db = env
    sid = _open(c)["session"]
    before = svc.calls
    for _ in range(20):
        assert c.post(f"/api/relay/karaoke/sessions/{sid}/pull", json={"license_key": KEY, "hwid": HW}).status_code == 200
    assert svc.calls - before == 0, "20 polls must not each look up (and write to) the license record"


def test_cache_does_not_let_a_wrong_machine_or_a_wrong_key_in(env):
    c, rr, svc, db = env
    _open(c)                                                      # primes the cache for (KEY, HW)
    assert c.post("/api/relay/karaoke/sessions", json={"license_key": KEY, "hwid": "other-pc", "venue": "x"}).status_code == 401
    assert c.post("/api/relay/karaoke/sessions", json={"license_key": "BHE-ZZZZ-ZZZZ-ZZZZ-ZZZZ", "hwid": HW, "venue": "x"}).status_code == 401


def test_a_revoked_license_stops_working_when_the_cache_runs_out(env, monkeypatch):
    c, rr, svc, db = env
    _open(c); svc.revoked = True
    assert c.post("/api/relay/karaoke/sessions", json={"license_key": KEY, "hwid": HW, "venue": "x"}).status_code == 200   # still cached
    monkeypatch.setattr(rr, "AUTH_CACHE_SECONDS", 0)                                                                         # cache window over
    assert c.post("/api/relay/karaoke/sessions", json={"license_key": KEY, "hwid": HW, "venue": "x"}).status_code == 401


def test_cache_can_be_switched_off(env, monkeypatch):
    c, rr, svc, db = env
    monkeypatch.setattr(rr, "AUTH_CACHE_SECONDS", 0)
    before = svc.calls; _open(c); _open(c)
    assert svc.calls - before == 2


def test_storage_cap_per_license_stops_big_totals(env, monkeypatch):
    c, rr, svc, db = env
    monkeypatch.setattr(rr, "MAX_BYTES_PER_LICENSE", 1000)
    assert up(c, data=b"a" * 600).status_code == 200
    r = up(c, data=b"b" * 600)
    assert r.status_code == 429 and "storage_full" in r.text
    assert list(rr._files_dir.glob("*.mp4")) and len(list(rr._files_dir.glob("*"))) == 1        # the refused file left nothing on disk
    assert up(c, data=b"c" * 300).status_code == 200                                              # smaller one still fits


@pytest.mark.asyncio
async def test_indexes_are_requested_for_every_relay_collection_and_never_crash_startup():
    from cloud import relay_router as rr
    made = []
    class C:
        def __init__(s, n): s.n = n
        async def create_index(s, spec, **kw): made.append((s.n, spec if isinstance(spec, str) else tuple(k for k, _ in spec)))
    class D:
        relay_files, relay_sessions, relay_requests = C("files"), C("sessions"), C("requests")
    await rr.ensure_indexes(D())
    names = {n for n, _ in made}
    assert names == {"files", "sessions", "requests"} and ("requests", ("session", "pulled", "created_ts")) in made and ("sessions", "id") in made
    class Broken:
        class relay_files:
            @staticmethod
            async def create_index(*a, **k): raise RuntimeError("boom")
    await rr.ensure_indexes(Broken())            # must not raise
