"""v32.2.11: "Update schedule from the Cloud". Real MontyDB + real files; only the Cloud's HTTP feed is faked.
Rules under test: the check changes NOTHING; apply does exactly what the check showed; never a duplicate; never an unnecessary delete."""
import asyncio, sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_cloud_sync import env, feed, V, P, E, run  # noqa: F401,E402


@pytest.fixture
def rec(env, monkeypatch):
    db, cs, es = env
    from native import schedule_reconcile as sr
    import importlib; importlib.reload(sr)
    return db, cs, sr


def synced(rec, monkeypatch, items):
    """A PC that already pulled `items` once (so it tracks them)."""
    db, cs, sr = rec
    feed(cs, monkeypatch, [{"seq": 5, "has_more": False, "items": items}])
    run(cs.pull_once(db))


def cloud_now(rec, monkeypatch, items):
    """What the Cloud's full feed (read from sequence 0) holds right now."""
    db, cs, sr = rec
    feed(cs, monkeypatch, [{"seq": 9, "has_more": False, "items": items}])


async def count(db): return await db.events.count_documents({})


def titles(db): return sorted(e["title"] for e in run(db.events.find({}, {"_id": 0}).to_list(1000)))


def base(): return [V("v1", "The Pub"), P("p1", "Sam Host", "sam@x.com"), E("e1", "v1", "Monday Trivia", date="2026-11-02T19:00:00+00:00"),
                    E("e2", "v1", "Friday Trivia", date="2026-11-06T19:00:00+00:00")]


def test_check_changes_nothing_at_all(rec, monkeypatch):
    db, cs, sr = rec
    synced(rec, monkeypatch, base())
    before = (titles(db), cs._read()["ids"])
    cloud_now(rec, monkeypatch, base() + [E("e3", "v1", "New Wednesday", date="2026-11-04T19:00:00+00:00")])
    out = run(sr.check(db))
    assert out["ok"] and out["summary"]["add"] == 1 and out["can_apply"] is True
    assert (titles(db), cs._read()["ids"]) == before                          # nothing written, no tracking changed
    assert not (Path(__file__).parent / "x").exists()


def test_a_pc_that_already_matches_says_so_and_offers_nothing(rec, monkeypatch):
    db, cs, sr = rec
    synced(rec, monkeypatch, base()); cloud_now(rec, monkeypatch, base())
    out = run(sr.check(db))
    assert out["ok"] and out["can_apply"] is False and out["summary"]["add"] == 0 and out["summary"]["remove"] == 0 and "already matches" in out["message"]


def test_a_missing_event_is_added_once_even_if_you_press_apply_twice(rec, monkeypatch):
    db, cs, sr = rec
    synced(rec, monkeypatch, base())
    new = base() + [E("e3", "v1", "New Wednesday", date="2026-11-04T19:00:00+00:00")]
    cloud_now(rec, monkeypatch, new); tok = run(sr.check(db))["token"]
    cloud_now(rec, monkeypatch, new); r1 = run(sr.apply(db, tok))
    assert r1["ok"] and r1["applied"]["added"] == 1 and run(count(db)) == 3
    cloud_now(rec, monkeypatch, new); r2 = run(sr.apply(db, tok))               # same token again
    assert run(count(db)) == 3 and titles(db).count("New Wednesday") == 1       # never a second copy


def test_an_event_already_here_at_that_time_is_matched_not_added_again(rec, monkeypatch):
    db, cs, sr = rec
    synced(rec, monkeypatch, [V("v1", "The Pub"), P("p1", "Sam", "sam@x.com")])
    vid = cs._read()["ids"]["venue"]["v1"]["local_id"]
    run(db.events.insert_one({"id": "mine", "venue_id": vid, "event_type": "TRIVIA", "title": "My own Monday", "date": "2026-11-02T19:00:00+00:00", "duration_hours": 2.0}))
    cloud_now(rec, monkeypatch, [V("v1", "The Pub"), E("e1", "v1", "Monday Trivia", date="2026-11-02T19:00:00+00:00")])
    out = run(sr.check(db))
    assert out["summary"]["add"] == 0 and out["summary"]["left_alone"] == 1 and "matched, not added again" in out["plan"]["left_alone"][0]["why"]
    cloud_now(rec, monkeypatch, [V("v1", "The Pub"), E("e1", "v1", "Monday Trivia", date="2026-11-02T19:00:00+00:00")])
    run(sr.apply(db, out["token"])); assert run(count(db)) == 1 and titles(db) == ["My own Monday"]


