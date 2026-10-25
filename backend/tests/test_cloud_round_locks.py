"""Round locks <-> Cloud (docs/CLOUD_TASK_round_locks.md). Real MontyDB + real round_usage.json; only the HTTP is faked."""
import asyncio, importlib, json, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_cloud_sync import env as _env, feed, V, run  # noqa: F401  (same fixture + helpers as the schedule sync)


@pytest.fixture
def env(_env, tmp_path, monkeypatch):
    db, cs, es = _env
    import native_slides, round_usage
    importlib.reload(round_usage)
    monkeypatch.setattr(native_slides, "_docs_root", lambda: tmp_path / "docs")
    from native import cloud_locks
    importlib.reload(cloud_locks)
    sent = []
    cloud = {"online": True, "reply": None}

    async def fake_post(actions):
        if not cloud["online"]:
            return {"ok": False, "error": "unreachable"}
        sent.extend(actions)
        return {"ok": True, "results": [{"action_id": a["action_id"], "result": (cloud["reply"] or "applied")} for a in actions]}
    monkeypatch.setattr(cloud_locks, "_post", fake_post)
    return db, cs, cloud_locks, round_usage, sent, cloud


def L(i, vid, file, used, released=False, released_at=None, pres="p1"):
    exp = (datetime.fromisoformat(used) + timedelta(days=180)).isoformat()
    return {"item_id": i, "kind": "round_lock", "revision": 1, "deleted": False, "data": {
        "venue_id": vid, "venue_name": "The Pub", "round_file_name": file, "round_type": "MYS", "used_at": used, "expires_at": exp,
        "presentation_id": pres, "presentation_name": "Show", "used_by": "sam", "released": released,
        "released_at": released_at, "released_by": "o@x.com" if released else None}}


def now(days=0): return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


def link_venue(env, monkeypatch):
    db, cs, cl, ru, sent, cloud = env
    feed(cs, monkeypatch, [{"seq": 1, "has_more": False, "items": [V("v1", "The Pub")]}])
    run(cs.pull_once(db))
    return db, cs, cl, ru, sent, cloud


def test_pull_adds_a_lock_from_another_pc_and_the_wizard_sees_it(env, monkeypatch):
    db, cs, cl, ru, sent, cloud = link_venue(env, monkeypatch)
    feed(cs, monkeypatch, [{"seq": 2, "has_more": False, "items": [L("a" * 40, "v1", "MYS__History-ab12cd34.bighat", now(-1))]}])
    run(cs.pull_once(db))
    assert "history" in {ru.norm_name(x) for x in ru.locked_names("The Pub")} or ru.is_locked("MYS__History.bighat", ru.locked_names("The Pub"))
    assert len(ru._load()) == 1 and ru._load()[0]["source"] == "cloud"


def test_pull_twice_does_not_duplicate(env, monkeypatch):
    db, cs, cl, ru, sent, cloud = link_venue(env, monkeypatch)
    it = L("a" * 40, "v1", "MYS__History.bighat", now(-1))
    feed(cs, monkeypatch, [{"seq": 2, "has_more": False, "items": [it]}]); run(cs.pull_once(db))
    feed(cs, monkeypatch, [{"seq": 3, "has_more": False, "items": [it]}]); run(cs.pull_once(db))
    assert len(ru._load()) == 1


def test_push_sends_new_local_locks_once(env, monkeypatch):
    db, cs, cl, ru, sent, cloud = link_venue(env, monkeypatch)
    ru.record_usage(location_id="the-pub", location_name="The Pub", round_files=[{"order": 1, "type": "MYS", "file": "MYS__History-ab12cd34.bighat"},
                    {"order": 2, "type": "GEN", "file": "GEN__Sports.bighat"}], used_by="sam", presentation_id="p9", presentation_name="Show 9")
    feed(cs, monkeypatch, []); run(cs.pull_once(db))
    locks = [a for a in sent if a["type"] == "lock"]
    assert len(locks) == 2 and all(a["payload"]["venue_id"] == "v1" for a in locks)
    assert len(locks[0]["payload"]["item_id"]) == 40
    feed(cs, monkeypatch, []); run(cs.pull_once(db))
    assert len([a for a in sent if a["type"] == "lock"]) == 2            # idempotent: nothing sent twice
    assert cl.public_status()["outbox"] == 0


def test_offline_pc_keeps_locks_and_sends_later_without_losing_any(env, monkeypatch):
    db, cs, cl, ru, sent, cloud = link_venue(env, monkeypatch)
    ru.record_usage(location_id="the-pub", location_name="The Pub", round_files=[{"order": 1, "type": "MYS", "file": "MYS__A.bighat"}],
                    used_by="s", presentation_id="p1", presentation_name="S")
    cloud["online"] = False
    feed(cs, monkeypatch, []); run(cs.pull_once(db))
    assert sent == [] and cl.public_status()["outbox"] == 1 and len(ru._load()) == 1
    cloud["online"] = True
    feed(cs, monkeypatch, []); run(cs.pull_once(db))
    assert len(sent) == 1 and cl.public_status()["outbox"] == 0


