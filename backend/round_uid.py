"""Permanent round ID (docs/PLAN_round_id_stamp.md). A round file's identity is `manifest.round_uid`: a lowercase UUID the Cloud library
stamps ONCE when the round is first uploaded and never changes (an edited, re-exported round keeps it). The File Creator's `content_id` is
NOT this: it is new on every export.

This module only READS. The Program never writes an ID into a file on the owner's PC (owner decision 2026-10-30): a file with no ID keeps
matching by name until the owner deletes it and re-downloads the stamped copy from the Cloud.
"""
import json
import os
import re
import threading
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

_UID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_cache: Dict[str, tuple] = {}           # path -> (size, mtime_ns, uid or None)
_lock = threading.Lock()


def clean(uid: Any) -> Optional[str]:
    """A valid round_uid (lowercase UUID) or None. Anything else is ignored, never trusted."""
    u = str(uid or "").strip().lower()
    return u if _UID.match(u) else None


def read_uid(path: Any) -> Optional[str]:
    """round_uid inside a round file, or None (no manifest, plain-JSON old round, not stamped yet, unreadable). Never raises."""
    try:
        p = Path(path)
        st = p.stat()
    except (OSError, TypeError, ValueError):
        return None
    key = str(p)
    with _lock:
        hit = _cache.get(key)
        if hit and hit[0] == st.st_size and hit[1] == st.st_mtime_ns:
            return hit[2]
    uid = None
    try:
        if zipfile.is_zipfile(p):
            with zipfile.ZipFile(p) as z:
                uid = clean((json.loads(z.read("manifest.json").decode("utf-8-sig")) or {}).get("round_uid"))
    except Exception:                                   # noqa: BLE001  a bad file must never break a list
        uid = None
    with _lock:
        _cache[key] = (st.st_size, st.st_mtime_ns, uid)
        if len(_cache) > 5000:
            _cache.clear()
    return uid


def read_uid_bytes(data: bytes) -> Optional[str]:
    import io
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            return clean((json.loads(z.read("manifest.json").decode("utf-8-sig")) or {}).get("round_uid"))
    except Exception:                                   # noqa: BLE001
        return None


def pool_files() -> List[Path]:
    """Every round file in the owner's type folders (MC, REG, MISC, MYS, BIG)."""
    import presentation_builder as pb
    out: List[Path] = []
    for t in ("MC", "REG", "MISC", "MYS", "BIG"):
        d = pb._round_pool_dir(t)
        if d.is_dir():
            out += sorted(x for x in d.iterdir() if x.is_file() and x.suffix.lower() == ".bighat")
    return out


def uid_for_name(name_or_path: Any) -> Optional[str]:
    """The round_uid of a round given by file name or path. A real path is read directly; a bare name is looked up in the pool.
    Returns None when the file is not on this PC or has no ID (callers then fall back to the name)."""
    s = str(name_or_path or "").strip()
    if not s:
        return None
    p = Path(s)
    if p.is_absolute() and p.is_file():
        return read_uid(p)
    import presentation_builder as pb
    leaf = p.name
    for cand in (pb._docs_root() / s, ):
        if cand.is_file():
            return read_uid(cand)
    for f in pool_files():
        if f.name.lower() == leaf.lower():
            return read_uid(f)
    return None


def unstamped_files() -> List[Dict[str, Any]]:
    """Round files on this PC with NO round_uid (the owner is asked to delete these and re-download the stamped copies)."""
    out = []
    for f in pool_files():
        if read_uid(f) is None:
            try:
                out.append({"type": f.parent.name.upper(), "file": f.name, "size": f.stat().st_size})
            except OSError:
                continue
    return out
