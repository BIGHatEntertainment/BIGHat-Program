"""
Backup service (v32.0.0-alpha.22).

Zips the merchant's per-install state — `system_config.json`, the
MontyDB store, `.env` secrets, asset folders — to a dated zip under
`~/Documents/BIG Hat Entertainment/Backups/` so any setup data can
survive a hard-drive crash, machine swap, or user error.

Triggered two ways:
  1. Automatically on every app startup (background task — see
     `server.py` lifespan).
  2. Manually from the dashboard's "Backup my setup" button which
     hits `POST /api/native/backup/run`.

Design choices that matter
--------------------------
* **One zip per calendar day.** If the merchant restarts the app
  three times in a day, the third backup just overwrites the first
  (atomic rename). Keeps disk usage predictable and the folder tidy.
* **Retention: keep last 14 dated zips.** Older files get pruned at
  the end of each run. The merchant gets ~2 weeks of point-in-time
  history without unbounded growth.
* **Atomic write.** Write to `bighat-backup-YYYY-MM-DD.zip.tmp` then
  `os.replace()` into place — never leave a half-written zip behind
  if the machine loses power mid-backup.
* **Best-effort, never crash.** A failed backup logs and returns an
  error dict but never raises into the FastAPI lifespan or the
  request handler. Losing one daily backup is a non-event.
* **Locked-file resilience.** MontyDB writes are short-lived
  fsyncs; we just iterate the tree with `shutil.make_archive` /
  `zipfile.ZipFile.write`. If a file is locked we skip it with a
  warning rather than failing the whole backup.
"""
from __future__ import annotations

import logging
import os
import sys
import threading
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Filenames we DO NOT want bundled into the backup, no matter where they live.
_EXCLUDED_NAMES = {
    ".DS_Store",
    "Thumbs.db",
}

# Subdirectory names (relative to the data root) we skip entirely.
_EXCLUDED_DIRS = {
    "Backups",          # the backup folder itself — never recurse into self
    "__pycache__",
    "tmp",
    "staging",          # update download staging — recreate on next update
}

# Default retention — keep the last N daily zips.
_DEFAULT_KEEP = 14


@dataclass
class BackupResult:
    ok: bool
    path: Optional[str]
    size: int
    files: int
    skipped: int
    timestamp: str
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "path": self.path,
            "size": self.size,
            "files": self.files,
            "skipped": self.skipped,
            "timestamp": self.timestamp,
            "error": self.error,
        }


def default_backups_dir() -> Path:
    """Where backups land. Lives UNDER the same `BIGHat Entertainment`
    root that holds the merchant's `.bighat` files folder so there's
    ONE Documents folder per app — Files + Backups as siblings — rather
    than two near-identical "BIG Hat Entertainment" / "BIGHat
    Entertainment" folders side-by-side.

    Windows:  C:\\Users\\<user>\\Documents\\BIGHat Entertainment\\Backups
    macOS:    ~/Documents/BIGHat Entertainment/Backups
    """
    override = os.environ.get("BIGHAT_BACKUPS_DIR")
    if override:
        return Path(override).expanduser().resolve()
    docs = Path.home() / "Documents"
    return docs / "BIGHat Entertainment" / "Backups"


def default_source_dir() -> Path:
    """The per-install state root. Mirrors `launcher._user_data_dir()`
    so we back up the same tree the launcher seeds — `system_config.json`,
    `.env`, `montydb/`, assets, generated, logs.
    """
    override = os.environ.get("BIGHAT_DATA_ROOT_FOR_BACKUP")
    if override:
        return Path(override).expanduser().resolve()
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "BIGHat" / "data"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "BIGHat" / "data"
    return Path.home() / ".local" / "share" / "BIGHat" / "data"


# A module-level lock + flag prevents two concurrent backups from
# stepping on each other (e.g. the startup auto-run AND a quick manual
# click). Only one writer at a time; subsequent callers get a "busy".
_lock = threading.Lock()
_in_progress = False


def is_running() -> bool:
    return _in_progress


def _backup_filename_for(day: datetime) -> str:
    return f"bighat-backup-{day.strftime('%Y-%m-%d')}.zip"


def _iter_files(source: Path) -> List[Path]:
    """List every file we want to include, relative to `source`."""
    out: List[Path] = []
    for root, dirs, files in os.walk(source):
        # Mutate dirs in-place so os.walk skips excluded subtrees entirely.
        dirs[:] = [d for d in dirs if d not in _EXCLUDED_DIRS]
        for name in files:
            if name in _EXCLUDED_NAMES:
                continue
            out.append(Path(root) / name)
    return out


