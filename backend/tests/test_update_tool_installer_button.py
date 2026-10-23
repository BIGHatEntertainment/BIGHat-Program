"""v32.2.1: the green "Download update" button did nothing visible (it copied the installer into a hidden folder). It now opens this PC's
installer (or the release page) in the user's browser. The link is read from the update channel by the BACKEND; the page cannot choose it."""
import json, sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
BASE = "https://github.com/BIGHatEntertainment/BIGHat-Program/releases/download"
MANIFEST = {"version": "32.2.1", "platforms": {
    "windows": {"url": f"{BASE}/v32.2.1/BIG.Hat.Entertainment_32.2.1_x64-setup.exe", "version": "32.2.1", "filename": "BIG.Hat.Entertainment_32.2.1_x64-setup.exe"},
    "macos_apple": {"url": f"{BASE}/v32.2.1/BIG.Hat.Entertainment_32.2.1_aarch64.dmg", "version": "32.2.1", "filename": "BIG.Hat.Entertainment_32.2.1_aarch64.dmg"},
    "macos_intel": {"url": None, "version": "32.2.1", "filename": None}}}


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("BIGHAT_NO_BROWSER", "1")
    monkeypatch.setenv("BIGHAT_DATA_ROOT", str(tmp_path / "AppData"))
    monkeypatch.delenv("BIGHAT_UPDATE_MANIFEST_FIXTURE", raising=False)
    import importlib
    from native import data_map, system_router, updates_service, updates_router
    for m in (data_map, system_router, updates_service, updates_router):
        importlib.reload(m)
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    updates_router.set_database(None)                                  # what server.py does at startup (the installer link needs no database)
    app = FastAPI(); app.include_router(updates_router.router, prefix="/api")
    e = type("E", (), {})()
    e.c, e.us, e.sr, e.tmp = TestClient(app), updates_service, system_router, tmp_path

    def serve(manifest, installed="32.2.0", platform_key="windows"):
        async def fake_fetch(self):
            data = json.loads(json.dumps(manifest))
            plat = (data.get("platforms") or {}).get(platform_key) or {}
            return updates_service.UpdateManifest.from_dict({"latest_version": plat.get("version") or data.get("version") or "", "download_url": plat.get("url") or "", "filename": plat.get("filename")})
        monkeypatch.setattr(updates_service.UpdatesService, "fetch_manifest", fake_fetch)
        monkeypatch.setattr(updates_service.UpdatesService, "installed_version", property(lambda self: installed))
        monkeypatch.setattr(updates_service, "_detect_platform_key", lambda: platform_key)
    e.serve = serve
    return e


def test_windows_gets_the_exe_link_and_it_opens(env):
    env.serve(MANIFEST, platform_key="windows")
    r = env.c.post("/api/native/updates/open-installer").json()
    assert r["update_available"] and r["opened"] and r["direct"] and r["url"].endswith("_x64-setup.exe") and r["filename"] == "BIG.Hat.Entertainment_32.2.1_x64-setup.exe"
    assert r["latest_version"] == "32.2.1" and r["installed_version"] == "32.2.0" and r["platform"] == "windows"


def test_apple_mac_gets_the_dmg(env):
    env.serve(MANIFEST, platform_key="macos_apple")
    r = env.c.post("/api/native/updates/open-installer").json()
    assert r["url"].endswith("_aarch64.dmg") and r["direct"]


def test_no_installer_for_this_os_opens_the_release_page_instead(env):
    env.serve(MANIFEST, platform_key="macos_intel")
    r = env.c.post("/api/native/updates/open-installer").json()
    assert r["opened"] and r["direct"] is False and r["url"] == "https://github.com/BIGHatEntertainment/BIGHat-Program/releases/latest"


@pytest.mark.parametrize("bad", ["https://evil.com/BIGHatEntertainment/BIGHat-Program/releases/x.exe", "https://github.com/someone-else/BIGHat-Program/releases/x.exe",
                                 "http://github.com/BIGHatEntertainment/BIGHat-Program/releases/x.exe", "file:///C:/x.exe", "javascript:alert(1)"])
def test_a_manifest_pointing_anywhere_else_falls_back_to_the_release_page(env, bad):
    m = json.loads(json.dumps(MANIFEST)); m["platforms"]["windows"]["url"] = bad
    env.serve(m, platform_key="windows")
    r = env.c.post("/api/native/updates/open-installer").json()
    assert r["url"] == "https://github.com/BIGHatEntertainment/BIGHat-Program/releases/latest" and r["direct"] is False


