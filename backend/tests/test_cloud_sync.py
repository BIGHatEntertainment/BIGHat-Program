"""Phase 3: the Program pulls venues/people/schedule from the Cloud. Real MontyDB, real files; only the HTTP feed is faked."""
import asyncio, importlib, json, os, sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("BIGHAT_CONFIG_PATH", str(tmp_path / "system_config.json"))
    monkeypatch.setenv("BIGHAT_NATIVE_MODE", "1")
    monkeypatch.setenv("BIGHAT_DATA_ROOT", str(tmp_path / "app"))
    (tmp_path / "db").mkdir()
    monkeypatch.setenv("BIGHAT_DB_DIR", str(tmp_path / "db"))
    monkeypatch.setenv("BIGHAT_CLOUD_BASE_URL", "https://cloud.test")
    from native import db_factory
    importlib.reload(db_factory)
    import native.config as cfg
    importlib.reload(cfg)
    import native
    native.config_manager = cfg.config_manager
    from native import admin_router, employee_sync, cloud_link, cloud_sync, schedule_safety
    for m in (admin_router, employee_sync, cloud_link, cloud_sync):
        importlib.reload(m)
    cfg.config_manager.config["users"] = [{"id": "m1", "email": "owner@x.com", "role": "master_admin", "is_master": True,
                                            "password_hash": "x", "first_name": "Owner"}]
    monkeypatch.setattr(cloud_link, "get_token", lambda: "tok")
    monkeypatch.setattr(schedule_safety, "folder", lambda: (tmp_path / "sched").mkdir(exist_ok=True) or tmp_path / "sched")
    db = db_factory.get_db()
    yield db, cloud_sync, employee_sync
    db_factory.close_all()


def feed(cs, monkeypatch, pages):
    """pages: list of dicts returned in order by the fake Cloud."""
    calls = []
    async def fake(since):
        calls.append(since)
        p = pages.pop(0) if pages else {"seq": since, "has_more": False, "items": []}
        return {"ok": True, "data": p} if not isinstance(p, dict) or "ok" not in p else p
    monkeypatch.setattr(cs, "_fetch", fake)
    return calls


def V(i, name, seq=1): return {"item_id": i, "kind": "venue", "revision": seq, "deleted": False, "data": {"id": i, "name": name, "address": "1 Main", "city": "Mesa", "state": "AZ", "notes": None, "venue_pays_host_directly": False}}
def P(i, name, email, admin=False): return {"item_id": i, "kind": "person", "revision": 1, "deleted": False, "data": {"name": name, "email": email, "phone": "5", "role": "host", "is_admin": admin}}
def PR(vid): return {"item_id": vid, "kind": "venue_pricing", "revision": 1, "deleted": False, "data": {"venue_id": vid, "trivia_price": 100, "music_bingo_price": 90, "karaoke_price": 80}}
def R(i, vid, eid): return {"item_id": i, "kind": "venue_role", "revision": 1, "deleted": False, "data": {"id": i, "venue_id": vid, "employee_id": eid, "role_category": "primary", "role_type": "trivia"}}
def E(i, vid, title="Trivia Night", claimed=None, date="2026-11-02T19:00:00+00:00"):
    return {"item_id": i, "kind": "event", "revision": 1, "deleted": False, "data": {"id": i, "title": title, "event_type": "trivia", "venue_id": vid, "date": date, "duration_hours": 2, "pay_rate": None, "notes": None, "is_special_event": False, "status": "claimed" if claimed else "available", "claimed_by": claimed[0] if claimed else None, "claimed_at": None, "wore_big_hat": False, "social_media_posts": False, "winners_post": False, "claimed_by_name": None, "claimed_by_email": claimed[1] if claimed else None}}


def run(c): return asyncio.run(c)


def test_fresh_pc_pulls_everything_and_creates_logins(env, monkeypatch):
    db, cs, es = env
    feed(cs, monkeypatch, [{"seq": 6, "has_more": False, "items": [E("e1", "v1", claimed=("p1", "sam@x.com")), R("r1", "v1", "p1"), PR("v1"), P("p1", "Sam Host", "Sam@X.com"), V("v1", "The Pub")]}])
    st = run(cs.pull_once(db))
    assert st["state"] == "ok" and st["last_seq"] == 6
    assert run(db.venues.count_documents({})) == 1 and run(db.employees.count_documents({})) == 1
    assert run(db.venue_pricing.count_documents({})) == 1 and run(db.venue_roles.count_documents({})) == 1
    ev = run(db.events.find_one({}, {"_id": 0}))
    emp = run(db.employees.find_one({"email": "sam@x.com"}, {"_id": 0}))
    assert ev["claimed_by"] == emp["id"] and ev["venue_id"] == run(db.venues.find_one({}, {"_id": 0}))["id"]
    u = es.find_user("sam@x.com")
    assert u and u["password_hash"].startswith("$2") and u["role"] == "host"
    logins = cs.take_new_logins()
    assert len(logins) == 1 and logins[0]["email"] == "sam@x.com" and logins[0]["temp_password"]
    assert cs.take_new_logins() == []                                  # shown once
    assert logins[0]["temp_password"] not in cs._path().read_text()    # never written to disk


