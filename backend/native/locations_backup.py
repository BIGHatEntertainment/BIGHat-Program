"""alpha.73: a second copy of every location (settings + branding + overlay images) in AppData, so images are never
silently lost when the Documents folder is missing, moved, or reset (OneDrive redirect, new PC folder, update).

  Documents\\BIG Hat Entertainment\\Files\\Locations\\<slug>\\...      the copy the merchant sees (primary)
  <AppData>\\backups\\locations\\<slug>\\...                          the safety copy (this module)

Rules:
  * mirror() copies Documents -> AppData after every change (only files that are new or changed).
  * restore_missing() copies AppData -> Documents for anything missing there (never overwrites a newer Documents file).
  * Nothing is ever deleted from the backup by a Documents-side loss.  A location the merchant DELETES is removed from both.
"""
from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Dict, List

from native import data_map

logger = logging.getLogger(__name__)
_SKIP = (".tmp", ".part")


def primary_root() -> Path:
    return data_map.docs_root() / "Locations"


def backup_root() -> Path:
    return data_map.locations_backup_dir()


def _files(folder: Path) -> List[Path]:
    out: List[Path] = []
    try:
        for f in folder.rglob("*"):
            if f.is_file() and not f.name.endswith(_SKIP) and not f.name.startswith("."):
                out.append(f)
    except OSError:
        pass
    return out


def _copy_if_newer(src: Path, dst: Path) -> bool:
    try:
        if dst.exists() and dst.stat().st_size == src.stat().st_size and dst.stat().st_mtime >= src.stat().st_mtime:
            return False
        dst.parent.mkdir(parents=True, exist_ok=True)
        tmp = dst.with_name(dst.name + ".part")
        shutil.copy2(src, tmp)
        tmp.replace(dst)
        return True
    except OSError as exc:
        logger.warning("[locations-backup] could not copy %s: %s", src, exc)
        return False


def mirror(slug: str) -> int:
    """Documents -> AppData for one location.  Returns files copied.  Never raises."""
    src = primary_root() / slug
    if not slug or not src.is_dir():
        return 0
    n = 0
    for f in _files(src):
        if _copy_if_newer(f, backup_root() / slug / f.relative_to(src)):
            n += 1
    return n


def remove(slug: str) -> None:
    """The merchant deleted the location on purpose: drop the safety copy too."""
    try:
        shutil.rmtree(backup_root() / slug, ignore_errors=True)
    except OSError:
        pass


def restore_missing() -> Dict[str, int]:
    """AppData -> Documents for anything that is missing there.  Run at startup.  Never overwrites a Documents file."""
    restored: Dict[str, int] = {}
    root = backup_root()
    if not root.is_dir():
        return restored
    for slug_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        n = 0
        for f in _files(slug_dir):
            dst = primary_root() / slug_dir.name / f.relative_to(slug_dir)
            if not dst.exists():
                try:
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    tmp = dst.with_name(dst.name + ".part")
                    shutil.copy2(f, tmp)
                    tmp.replace(dst)
                    n += 1
                except OSError as exc:
                    logger.warning("[locations-backup] could not restore %s: %s", f, exc)
        if n:
            restored[slug_dir.name] = n
    if restored:
        logger.warning("[locations-backup] restored %s file(s) from the AppData safety copy: %s", sum(restored.values()), restored)
    return restored


def slugs_with_backup() -> List[str]:
    root = backup_root()
    return sorted(p.name for p in root.iterdir() if p.is_dir()) if root.is_dir() else []
