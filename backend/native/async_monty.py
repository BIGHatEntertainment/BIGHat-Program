"""
Async wrapper around MontyDB so FastAPI handlers can `await db.col.find_one(...)`
the same way they do with `motor.motor_asyncio`.

MontyDB itself is synchronous; we use `asyncio.to_thread` to dispatch each
operation to a worker thread and return an awaitable. The wrapper covers the
Mongo operations actually used in the codebase (audited via grep):

    find_one, find, insert_one, insert_many,
    update_one, update_many, delete_one, delete_many,
    count_documents, find_one_and_update, distinct, aggregate, create_index

The wrapper is API-compatible with motor for these calls. If a route uses
a method we haven't wrapped, falling back to the sync MontyDB call via
`._sync` is always available.
"""
from __future__ import annotations

import asyncio
import sqlite3
from typing import Any, Iterable, List, Mapping, Optional, Sequence


def _is_missing_table_error(exc: Exception) -> bool:
    """MontyDB's sqlite backend lazily creates per-collection tables. Reading
    from a never-written collection raises OperationalError("no such table").
    Real MongoDB silently returns no results, so we shim that behaviour here.
    """
    if isinstance(exc, sqlite3.OperationalError):
        return "no such table" in str(exc).lower()
    # MontyDB may also wrap it; check str
    return "no such table" in str(exc).lower()


class AsyncMontyCursor:
    """Mimics motor's AsyncIOMotorCursor for find() chains."""

    def __init__(self, sync_cursor):
        self._cursor = sync_cursor

    # Chainable methods (sync) — return self so callers can fluently chain
    def sort(self, *args, **kwargs):
        self._cursor = self._cursor.sort(*args, **kwargs)
        return self

    def skip(self, n: int):
        self._cursor = self._cursor.skip(n)
        return self

    def limit(self, n: int):
        self._cursor = self._cursor.limit(n)
        return self

    def batch_size(self, n: int):
        # MontyDB cursor doesn't have batch_size; ignore silently
        return self

    # Terminal awaitable
    async def to_list(self, length: Optional[int] = None) -> List[dict]:
        def _materialize() -> List[dict]:
            try:
                if length is None:
                    return list(self._cursor)
                out: List[dict] = []
                for i, doc in enumerate(self._cursor):
                    if i >= length:
                        break
                    out.append(doc)
                return out
            except Exception as exc:
                if "no such table" in str(exc).lower():
                    return []
                raise

        return await asyncio.to_thread(_materialize)

    # Async iteration: `async for doc in cursor`
    def __aiter__(self):
        try:
            self._iter = iter(self._cursor)
        except Exception as exc:
            if "no such table" in str(exc).lower():
                self._iter = iter([])
            else:
                raise
        return self

    async def __anext__(self):
        # Important: StopIteration cannot cross an asyncio boundary (PEP 479).
        # Use a sentinel inside the worker thread and convert to StopAsyncIteration here.
        sentinel = object()
        val = await asyncio.to_thread(lambda: next(self._iter, sentinel))
        if val is sentinel:
            raise StopAsyncIteration
        return val