def test_a_change_made_in_the_cloud_updates_the_event(rec, monkeypatch):
    db, cs, sr = rec
    synced(rec, monkeypatch, base())
    changed = [V("v1", "The Pub"), P("p1", "Sam Host", "sam@x.com"), E("e1", "v1", "Monday Trivia", date="2026-11-02T20:30:00+00:00"),
               E("e2", "v1", "Friday Trivia", date="2026-11-06T19:00:00+00:00")]
    cloud_now(rec, monkeypatch, changed); out = run(sr.check(db))
    assert out["summary"]["update"] == 1 and "date" in out["plan"]["update"][0]["fields"]
    cloud_now(rec, monkeypatch, changed); assert run(sr.apply(db, out["token"]))["applied"]["updated"] == 1
    assert any(str(e["date"]).startswith("2026-11-02T20:30") for e in run(db.events.find({}, {"_id": 0}).to_list(10)))
    assert run(count(db)) == 2


def test_an_event_removed_in_the_cloud_is_removed_only_if_the_sync_created_it_and_nobody_edited_it(rec, monkeypatch):
    db, cs, sr = rec
    synced(rec, monkeypatch, base())
    only_e1 = [V("v1", "The Pub"), P("p1", "Sam Host", "sam@x.com"), E("e1", "v1", "Monday Trivia", date="2026-11-02T19:00:00+00:00")]
    cloud_now(rec, monkeypatch, only_e1); out = run(sr.check(db))
    assert out["summary"]["remove"] == 1 and out["plan"]["remove"][0]["title"] == "Friday Trivia"
    cloud_now(rec, monkeypatch, only_e1); r = run(sr.apply(db, out["token"]))
    assert r["applied"]["removed"] == 1 and titles(db) == ["Monday Trivia"]


def test_an_event_edited_on_this_pc_is_never_overwritten_or_removed(rec, monkeypatch):
    db, cs, sr = rec
    synced(rec, monkeypatch, base())
    lid = cs._read()["ids"]["event"]["e2"]["local_id"]
    run(db.events.update_one({"id": lid}, {"$set": {"title": "Friday Trivia (host edited)", "notes": "bring the big hat"}}))
    gone = [V("v1", "The Pub"), P("p1", "Sam Host", "sam@x.com"), E("e1", "v1", "Monday Trivia", date="2026-11-02T19:00:00+00:00")]
    cloud_now(rec, monkeypatch, gone); out = run(sr.check(db))
    assert out["summary"]["remove"] == 0 and any("edited on this PC" in x["why"] for x in out["plan"]["left_alone"])
    cloud_now(rec, monkeypatch, gone); run(sr.apply(db, out["token"]))
    assert "Friday Trivia (host edited)" in titles(db)                               # still here
    again = [V("v1", "The Pub"), P("p1", "Sam Host", "sam@x.com"), E("e1", "v1", "Monday Trivia", date="2026-11-02T19:00:00+00:00"),
             E("e2", "v1", "Friday FROM CLOUD", date="2026-11-06T19:00:00+00:00")]
    cloud_now(rec, monkeypatch, again); out2 = run(sr.check(db))
    assert out2["summary"]["update"] == 0 and any("edited on this PC" in x["why"] for x in out2["plan"]["left_alone"])


def test_events_made_on_this_pc_are_never_removed(rec, monkeypatch):
    db, cs, sr = rec
    synced(rec, monkeypatch, base())
    vid = cs._read()["ids"]["venue"]["v1"]["local_id"]
    run(db.events.insert_one({"id": "pc1", "venue_id": vid, "event_type": "Karaoke", "title": "PC-only karaoke", "date": "2026-11-09T19:00:00+00:00"}))
    cloud_now(rec, monkeypatch, base()); out = run(sr.check(db))
    assert out["on_this_pc_only"] >= 1 and out["summary"]["remove"] == 0
    cloud_now(rec, monkeypatch, base()); run(sr.apply(db, out["token"]))
    assert "PC-only karaoke" in titles(db)


def test_an_empty_cloud_list_never_removes_anything(rec, monkeypatch):
    db, cs, sr = rec
    synced(rec, monkeypatch, base())
    cloud_now(rec, monkeypatch, [])                                                  # a glitch / wrong account / empty read
    out = run(sr.check(db))
    assert out["summary"]["remove"] == 0 and out["can_apply"] is False and titles(db) == ["Friday Trivia", "Monday Trivia"]
    assert any("empty" in x["why"] for x in out["plan"]["left_alone"])