def test_second_pull_asks_only_for_changes_and_applies_updates(env, monkeypatch):
    db, cs, _ = env
    calls = feed(cs, monkeypatch, [{"seq": 1, "has_more": False, "items": [V("v1", "The Pub")]},
                                   {"seq": 2, "has_more": False, "items": [V("v1", "The Pub")]}])
    run(cs.pull_once(db))
    it = V("v1", "The Pub"); it["data"]["address"] = "9 New St"
    cs_pages = [{"seq": 2, "has_more": False, "items": [it]}]
    feed(cs, monkeypatch, cs_pages)
    run(cs.pull_once(db))
    assert run(db.venues.find_one({}, {"_id": 0}))["address"] == "9 New St"
    assert run(db.venues.count_documents({})) == 1                     # updated, not duplicated


def test_first_pull_on_a_pc_with_its_own_data_waits_for_approval_and_changes_nothing(env, monkeypatch):
    db, cs, _ = env
    run(db.venues.insert_one({"id": "L1", "name": "Local Bar", "address": "x", "city": "c", "state": "s"}))
    feed(cs, monkeypatch, [{"seq": 3, "has_more": False, "items": [V("v1", "The Pub")]}])
    st = run(cs.pull_once(db))
    assert st["state"] == "needs_approval" and st["counts"]["preview"] == {"venue": 1}
    assert run(db.venues.count_documents({})) == 1 and st["last_seq"] == 0
    feed(cs, monkeypatch, [{"seq": 3, "has_more": False, "items": [V("v1", "The Pub")]}])
    st = run(cs.pull_once(db, approve_first_link=True))
    assert st["state"] == "ok" and run(db.venues.count_documents({})) == 2
    assert run(db.venues.find_one({"id": "L1"})) is not None           # the local venue was never touched


def test_same_name_venue_is_adopted_not_duplicated(env, monkeypatch):
    db, cs, _ = env
    run(db.venues.insert_one({"id": "L1", "name": "The  Pub!", "address": "old", "city": "c", "state": "s"}))
    feed(cs, monkeypatch, [{"seq": 1, "has_more": False, "items": [V("v1", "the pub")]}])
    st = run(cs.pull_once(db, approve_first_link=True))
    assert run(db.venues.count_documents({})) == 1 and st["counts"]["adopted"] == 1
    assert run(db.venues.find_one({"id": "L1"}))["address"] == "1 Main"


def test_a_backup_is_written_before_applying(env, monkeypatch, tmp_path):
    db, cs, _ = env
    run(db.venues.insert_one({"id": "L1", "name": "Local Bar", "address": "x", "city": "c", "state": "s"}))
    feed(cs, monkeypatch, [{"seq": 1, "has_more": False, "items": [V("v1", "Other")]}])
    run(cs.pull_once(db, approve_first_link=True))
    saved = list((tmp_path / "sched" / "before-cloud-sync").rglob("venues.json"))
    assert saved and any("Local Bar" in f.read_text() for f in saved)


def test_local_change_since_last_pull_is_kept_and_reported(env, monkeypatch):
    db, cs, _ = env
    feed(cs, monkeypatch, [{"seq": 1, "has_more": False, "items": [V("v1", "The Pub")]}])
    run(cs.pull_once(db))
    run(db.venues.update_one({"name": "The Pub"}, {"$set": {"address": "HOST EDIT"}}))
    it = V("v1", "The Pub"); it["data"]["address"] = "cloud edit"
    feed(cs, monkeypatch, [{"seq": 2, "has_more": False, "items": [it]}])
    st = run(cs.pull_once(db))
    assert run(db.venues.find_one({}, {"_id": 0}))["address"] == "HOST EDIT"
    assert st["conflict_count"] == 1


def test_cloud_removal_deletes_only_what_the_sync_created(env, monkeypatch):
    db, cs, _ = env
    run(db.venues.insert_one({"id": "L1", "name": "Mine", "address": "x", "city": "c", "state": "s"}))
    feed(cs, monkeypatch, [{"seq": 2, "has_more": False, "items": [V("v1", "Mine"), V("v2", "Theirs")]}])
    run(cs.pull_once(db, approve_first_link=True))
    gone = lambda i: {"item_id": i, "kind": "venue", "revision": 2, "deleted": True, "data": None}
    feed(cs, monkeypatch, [{"seq": 4, "has_more": False, "items": [gone("v1"), gone("v2")]}])
    run(cs.pull_once(db))
    names = [v["name"] for v in run(db.venues.find({}, {"_id": 0}).to_list(10))]
    assert names == ["Mine"]                                           # adopted one stays, created one goes


def test_a_pull_never_deletes_a_person_or_their_login(env, monkeypatch):
    db, cs, es = env
    feed(cs, monkeypatch, [{"seq": 1, "has_more": False, "items": [P("p1", "Sam", "sam@x.com")]}])
    run(cs.pull_once(db))
    gone = {"item_id": "p1", "kind": "person", "revision": 2, "deleted": True, "data": None}
    feed(cs, monkeypatch, [{"seq": 2, "has_more": False, "items": [gone]}])
    st = run(cs.pull_once(db))
    assert run(db.employees.count_documents({"email": "sam@x.com"})) == 1 and es.find_user("sam@x.com") and st["held_back"] == 1