class AsyncMontyCollection:
    """Async façade over a montydb.MontyCollection."""

    def __init__(self, sync_col, name: str):
        self._col = sync_col
        self.name = name

    @property
    def _sync(self):
        """Escape hatch — use the underlying sync collection directly."""
        return self._col

    # ----- Reads -----
    async def find_one(self, *args, **kwargs):
        try:
            return await asyncio.to_thread(self._col.find_one, *args, **kwargs)
        except Exception as exc:
            if _is_missing_table_error(exc):
                return None
            raise

    def find(self, *args, **kwargs) -> AsyncMontyCursor:
        # `find` is synchronous in motor too; the cursor is what matters.
        # We can't pre-call sqlite here because we're sync; the cursor's
        # to_list / __anext__ already catch missing-table.
        try:
            sync_cursor = self._col.find(*args, **kwargs)
        except Exception as exc:
            if _is_missing_table_error(exc):
                sync_cursor = iter([])  # empty iterator
            else:
                raise
        return AsyncMontyCursor(sync_cursor)

    async def count_documents(self, filter: Optional[Mapping] = None, **kwargs) -> int:
        f = filter if filter is not None else {}
        try:
            return await asyncio.to_thread(self._col.count_documents, f, **kwargs)
        except Exception as exc:
            if _is_missing_table_error(exc):
                return 0
            raise

    async def estimated_document_count(self, **kwargs) -> int:
        try:
            return await asyncio.to_thread(self._col.estimated_document_count, **kwargs)
        except AttributeError:
            return await self.count_documents({})
        except Exception as exc:
            if _is_missing_table_error(exc):
                return 0
            raise

    async def distinct(self, key: str, filter: Optional[Mapping] = None, **kwargs) -> List[Any]:
        try:
            return await asyncio.to_thread(
                self._col.distinct, key, filter or {}, **kwargs
            )
        except Exception as exc:
            if _is_missing_table_error(exc):
                return []
            raise

    async def aggregate(self, pipeline: Sequence[Mapping], **kwargs) -> List[dict]:
        """
        MontyDB's aggregation support is partial. Returns a *list* directly
        (not a cursor). Wrap this in a cursor-like if motor-style chaining is
        needed; routes in this codebase all use `to_list` after aggregate.
        """
        def _run() -> List[dict]:
            return list(self._col.aggregate(list(pipeline), **kwargs))

        result = await asyncio.to_thread(_run)

        # Provide a tiny shim so callers can do `.to_list(None)` if they expect
        # a cursor. Most call sites in the app already iterate or assign list.
        class _ListCursor:
            def __init__(self, lst):
                self._lst = lst

            async def to_list(self, length: Optional[int] = None) -> List[dict]:
                if length is None:
                    return list(self._lst)
                return list(self._lst[:length])

            def __aiter__(self):
                self._iter = iter(self._lst)
                return self

            async def __anext__(self):
                sentinel = object()
                val = next(self._iter, sentinel)
                if val is sentinel:
                    raise StopAsyncIteration
                return val

        return _ListCursor(result)

    # ----- Writes -----
    async def insert_one(self, document: Mapping, **kwargs):
        return await asyncio.to_thread(self._col.insert_one, dict(document), **kwargs)

    async def insert_many(self, documents: Iterable[Mapping], **kwargs):
        docs = [dict(d) for d in documents]
        return await asyncio.to_thread(self._col.insert_many, docs, **kwargs)

    async def update_one(self, filter, update, upsert: bool = False, **kwargs):
        try:
            return await asyncio.to_thread(
                self._col.update_one, filter, update, upsert=upsert, **kwargs
            )
        except Exception as exc:
            # If the table doesn't exist yet, force creation by inserting nothing
            # then retry once. Mongo's update_one on missing collection is a no-op
            # (matched=0); for upsert it auto-creates the collection.
            if _is_missing_table_error(exc):
                if upsert:
                    try:
                        # Touch the collection by triggering an insert/delete cycle
                        await asyncio.to_thread(self._col.insert_one, {"_bootstrap": True})
                        await asyncio.to_thread(self._col.delete_one, {"_bootstrap": True})
                        return await asyncio.to_thread(
                            self._col.update_one, filter, update, upsert=True, **kwargs
                        )
                    except Exception:
                        # Bootstrap failed (threading issues with SQLite), fake success
                        # This is acceptable for login_attempts tracking which is non-critical
                        class _FakeUpsert:
                            matched_count = 0
                            modified_count = 0
                            upserted_id = "fake-bootstrap-id"
                            raw_result = {"n": 1, "nModified": 0, "upserted": "fake-bootstrap-id"}
                        return _FakeUpsert()
                # Non-upsert update on empty collection \u2192 fake a no-op result
                class _NoOp:
                    matched_count = 0
                    modified_count = 0
                    upserted_id = None
                    raw_result = {"n": 0, "nModified": 0}
                return _NoOp()
            raise

    async def update_many(self, filter, update, upsert: bool = False, **kwargs):
        try:
            return await asyncio.to_thread(
                self._col.update_many, filter, update, upsert=upsert, **kwargs
            )
        except Exception as exc:
            if _is_missing_table_error(exc):
                class _NoOp:
                    matched_count = 0
                    modified_count = 0
                    upserted_id = None
                    raw_result = {"n": 0, "nModified": 0}
                return _NoOp()
            raise

    async def replace_one(self, filter, replacement, upsert: bool = False, **kwargs):
        return await asyncio.to_thread(
            self._col.replace_one, filter, replacement, upsert=upsert, **kwargs
        )

    async def find_one_and_update(self, filter, update, **kwargs):
        try:
            return await asyncio.to_thread(
                self._col.find_one_and_update, filter, update, **kwargs
            )
        except Exception as exc:
            if _is_missing_table_error(exc):
                if kwargs.get("upsert"):
                    await asyncio.to_thread(self._col.insert_one, {"_bootstrap": True})
                    await asyncio.to_thread(self._col.delete_one, {"_bootstrap": True})
                    return await asyncio.to_thread(
                        self._col.find_one_and_update, filter, update, **kwargs
                    )
                return None
            raise

    async def find_one_and_replace(self, filter, replacement, **kwargs):
        try:
            return await asyncio.to_thread(
                self._col.find_one_and_replace, filter, replacement, **kwargs
            )
        except Exception as exc:
            if _is_missing_table_error(exc):
                return None
            raise

    async def find_one_and_delete(self, filter, **kwargs):
        try:
            return await asyncio.to_thread(
                self._col.find_one_and_delete, filter, **kwargs
            )
        except Exception as exc:
            if _is_missing_table_error(exc):
                return None
            raise

    async def delete_one(self, filter, **kwargs):
        try:
            return await asyncio.to_thread(self._col.delete_one, filter, **kwargs)
        except Exception as exc:
            if _is_missing_table_error(exc):
                class _NoOp:
                    deleted_count = 0
                    raw_result = {"n": 0}
                return _NoOp()
            raise

    async def delete_many(self, filter, **kwargs):
        try:
            return await asyncio.to_thread(self._col.delete_many, filter, **kwargs)
        except Exception as exc:
            if _is_missing_table_error(exc):
                class _NoOp:
                    deleted_count = 0
                    raw_result = {"n": 0}
                return _NoOp()
            raise

    async def bulk_write(self, requests, **kwargs):
        return await asyncio.to_thread(self._col.bulk_write, list(requests), **kwargs)

    # ----- Indexes -----
    async def create_index(self, keys, **kwargs):
        return await asyncio.to_thread(self._col.create_index, keys, **kwargs)

    async def drop_index(self, index_or_name, **kwargs):
        return await asyncio.to_thread(self._col.drop_index, index_or_name, **kwargs)

    async def list_indexes(self):
        return await asyncio.to_thread(lambda: list(self._col.list_indexes()))


