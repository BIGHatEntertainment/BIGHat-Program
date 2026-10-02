"""alpha.70: Karaoke Setup - folders, master overlay, venue logos, filler music, key masking."""
import io, sys
from pathlib import Path
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def png(w, h, color=(10, 200, 30), fmt="PNG"):
    b = io.BytesIO(); Image.new("RGB", (w, h), color).save(b, fmt); return b.getvalue()


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("BIGHAT_KARAOKE_DIR", str(tmp_path / "Karaoke"))
    monkeypatch.setenv("BIGHAT_KARAOKE_SETTINGS", str(tmp_path / "cfg" / "karaoke_settings.json"))
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    from routes import karaoke_setup
    app = FastAPI(); app.include_router(karaoke_setup.router, prefix="/api")
    return TestClient(app), tmp_path


def test_folders_are_created_for_the_user(client):
    c, t = client
    r = c.get("/api/karaoke/setup").json()
    for sub in ["Master Overlay", "Venue Logos", "Song Library"]:
        assert (t / "Karaoke" / sub).is_dir(), sub
    assert r["folders"]["overlay"].endswith("Master Overlay")


def test_default_overlay_is_the_bundled_one_1920x1080(client):
    c, _ = client
    r = c.get("/api/karaoke/overlay/master")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert Image.open(io.BytesIO(r.content)).size == (1920, 1080)
    assert c.get("/api/karaoke/setup").json()["overlay"]["custom"] is False


def test_good_overlay_is_saved_and_served(client):
    c, t = client
    r = c.post("/api/karaoke/overlay/master", files={"file": ("mine.png", png(1920, 1080, (200, 0, 0)), "image/png")}).json()
    assert r["saved"] is True
    got = Image.open(io.BytesIO(c.get("/api/karaoke/overlay/master").content)).convert("RGB")
    assert got.getpixel((5, 5)) == (200, 0, 0)
    assert c.get("/api/karaoke/setup").json()["overlay"]["custom"] is True
    assert len(list((t / "Karaoke" / "Master Overlay").iterdir())) == 1


def test_wrong_size_overlay_is_refused_and_keeps_the_good_one(client):
    c, _ = client
    c.post("/api/karaoke/overlay/master", files={"file": ("a.png", png(1920, 1080, (0, 0, 200)), "image/png")})
    r = c.post("/api/karaoke/overlay/master", files={"file": ("b.png", png(1280, 720), "image/png")}).json()
    assert r["saved"] is False and r["error"] == "wrong_size" and (r["width"], r["height"]) == (1280, 720)
    got = Image.open(io.BytesIO(c.get("/api/karaoke/overlay/master").content)).convert("RGB")
    assert got.getpixel((5, 5)) == (0, 0, 200)          # still the good one


def test_reset_goes_back_to_the_bundled_overlay(client):
    c, _ = client
    c.post("/api/karaoke/overlay/master", files={"file": ("a.png", png(1920, 1080, (0, 0, 200)), "image/png")})
    assert c.delete("/api/karaoke/overlay/master").json()["reset"] is True
    assert c.get("/api/karaoke/setup").json()["overlay"]["custom"] is False


def test_not_an_image_and_bad_type(client):
    c, _ = client
    assert c.post("/api/karaoke/overlay/master", files={"file": ("a.png", b"not an image", "image/png")}).json()["error"] == "not_an_image"
    assert c.post("/api/karaoke/overlay/master", files={"file": ("a.exe", b"x", "application/octet-stream")}).status_code == 400


@pytest.mark.parametrize("w,h,ok,err", [(145, 145, True, None), (150, 150, True, None), (249, 249, True, None),
                                         (400, 380, True, None), (144, 144, False, "too_small"),
                                         (400, 200, False, "not_square"), (200, 400, False, "not_square"), (300, 100, False, "too_small")])
def test_venue_logo_size_rules(client, w, h, ok, err):
    c, _ = client
    r = c.post("/api/karaoke/venue-logo/Pub One", files={"file": ("l.png", png(w, h), "image/png")}).json()
    assert r["saved"] is ok
    if err:
        assert r["error"] == err


