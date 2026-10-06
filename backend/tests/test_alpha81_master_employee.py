"""alpha.81: the master admin is also a Schedule employee; their password is never replaced."""
import sys, importlib
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


class FakeEmployees:
    def __init__(self): self.rows = []
    async def find_one(self, q, *a, **k):
        rx = (q.get("email") or {}).get("$regex") if isinstance(q.get("email"), dict) else None
        for r in self.rows:
            if rx and __import__("re").match(rx, r["email"], __import__("re").I): return r
        return None
    async def insert_one(self, d): self.rows.append(dict(d))


class FakeDB:
    def __init__(self): self.employees = FakeEmployees()


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("BIGHAT_CONFIG_PATH", str(tmp_path / "system_config.json"))
    monkeypatch.setenv("BIGHAT_NATIVE_MODE", "1")
    (tmp_path / "db").mkdir()
    monkeypatch.setenv("BIGHAT_DB_DIR", str(tmp_path / "db"))
    from native import db_factory
    importlib.reload(db_factory)
    import native.config as cfg
    importlib.reload(cfg)
    import native
    native.config_manager = cfg.config_manager
    from native import admin_router, employee_sync
    importlib.reload(admin_router)
    importlib.reload(employee_sync)
    cfg.config_manager.config["users"] = [{
        "id": "m1", "email": "Sellards@BigHat.live", "role": "master_admin", "is_master": True,
        "password_hash": "REAL-HASH", "first_name": "Nick", "last_name": "Sellards", "display_name": "Nick Sellards", "phone": "555"}]
    yield employee_sync, cfg.config_manager, FakeDB()
    db_factory.close_all()


@pytest.mark.asyncio
async def test_master_is_added_to_the_schedule_with_no_password_change(env):
    es, cm, db = env
    assert await es.ensure_master_employee(db) is True
    row = db.employees.rows[0]
    assert row["email"] == "sellards@bighat.live" and row["is_admin"] is True and row["name"] == "Nick Sellards"
    assert row["password"] == ""                                   # no copy of any password in the schedule
    assert cm.config["users"][0]["password_hash"] == "REAL-HASH"   # real login untouched


@pytest.mark.asyncio
async def test_it_is_idempotent_and_never_duplicates(env):
    es, cm, db = env
    assert await es.ensure_master_employee(db) is True
    assert await es.ensure_master_employee(db) is False
    assert len(db.employees.rows) == 1


@pytest.mark.asyncio
async def test_no_master_means_nothing_happens(env):
    es, cm, db = env
    cm.config["users"] = [{"id": "u", "email": "host@x.com", "role": "host", "password_hash": "h"}]
    assert await es.ensure_master_employee(db) is False and db.employees.rows == []


@pytest.mark.asyncio
async def test_a_typed_password_can_never_replace_the_masters(env):
    es, cm, db = env
    await es.upsert_user_for_employee("Nick", "sellards@bighat.live", True, None, "Typed-Pass-1", "default")
    await es.upsert_user_for_employee("Nick", "SELLARDS@bighat.live ", True, None, None, "default")
    assert cm.config["users"][0]["password_hash"] == "REAL-HASH"
    assert len([u for u in cm.config["users"] if u["email"].lower().startswith("sellards")]) == 1


@pytest.mark.asyncio
async def test_password_reset_for_master_reports_not_changed(env):
    es, cm, db = env
    assert await es.set_user_password("sellards@bighat.live", "Reset-1234") is False
    assert cm.config["users"][0]["password_hash"] == "REAL-HASH"


@pytest.mark.asyncio
async def test_startup_sync_does_not_touch_the_master(env):
    es, cm, db = env
    made = await es.sync_all([{"name": "Nick", "email": "sellards@bighat.live", "is_admin": True}], "default")
    assert made == 0 and cm.config["users"][0]["password_hash"] == "REAL-HASH"