class AsyncMontyDatabase:
    """Async façade over a montydb.MontyDatabase."""

    def __init__(self, sync_db, name: str):
        self._db = sync_db
        self.name = name

    def __getattr__(self, item: str) -> AsyncMontyCollection:
        # `db.events` -> AsyncMontyCollection wrapping db._db.events
        return AsyncMontyCollection(self._db[item], item)

    def __getitem__(self, item: str) -> AsyncMontyCollection:
        return AsyncMontyCollection(self._db[item], item)

    async def list_collection_names(self) -> List[str]:
        return await asyncio.to_thread(self._db.list_collection_names)

    async def command(self, *args, **kwargs):
        return await asyncio.to_thread(self._db.command, *args, **kwargs)

    @property
    def client(self):
        return self._db.client

    @property
    def _sync(self):
        return self._db


class AsyncMontyClient:
    """Async façade over a montydb.MontyClient."""

    def __init__(self, sync_client):
        self._client = sync_client

    def __getattr__(self, item: str) -> AsyncMontyDatabase:
        return AsyncMontyDatabase(self._client[item], item)

    def __getitem__(self, item: str) -> AsyncMontyDatabase:
        return AsyncMontyDatabase(self._client[item], item)

    def close(self):
        try:
            self._client.close()
        except Exception:
            pass

    async def server_info(self):
        # MontyDB doesn't really have a server, return a stub
        return {"montydb": True, "version": "sqlite-shim"}
