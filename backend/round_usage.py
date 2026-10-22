"""Round usage + 180-day lockout. DISK IS THE SOURCE OF TRUTH.

File: <Files>/Trivia/round_usage.json  ->  {"records": [ {...}, ... ]}

A record is created for every round in a built presentation. A round is LOCKED
for a location for LOCK_DAYS (180) after `usedDate`, or until an admin releases
(deletes) the record. Mirrors the webapp prototype (db.round_usage) fields:
id, location, roundFile, roundFileName, roundType, roundNumber, usedDate,
expiresDate, usedBy, presentationId, presentationName.
"""
import json
import re
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

LOCK_DAYS = 180
_lock = threading.Lock()


def _path() -> Path:
    from native_slides import _docs_root
    p = _docs_root() / "Files" / "Trivia" / "round_usage.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse(s: Any) -> Optional[datetime]:
    if isinstance(s, datetime):
        return s if s.tzinfo else s.replace(tzinfo=timezone.utc)
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _backup_file() -> Optional[Path]:
    try:
        from native.data_map import backups_dir
        d = backups_dir()
        d.mkdir(parents=True, exist_ok=True)
        return d / "round_usage.json"
    except Exception:
        return None


def _read_backup() -> Dict[str, Any]:
    b = _backup_file()
    try:
        d = json.loads(b.read_text(encoding="utf-8")) if b and b.exists() else {}
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _read_doc() -> Dict[str, Any]:
    """The usage file. A damaged file is kept aside as .bad and is NEVER read as 'no records' (the next save would
    have overwritten every lock). If the file is DAMAGED or EMPTY (0 bytes), the copy kept in AppData\\backups is put back.
    A file that is simply missing is a fresh start and is NOT refilled (no old locks come back by surprise)."""
    p = _path()
    damaged = False
    doc: Any = None
    if not p.exists():
        return {}
    if p.exists():
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
            if not isinstance(doc, dict):
                raise ValueError("not an object")
        except Exception:
            damaged, doc = True, None
            try:
                import os
                os.replace(p, p.with_suffix(".json.bad"))
            except OSError:
                pass
    if doc is None:
        bak = _read_backup()
        if bak.get("records") or bak.get("released"):
            try:
                _write_main(bak)
            except OSError:
                pass
            return bak
        return {}
    return doc


def _load() -> List[Dict[str, Any]]:
    return list(_read_doc().get("records", []))


def _released() -> set:
    """'presentationId:roundNumber' keys an admin released. Backfill must
    never resurrect these."""
    return set(_read_doc().get("released", []))


def _write_main(doc: Dict[str, Any]) -> None:
    p = _path()
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    tmp.replace(p)


def _save(records: List[Dict[str, Any]], released: Optional[set] = None) -> None:
    rel = _released() if released is None else released
    doc = {"records": records, "released": sorted(rel)}
    _write_main(doc)
    b = _backup_file()                              # second copy outside Documents (best effort)
    if b is not None:
        try:
            tmp = b.with_suffix(".tmp")
            tmp.write_text(json.dumps(doc, indent=2), encoding="utf-8")
            tmp.replace(b)
        except OSError:
            pass


def norm_name(s: Any) -> str:
    """Stable key for a round: file stem, lowercased, no extension."""
    t = str(s or "").replace("\\", "/").split("/")[-1].strip().lower()
    return re.sub(r"\.(bighat|pptx)$", "", t)


_LOC_FORMS = (re.compile(r"^location:([^/\\]+)$", re.I),                       # sentinel when a location has no branding image
              re.compile(r"/api/native/locations/([^/\\?]+)", re.I))            # branding image URL the Wizard/Roulette send


def norm_location(s: Any) -> str:
    raw = str(s or "").strip()
    for rx in _LOC_FORMS:                       # v32.1.7: the lists were sent these and matched nothing, so nothing was hidden
        m = rx.search(raw)
        if m:
            return re.sub(r"[^a-z0-9]+", "-", m.group(1).lower()).strip("-")
    t = raw.replace("\\", "/").rstrip("/").split("/")[-1].strip().lower()
    t = re.sub(r"^\d+_", "", t)
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")