def test_nothing_opens_when_you_are_current(env):
    env.serve(MANIFEST, installed="32.2.1")
    r = env.c.post("/api/native/updates/open-installer").json()
    assert r["update_available"] is False and r["opened"] is False and r["reason"] == "no_update_available"


def test_the_page_cannot_choose_the_link(env):
    env.serve(MANIFEST)
    r = env.c.post("/api/native/updates/open-installer", json={"url": "https://evil.com/x.exe", "download_url": "https://evil.com/x.exe"}).json()
    assert "evil" not in r["url"]


def test_a_missing_service_is_reported_as_503_not_a_500(env, monkeypatch):
    monkeypatch.setattr(env.us, "UpdatesService", env.us.UpdatesService)         # keep the module in use
    from native import updates_router
    monkeypatch.setattr(updates_router, "_service", None)
    r = env.c.post("/api/native/updates/open-installer")
    assert r.status_code == 503 and r.json()["detail"] == "updates_service_unavailable"


def test_a_channel_failure_is_a_clear_error_not_a_silent_one(env, monkeypatch):
    async def boom(self): raise RuntimeError("manifest_http_503")
    monkeypatch.setattr(env.us.UpdatesService, "fetch_manifest", boom)
    r = env.c.post("/api/native/updates/open-installer")
    assert r.status_code == 502 and r.json()["detail"] == "manifest_http_503"


@pytest.mark.parametrize("url,ok", [
    (f"{BASE}/v32.2.1/BIG.Hat.Entertainment_32.2.1_x64-setup.exe", True),
    ("https://github.com/BIGHatEntertainment/BIGHat-Program/releases/latest", True),
    ("https://github.com/BIGHatEntertainment/BIGHat-Program/releases/tag/v32.2.1", True),
    ("https://github.com/BIGHatEntertainment/BIGHat-Program", False),
    ("https://github.com/BIGHatEntertainment/BIGHat-Program/issues/1", False),
    ("https://github.com/BIGHatEntertainment/BIGHat-Cloud/releases/latest", False),
    ("https://github.com/BIGHatEntertainment/BIGHat-Program-evil/releases/latest", False),
    ("https://github.com.evil.com/BIGHatEntertainment/BIGHat-Program/releases/x", False),
    ("https://evilgithub.com/BIGHatEntertainment/BIGHat-Program/releases/x", False),
    ("https://user@github.com/BIGHatEntertainment/BIGHat-Program/releases/x", False),
    ("https://github.com:8443/BIGHatEntertainment/BIGHat-Program/releases/x", False),
    ("https://github.com/BIGHatEntertainment/BIGHat-Program/releases/../../evil/x", False),
    ("http://github.com/BIGHatEntertainment/BIGHat-Program/releases/x", False),
    ("https://raw.githubusercontent.com/BIGHatEntertainment/BIGHat-Program/releases/x", False),
    ("", False), ("not a url", False)])
def test_only_this_programs_own_release_links_are_allowed(env, url, ok):
    assert env.sr.is_release_url(url) is ok


def test_open_url_still_refuses_other_github_links_and_still_allows_bighat_and_releases(env):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    app = FastAPI(); app.include_router(env.sr.router); c = TestClient(app)
    assert c.post("/api/native/system/open-url", json={"url": "https://github.com/BIGHatEntertainment/BIGHat-Program/issues/1"}).status_code == 400
    assert c.post("/api/native/system/open-url", json={"url": "https://github.com/evil/x/releases/y"}).status_code == 400
    assert c.post("/api/native/system/open-url", json={"url": "https://www.bighat.live/"}).status_code == 200
    assert c.post("/api/native/system/open-url", json={"url": f"{BASE}/v32.2.1/x.exe"}).status_code == 200


def test_the_page_calls_the_new_route_and_no_longer_the_hidden_download():
    src = (Path(__file__).resolve().parents[2] / "frontend" / "src" / "pages" / "UpdateTool.jsx").read_text(encoding="utf-8")
    assert "/api/native/updates/open-installer" in src and "/api/native/updates/download" not in src
    assert "update-link" in src                                        # the link is shown if the browser could not be opened
