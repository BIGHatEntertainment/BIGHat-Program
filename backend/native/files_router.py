"""User-files store for .bighat files (saved trivia rounds, bingo cards,
karaoke playlists, etc.) AND host-scoped working data.

v32.0.0-alpha.18: typed subfolders + auto-migration.
v32.0.0-alpha.26: rename Rounds→Trivia, subdivide Trivia by round_type,
                  unify "BIG Hat Entertainment" / "BIGHat Entertainment"
                  into a single canonical "BIG Hat Entertainment" root.

Layout on disk (alpha.26+):
    %USERPROFILE%\\Documents\\BIG Hat Entertainment\\
      ├─ Files\\
      │    ├─ Trivia\\           ← trivia round .bighat files, split by
      │    │    ├─ MC\\          ← multiple-choice rounds
      │    │    ├─ REG\\         ← general (regular) rounds
      │    │    ├─ MISC\\        ← miscellaneous rounds
      │    │    ├─ MYS\\         ← mystery rounds
      │    │    └─ BIG\\         ← big rounds
      │    ├─ Bingo\\            ← bingo pack .bighat files
      │    ├─ Karaoke\\          ← karaoke playlist .bighat files
      │    └─ Other\\            ← unknown content_type fallback
      ├─ Backups\\               ← auto + manual backup zips
      └─ Hosts\\<host_slug>\\    ← host-scoped event drafts, schedule
                                    snapshots, presenter notes

Why the Trivia/<round_type>/ split:
  The merchant reported that Build Wizard / Round Roulette were
  pulling random round types when assembling a presentation, because
  every .bighat round file lived in a single flat "Rounds" folder
  with no way to filter by type. Splitting at the filesystem level
  means the wizard can request, e.g. "give me 2 MC and 3 REG", and
  scan only those two subdirectories deterministically.

Why one canonical "BIG Hat Entertainment" root:
  Pre-alpha.26 two adjacent folders ("BIG Hat Entertainment" with a
  space, "BIGHat Entertainment" without) accumulated content from
  different code paths (installer, backup service, files router).
  The merchant couldn't tell which was the real one. Canonical is
  now WITH SPACE — matches the productName in tauri.conf.json, the
  Cargo description, the installer shortcuts, and every brand asset.

Files MUST end in `.bighat`. Overwrite is allowed (same filename replaces).
"""
from __future__ import annotations

import json
import logging
import os
import platform
import re
import shutil
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

# Canonical brand name used as the Documents subfolder. Must match
# `tauri.conf.json` productName + the installer "App Name". See module
# docstring for why we standardised on the spaced form.
APP_DOCS_FOLDER = "BIG Hat Entertainment"
# Legacy aliases that we attempt to merge into the canonical folder on
# startup. Order matters: aliases are processed top-down, each migrated
# into APP_DOCS_FOLDER and then removed (when empty) so the merchant
# stops seeing duplicate sibling folders.
LEGACY_DOCS_FOLDER_ALIASES: tuple[str, ...] = (
    "BIGHat Entertainment",   # alpha.18 → alpha.25 backup_service / files_router
    "BH Entertainment",       # pre-alpha.18 short form, if any old installs linger
)

# Allowed top-level subfolder names inside Files/. The keys are the
# URL-safe slugs the frontend sends in `?folder=`; the values are the
# on-disk folder names. Keeping them in sync (case + spelling) makes
# the URL → path mapping trivial.
#
# v32.0.0-alpha.27: `Files/` now also hosts the host-scoped working
# data (`Hosts/`), location media (`Locations/`), and scoreboard JSON
# blobs (`Scoreboard/`).
# v32.0.0-alpha.28: added `Schedule/` for event scheduling data with
# `Location Prices/`, `Events/`, and an `Archive/` for previous
# months. Trivia gained a `Rounds/` subfolder for presentation JSON
# files consumed by both the Trivia Presenter AND the Story Generator.
SUBFOLDERS: tuple[str, ...] = (
    "Trivia",
    "Bingo",
    "Karaoke",
    "Hosts",
    "Locations",
    "Scoreboard",
    "Schedule",
    "Other",
)
DEFAULT_SUBFOLDER = "Other"

