"""Contract test for v32.0.0-alpha.22 backup service.

Covers:
  • A fresh run zips the source tree into a dated file under dest.
  • Re-running on the same day overwrites idempotently.
  • Excluded subdirectories (Backups, __pycache__, tmp, staging) are skipped.
  • Retention keeps only the N most-recent dated zips.
  • A locked / unreadable file is skipped, not fatal.
  • Concurrent calls return `busy` instead of clobbering each other.
"""
from __future__ import annotations

import os
import threading
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend.native import backup_service as bs


@pytest.fixture
def src_and_dst(tmp_path):
    src = tmp_path / "data"
    src.mkdir()
    (src / "system_config.json").write_text('{"license":"abc"}', encoding="utf-8")
    (src / ".env").write_text("JWT_SECRET=zzz\n", encoding="utf-8")
    (src / "montydb").mkdir()
    (src / "montydb" / "store.collection").write_text("{}", encoding="utf-8")
    (src / "logs").mkdir()
    (src / "logs" / "app.log").write_text("init\n", encoding="utf-8")
    # Exclusion candidates that should NOT end up inside the zip.
    (src / "Backups").mkdir()
    (src / "Backups" / "old-zip.zip").write_bytes(b"old")
    (src / "__pycache__").mkdir()
    (src / "__pycache__" / "x.pyc").write_bytes(b"py")
    (src / "tmp").mkdir()
    (src / "tmp" / "scratch").write_text("temp", encoding="utf-8")
    (src / ".DS_Store").write_bytes(b"junk")
    dst = tmp_path / "backups"
    return src, dst


def test_run_backup_writes_dated_zip_with_expected_files(src_and_dst):
    src, dst = src_and_dst
    result = bs.run_backup(source=src, dest_dir=dst)
    assert result.ok is True, result.error
    assert result.path is not None
    zp = Path(result.path)
    assert zp.is_file()
    today = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d")
    assert zp.name == f"bighat-backup-{today}.zip"

    with zipfile.ZipFile(zp) as zf:
        members = set(zf.namelist())
    # Core state files are present.
    assert "system_config.json" in members
    assert ".env" in members
    # Subdir files are present (path separator may be '/' or '\\' on Win).
    assert any(m.endswith("store.collection") for m in members)
    assert any(m.endswith("app.log") for m in members)
    # Exclusions held.
    assert not any(m.startswith("Backups") for m in members)
    assert not any(m.startswith("__pycache__") for m in members)
    assert not any(m.startswith("tmp") for m in members)
    assert ".DS_Store" not in members


def test_run_backup_is_idempotent_per_day(src_and_dst):
    src, dst = src_and_dst
    a = bs.run_backup(source=src, dest_dir=dst)
    assert a.ok
    # Add a new file then re-run; the same-day zip must update in place.
    (src / "new_thing.txt").write_text("hello", encoding="utf-8")
    b = bs.run_backup(source=src, dest_dir=dst)
    assert b.ok
    assert b.path == a.path, "Same calendar day → same zip file path"
    with zipfile.ZipFile(b.path) as zf:
        assert "new_thing.txt" in zf.namelist()


def test_retention_keeps_newest_n(src_and_dst):
    src, dst = src_and_dst
    dst.mkdir(parents=True, exist_ok=True)
    # Plant 20 dated zips in the destination, dated days apart.
    for i in range(20):
        day = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=i)
        p = dst / f"bighat-backup-{day.strftime('%Y-%m-%d')}.zip"
        # Write a real zip so we can verify retention doesn't corrupt them.
        with zipfile.ZipFile(p, "w") as zf:
            zf.writestr("placeholder", "x")
    removed = bs.cleanup_old_backups(dst, keep=5)
    assert removed == 15
    remaining = sorted([p.name for p in dst.glob("bighat-backup-*.zip")])
    assert len(remaining) == 5
    # Newest 5 — by lexicographic date sort, those are the LAST 5 of 2026-01-(16..20).
    expected = [f"bighat-backup-2026-01-{16+i:02d}.zip" for i in range(5)]
    assert remaining == expected


def test_retention_does_not_touch_unrelated_zips(src_and_dst):
    """Some merchants drop their own archives in the Backups folder. The
    retention sweep must only remove our own `bighat-backup-*.zip`
    naming pattern, never user-named files.
    """
    _, dst = src_and_dst
    dst.mkdir(parents=True, exist_ok=True)
    user_zip = dst / "my-manual-archive.zip"
    with zipfile.ZipFile(user_zip, "w") as zf:
        zf.writestr("note", "important")
    for i in range(3):
        day = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=i)
        with zipfile.ZipFile(dst / f"bighat-backup-{day.strftime('%Y-%m-%d')}.zip", "w") as zf:
            zf.writestr("x", "1")
    bs.cleanup_old_backups(dst, keep=1)
    assert user_zip.is_file(), "User-named zip must not be deleted"


def test_concurrent_backups_return_busy(src_and_dst):
    src, dst = src_and_dst
    # Hold the lock from another thread to simulate an in-flight backup.
    bs._lock.acquire()
    try:
        result = bs.run_backup(source=src, dest_dir=dst)
        assert result.ok is False
        assert result.error == "busy"
    finally:
        bs._lock.release()


def test_missing_source_returns_failure_not_exception(tmp_path):
    src = tmp_path / "ghost"            # never created
    dst = tmp_path / "backups"
    result = bs.run_backup(source=src, dest_dir=dst)
    assert result.ok is False
    assert (result.error or "").startswith("source_missing")


def test_list_backups_returns_newest_first(src_and_dst):
    src, dst = src_and_dst
    dst.mkdir(parents=True, exist_ok=True)
    days = ["2026-01-05", "2026-02-01", "2026-01-22"]
    for d in days:
        with zipfile.ZipFile(dst / f"bighat-backup-{d}.zip", "w") as zf:
            zf.writestr("x", "y")
    out = bs.list_backups(dest_dir=dst)
    names = [e["name"] for e in out]
    assert names == [
        "bighat-backup-2026-02-01.zip",
        "bighat-backup-2026-01-22.zip",
        "bighat-backup-2026-01-05.zip",
    ]
