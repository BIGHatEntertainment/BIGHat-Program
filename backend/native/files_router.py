"""User-files store for .bighat files (saved trivia rounds, bingo cards,
karaoke playlists, etc.). Lives outside the app bundle in the user's home
directory so files persist across installs and reinstalls.

On Windows:  %USERPROFILE%\\Documents\\BIGHat Entertainment\\Files
On macOS:    ~/Documents/BIGHat Entertainment/Files
On Linux:    ~/Documents/BIGHat Entertainment/Files

Files MUST end in `.bighat`. Overwrite is allowed (same filename replaces).
"""
from __future__ import annotations

import os
import platform
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

router = APIRouter(prefix="/api/native/files", tags=["native-files"])

MAX_FILE_BYTES = 50 * 1024 * 1024     # 50 MB hard cap


def _store_root() -> Path:
    """Resolve the on-disk folder for the current user, creating it if absent."""
    override = os.environ.get("BIGHAT_FILES_DIR")
    if override:
        root = Path(override).expanduser()
    else:
        home = Path.home()
        # Use Documents on Win/Mac; bare home folder on Linux fallback.
        docs = home / "Documents"
        base = docs if docs.exists() else home
        root = base / "BIGHat Entertainment" / "Files"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _safe_name(name: str) -> str:
    """Reject path-traversal / sneaky names. .bighat extension required."""
    name = name.strip()
    if not name or name.startswith(".") or "/" in name or "\\" in name or ".." in name:
        raise HTTPException(status_code=400, detail="invalid_filename")
    if not name.lower().endswith(".bighat"):
        raise HTTPException(status_code=400, detail="must_end_in_.bighat")
    if len(name) > 200:
        raise HTTPException(status_code=400, detail="filename_too_long")
    return name


@router.get("/folder")
async def files_folder() -> dict[str, Any]:
    """Return the absolute path of the .bighat files folder. Exposed so the
    UI can show 'Files saved to: <path>' to the user."""
    root = _store_root()
    return {
        "ok": True,
        "folder": str(root),
        "exists": root.exists(),
        "platform": platform.system(),
    }


@router.get("")
async def files_list() -> dict[str, Any]:
    """List every .bighat file in the store with size + mtime."""
    root = _store_root()
    items: list[dict[str, Any]] = []
    for p in sorted(root.glob("*.bighat"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            st = p.stat()
            items.append({
                "name": p.name,
                "size_bytes": st.st_size,
                "modified_at": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
            })
        except OSError:
            continue
    return {"ok": True, "folder": str(root), "count": len(items), "files": items}


@router.post("/upload")
async def files_upload(file: UploadFile = File(...)) -> dict[str, Any]:
    """Save a .bighat file to the user's store. Overwrites a same-named file."""
    name = _safe_name(file.filename or "")
    dest = _store_root() / name
    # Read with size cap to prevent runaway uploads.
    size = 0
    with dest.open("wb") as out:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_FILE_BYTES:
                out.close()
                dest.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="file_too_large_max_50MB")
            out.write(chunk)
    return {"ok": True, "name": name, "size_bytes": size, "path": str(dest)}


@router.get("/download/{name}")
async def files_download(name: str):
    name = _safe_name(name)
    p = _store_root() / name
    if not p.exists():
        raise HTTPException(status_code=404, detail="not_found")
    return FileResponse(path=str(p), filename=name, media_type="application/octet-stream")


@router.delete("/{name}")
async def files_delete(name: str) -> dict[str, Any]:
    name = _safe_name(name)
    p = _store_root() / name
    if not p.exists():
        raise HTTPException(status_code=404, detail="not_found")
    p.unlink()
    return {"ok": True, "deleted": name}