# Whitelist of subfolder names allowed to live directly under the
# canonical "BIG Hat Entertainment" Documents root. The legacy-folder
# merger refuses to copy ANY other top-level child across — that's how
# we prevent stray `backend/` directories from dev installs / older
# alpha packagers ending up in the merchant's Documents tree.
ALLOWED_DOCS_CHILDREN: frozenset[str] = frozenset({
    "Files",     # user data tree (the one this router manages)
    "Backups",   # backup_service.py writes here
})

# Round-type subdirectories under Files/Trivia/. Mirrors the codes the
# Round Maker uses (`MC`, `REG`, `MISC`, `MYS`, `BIG`) plus a `_Other`
# catchall for round .bighat files that arrive without a recognisable
# round_type (e.g. external generators that haven't been updated).
TRIVIA_ROUND_TYPES: tuple[str, ...] = ("MC", "REG", "MISC", "MYS", "BIG")
TRIVIA_DEFAULT_ROUND_TYPE = "_Other"

# Map of content_type (from .bighat manifest.json) → top-level subfolder.
# `round`, `presentation`, `pack` all relate to trivia → Trivia. `bingo`
# → Bingo. `karaoke` / `playlist` → Karaoke. Unknown → Other.
_TYPE_TO_FOLDER = {
    "round": "Trivia",
    "presentation": "Trivia",
    "pack": "Trivia",
    "bingo": "Bingo",
    "karaoke": "Karaoke",
    "playlist": "Karaoke",
}

# Older marker (alpha.18) — still respected so we don't redo the flat
# layout migration. The alpha.26 layout migration uses its own marker.
_MIGRATION_DONE_MARKER = ".alpha18-migrated"
_LAYOUT_MIGRATION_MARKER = ".alpha26-migrated"


# ---------- Filesystem layout helpers ----------

def _docs_root() -> Path:
    """Resolve the Documents-level root.
    Picks up `BIGHAT_FILES_DIR` for tests (which can point at a tmp tree
    and bypass the BIG Hat Entertainment naming entirely)."""
    override = os.environ.get("BIGHAT_FILES_DIR")
    if override:
        # When the override is set, it IS the base — no Documents prefix.
        return Path(override).expanduser()
    home = Path.home()
    docs = home / "Documents"
    base = docs if docs.exists() else home
    return base / APP_DOCS_FOLDER


