"""alpha.85: desktop Setup Package - by-name/by-email mapping, no secrets, no master overwrite, safe re-runs."""
import importlib, io, json, sys, zipfile
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


class Coll:
    def __init__(self): self.rows = []
    def _m(self, r, q): return all(r.get(k) == v for k, v in q.items())
    async def insert_one(self, d): self.rows.append(dict(d))
    async def find_one(self, q, proj=None, *a, **k):
        for r in self.rows:
            if self._m(r, q): return dict(r)
    def find(self, q, proj=None):
        coll = self
        class C:
            def __init__(s): s.m = [dict(r) for r in coll.rows if coll._m(r, q)]
            async def to_list(s, n): return s.m[:n]
        return C()
    async def update_one(self, q, u):
        for r in self.rows:
            if self._m(r, q): r.update(u.get("$set", {})); return


class DB:
    def __init__(self): self.venues, self.employees, self.venue_pricing, self.venue_roles, self.locations = Coll(), Coll(), Coll(), Coll(), Coll()


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("BIGHAT_CONFIG_PATH", str(tmp_path / "system_config.json"))
    monkeypatch.setenv("BIGHAT_NATIVE_MODE", "1"); monkeypatch.setenv("BIGHAT_DB_DIR", str(tmp_path / "db")); (tmp_path / "db").mkdir()
    monkeypatch.setenv("HOME", str(tmp_path / "home")); monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))
    from native import db_factory; importlib.reload(db_factory)
    import native.config as cfg; importlib.reload(cfg)
    import native; native.config_manager = cfg.config_manager
    from native import admin_router, employee_sync, venue_sync, locations_router, setup_package
    for m in (admin_router, employee_sync, venue_sync, locations_router, setup_package): importlib.reload(m)
    root = tmp_path / "locroot"; root.mkdir()
    monkeypatch.setattr(locations_router, "_files_locations_root", lambda: root)
    async def no_hydrate(): return {}
    monkeypatch.setattr(locations_router, "_hydrate_from_disk", no_hydrate)
    cfg.config_manager.config["users"] = [{"id": "m1", "email": "owner@x.com", "role": "master_admin", "is_master": True, "password_hash": "MASTER-OWN-HASH", "first_name": "Owen"}]
    yield setup_package, cfg.config_manager, root, DB(), employee_sync
    db_factory.close_all()


def make_pkg(doc, images=None):
    d = {"format": "bighat-setup-package", "format_version": 1, "venues": [], "venue_pricing": [], "people": [], "venue_roles": [], "locations": []}
    d.update(doc)
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("package.json", json.dumps(d))
        for n, data in (images or {}).items(): z.writestr(n, data)
    return b.getvalue()


@pytest.mark.asyncio
async def test_package_never_contains_passwords_or_hashes(env):
    sp, cm, root, db, es = env
    cm.config["users"].append({"id": "u2", "email": "sam@x.com", "role": "host", "password_hash": "SAM-SECRET-HASH", "display_name": "Sam"})
    await db.employees.insert_one({"id": "e1", "name": "Sam", "email": "sam@x.com", "is_admin": False, "password": "PLAIN-LEFTOVER"})
    raw = await sp.build_package(db)
    text = b"".join(zipfile.ZipFile(io.BytesIO(raw)).read(n) for n in zipfile.ZipFile(io.BytesIO(raw)).namelist()).decode("latin1")
    for bad in ("SAM-SECRET-HASH", "MASTER-OWN-HASH", "PLAIN-LEFTOVER", "password", "hash"):
        assert bad not in text, bad


@pytest.mark.asyncio
async def test_roles_and_pricing_travel_by_name_and_email_not_by_local_id(env):
    sp, cm, root, db, es = env
    raw = make_pkg({"venues": [{"name": "Monkey Pants", "city": "Phoenix"}], "venue_pricing": [{"venue": "monkey pants", "trivia_price": 125.5, "music_bingo_price": 90, "karaoke_price": 75}],
                    "people": [{"email": "SAM@x.com ", "name": "Sam", "role": "host"}],
                    "venue_roles": [{"venue": "Monkey Pants", "email": "sam@x.com", "role_category": "trivia", "role_type": "primary"}]})
    out = await sp.apply_package(db, raw)
    v, e = db.venues.rows[0], db.employees.rows[0]
    assert out["venues_added"] == 1 and out["pricing_set"] == 1 and out["roles_added"] == 1 and e["email"] == "sam@x.com"
    assert db.venue_pricing.rows[0]["venue_id"] == v["id"] and db.venue_pricing.rows[0]["trivia_price"] == 125.5
    assert (db.venue_roles.rows[0]["venue_id"], db.venue_roles.rows[0]["employee_id"]) == (v["id"], e["id"])      # THIS computer's ids


@pytest.mark.asyncio
async def test_the_master_admin_is_never_created_or_changed_by_a_pull(env):
    sp, cm, root, db, es = env
    raw = make_pkg({"people": [{"email": "owner@x.com", "name": "Hacker", "role": "master_admin"}, {"email": "other-master@x.com", "name": "Evil", "role": "master_admin"},
                               {"email": "alex@x.com", "name": "Alex", "role": "admin", "is_admin": True}]})
    out = await sp.apply_package(db, raw, overwrite_changed=True)
    users = {u["email"]: u for u in cm.config["users"]}
    assert users["owner@x.com"]["password_hash"] == "MASTER-OWN-HASH" and users["owner@x.com"]["role"] == "master_admin"
    assert "other-master@x.com" not in users                                    # a second master can never be created by a package
    assert [p["email"] for p in out["people_added"]] == ["alex@x.com"]
    assert users["alex@x.com"]["role"] != "master_admin" and users["alex@x.com"]["password_hash"] != "MASTER-OWN-HASH"