def test_master_admin_is_never_changed_and_no_second_login_made(env, monkeypatch):
    db, cs, es = env
    before = dict(es.find_user("owner@x.com"))
    feed(cs, monkeypatch, [{"seq": 1, "has_more": False, "items": [P("p9", "Totally Else", "OWNER@x.com", admin=False)]}])
    run(cs.pull_once(db))
    assert es.find_user("owner@x.com") == before and cs.take_new_logins() == []


def test_event_waits_for_its_venue_and_person_then_lands_on_a_later_pull(env, monkeypatch):
    db, cs, _ = env
    feed(cs, monkeypatch, [{"seq": 1, "has_more": False, "items": [E("e1", "v1")]}])
    st = run(cs.pull_once(db))
    assert run(db.events.count_documents({})) == 0 and st["pending"] == 1
    feed(cs, monkeypatch, [{"seq": 2, "has_more": False, "items": [V("v1", "The Pub")]}])
    run(cs.pull_once(db))
    assert run(db.events.count_documents({})) == 1


def test_offline_lapsed_and_unlinked_change_nothing_and_say_why(env, monkeypatch):
    db, cs, _ = env
    run(db.venues.insert_one({"id": "L1", "name": "Mine", "address": "x", "city": "c", "state": "s"}))
    for err, state in (("unreachable", "unreachable"), ("subscription_lapsed", "subscription_lapsed"), ("unlinked", "unlinked")):
        async def bad(since, e=err): return {"ok": False, "error": e}
        monkeypatch.setattr(cs, "_fetch", bad)
        st = run(cs.pull_once(db))
        assert st["state"] == state and st["message"] and run(db.venues.count_documents({})) == 1


def test_not_linked_pc_does_nothing(env, monkeypatch):
    db, cs, _ = env
    from native import cloud_link
    monkeypatch.setattr(cloud_link, "get_token", lambda: None)
    assert run(cs.pull_once(db))["state"] == "not_linked"


def test_damaged_state_file_is_kept_aside_not_replaced_by_empty(env, monkeypatch):
    db, cs, _ = env
    cs._path().write_text("{ not json", encoding="utf-8")
    feed(cs, monkeypatch, [{"seq": 1, "has_more": False, "items": []}])
    run(cs.pull_once(db))
    assert cs._path().with_suffix(".json.bad").read_text() == "{ not json"


def test_if_the_backup_fails_nothing_is_applied(env, monkeypatch):
    db, cs, _ = env
    async def boom(db): raise OSError("disk full")
    monkeypatch.setattr(cs, "_backup_schedule", boom)
    feed(cs, monkeypatch, [{"seq": 1, "has_more": False, "items": [V("v1", "The Pub")]}])
    st = run(cs.pull_once(db))
    assert st["state"] == "error" and run(db.venues.count_documents({})) == 0 and st["last_seq"] == 0


def test_resync_signal_restarts_from_zero(env, monkeypatch):
    db, cs, _ = env
    feed(cs, monkeypatch, [{"seq": 5, "has_more": False, "items": [V("v1", "The Pub")]}])
    run(cs.pull_once(db))
    seen = []
    async def fake(since):
        seen.append(since)
        if len(seen) == 1:
            return {"ok": True, "data": {"seq": 9, "has_more": False, "items": [], "resync_required": True}}
        return {"ok": True, "data": {"seq": 9, "has_more": False, "items": [V("v1", "The Pub"), V("v2", "Second")]}}
    monkeypatch.setattr(cs, "_fetch", fake)
    run(cs.pull_once(db))
    assert seen == [5, 0] and run(db.venues.count_documents({})) == 2


def test_the_pull_never_replaces_a_program_accounts_password(env, monkeypatch):
    """v32.4.0 (found while building the org login): a person the Cloud has that ALREADY has a hand-made login on this PC used to get a new
    temporary password from the pull, which silently replaced their program password. Now they keep it; only a person with no login gets one."""
    db, cs, es = env
    import bcrypt
    run(es.upsert_user_for_employee("Sam Host", "sam@x.com", False, None, "MyProgramPw1", ""))
    before = es.find_user("sam@x.com")["password_hash"]
    feed(cs, monkeypatch, [{"seq": 2, "has_more": False, "items": [P("p1", "Sam Host", "Sam@X.com"), P("p2", "New Person", "new@x.com")]}])
    st = run(cs.pull_once(db, approve_first_link=True))
    assert st["state"] == "ok"
    u = es.find_user("sam@x.com")
    assert u["password_hash"] == before and bcrypt.checkpw(b"MyProgramPw1", u["password_hash"].encode())
    logins = {l["email"] for l in cs.take_new_logins()}
    assert logins == {"new@x.com"}                                         # only the person with NO login here got a temporary password
    ids = cs._read()["ids"]["person"]
    assert ids["p1"]["created"] is False and ids["p2"]["created"] is True