def test_a_cloud_event_for_a_venue_or_host_not_on_this_pc_waits_instead_of_guessing(rec, monkeypatch):
    db, cs, sr = rec
    synced(rec, monkeypatch, base())
    cloud_now(rec, monkeypatch, base() + [E("e9", "vNEW", "Mystery", date="2026-11-10T19:00:00+00:00"),
                                          E("e8", "v1", "Claimed by a stranger", claimed="stranger@x.com", date="2026-11-11T19:00:00+00:00")])
    out = run(sr.check(db))
    assert out["summary"]["waiting"] == 2 and out["summary"]["add"] == 0
    assert "Mystery" not in titles(db)


def test_apply_refuses_when_the_schedule_changed_after_the_check(rec, monkeypatch):
    db, cs, sr = rec
    synced(rec, monkeypatch, base())
    cloud_now(rec, monkeypatch, base() + [E("e3", "v1", "New", date="2026-11-04T19:00:00+00:00")]); tok = run(sr.check(db))["token"]
    cloud_now(rec, monkeypatch, base() + [E("e3", "v1", "New", date="2026-11-04T19:00:00+00:00"), E("e4", "v1", "Even newer", date="2026-11-05T19:00:00+00:00")])
    r = run(sr.apply(db, tok))
    assert not r["ok"] and r["error"] == "changed" and run(count(db)) == 2           # nothing applied on a stale preview


def test_apply_without_a_check_does_nothing(rec, monkeypatch):
    db, cs, sr = rec
    synced(rec, monkeypatch, base()); cloud_now(rec, monkeypatch, base() + [E("e3", "v1", "New", date="2026-11-04T19:00:00+00:00")])
    for bad in ("", None, "made-up-token"):
        assert not run(sr.apply(db, bad))["ok"]
    assert run(count(db)) == 2


def test_a_backup_is_written_before_any_change(rec, monkeypatch, tmp_path):
    db, cs, sr = rec
    synced(rec, monkeypatch, base())
    new = base() + [E("e3", "v1", "New", date="2026-11-04T19:00:00+00:00")]
    cloud_now(rec, monkeypatch, new); tok = run(sr.check(db))["token"]
    cloud_now(rec, monkeypatch, new); r = run(sr.apply(db, tok))
    assert r["ok"] and Path(r["backup"]).is_dir() and (Path(r["backup"]) / "events.json").exists()
    import json; assert len(json.loads((Path(r["backup"]) / "events.json").read_text())) == 2        # the BEFORE state


def test_offline_lapsed_and_unlinked_change_nothing_and_say_why(rec, monkeypatch):
    db, cs, sr = rec
    synced(rec, monkeypatch, base()); before = titles(db)
    for err in ("unreachable", "subscription_lapsed", "unauthorized"):
        async def bad(since, e=err): return {"ok": False, "error": e}
        monkeypatch.setattr(cs, "_fetch", bad)
        out = run(sr.check(db))
        assert out["ok"] is False and out["message"] and out["can_apply"] is False and titles(db) == before
    from native import cloud_link
    monkeypatch.setattr(cloud_link, "get_token", lambda: "")
    assert run(sr.check(db))["error"] == "unlinked"


def test_people_are_never_deleted_by_a_reconcile(rec, monkeypatch):
    db, cs, sr = rec
    synced(rec, monkeypatch, base())
    n = run(db.employees.count_documents({}))
    cloud_now(rec, monkeypatch, [V("v1", "The Pub")])                                 # the person is gone from the Cloud feed
    run(sr.check(db)); assert run(db.employees.count_documents({})) == n


def test_a_deleted_then_recreated_event_in_the_feed_log_counts_once(rec, monkeypatch):
    """The feed is a log: the LAST entry for an item wins, and a later delete removes it."""
    db, cs, sr = rec
    synced(rec, monkeypatch, base())
    gone_e2 = {"item_id": "e2", "kind": "event", "revision": 9, "deleted": True, "data": None}
    cloud_now(rec, monkeypatch, base() + [gone_e2]); out = run(sr.check(db))
    assert out["summary"]["remove"] == 1 and out["cloud_events"] == 1
    again = {**E("e2", "v1", "Friday Trivia", date="2026-11-06T19:00:00+00:00"), "revision": 10}
    cloud_now(rec, monkeypatch, base() + [gone_e2, again]); out2 = run(sr.check(db))
    assert out2["cloud_events"] == 2 and out2["summary"]["remove"] == 0