def record_usage(*, location_id: str, location_name: str, round_files: List[Dict[str, Any]],
                 used_by: str, presentation_id: str, presentation_name: str,
                 used_at: Optional[datetime] = None, skip_released: bool = False) -> int:
    """Add one record per round. Idempotent per (presentation, round order)."""
    now = used_at or _now()
    with _lock:
        recs = _load()
        have = {(r.get("presentationId"), r.get("roundNumber")) for r in recs}
        gone = _released() if skip_released else set()
        added = 0
        for rf in round_files:
            key = (presentation_id, rf.get("order"))
            if key in have or f"{presentation_id}:{rf.get('order')}" in gone:
                continue
            recs.append({
                "id": str(uuid.uuid4()),
                "location": location_name or location_id,
                "locationId": location_id,
                "roundFile": rf.get("file", ""),
                "roundFileName": norm_name(rf.get("file", "")),
                "roundType": rf.get("type", ""),
                "roundNumber": rf.get("order", 0),
                "usedDate": now.isoformat(),
                "expiresDate": (now + timedelta(days=LOCK_DAYS)).isoformat(),
                "usedBy": used_by or "",
                "presentationId": presentation_id,
                "presentationName": presentation_name,
            })
            added += 1
        if added:
            _save(recs)
        return added


def list_records() -> List[Dict[str, Any]]:
    try:
        backfill_from_presentations()
    except Exception:
        pass
    now = _now()
    out = []
    for r in _load():
        r = dict(r)
        exp = _parse(r.get("expiresDate"))
        r["isExpired"] = bool(exp and exp < now)
        r["locationName"] = str(r.get("location", "")).replace("\\", "/").split("/")[-1]
        out.append(r)
    out.sort(key=lambda r: str(r.get("usedDate", "")), reverse=True)
    return out


def locked_names(location: Optional[str]) -> set:
    """Round stems currently locked (active, not expired) for a location."""
    try:
        backfill_from_presentations()
    except Exception:
        pass
    want = norm_location(location) if location else ""
    now = _now()
    s = set()
    for r in _load():
        exp = _parse(r.get("expiresDate"))
        if exp and exp < now:
            continue
        if want and want not in (norm_location(r.get("location")), norm_location(r.get("locationId"))):
            continue
        s.add(norm_name(r.get("roundFileName") or r.get("roundFile")))
    return s


def _tomb(recs: List[Dict[str, Any]]) -> set:
    return {f"{r.get('presentationId')}:{r.get('roundNumber')}" for r in recs}


def release(usage_id: str) -> int:
    with _lock:
        recs = _load()
        gone = [r for r in recs if r.get("id") == usage_id]
        keep = [r for r in recs if r.get("id") != usage_id]
        if gone:
            _save(keep, _released() | _tomb(gone))
        return len(gone)


def release_presentation(presentation_id: str) -> int:
    with _lock:
        recs = _load()
        gone = [r for r in recs if r.get("presentationId") == presentation_id]
        keep = [r for r in recs if r.get("presentationId") != presentation_id]
        if gone:
            _save(keep, _released() | _tomb(gone))
        return len(gone)


def release_all() -> int:
    with _lock:
        recs = _load()
        _save([], _released() | _tomb(recs))
        return len(recs)


def backfill_from_presentations() -> int:
    """One-time/boot heal: shows built before usage tracking existed (or whose
    records were lost) get their rounds recorded from the saved presentation
    files. Respects admin releases. Idempotent."""
    try:
        from native_slides import _docs_root
        rdir = _docs_root() / "Files" / "Trivia" / "Rounds"
        if not rdir.is_dir():
            return 0
    except Exception:
        return 0
    added = 0
    for f in sorted(rdir.glob("*.bighat")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        refs = d.get("roundFiles") or []
        if not d.get("id") or not refs or not all(isinstance(r, dict) and r.get("file") for r in refs):
            continue
        when = _parse(d.get("created_at") or d.get("createdAt")) or _now()
        added += record_usage(
            location_id=d.get("location_id") or "",
            location_name=d.get("location_name") or d.get("location") or "",
            round_files=[{"order": r.get("order", i + 1), "type": r.get("type", ""), "file": r["file"]}
                         for i, r in enumerate(refs)],
            used_by=d.get("host_name") or d.get("created_by") or "",
            presentation_id=d["id"], presentation_name=d.get("name", ""),
            used_at=when, skip_released=True,
        )
    return added


def cleanup_expired() -> int:
    now = _now()
    with _lock:
        recs = _load()
        keep = [r for r in recs if not ((_parse(r.get("expiresDate")) or now) < now)]
        if len(keep) != len(recs):
            _save(keep)
        return len(recs) - len(keep)


def stats() -> Dict[str, Any]:
    recs = list_records()
    by_type: Dict[str, int] = {}
    for r in recs:
        by_type[r.get("roundType", "")] = by_type.get(r.get("roundType", ""), 0) + 1
    active = sum(1 for r in recs if not r["isExpired"])
    return {"totalUsageRecords": len(recs), "activeRecords": active,
            "expiredRecords": len(recs) - active, "usageByType": by_type}