def run_backup(
    source: Optional[Path] = None,
    dest_dir: Optional[Path] = None,
    keep: int = _DEFAULT_KEEP,
) -> BackupResult:
    """Run a single backup. Idempotent for the current calendar day —
    re-running on the same day overwrites the existing zip.
    """
    global _in_progress

    src = (source or default_source_dir()).resolve()
    dst = (dest_dir or default_backups_dir()).resolve()
    now = datetime.now(timezone.utc).astimezone()

    if not src.is_dir():
        msg = f"source_missing:{src}"
        logger.warning("backup: %s — nothing to back up", msg)
        return BackupResult(False, None, 0, 0, 0, now.isoformat(), msg)

    # Single-writer guard. We hold the lock for the whole run; the
    # acquire is non-blocking so a second caller gets `busy` instead of
    # queueing forever.
    if not _lock.acquire(blocking=False):
        return BackupResult(False, None, 0, 0, 0, now.isoformat(), "busy")

    _in_progress = True
    try:
        dst.mkdir(parents=True, exist_ok=True)
        zip_path = dst / _backup_filename_for(now)
        tmp_path = zip_path.with_suffix(".zip.tmp")
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass

        files = _iter_files(src)
        n_added = 0
        n_skipped = 0
        try:
            with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
                for f in files:
                    arcname = str(f.relative_to(src))
                    try:
                        zf.write(f, arcname=arcname)
                        n_added += 1
                    except (OSError, PermissionError) as e:
                        # Locked file (live MontyDB write, antivirus lock,
                        # etc.) — skip with a warning, do NOT fail the
                        # whole backup. Losing a single file is much less
                        # bad than losing the entire daily snapshot.
                        logger.warning("backup: skipped %s: %s", arcname, e)
                        n_skipped += 1
            os.replace(tmp_path, zip_path)  # atomic publish
        except Exception as exc:
            # Clean up the partial tmp so the folder stays tidy.
            try:
                if tmp_path.exists():
                    tmp_path.unlink()
            except OSError:
                pass
            logger.error("backup: failed: %s", exc, exc_info=True)
            return BackupResult(False, None, 0, n_added, n_skipped, now.isoformat(), str(exc))

        # Retention.
        try:
            cleanup_old_backups(dst, keep=keep)
        except Exception as exc:
            # Retention failure shouldn't poison the result — the
            # primary value (today's backup) IS on disk.
            logger.warning("backup: cleanup failed: %s", exc)

        size = zip_path.stat().st_size
        logger.info("backup: wrote %s (%d files, %d skipped, %d bytes)",
                    zip_path, n_added, n_skipped, size)
        return BackupResult(
            ok=True,
            path=str(zip_path),
            size=size,
            files=n_added,
            skipped=n_skipped,
            timestamp=now.isoformat(),
        )
    finally:
        _in_progress = False
        _lock.release()


def cleanup_old_backups(dest_dir: Path, keep: int = _DEFAULT_KEEP) -> int:
    """Delete all but the most-recent `keep` dated backups.

    Returns the number of files removed.

    We only match `bighat-backup-YYYY-MM-DD.zip` files (NOT `.tmp`,
    NOT arbitrary user zips in the same folder) so a paranoid merchant
    can drop their own archives there without losing them.
    """
    pattern = "bighat-backup-*.zip"
    candidates: List[Path] = sorted(
        [p for p in dest_dir.glob(pattern) if not p.name.endswith(".tmp")],
        key=lambda p: p.name,
        reverse=True,        # newest first by lexicographic date sort
    )
    to_remove = candidates[keep:]
    removed = 0
    for p in to_remove:
        try:
            p.unlink()
            removed += 1
        except OSError as e:
            logger.warning("backup: could not delete %s: %s", p, e)
    return removed


def list_backups(dest_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    """List existing daily backups, newest first."""
    dst = (dest_dir or default_backups_dir()).resolve()
    if not dst.is_dir():
        return []
    out: List[Dict[str, Any]] = []
    for p in sorted(dst.glob("bighat-backup-*.zip"), key=lambda x: x.name, reverse=True):
        try:
            st = p.stat()
        except OSError:
            continue
        out.append({
            "name": p.name,
            "path": str(p),
            "size": st.st_size,
            "mtime": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
        })
    return out
