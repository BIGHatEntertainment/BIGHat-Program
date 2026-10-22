"""
Database factory: returns either motor (MongoDB) or AsyncMontyClient (SQLite)
based on the `BIGHAT_NATIVE_MODE` env var.

Usage:
    from native.db_factory import get_db, get_client
    db = get_db()
    await db.events.find_one({"_id": eid})

The factory caches the client globally so all imports share the same handle.
The SQLite database file lives at `BIGHAT_DB_DIR/bighat_db/` (a MontyDB
repository directory) which sits next to `system_config.json` in production.

DB name is read from env `DB_NAME` (same as the Mongo webapp), defaulting to
`bighat`. This means routes using `client[os.environ['DB_NAME']]` continue
to work unchanged.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

from .async_monty import AsyncMontyClient, AsyncMontyDatabase

logger = logging.getLogger("bighat-db-factory")


def _is_cloud_mode() -> bool:
    """Cloud mode always wins over native mode. Set on the cloud server pod
    (api.bighat.live) where MongoDB must be used for license persistence."""
    return os.environ.get("BIGHAT_CLOUD_MODE", "0") in ("1", "true", "True", "yes")


def _is_native_mode() -> bool:
    # If cloud mode is on, native mode is ignored — even when its env var is
    # set, the server uses MongoDB. This protects against an operator
    # accidentally leaving BIGHAT_NATIVE_MODE=1 on the cloud pod, which would
    # otherwise route every license through the container's ephemeral SQLite
    # file and lose every customer key on each Kubernetes redeploy.
    if _is_cloud_mode():
        return False
    return os.environ.get("BIGHAT_NATIVE_MODE", "0") in ("1", "true", "True", "yes")


def _db_name() -> str:
    return os.environ.get("DB_NAME", "bighat")


# Globals (lazy-initialised)
_native_client: Optional[AsyncMontyClient] = None
_motor_client = None  # AsyncIOMotorClient when not in native mode


# montydb stores each collection as its own SQLite file (<db>/<collection>.collection) with one table, "documents".
# A file that exists but has NO table (0 bytes) is treated by montydb as a real collection, and every read then fails
# with "OperationalError: no such table: documents". That is what a hard kill between "create file" and "create table"
# leaves behind (seen on a Mac after the app was closed once; the login then failed forever).
# A 0-byte file holds no data, so creating the table in it cannot lose anything. A NON-empty file is NEVER touched.
_EMPTY_COLLECTION_SQL = "CREATE TABLE IF NOT EXISTS [documents](k text NOT NULL, v text NOT NULL, PRIMARY KEY(k))"


def heal_empty_collections(repo_dir) -> dict:
    """Create the missing table in any zero-byte collection file under repo_dir. Never raises.

    Returns {"healed": [paths], "suspect": [paths]}. "suspect" = non-empty files without the table; left alone and logged.
    """
    import sqlite3

    out = {"healed": [], "suspect": []}
    try:
        base = Path(repo_dir)
        if not base.is_dir():
            return out
        for f in base.rglob("*.collection"):
            try:
                # A SQLite file with NO tables at all holds no rows, whatever its size (montydb leaves a 4096-byte
                # file with only its settings when it is stopped between "create file" and "create table"; 0 bytes too).
                # Creating the table in it cannot lose data. A file that has OTHER tables but no "documents" is left alone.
                con = sqlite3.connect(str(f))
                try:
                    tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
                    if "documents" in tables:
                        continue
                    if not tables:
                        with con:
                            con.execute(_EMPTY_COLLECTION_SQL)
                        out["healed"].append(str(f))
                        logger.warning("db heal: created the missing table in table-less collection file %s", f)
                    else:
                        out["suspect"].append(str(f))
                        logger.error("db heal: %s has other tables but no documents table. NOT touching it.", f)
                finally:
                    con.close()
            except Exception as e:  # one bad file must never stop the app from starting
                logger.error("db heal: could not check %s: %s", f, e)
    except Exception as e:
        logger.error("db heal failed: %s", e)
    return out



def _build_native_client() -> AsyncMontyClient:
    """Build a MontyDB-backed sqlite client and async-wrap it."""
    from montydb import MontyClient, set_storage  # local import; only load when needed

    # Persistence fix: launcher.py exports MONTYDB_DATA_DIR (=%LOCALAPPDATA%\\BIGHat\\data\\montydb)
    # but this factory only read BIGHAT_DB_DIR, so packaged builds fell back to a
    # folder beside the code (a per-launch temp dir) and data silently vanished.
    # Resolution order: BIGHAT_DB_DIR, then the parent of MONTYDB_DATA_DIR
    # (we append "bighat_db" ourselves), then the legacy in-repo dev path.
    _env_db = os.environ.get("BIGHAT_DB_DIR")
    if not _env_db and os.environ.get("MONTYDB_DATA_DIR"):
        _env_db = str(Path(os.environ["MONTYDB_DATA_DIR"]).parent)
    base_dir = Path(_env_db or str(Path(__file__).resolve().parent / "data"))
    base_dir.mkdir(parents=True, exist_ok=True)
    repo_dir = base_dir / "bighat_db"
    # alpha.90: the connection is used from worker threads, one call at a time (see async_monty._DB_LOCK)
    heal_empty_collections(repo_dir)          # before anything reads: repair half-made collection files
    from . import async_monty as _am
    _am.HEAL_HOOK = lambda: heal_empty_collections(repo_dir)   # same repair, if it happens while the app runs
    set_storage(repository=str(repo_dir), storage="sqlite", check_same_thread=False)
    sync_client = MontyClient(str(repo_dir))
    return AsyncMontyClient(sync_client)


def get_client():
    """Returns the active client. Motor in webapp mode, AsyncMontyClient native mode."""
    global _native_client, _motor_client
    if _is_native_mode():
        if _native_client is None:
            _native_client = _build_native_client()
        return _native_client
    # Webapp mode — keep using motor
    if _motor_client is None:
        from motor.motor_asyncio import AsyncIOMotorClient

        mongo_url = os.environ["MONGO_URL"]
        _motor_client = AsyncIOMotorClient(mongo_url)
    return _motor_client


def get_db():
    """Returns the active database object. Drop-in replacement for `db = client[name]`."""
    return get_client()[_db_name()]


def is_native() -> bool:
    return _is_native_mode()


def close_all() -> None:
    """Best-effort close on shutdown."""
    global _native_client, _motor_client
    if _native_client is not None:
        try:
            _native_client.close()
        except Exception:
            pass
        _native_client = None
    if _motor_client is not None:
        try:
            _motor_client.close()
        except Exception:
            pass
        _motor_client = None
