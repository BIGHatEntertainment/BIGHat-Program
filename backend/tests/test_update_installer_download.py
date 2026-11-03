"""v32.2.10: the Update tool DOWNLOADS the installer itself. Real local HTTP server (with GitHub's 302-to-signed-URL redirect), real files on a tmp disk.
The rule under test: the program never says "downloaded" unless a whole file, of the size the server promised, is on disk."""
import asyncio, hashlib, json, os, socket, sys, threading, time
from pathlib import Path
import pytest

aiohttp = pytest.importorskip("aiohttp")
from aiohttp import web

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
PAYLOAD = b"MZ-fake-installer-" + os.urandom(2_500_000)                  # 2.5 MB: several chunks, so progress is real


def _port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


class Srv:
    """GitHub-like: /asset -> 302 -> /real. Modes: ok | short (closes early) | 404 | slow."""
    def __init__(self):
        self.port, self.mode, self.hits, self.loop = _port(), "ok", 0, None

    def start(self):
        async def real(request):
            self.hits += 1
            if self.mode == "404": raise web.HTTPNotFound()
            resp = web.StreamResponse(headers={"Content-Length": str(len(PAYLOAD))}); await resp.prepare(request)
            cut = len(PAYLOAD) // 2 if self.mode == "short" else len(PAYLOAD)
            step = 250_000
            for i in range(0, cut, step):
                await resp.write(PAYLOAD[i:min(i + step, cut)])
                if self.mode == "slow": await asyncio.sleep(0.15)
            if self.mode == "short":
                request.transport.close(); return resp
            await resp.write_eof(); return resp

        async def asset(request):
            raise web.HTTPFound(location=f"http://127.0.0.1:{self.port}/real")
        app = web.Application(); app.router.add_get("/asset", asset); app.router.add_get("/real", real)

        def run():
            self.loop = asyncio.new_event_loop(); asyncio.set_event_loop(self.loop)
            r = web.AppRunner(app); self.loop.run_until_complete(r.setup())
            self.loop.run_until_complete(web.TCPSite(r, "127.0.0.1", self.port).start()); self.loop.run_forever()
        threading.Thread(target=run, daemon=True).start()
        for _ in range(100):
            try: socket.create_connection(("127.0.0.1", self.port), 0.1).close(); return
            except OSError: time.sleep(0.05)


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("BIGHAT_NO_BROWSER", "1")
    monkeypatch.setenv("BIGHAT_DATA_ROOT", str(tmp_path / "AppData"))
    monkeypatch.setenv("BIGHAT_DOWNLOADS_DIR", str(tmp_path / "Downloads"))
    monkeypatch.delenv("BIGHAT_UPDATE_MANIFEST_FIXTURE", raising=False)
    import importlib
    from native import data_map, system_router, updates_service, updates_router, installer_download
    for m in (data_map, system_router, updates_service, updates_router, installer_download):
        importlib.reload(m)
    installer_download.reset()
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    updates_router.set_database(None)
    app = FastAPI(); app.include_router(updates_router.router, prefix="/api")
    srv = Srv(); srv.start()
    e = type("E", (), {})(); e.c, e.srv, e.idl, e.sr, e.us, e.dl = TestClient(app), srv, installer_download, system_router, updates_service, tmp_path / "Downloads"
    monkeypatch.setattr(system_router, "is_release_url", lambda u: u.startswith(f"http://127.0.0.1:{srv.port}/"))     # the host check is replaced for the LOCAL server only

    def serve(size=len(PAYLOAD), version="32.2.10", url=None, name="BIG.Hat.Entertainment_32.2.10_x64-setup.exe", installed="32.2.9"):
        async def fake_fetch(self):
            return updates_service.UpdateManifest.from_dict({"latest_version": version, "download_url": url or f"http://127.0.0.1:{srv.port}/asset",
                                                             "sha256": "", "filename": name, "size": size})
        monkeypatch.setattr(updates_service.UpdatesService, "fetch_manifest", fake_fetch)
        monkeypatch.setattr(updates_service.UpdatesService, "installed_version", property(lambda self: installed))
        monkeypatch.setattr(updates_service, "_detect_platform_key", lambda: "windows")
    e.serve = serve
    return e


