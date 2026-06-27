"""User-files store for .bighat files (saved trivia rounds, bingo cards,
karaoke playlists, etc.) AND host-scoped working data.

v32.0.0-alpha.18: typed subfolders + auto-migration.

Layout on disk:
    %USERPROFILE%\\Documents\\BIGHat Entertainment\\
      ├─ Files\\
      │    ├─ Rounds\\           ← trivia round .bighat files
      │    ├─ Bingo\\            ← bingo pack .bighat files
      │    ├─ Karaoke\\          ← karaoke playlist .bighat files
      │    └─ Other\\            ← unknown content_type fallback
      └─ Hosts\\<host_slug>\\    ← host-scoped event drafts, schedule
                                    snapshots, presenter notes

Why this exists:
  Before alpha.18 every .bighat dumped into a flat folder. The customer
  reported it was unusable — uploading works, but there's no way to find
  things again or organise by event type. We now route uploads to a
  subfolder by inspecting the archive's `type` field (`round`,
  `presentation`, `pack`, `bingo`, `karaoke`), with a one-shot migration
  that moves existing flat-layout files into their correct subfolders on
  first request.

Files MUST end in `.bighat`. Overwrite is allowed (same filename replaces).
"""
from __future__ import annotations

import json
import logging
import os
import platform
import re
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

logger = logging.getLogger("bighat-native-files")

router = APIRouter(prefix="/api/native/files", tags=["native-files"])

MAX_FILE_BYTES = 50 * 1024 * 1024     # 50 MB hard cap

# Allowed subfolder names. The keys are the URL-safe slugs the frontend
# sends in `?folder=`; the values are the on-disk folder names. Keeping
# them in sync (case + spelling) makes the URL → path mapping trivial.
SUBFOLDERS: tuple[str, ...] = ("Rounds", "Bingo", "Karaoke", "Other")
DEFAULT_SUBFOLDER = "Other"

# Map of content_type (from .bighat manifest.json) → subfolder.
# `round`, `presentation`, `pack` all relate to trivia → Rounds.
# `bingo` → Bingo. `karaoke` / `playlist` → Karaoke. Unknown → Other.
_TYPE_TO_FOLDER = {
    "round": "Rounds",
    "presentation": "Rounds",
    "pack": "Rounds",
    "bingo": "Bingo",
    "karaoke": "Karaoke",
    "playlist": "Karaoke",
}

_MIGRATION_DONE_MARKER = ".alpha18-migrated"


# ---------- Filesystem layout helpers ----------

def _base_root() -> Path:
    """Resolve the on-disk base for the current user (~/Documents/BIGHat...)."""
    override = os.environ.get("BIGHAT_FILES_DIR")
    if override:
        root = Path(override).expanduser()
    else:
        home = Path.home()
        docs = home / "Documents"
        base = docs if docs.exists() else home
        root = base / "BIGHat Entertainment" / "Files"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _hosts_root() -> Path:
    """Sibling of Files/ — per-host working data (event drafts, snapshots).
    Lives outside Files/ so it doesn't pollute the .bighat file listing
    but stays inside the same `BIGHat Entertainment` parent so a single
    backup captures everything."""
    files_root = _base_root()
    # Files/.. = BIGHat Entertainment/
    hosts = files_root.parent / "Hosts"
    hosts.mkdir(parents=True, exist_ok=True)
    return hosts


def _ensure_subfolders() -> None:
    """Idempotently create every typed subfolder. Cheap on every call."""
    root = _base_root()
    for name in SUBFOLDERS:
        (root / name).mkdir(parents=True, exist_ok=True)


def _resolve_folder(folder: str | None) -> tuple[str, Path]:
    """Validate `folder` against SUBFOLDERS, return (canonical_name, path).
    None / empty / "all" → return ("", base_root) which means "every
    subfolder, aggregated"."""
    if not folder or folder.lower() == "all":
        return "", _base_root()
    # Case-insensitive match against allow-list — never trust raw input.
    for name in SUBFOLDERS:
        if folder.lower() == name.lower():
            return name, _base_root() / name
    raise HTTPException(status_code=400, detail=f"invalid_folder: {folder!r}")


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


def _slug(s: str) -> str:
    """Filesystem-safe slug for the per-host working dir."""
    s = (s or "").strip().lower()
    s = re.sub(r"[^a-z0-9._-]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-._")
    return s or "host"


def _host_dir(host: str) -> Path:
    """Create-or-return the working dir for a specific host."""
    d = _hosts_root() / _slug(host)
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------- .bighat archive parsing ----------

