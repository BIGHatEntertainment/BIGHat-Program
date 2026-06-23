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
    """List every .bighat file in the store with size, mtime, and (for
    trivia content) a one-line summary parsed from the file's manifest."""
    root = _store_root()
    items: list[dict[str, Any]] = []
    for p in sorted(root.glob("*.bighat"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            st = p.stat()
            entry = {
                "name": p.name,
                "size_bytes": st.st_size,
                "modified_at": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
            }
            entry.update(_summarise_bighat(p))
            items.append(entry)
        except OSError:
            continue
    return {"ok": True, "folder": str(root), "count": len(items), "files": items}


def _summarise_bighat(path: Path) -> dict[str, Any]:
    """Read manifest.json + payload.json from the .bighat archive and
    surface a human-readable one-line summary. Trivia content gets a
    rich summary (rounds, questions, categories). Other content types
    just get a type label — they have flatter formats that don't benefit
    from custom parsing.

    Always returns a dict (`type`, optional `summary`); never raises.
    """
    import json
    import zipfile
    try:
        with zipfile.ZipFile(path, "r") as zf:
            names = set(zf.namelist())
            if "manifest.json" not in names:
                return {"type": "unknown"}
            manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
            content_type = str(manifest.get("type") or "unknown")
            out: dict[str, Any] = {"type": content_type}

            # Trivia gets the deep parse. Bingo + karaoke fall through with
            # just the type label — both have straightforward flat formats
            # where a custom summary line would add no real value.
            if content_type in ("round", "presentation", "pack") and "payload.json" in names:
                payload = json.loads(zf.read("payload.json").decode("utf-8"))
                out["summary"] = _trivia_summary(content_type, manifest, payload)
            elif content_type == "bingo":
                out["summary"] = "Bingo content"
            else:
                out["summary"] = content_type.replace("_", " ").capitalize() or "BIG Hat file"
            return out
    except (zipfile.BadZipFile, json.JSONDecodeError, KeyError, UnicodeDecodeError):
        return {"type": "unknown", "summary": "Unreadable archive"}


def _trivia_summary(content_type: str, manifest: dict, payload: dict) -> str:
    """Build a one-line description for trivia archives.

    Examples:
      "Round · 12 questions · 4 categories · tiebreaker · cover image"
      "Presentation · 4 rounds · 47 questions"
      "Pack · 5 rounds · author: Trivia Mafia"
    """
    bits: list[str] = []

    if content_type == "round":
        bits.append("Round")
        name = manifest.get("round_name") or payload.get("name") or payload.get("title")
        if name:
            bits.append(f'"{name}"')
        qs = payload.get("questions") or payload.get("items") or []
        if isinstance(qs, list) and qs:
            bits.append(f"{len(qs)} question{'s' if len(qs) != 1 else ''}")
        cats = set()
        for q in qs if isinstance(qs, list) else []:
            cat = (q or {}).get("category") or (q or {}).get("topic")
            if cat:
                cats.add(str(cat).strip())
        if len(cats) > 1:
            bits.append(f"{len(cats)} categories")
        elif len(cats) == 1:
            bits.append(f"category: {next(iter(cats))}")
        if payload.get("tiebreaker"):
            bits.append("tiebreaker")
        if payload.get("cover_image") or payload.get("cover_asset"):
            bits.append("cover image")
        rt = manifest.get("round_type") or payload.get("round_type")
        if rt:
            bits.append(f"type: {rt}")

    elif content_type == "presentation":
        bits.append("Presentation")
        rounds = payload.get("rounds") or []
        if isinstance(rounds, list):
            n_rounds = len(rounds)
            n_qs = sum(len(r.get("questions") or []) for r in rounds if isinstance(r, dict))
            if n_rounds:
                bits.append(f"{n_rounds} round{'s' if n_rounds != 1 else ''}")
            if n_qs:
                bits.append(f"{n_qs} questions")

    elif content_type == "pack":
        bits.append("Pack")
        items = payload.get("items") or payload.get("rounds") or []
        if isinstance(items, list) and items:
            bits.append(f"{len(items)} round{'s' if len(items) != 1 else ''}")
        author = manifest.get("author") or payload.get("author")
        if author:
            bits.append(f"by {author}")

    if manifest.get("signature"):
        bits.append("signed")

    return " · ".join(bits) if bits else "Trivia content"


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