def wait_done(e, secs=15):
    end = time.time() + secs
    while time.time() < end:
        s = e.c.get("/api/native/updates/download-installer/status").json()
        if s["state"] in ("done", "failed"): return s
        time.sleep(0.05)
    raise AssertionError("download never finished: " + json.dumps(e.c.get("/api/native/updates/download-installer/status").json()))


def test_the_click_really_downloads_the_installer_to_downloads(env):
    env.serve()
    r = env.c.post("/api/native/updates/download-installer").json()
    assert r["state"] == "running" and r["version"] == "32.2.10"
    s = wait_done(env)
    assert s["state"] == "done" and s["percent"] == 100 and s["bytes"] == len(PAYLOAD)
    f = env.dl / "BIG.Hat.Entertainment_32.2.10_x64-setup.exe"
    assert f.is_file() and f.read_bytes() == PAYLOAD                                  # the real bytes, through GitHub's 302
    assert not list(env.dl.glob("*.part"))


def test_progress_is_real_while_it_runs(env):
    env.serve(); env.srv.mode = "slow"
    env.c.post("/api/native/updates/download-installer")
    seen = set()
    for _ in range(60):
        s = env.c.get("/api/native/updates/download-installer/status").json(); seen.add(s["percent"])
        if s["state"] == "done": break
        time.sleep(0.1)
    assert s["state"] == "done" and len(seen) >= 3 and max(seen) == 100 and any(0 < p < 100 for p in seen)


def test_a_second_click_joins_the_running_download_instead_of_starting_another(env):
    env.serve(); env.srv.mode = "slow"
    a = env.c.post("/api/native/updates/download-installer").json()
    b = env.c.post("/api/native/updates/download-installer").json()
    assert a["joined"] is False and b["joined"] is True and b["state"] == "running"
    wait_done(env)
    assert env.srv.hits == 1                                                          # ONE download, not two


def test_a_short_download_is_thrown_away_and_never_called_done(env):
    env.serve(); env.srv.mode = "short"
    env.c.post("/api/native/updates/download-installer")
    s = wait_done(env)
    assert s["state"] == "failed" and ("interrupted" in s["message"] or "incomplete" in s["message"])
    assert not list(env.dl.glob("*"))                                                 # no .part, no half installer left behind


def test_a_wrong_size_is_refused_even_if_the_stream_ended_cleanly(env):
    env.serve(size=len(PAYLOAD) + 5)                                                   # the server promised more than it sent
    env.c.post("/api/native/updates/download-installer")
    s = wait_done(env)
    assert s["state"] == "failed" and "incomplete" in s["message"] and not list(env.dl.glob("*"))


def test_a_server_error_says_so_in_plain_words(env):
    env.serve(); env.srv.mode = "404"
    env.c.post("/api/native/updates/download-installer")
    s = wait_done(env)
    assert s["state"] == "failed" and "404" in s["message"] and not list(env.dl.glob("*"))


def test_try_again_after_a_failure_works(env):
    env.serve(); env.srv.mode = "404"
    env.c.post("/api/native/updates/download-installer"); assert wait_done(env)["state"] == "failed"
    env.srv.mode = "ok"
    assert env.c.post("/api/native/updates/download-installer/reset").json()["state"] == "idle"
    env.c.post("/api/native/updates/download-installer"); assert wait_done(env)["state"] == "done"


def test_an_existing_different_file_is_never_overwritten(env):
    env.serve(); env.dl.mkdir(parents=True)
    (env.dl / "BIG.Hat.Entertainment_32.2.10_x64-setup.exe").write_bytes(b"something else the user saved")
    env.c.post("/api/native/updates/download-installer"); s = wait_done(env)
    assert s["state"] == "done" and s["path"].endswith("(2).exe")
    assert (env.dl / "BIG.Hat.Entertainment_32.2.10_x64-setup.exe").read_bytes() == b"something else the user saved"


def test_a_finished_download_is_found_again_not_downloaded_twice(env):
    env.serve()
    env.c.post("/api/native/updates/download-installer"); wait_done(env)
    env.idl.reset()                                                                    # like closing and reopening the program
    env.c.post("/api/native/updates/download-installer"); s = wait_done(env)
    assert s["state"] == "done" and s["message"] == "Already downloaded." and env.srv.hits == 1
    assert len(list(env.dl.glob("*.exe"))) == 1