def _summarise_bighat(path: Path) -> dict[str, Any]:
    """Read manifest.json + payload.json. Returns at minimum `type`."""
    try:
        with zipfile.ZipFile(path, "r") as zf:
            names = set(zf.namelist())
            if "manifest.json" not in names:
                return {"type": "unknown"}
            manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
            content_type = str(manifest.get("type") or "unknown")
            out: dict[str, Any] = {"type": content_type}
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
    bits: list[str] = []
    if content_type == "round":
        bits.append("Round")
        name = manifest.get("round_name") or payload.get("name") or payload.get("title")
        if name:
            bits.append(f'"{name}"')
        qs = payload.get("questions") or payload.get("items") or []
        if isinstance(qs, list) and qs:
            bits.append(f"{len(qs)} question{'s' if len(qs) != 1 else ''}")
        cats = {(q or {}).get("category") or (q or {}).get("topic") for q in qs if isinstance(q, dict)}
        cats.discard(None)
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


def _folder_for_path(path: Path) -> str:
    """Inspect a .bighat archive and pick the destination subfolder."""
    info = _summarise_bighat(path)
    content_type = str(info.get("type") or "").lower()
    return _TYPE_TO_FOLDER.get(content_type, DEFAULT_SUBFOLDER)


# ---------- One-shot migration: flat → typed subfolders ----------

def _migrate_flat_layout() -> int:
    """If the user has any .bighat files DIRECTLY in Files/ (legacy flat
    layout), move them into the right subfolder by inspecting each
    archive's content_type. Idempotent — runs once per install (guarded
    by a marker file)."""
    root = _base_root()
    marker = root / _MIGRATION_DONE_MARKER
    if marker.exists():
        return 0
    _ensure_subfolders()
    moved = 0
    for p in root.glob("*.bighat"):
        # Skip files that are already inside a subfolder — glob('*.bighat')
        # only yields direct children, so this is just defense in depth.
        if p.parent != root:
            continue
        try:
            target_subfolder = _folder_for_path(p)
            dest = root / target_subfolder / p.name
            # If a file of the same name already exists in the subfolder
            # (re-upload happened post-migration), keep the newer mtime.
            if dest.exists():
                if dest.stat().st_mtime >= p.stat().st_mtime:
                    p.unlink(missing_ok=True)
                    continue
                dest.unlink(missing_ok=True)
            p.rename(dest)
            moved += 1
        except OSError as e:
            logger.warning("migration skip %s: %s", p, e)
    try:
        marker.write_text(
            f"alpha.18 migration completed at "
            f"{datetime.now(timezone.utc).isoformat()}, moved={moved}\n",
            encoding="utf-8",
        )
    except OSError:
        pass
    if moved:
        logger.info("[native-files] migrated %d flat .bighat files into typed subfolders", moved)
    return moved


def _all_files_iter() -> Iterable[tuple[str, Path]]:
    """Walk every typed subfolder. Yields (subfolder_name, file_path) so
    callers can show the folder column without re-stat-ing the parent."""
    root = _base_root()
    for sub in SUBFOLDERS:
        sub_dir = root / sub
        if not sub_dir.exists():
            continue
        for p in sub_dir.glob("*.bighat"):
            yield sub, p


# ---------- HTTP routes ----------

@router.get("/folder")
async def files_folder() -> dict[str, Any]:
    """Return the absolute path of the base Files/ folder + list of
    typed subfolders + the Hosts/ root. Exposed so the UI can show
    'Files saved to: <path>'."""
    _ensure_subfolders()
    root = _base_root()
    return {
        "ok": True,
        "folder": str(root),
        "hosts_folder": str(_hosts_root()),
        "subfolders": list(SUBFOLDERS),
        "exists": root.exists(),
        "platform": platform.system(),
    }


@router.get("")
async def files_list(folder: str | None = None) -> dict[str, Any]:
    """List every .bighat file. With `?folder=Rounds` (etc) lists only
    that subfolder. Without a folder param, returns all files annotated
    with the subfolder they live in. Triggers the one-shot migration."""
    _ensure_subfolders()
    _migrate_flat_layout()

    items: list[dict[str, Any]] = []
    canonical, target = _resolve_folder(folder)

    if canonical:
        # Single-folder listing.
        for p in sorted(target.glob("*.bighat"), key=lambda x: x.stat().st_mtime, reverse=True):
            try:
                st = p.stat()
                entry = {
                    "name": p.name,
                    "folder": canonical,
                    "size_bytes": st.st_size,
                    "modified_at": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
                    "path": str(p),
                }
                entry.update(_summarise_bighat(p))
                items.append(entry)
            except OSError:
                continue
    else:
        # Aggregate listing across every subfolder.
        for sub, p in _all_files_iter():
            try:
                st = p.stat()
                entry = {
                    "name": p.name,
                    "folder": sub,
                    "size_bytes": st.st_size,
                    "modified_at": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
                    "path": str(p),
                }
                entry.update(_summarise_bighat(p))
                items.append(entry)
            except OSError:
                continue
        items.sort(key=lambda e: e["modified_at"], reverse=True)

    return {
        "ok": True,
        "folder": str(_base_root()),
        "selected_folder": canonical or "all",
        "subfolders": list(SUBFOLDERS),
        "count": len(items),
        "files": items,
    }


