"""alpha.78: downloads land in the Downloads folder, and Buy buttons open real bighat.live links via the backend."""
import io, json, sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("BIGHAT_DOWNLOADS_DIR", str(tmp_path / "Downloads"))
    monkeypatch.setenv("BIGHAT_DATA_ROOT", str(tmp_path / "AppData"))
    monkeypatch.setenv("BIGHAT_NO_BROWSER", "1")               # never really open a browser or Explorer in tests
    import importlib
    from native import data_map, system_router
    importlib.reload(data_map); importlib.reload(system_router)
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    app = FastAPI(); app.include_router(system_router.router)
    c = TestClient(app); c.tmp = tmp_path; c.sr = system_router
    return c


# ---------- open-url ----------
@pytest.mark.parametrize("url", ["https://bighat.live/", "https://www.bighat.live/about-bh-karaoke", "https://api.bighat.live/x?y=1", "https://BIGHAT.LIVE/Shop"])
def test_bighat_links_open(client, url):
    r = client.post("/api/native/system/open-url", json={"url": url})
    assert r.status_code == 200 and r.json()["ok"] is True and r.json()["opened"] == url


@pytest.mark.parametrize("url", ["http://bighat.live/", "https://evil.com/", "https://bighat.live.evil.com/", "https://evilbighat.live/", "https://user:pw@bighat.live/",
                                 "file:///C:/Windows/System32/cmd.exe", "javascript:alert(1)", "C:\\Windows\\notepad.exe", "", "bighat.live", "https://"])
def test_anything_else_is_refused(client, url):
    r = client.post("/api/native/system/open-url", json={"url": url})
    assert r.status_code == 400


def test_missing_url_is_refused(client):
    assert client.post("/api/native/system/open-url", json={}).status_code == 400


# ---------- store links ----------
def test_every_buy_button_has_a_real_working_default(client):
    links = client.get("/api/native/system/store-links").json()
    assert {"default", "standalone", "karaoke", "story", "bingo"} <= set(links)
    assert all(client.sr.is_allowed_url(v) for v in links.values())
    assert all("/shop" not in v for v in links.values())            # the old /shop/... pages never existed (404)


def test_store_links_can_be_changed_without_a_release(client):
    f = client.tmp / "AppData" / "store_links.json"; f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"karaoke": "https://bighat.live/karaoke-key", "story": "https://evil.com/x", "standalone": 5, "junk": "https://bighat.live/j"}))
    links = client.get("/api/native/system/store-links").json()
    assert links["karaoke"] == "https://bighat.live/karaoke-key"        # accepted
    assert links["story"] == "https://bighat.live/" and links["standalone"] == "https://bighat.live/"   # bad ones ignored
    assert links["junk"] == "https://bighat.live/j"
    f.write_text("{ not json")
    assert client.get("/api/native/system/store-links").json()["karaoke"] == "https://bighat.live/"       # broken file never breaks the buttons


# ---------- save-download ----------
def up(client, name, data, **form):
    return client.post("/api/native/system/save-download", files={"file": ("blob", io.BytesIO(data), "application/octet-stream")}, data={"filename": name, **form})


def test_a_file_lands_in_downloads(client):
    r = up(client, "bingo-cards.pdf", b"%PDF-1.4 hello")
    j = r.json()
    assert r.status_code == 200 and j["ok"] and j["filename"] == "bingo-cards.pdf" and j["size"] == 14
    assert (client.tmp / "Downloads" / "bingo-cards.pdf").read_bytes() == b"%PDF-1.4 hello"
    assert not list((client.tmp / "Downloads").glob("*.part"))


def test_same_name_never_overwrites(client):
    up(client, "story.mp4", b"one"); b = up(client, "story.mp4", b"two").json(); c = up(client, "story.mp4", b"three").json()
    assert b["filename"] == "story (2).mp4" and c["filename"] == "story (3).mp4"
    assert (client.tmp / "Downloads" / "story.mp4").read_bytes() == b"one"


@pytest.mark.parametrize("bad,expect", [("../../evil.exe", "evil.exe"), ("..\\..\\evil.exe", "evil.exe"), ("a/b/c.pdf", "c.pdf"), ('we"ird:na*me?.pdf', "weirdname.pdf"),
                                        ("CON.txt", "_CON.txt"), ("...", "download"), ("  spaced name .pdf ", "spaced name .pdf")])
def test_file_names_are_made_safe(client, bad, expect):
    j = up(client, bad, b"x").json()
    assert j["filename"] == expect and Path(j["path"]).parent == client.tmp / "Downloads"


def test_with_no_name_the_upload_name_is_used_then_download(client):
    assert up(client, "", b"x").json()["filename"] == "blob"          # the browser sent the file as "blob"
    r = client.post("/api/native/system/save-download", files={"file": ("", io.BytesIO(b"x"), "application/octet-stream")})
    assert r.status_code in (400, 422)                                 # a nameless upload part is refused safely, nothing is written


def test_empty_file_is_refused(client):
    r = up(client, "x.pdf", b"")
    assert r.status_code == 400 and not list((client.tmp / "Downloads").glob("*"))


def test_a_name_with_no_extension_or_dots_works(client):
    assert up(client, "README", b"x").json()["filename"] == "README"
    assert up(client, "my.report.final.csv", b"x").json()["filename"] == "my.report.final.csv"


def test_uses_the_file_name_from_the_upload_when_none_is_given(client):
    r = client.post("/api/native/system/save-download", files={"file": ("from-upload.png", io.BytesIO(b"png"), "image/png")})
    assert r.json()["filename"] == "from-upload.png"


def test_a_big_file_streams_through(client):
    big = b"0123456789" * 1024 * 1024 * 3                       # 30 MB
    j = up(client, "big.mp4", big).json()
    assert j["size"] == len(big) and (client.tmp / "Downloads" / "big.mp4").stat().st_size == len(big)


def test_downloads_folder_is_created_if_missing(client):
    assert not (client.tmp / "Downloads").exists()
    up(client, "a.pdf", b"x")
    assert (client.tmp / "Downloads" / "a.pdf").is_file()


def test_an_unwritable_folder_gives_a_clear_error(client, monkeypatch):
    blocker = client.tmp / "Downloads"; blocker.write_text("i am a file, not a folder")
    r = up(client, "a.pdf", b"x")
    assert r.status_code == 500 and "Downloads" in r.json()["detail"]
