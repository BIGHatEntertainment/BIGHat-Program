"""v32.2.13: a HOST (the login the schedule sync creates) gets the Karaoke venue list, limited to the venues they work at.
Real MontyDB, real Cloud-sync pull, the real locations router. Admins and master admins behave as before; every admin-only door stays shut to a host."""
import sys
sys.path.insert(0, "tests")
from test_cloud_sync import env, feed, V, P, PR, R, run  # noqa: F401
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient


def client(db, uid, role, email):
    from native import locations_router as lr
    async def resolver(request: Request):
        return {"_id": uid, "id": uid, "role": role, "email": email, "name": "X"}
    lr.set_database(db); lr.set_current_user_resolver(resolver)
    app = FastAPI(); app.include_router(lr.router, prefix="/api")
    return TestClient(app)


def pull(env, monkeypatch, items):
    db, cs, es = env
    feed(cs, monkeypatch, [{"seq": 20, "has_more": False, "items": items}])
    run(cs.pull_once(db))
    return db, es


def names(r):
    return sorted(x["name"] for x in r.json())


def test_a_host_sees_the_venue_they_work_at_for_karaoke(env, monkeypatch):
    db, es = pull(env, monkeypatch, [V("v1", "Monkey Pants"), PR("v1"), P("p1", "Sam Host", "sam@x.com"), R("r1", "v1", "p1")])
    c = client(db, es.find_user("sam@x.com")["id"], "host", "sam@x.com")
    r = c.get("/api/native/locations", params={"game": "karaoke"})
    assert r.status_code == 200 and names(r) == ["Monkey Pants"]


def test_a_host_sees_only_their_own_venues_not_every_venue(env, monkeypatch):
    db, es = pull(env, monkeypatch, [V("v1", "Monkey Pants"), V("v2", "Copper Blues"), V("v3", "Rusty Nail"), PR("v1"), PR("v2"), PR("v3"),
                                     P("p1", "Sam Host", "sam@x.com"), P("p2", "Other Host", "other@x.com"),
                                     R("r1", "v1", "p1"), R("r2", "v3", "p1"), R("r3", "v2", "p2")])
    sam = client(db, es.find_user("sam@x.com")["id"], "host", "sam@x.com")
    assert names(sam.get("/api/native/locations", params={"game": "karaoke"})) == ["Monkey Pants", "Rusty Nail"]
    other = client(db, es.find_user("other@x.com")["id"], "host", "other@x.com")
    assert names(other.get("/api/native/locations", params={"game": "karaoke"})) == ["Copper Blues"]


def test_the_email_match_ignores_capital_letters(env, monkeypatch):
    db, es = pull(env, monkeypatch, [V("v1", "Monkey Pants"), PR("v1"), P("p1", "Sam Host", "Sam@X.com"), R("r1", "v1", "p1")])
    c = client(db, es.find_user("sam@x.com")["id"], "host", "SAM@x.COM")
    assert names(c.get("/api/native/locations", params={"game": "karaoke"})) == ["Monkey Pants"]


def test_a_host_with_no_venue_role_gets_an_empty_list_not_everything(env, monkeypatch):
    db, es = pull(env, monkeypatch, [V("v1", "Monkey Pants"), PR("v1"), P("p1", "Sam Host", "sam@x.com")])
    c = client(db, es.find_user("sam@x.com")["id"], "host", "sam@x.com")
    r = c.get("/api/native/locations", params={"game": "karaoke"})
    assert r.status_code == 200 and r.json() == []


def test_a_host_login_with_no_schedule_employee_gets_an_empty_list(env, monkeypatch):
    db, es = pull(env, monkeypatch, [V("v1", "Monkey Pants"), PR("v1")])
    r = client(db, "ghost", "host", "nobody@x.com").get("/api/native/locations", params={"game": "karaoke"})
    assert r.status_code == 200 and r.json() == []


