"""alpha.75: Story Generator images are stored on the PC (Files/Story/{Trivia,Bingo,Karaoke,Hosts})."""
import io, shutil, sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

JPG = b"\xff\xd8\xff\xe0" + b"0" * 200
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 200
GIF = b"GIF89a" + b"0" * 200


@pytest.fixture
def si(tmp_path, monkeypatch):
    monkeypatch.setenv("BIGHAT_DATA_ROOT", str(tmp_path / "AppData"))
    monkeypatch.setenv("BIGHAT_FILES_DIR", str(tmp_path / "Docs"))
    import importlib
    from native import data_map, story_images
    importlib.reload(data_map); importlib.reload(story_images)
    return story_images


def test_folders_are_created_with_the_right_names(si):
    si.ensure_folders()
    assert sorted(p.name for p in si.root().iterdir()) == ["Bingo", "Hosts", "Karaoke", "Trivia"]
    assert si.root().name == "Story" and si.root().parent.name == "Files"


def test_trivia_holds_a_location_image_and_a_background(si):
    si.save("trivia", "Monkey Pants", JPG)
    si.save("Trivia", "Monkey Pants", PNG, variant="background", ext=".png")
    names = sorted(f["filename"] for f in si.list_files("Trivia"))
    assert names == ["Monkey Pants.jpg", "Monkey Pants_background.png"]
    locs = si.locations("Trivia")
    assert len(locs) == 1 and locs[0]["name"] == "Monkey Pants" and locs[0]["has_background"] is True


def test_bingo_and_karaoke_hold_only_a_location_image(si):
    si.save("bingo", "The Pub", JPG); si.save("karaoke", "The Pub", PNG, ext=".png")
    assert [l["name"] for l in si.locations("bingo")] == ["The Pub"]
    assert [l["name"] for l in si.locations("karaoke")] == ["The Pub"]
    with pytest.raises(ValueError):
        si.save("bingo", "The Pub", JPG, variant="background")                 # only trivia has a background
    assert si.list_files("Trivia") == []                                       # folders are separate


def test_a_gif_is_only_allowed_for_hosts(si):
    si.save("hosts", "Alex", GIF, ext=".gif")
    assert si.hosts() == [{"id": "Alex.gif", "name": "Alex", "filename": "Alex.gif", "is_gif": True}]
    with pytest.raises(ValueError):
        si.save("trivia", "Pub", GIF, ext=".gif")


def test_bad_uploads_are_refused(si):
    for kind, name, data in (("trivia", "", JPG), ("trivia", "X", b""), ("trivia", "X", b"not an image"), ("trivia", "X", b"\xff\xd8\xff" + b"0" * (16 * 1024 * 1024)), ("nope", "X", JPG)):
        with pytest.raises(ValueError):
            si.save(kind, name, data)
    assert si.list_files("Trivia") == []


def test_names_match_loosely_like_the_trivia_story_expects(si):
    si.save("trivia", "Monkey Pants", JPG)
    for q in ("monkey_pants", "01_Monkey_Pants", "MONKEY PANTS", "Monkey  Pants"):
        assert si.find("Trivia", q) is not None, q
    assert si.find("Trivia", "other") is None and si.find("Trivia", "") is None


def test_replacing_an_image_keeps_one_file(si):
    si.save("trivia", "Pub", JPG)
    si.save("trivia", "pub", PNG, ext=".png")                                 # same place, new picture and extension
    f = si.list_files("Trivia")
    assert len(f) == 1 and f[0]["filename"] == "pub.png"
    assert not any((si.backup_root() / "Trivia").glob("*.jpg"))               # the old safety copy went too


def test_a_safety_copy_is_kept_and_restores_a_lost_documents_folder(si):
    si.save("trivia", "Pub", JPG); si.save("bingo", "Pub", PNG, ext=".png"); si.save("hosts", "Alex", GIF, ext=".gif")
    assert (si.backup_root() / "Trivia" / "Pub.jpg").is_file()
    shutil.rmtree(si.root())                                                   # Documents folder lost
    assert [f["name"] for f in si.list_files("Trivia")] == ["Pub"]
    assert (si.root() / "Trivia" / "Pub.jpg").read_bytes() == JPG              # copied back
    assert si.find("Bingo", "pub") is not None and si.find("Hosts", "alex") is not None


def test_delete_removes_both_copies_and_it_stays_deleted(si):
    r = si.save("trivia", "Pub", JPG)
    assert si.delete_file("trivia", r["filename"]) is True
    assert si.list_files("Trivia") == [] and si.delete_file("trivia", r["filename"]) is False
    for bad in ("../x.jpg", "a/b.jpg", "..\\x.jpg", ".hidden", ""):
        assert si.delete_file("trivia", bad) is False and si.read_by_filename("trivia", bad) is None


def test_hostile_names_cannot_escape_the_folder(si):
    r = si.save("trivia", "../../evil", JPG)
    assert "/" not in r["filename"] and ".." not in r["filename"]
    assert (si.root() / "Trivia" / r["filename"]).is_file()
    assert not (si.root().parent / "evil.jpg").exists()


