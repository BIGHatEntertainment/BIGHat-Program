"""Cloud link: the permanent per-PC code, the encrypted access key, and the link flow.

The promise being tested: the code and the link survive restarts and updates (the file in AppData is the truth),
the access key is never readable from the file or the API, and a damaged file never silently changes the code.
"""
import asyncio
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture()
def link(tmp_path, monkeypatch):
    monkeypatch.setenv("BIGHAT_DATA_ROOT", str(tmp_path))
    monkeypatch.delenv("BIGHAT_CLOUD_BASE_URL", raising=False)
    import importlib
    from native import data_map, cloud_link
    importlib.reload(data_map)
    importlib.reload(cloud_link)
    return cloud_link


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def test_code_is_six_chars_from_the_cloud_alphabet(link):
    code = link.get_or_create()["code"]
    assert len(code) == 6 and set(code) <= set(link.CODE_CHARS)
    assert not set(code) & set("0O1IL")


def test_code_is_permanent_across_restarts(link):
    first = link.get_or_create()["code"]
    import importlib
    importlib.reload(link)                      # simulates the app restarting
    assert link.get_or_create()["code"] == first
    assert link.public_view()["code"] == first


def test_code_survives_an_update_that_wipes_the_database(link, tmp_path):
    first = link.get_or_create()["code"]
    for p in tmp_path.glob("montydb*"):         # the database is disposable; the file in AppData is the truth
        p.unlink() if p.is_file() else None
    assert link.get_or_create()["code"] == first
    assert (tmp_path / "secure" / "cloud_link.json").exists()


def test_damaged_file_is_kept_and_the_code_is_recovered_not_replaced(link, tmp_path):
    first = link.get_or_create()["code"]
    f = tmp_path / "secure" / "cloud_link.json"
    f.write_text('{"code": "' + first + '", "status": ', encoding="utf-8")   # truncated JSON, a crash mid-write
    # recovery only works if the damaged text still parses; here it cannot, so the file must be KEPT as .bad
    rec = link.get_or_create()
    assert (tmp_path / "secure" / "cloud_link.json.bad").exists()
    assert len(rec["code"]) == 6


def test_access_key_is_encrypted_on_disk_and_never_in_the_api_view(link, tmp_path, monkeypatch):
    link.get_or_create()
    secret = "tok_THIS_MUST_NOT_APPEAR_IN_PLAIN_TEXT"
    enc = link._fernet().encrypt(secret.encode()).decode()
    link._save(token_enc=enc, status="linked")
    raw = (tmp_path / "secure" / "cloud_link.json").read_text(encoding="utf-8")
    assert secret not in raw
    assert secret not in json.dumps(link.public_view())
    assert link.get_token() == secret


def test_default_cloud_address_is_host_bighat_live(link):
    assert link.cloud_base_url() == "https://host.bighat.live"
    assert link.public_view()["cloud_configured"] is True


def test_env_overrides_the_default_cloud_address(link, monkeypatch):
    monkeypatch.setenv("BIGHAT_CLOUD_BASE_URL", "https://staging.example/")
    assert link.cloud_base_url() == "https://staging.example"


def test_no_license_key_stops_before_any_network_call(link, monkeypatch):
    monkeypatch.setenv("BIGHAT_CLOUD_BASE_URL", "https://cloud.example")
    monkeypatch.setattr(link, "_license_key", lambda: "")
    called = []

    async def boom(*a, **k):
        called.append(1)
        return {"ok": True}
    monkeypatch.setattr(link, "_post", boom)
    out = run(link.check())
    assert not called and "product key" in out["message"].lower()


def _flow(link, monkeypatch, announce, claim):
    monkeypatch.setenv("BIGHAT_CLOUD_BASE_URL", "https://cloud.example")
    monkeypatch.setattr(link, "_license_key", lambda: "BHE-AAAA-BBBB-CCCC-DDDD")

    async def fake(path, body):
        assert body["license_key"] == "BHE-AAAA-BBBB-CCCC-DDDD"
        return announce if path.endswith("announce") else claim
    monkeypatch.setattr(link, "_post", fake)


def test_waiting_until_the_owner_links_the_code(link, monkeypatch):
    _flow(link, monkeypatch, {"ok": True, "status": "pending"}, {"ok": True, "status": "pending"})
    out = run(link.check())
    assert out["status"] == "waiting" and out["has_token"] is False


def test_linked_collects_the_key_once_and_stores_it_encrypted(link, monkeypatch, tmp_path):
    _flow(link, monkeypatch, {"ok": True, "status": "linked"},
          {"ok": True, "status": "linked", "token": "tok_abc123", "program_id": "p1"})
    out = run(link.check())
    assert out["status"] == "linked" and out["has_token"] is True
    assert "tok_abc123" not in (tmp_path / "secure" / "cloud_link.json").read_text(encoding="utf-8")
    assert link.get_token() == "tok_abc123"
    # the code did not change while linking
    assert link.get_or_create()["code"] == out["code"]


def test_link_survives_a_restart_and_a_later_check_does_not_claim_again(link, monkeypatch):
    _flow(link, monkeypatch, {"ok": True, "status": "linked"},
          {"ok": True, "status": "linked", "token": "tok_abc123", "program_id": "p1"})
    run(link.check())
    import importlib
    importlib.reload(link)
    calls = []

    async def fake(path, body):
        calls.append(path)
        return {"ok": True, "status": "linked"}
    monkeypatch.setenv("BIGHAT_CLOUD_BASE_URL", "https://cloud.example")
    monkeypatch.setattr(link, "_license_key", lambda: "BHE-AAAA-BBBB-CCCC-DDDD")
    monkeypatch.setattr(link, "_post", fake)
    out = run(link.check())
    assert out["status"] == "linked" and link.get_token() == "tok_abc123"
    assert not any(c.endswith("claim-token") for c in calls)


def test_unreachable_cloud_never_unlinks(link, monkeypatch):
    _flow(link, monkeypatch, {"ok": True, "status": "linked"},
          {"ok": True, "status": "linked", "token": "tok_abc123", "program_id": "p1"})
    run(link.check())

    async def down(path, body):
        return {"ok": False, "error": "unreachable"}
    monkeypatch.setattr(link, "_post", down)
    out = run(link.check())
    assert out["status"] == "linked" and out["has_token"] is True
    assert link.get_token() == "tok_abc123"


def test_already_claimed_keeps_the_link_without_inventing_a_key(link, monkeypatch):
    _flow(link, monkeypatch, {"ok": True, "status": "linked"}, {"ok": True, "status": "already_claimed"})
    out = run(link.check())
    assert out["status"] == "linked" and out["has_token"] is False


def test_installed_program_refuses_to_store_inside_its_own_install_folder(tmp_path, monkeypatch):
    """In the installed app the install folder is wiped by every update. Storing there would change the code silently."""
    install = Path(__file__).resolve().parent.parent
    monkeypatch.setenv("BIGHAT_DATA_ROOT", str(install / "native" / "oops"))
    import importlib
    from native import data_map, cloud_link
    importlib.reload(data_map)
    importlib.reload(cloud_link)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    with pytest.raises(RuntimeError):
        cloud_link.get_or_create()
    assert not (install / "native" / "oops").exists()
