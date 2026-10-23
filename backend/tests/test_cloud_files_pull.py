"""v32.3.0: the Program pulls the Cloud's FILES (.bighat, location overlays/pictures). Real MontyDB, real files, real importer;
only the HTTP (manifest + download) is faked, with the same shapes the Cloud's /api/program/manifest and /files/{id} return."""
import asyncio, hashlib, importlib, io, json, os, sys, zipfile
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tests"))
from test_cloud_sync import feed, V, PR, run   # noqa: E402

PNG = b"\x89PNG\r\n\x1a\n" + b"x" * 400
GIF = b"GIF89a" + b"y" * 400


def sha(b): return hashlib.sha256(b).hexdigest()


@pytest.fixture
def env(tmp_path, monkeypatch):
    home = tmp_path / "home"; home.mkdir()
    for k in ("HOME", "USERPROFILE"):
        monkeypatch.setenv(k, str(home))
    monkeypatch.setenv("BIGHAT_CONFIG_PATH", str(tmp_path / "system_config.json"))
    monkeypatch.setenv("BIGHAT_NATIVE_MODE", "1")
    monkeypatch.setenv("BIGHAT_DATA_ROOT", str(tmp_path / "app"))
    monkeypatch.setenv("BIGHAT_FILES_DIR", str(home / "Documents" / "BIG Hat Entertainment" / "Files"))
    (tmp_path / "db").mkdir()
    monkeypatch.setenv("BIGHAT_DB_DIR", str(tmp_path / "db"))
    monkeypatch.setenv("BIGHAT_CLOUD_BASE_URL", "https://cloud.test")
    from native import db_factory
    importlib.reload(db_factory)
    import native.config as cfg
    importlib.reload(cfg)
    import native
    native.config_manager = cfg.config_manager
    from native import admin_router, employee_sync, cloud_link, cloud_sync, schedule_safety, data_map
    for m in (data_map, admin_router, employee_sync, cloud_link, cloud_sync):
        importlib.reload(m)
    from native import cloud_files, locations_router, venue_sync
    for m in (locations_router, venue_sync, cloud_files):
        importlib.reload(m)
    cfg.config_manager.config["users"] = [{"id": "m1", "email": "owner@x.com", "role": "master_admin", "is_master": True, "password_hash": "x", "first_name": "Owner"}]
    monkeypatch.setattr(cloud_link, "get_token", lambda: "tok")
    monkeypatch.setattr(schedule_safety, "folder", lambda: (tmp_path / "sched").mkdir(exist_ok=True) or tmp_path / "sched")
    db = db_factory.get_db()
    e = type("E", (), {})()
    e.db, e.cs, e.cf, e.lr, e.home, e.tmp, e.mp = db, cloud_sync, cloud_files, locations_router, home, tmp_path, monkeypatch
    e.files, e.bytes, e.calls = [], {}, []

    async def manifest():
        return {"ok": True, "files": [dict(f) for f in e.files]}

    async def download(fid, want_sha, max_bytes):
        e.calls.append(fid)
        data = e.bytes.get(fid)
        if data is None:
            return None, "http_404"
        if len(data) > max_bytes:
            return None, "too_large"
        if sha(data) != want_sha:
            return None, "checksum_mismatch"
        return data, ""
    monkeypatch.setattr(cloud_files, "_fetch_manifest", manifest)
    monkeypatch.setattr(cloud_files, "_download", download)

    def add(fid, category, name, data, venue_id="v1", sha_override=None):
        e.files.append({"file_id": fid, "area": "trivia", "category": category, "venue_id": venue_id, "name": name, "size": len(data),
                        "sha256": sha_override or sha(data), "updated_at": "2026-10-23T00:00:00+00:00"})
        e.bytes[fid] = data
    e.add = add

    def pull_venue(name="Monkey Pants Bar & Grill"):
        feed(cloud_sync, monkeypatch, [{"seq": 2, "has_more": False, "items": [V("v1", name), PR("v1")]}])
        run(cloud_sync.pull_once(db, approve_first_link=True))
    e.pull_venue = pull_venue
    e.pull = lambda: run(cloud_files.pull_once(db))
    e.loc = lambda: run(db.locations.find_one({"venue_id": {"$ne": None}}, {"_id": 0}))
    e.root = lambda: Path(os.environ["BIGHAT_FILES_DIR"])
    yield e
    db_factory.close_all()


