"""Local disk persistence helpers.

BIG Hat is a native desktop app — the end user's local disk is the
canonical source of truth (not ephemeral pod storage). All routers
persist through these helpers.
"""
from pathlib import Path

from fastapi import HTTPException


def write_local_bytes(path, data: bytes) -> int:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return len(data)


def write_local_text(path, text: str) -> int:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    return len(text)


async def stream_to_disk(path, read, max_bytes: int | None = None) -> int:
    """Stream chunks from an async `read(n)` callable to a local file."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    size = 0
    with p.open("wb") as out:
        while True:
            chunk = await read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if max_bytes is not None and size > max_bytes:
                out.close()
                p.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="file_too_large_max_50MB")
            out.write(chunk)
    return size
