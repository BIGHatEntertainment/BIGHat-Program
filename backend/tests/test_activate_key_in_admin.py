"""v32.2.5: a host who skipped key verification at Setup can still activate the key in Admin > Product Key.
Real routes + real config + the real Cloud-link key; only the license server's answers are faked."""
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_alpha80_product_keys import env, _prefix, MAIN, ADDON  # noqa: E402,F401

TYPO = "BHE-ZZZZ-ZZZZ-ZZZZ-ZZZZ"


def offline_setup(cm, key=MAIN, **extra):
    """exactly what /setup/initialize leaves after 'Continue offline'"""
    cm.config["license_status"] = {"key": key, "pending_cloud_activation": True, "master_admin_email": "owner@x.com",
                                   "total_seats_allowed": 5, "active_seats": [], **extra}
    cm.config["subscription"] = {}


def premium():
    from native.subscription import is_premium_active
    return is_premium_active("story_generator_enabled")


def link_key():
    from native import cloud_link
    return cloud_link._license_key()


def test_same_key_entered_in_admin_activates_and_clears_the_waiting_flag(env):
    c, cloud, cm = env; p = _prefix(c)
    offline_setup(cm)
    st = c.get(p + "/license/product-keys").json()
    assert st["needs_verification"] is True and st["verified"] is False and st["owns_standalone"] is False and not premium()
    r = c.post(p + "/license/product-key", json={"product_key": MAIN})
    assert r.status_code == 200
    body = r.json()
    assert body["verified"] is True and body["needs_verification"] is False and body["owns_standalone"] is True and premium()
    lic = cm.config["license_status"]
    assert lic["pending_cloud_activation"] is False and "cloud_activation_error" not in lic and link_key() == MAIN


def test_the_right_key_replaces_a_mistyped_key_saved_at_setup(env):
    c, cloud, cm = env; p = _prefix(c)
    offline_setup(cm, key=TYPO)
    assert link_key() == TYPO
    r = c.post(p + "/license/product-key", json={"product_key": MAIN})
    assert r.status_code == 200 and premium()
    assert cm.config["license_status"]["key"] == MAIN and link_key() == MAIN          # the Cloud link now announces the RIGHT key
    assert r.json()["main_key"].endswith("DDDD") and r.json()["extra_keys"] == []      # not filed away as an add-on
    assert cm.config["license_status"]["pending_cloud_activation"] is False


def test_after_the_background_retry_gave_up_admin_can_still_activate(env):
    c, cloud, cm = env; p = _prefix(c)
    offline_setup(cm, pending_cloud_activation=False, cloud_activation_error="unknown_key")
    st = c.get(p + "/license/product-keys").json()
    assert st["needs_verification"] is True and st["verify_problem"] == "unknown_key"
    assert c.post(p + "/license/product-key", json={"product_key": MAIN}).status_code == 200
    st = c.get(p + "/license/product-keys").json()
    assert st["verified"] is True and st["verify_problem"] is None and premium()


def test_a_verified_program_still_treats_a_different_key_as_an_addon(env):
    c, cloud, cm = env; p = _prefix(c)
    assert c.post(p + "/license/product-key", json={"product_key": MAIN}).status_code == 200      # a normal, verified main key
    assert c.get(p + "/license/product-keys").json()["verified"] is True
    cloud["answers"][ADDON] = {"ok": True, "owns_standalone": False, "owns_music_bingo": True, "owns_karaoke": False, "cloud_library_active": False}
    r = c.post(p + "/license/product-key", json={"product_key": ADDON})
    assert r.status_code == 200 and cm.config["license_status"]["key"] == MAIN             # main key NEVER swapped for an add-on
    assert [e["unlocks"] for e in r.json()["extra_keys"]] == [["music_bingo"]]


def test_a_refused_key_changes_nothing_and_says_why(env):
    c, cloud, cm = env; p = _prefix(c)
    offline_setup(cm)
    cloud["answers"][MAIN] = {"ok": False, "error": "seat_limit_reached (5)", "message": "seat_limit_reached (5)", "status_code": 400}
    r = c.post(p + "/license/product-key", json={"product_key": MAIN})
    assert r.status_code == 400 and "seat_limit_reached" in r.json()["detail"]["error"]
    assert cm.config["license_status"]["pending_cloud_activation"] is True and not premium()      # still waiting, still locked, nothing granted


def test_offline_in_admin_changes_nothing(env):
    c, cloud, cm = env; p = _prefix(c)
    offline_setup(cm)
    cloud["answers"][MAIN] = {"ok": False, "error": "network_error", "message": "down"}
    r = c.post(p + "/license/product-key", json={"product_key": MAIN})
    assert r.status_code == 503 and not premium() and cm.config["license_status"]["pending_cloud_activation"] is True


def test_a_wrong_key_cannot_replace_the_saved_key_or_unlock_anything(env):
    c, cloud, cm = env; p = _prefix(c)
    offline_setup(cm, key=MAIN)
    r = c.post(p + "/license/product-key", json={"product_key": "BHE-QQQQ-QQQQ-QQQQ-QQQQ"})        # the fake server does not know it
    assert r.status_code == 400 and cm.config["license_status"]["key"] == MAIN and not premium()


def test_the_card_button_route_also_clears_the_waiting_flag(env):
    c, cloud, cm = env; p = _prefix(c)
    offline_setup(cm, key=TYPO)
    r = c.post(p + "/license/cloud/activate", json={"license_key": MAIN, "email": "owner@x.com"})
    assert r.status_code == 200 and premium()
    lic = cm.config["license_status"]
    assert lic["key"] == MAIN and lic["pending_cloud_activation"] is False and "cloud_activation_error" not in lic


def test_saved_addon_keys_survive_activating_the_main_key_late(env):
    c, cloud, cm = env; p = _prefix(c)
    offline_setup(cm)
    cm.config["subscription"] = {"extra_keys": [{"key": ADDON, "unlocks": ["karaoke"]}]}
    assert c.post(p + "/license/product-key", json={"product_key": MAIN}).status_code == 200
    s = cm.config["subscription"]
    assert s["owns_standalone"] is True and s["owns_karaoke"] is True and s["karaoke_enabled"] is True


def test_background_retry_keeps_the_reason_when_the_server_refuses(env, monkeypatch):
    import asyncio
    monkeypatch.setenv("MONGO_URL", "mongodb://localhost:27017")          # scheduler.py reads it at import
    monkeypatch.setenv("DB_NAME", "test")
    import scheduler
    from native import cloud_client
    c, cloud, cm = env
    offline_setup(cm)
    async def refuse(**kw): return {"ok": False, "error": "unknown_key", "message": "unknown_key", "status_code": 404}
    monkeypatch.setattr(cloud_client, "activate", refuse)
    monkeypatch.setattr("native.config.config_manager", cm)
    asyncio.run(scheduler.retry_pending_cloud_activation())
    lic = cm.config["license_status"]
    assert lic["pending_cloud_activation"] is False and lic["cloud_activation_error"] == "unknown_key"
    p = _prefix(c)
    st = c.get(p + "/license/product-keys").json()
    assert st["needs_verification"] is True and st["verify_problem"] == "unknown_key"          # the owner is told, not left guessing
