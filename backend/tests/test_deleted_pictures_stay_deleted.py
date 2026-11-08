"""v32.2.12: a picture the owner removes (branding image or round overlay) must be gone from the screen, the database, the Documents folder,
location.json AND the AppData safety copy, and must not come back after a sync or a restart. The safety net must still restore a picture whose
folder was LOST (not deleted)."""
import shutil, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from test_cloud_files_pull import env, run, PNG  # noqa: F401
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient


def web(env):
    lr = env.lr
    async def resolver(request: Request):
        return {"_id": "m1", "id": "m1", "role": "master_admin", "email": "owner@x.com", "name": "O"}
    lr.set_database(env.db); lr.set_current_user_resolver(resolver)
    app = FastAPI(); app.include_router(lr.router, prefix="/api")
    return TestClient(app)


def names(d):
    return sorted(p.name for p in d.iterdir() if p.is_file())


def backup_dir(env, slug, sub):
    from native import locations_backup
    return locations_backup.backup_root() / slug / sub


def restart(env):
    """A fresh launch: native mode wipes the database, then the app rebuilds it from disk (and the safety copy)."""
    run(env.db.locations.delete_many({}))
    return run(env.lr._hydrate_from_disk())


def setup(env, kind):
    c = web(env); env.pull_venue(); loc = env.loc(); slug = loc["slug"]
    route = "images" if kind == "branding" else "overlays"
    up = c.post(f"/api/native/locations/{loc['id']}/{route}", files={"file": ("mine.png", PNG, "image/png")})
    assert up.status_code == 201
    env.add("f1", "image" if kind == "branding" else "overlay", "cloud.png", PNG + b"2"); env.pull()
    d = env.lr._branding_dir(slug) if kind == "branding" else env.lr._overlays_dir(slug)
    return c, env.loc(), slug, route, d


def _delete_all_then_check(env, kind):
    c, loc, slug, route, d = setup(env, kind)
    field = "branding_images" if kind == "branding" else "overlay_images"
    sub = "branding" if kind == "branding" else "overlays"
    assert len(names(d)) == 2 and len(names(backup_dir(env, slug, sub))) == 2          # both are in Documents AND the safety copy
    for r in list(loc[field]):
        assert c.delete(f"/api/native/locations/{loc['id']}/{route}/{r['id']}").status_code == 204
    assert env.loc()[field] == [] and names(d) == [] and names(backup_dir(env, slug, sub)) == []   # gone everywhere at once
    env.pull(); assert env.loc()[field] == [] and names(d) == []                         # a sync does not bring them back
    restart(env)
    assert env.loc()[field] == [] and names(d) == []                                     # nor does a restart (the reported bug)


def test_a_deleted_branding_image_stays_deleted_after_a_sync_and_a_restart(env):
    _delete_all_then_check(env, "branding")


def test_a_deleted_round_overlay_stays_deleted_after_a_sync_and_a_restart(env):
    _delete_all_then_check(env, "overlays")


def test_deleting_one_picture_leaves_the_others_alone(env):
    c, loc, slug, route, d = setup(env, "branding")
    mine = next(r for r in loc["branding_images"] if r["uploaded_by"] != "cloud-sync")
    c.delete(f"/api/native/locations/{loc['id']}/{route}/{mine['id']}")
    restart(env)
    left = env.loc()["branding_images"]
    assert [r["uploaded_by"] for r in left] == ["cloud-sync"] and len(names(d)) == 1


def test_location_json_no_longer_lists_a_deleted_picture(env):
    import json
    c, loc, slug, route, d = setup(env, "branding")
    mine = next(r for r in loc["branding_images"] if r["uploaded_by"] != "cloud-sync")
    c.delete(f"/api/native/locations/{loc['id']}/{route}/{mine['id']}")
    saved = json.loads(env.lr._location_json_path(slug).read_text(encoding="utf-8"))
    assert mine["id"] not in [r["id"] for r in saved["branding_images"]]


def test_the_safety_net_still_restores_pictures_when_the_documents_folder_is_lost_not_deleted(env):
    c, loc, slug, route, d = setup(env, "branding")
    shutil.rmtree(env.lr._files_locations_root() / slug)                                  # OneDrive / a reset wipes the folder
    restart(env)
    got = env.loc()
    assert got and len(got["branding_images"]) == 2 and len(names(env.lr._branding_dir(slug))) == 2


def test_deleting_a_picture_whose_file_is_already_gone_still_clears_it_everywhere(env):
    c, loc, slug, route, d = setup(env, "branding")
    mine = next(r for r in loc["branding_images"] if r["uploaded_by"] != "cloud-sync")
    (d / f"{mine['id']}{mine['ext']}").unlink()                                           # the file vanished, the record is stale
    assert c.delete(f"/api/native/locations/{loc['id']}/{route}/{mine['id']}").status_code == 204
    restart(env)
    assert [r["uploaded_by"] for r in env.loc()["branding_images"]] == ["cloud-sync"]


def test_a_cloud_picture_that_changes_type_does_not_leave_its_old_copy_to_come_back(env):
    """png -> gif: the sync removes the old .png; the safety copy must not bring it back at the next start."""
    GIF = b"GIF89a" + b"y" * 400
    web(env)                                                                             # hands the database to the locations router
    env.pull_venue(); env.add("f1", "image", "logo.png", PNG); env.pull()
    loc = env.loc(); slug = loc["slug"]; d = env.lr._branding_dir(slug)
    env.files.clear(); env.add("f1", "image", "logo.gif", GIF); env.pull()
    assert [p.suffix for p in d.iterdir()] == [".gif"]
    restart(env)
    after = run(env.db.locations.find_one({"slug": slug}, {"_id": 0}))
    assert [p.suffix for p in env.lr._branding_dir(slug).iterdir()] == [".gif"] and len(after["branding_images"]) == 1
