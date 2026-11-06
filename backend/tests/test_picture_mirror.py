"""A LINKED PC's branding images and round overlays match the Cloud (new/changed arrive; Cloud-removed ones go after a confirm).
An UNLINKED PC is untouched. The owner's own pictures, tags and order are never overridden. Real pull + files + HTTP routes; only the Cloud's answer is faked."""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from test_cloud_files_pull import env, run, PNG, sha  # noqa: F401
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient


def web(env):
    lr = env.lr
    async def resolver(request: Request):
        return {"_id": "m1", "id": "m1", "role": "master_admin", "email": "owner@x.com", "name": "O"}
    lr.set_database(env.db); lr.set_current_user_resolver(resolver)
    from native import cloud_link_router as clr
    import importlib; importlib.reload(clr)
    env.mp.setattr(clr, "_db", lambda: env.db)
    app = FastAPI(); app.include_router(lr.router, prefix="/api"); app.include_router(clr.router)
    return TestClient(app), clr


def cloud(env, complete=True, venues=None):
    """The Cloud's manifest in the shape the Cloud task specifies: complete + venues + per-file sort_order / applies_to_round_types / meta_version.
    Call it AFTER env.pull_venue(): the linked venue's id is a uuid, read here once (plain code, not inside the async manifest)."""
    vs = list(venues) if venues is not None else ["v1"]            # the CLOUD's venue id (the PC maps it to its own uuid through the sync id map)
    async def manifest():
        return {"ok": True, "files": [dict(f) for f in env.files], "complete": complete, "venues": vs}
    env.mp.setattr(env.cf, "_fetch_manifest", manifest)
    from native import picture_mirror
    return picture_mirror


def add(env, fid, cat, name, data=None, **meta):
    env.add(fid, cat, name, data or (PNG + fid.encode()))
    env.files[-1].update(meta)


def recs(env, field):
    loc = env.loc()
    return {r["id"]: r for r in (loc.get(field) or [])}


def sid(env, fid):
    return env.cf.stable_id(fid)


# ---------- pulling ----------
def test_a_linked_pc_pulls_branding_and_overlays_with_the_clouds_order_and_tags(env):
    env.pull_venue(); pm = cloud(env)
    add(env, "b1", "image", "one.png", sort_order=1, meta_version=1); add(env, "b2", "image", "two.png", sort_order=0, meta_version=1)
    add(env, "o1", "overlay", "ov.png", sort_order=0, meta_version=1, applies_to_round_types=["mc", "ANS", "bogus"])
    add(env, "o2", "overlay", "ov2.png", sort_order=1, meta_version=1, applies_to_round_types=[])
    add(env, "o3", "overlay", "ov3.png", sort_order=2, meta_version=1)                                  # no tag key = untagged
    env.pull()
    b = recs(env, "branding_images"); o = recs(env, "overlay_images")
    assert b[sid(env, "b2")]["order"] == 0 and b[sid(env, "b1")]["order"] == 1
    assert o[sid(env, "o1")]["applies_to_round_types"] == ["MC", "ANS"]                                 # cleaned, bad tag dropped
    assert o[sid(env, "o2")]["applies_to_round_types"] == []                                            # dormant stays dormant
    assert "applies_to_round_types" not in o[sid(env, "o3")]                                            # untagged stays untagged


def test_an_old_cloud_with_no_order_or_tags_behaves_exactly_as_before(env):
    env.pull_venue(); cloud(env)
    add(env, "b1", "image", "one.png"); add(env, "o1", "overlay", "ov.png")
    env.pull()
    assert "applies_to_round_types" not in recs(env, "overlay_images")[sid(env, "o1")] and len(recs(env, "branding_images")) == 1


def test_a_tag_only_change_in_the_cloud_reaches_the_pc_even_though_the_file_is_the_same(env):
    env.pull_venue(); cloud(env)
    add(env, "o1", "overlay", "ov.png", meta_version=1, applies_to_round_types=["MC"]); env.pull()
    env.files[0].update(meta_version=2, applies_to_round_types=["REG2", "ANS"]); env.calls.clear(); r = env.pull()
    assert recs(env, "overlay_images")[sid(env, "o1")]["applies_to_round_types"] == ["REG2", "ANS"] and r["counts"]["updated"] == 1


