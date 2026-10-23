"""v32.3.1: the REAL httpx calls (headers, status codes, X-Content-Sha256, JSON parsing) against a tiny local server that answers exactly
like the Cloud's /api/program/manifest and /api/program/files/{id} (Cloud PR #32/#34). The other tests fake the HTTP functions; this one does not."""
import hashlib, importlib, json, sys, threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tests"))
from test_cloud_sync import feed, V, PR, P, run   # noqa: E402
from test_cloud_files_pull import env as files_env, PNG, GIF, sha   # noqa: E402,F401

KEY = "good-key"


class Cloud(BaseHTTPRequestHandler):
    files = {}      # file_id -> (meta, bytes)
    mode = {"lapsed": False, "slow": False}

    def log_message(self, *a): pass

    def _send(self, code, body, ctype="application/json", extra=None):
        raw = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(raw)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers(); self.wfile.write(raw)

    def do_GET(self):
        if self.headers.get("Authorization") != f"Bearer {KEY}":
            return self._send(401, {"error": "unauthorized", "message": "Missing program access key"})
        if self.mode["lapsed"]:
            return self._send(402, {"error": "subscription_lapsed", "message": "lapsed"})
        if self.path == "/api/program/manifest":
            return self._send(200, {"files": [m for m, _ in self.files.values()], "count": len(self.files)})
        if self.path.startswith("/api/program/files/"):
            fid = self.path.rsplit("/", 1)[-1]
            if fid not in self.files:
                return self._send(404, {"error": "not_found", "message": "No such file for this program"})
            meta, data = self.files[fid]
            return self._send(200, data, "application/octet-stream", {"X-Content-Sha256": meta["sha256"], "Content-Disposition": "attachment"})
        self._send(404, {"error": "not_found"})


@pytest.fixture
def cloud(files_env, monkeypatch):
    e = files_env
    Cloud.files = {}; Cloud.mode = {"lapsed": False, "slow": False}
    srv = HTTPServer(("127.0.0.1", 0), Cloud)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    importlib.reload(e.cf)
    monkeypatch.setattr(e.cf.cloud_link, "get_token", lambda: KEY)
    monkeypatch.setattr(e.cf.cloud_link, "cloud_base_url", lambda: f"http://127.0.0.1:{srv.server_port}")
    e.srv = srv
    e.put = lambda fid, category, name, data, **kw: Cloud.files.__setitem__(fid, (dict({"file_id": fid, "area": "trivia", "category": category, "venue_id": "v1", "name": name,
                                                                                         "size": len(data), "sha256": sha(data), "updated_at": "2026-10-23T00:00:00+00:00"}, **kw), data))
    e.pull = lambda: run(e.cf.pull_once(e.db))
    yield e
    srv.shutdown()


def test_a_real_overlay_travels_over_http_and_is_saved(cloud):
    cloud.pull_venue(); cloud.put("f1", "overlay", "Reg Round.png", PNG)
    r = cloud.pull()
    assert r["state"] == "ok" and r["counts"]["added"] == 1
    assert cloud.loc()["overlay_images"][0]["filename"] == "Reg Round.png"


def test_a_host_picture_travels_over_http(cloud, monkeypatch):
    cloud.pull_venue()
    feed(cloud.cs, monkeypatch, [{"seq": 9, "has_more": False, "items": [P("p1", "Sam Host", "sam@x.com")]}])
    run(cloud.cs.pull_once(cloud.db, approve_first_link=True))
    cloud.put("h1", "host_avatar", "me.png", PNG, area="hosts", person_id="p1", venue_id=None)
    r = cloud.pull()
    from native import files_router
    assert r["counts"]["added"] == 1 and (files_router.host_folder("sam@x.com") / "avatar.png").read_bytes() == PNG


def test_a_wrong_key_is_reported_as_unauthorized(cloud, monkeypatch):
    monkeypatch.setattr(cloud.cf.cloud_link, "get_token", lambda: "wrong")
    assert cloud.pull()["state"] == "unauthorized"


def test_a_lapsed_subscription_pauses_quietly(cloud):
    cloud.pull_venue(); cloud.put("f1", "overlay", "a.png", PNG)
    cloud.pull()
    Cloud.mode["lapsed"] = True
    r = cloud.pull()
    assert r["state"] == "subscription_lapsed" and len(cloud.loc()["overlay_images"]) == 1


def test_a_file_that_vanished_between_manifest_and_download_is_a_failure_not_a_crash(cloud):
    cloud.pull_venue(); cloud.put("f1", "overlay", "a.png", PNG)
    real = Cloud.do_GET
    meta, data = Cloud.files["f1"]
    Cloud.files["f1"] = (meta, b"")
    del Cloud.files["f1"]
    Cloud.files["ghost"] = (dict(meta, file_id="ghost"), b"")
    del Cloud.files["ghost"]
    # the manifest lists f1, the download says not_found
    manifest = [dict(meta)]
    import types
    async def m(): return {"ok": True, "files": manifest}
    cloud.cf._fetch_manifest = m
    r = cloud.pull()
    assert r["counts"]["failed"] == 1 and r["state"] == "ok"


def test_a_tampered_download_is_refused(cloud):
    cloud.pull_venue(); cloud.put("f1", "overlay", "a.png", PNG)
    meta, _ = Cloud.files["f1"]
    Cloud.files["f1"] = (meta, PNG + b"TAMPERED")
    r = cloud.pull()
    assert r["counts"]["failed"] == 1 and cloud.loc().get("overlay_images") in ([], None)


def test_the_cloud_being_down_is_unreachable_not_a_crash(cloud, monkeypatch):
    cloud.srv.shutdown(); cloud.srv.server_close()
    assert cloud.pull()["state"] == "unreachable"