def test_up_to_date_downloads_nothing(env):
    env.serve(installed="32.2.10")
    r = env.c.post("/api/native/updates/download-installer").json()
    assert r["state"] == "idle" and r["reason"] == "no_update_available" and env.srv.hits == 0


def test_no_installer_for_this_pc_says_so_and_downloads_nothing(env):
    env.serve(url="https://github.com/BIGHatEntertainment/BIGHat-Program/releases/latest", name="")
    r = env.c.post("/api/native/updates/download-installer").json()
    assert r["state"] == "failed" and r["no_direct_link"] is True and env.srv.hits == 0 and not env.dl.exists()


def test_a_link_that_is_not_this_programs_release_is_refused(env, monkeypatch):
    env.serve(url=f"http://127.0.0.1:{env.srv.port}/asset")
    monkeypatch.setattr(env.sr, "is_release_url", lambda u: False)
    r = env.c.post("/api/native/updates/download-installer").json()
    assert r["state"] == "failed" and r["error"] in ("bad_link", "no_direct_link") and env.srv.hits == 0 and not env.dl.exists()   # stopped before any download


def test_the_real_github_link_shape_passes_the_real_check_and_others_do_not(env):
    from importlib import reload
    reload(env.sr)
    good = "https://github.com/BIGHatEntertainment/BIGHat-Program/releases/download/v32.2.9/BIG.Hat.Entertainment_32.2.9_x64-setup.exe"
    assert env.sr.is_release_url(good)
    for bad in ("https://github.com/evil/BIGHat-Program/releases/download/v1/x.exe", "https://evil.com/BIGHatEntertainment/BIGHat-Program/releases/x.exe",
                "http://github.com/BIGHatEntertainment/BIGHat-Program/releases/download/v1/x.exe", "file:///C:/x.exe", "javascript:alert(1)"):
        assert not env.sr.is_release_url(bad), bad


def test_show_in_folder_only_for_the_file_this_program_downloaded(env, tmp_path):
    env.serve(); env.c.post("/api/native/updates/download-installer"); wait_done(env)
    ok = env.c.post("/api/native/updates/download-installer/show").json()
    assert ok["ok"] is True and ok["shown"].endswith(".exe")
    other = tmp_path / "elsewhere.exe"; other.write_bytes(b"x")
    assert env.idl.open_installer(str(other))["ok"] is False                           # outside Downloads
    (env.dl / "notes.txt").write_text("x"); assert env.idl.open_installer(str(env.dl / "notes.txt"))["ok"] is False     # not an installer


def test_status_never_starts_anything(env):
    env.serve()
    assert env.c.get("/api/native/updates/download-installer/status").json()["state"] == "idle" and env.srv.hits == 0


# ---- the screen (source checks: the app window itself can only be tried on a real PC) ----
UI = (Path(__file__).resolve().parent.parent.parent / "frontend" / "src" / "pages" / "UpdateTool.jsx").read_text(encoding="utf-8")


def test_the_button_downloads_inside_the_program_and_never_claims_success_from_a_link_hand_off():
    assert "/api/native/updates/download-installer`" in UI and "/download-installer/status" in UI
    assert "/updates/open-installer" not in UI                                   # the "ask the OS to open a link" path is gone from the click
    assert "Your browser is downloading" not in UI                               # the message that could be false
    assert "dl?.state === 'done'" in UI and "update-downloaded" in UI            # "Downloaded" only from the backend's DONE state


def test_the_screen_shows_progress_failure_and_try_again_and_survives_reopening():
    for needle in ("update-progress", "update-failed", "Try again", "dl.percent", "show-installer-btn"):
        assert needle in UI, needle
    mount = UI[UI.index("closing and reopening"):][:420]
    assert "download-installer/status" in mount and "'running'" in mount and "'done'" in mount   # reopening finds a running / finished download


def test_the_plain_link_is_only_a_last_resort_when_no_installer_exists_for_this_pc():
    i = UI.index("info.no_direct_link")
    assert "setOpened(" in UI[i:i + 400] and UI.count("setOpened({") == 1
