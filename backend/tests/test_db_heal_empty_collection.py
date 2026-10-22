"""A zero-byte montydb collection file must not break the app ("OperationalError: no such table: documents").

Seen on a Mac: setup finished, the app was closed, and on the next start every login failed. montydb treats an existing
file as a real collection, and a hard kill between "create the file" and "create the table" leaves a 0-byte file.
The rule: heal 0-byte files (they hold nothing), NEVER touch a file that has data.
"""
import glob
import os
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from native import db_factory  # noqa: E402


def _fresh_repo(tmp_path):
    from montydb import MontyClient, set_storage
    repo = tmp_path / "bighat_db"
    set_storage(repository=str(repo), storage="sqlite", check_same_thread=False)
    return repo, MontyClient(str(repo))


def _col(repo, name):
    return glob.glob(str(repo / "*" / f"{name}.collection"))[0]


def test_empty_collection_file_breaks_reads_without_the_heal(tmp_path):
    """Proves the test setup reproduces the user's exact error (so the fix test below means something)."""
    repo, client = _fresh_repo(tmp_path)
    client["bighat"].users.insert_one({"email": "a@b.c"})
    open(_col(repo, "users"), "wb").close()                      # 0 bytes = half-created collection
    with pytest.raises(sqlite3.OperationalError, match="no such table: documents"):
        client["bighat"].users.find_one({})


def test_heal_repairs_an_empty_file_and_reads_work_again(tmp_path):
    repo, client = _fresh_repo(tmp_path)
    client["bighat"].users.insert_one({"email": "a@b.c"})
    open(_col(repo, "users"), "wb").close()
    out = db_factory.heal_empty_collections(repo)
    assert len(out["healed"]) == 1 and out["suspect"] == []
    assert client["bighat"].users.find_one({}) is None           # empty but valid: reads and writes work
    client["bighat"].users.insert_one({"email": "new@b.c"})
    assert client["bighat"].users.find_one({"email": "new@b.c"}) is not None


def test_heal_never_touches_a_file_that_has_data(tmp_path):
    repo, client = _fresh_repo(tmp_path)
    client["bighat"].users.insert_one({"email": "keep@me"})
    f = _col(repo, "users")
    before = Path(f).read_bytes()
    out = db_factory.heal_empty_collections(repo)
    assert out == {"healed": [], "suspect": []}
    assert Path(f).read_bytes() == before
    assert client["bighat"].users.find_one({"email": "keep@me"}) is not None


def test_non_empty_file_without_the_table_is_reported_and_left_alone(tmp_path):
    repo, client = _fresh_repo(tmp_path)
    client["bighat"].users.insert_one({"email": "x@y.z"})
    f = _col(repo, "users")
    con = sqlite3.connect(f)
    con.execute("DROP TABLE documents"); con.execute("CREATE TABLE other(a)"); con.commit(); con.close()
    before = Path(f).read_bytes()
    out = db_factory.heal_empty_collections(repo)
    assert out["healed"] == [] and len(out["suspect"]) == 1
    assert Path(f).read_bytes() == before                         # untouched: never "fix" a file that holds data


def test_heal_is_safe_on_missing_dir_and_idempotent(tmp_path):
    assert db_factory.heal_empty_collections(tmp_path / "nope") == {"healed": [], "suspect": []}
    repo, client = _fresh_repo(tmp_path)
    client["bighat"].users.insert_one({"a": 1})
    open(_col(repo, "users"), "wb").close()
    assert len(db_factory.heal_empty_collections(repo)["healed"]) == 1
    assert db_factory.heal_empty_collections(repo) == {"healed": [], "suspect": []}   # second run: nothing left to heal


def test_heal_never_raises_on_a_locked_or_odd_path(tmp_path, monkeypatch):
    repo, _ = _fresh_repo(tmp_path)
    (repo / "bighat").mkdir(exist_ok=True)
    (repo / "bighat" / "weird.collection").write_bytes(b"")
    monkeypatch.setattr(db_factory.sqlite3 if hasattr(db_factory, "sqlite3") else __import__("sqlite3"), "connect",
                        lambda *a, **k: (_ for _ in ()).throw(sqlite3.OperationalError("database is locked")))
    out = db_factory.heal_empty_collections(repo)                 # must not raise
    assert out["healed"] == []