def test_a_tag_or_order_the_owner_set_on_this_pc_is_never_overridden_by_the_cloud(env):
    env.pull_venue(); cloud(env); c, clr = web(env)
    add(env, "o1", "overlay", "ov.png", meta_version=1, applies_to_round_types=["MC"], sort_order=0); env.pull()
    loc = env.loc(); oid = sid(env, "o1")
    assert c.patch(f"/api/native/locations/{loc['id']}/overlays/{oid}/tags", json={"applies_to_round_types": ["BIG"]}).status_code == 200
    env.files[0].update(meta_version=2, applies_to_round_types=["MYS"], sort_order=5); env.pull()
    o = recs(env, "overlay_images")[oid]
    assert o["applies_to_round_types"] == ["BIG"] and o["owner_set"] is True and o["order"] == 0


def test_the_owners_own_picture_is_never_touched_by_a_pull(env):
    env.pull_venue(); cloud(env); c, clr = web(env)
    loc = env.loc()
    c.post(f"/api/native/locations/{loc['id']}/images", files={"file": ("mine.png", PNG, "image/png")})
    add(env, "b1", "image", "cloud.png", sort_order=0, meta_version=1); env.pull()
    mine = [r for r in recs(env, "branding_images").values() if r["uploaded_by"] != "cloud-sync"]
    assert len(mine) == 1 and mine[0]["filename"] == "mine.png"


# ---------- removing (the risky half) ----------
def _linked_with(env, n=4):
    env.pull_venue(); pm = cloud(env)
    for i in range(n): add(env, f"b{i}", "image", f"p{i}.png", sort_order=i, meta_version=1)
    env.pull(); return pm


def test_check_changes_nothing_and_lists_what_the_cloud_no_longer_has(env):
    pm = _linked_with(env, 4); env.files[:] = [f for f in env.files if f["file_id"] != "b3"]
    before = recs(env, "branding_images")
    r = run(pm.check(env.db))
    assert r["ok"] and r["safe"] and [x["id"] for x in r["remove"]] == [sid(env, "b3")] and recs(env, "branding_images") == before


def test_remove_deletes_the_file_the_record_and_the_safety_copy_and_stays_gone(env):
    pm = _linked_with(env, 4); env.files[:] = [f for f in env.files if f["file_id"] != "b3"]
    chk = run(pm.check(env.db)); res = run(pm.remove(env.db, chk["token"]))
    assert res["ok"] and res["removed"] == 1 and Path(res["backup"]).exists()
    d = env.lr._branding_dir(env.loc()["slug"]); gone = sid(env, "b3")
    assert not list(d.glob(gone + ".*")) and gone not in recs(env, "branding_images")
    from native import locations_backup as lb
    assert not list((lb.backup_root() / env.loc()["slug"] / "branding").glob(gone + ".*"))
    run(env.db.locations.delete_many({})); web(env); run(env.lr._hydrate_from_disk())                      # a restart does not bring it back
    assert gone not in recs(env, "branding_images") and sorted(r["order"] for r in recs(env, "branding_images").values()) == [0, 1, 2]


def test_an_owners_own_picture_is_never_listed_or_removed_even_when_the_cloud_does_not_have_it(env):
    pm = _linked_with(env, 4); c, clr = web(env); loc = env.loc()
    c.post(f"/api/native/locations/{loc['id']}/images", files={"file": ("mine.png", PNG, "image/png")})
    env.files[:] = [f for f in env.files if f["file_id"] != "b3"]
    chk = run(pm.check(env.db)); run(pm.remove(env.db, chk["token"]))
    assert any(r["filename"] == "mine.png" for r in recs(env, "branding_images").values())