def _merge_legacy_docs_folders() -> int:
    """If any legacy "BIGHat Entertainment" / "BH Entertainment" sibling
    folders exist next to the canonical "BIG Hat Entertainment" folder,
    move their contents into the canonical one and remove the (now
    empty) alias.

    Called once per process start via `_base_root()`. Idempotent — once
    the alias is gone (or has no overlap) this is a cheap no-op.

    Conflict rule: if the SAME relative path exists in both the legacy
    and canonical roots, the file with the newer mtime wins. We refuse
    to overwrite a newer canonical file with an older legacy one. This
    matters because alpha.24's backup_service wrote into the
    no-space "BIGHat" folder for two releases — the merchant's most
    recent backup is likely there, but they may also have started
    writing fresh data into "BIG Hat" since installing alpha.26.
    """
    if os.environ.get("BIGHAT_FILES_DIR"):
        return 0     # test override → never touch real Documents
    home = Path.home()
    docs = home / "Documents"
    if not docs.exists():
        return 0
    canonical = docs / APP_DOCS_FOLDER
    moved_total = 0
    for alias in LEGACY_DOCS_FOLDER_ALIASES:
        legacy = docs / alias
        if not legacy.exists() or legacy == canonical:
            continue
        canonical.mkdir(parents=True, exist_ok=True)
        # Only merge children whose name is in ALLOWED_DOCS_CHILDREN.
        # Everything else (notably stray `backend/`, `python/`, `lib/`
        # directories from broken dev builds or alpha packagers) gets
        # quarantined into `.legacy-unknown/<alias>/<child>/` under
        # canonical so the merchant can decide whether to keep it,
        # rather than silently inheriting confusing data.
        for child in list(legacy.iterdir()):
            try:
                if child.name in ALLOWED_DOCS_CHILDREN and child.is_dir():
                    dest_child = canonical / child.name
                    dest_child.mkdir(parents=True, exist_ok=True)
                    moved_total += _merge_tree(child, dest_child)
                    # Remove the now-empty source.
                    try:
                        if not any(child.rglob("*")):
                            shutil.rmtree(child, ignore_errors=True)
                    except OSError:
                        pass
                else:
                    # Quarantine — DON'T leave random data in the
                    # canonical brand folder.
                    quarantine_root = canonical / ".legacy-unknown" / alias
                    quarantine_root.mkdir(parents=True, exist_ok=True)
                    try:
                        shutil.move(str(child), str(quarantine_root / child.name))
                        logger.info(
                            "[native-files] quarantined unexpected legacy child "
                            "'%s/%s' into %s (was NOT a known data folder)",
                            alias, child.name, quarantine_root,
                        )
                    except OSError as e:
                        logger.warning(
                            "[native-files] could not quarantine %s: %s",
                            child, e,
                        )
            except OSError as e:
                logger.warning(
                    "[native-files] error processing legacy child %s: %s",
                    child, e,
                )
        # Try to remove the now-empty alias.
        try:
            if not any(legacy.iterdir()):
                legacy.rmdir()
                logger.info(
                    "[native-files] merged '%s' into canonical '%s' (%d files), "
                    "removed empty legacy folder",
                    alias, APP_DOCS_FOLDER, moved_total,
                )
        except OSError as e:
            logger.warning("[native-files] could not remove legacy folder '%s': %s", alias, e)
    return moved_total


def _merge_tree(src: Path, dst: Path) -> int:
    """Recursively move every file under `src` into the matching relative
    path under `dst`. Returns count of files moved. Skips overwriting
    when the destination is newer; otherwise overwrites in-place.

    We deliberately use rename (cross-device safe via shutil.move) rather
    than copy-then-delete: the merchant doesn't have 2× free space for
    their backup history."""
    moved = 0
    for src_path in src.rglob("*"):
        if not src_path.is_file():
            continue
        rel = src_path.relative_to(src)
        dst_path = dst / rel
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            if dst_path.exists():
                # Same-name conflict: newer wins.
                try:
                    if dst_path.stat().st_mtime >= src_path.stat().st_mtime:
                        src_path.unlink(missing_ok=True)
                        continue
                except OSError:
                    pass
                dst_path.unlink(missing_ok=True)
            shutil.move(str(src_path), str(dst_path))
            moved += 1
        except OSError as e:
            logger.warning("[native-files] skipped merging %s → %s: %s", src_path, dst_path, e)
    return moved


def _base_root() -> Path:
    """Resolve the on-disk base for the current user — the `Files/`
    folder UNDER the canonical "BIG Hat Entertainment" Documents root.

    Side-effect: triggers a one-shot merge of the legacy "BIGHat
    Entertainment" / "BH Entertainment" sibling folders into the
    canonical "BIG Hat Entertainment" before returning. This keeps
    the merchant's Documents tree clean on every app launch without
    any explicit migration UI.
    """
    override = os.environ.get("BIGHAT_FILES_DIR")
    if override:
        root = Path(override).expanduser()
        root.mkdir(parents=True, exist_ok=True)
        return root
    # First merge any legacy sibling folders, then resolve Files/.
    _merge_legacy_docs_folders()
    root = _docs_root() / "Files"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _hosts_root() -> Path:
    """v32.0.0-alpha.27: now lives UNDER Files/ (was `Files/..` before)
    so the merchant has a single `Files/` umbrella with everything in
    it. On first launch after alpha.27 we migrate any pre-existing
    `BIG Hat Entertainment/Hosts/` directory into
    `BIG Hat Entertainment/Files/Hosts/` so existing host data is
    preserved."""
    files_root = _base_root()
    hosts = files_root / "Hosts"
    # One-shot migration: pre-alpha.27 sat at the same level as Files/.
    legacy = files_root.parent / "Hosts"
    if legacy.exists() and legacy != hosts:
        hosts.mkdir(parents=True, exist_ok=True)
        try:
            _merge_tree(legacy, hosts)
            shutil.rmtree(legacy, ignore_errors=True)
            logger.info(
                "[native-files] alpha.27: moved legacy Hosts/ into Files/Hosts/"
            )
        except OSError as e:
            logger.warning("[native-files] could not migrate legacy Hosts/: %s", e)
    hosts.mkdir(parents=True, exist_ok=True)
    return hosts