# ---- the real HTTP routes the button calls ----
@pytest.fixture
def web(rec, monkeypatch):
    db, cs, sr = rec
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from native import cloud_link_router as clr
    import importlib; importlib.reload(clr)
    monkeypatch.setattr(clr, "_db", lambda: db)
    app = FastAPI(); app.include_router(clr.router)
    return TestClient(app), clr, db, cs, sr


def test_the_routes_check_then_apply_over_http(web, monkeypatch):
    c, clr, db, cs, sr = web
    rec = (db, cs, sr)
    synced(rec, monkeypatch, base())
    new = base() + [E("e3", "v1", "Wednesday Trivia", date="2026-11-04T19:00:00+00:00")]
    cloud_now(rec, monkeypatch, new)
    chk = c.post(clr.router.prefix + "/schedule/check").json()
    assert chk["ok"] and chk["summary"]["add"] == 1 and run(count(db)) == 2             # the check changed nothing
    cloud_now(rec, monkeypatch, new)
    done = c.post(clr.router.prefix + "/schedule/apply", json={"token": chk["token"]}).json()
    assert done["ok"] and done["applied"]["added"] == 1 and run(count(db)) == 3
    cloud_now(rec, monkeypatch, new)
    assert c.post(clr.router.prefix + "/schedule/check").json()["can_apply"] is False   # now it matches


def test_the_apply_route_refuses_a_missing_or_wrong_token(web, monkeypatch):
    c, clr, db, cs, sr = web
    synced((db, cs, sr), monkeypatch, base()); cloud_now((db, cs, sr), monkeypatch, base() + [E("e3", "v1", "New", date="2026-11-04T19:00:00+00:00")])
    for body in ({}, {"token": ""}, {"token": "nope"}):
        r = c.post(clr.router.prefix + "/schedule/apply", json=body).json()
        assert r["ok"] is False
    assert run(count(db)) == 2


# ---- the screen (source checks: the window itself can only be tried on a real PC) ----
CARD = (Path(__file__).resolve().parent.parent.parent / "frontend" / "src" / "components" / "admin" / "ScheduleReconcile.jsx").read_text(encoding="utf-8")
TAB = (Path(__file__).resolve().parent.parent.parent / "frontend" / "src" / "components" / "admin" / "IntegrationsTab.jsx").read_text(encoding="utf-8")
API = (Path(__file__).resolve().parent.parent.parent / "frontend" / "src" / "lib" / "api.js").read_text(encoding="utf-8")


def test_the_card_only_reads_fields_the_backend_sends(web, monkeypatch):
    import re
    c, clr, db, cs, sr = web
    synced((db, cs, sr), monkeypatch, base()); cloud_now((db, cs, sr), monkeypatch, base() + [E("e3", "v1", "New", date="2026-11-04T19:00:00+00:00")])
    chk = c.post(clr.router.prefix + "/schedule/check").json()
    top = set(chk) | {"ok"}
    row_keys = set(chk["plan"]["add"][0])
    used_top = set(re.findall(r"\bres\.([a-z_]+)", CARD)) - {"map"}
    used_plan = set(re.findall(r"\bplan\.([a-z_]+)", CARD))
    used_row = set(re.findall(r"\br\.([a-z_]+)", CARD)) - {"ok", "token", "error", "message", "kept", "applied"}
    assert used_top <= top, used_top - top
    assert used_plan <= set(chk["plan"]), used_plan - set(chk["plan"])
    assert used_row <= row_keys, used_row - row_keys


def test_the_screen_checks_first_applies_only_the_checked_token_and_sits_in_the_sync_box():
    assert "api.cloudScheduleCheck" in CARD and "api.cloudScheduleApply(res.token)" in CARD and "if (!res?.token) return;" in CARD
    assert "res.can_apply &&" in CARD                                     # the Update button only appears when the check found something
    assert "Nothing changes until you press Update" in CARD and "a backup is saved first" in CARD
    assert "<ScheduleReconcile" in TAB and "cloudScheduleCheck" in API and "schedule/check" in API and "schedule/apply" in API
    assert "if (r.ok) { setRes(null); onDone" in CARD and "r.error === 'changed'" in CARD    # a stale preview is dropped, not reused
