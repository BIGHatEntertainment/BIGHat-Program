"""alpha.67: Bingo Setup routes over real HTTP (FastAPI TestClient)."""
import sys
from pathlib import Path
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("BIGHAT_BINGO_SETTINGS", str(tmp_path / "cfg" / "bingo_settings.json"))
    main = tmp_path / "Bingo"
    (main / "1990s").mkdir(parents=True)
    (main / "Emo").mkdir()
    (main / "Nothing").mkdir()
    (main / "1990s" / "songs.csv").write_text("1,Song One,Band One\n2,Song Two,Band Two\n", encoding="utf-8")
    (main / "1990s" / "01_one.mp4").write_bytes(bytes(range(256)) * 40)        # 10,240 bytes
    (main / "1990s" / "02_two.webm").write_bytes(b"w" * 500)
    (main / "Emo" / "list.csv").write_text("10,Emo Song,Emo Band\n", encoding="utf-8")
    (main / "Emo" / "10_emo.mp4").write_bytes(b"e" * 100)
    (tmp_path / "secret.txt").write_text("TOP SECRET")
    # mount in the SAME order as server.py: new router first, then the old SharePoint one
    from routes import bingo_setup, bingo
    app = FastAPI()
    app.include_router(bingo_setup.router, prefix="/api")
    app.include_router(bingo.router, prefix="/api")
    return TestClient(app), main, tmp_path


def _save(c, main, themes=None):
    r = c.post("/api/bingo/setup", json={"main_folder": str(main), "themes": themes or {}})
    assert r.status_code == 200, r.text
    return r.json()


def test_nothing_configured_yet(api):
    c, main, _ = api
    r = c.get("/api/bingo/setup").json()
    assert r["main_folder"] == "" and r["ok"] is False and r["error"] == "no_folder" and r["themes"] == []
    t = c.get("/api/bingo/available-themes").json()
    assert t["configured"] is False and t["themes"] == []
    assert c.get("/api/bingo/available-decades").json()["decades"] == []     # compat route: empty, not SharePoint


def test_save_folder_then_tiles_follow_the_toggles(api):
    c, main, _ = api
    s = _save(c, main)
    assert s["ok"] and {t["id"]: t["ready"] for t in s["themes"]} == {"1990s": True, "Emo": True, "Nothing": False}
    assert {t["id"] for t in c.get("/api/bingo/available-themes").json()["themes"]} == {"1990s", "Emo"}
    _save(c, main, {"Emo": {"enabled": False}})
    assert [t["id"] for t in c.get("/api/bingo/available-themes").json()["themes"]] == ["1990s"]
    # the old Lobby route returns the SAME tiles (replaces SharePoint)
    dec = c.get("/api/bingo/available-decades").json()
    assert dec["source"] == "local-folder" and [d["id"] for d in dec["decades"]] == ["1990s"]


def test_bad_folder_is_rejected_and_not_saved(api):
    c, main, _ = api
    _save(c, main)
    r = c.post("/api/bingo/setup", json={"main_folder": "/no/such/folder", "themes": {}})
    assert r.status_code == 400 and r.json()["detail"] == "folder_not_found"
    assert c.get("/api/bingo/setup").json()["main_folder"] == str(main)


def test_preview_scan_does_not_save(api):
    c, main, _ = api
    r = c.post("/api/bingo/setup/scan", json={"main_folder": str(main)}).json()
    assert r["ok"] and len(r["themes"]) == 3
    assert c.get("/api/bingo/setup").json()["main_folder"] == ""


def test_songs_for_a_theme_and_the_old_songlist_route(api):
    c, main, _ = api
    _save(c, main)
    r = c.get("/api/bingo/theme-songs/1990s").json()
    assert [(s["number"], s["title"], s["has_video"]) for s in r["songs"]] == [(1, "Song One", True), (2, "Song Two", True)]
    old = c.get("/api/bingo/songlist/1990s").json()                      # the route the Host page calls
    assert old["source"] == "local-folder" and [s["title"] for s in old["songs"]] == ["Song One", "Song Two"]
    assert c.get("/api/bingo/songlist/Nope").status_code == 404
    assert c.get("/api/bingo/theme-songs/Nothing").status_code == 404     # folder with no list


def test_video_streams_whole_and_in_ranges(api):
    c, main, _ = api
    _save(c, main)
    full = c.get("/api/bingo/media/1990s/1")
    assert full.status_code == 200 and len(full.content) == 10240
    assert full.headers["content-type"] == "video/mp4" and full.headers["accept-ranges"] == "bytes"
    assert full.content == bytes(range(256)) * 40
    part = c.get("/api/bingo/media/1990s/1", headers={"Range": "bytes=256-511"})
    assert part.status_code == 206 and part.content == bytes(range(256))
    assert part.headers["content-range"] == "bytes 256-511/10240"
    tail = c.get("/api/bingo/media/1990s/1", headers={"Range": "bytes=10000-"})
    assert tail.status_code == 206 and len(tail.content) == 240
    last = c.get("/api/bingo/media/1990s/1", headers={"Range": "bytes=-100"})
    assert last.status_code == 206 and len(last.content) == 100
    assert c.get("/api/bingo/media/1990s/1", headers={"Range": "bytes=99999-"}).status_code == 416
    assert c.get("/api/bingo/media/1990s/2").headers["content-type"] == "video/webm"
    head = c.head("/api/bingo/media/1990s/1")
    assert head.status_code == 200 and head.headers["content-length"] == "10240"


def test_missing_videos_and_unknown_themes_are_404(api):
    c, main, _ = api
    _save(c, main)
    for url in ("/api/bingo/media/1990s/99", "/api/bingo/media/Nope/1", "/api/bingo/media/Nothing/1"):
        assert c.get(url).status_code == 404, url


def test_streaming_cannot_read_files_outside_the_folder(api):
    c, main, tmp = api
    _save(c, main)
    for theme in ("..", "%2e%2e", "..%2f", "1990s%2f..%2f..", "%2e%2e%2fsecret.txt"):
        r = c.get(f"/api/bingo/media/{theme}/1")
        assert r.status_code == 404 and b"TOP SECRET" not in r.content, theme


def test_old_sharepoint_route_is_shadowed(api):
    c, main, _ = api
    d = c.get("/api/bingo/available-decades").json()
    assert d.get("source") == "local-folder"          # the SharePoint version never answers