def test_the_test_cannot_write_outside_its_own_folder(env):
    env.pull_venue()
    loc = env.loc()
    assert str(env.tmp) in str(env.lr._overlays_dir(loc["slug"]))


def test_an_overlay_lands_in_the_location_folder_and_its_record(env):
    env.pull_venue(); env.add("f1", "overlay", "Reg Round.png", PNG)
    r = env.pull()
    assert r["state"] == "ok" and r["counts"]["added"] == 1
    loc = env.loc()
    rec = loc["overlay_images"][0]
    path = env.lr._overlays_dir(loc["slug"]) / f"{rec['id']}{rec['ext']}"
    assert path.read_bytes() == PNG and rec["id"] == env.cf.stable_id("f1") and rec["uploaded_by"] == "cloud-sync" and rec["mime"] == "image/png"


def test_a_picture_lands_as_branding_and_a_gif_overlay_is_kept(env):
    env.pull_venue(); env.add("f1", "image", "logo.png", PNG); env.add("f2", "overlay", "BIG.gif", GIF)
    env.pull()
    loc = env.loc()
    assert [r["filename"] for r in loc["branding_images"]] == ["logo.png"] and [r["filename"] for r in loc["overlay_images"]] == ["BIG.gif"]


def test_the_pull_survives_a_restart_the_app_rebuilds_from_disk(env):
    """Wipe the database copy of the location, then run the app's own startup rebuild (hydrate). The pictures must come back."""
    env.pull_venue(); env.add("f1", "overlay", "a.png", PNG); env.add("f2", "image", "logo.png", PNG + b"2")
    env.pull()
    loc = env.loc()
    before = (sorted(r["id"] for r in loc["overlay_images"]), sorted(r["id"] for r in loc["branding_images"]))
    names = {r["id"]: (r["filename"], r["uploaded_by"]) for r in loc["overlay_images"] + loc["branding_images"]}
    run(env.db.locations.delete_many({}))
    assert env.loc() is None
    env.lr.set_database(env.db)
    out = run(env.lr._hydrate_from_disk())
    again = run(env.db.locations.find_one({"slug": loc["slug"]}, {"_id": 0}))
    assert again and (sorted(r["id"] for r in again["overlay_images"]), sorted(r["id"] for r in again["branding_images"])) == before
    assert (env.lr._overlays_dir(loc["slug"]) / f"{env.cf.stable_id('f1')}.png").read_bytes() == PNG
    # the RECORDS come back as they were (the Cloud file name and who brought them), not as generic orphan files found in the folder
    assert {r["id"]: (r["filename"], r["uploaded_by"]) for r in again["overlay_images"] + again["branding_images"]} == names == {
        env.cf.stable_id("f1"): ("a.png", "cloud-sync"), env.cf.stable_id("f2"): ("logo.png", "cloud-sync")}


def test_a_second_pull_downloads_nothing_new(env):
    env.pull_venue(); env.add("f1", "overlay", "a.png", PNG)
    env.pull(); env.calls.clear()
    r = env.pull()
    assert env.calls == [] and r["counts"]["unchanged"] == 1 and r["counts"]["added"] == 0
    assert len(env.loc()["overlay_images"]) == 1


def test_a_changed_cloud_file_replaces_our_copy_and_never_duplicates(env):
    env.pull_venue(); env.add("f1", "overlay", "a.png", PNG)
    env.pull()
    env.files.clear(); env.add("f1", "overlay", "a.png", PNG + b"NEW")
    r = env.pull()
    loc = env.loc()
    assert r["counts"]["updated"] == 1 and len(loc["overlay_images"]) == 1
    assert (env.lr._overlays_dir(loc["slug"]) / f"{env.cf.stable_id('f1')}.png").read_bytes() == PNG + b"NEW"


def test_a_changed_file_type_replaces_the_old_extension(env):
    env.pull_venue(); env.add("f1", "overlay", "a.png", PNG)
    env.pull()
    env.files.clear(); env.add("f1", "overlay", "a.gif", GIF)
    env.pull()
    names = sorted(p.name for p in env.lr._overlays_dir(env.loc()["slug"]).iterdir() if p.is_file())
    assert names == [f"{env.cf.stable_id('f1')}.gif"]