def test_an_incomplete_or_old_style_cloud_answer_removes_nothing(env):
    pm = _linked_with(env, 4); env.files[:] = [f for f in env.files if f["file_id"] != "b3"]
    for complete in (False, None):
        cloud(env, complete=complete)
        r = run(pm.check(env.db))
        assert r["safe"] is False and r["remove"] == [] and r["token"] == ""
    async def old():                                                                                      # an old Cloud: no complete/venues keys at all
        return {"ok": True, "files": [dict(f) for f in env.files]}
    env.mp.setattr(env.cf, "_fetch_manifest", old)
    assert run(pm.check(env.db))["safe"] is False


def test_a_venue_the_cloud_did_not_cover_is_left_alone(env):
    pm = _linked_with(env, 3); env.files.clear(); cloud(env, venues=("some-other-venue",))
    assert run(pm.check(env.db))["remove"] == []


def test_one_run_never_removes_more_than_half_of_a_venues_cloud_pictures(env):
    pm = _linked_with(env, 4); env.files.clear()                                                          # the Cloud list suddenly empty
    r = run(pm.check(env.db))
    assert r["remove"] == [] and len(r["kept"]) == 4 and "glitch" in r["kept"][0]["why"]
    env.files[:] = []; add(env, "b0", "image", "p0.png", sort_order=0, meta_version=1); add(env, "b1", "image", "p1.png", sort_order=1, meta_version=1)
    assert len(run(pm.check(env.db))["remove"]) == 2                                                      # exactly half is allowed


def test_a_stale_or_missing_token_removes_nothing(env):
    pm = _linked_with(env, 4); env.files[:] = [f for f in env.files if f["file_id"] != "b3"]
    assert run(pm.remove(env.db, ""))["error"] == "no_token"
    chk = run(pm.check(env.db)); env.files[:] = [f for f in env.files if f["file_id"] != "b2"]
    res = run(pm.remove(env.db, chk["token"]))
    assert res["ok"] is False and res["error"] == "changed" and len(recs(env, "branding_images")) == 4


def test_an_unlinked_pc_is_untouched(env):
    from native import cloud_link, picture_mirror
    _linked_with(env, 3)
    env.mp.setattr(cloud_link, "get_token", lambda: None)
    r = run(picture_mirror.check(env.db))
    assert r["ok"] is False and r["error"] == "not_linked" and len(recs(env, "branding_images")) == 3
    assert run(picture_mirror.remove(env.db, "x"))["ok"] is False


def test_cloud_trouble_removes_nothing(env):
    pm = _linked_with(env, 3)
    async def down(): return {"ok": False, "error": "unreachable"}
    env.mp.setattr(env.cf, "_fetch_manifest", down)
    r = run(pm.check(env.db))
    assert r["ok"] is False and r["error"] == "unreachable" and len(recs(env, "branding_images")) == 3


def test_the_real_http_routes_check_then_remove(env):
    pm = _linked_with(env, 4); c, clr = web(env); env.files[:] = [f for f in env.files if f["file_id"] != "b3"]
    chk = c.post(clr.router.prefix + "/pictures/check").json()
    assert chk["can_remove"] == 1 and len(recs(env, "branding_images")) == 4
    assert c.post(clr.router.prefix + "/pictures/remove", json={"token": ""}).json()["error"] == "no_token"
    done = c.post(clr.router.prefix + "/pictures/remove", json={"token": chk["token"]}).json()
    assert done["ok"] and done["removed"] == 1 and len(recs(env, "branding_images")) == 3


def test_a_pc_with_no_cloud_account_pulls_nothing_changes_nothing_and_loses_nothing(env):
    """The default for a Program: no Cloud link means none of this runs, and the owner's pictures are exactly as they were."""
    from native import cloud_link, picture_mirror
    env.pull_venue(); cloud(env); c, clr = web(env); loc = env.loc()
    c.post(f"/api/native/locations/{loc['id']}/images", files={"file": ("mine.png", PNG, "image/png")})
    add(env, "b1", "image", "cloud.png", sort_order=0, meta_version=1)
    env.mp.setattr(cloud_link, "get_token", lambda: None)
    before = recs(env, "branding_images"); r = env.pull()
    assert r["state"] == "not_linked" and recs(env, "branding_images") == before and env.calls == []
    assert run(picture_mirror.check(env.db))["error"] == "not_linked"
    assert [x["filename"] for x in before.values()] == ["mine.png"]
