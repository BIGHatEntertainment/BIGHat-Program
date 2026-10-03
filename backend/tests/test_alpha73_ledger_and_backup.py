"""alpha.73: encrypted credential ledger in AppData, location safety copy, and the data map."""
import json, os, sys, shutil, time
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
HASH = "$2b$12$" + "a" * 53


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("BIGHAT_DATA_ROOT", str(tmp_path / "AppData"))
    monkeypatch.setenv("BIGHAT_FILES_DIR", str(tmp_path / "Docs"))
    import importlib
    from native import data_map, credential_ledger, locations_backup
    for m in (data_map, credential_ledger, locations_backup):
        importlib.reload(m)
    return tmp_path, data_map, credential_ledger, locations_backup


def test_ledger_is_in_appdata_not_documents_and_is_encrypted(env):
    t, dm, cl, lb = env
    cl.record("created", "Sam@X.com", role="host", password_hash=HASH, by="owner")
    led = t / "AppData" / "secure" / "credentials.ledger"
    assert led.is_file() and (t / "AppData" / "secure" / "ledger.key").is_file()
    raw = led.read_bytes()
    assert b"sam@x.com" not in raw and HASH.encode() not in raw and b"host" not in raw           # unreadable without the key
    assert not any("ledger" in str(p) for p in (t / "Docs").rglob("*")) if (t / "Docs").exists() else True


def test_ledger_refuses_a_readable_password(env):
    _, _, cl, _ = env
    with pytest.raises(ValueError):
        cl.record("created", "a@b.com", password_hash="MyPlainPassword1")


def test_history_never_shows_hashes_and_current_replays_changes(env):
    _, _, cl, _ = env
    cl.record("created", "a@b.com", role="host", password_hash=HASH)
    cl.record("role_changed", "a@b.com", role="admin")
    cl.record("password_set", "a@b.com", password_hash="$2b$12$" + "b" * 53)
    cl.record("created", "c@d.com", role="host", password_hash=HASH)
    cl.record("removed", "c@d.com")
    h = cl.history("A@B.com")
    assert [x["event"] for x in h] == ["created", "role_changed", "password_set"] and "password_hash" not in json.dumps(h)
    cur = cl.current()
    assert set(cur) == {"a@b.com"} and cur["a@b.com"]["role"] == "admin" and cur["a@b.com"]["password_hash"].endswith("b" * 53)


def test_tampering_is_detected(env):
    t, _, cl, _ = env
    for i in range(3):
        cl.record("created", f"u{i}@x.com", role="host", password_hash=HASH)
    assert cl.verify_chain() == {"ok": True, "events": 3}
    led = t / "AppData" / "secure" / "credentials.ledger"
    lines = led.read_bytes().splitlines()
    led.write_bytes(b"\n".join([lines[0], lines[2]]) + b"\n")                  # someone deletes the middle line
    assert cl.verify_chain()["ok"] is False
    led.write_bytes(b"\n".join(lines) + b"\ngarbage-not-encrypted\n")        # or appends junk
    assert cl.verify_chain()["ok"] is False
    assert len(cl.history()) >= 3                                              # and a damaged line never crashes reading


def test_a_copied_ledger_is_useless_without_the_key(env):
    t, _, cl, _ = env
    cl.record("created", "a@b.com", role="host", password_hash=HASH)
    stolen = t / "stolen.ledger"; shutil.copy(t / "AppData" / "secure" / "credentials.ledger", stolen)
    from cryptography.fernet import Fernet, InvalidToken
    other = Fernet(Fernet.generate_key())
    with pytest.raises(InvalidToken):
        other.decrypt(stolen.read_bytes().splitlines()[0])