def test_cloud_release_frees_the_round_here_and_stale_copy_cannot_relock(env, monkeypatch):
    db, cs, cl, ru, sent, cloud = link_venue(env, monkeypatch)
    used = now(-5)
    feed(cs, monkeypatch, [{"seq": 2, "has_more": False, "items": [L("b" * 40, "v1", "MYS__A.bighat", used)]}]); run(cs.pull_once(db))
    assert len(ru._load()) == 1
    feed(cs, monkeypatch, [{"seq": 3, "has_more": False, "items": [L("b" * 40, "v1", "MYS__A.bighat", used, True, now(-1))]}]); run(cs.pull_once(db))
    assert ru._load() == [] and not ru.is_locked("MYS__A.bighat", ru.locked_names("The Pub"))
    feed(cs, monkeypatch, [{"seq": 4, "has_more": False, "items": [L("b" * 40, "v1", "MYS__A.bighat", used)]}]); run(cs.pull_once(db))
    assert ru._load() == []                                              # the old copy of the lock does not come back


def test_a_genuinely_newer_use_after_a_release_locks_again(env, monkeypatch):
    db, cs, cl, ru, sent, cloud = link_venue(env, monkeypatch)
    feed(cs, monkeypatch, [{"seq": 2, "has_more": False, "items": [L("c" * 40, "v1", "MYS__A.bighat", now(-9), True, now(-8))]}]); run(cs.pull_once(db))
    feed(cs, monkeypatch, [{"seq": 3, "has_more": False, "items": [L("c" * 40, "v1", "MYS__A.bighat", now(-1))]}]); run(cs.pull_once(db))
    assert len(ru._load()) == 1


def test_local_admin_release_is_pushed_as_a_release(env, monkeypatch):
    db, cs, cl, ru, sent, cloud = link_venue(env, monkeypatch)
    ru.record_usage(location_id="the-pub", location_name="The Pub", round_files=[{"order": 1, "type": "MYS", "file": "MYS__A.bighat"}],
                    used_by="s", presentation_id="p1", presentation_name="S")
    feed(cs, monkeypatch, []); run(cs.pull_once(db))
    rid = ru._load()[0]["id"]
    assert ru.release(rid) == 1
    feed(cs, monkeypatch, []); run(cs.pull_once(db))
    rel = [a for a in sent if a["type"] == "release"]
    assert len(rel) == 1 and rel[0]["payload"]["item_id"] == [a for a in sent if a["type"] == "lock"][0]["payload"]["item_id"]
    # and the old Cloud copy does not re-lock it here
    feed(cs, monkeypatch, [{"seq": 9, "has_more": False, "items": [L(rel[0]["payload"]["item_id"], "v1", "MYS__A.bighat", ru._load() and now(-1) or now(-30))]}])
    run(cs.pull_once(db))
    assert ru._load() == []


def test_a_missing_record_without_a_release_is_never_told_to_the_cloud(env, monkeypatch):
    db, cs, cl, ru, sent, cloud = link_venue(env, monkeypatch)
    ru.record_usage(location_id="the-pub", location_name="The Pub", round_files=[{"order": 1, "type": "MYS", "file": "MYS__A.bighat"}],
                    used_by="s", presentation_id="p1", presentation_name="S")
    feed(cs, monkeypatch, []); run(cs.pull_once(db))
    ru._save([])                                   # file lost/edited by hand: NOT a release
    feed(cs, monkeypatch, []); run(cs.pull_once(db))
    assert not [a for a in sent if a["type"] == "release"]


def test_lock_for_a_venue_not_here_yet_waits_then_applies(env, monkeypatch):
    db, cs, cl, ru, sent, cloud = env
    feed(cs, monkeypatch, [{"seq": 2, "has_more": False, "items": [L("d" * 40, "v1", "MYS__A.bighat", now(-1)), V("v1", "The Pub")]}])
    run(cs.pull_once(db))
    assert len(ru._load()) == 1


def test_not_admin_release_stays_queued_and_blocked_not_dropped(env, monkeypatch):
    db, cs, cl, ru, sent, cloud = link_venue(env, monkeypatch)
    ru.record_usage(location_id="the-pub", location_name="The Pub", round_files=[{"order": 1, "type": "MYS", "file": "MYS__A.bighat"}],
                    used_by="s", presentation_id="p1", presentation_name="S")
    feed(cs, monkeypatch, []); run(cs.pull_once(db))
    ru.release(ru._load()[0]["id"])
    cloud["reply"] = "rejected"
    async def nope(actions): return {"ok": True, "results": [{"action_id": a["action_id"], "result": "rejected", "reason": "not_admin"} for a in actions]}
    monkeypatch.setattr(cl, "_post", nope)
    feed(cs, monkeypatch, []); run(cs.pull_once(db))
    assert cl.public_status()["blocked"] == 1 and cl.public_status()["outbox"] == 1
