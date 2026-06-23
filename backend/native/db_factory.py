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

import os
from pathlib import Path
from typing import Optional

from .async_monty import AsyncMontyClient, AsyncMontyDatabase


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


def _build_native_client() -> AsyncMontyClient:
    """Build a MontyDB-backed sqlite client and async-wrap it."""
    from montydb import MontyClient, set_storage  # local import; only load when needed

    base_dir = Path(
        os.environ.get(
            "BIGHAT_DB_DIR",
            str(Path(__file__).resolve().parent / "data"),
        )
    )
    base_dir.mkdir(parents=True, exist_ok=True)
    repo_dir = base_dir / "bighat_db"
    set_storage(repository=str(repo_dir), storage="sqlite")
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