def host_folder(host_identifier: str) -> Path:
    """Resolve (and create) the per-host folder under Files/Hosts/.

    `host_identifier` is the user's email, slug, or id — sanitised to a
    safe directory name. Returns the absolute path. Used by the
    profile-page image uploaders so each host's 16:9 / 9:16 GIFs +
    profile picture land in their own folder.
    """
    raw = (host_identifier or "").strip().lower()
    if not raw:
        raise HTTPException(status_code=400, detail="host_identifier required")
    # Strip any path separators or shell metacharacters the user might
    # type into the email field — defence against directory traversal.
    safe = re.sub(r"[^a-z0-9._@-]+", "-", raw).strip("-_.")
    if not safe:
        raise HTTPException(status_code=400, detail="host_identifier invalid")
    folder = _hosts_root() / safe
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def archive_previous_month_events() -> int:
    """On the first of every month, fold all of last month's events
    out of `Schedule/Events/` into `Schedule/Events/Archive/<YYYY-MM>.csv`.

    Idempotent — a marker file `Archive/.last-archived` records the
    most recent month archived so re-launching the app on the 2nd–31st
    of any month never re-runs the archive.

    Returns the number of event JSON files folded into the archive.
    """
    schedule = _base_root() / "Schedule"
    events_dir = schedule / "Events"
    archive_dir = events_dir / "Archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    marker = archive_dir / ".last-archived"
    now = datetime.now(timezone.utc)
    # Previous month: roll back to the 1st of the current month, then
    # subtract a day → that's a date inside last month.
    first_of_this_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    last_month_anchor = first_of_this_month - __import__("datetime").timedelta(days=1)
    last_month_key = last_month_anchor.strftime("%Y-%m")
    try:
        if marker.exists() and marker.read_text().strip() == last_month_key:
            return 0
    except OSError:
        pass

    # Walk every JSON in Events/ (NOT inside Archive/), parse, keep only
    # those whose `event_date` falls in last_month_key. Fold into one
    # CSV per month.
    archived = 0
    csv_path = archive_dir / f"{last_month_key}.csv"
    import csv as _csv
    rows: list[dict[str, Any]] = []
    for p in events_dir.glob("*.json"):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        event_date = str(data.get("event_date") or data.get("date") or "")
        if not event_date.startswith(last_month_key):
            continue
        rows.append(data)
        try:
            p.unlink()
        except OSError:
            pass

    if rows:
        # Use the union of every key seen so partial events still
        # archive without dropping fields.
        fieldnames: list[str] = []
        for r in rows:
            for k in r.keys():
                if k not in fieldnames:
                    fieldnames.append(k)
        with csv_path.open("w", newline="", encoding="utf-8") as fh:
            w = _csv.DictWriter(fh, fieldnames=fieldnames)
            w.writeheader()
            w.writerows(rows)
        archived = len(rows)

    try:
        marker.write_text(last_month_key, encoding="utf-8")
    except OSError:
        pass
    if archived:
        logger.info(
            "[native-files] archived %d events from %s into %s",
            archived, last_month_key, csv_path,
        )
    return archived