def test_nothing_the_owner_put_there_is_ever_deleted_or_replaced(env):
    env.pull_venue()
    loc = env.loc()
    own = env.lr._overlays_dir(loc["slug"]) / "my-own-overlay.png"
    own.parent.mkdir(parents=True, exist_ok=True); own.write_bytes(b"MINE")
    env.add("f1", "overlay", "a.png", PNG)
    env.pull()
    env.files.clear()                                                   # the owner removes it in the Cloud
    r = env.pull()
    assert own.read_bytes() == b"MINE" and r["state"] == "ok"
    assert (env.lr._overlays_dir(loc["slug"]) / f"{env.cf.stable_id('f1')}.png").exists()    # removed in the Cloud: still here


def test_a_bad_download_is_thrown_away_and_retried_next_time(env):
    env.pull_venue(); env.add("f1", "overlay", "a.png", PNG, sha_override="0" * 64)
    r = env.pull()
    assert r["counts"]["failed"] == 1 and env.loc().get("overlay_images") in ([], None)
    env.files.clear(); env.add("f1", "overlay", "a.png", PNG)
    assert env.pull()["counts"]["added"] == 1


def test_the_real_download_checks_both_checksums(env, monkeypatch):
    import httpx
    class R:
        status_code = 200; content = PNG
        def __init__(s, h): s.headers = h
        def json(s): return {}
    import types
    async def fake_get(self, url, headers=None): return R({"x-content-sha256": sha(PNG)})
    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    importlib.reload(env.cf); monkeypatch.setattr(env.cf.cloud_link, "get_token", lambda: "tok")
    assert run(env.cf._download("f1", sha(PNG), 10**6)) == (PNG, "")
    assert run(env.cf._download("f1", "0" * 64, 10**6))[1] == "checksum_mismatch"
    async def liar(self, url, headers=None): return R({"x-content-sha256": "1" * 64})
    monkeypatch.setattr(httpx.AsyncClient, "get", liar)
    assert run(env.cf._download("f1", sha(PNG), 10**6))[1] == "checksum_mismatch"
    assert run(env.cf._download("f1", sha(PNG), 10))[1] == "too_large"


def test_a_venue_that_has_not_arrived_makes_its_files_wait(env):
    env.add("f1", "overlay", "a.png", PNG, venue_id="not-pulled-yet")
    r = env.pull()
    assert r["counts"]["waiting"] == 1 and env.calls == []
    env.pull_venue()                                                    # the venue arrives under another id: still waiting
    assert env.pull()["counts"]["waiting"] == 1
    env.files.clear(); env.add("f1", "overlay", "a.png", PNG, venue_id="v1")
    assert env.pull()["counts"]["added"] == 1


@pytest.mark.parametrize("name", ["evil.exe", "x.svg", "no-extension", "a.png.exe", "..\\..\\x.dll"])
def test_unsafe_picture_types_are_refused(env, name):
    env.pull_venue(); env.add("f1", "overlay", name, PNG)
    r = env.pull()
    assert r["counts"]["failed"] == 1
    assert not any(env.lr._overlays_dir(env.loc()["slug"]).glob("cf*"))


def test_a_video_is_ok_for_an_overlay_but_not_for_a_branding_picture(env):
    env.pull_venue(); env.add("f1", "overlay", "intro.mp4", b"\x00\x00\x00\x18ftypmp42" + b"z" * 100); env.add("f2", "image", "intro.mp4", b"\x00\x00\x00\x18ftypmp42" + b"z" * 100)
    r = env.pull()
    assert r["counts"]["added"] == 1 and r["counts"]["failed"] == 1


def test_the_folder_comes_from_our_slug_never_from_the_cloud(env):
    env.pull_venue("../../../Windows"); env.add("f1", "overlay", "a.png", PNG)
    env.pull()
    loc = env.loc()
    assert ".." not in loc["slug"] and env.home in env.lr._overlays_dir(loc["slug"]).resolve().parents or env.tmp in env.lr._overlays_dir(loc["slug"]).resolve().parents


