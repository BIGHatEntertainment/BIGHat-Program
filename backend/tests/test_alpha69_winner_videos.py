"""alpha.69: winner videos live in app data, stream with Range, fall back to Generic,
and can be added from Bingo Setup."""
import sys, io
from pathlib import Path
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("BIGHAT_WINNER_VIDEOS_DIR", str(tmp_path / "user_wv"))
    from routes import bingo_setup
    app = FastAPI()
    app.include_router(bingo_setup.router, prefix="/api")
    return TestClient(app), tmp_path / "user_wv"


def test_bundled_videos_are_copied_to_app_data_and_listed(client):
    c, user = client
    r = c.get("/api/bingo/winner-videos").json()
    names = {v["name"] for v in r["videos"]}
    for n in ["(1970's).mp4", "(1980's).mp4", "(1990's).mp4", "(2000's).mp4", "(Loteria).mp4",
              "(Pop-Punk and Emo).mp4", "(X-Mas).mp4", "(Generic).mp4"]:
        assert n in names, n
        assert (user / n).is_file()           # seeded into app data
    assert r["folder"] == str(user)


def test_theme_names_find_the_right_video_and_stream(client):
    c, _ = client
    sizes = {v["name"]: v["size"] for v in c.get("/api/bingo/winner-videos").json()["videos"]}
    for theme, want in [("1980s", "(1980's).mp4"), ("(1990's)", "(1990's).mp4"), ("Y2K", "(2000's).mp4"),
                        ("Pop-Punk & Emo", "(Pop-Punk and Emo).mp4"), ("Loteria", "(Loteria).mp4"),
                        ("Zydeco", "(Generic).mp4")]:
        r = c.get("/api/bingo/winner-video/" + theme)
        assert r.status_code == 200, theme
        assert r.headers["content-type"] == "video/mp4"
        assert len(r.content) == sizes[want], theme


def test_range_request_gives_partial_content(client):
    c, _ = client
    r = c.get("/api/bingo/winner-video/1980s", headers={"Range": "bytes=100-199"})
    assert r.status_code == 206 and len(r.content) == 100
    assert r.headers["content-range"].startswith("bytes 100-199/")
    assert c.head("/api/bingo/winner-video/1980s").headers["accept-ranges"] == "bytes"


def test_add_a_video_then_it_wins_for_that_theme(client):
    c, user = client
    r = c.post("/api/bingo/winner-videos", files=[("files", ("Zydeco.mp4", io.BytesIO(b"x" * 5000), "video/mp4"))])
    assert r.json()["saved"] == ["Zydeco.mp4"]
    assert (user / "Zydeco.mp4").is_file()
    got = c.get("/api/bingo/winner-video/Zydeco")
    assert got.status_code == 200 and len(got.content) == 5000


def test_user_video_replaces_the_bundled_one(client):
    c, user = client
    c.post("/api/bingo/winner-videos", files=[("files", ("(1980's).mp4", io.BytesIO(b"y" * 777), "video/mp4"))])
    assert len(c.get("/api/bingo/winner-video/1980s").content) == 777
    # a restart (seed again) must not overwrite the user's file
    from native import winner_videos as wv
    wv.seed()
    assert (user / "(1980's).mp4").stat().st_size == 777


def test_bad_uploads_are_rejected(client):
    c, user = client
    r = c.post("/api/bingo/winner-videos", files=[("files", ("notes.txt", io.BytesIO(b"hi"), "text/plain")),
                                                  ("files", ("....mp4", io.BytesIO(b"hi"), "video/mp4")),
                                                  ("files", ("Good.mp4", io.BytesIO(b"ok"), "video/mp4"))]).json()
    assert r["saved"] == ["Good.mp4"]
    assert {x["reason"] for x in r["rejected"]} == {"bad_type", "bad_name"}
    assert not list(user.glob("*.part"))


def test_delete_only_user_files_and_no_path_tricks(client):
    c, user = client
    c.post("/api/bingo/winner-videos", files=[("files", ("Zydeco.mp4", io.BytesIO(b"x"), "video/mp4"))])
    assert c.delete("/api/bingo/winner-videos/Zydeco.mp4").status_code == 200
    assert not (user / "Zydeco.mp4").exists()
    assert c.delete("/api/bingo/winner-videos/Zydeco.mp4").status_code == 404
    assert c.delete("/api/bingo/winner-videos/..%2F..%2Fetc%2Fpasswd").status_code in (404, 405)
    assert c.get("/api/bingo/winner-video/..%2F..%2Fetc%2Fpasswd").headers["content-type"] == "video/mp4"  # falls to Generic, never a real path