def _ensure_subfolders() -> None:
    """Idempotently create every typed subfolder. Cheap on every call.
    Also creates the nested working folders:
      • Trivia/<round_type>/ + Trivia/Rounds/ for presentation JSON
      • Schedule/Events/ + Schedule/Location Prices/ + Schedule/Events/Archive/
    """
    root = _base_root()
    for name in SUBFOLDERS:
        (root / name).mkdir(parents=True, exist_ok=True)
    trivia = root / "Trivia"
    for rt in TRIVIA_ROUND_TYPES:
        (trivia / rt).mkdir(parents=True, exist_ok=True)
    # Trivia/Rounds/ holds the JSON descriptors for built presentations.
    # Both the Trivia Presenter (for playback) and the Story Generator
    # (for social-asset matching) read from here.
    (trivia / "Rounds").mkdir(parents=True, exist_ok=True)
    # Schedule tree.
    schedule = root / "Schedule"
    (schedule / "Events").mkdir(parents=True, exist_ok=True)
    (schedule / "Events" / "Archive").mkdir(parents=True, exist_ok=True)
    (schedule / "Location Prices").mkdir(parents=True, exist_ok=True)


def _resolve_folder(folder: str | None) -> tuple[str, Path]:
    """Validate `folder` against SUBFOLDERS, return (canonical_name, path).
    None / empty / "all" → return ("", base_root) which means "every
    subfolder, aggregated".

    Round-type buckets are addressable too via the `Trivia/MC` form (or
    the slash-less `Trivia-MC`). Validation walks the allow-list end-to-
    end so we never trust raw input on disk."""
    if not folder or folder.lower() == "all":
        return "", _base_root()
    base = _base_root()

    # Round-type bucket form, e.g. `Trivia/MC` or `Trivia-MC`. The
    # separator-tolerant split handles both URL-friendly variants the
    # frontend might use.
    sep = "/" if "/" in folder else ("-" if "-" in folder else None)
    if sep:
        head, _, tail = folder.partition(sep)
        if head.lower() == "trivia" and tail:
            tail_up = tail.strip().upper()
            valid_buckets = set(TRIVIA_ROUND_TYPES) | {TRIVIA_DEFAULT_ROUND_TYPE.upper()}
            if tail_up in valid_buckets:
                # Preserve the on-disk casing of `_Other` if requested.
                tail_disk = TRIVIA_DEFAULT_ROUND_TYPE if tail_up == TRIVIA_DEFAULT_ROUND_TYPE.upper() else tail_up
                return f"Trivia/{tail_disk}", base / "Trivia" / tail_disk

    # Case-insensitive match against allow-list — never trust raw input.
    for name in SUBFOLDERS:
        if folder.lower() == name.lower():
            return name, base / name
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


def _round_type_from_archive(path: Path) -> str | None:
    """Inspect a .bighat archive's manifest + payload and return the
    canonical round_type code (`MC`/`REG`/`MISC`/`MYS`/`BIG`) if present.
    Returns None when the archive isn't a round, or carries no recognisable
    round_type — caller then drops it into `Trivia/_Other`."""
    try:
        with zipfile.ZipFile(path, "r") as zf:
            names = set(zf.namelist())
            if "manifest.json" not in names:
                return None
            manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
            content_type = str(manifest.get("type") or "").lower()
            if content_type not in ("round", "presentation", "pack"):
                return None
            rt = manifest.get("round_type")
            if not rt and "payload.json" in names:
                try:
                    payload = json.loads(zf.read("payload.json").decode("utf-8"))
                    rt = payload.get("round_type") or payload.get("type")
                except (json.JSONDecodeError, KeyError):
                    rt = None
            if not rt:
                return None
            rt_up = str(rt).strip().upper()
            return rt_up if rt_up in TRIVIA_ROUND_TYPES else None
    except (zipfile.BadZipFile, json.JSONDecodeError, KeyError, UnicodeDecodeError):
        return None


def _folder_for_path(path: Path) -> tuple[str, str | None]:
    """Inspect a .bighat archive and pick the destination subfolder.

    Returns `(top_level_subfolder, round_type_sub | None)`. For trivia
    content the second value is the round_type bucket (`MC`/`REG`/…).
    For non-trivia content it's None so callers know not to nest.
    """
    info = _summarise_bighat(path)
    content_type = str(info.get("type") or "").lower()
    top = _TYPE_TO_FOLDER.get(content_type, DEFAULT_SUBFOLDER)
    if top == "Trivia":
        rt = _round_type_from_archive(path)
        return top, rt or TRIVIA_DEFAULT_ROUND_TYPE
    return top, None