def test_the_games_price_rule_still_applies_to_a_host(env, monkeypatch):
    """A venue whose karaoke price is $0 is OFF for karaoke, for hosts exactly as for admins."""
    db, es = pull(env, monkeypatch, [V("v1", "Monkey Pants"), P("p1", "Sam Host", "sam@x.com"), R("r1", "v1", "p1")])
    run(db.venue_pricing.delete_many({}))
    vid = run(db.venues.find_one({}, {"_id": 0}))["id"]
    run(db.venue_pricing.insert_one({"venue_id": vid, "trivia_price": 100, "music_bingo_price": 90, "karaoke_price": 0}))
    c = client(db, es.find_user("sam@x.com")["id"], "host", "sam@x.com")
    assert c.get("/api/native/locations", params={"game": "karaoke"}).json() == []
    assert names(c.get("/api/native/locations", params={"game": "trivia"})) == ["Monkey Pants"]


def test_a_host_still_cannot_list_every_location_without_asking_for_a_game(env, monkeypatch):
    db, es = pull(env, monkeypatch, [V("v1", "Monkey Pants"), PR("v1"), P("p1", "Sam Host", "sam@x.com"), R("r1", "v1", "p1")])
    c = client(db, es.find_user("sam@x.com")["id"], "host", "sam@x.com")
    r = c.get("/api/native/locations")
    assert r.status_code == 403 and r.json()["detail"] == "admin_or_master_required"


def test_every_admin_only_door_is_still_shut_to_a_host(env, monkeypatch):
    db, es = pull(env, monkeypatch, [V("v1", "Monkey Pants"), PR("v1"), P("p1", "Sam Host", "sam@x.com"), R("r1", "v1", "p1")])
    c = client(db, es.find_user("sam@x.com")["id"], "host", "sam@x.com")
    loc = run(db.locations.find_one({}, {"_id": 0}))["id"]
    shut = [c.post("/api/native/locations", json={"name": "New"}), c.get(f"/api/native/locations/{loc}"),
            c.delete(f"/api/native/locations/{loc}"), c.patch(f"/api/native/locations/{loc}/admins", json={"assigned_user_ids": ["x"]}),
            c.post(f"/api/native/locations/{loc}/images", files={"file": ("a.png", b"x", "image/png")}),
            c.delete(f"/api/native/locations/{loc}/images/nope")]
    assert [r.status_code for r in shut] == [403] * len(shut)


def test_a_host_cannot_fake_their_way_in_with_another_role_name(env, monkeypatch):
    db, es = pull(env, monkeypatch, [V("v1", "Monkey Pants"), PR("v1")])
    for role in ("", "viewer", "HOST", None):
        r = client(db, "u", role, "sam@x.com").get("/api/native/locations", params={"game": "karaoke"})
        assert r.status_code == 403, role


def test_master_admin_and_admin_behave_exactly_as_before(env, monkeypatch):
    """The master sees every location (the Program also seeds default ones) and an admin only the ones they are assigned to. Compared with
    what the ORIGINAL code returned for the same data (captured below from the database, not typed in)."""
    db, es = pull(env, monkeypatch, [V("v1", "Monkey Pants"), V("v2", "Copper Blues"), PR("v1"), PR("v2")])
    master = client(db, "m1", "master_admin", "owner@x.com")
    master.get("/api/native/locations")                      # the list reconciles the disk and the Schedule first (it creates the default places)
    everything = sorted(x["name"] for x in run(db.locations.find({"retired": {"$ne": True}}, {"_id": 0, "name": 1}).to_list(500)))
    assert names(master.get("/api/native/locations")) == everything
    assert "Monkey Pants" in names(master.get("/api/native/locations", params={"game": "karaoke"}))
    loc = run(db.locations.find_one({"name": "Monkey Pants"}, {"_id": 0}))
    run(db.locations.update_one({"id": loc["id"]}, {"$set": {"assigned_user_ids": ["adm1"]}}))
    adm = client(db, "adm1", "admin", "adm@x.com")
    assert names(adm.get("/api/native/locations", params={"game": "karaoke"})) == ["Monkey Pants"]      # only the one they are assigned to
    assert names(adm.get("/api/native/locations")) == ["Monkey Pants"]