@pytest.mark.asyncio
async def test_existing_people_keep_their_passwords_and_nothing_duplicates_on_rerun(env):
    sp, cm, root, db, es = env
    await db.employees.insert_one({"id": "e9", "name": "Sam", "email": "sam@x.com", "is_admin": False})
    cm.config["users"].append({"id": "u9", "email": "sam@x.com", "role": "host", "password_hash": "SAMS-OWN-NEW-HASH"})
    raw = make_pkg({"people": [{"email": "sam@x.com", "name": "Samuel", "role": "host"}], "venues": [{"name": "A Bar"}]})
    await sp.apply_package(db, raw, overwrite_changed=True)
    assert [u["password_hash"] for u in cm.config["users"] if u["email"] == "sam@x.com"] == ["SAMS-OWN-NEW-HASH"]
    out2 = await sp.apply_package(db, raw)
    assert out2["venues_added"] == 0 and out2["people_added"] == [] and len(db.venues.rows) == 1 and len(db.employees.rows) == 1


@pytest.mark.asyncio
async def test_existing_values_are_only_replaced_when_the_master_says_so(env):
    sp, cm, root, db, es = env
    await db.venues.insert_one({"id": "v1", "name": "Monkey Pants", "address": "OLD"})
    raw = make_pkg({"venues": [{"name": "Monkey Pants", "address": "NEW"}]})
    plan = await sp.plan_apply(db, raw); assert plan["venues_changed"] == ["Monkey Pants"] and plan["differs"] is True
    await sp.apply_package(db, raw); assert db.venues.rows[0]["address"] == "OLD"
    await sp.apply_package(db, raw, overwrite_changed=True); assert db.venues.rows[0]["address"] == "NEW"


@pytest.mark.asyncio
async def test_images_go_to_THIS_computers_folder_for_the_same_place_even_when_names_differ(env):
    sp, cm, root, db, es = env
    # this computer's "Monkey Pants" lives in a differently named folder than the sender's
    await db.venues.insert_one({"id": "v1", "name": "Monkey Pants"})
    await db.locations.insert_one({"id": "l1", "name": "Monkey Pants", "slug": "monkey-pants-2"})
    raw = make_pkg({"locations": [{"slug": "monkey-pants", "name": "Monkey Pants", "branding": ["logo.png"]}, {"slug": "ghost", "name": "Ghost Bar", "branding": ["x.png"]}]},
                   {"images/monkey-pants/branding/logo.png": b"PNG", "images/ghost/branding/x.png": b"PNG"})
    plan = await sp.plan_apply(db, raw); assert plan["images_new"] == 1                    # the ghost place is not counted: it does not exist here
    out = await sp.apply_package(db, raw)
    assert (root / "monkey-pants-2" / "branding" / "logo.png").read_bytes() == b"PNG"
    assert not (root / "monkey-pants").exists() and not (root / "ghost").exists()           # no stray folders
    assert out["images_added"] == 1 and any("Ghost Bar" in s for s in out["skipped"])
    assert (await sp.apply_package(db, raw))["images_added"] == 0                          # never overwritten, never duplicated


@pytest.mark.asyncio
async def test_hostile_zip_members_are_ignored(env):
    sp, cm, root, db, es = env
    await db.locations.insert_one({"id": "l1", "name": "Bar", "slug": "bar"})
    raw = make_pkg({"locations": [{"slug": "bar", "name": "Bar"}]},
                   {"images/bar/branding/../../../evil.png": b"x", "images/bar/branding/run.exe": b"x", "../escape.png": b"x", "images/.hidden/branding/a.png": b"x", "images/bar/other/a.png": b"x"})
    out = await sp.apply_package(db, raw)
    assert out["images_added"] == 0
    assert [p for p in root.rglob("*") if p.is_file()] == []                          # not one file was written anywhere
    assert not (root.parent / "evil.png").exists() and not (root.parent / "escape.png").exists()


@pytest.mark.asyncio
async def test_roles_respect_the_one_primary_rule_and_bad_types(env):
    sp, cm, root, db, es = env
    raw = make_pkg({"venues": [{"name": "Bar"}], "people": [{"email": "a@x.com", "name": "A"}, {"email": "b@x.com", "name": "B"}],
                    "venue_roles": [{"venue": "Bar", "email": "a@x.com", "role_category": "trivia", "role_type": "primary"},
                                    {"venue": "Bar", "email": "b@x.com", "role_category": "trivia", "role_type": "primary"},
                                    {"venue": "Bar", "email": "b@x.com", "role_category": "dancing", "role_type": "primary"},
                                    {"venue": "Nowhere", "email": "b@x.com", "role_category": "trivia", "role_type": "secondary"}]})
    out = await sp.apply_package(db, raw)
    assert out["roles_added"] == 1 and len(out["skipped"]) == 3


@pytest.mark.asyncio
async def test_not_a_package_is_refused_cleanly(env):
    sp, cm, root, db, es = env
    with pytest.raises(Exception): await sp.plan_apply(db, b"hello")
    with pytest.raises(ValueError): sp.read_package(make_pkg({"format": "other"}).replace(b"bighat-setup-package", b"something-else-here-x"))
