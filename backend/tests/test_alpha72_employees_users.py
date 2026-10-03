"""alpha.72: a Schedule employee is also a User Management user (standalone app keeps users in system_config.json)."""
import os, sys, json
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture
def sync(tmp_path, monkeypatch):
    monkeypatch.setenv("BIGHAT_CONFIG_PATH", str(tmp_path / "system_config.json"))
    monkeypatch.setenv("BIGHAT_NATIVE_MODE", "1")
    (tmp_path / "db").mkdir()
    monkeypatch.setenv("BIGHAT_DB_DIR", str(tmp_path / "db"))
    import importlib
    from native import db_factory
    importlib.reload(db_factory)
    import native.config as cfg
    importlib.reload(cfg)
    import native
    native.config_manager = cfg.config_manager
    from native import admin_router, employee_sync
    importlib.reload(admin_router)
    importlib.reload(employee_sync)
    cfg.config_manager.config["users"] = [{"id": "m1", "email": "owner@example.com", "role": "master_admin", "is_master": True,
                                            "password_hash": "x", "first_name": "Owner"}]
    yield employee_sync, cfg.config_manager
    db_factory.close_all()


async def _run(coro):
    return await coro


@pytest.mark.asyncio
async def test_new_employee_becomes_a_user_that_is_saved_in_the_config(sync):
    es, cm = sync
    u = await es.upsert_user_for_employee("Sam Q Host", "Sam.Host@Example.com", False, "555", "SamsPass99", "default")
    assert u["email"] == "sam.host@example.com" and u["role"] == "host" and u["first_name"] == "Sam" and u["last_name"] == "Q Host"
    assert any(x["email"] == "sam.host@example.com" for x in cm.config["users"])
    assert u["password_hash"] != "SamsPass99" and u["password_hash"].startswith("$2")        # hashed, never plain


@pytest.mark.asyncio
async def test_edit_changes_role_but_keeps_the_password_unless_a_new_one_is_given(sync):
    es, cm = sync
    u = await es.upsert_user_for_employee("Sam", "sam@x.com", False, None, "SamsPass99", "default")
    h1 = u["password_hash"]
    u2 = await es.upsert_user_for_employee("Sam", "sam@x.com", True, None, None, "default")
    assert u2["role"] == "admin" and u2["password_hash"] == h1
    u3 = await es.upsert_user_for_employee("Sam", "sam@x.com", True, None, "NewPass77", "default")
    assert u3["password_hash"] != h1
    assert len([x for x in cm.config["users"] if x["email"] == "sam@x.com"]) == 1          # never a duplicate


@pytest.mark.asyncio
async def test_master_admin_is_never_changed_or_removed_from_the_schedule(sync):
    es, cm = sync
    before = dict(cm.config["users"][0])
    await es.upsert_user_for_employee("Hacker", "owner@example.com", False, None, "Whatever1", "default")
    assert cm.config["users"][0]["role"] == "master_admin" and cm.config["users"][0]["password_hash"] == before["password_hash"]
    assert await es.remove_user_for_employee("owner@example.com") is False
    assert await es.set_user_password("owner@example.com", "Whatever1") is False
    assert any(x["email"] == "owner@example.com" for x in cm.config["users"])


@pytest.mark.asyncio
async def test_delete_removes_the_user_and_reset_changes_the_login(sync):
    es, cm = sync
    u = await es.upsert_user_for_employee("Sam", "sam@x.com", False, None, "OldPass11", "default")
    old = u["password_hash"]
    assert await es.set_user_password("SAM@x.com", "BrandNew77") is True
    assert es.find_user("sam@x.com")["password_hash"] != old
    assert await es.remove_user_for_employee("sam@x.com") is True
    assert es.find_user("sam@x.com") is None


@pytest.mark.asyncio
async def test_startup_sync_only_adds_missing_users_and_never_changes_existing_ones(sync):
    es, cm = sync
    await es.upsert_user_for_employee("Ann", "ann@x.com", False, None, "AnnPass11", "default")
    h = es.find_user("ann@x.com")["password_hash"]
    made = await es.sync_all([{"name": "Ann", "email": "ann@x.com", "is_admin": True}, {"name": "Bo", "email": "bo@x.com", "is_admin": False}, {"name": "", "email": ""}], "default")
    assert made == 1 and es.find_user("bo@x.com") and es.find_user("ann@x.com")["role"] == "host" and es.find_user("ann@x.com")["password_hash"] == h


def test_temporary_passwords_are_readable_and_different():
    from native import employee_sync as es
    import re
    pws = {es.make_temp_password() for _ in range(40)}
    assert len(pws) > 20 and all(re.fullmatch(r"[A-Z][a-z]+-[A-Z][a-z]+-\d{4}", p) for p in pws)
