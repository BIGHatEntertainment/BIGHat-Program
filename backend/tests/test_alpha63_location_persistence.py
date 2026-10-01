"""Location settings (overlay tags, names, order, admins) survive a restart.

Native mode wipes MontyDB on launch; before this fix the rebuild invented
fresh records: new location id, UUID filenames, no overlay tags, and broken
previews for any page that still held the old id."""
import os, shutil, sys, tempfile
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
pytest.importorskip("montydb")
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def world(monkeypatch):
    tmp = tempfile.mkdtemp()
    monkeypatch.setenv("BIGHAT_FILES_DIR", tmp)
    monkeypatch.setenv("BIGHAT_DB_DIR", tmp + "/db")
    monkeypatch.setenv("BIGHAT_NATIVE_MODE", "1")
    from native import locations_router as lr
    import native.db_factory as dbf

    def boot():
        dbf._native_client = None
        lr.set_database(dbf.get_db())
        async def me(request):
            return {"id": "u1", "_id": "u1", "role": "master_admin", "email": "m@x.com"}
        lr.set_current_user_resolver(me)
        app = FastAPI(); app.include_router(lr.router, prefix="/api")
        return TestClient(app)

    def restart():
        shutil.rmtree(tmp + "/db", ignore_errors=True)   # what a real launch does
        return boot()

    yield boot, restart, tmp, lr
    shutil.rmtree(tmp, ignore_errors=True)


GIF = b"GIF89a" + b"\x00" * 300


def test_overlay_tags_names_order_and_id_survive_restart(world):
    boot, restart, tmp, lr = world
    c = boot()
    loc = c.post("/api/native/locations", json={"name": "Monkey Pants Bar Grill"}).json()
    lid = loc["id"]
    ids = [c.post(f"/api/native/locations/{lid}/overlays", files={"file": (n, GIF, "image/gif")}).json()["id"]
           for n in ("round2.gif", "big.gif", "answers.gif")]
    c.patch(f"/api/native/locations/{lid}/overlays/{ids[0]}/tags", json={"applies_to_round_types": ["REG", "MISC"]})
    c.patch(f"/api/native/locations/{lid}/overlays/{ids[1]}/tags", json={"applies_to_round_types": ["BIG"]})
    c.patch(f"/api/native/locations/{lid}/overlays/{ids[2]}/tags", json={"applies_to_round_types": ["ANS"]})
    c.patch(f"/api/native/locations/{lid}/overlays/order", json={"image_ids": [ids[2], ids[0], ids[1]]})

    c = restart()
    locs = c.get("/api/native/locations").json()
    assert len(locs) == 1 and locs[0]["id"] == lid                 # SAME id
    assert locs[0]["name"] == "Monkey Pants Bar Grill"
    ov = locs[0]["overlay_images"]
    assert [o["filename"] for o in ov] == ["answers.gif", "round2.gif", "big.gif"]   # names + order
    assert [o["applies_to_round_types"] for o in ov] == [["ANS"], ["REG", "MISC"], ["BIG"]]
    for o in ov:                                                    # previews work
        assert c.get(f"/api/native/locations/{lid}/overlays/{o['id']}/raw").status_code == 200


def test_page_holding_old_location_id_still_works_after_restart(world):
    boot, restart, tmp, lr = world
    c = boot()
    lid = c.post("/api/native/locations", json={"name": "Bar"}).json()["id"]
    oid = c.post(f"/api/native/locations/{lid}/overlays", files={"file": ("a.gif", GIF, "image/gif")}).json()["id"]
    c = restart()
    c.get("/api/native/locations")                                  # triggers rebuild
    assert c.get(f"/api/native/locations/{lid}/overlays/{oid}/raw").status_code == 200


def test_branding_and_admins_survive_restart(world):
    boot, restart, tmp, lr = world
    c = boot()
    lid = c.post("/api/native/locations", json={"name": "Bar"}).json()["id"]
    c.post(f"/api/native/locations/{lid}/images", files={"file": ("logo.png", b"\x89PNG\r\n\x1a\n" + b"0" * 50, "image/png")})
    c.patch(f"/api/native/locations/{lid}/admins", json={"assigned_user_ids": ["u9", "u7"]})
    c.patch(f"/api/native/locations/{lid}", json={"name": "Bar & Grill"})
    c = restart()
    loc = c.get("/api/native/locations").json()[0]
    assert loc["name"] == "Bar & Grill"
    assert [b["filename"] for b in loc["branding_images"]] == ["logo.png"]
    assert loc["assigned_user_ids"] == ["u9", "u7"]


def test_location_json_written_for_builder(world):
    boot, restart, tmp, lr = world
    c = boot()
    loc = c.post("/api/native/locations", json={"name": "Bar"}).json()
    p = Path(tmp) / "Files" / "Locations" / loc["slug"] / "location.json"
    assert p.is_file()
    import json
    assert json.loads(p.read_text())["id"] == loc["id"]


def test_pre_alpha63_folder_without_json_still_hydrates_and_then_persists(world):
    boot, restart, tmp, lr = world
    d = Path(tmp) / "Files" / "Locations" / "old-bar" / "overlays"; d.mkdir(parents=True)
    (d / "11111111-2222-3333-4444-555555555555.gif").write_bytes(GIF)
    c = boot()
    locs = c.get("/api/native/locations").json()
    assert locs[0]["slug"] == "old-bar" and len(locs[0]["overlay_images"]) == 1
    assert (Path(tmp) / "Files" / "Locations" / "old-bar" / "location.json").is_file()   # now protected
    first_id = locs[0]["id"]
    c = restart()
    assert c.get("/api/native/locations").json()[0]["id"] == first_id                    # stable from now on


def test_deleted_overlay_does_not_come_back(world):
    boot, restart, tmp, lr = world
    c = boot()
    lid = c.post("/api/native/locations", json={"name": "Bar"}).json()["id"]
    oid = c.post(f"/api/native/locations/{lid}/overlays", files={"file": ("a.gif", GIF, "image/gif")}).json()["id"]
    assert c.delete(f"/api/native/locations/{lid}/overlays/{oid}").status_code == 204
    c = restart()
    assert c.get("/api/native/locations").json()[0]["overlay_images"] == []