def test_logo_is_found_by_location_name_loosely_and_can_be_replaced_and_removed(client):
    c, t = client
    c.post("/api/karaoke/venue-logo/The Rusty Nail", files={"file": ("l.png", png(150, 150, (1, 2, 3)), "image/png")})
    for name in ["The Rusty Nail", "the rusty nail", "The Rusty Nail!"]:
        assert c.get("/api/karaoke/venue-logo/" + name).status_code == 200, name
    assert c.get("/api/karaoke/venue-logo/Other Bar").status_code == 404
    c.post("/api/karaoke/venue-logo/The Rusty Nail", files={"file": ("l2.jpg", png(160, 160, (9, 9, 9), "JPEG"), "image/jpeg")})
    assert len(list((t / "Karaoke" / "Venue Logos").iterdir())) == 1      # replaced, not duplicated
    assert c.delete("/api/karaoke/venue-logo/The Rusty Nail").status_code == 200
    assert c.get("/api/karaoke/venue-logo/The Rusty Nail").status_code == 404


def test_youtube_key_is_saved_but_never_returned(client):
    c, t = client
    key = "AIzaSyFAKEKEYFORTESTING1234567890abcd"
    r = c.post("/api/karaoke/setup", json={"youtube_api_key": key}).json()
    assert r["youtube_key_set"] is True and key not in str(r) and r["youtube_key_hint"].startswith("AIza")
    assert key not in str(c.get("/api/karaoke/setup").json())
    # an empty filler save must not wipe the key
    c.post("/api/karaoke/setup", json={"filler_folder": ""})
    assert c.get("/api/karaoke/setup").json()["youtube_key_set"] is True


def _make_drive(base):
    for artist, songs in {"ABBA": ["Waterloo.mp3", "SOS.mp3"], "Queen": ["Radio.flac"]}.items():
        (base / artist).mkdir(parents=True)
        for s in songs:
            (base / artist / s).write_bytes(b"A" * 1000)
    (base / "Empty").mkdir()
    (base / "notes.txt").write_text("x")
    (base / "loose.mp3").write_bytes(b"L" * 500)


def test_filler_folder_lists_artist_folders_and_counts(client):
    c, t = client
    drive = t / "E_drive" / "Filler"; drive.mkdir(parents=True); _make_drive(drive)
    r = c.post("/api/karaoke/setup", json={"filler_folder": str(drive)}).json()["filler"]
    assert r["ok"] and r["tracks"] == 4 and r["loose_tracks"] == 1
    assert {f["name"]: f["tracks"] for f in r["folders"]} == {"ABBA": 2, "Queen": 1}      # Empty is not listed


def test_unplugged_drive_is_reported_not_a_crash(client):
    c, t = client
    r = c.post("/api/karaoke/setup", json={"filler_folder": "E:\\Karaoke Filler"}).json()
    assert r["filler"]["ok"] is False and r["filler"]["error"] == "drive_missing"
    assert c.get("/api/karaoke/filler/folders").json()["error"] == "drive_missing"
    assert c.get("/api/karaoke/filler/tracks").status_code == 404
    # and it comes back when the drive is plugged in again
    drive = t / "E"; drive.mkdir(); _make_drive(drive)
    c.post("/api/karaoke/setup", json={"filler_folder": str(drive)})
    assert c.get("/api/karaoke/filler/folders").json()["ok"] is True


def test_filler_tracks_and_streaming_with_range(client):
    c, t = client
    drive = t / "D"; drive.mkdir(); _make_drive(drive)
    c.post("/api/karaoke/setup", json={"filler_folder": str(drive)})
    rows = c.get("/api/karaoke/filler/tracks", params={"folder": "ABBA"}).json()["tracks"]
    assert {r["name"] for r in rows} == {"Waterloo.mp3", "SOS.mp3"} and all(r["artist"] == "ABBA" for r in rows)
    assert len(c.get("/api/karaoke/filler/tracks").json()["tracks"]) == 4              # all folders
    one = next(r for r in rows if r["name"] == "SOS.mp3")
    full = c.get("/api/karaoke/filler/play/" + one["id"])
    assert full.status_code == 200 and full.headers["content-type"] == "audio/mpeg" and len(full.content) == 1000
    part = c.get("/api/karaoke/filler/play/" + one["id"], headers={"Range": "bytes=10-19"})
    assert part.status_code == 206 and len(part.content) == 10


def test_nothing_outside_the_filler_folder_can_be_read(client):
    c, t = client
    drive = t / "D"; drive.mkdir(); _make_drive(drive)
    (t / "secret.mp3").write_bytes(b"S" * 10)
    c.post("/api/karaoke/setup", json={"filler_folder": str(drive)})
    for bad in ["../secret.mp3", "ABBA/../../secret.mp3", "%2e%2e/secret.mp3", "notes.txt"]:
        assert c.get("/api/karaoke/filler/play/" + bad).status_code == 404, bad
    assert c.get("/api/karaoke/filler/tracks", params={"folder": ".."}).status_code == 404
    assert c.get("/api/karaoke/filler/tracks", params={"folder": "ABBA/.."}).status_code == 404