def test_sponsor_fills_an_empty_slot_but_never_replaces_the_owners_own(env):
    env.pull_venue(); env.add("f1", "sponsor", "sponsor.png", PNG)
    env.pull()
    assert env.loc()["sponsor_image"]["uploaded_by"] == "cloud-sync"
    run(env.db.locations.update_one({"id": env.loc()["id"]}, {"$set": {"sponsor_image": {"id": "own1", "filename": "mine.png", "uploaded_by": "someone"}}}))
    env.files.clear(); env.add("f1", "sponsor", "sponsor.png", PNG + b"2")
    r = env.pull()
    assert env.loc()["sponsor_image"]["id"] == "own1" and r["counts"]["skipped"] == 1


def test_an_unknown_category_is_counted_not_pulled(env):
    env.pull_venue(); env.add("f1", "other", "notes.txt", b"hello")
    r = env.pull()
    assert r["counts"]["skipped"] == 1 and env.calls == []


def _round_bighat(name="Cloud Round", rtype="REG"):
    return json.dumps({"schema": "bighat-round/v1", "type": rtype, "name": name, "rounds": [{"type": rtype, "name": name, "questions": [{"n": i, "prompt": f"q{i}", "answer": f"a{i}"} for i in range(1, 11)]}]}).encode()


def test_a_bighat_goes_through_the_apps_own_importer_and_is_not_imported_twice(env, monkeypatch):
    from routes import bighat_files
    seen = []
    async def fake_import(payload):
        seen.append(payload)
        return type("Res", (), {"type": "round", "name": "Cloud Round"})()
    monkeypatch.setattr(bighat_files, "_import_zip_bytes", fake_import)
    env.add("b1", "bighat", "Cloud Round.bighat", _round_bighat(), venue_id=None)
    r1 = env.pull(); r2 = env.pull()
    assert len(seen) == 1 and r1["counts"]["added"] == 1 and r2["counts"]["unchanged"] == 1
    env.files.clear(); env.add("b1", "bighat", "Cloud Round.bighat", _round_bighat("Cloud Round v2"), venue_id=None)
    assert env.pull()["counts"]["updated"] == 1 and len(seen) == 2


def test_a_bighat_that_the_importer_rejects_is_reported_and_the_rest_continue(env, monkeypatch):
    from routes import bighat_files
    from fastapi import HTTPException
    async def fake_import(payload):
        if b"BAD" in payload:
            raise HTTPException(400, "Corrupted .bighat")
        return type("Res", (), {"type": "round", "name": "ok"})()
    monkeypatch.setattr(bighat_files, "_import_zip_bytes", fake_import)
    env.pull_venue()
    env.add("b1", "bighat", "bad.bighat", b"BAD" * 20, venue_id=None); env.add("b2", "bighat", "good.bighat", _round_bighat(), venue_id=None); env.add("f1", "overlay", "a.png", PNG)
    r = env.pull()
    assert r["counts"] == {"added": 2, "updated": 0, "unchanged": 0, "waiting": 0, "skipped": 0, "failed": 1} and r["failed"] == 1


@pytest.mark.parametrize("err", ["unreachable", "subscription_lapsed", "rate_limited", "unauthorized", "unlinked"])
def test_cloud_trouble_waits_quietly_and_keeps_what_is_here(env, monkeypatch, err):
    env.pull_venue(); env.add("f1", "overlay", "a.png", PNG)
    env.pull()
    async def down(): return {"ok": False, "error": err}
    monkeypatch.setattr(env.cf, "_fetch_manifest", down)
    r = env.pull()
    assert r["state"] == err and r["message"] and len(env.loc()["overlay_images"]) == 1


def test_a_cloud_that_stops_part_way_keeps_the_files_that_arrived(env, monkeypatch):
    env.pull_venue(); env.add("f1", "overlay", "a.png", PNG); env.add("f2", "overlay", "b.png", PNG + b"2")
    real = env.cf._download
    async def flaky(fid, s, m):
        return (None, "unreachable") if fid == "f2" else await real(fid, s, m)
    monkeypatch.setattr(env.cf, "_download", flaky)
    r = env.pull()
    assert r["state"] == "unreachable" and [x["filename"] for x in env.loc()["overlay_images"]] == ["a.png"]
    monkeypatch.setattr(env.cf, "_download", real)
    assert env.pull()["counts"]["added"] == 1 and len(env.loc()["overlay_images"]) == 2