# ---------- One-shot migration: flat → typed subfolders ----------

def _migrate_flat_layout() -> int:
    """If the user has any .bighat files DIRECTLY in Files/ (legacy flat
    layout, pre-alpha.18), move them into the right subfolder by
    inspecting each archive's content_type. Idempotent — runs once per
    install (guarded by a marker file)."""
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
            top, rt = _folder_for_path(p)
            dest_dir = root / top
            if rt is not None:
                dest_dir = dest_dir / rt
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / p.name
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


def _migrate_rounds_to_trivia_layout() -> int:
    """One-shot alpha.26 migration: rename the legacy `Rounds/` folder
    to `Trivia/` AND redistribute every .bighat file inside it into
    the new round-type subdirectories (`MC/`, `REG/`, …).

    Idempotent — guarded by `_LAYOUT_MIGRATION_MARKER`. The migration
    runs even if the merchant only has `Trivia/` already (i.e. they
    manually renamed in Explorer) because the round-type split is the
    point of the migration, not the folder rename.
    """
    root = _base_root()
    marker = root / _LAYOUT_MIGRATION_MARKER
    if marker.exists():
        return 0

    legacy_rounds = root / "Rounds"
    trivia = root / "Trivia"

    # Step 1: if legacy Rounds/ exists, fold its contents into Trivia/.
    if legacy_rounds.exists() and legacy_rounds.is_dir():
        trivia.mkdir(parents=True, exist_ok=True)
        for child in legacy_rounds.rglob("*"):
            if not child.is_file():
                continue
            rel = child.relative_to(legacy_rounds)
            dest = trivia / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            try:
                if dest.exists():
                    if dest.stat().st_mtime >= child.stat().st_mtime:
                        child.unlink(missing_ok=True)
                        continue
                    dest.unlink(missing_ok=True)
                shutil.move(str(child), str(dest))
            except OSError as e:
                logger.warning("[native-files] could not migrate %s: %s", child, e)
        # Remove the now-empty `Rounds/` directory tree if possible.
        try:
            if not any(legacy_rounds.rglob("*")):
                shutil.rmtree(legacy_rounds, ignore_errors=True)
        except OSError:
            pass

    # Step 2: ensure all round-type subdirs exist.
    trivia.mkdir(parents=True, exist_ok=True)
    for rt in TRIVIA_ROUND_TYPES:
        (trivia / rt).mkdir(parents=True, exist_ok=True)

    # Step 3: move any .bighat files sitting DIRECTLY in Trivia/ (i.e.
    # the flat-layout legacy from before this release) into their
    # round-type bucket.
    moved = 0
    for p in trivia.glob("*.bighat"):
        if not p.is_file():
            continue
        rt = _round_type_from_archive(p) or TRIVIA_DEFAULT_ROUND_TYPE
        dest_dir = trivia / rt
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / p.name
        try:
            if dest.exists():
                if dest.stat().st_mtime >= p.stat().st_mtime:
                    p.unlink(missing_ok=True)
                    continue
                dest.unlink(missing_ok=True)
            p.rename(dest)
            moved += 1
        except OSError as e:
            logger.warning("[native-files] could not bucket %s: %s", p, e)

    try:
        marker.write_text(
            f"alpha.26 layout migration completed at "
            f"{datetime.now(timezone.utc).isoformat()}, moved={moved}\n",
            encoding="utf-8",
        )
    except OSError:
        pass
    if moved:
        logger.info(
            "[native-files] alpha.26: bucketed %d trivia round .bighat files by round_type",
            moved,
        )
    return moved