def test_sync_from_config_records_only_what_changed(env):
    _, _, cl, _ = env
    users = [{"email": "o@x.com", "role": "master_admin", "password_hash": HASH}, {"email": "s@x.com", "role": "host", "password_hash": HASH}]
    assert cl.sync_from_config(users) == 2
    assert cl.sync_from_config(users) == 0                                    # saving again changes nothing
    users[1]["role"] = "admin"; users[1]["password_hash"] = "$2b$12$" + "z" * 53
    assert cl.sync_from_config(users) == 2                                    # password + role
    assert cl.sync_from_config(users[:1]) == 1                                # s@x.com removed
    assert [x["event"] for x in cl.history("s@x.com")] == ["created", "password_set", "role_changed", "removed"]
    assert cl.sync_from_config([{"email": "nohash@x.com", "role": "host"}]) == 1       # only the removal of o@x.com; a user with no hash is ignored
    assert cl.verify_chain()["ok"] is True


def test_restore_users_finds_users_the_config_lost(env):
    _, _, cl, _ = env
    cl.sync_from_config([{"email": "o@x.com", "role": "master_admin", "password_hash": HASH}, {"email": "s@x.com", "role": "host", "password_hash": HASH}])
    lost = cl.restore_users(["o@x.com"])
    assert [u["email"] for u in lost] == ["s@x.com"] and lost[0]["role"] == "host" and lost[0]["password_hash"] == HASH


def _make_loc(lb, slug="pub", n=2):
    base = lb.primary_root() / slug
    (base / "branding").mkdir(parents=True); (base / "overlays").mkdir()
    (base / "location.json").write_text(json.dumps({"name": "Pub", "slug": slug}))
    for i in range(n):
        (base / "branding" / f"b{i}.png").write_bytes(b"IMG" * 100 + bytes([i]))
    (base / "overlays" / "o0.png").write_bytes(b"OVR" * 50)
    return base


def test_mirror_copies_documents_to_appdata_and_only_changes(env):
    t, _, _, lb = env
    _make_loc(lb)
    assert lb.mirror("pub") == 4
    assert lb.mirror("pub") == 0                                              # nothing new
    assert (lb.backup_root() / "pub" / "branding" / "b1.png").read_bytes() == (lb.primary_root() / "pub" / "branding" / "b1.png").read_bytes()
    (lb.primary_root() / "pub" / "branding" / "b2.png").write_bytes(b"NEW")
    assert lb.mirror("pub") == 1
    assert lb.mirror("") == 0 and lb.mirror("nope") == 0


def test_restore_brings_back_a_lost_documents_folder_and_never_overwrites(env):
    t, _, _, lb = env
    base = _make_loc(lb); lb.mirror("pub")
    shutil.rmtree(lb.primary_root())                                          # Documents folder lost / moved / reset
    assert lb.restore_missing() == {"pub": 4}
    assert (base / "branding" / "b0.png").is_file() and (base / "location.json").is_file()
    (base / "branding" / "b0.png").write_bytes(b"EDITED")                     # a newer copy in Documents wins
    assert lb.restore_missing() == {}
    assert (base / "branding" / "b0.png").read_bytes() == b"EDITED"


def test_deleting_a_location_on_purpose_does_not_bring_it_back(env):
    t, _, _, lb = env
    base = _make_loc(lb); lb.mirror("pub")
    lb.remove("pub"); shutil.rmtree(base)
    assert lb.restore_missing() == {} and not (lb.primary_root() / "pub").exists()


def test_data_map_says_where_everything_lives_and_secrets_stay_in_appdata(env):
    t, dm, _, _ = env
    es = dm.entries()
    homes = {e["name"]: e["home"] for e in es}
    assert homes["Credential ledger (encrypted)"] == "appdata" and homes["Locations backup (copy of the images + settings)"] == "appdata"
    assert all(e["home"] == "appdata" for e in es if e["secret"])             # no secret ever lives in Documents
    assert all(str(t / "AppData") in e["path"] for e in es if e["home"] == "appdata")
    p = dm.write_map()
    assert p.parent == t / "AppData" and len(json.loads(p.read_text())["entries"]) == len(es)