def test_a_half_written_file_is_never_listed(si):
    si.ensure_folders()
    (si.root() / "Trivia" / "Broken.jpg.part").write_bytes(b"x")
    assert si.list_files("Trivia") == []


# ---- the HTTP routes, through the real router ----
@pytest.fixture
def client(si, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import routes.story_generator as sg
    app = FastAPI(); app.include_router(sg.router, prefix="/api")
    app.dependency_overrides = {d.dependency: (lambda: None) for r in sg.router.routes for d in getattr(r, "dependencies", [])}
    return TestClient(app)


def test_routes_upload_list_fetch_delete(client):
    r = client.post("/api/story-generator/story-images/trivia", files={"file": ("a.jpg", JPG, "image/jpeg")}, data={"name": "Monkey Pants"})
    assert r.status_code == 200 and r.json()["filename"] == "Monkey Pants.jpg"
    assert client.post("/api/story-generator/story-images/trivia", files={"file": ("b.jpg", JPG, "image/jpeg")}, data={"name": "Monkey Pants", "variant": "background"}).status_code == 200
    lst = client.get("/api/story-generator/story-images/trivia").json()
    assert [f["filename"] for f in lst["files"]] == ["Monkey Pants.jpg", "Monkey Pants_background.jpg"] and lst["folder"].endswith("Trivia")
    assert client.get("/api/story-generator/story-images/trivia/file/Monkey Pants.jpg").content == JPG
    assert client.get("/api/story-generator/story-images/trivia/file/nope.jpg").status_code == 404
    assert client.get("/api/story-generator/story-images/bogus").status_code == 400
    assert client.post("/api/story-generator/story-images/bingo", files={"file": ("x.txt", b"hi", "text/plain")}, data={"name": "X"}).status_code == 400
    assert client.delete("/api/story-generator/story-images/trivia/file/Monkey Pants.jpg").status_code == 200
    assert client.delete("/api/story-generator/story-images/trivia/file/Monkey Pants.jpg").status_code == 404


def test_event_lists_come_from_the_story_folders_not_sharepoint(client):
    client.post("/api/story-generator/story-images/bingo", files={"file": ("a.jpg", JPG, "image/jpeg")}, data={"name": "Bingo Bar"})
    client.post("/api/story-generator/story-images/karaoke", files={"file": ("a.jpg", JPG, "image/jpeg")}, data={"name": "Sing Bar"})
    client.post("/api/story-generator/story-images/hosts", files={"file": ("a.gif", GIF, "image/gif")}, data={"name": "Alex"})
    b = client.get("/api/story-generator/event-assets/bingo").json()
    k = client.get("/api/story-generator/event-assets/karaoke").json()
    assert [l["name"] for l in b["locations"]] == ["Bingo Bar"] and [l["name"] for l in k["locations"]] == ["Sing Bar"]
    assert b["hosts"][0]["name"] == "Alex" and b["hosts"][0]["is_gif"] is True and b["success"] is True
    assert client.get("/api/story-generator/event-assets/trivia").status_code == 400


def test_event_preview_reads_the_local_images(client):
    client.post("/api/story-generator/story-images/bingo", files={"file": ("a.jpg", JPG, "image/jpeg")}, data={"name": "Bingo Bar"})
    client.post("/api/story-generator/story-images/hosts", files={"file": ("a.gif", GIF, "image/gif")}, data={"name": "Alex"})
    r = client.post("/api/story-generator/event-preview", json={"event_type": "bingo", "location_id": "Bingo Bar.jpg", "host_id": "Alex.gif", "host_is_gif": True})
    j = r.json()
    assert r.status_code == 200 and j["locationImage"].startswith("data:image/png;base64,") and j["hostImage"].startswith("data:image/gif;base64,")
    r2 = client.post("/api/story-generator/event-preview", json={"event_type": "karaoke", "location_id": "Bingo Bar.jpg", "host_id": "Alex.gif"}).json()
    assert r2["locationImage"] is None                                          # a bingo picture is not offered to karaoke


def test_the_trivia_story_finds_its_location_background_and_host_locally(si):
    from PIL import Image
    def real(fmt, color):
        b = io.BytesIO(); Image.new("RGB", (40, 60), color).save(b, fmt); return b.getvalue()
    si.save("trivia", "Monkey Pants", real("JPEG", "red")); si.save("trivia", "Monkey Pants", real("PNG", "blue"), variant="background", ext=".png")
    si.save("hosts", "alex", real("GIF", "green"), ext=".gif")
    from story_generator_service import StoryGeneratorService
    svc = StoryGeneratorService.__new__(StoryGeneratorService)
    loc = svc._get_location_image("monkey_pants"); bg = svc._get_background_image("monkey_pants")
    assert loc is not None and loc.size == (40, 60) and bg is not None and bg.size == (40, 60)
    host, is_gif = svc._get_host_image("alex")
    assert host is not None and is_gif is True