def _all_files_iter() -> Iterable[tuple[str, Path]]:
    """Walk every typed subfolder + every Trivia/<round_type>/ bucket.
    Yields (subfolder_name, file_path). The `subfolder_name` for trivia
    rounds is reported as e.g. `Trivia/MC` so the UI can show the full
    path-tail in a single column."""
    root = _base_root()
    for sub in SUBFOLDERS:
        sub_dir = root / sub
        if not sub_dir.exists():
            continue
        if sub == "Trivia":
            # Walk every round-type bucket plus the catchall.
            for rt_dir in sub_dir.iterdir():
                if not rt_dir.is_dir():
                    continue
                label = f"Trivia/{rt_dir.name}"
                for p in rt_dir.glob("*.bighat"):
                    yield label, p
            # Defensive: surface any .bighat files that somehow ended
            # up directly under Trivia/ (e.g. a legacy upload while the
            # migration was disabled) so the UI doesn't hide them.
            for p in sub_dir.glob("*.bighat"):
                yield "Trivia", p
        else:
            for p in sub_dir.glob("*.bighat"):
                yield sub, p


# ---------- HTTP routes ----------

@router.get("/folder")
async def files_folder() -> dict[str, Any]:
    """Return the absolute path of the base Files/ folder + list of
    typed subfolders + the trivia round-type buckets + the Hosts/ root.
    Also runs the monthly archive job for past events (idempotent —
    only fires once per calendar month, on the first launch of the
    month).
    """
    _ensure_subfolders()
    # Fire-and-forget the archive job. Wrapped in try/except so a
    # filesystem hiccup doesn't break the /folder endpoint.
    try:
        archive_previous_month_events()
    except Exception as e:                          # pragma: no cover
        logger.warning("[native-files] archive job failed: %s", e)
    root = _base_root()
    return {
        "ok": True,
        "folder": str(root),
        "hosts_folder": str(_hosts_root()),
        "subfolders": list(SUBFOLDERS),
        "trivia_round_types": list(TRIVIA_ROUND_TYPES),
        "exists": root.exists(),
        "platform": platform.system(),
    }


@router.post("/host-image")
async def upload_host_image(
    host_id: str = Form(...),
    kind: str = Form(...),   # 'avatar' | 'host-16x9' | 'host-9x16'
    file: UploadFile = File(...),
) -> dict[str, Any]:
    """Save a host's profile picture or one of their two host slide
    GIFs (16:9 for the trivia presentation host slide, 9:16 for the
    social story tool) into `Files/Hosts/<host_slug>/`.

    `host_id` is the host's email or slug — sanitised via
    `host_folder()` so a malformed value can't escape the Hosts/
    directory. `kind` constrains the filename to one of three
    canonical names so the consumers (Trivia Presenter slide
    generator, Story Generator) can find the asset deterministically
    without scanning."""
    KIND_TO_NAME = {
        "avatar":   "avatar",
        "host-16x9": "host-16x9",
        "host-9x16": "host-9x16",
    }
    if kind not in KIND_TO_NAME:
        raise HTTPException(status_code=400, detail=f"kind must be one of {sorted(KIND_TO_NAME)}")

    folder = host_folder(host_id)
    ext = Path(file.filename or "").suffix.lower()
    if ext not in {".png", ".jpg", ".jpeg", ".gif", ".webp"}:
        raise HTTPException(status_code=400, detail="image must be png/jpg/gif/webp")

    # Clear any prior file with the same canonical stem (host swapping
    # png → gif shouldn't leave the stale png on disk to be served by
    # mistake).
    for prior in folder.glob(f"{KIND_TO_NAME[kind]}.*"):
        try:
            prior.unlink()
        except OSError:
            pass

    dest = folder / f"{KIND_TO_NAME[kind]}{ext}"
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
    return {
        "ok": True,
        "host_id": host_id,
        "kind": kind,
        "path": str(dest),
        "size_bytes": size,
    }