def test_native_client_startup_heals_before_opening(tmp_path):
    """The real entry point, in a FRESH process (a restart has no cached connection): build the client on a folder that
    holds a 0-byte collection file, then WRITE. Without the heal, insert_one raises
    'OperationalError: no such table: documents' (reads alone are shimmed, so a write is the honest test)."""
    import subprocess
    probe = tmp_path / "probe.py"
    probe.write_text(
        "import os, sys, glob, asyncio\n"
        "sys.path.insert(0, %r)\n"
        "d = sys.argv[2]\n"
        "os.environ['BIGHAT_DB_DIR'] = d; os.environ.pop('MONTYDB_DATA_DIR', None)\n"
        "repo = os.path.join(d, 'bighat_db')\n"
        "if sys.argv[1] == 'seed':\n"
        "    from montydb import MontyClient, set_storage\n"
        "    set_storage(repository=repo, storage='sqlite', check_same_thread=False)\n"
        "    MontyClient(repo)['bighat'].users.insert_one({'e': 1})\n"
        "    open(glob.glob(repo + '/*/users.collection')[0], 'wb').close()\n"
        "else:\n"
        "    from native import db_factory\n"
        "    db = db_factory._build_native_client()['bighat']\n"
        "    loop = asyncio.new_event_loop()\n"
        "    loop.run_until_complete(db.users.insert_one({'email': 'new@b.c'}))\n"
        "    print('WROTE', loop.run_until_complete(db.users.find_one({'email': 'new@b.c'})) is not None)\n"
        % str(Path(__file__).resolve().parent.parent))
    data = tmp_path / "data"
    data.mkdir()
    subprocess.run([sys.executable, str(probe), "seed", str(data)], check=True, capture_output=True)
    r = subprocess.run([sys.executable, str(probe), "read", str(data)], capture_output=True, text=True)
    assert "WROTE True" in r.stdout, (r.stdout, r.stderr[-400:])


# ---- v32.1.5: the half-made file is 4096 bytes (montydb's settings only), not 0 bytes ----
def _tableless_file(repo, name):
    p = _col(repo, name)
    os.remove(p)
    con = sqlite3.connect(p)
    con.execute("PRAGMA journal_mode=WAL")      # what montydb writes on connect; makes the file non-empty, still no table
    con.close()
    with open(p, "ab") as fh:
        fh.write(b"")
    return p


def test_heal_repairs_a_nonzero_file_that_has_no_table(tmp_path):
    repo, client = _fresh_repo(tmp_path)
    client["bighat"].users.insert_one({"email": "a@b.c"})
    p = _tableless_file(repo, "users")
    out = db_factory.heal_empty_collections(repo)
    assert str(p) in out["healed"] and out["suspect"] == []
    client["bighat"].users.insert_one({"email": "new@b.c"})
    assert client["bighat"].users.find_one({"email": "new@b.c"}) is not None


def test_a_running_app_repairs_and_retries_a_tableless_file(tmp_path):
    """The exact login failure: insert_one on a table-less users file. The wrapper must repair it and succeed."""
    import asyncio
    from native import async_monty
    repo, client = _fresh_repo(tmp_path)
    client["bighat"].users.insert_one({"email": "a@b.c"})
    _tableless_file(repo, "users")
    async_monty.HEAL_HOOK = lambda: db_factory.heal_empty_collections(repo)
    try:
        col = async_monty.AsyncMontyClient(client)["bighat"].users
        asyncio.run(col.insert_one({"email": "caelie@x.com"}))
        assert asyncio.run(col.find_one({"email": "caelie@x.com"})) is not None
    finally:
        async_monty.HEAL_HOOK = None


def test_without_the_hook_the_tableless_file_still_fails(tmp_path):
    """Proves the retry test above can fail."""
    import asyncio
    from native import async_monty
    repo, client = _fresh_repo(tmp_path)
    client["bighat"].users.insert_one({"email": "a@b.c"})
    _tableless_file(repo, "users")
    async_monty.HEAL_HOOK = None
    col = async_monty.AsyncMontyClient(client)["bighat"].users
    with pytest.raises(sqlite3.OperationalError, match="no such table"):
        asyncio.run(col.insert_one({"email": "x@y.z"}))