def test_unlinked_pc_does_nothing(env, monkeypatch):
    monkeypatch.setattr(env.cf.cloud_link, "get_token", lambda: None)
    assert env.pull()["state"] == "not_linked" and env.calls == []


def test_a_damaged_state_file_is_kept_and_the_pull_starts_over(env):
    env.pull_venue(); env.add("f1", "overlay", "a.png", PNG)
    env.pull()
    env.cf._path().write_text("{ not json", encoding="utf-8")
    r = env.pull()
    assert r["state"] == "ok" and env.cf._path().with_suffix(".json.bad").exists() and len(env.loc()["overlay_images"]) == 1


def test_one_sync_at_a_time(env):
    env.pull_venue(); env.add("f1", "overlay", "a.png", PNG)
    async def both():
        return await asyncio.gather(env.cf.pull_once(env.db), env.cf.pull_once(env.db))
    a, b = asyncio.run(both())
    assert len(env.loc()["overlay_images"]) == 1


def test_the_routes_exist_and_sync_now_runs_files_after_the_data(env):
    from native import cloud_link_router
    src = Path(cloud_link_router.__file__).read_text(encoding="utf-8")
    assert "files-status" in src and "files-sync-now" in src and src.index("cloud_sync.pull_once(_db())") < src.index("cloud_files.pull_once(_db())")


def test_a_file_removed_in_the_cloud_stays_on_this_pc_and_in_the_record(env):
    env.pull_venue(); env.add("f1", "overlay", "a.png", PNG); env.add("f2", "image", "b.png", PNG + b"2"); env.add("f3", "sponsor", "s.png", PNG + b"3")
    env.pull()
    loc = env.loc()
    keep = sorted(p.name for d in (env.lr._overlays_dir(loc["slug"]), env.lr._branding_dir(loc["slug"]), env.lr._sponsor_dir(loc["slug"])) for p in d.iterdir() if p.is_file())
    env.files.clear()
    assert env.pull()["state"] == "ok"
    after = sorted(p.name for d in (env.lr._overlays_dir(loc["slug"]), env.lr._branding_dir(loc["slug"]), env.lr._sponsor_dir(loc["slug"])) for p in d.iterdir() if p.is_file())
    assert after == keep and len(keep) == 3 and len(env.loc()["overlay_images"]) == 1 and env.loc()["sponsor_image"]


def test_a_hard_crash_part_way_keeps_what_already_arrived_and_does_not_redownload_it(env, monkeypatch):
    """A power cut: the process dies at file 2 and NOTHING after that point can be written. Only the save made right after file 1 counts."""
    env.pull_venue(); env.add("f1", "overlay", "a.png", PNG); env.add("f2", "overlay", "b.png", PNG + b"2")
    real_put, real_write = env.cf._put_picture, env.cf._write
    state = {"dead": False}
    async def boom(db, loc, kind, f, data):
        if f["file_id"] == "f2":
            state["dead"] = True
            raise RuntimeError("power cut")
        return await real_put(db, loc, kind, f, data)
    def dead_write(st):
        if state["dead"]:
            raise OSError("the machine is off")
        return real_write(st)
    monkeypatch.setattr(env.cf, "_put_picture", boom); monkeypatch.setattr(env.cf, "_write", dead_write)
    env.pull()
    monkeypatch.setattr(env.cf, "_put_picture", real_put); monkeypatch.setattr(env.cf, "_write", real_write)
    assert env.cf._read()["files"].get("f1", {}).get("done") is True        # f1 was saved the moment it arrived
    env.calls.clear()
    assert env.pull()["counts"]["added"] == 1 and env.calls == ["f2"]        # only f2 is fetched on the next pull


def test_a_pull_error_is_reported_safely_and_nothing_is_lost(env, monkeypatch):
    env.pull_venue(); env.add("f1", "overlay", "a.png", PNG)
    async def boom(db, loc, kind, f, data): raise RuntimeError("disk full")
    monkeypatch.setattr(env.cf, "_put_picture", boom)
    r = env.pull()
    assert r["state"] == "error" and "Nothing was lost" in r["message"]