@router.get("/raw")
async def serve_raw_file(path: str):
    """Serve an arbitrary file under the canonical Files/ root by its
    absolute path. Used by the user-profile page to render host
    images stored at `Files/Hosts/<slug>/avatar.png` (and similar)
    without having to know the file extension upfront.

    Defence: the requested path MUST resolve inside `_base_root()` —
    any path that walks above the Files/ tree (`..`, symlink jumps)
    is rejected with a 403."""
    try:
        resolved = Path(path).resolve()
    except (OSError, ValueError):
        raise HTTPException(status_code=400, detail="invalid path")
    root = _base_root().resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        raise HTTPException(status_code=403, detail="path outside Files root")
    if not resolved.is_file():
        raise HTTPException(status_code=404, detail="not_found")
    return FileResponse(str(resolved))


@router.get("")
async def files_list(folder: str | None = None) -> dict[str, Any]:
    """List every .bighat file. With `?folder=Trivia` (etc) lists only
    that subfolder; with `?folder=Trivia/MC` lists only that
    round-type bucket. Without a folder param, returns all files
    annotated with the subfolder (and round-type bucket where
    applicable) they live in. Triggers the one-shot migrations on
    first call after install / upgrade."""
    _ensure_subfolders()
    _migrate_flat_layout()
    _migrate_rounds_to_trivia_layout()

    items: list[dict[str, Any]] = []
    canonical, target = _resolve_folder(folder)

    if canonical and target.is_dir():
        if canonical == "Trivia":
            # Aggregating ALL round-type buckets while the merchant
            # filters at the top "Trivia" level — show every round file.
            for rt_dir in target.iterdir():
                if not rt_dir.is_dir():
                    continue
                for p in sorted(rt_dir.glob("*.bighat"), key=lambda x: x.stat().st_mtime, reverse=True):
                    try:
                        st = p.stat()
                        entry = {
                            "name": p.name,
                            "folder": f"Trivia/{rt_dir.name}",
                            "size_bytes": st.st_size,
                            "modified_at": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
                            "path": str(p),
                        }
                        entry.update(_summarise_bighat(p))
                        items.append(entry)
                    except OSError:
                        continue
        else:
            # Single-folder listing (Bingo/Karaoke/Other OR a specific
            # Trivia/<type> bucket).
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
        # Aggregate listing across every subfolder + round-type bucket.
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
        "trivia_round_types": list(TRIVIA_ROUND_TYPES),
        "count": len(items),
        "files": items,
    }


@router.post("/upload")
async def files_upload(
    file: UploadFile = File(...),
    folder: str | None = Form(default=None),
) -> dict[str, Any]:
    """Save a .bighat file. If `folder` is supplied (e.g. 'Trivia' or
    'Trivia/MC') the file goes there directly. Otherwise the archive's
    content_type is inspected to pick the right top-level subfolder,
    AND for trivia rounds the round_type is inspected to pick the
    right `Trivia/<TYPE>/` bucket. Overwrites a same-named file IN
    THE SAME LEAF FOLDER (not across folders)."""
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
            top, rt = _folder_for_path(staged)
            if top == "Trivia" and rt is not None:
                canonical = f"Trivia/{rt}"
                target_dir = base / "Trivia" / rt
            else:
                canonical = top
                target_dir = base / top
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
    absolute path. 404s if not found in any subfolder. With the
    alpha.26 layout, Trivia files live in `Trivia/<round_type>/`
    buckets — we scan all of them when no folder hint is supplied."""
    if folder:
        _, target_dir = _resolve_folder(folder)
        p = target_dir / name
        if p.exists():
            return p
        raise HTTPException(status_code=404, detail="not_found")
    # No folder hint — search every typed subfolder. For Trivia,
    # also walk each round-type bucket.
    base = _base_root()
    for sub in SUBFOLDERS:
        sub_dir = base / sub
        if not sub_dir.exists():
            continue
        if sub == "Trivia":
            for rt_dir in sub_dir.iterdir():
                if rt_dir.is_dir():
                    p = rt_dir / name
                    if p.exists():
                        return p
            # Defensive: legacy flat-layout in Trivia/ root.
            p = sub_dir / name
            if p.exists():
                return p
        else:
            p = sub_dir / name
            if p.exists():
                return p
    # Last-ditch: pre-migration flat layout at Files/ root.
    p = base / name
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
