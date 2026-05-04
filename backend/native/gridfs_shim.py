"""
GridFS shim for native (MontyDB/SQLite) mode.

MontyDB has no GridFS, but the existing `gridfs_service.GridFSService` only
needs a `bucket` with these methods:

    upload_from_stream(filename, stream, metadata=...) -> file_id
    find(filter)  -> async cursor with `async for doc in cursor` and `.to_list(length)`
    open_download_stream(file_id) -> stream with `.read()` -> bytes
    delete(file_id) -> None

We back it with a single MontyDB collection (`slides_files`) where each doc
holds the full gzipped blob plus metadata. Documents are tiny (≤ 8MB after
compression — well within SQLite/MontyDB capacity), so chunking on top of
this layer (already done by GridFSService) is fine.

Used in native mode only. Webapp mode keeps the real motor GridFS bucket.
"""
from __future__ import annotations

import asyncio
import base64
import uuid
from typing import Any, Dict, List, Optional


def _new_id() -> str:
    return str(uuid.uuid4())


class _AsyncBytesStream:
    """Mimics motor's GridOut: has an async .read() returning all bytes."""

    def __init__(self, data: bytes):
        self._data = data

    async def read(self, size: int = -1) -> bytes:
        if size in (-1, None):
            return self._data
        chunk, self._data = self._data[:size], self._data[size:]
        return chunk


class _AsyncGridCursor:
    """Mimics motor's gridfs find() cursor: supports `async for` and to_list."""

    def __init__(self, docs: List[Dict[str, Any]]):
        self._docs = docs

    def __aiter__(self):
        self._iter = iter(self._docs)
        return self

    async def __anext__(self):
        sentinel = object()
        v = next(self._iter, sentinel)
        if v is sentinel:
            raise StopAsyncIteration
        return v

    async def to_list(self, length: Optional[int] = None) -> List[Dict[str, Any]]:
        if length is None:
            return list(self._docs)
        return list(self._docs[:length])


class NativeGridFSBucket:
    """Drop-in replacement for AsyncIOMotorGridFSBucket against an
    AsyncMontyDatabase. Stores blobs base64-encoded inside a normal collection.
    """

    def __init__(self, async_monty_db, bucket_name: str = "slides"):
        # The wrapped collection holds rows: {_id, filename, length, metadata, data_b64}
        self._coll = async_monty_db[f"{bucket_name}_files"]
        self._bucket_name = bucket_name

    # ----- Writes -----
    async def upload_from_stream(
        self,
        filename: str,
        source,
        metadata: Optional[Dict[str, Any]] = None,
        **_kwargs,
    ) -> str:
        # Accept BytesIO-like or raw bytes
        if hasattr(source, "read"):
            data = source.read()
        else:
            data = bytes(source)
        if isinstance(data, str):
            data = data.encode("utf-8")
        file_id = _new_id()
        doc = {
            "_id": file_id,
            "filename": filename,
            "length": len(data),
            "metadata": dict(metadata or {}),
            "data_b64": base64.b64encode(data).decode("ascii"),
        }
        await self._coll.insert_one(doc)
        return file_id

    async def delete(self, file_id) -> None:
        # Accept str or anything stringifiable; MongoDB ObjectIds become strings here
        fid = str(file_id)
        await self._coll.delete_one({"_id": fid})

    # ----- Reads -----
    def find(self, filt: Optional[Dict[str, Any]] = None) -> _AsyncGridCursor:
        # We must materialise sync because the upstream code uses both
        # `async for doc in cursor` (we satisfy) and `to_list` (we satisfy).
        # This means we run a blocking read inside an asyncio loop call.
        async def _gather() -> List[Dict[str, Any]]:
            docs = await self._coll.find(filt or {}).to_list(None)
            # Strip data_b64 from listing — callers only need _id/filename/metadata
            for d in docs:
                d.pop("data_b64", None)
            return docs

        # Schedule and block — the caller almost always wraps this in `async for`
        # which awaits each step; we return a cursor that has the docs ready.
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            # In an async context — return a cursor that lazily fetches on first iter
            return _LazyAsyncGridCursor(_gather)
        # Sync context (unusual path) — run directly
        return _AsyncGridCursor(asyncio.run(_gather()))

    async def open_download_stream(self, file_id) -> _AsyncBytesStream:
        fid = str(file_id)
        doc = await self._coll.find_one({"_id": fid})
        if not doc:
            raise FileNotFoundError(f"GridFS file {fid} not found")
        data = base64.b64decode(doc["data_b64"])
        return _AsyncBytesStream(data)


class _LazyAsyncGridCursor:
    """Same as _AsyncGridCursor but materialises on first await."""

    def __init__(self, gather_coro_factory):
        self._gather = gather_coro_factory
        self._docs: Optional[List[Dict[str, Any]]] = None

    async def _ensure(self) -> List[Dict[str, Any]]:
        if self._docs is None:
            self._docs = await self._gather()
        return self._docs

    def __aiter__(self):
        self._iter = None
        return self

    async def __anext__(self):
        if self._iter is None:
            docs = await self._ensure()
            self._iter = iter(docs)
        sentinel = object()
        v = next(self._iter, sentinel)
        if v is sentinel:
            raise StopAsyncIteration
        return v

    async def to_list(self, length: Optional[int] = None) -> List[Dict[str, Any]]:
        docs = await self._ensure()
        if length is None:
            return list(docs)
        return list(docs[:length])
