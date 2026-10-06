"""alpha.80 - Product Key tab backend: add-on keys merge, never replace."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


MAIN = "BHE-AAAA-BBBB-CCCC-DDDD"
ADDON = "BHE-EEEE-FFFF-GGGG-HHHH"


@pytest.fixture
def env(tmp_path, monkeypatch):
    # Other test files importlib.reload() native modules, so each module can hold
    # a DIFFERENT config_manager object. Point every one of them at the same
    # fresh temp config so these tests can't be affected by test order.
    import sys
    from native import config as native_config
    from native import router as native_router
    from native import cloud_client
    from native import product_keys, license as native_license, subscription as native_sub
    cm = native_config.config_manager
    monkeypatch.setattr(cm, "config_path", tmp_path / "system_config.json")
    monkeypatch.setattr(cm, "config", native_config._default_config())
    for mod in (native_router, product_keys, native_license, native_sub):
        monkeypatch.setattr(mod, "config_manager", cm, raising=False)
    globals()["native_router"] = native_router
    app = FastAPI()
    app.include_router(native_router.router, prefix="/api")
    app.dependency_overrides[native_router._master_guard] = lambda: {"role": "master_admin"}
    cloud = {"calls": [], "answers": {}}

    async def fake_activate(*, license_key, hwid, machine_name=None, email=None):
        cloud["calls"].append(("activate", license_key))
        return cloud["answers"].get(license_key, {"ok": False, "error": "invalid_key", "message": "Unknown key"})

    async def fake_validate(*, license_key, hwid):
        cloud["calls"].append(("validate", license_key))
        return cloud["answers"].get(license_key, {"ok": False, "error": "network_error"})

    monkeypatch.setattr(cloud_client, "activate", fake_activate)
    monkeypatch.setattr(cloud_client, "validate", fake_validate)
    cloud["answers"][MAIN] = {"ok": True, "owns_standalone": True, "owns_music_bingo": False,
                              "owns_karaoke": False, "cloud_library_active": False}
    return TestClient(app), cloud, cm


def _prefix(c):
    # find the route prefix actually used
    for r in c.app.routes:
        if getattr(r, "path", "").endswith("/license/product-key"):
            return r.path.rsplit("/license/product-key", 1)[0]
    raise AssertionError("route missing")


def test_main_key_then_addon_key_merges(env):
    c, cloud, cm = env
    p = _prefix(c)
    assert c.post(p + "/license/product-key", json={"product_key": MAIN}).status_code == 200
    cloud["answers"][ADDON] = {"ok": True, "owns_standalone": False, "owns_music_bingo": True,
                               "owns_karaoke": False, "cloud_library_active": False}
    r = c.post(p + "/license/product-key", json={"product_key": ADDON.lower()})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["owns_standalone"] is True            # base kept
    assert body["addons"]["music_bingo"] is True      # new add-on unlocked
    assert body["addons"]["karaoke"] is False
    assert cm.config["license_status"]["key"] == MAIN  # main key NOT replaced
    from native.subscription import is_premium_active
    assert is_premium_active("music_bingo_enabled") is True   # the REAL lock opens
    assert is_premium_active("karaoke_enabled") is False      # other add-on stays locked
    assert body["extra_keys"][0]["unlocks"] == ["music_bingo"]


def test_addon_key_without_base_stays_locked(env):
    c, cloud, cm = env
    p = _prefix(c)
    cloud["answers"][ADDON] = {"ok": True, "owns_standalone": False, "owns_karaoke": True}
    assert c.post(p + "/license/product-key", json={"product_key": ADDON}).status_code == 200
    from native.subscription import is_premium_active
    assert is_premium_active("karaoke_enabled") is False  # add-ons need the base program


def test_bad_format_and_rejected_key(env):
    c, cloud, cm = env
    p = _prefix(c)
    r = c.post(p + "/license/product-key", json={"product_key": "nonsense"})
    assert r.status_code == 400 and r.json()["detail"]["error"] == "invalid_license_format"
    r = c.post(p + "/license/product-key", json={"product_key": "BHE-1111-2222-3333-4444"})
    assert r.status_code == 400
    assert "license_status" not in cm.config or not cm.config["license_status"].get("key")


def test_offline_changes_nothing(env):
    c, cloud, cm = env
    p = _prefix(c)
    c.post(p + "/license/product-key", json={"product_key": MAIN})
    cloud["answers"]["BHE-9999-9999-9999-9999"] = {"ok": False, "error": "network_error"}
    r = c.post(p + "/license/product-key", json={"product_key": "BHE-9999-9999-9999-9999"})
    assert r.status_code == 503
    assert not cm.config["subscription"].get("extra_keys")


def test_validate_replays_extra_keys_and_offline_keeps_them(env):
    c, cloud, cm = env
    p = _prefix(c)
    c.post(p + "/license/product-key", json={"product_key": MAIN})
    cloud["answers"][ADDON] = {"ok": True, "owns_standalone": False, "owns_music_bingo": True}
    c.post(p + "/license/product-key", json={"product_key": ADDON})
    # periodic validate: main ok, add-on key ok -> still unlocked (not switched off)
    cloud["answers"][MAIN] = {"ok": True, "owns_standalone": True}
    assert c.post(p + "/license/cloud/validate").json()["status"] == "ok"
    assert cm.config["subscription"]["owns_music_bingo"] is True
    # add-on key offline during validate -> stays unlocked
    cloud["answers"][ADDON] = {"ok": False, "error": "network_error"}
    c.post(p + "/license/cloud/validate")
    assert cm.config["subscription"]["owns_music_bingo"] is True


def test_non_master_is_refused(env):
    c, cloud, cm = env
    from fastapi import HTTPException
    def deny():
        raise HTTPException(status_code=403, detail="master_admin_required")
    c.app.dependency_overrides[native_router._master_guard] = deny
    p = _prefix(c)
    assert c.post(p + "/license/product-key", json={"product_key": MAIN}).status_code == 403
    assert c.get(p + "/license/product-keys").status_code == 403
    assert cloud["calls"] == []  # never reached the cloud


def test_status_masks_keys(env):
    c, cloud, cm = env
    p = _prefix(c)
    c.post(p + "/license/product-key", json={"product_key": MAIN})
    s = c.get(p + "/license/product-keys").json()
    assert MAIN not in str(s) and s["main_key"].startswith("BHE-")


def test_revoked_addon_key_is_not_reapplied(env):
    c, cloud, cm = env
    p = _prefix(c)
    c.post(p + "/license/product-key", json={"product_key": MAIN})
    cloud["answers"][ADDON] = {"ok": True, "owns_standalone": False, "owns_music_bingo": True}
    c.post(p + "/license/product-key", json={"product_key": ADDON})
    cloud["answers"][ADDON] = {"ok": False, "error": "revoked", "message": "Key revoked"}
    c.post(p + "/license/cloud/validate")
    from native.subscription import is_premium_active
    assert is_premium_active("music_bingo_enabled") is False


def test_reentering_main_key_keeps_addons(env):
    c, cloud, cm = env
    p = _prefix(c)
    c.post(p + "/license/product-key", json={"product_key": MAIN})
    cloud["answers"][ADDON] = {"ok": True, "owns_standalone": False, "owns_music_bingo": True}
    c.post(p + "/license/product-key", json={"product_key": ADDON})
    r = c.post(p + "/license/product-key", json={"product_key": MAIN})
    assert r.status_code == 200
    assert r.json()["addons"]["music_bingo"] is True
    from native.subscription import is_premium_active
    assert is_premium_active("music_bingo_enabled") is True
