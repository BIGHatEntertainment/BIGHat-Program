"""v32.4.0: the SECOND layer of the organization login's safety rules, called directly (the HTTP tests prove the first layer; these prove that
each rule still holds if an earlier check is ever changed)."""
import asyncio, importlib, sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tests"))
from test_cloud_sync import run   # noqa: E402
from test_cloud_files_pull import env as files_env   # noqa: E402,F401


@pytest.fixture
def env(files_env, monkeypatch):
    e = files_env
    from native import org_login, admin_router, employee_sync
    importlib.reload(org_login)
    e.ol, e.ar, e.es = org_login, admin_router, employee_sync
    monkeypatch.setattr(org_login.cloud_link, "get_token", lambda: "tok")
    return e


CLOUD = {"email": "sam@x.com", "name": "Sam Host", "role": "host", "is_admin": False, "phone": "1"}


def test_the_master_admin_is_never_sent_to_the_cloud_even_if_everything_else_says_yes(env):
    master = {"email": "owner@x.com", "role": "master_admin", "is_master": True, "auth_method": "cloud"}
    assert run(env.ol.should_ask_cloud(env.db, master, False)) is False and run(env.ol.should_ask_cloud(env.db, master, True)) is False
    master2 = {"email": "owner@x.com", "role": "master_admin", "auth_method": "cloud"}
    assert run(env.ol.should_ask_cloud(env.db, master2, False)) is False


def test_adopt_never_rewrites_a_hand_made_account(env):
    run(env.es.upsert_user_for_employee("Sam Host", "sam@x.com", False, None, "MyProgramPw1", ""))
    u = env.es.find_user("sam@x.com"); before = dict(u)
    out = run(env.ol.adopt(env.db, CLOUD, "CloudPw12345", u, False))
    assert out is u and u["password_hash"] == before["password_hash"] and u.get("auth_method", "local") == "local" and u["role"] == before["role"]


def test_adopt_never_touches_the_master_admin(env):
    m = env.es.find_user("owner@x.com")
    before = dict(m)
    assert run(env.ol.adopt(env.db, dict(CLOUD, email="owner@x.com"), "CloudPw12345", m, True)) is None
    assert m["password_hash"] == before["password_hash"] and m["role"] == "master_admin"


def test_adopt_with_no_copy_saves_nothing(env):
    n = len(env.ar.config_manager.config["users"])
    assert run(env.ol.adopt(env.db, CLOUD, "CloudPw12345", None, False)) is None
    assert len(env.ar.config_manager.config["users"]) == n


def test_adopt_copy_creates_a_cloud_account_with_a_bcrypt_hash_and_no_master_flag(env):
    import bcrypt
    u = run(env.ol.adopt(env.db, CLOUD, "CloudPw12345", None, True))
    assert u["auth_method"] == "cloud" and u["is_master"] is False and u["role"] == "host" and "password" not in u
    assert bcrypt.checkpw(b"CloudPw12345", u["password_hash"].encode())
    assert env.es.find_user("sam@x.com") is u or env.es.find_user("sam@x.com")["id"] == u["id"]


def test_adopt_updates_a_copied_account_to_the_clouds_role_and_password(env):
    import bcrypt
    u = run(env.ol.adopt(env.db, CLOUD, "FirstPw12345", None, True))
    u2 = run(env.ol.adopt(env.db, dict(CLOUD, role="admin", is_admin=True), "SecondPw12345", u, False))
    assert u2["role"] == "admin" and u2["is_admin"] is True and bcrypt.checkpw(b"SecondPw12345", u2["password_hash"].encode())


def test_an_unlinked_pc_never_asks_the_cloud(env, monkeypatch):
    monkeypatch.setattr(env.ol.cloud_link, "get_token", lambda: None)
    assert run(env.ol.should_ask_cloud(env.db, None, False)) is False
    assert run(env.ol.cloud_check("a@b.com", "x")) == {"ok": False, "error": "not_linked"}


@pytest.mark.parametrize("status,body,want", [
    (200, {"ok": True, "user": {"email": "A@B.com", "name": "A", "role": "host", "is_admin": False}}, "ok"),
    (200, {"ok": True, "user": {"email": "a@b.com", "name": "A", "role": "master_admin"}}, "invalid_credentials"),
    (200, {"ok": True, "user": {"email": "", "name": "A", "role": "host"}}, "invalid_credentials"),
    (200, {"ok": False}, "error"),
    (401, {"error": "invalid_credentials"}, "invalid_credentials"),
    (401, {"error": "unlinked"}, "unlinked"), (401, {"error": "unauthorized"}, "unlinked"),
    (403, {"error": "deactivated"}, "deactivated"), (429, {"error": "rate_limited"}, "rate_limited"),
    (402, {"error": "subscription_lapsed"}, "subscription_lapsed"), (500, {}, "unreachable"), (404, {}, "unreachable"),
])
def test_every_answer_the_cloud_can_give_is_understood(env, monkeypatch, status, body, want):
    import httpx
    class R:
        status_code = status
        def json(s): return body
    async def fake_post(self, url, json=None, headers=None): return R()
    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    monkeypatch.setattr(env.ol.cloud_link, "cloud_base_url", lambda: "https://cloud.test")
    out = run(env.ol.cloud_check("a@b.com", "pw"))
    assert (out["ok"] is True) == (want == "ok") and (out.get("error") == want or want == "ok")
    if want == "ok":
        assert out["user"]["email"] == "a@b.com" and out["user"]["role"] == "host"


def test_a_network_failure_is_unreachable_and_the_password_is_not_in_the_result(env, monkeypatch):
    import httpx
    async def boom(self, url, json=None, headers=None): raise httpx.ConnectError("down")
    monkeypatch.setattr(httpx.AsyncClient, "post", boom)
    monkeypatch.setattr(env.ol.cloud_link, "cloud_base_url", lambda: "https://cloud.test")
    out = run(env.ol.cloud_check("a@b.com", "SECRET-pw-1"))
    assert out == {"ok": False, "error": "unreachable"} and "SECRET" not in str(out)


def test_the_email_is_lower_cased_and_trimmed_before_it_is_sent(env, monkeypatch):
    import httpx
    sent = {}
    class R:
        status_code = 401
        def json(s): return {"error": "invalid_credentials"}
    async def fake_post(self, url, json=None, headers=None):
        sent.update(json=json, headers=headers); return R()
    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    monkeypatch.setattr(env.ol.cloud_link, "cloud_base_url", lambda: "https://cloud.test")
    run(env.ol.cloud_check("  Sam@X.COM ", "pw"))
    assert sent["json"] == {"email": "sam@x.com", "password": "pw"} and sent["headers"] == {"Authorization": "Bearer tok"}