@router.post("/upload")
async def files_upload(
    file: UploadFile = File(...),
    folder: str | None = Form(default=None),
) -> dict[str, Any]:
    """Save a .bighat file. If `folder` is supplied (e.g. 'Rounds') the
    file goes there directly. Otherwise the archive's content_type is
    inspected to pick the right typed subfolder. Overwrites a same-named
    file IN THE SAME SUBFOLDER (but not across folders)."""
    _ensure_subfolders()
    name = _safe_name(file.filename or "")

    # Stage to base_root first so we can inspect the manifest to decide
    # the destination subfolder. If the caller specified a folder we
    # skip the auto-detect.
    base = _base_root()
    staged = base / f".staging-{name}"
    size = 0
    with staged.open("wb") as out:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_FILE_BYTES:
                out.close()
                staged.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="file_too_large_max_50MB")
            out.write(chunk)

    try:
        if folder:
            canonical, target_dir = _resolve_folder(folder)
        else:
            canonical = _folder_for_path(staged)
            target_dir = base / canonical
        target_dir.mkdir(parents=True, exist_ok=True)
        dest = target_dir / name
        if dest.exists():
            dest.unlink()
        staged.rename(dest)
    except HTTPException:
        staged.unlink(missing_ok=True)
        raise
    except OSError as e:
        staged.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"upload_failed: {e}")

    return {
        "ok": True,
        "name": name,
        "folder": canonical,
        "size_bytes": size,
        "path": str(dest),
    }


@router.get("/download/{name}")
async def files_download(name: str, folder: str | None = None):
    """Download a .bighat file. `folder` is optional — if omitted, we
    search every typed subfolder for the first match (backwards-compat
    with pre-alpha.18 callers that don't supply a folder)."""
    _ensure_subfolders()
    name = _safe_name(name)
    p = _locate(name, folder)
    return FileResponse(path=str(p), filename=name, media_type="application/octet-stream")


@router.delete("/{name}")
async def files_delete(name: str, folder: str | None = None) -> dict[str, Any]:
    """Delete a .bighat file. Folder optional — same lookup semantics as
    download."""
    _ensure_subfolders()
    name = _safe_name(name)
    p = _locate(name, folder)
    p.unlink()
    return {"ok": True, "deleted": name, "folder": p.parent.name}


@router.post("/reveal")
async def files_reveal(name: str | None = Form(default=None),
                       folder: str | None = Form(default=None)) -> dict[str, Any]:
    """Open the host OS file manager focused on a file (or its containing
    folder if `name` is omitted). Native-only — does nothing useful when
    the FastAPI sidecar runs headlessly inside a server. Best-effort."""
    if name:
        name = _safe_name(name)
        target = _locate(name, folder)
    else:
        _, target = _resolve_folder(folder)
    system = platform.system()
    try:
        if system == "Windows":
            # /select, highlights the file in Explorer.
            if target.is_file():
                subprocess.Popen(["explorer", "/select,", str(target)])
            else:
                subprocess.Popen(["explorer", str(target)])
        elif system == "Darwin":
            if target.is_file():
                subprocess.Popen(["open", "-R", str(target)])
            else:
                subprocess.Popen(["open", str(target)])
        else:
            subprocess.Popen(["xdg-open", str(target if target.is_dir() else target.parent)])
        return {"ok": True, "opened": str(target)}
    except (FileNotFoundError, OSError) as e:
        # Headless environments raise FileNotFoundError on `explorer` etc.
        # Don't 500 — the UI should just show a soft warning.
        return {"ok": False, "error": f"reveal_unavailable: {e}", "path": str(target)}


def _locate(name: str, folder: str | None) -> Path:
    """Helper: resolve a file by name (+ optional folder hint) to its
    absolute path. 404s if not found in any subfolder."""
    if folder:
        _, target_dir = _resolve_folder(folder)
        p = target_dir / name
        if p.exists():
            return p
        raise HTTPException(status_code=404, detail="not_found")
    # No folder hint — search every typed subfolder + base root (for
    # files that haven't been migrated yet).
    for sub in SUBFOLDERS:
        p = _base_root() / sub / name
        if p.exists():
            return p
    # Last-ditch: pre-migration flat layout.
    p = _base_root() / name
    if p.exists():
        return p
    raise HTTPException(status_code=404, detail="not_found")


# ---------- Host working-dir endpoints (event drafts, snapshots) ----------

@router.get("/hosts/{host}/list")
async def host_files_list(host: str) -> dict[str, Any]:
    """List every file in a host's working folder.
    `host` is typically the host's email or username; it's slugified to
    a filesystem-safe name."""
    d = _host_dir(host)
    items = []
    for p in sorted(d.glob("*"), key=lambda x: x.stat().st_mtime, reverse=True):
        if not p.is_file():
            continue
        st = p.stat()
        items.append({
            "name": p.name,
            "size_bytes": st.st_size,
            "modified_at": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
            "path": str(p),
        })
    return {"ok": True, "host": host, "folder": str(d), "count": len(items), "files": items}
