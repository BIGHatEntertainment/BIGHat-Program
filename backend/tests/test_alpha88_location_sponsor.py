"""alpha.88: each location has ONE sponsor slide image; it survives a restart and a Documents wipe."""
import shutil, sys, tempfile
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
pytest.importorskip("montydb")
from fastapi import FastAPI
from fastapi.testclient import TestClient

PNG1 = b"\x89PNG\r\n\x1a\n" + b"1" * 300
PNG2 = b"\x89PNG\r\n\x1a\n" + b"2" * 300


@pytest.fixture
def world(monkeypatch):
    tmp = tempfile.mkdtemp()
    monkeypatch.setenv("BIGHAT_FILES_DIR", tmp)
    monkeypatch.setenv("BIGHAT_DATA_DIR", tmp + "/appdata")     # the AppData safety copy stays in the temp folder
    monkeypatch.setenv("BIGHAT_DB_DIR", tmp + "/db")
    monkeypatch.setenv("BIGHAT_NATIVE_MODE", "1")
    from native import locations_router as lr
    import native.db_factory as dbf

    def boot(role="master_admin"):
        dbf._native_client = None
        lr.set_database(dbf.get_db())
        async def me(request):
            return {"id": "u1", "_id": "u1", "role": role, "email": "m@x.com"}
        lr.set_current_user_resolver(me)
        app = FastAPI(); app.include_router(lr.router, prefix="/api")
        return TestClient(app)

    def restart():
        shutil.rmtree(tmp + "/db", ignore_errors=True)
        return boot()

    yield boot, restart, tmp, lr
    shutil.rmtree(tmp, ignore_errors=True)


U = "/api/native/locations"


def sponsor_files(tmp, slug="monkey-pants-bar-grill"):
    d = Path(tmp) / "Files" / "Locations" / slug / "sponsor"
    return sorted(p.name for p in d.glob("*")) if d.is_dir() else []


def test_upload_get_replace_delete(world):
    boot, restart, tmp, lr = world
    c = boot()
    lid = c.post(U, json={"name": "Monkey Pants Bar Grill"}).json()["id"]
    assert c.get(f"{U}/{lid}/sponsor/raw").status_code == 404            # none yet
    r1 = c.post(f"{U}/{lid}/sponsor", files={"file": ("a.png", PNG1, "image/png")})
    assert r1.status_code == 201 and len(sponsor_files(tmp)) == 1
    assert c.get(f"{U}/{lid}/sponsor/raw").content == PNG1
    r2 = c.post(f"{U}/{lid}/sponsor", files={"file": ("b.png", PNG2, "image/png")})
    assert r2.status_code == 201 and r2.json()["id"] != r1.json()["id"]
    assert len(sponsor_files(tmp)) == 1                                   # ONE image: the old file is gone
    assert c.get(f"{U}/{lid}/sponsor/raw").content == PNG2
    assert c.delete(f"{U}/{lid}/sponsor").status_code == 204
    assert sponsor_files(tmp) == [] and c.get(f"{U}/{lid}/sponsor/raw").status_code == 404
    assert c.delete(f"{U}/{lid}/sponsor").status_code == 404


def test_bad_uploads_are_refused(world):
    boot, restart, tmp, lr = world
    c = boot()
    lid = c.post(U, json={"name": "Monkey Pants Bar Grill"}).json()["id"]
    assert c.post(f"{U}/{lid}/sponsor", files={"file": ("a.exe", b"MZ" + b"0" * 50, "application/x-msdownload")}).status_code == 415
    assert c.post(f"{U}/{lid}/sponsor", files={"file": ("a.png", b"", "image/png")}).status_code == 400
    assert sponsor_files(tmp) == []
    assert c.post(f"{U}/nope/sponsor", files={"file": ("a.png", PNG1, "image/png")}).status_code in (403, 404)


def test_survives_restart_and_the_list_shows_it(world):
    boot, restart, tmp, lr = world
    c = boot()
    lid = c.post(U, json={"name": "Monkey Pants Bar Grill"}).json()["id"]
    rec = c.post(f"{U}/{lid}/sponsor", files={"file": ("a.png", PNG1, "image/png")}).json()
    c2 = restart()                                                         # DB wiped, like a real launch
    locs = c2.get(U).json()
    loc = [l for l in (locs if isinstance(locs, list) else locs.get("locations", [])) if l["id"] == lid][0]
    assert loc["sponsor_image"]["id"] == rec["id"]
    assert c2.get(f"{U}/{lid}/sponsor/raw").content == PNG1


def test_documents_wipe_is_restored_from_the_appdata_copy(world):
    boot, restart, tmp, lr = world
    from native import locations_backup as lb
    c = boot()
    lid = c.post(U, json={"name": "Monkey Pants Bar Grill"}).json()["id"]
    c.post(f"{U}/{lid}/sponsor", files={"file": ("a.png", PNG1, "image/png")})
    c.post(f"{U}/{lid}/sponsor", files={"file": ("b.png", PNG2, "image/png")})     # replaces a.png
    shutil.rmtree(Path(tmp) / "Files" / "Locations" / "monkey-pants-bar-grill")   # Documents folder lost
    lb.restore_missing()
    assert len(sponsor_files(tmp)) == 1                  # only the CURRENT image comes back, not the old one
    c2 = restart()
    c2.get(U)
    assert c2.get(f"{U}/{lid}/sponsor/raw").content == PNG2


def test_an_admin_of_another_location_cannot_touch_it(world):
    boot, restart, tmp, lr = world
    c = boot()
    lid = c.post(U, json={"name": "Monkey Pants Bar Grill"}).json()["id"]
    c.post(f"{U}/{lid}/sponsor", files={"file": ("a.png", PNG1, "image/png")})
    c3 = boot(role="admin")                       # an admin who is not assigned to this location
    assert c3.post(f"{U}/{lid}/sponsor", files={"file": ("x.png", PNG2, "image/png")}).status_code in (403, 404)
    assert c3.delete(f"{U}/{lid}/sponsor").status_code in (403, 404)
    assert c3.get(f"{U}/{lid}/sponsor/raw").status_code in (403, 404)
    assert boot().get(f"{U}/{lid}/sponsor/raw").content == PNG1


def test_deleting_the_location_removes_its_sponsor_folder(world):
    boot, restart, tmp, lr = world
    c = boot()
    lid = c.post(U, json={"name": "Monkey Pants Bar Grill"}).json()["id"]
    c.post(f"{U}/{lid}/sponsor", files={"file": ("a.png", PNG1, "image/png")})
    assert c.delete(f"{U}/{lid}").status_code == 409     # alpha.80: it has a Schedule venue, so delete it THERE
    import asyncio
    asyncio.run(lr._db.venues.delete_many({}))            # the venue was removed from the Schedule
    assert c.delete(f"{U}/{lid}").status_code == 204
    assert not (Path(tmp) / "Files" / "Locations" / "monkey-pants-bar-grill").exists()
    assert not (Path(tmp) / "Files" / "Locations" / "monkey-pants-bar-grill" / "sponsor").exists()
