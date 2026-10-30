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


def _save(records: List[Dict[str, Any]], released: Optional[set] = None, released_rounds: Optional[set] = None) -> None:
    rel = _released() if released is None else released
    rr = _released_rounds() if released_rounds is None else released_rounds
    doc = {"records": records, "released": sorted(rel), "released_rounds": sorted([list(x) for x in rr])}
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


_TYPE_PREFIX = re.compile(r"^(mc|reg|misc|mys|big)__")        # the File Creator names its exports TYPE__name
_STAMP = re.compile(r"-[0-9a-f]{8}$")                         # alpha.90 stamped copy: name-<8 hex>


UID_PREFIX = "uid:"


def _uid_of(x: Any) -> Optional[str]:
    """The round_uid for a lock record (dict) or a file name/path (string). None when it has none."""
    try:
        import round_uid as _ru                       # lazy: a problem reading a file's id must never stop locks from working
        if isinstance(x, dict):
            return _ru.clean(x.get("roundUid"))
        s = str(x or "")
        if s.startswith(UID_PREFIX):
            return _ru.clean(s[len(UID_PREFIX):])
        return _ru.uid_for_name(s)
    except Exception:                                 # noqa: BLE001
        return None


def round_keys_for(x: Any) -> set:
    """Every key a round answers to: its uid (when stamped) plus every name spelling. The uid is the real identity;
    the names keep unstamped files and the 180 days of locks that already exist working."""
    keys = same_round_keys(x.get("roundFileName") or x.get("roundFile") if isinstance(x, dict) else x)
    u = _uid_of(x)
    if u:
        keys = keys | {UID_PREFIX + u}
    return keys


def same_round_keys(s: Any) -> set:
    """Every spelling a round can have on disk. The File Creator gives each export a NEW random id, so a re-uploaded round
    comes back as MYS__name, name, or name-<8 hex>: the lock must treat all of them as ONE round.
    v32.1.8: locks used to match only the exact file name, so a re-uploaded copy of a locked round was offered again."""
    base = norm_name(s)
    keys = {base}
    no_prefix = _TYPE_PREFIX.sub("", base)
    keys.add(no_prefix)
    for k in list(keys):
        if _STAMP.search(k):
            keys.add(_STAMP.sub("", k))        # an 8-hex tail is also treated as a stamp; it only ever ADDS a possible match
    return {k for k in keys if k}


def is_locked(name_or_path: Any, locked: set) -> bool:
    """True when this file is the same round as any locked one. `locked` comes from locked_names().
    v32.2.5: a stamped file is also matched by its round_uid, so a RENAMED copy of a used round is still locked. A name match still locks
    too (a lock made before the round was stamped must never stop working), so this can only ADD locks, never drop one."""
    u = _uid_of(name_or_path)
    if u and (UID_PREFIX + u) in locked:
        return True
    mine = same_round_keys(name_or_path)
    if mine & locked:
        return True
    for l in locked:                         # a locked stamped copy locks the plain file too
        if same_round_keys(l) & mine:
            return True
    return False


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
        gone_rounds = _released_rounds() if skip_released else set()
        loc_key = norm_location(location_id or location_name)
        added = 0
        for rf in round_files:
            key = (presentation_id, rf.get("order"))
            if key in have or f"{presentation_id}:{rf.get('order')}" in gone:
                continue
            if skip_released and any((loc_key, k) in gone_rounds for k in round_keys_for(rf.get("file", ""))):
                continue                      # an admin released this round at this venue: an older saved show cannot re-lock it
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
                **({"roundUid": _u} if (_u := _uid_of(rf.get("file", ""))) else {}),     # v32.2.5: the round's permanent id, when stamped
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


def venue_identities(location: Optional[str]) -> set:
    """Every normalised identity (id, slug, name) of the venue `location` points at. A lock can be saved under the NAME (old shows,
    backfilled shows) while a screen sends the ID or an image URL, and the other way round. v32.1.10: the Wizard list only matched
    the one form it was sent, so a round locked under the venue's name was offered and then refused on the review page."""
    want = norm_location(location) if location else ""
    ids = {want} if want else set()
    if not want:
        return ids
    try:
        from native_slides import _docs_root
        root = _docs_root() / "Files" / "Locations"
        for lj in root.glob("*/location.json") if root.is_dir() else []:
            try:
                d = json.loads(lj.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            mine = {norm_location(d.get(k)) for k in ("id", "slug", "name") if d.get(k)} | {norm_location(lj.parent.name)}
            mine.discard("")
            if want in mine:
                ids |= mine
    except Exception:                                   # noqa: BLE001  never break the list over a bad folder
        pass
    return ids


def locked_names(location: Optional[str]) -> set:
    """Round stems currently locked (active, not expired) for a location."""
    try:
        backfill_from_presentations()
    except Exception:
        pass
    want = venue_identities(location) if location else set()
    now = _now()
    s = set()
    for r in _load():
        exp = _parse(r.get("expiresDate"))
        if exp and exp < now:
            continue
        if want and not (want & {norm_location(r.get("location")), norm_location(r.get("locationId"))}):
            continue
        s.add(norm_name(r.get("roundFileName") or r.get("roundFile")))
        u = _uid_of(r)
        if u:
            s.add(UID_PREFIX + u)                       # v32.2.5: the permanent id of the round
    return s


def _round_tomb(recs: List[Dict[str, Any]]) -> set:
    out = set()
    for r in recs:
        loc = norm_location(r.get("locationId") or r.get("location"))
        for k in round_keys_for(r):
            out.add((loc, k))
    return out


def _tomb(recs: List[Dict[str, Any]]) -> set:
    return {f"{r.get('presentationId')}:{r.get('roundNumber')}" for r in recs}


def _same_place_and_round(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    la = {norm_location(a.get("location")), norm_location(a.get("locationId"))} - {""}
    lb = {norm_location(b.get("location")), norm_location(b.get("locationId"))} - {""}
    for k in list(la):                                  # v32.1.10: a venue's id, slug and name are ONE place
        la |= venue_identities(k)
    if la and lb and not (la & lb):
        return False
    return bool(round_keys_for(a) & round_keys_for(b))


def release(usage_id: str) -> int:
    """Release a round: the record AND every other active record of the same round at the same venue (another spelling of its
    file name, or an earlier show that used it), so it cannot stay locked after an admin released it. v32.1.8"""
    with _lock:
        recs = _load()
        first = [r for r in recs if r.get("id") == usage_id]
        if not first:
            return 0
        gone = [r for r in recs if r.get("id") == usage_id or any(_same_place_and_round(r, f) for f in first)]
        gone_ids = {r.get("id") for r in gone}
        keep = [r for r in recs if r.get("id") not in gone_ids]
        _save(keep, _released() | _tomb(gone), _released_rounds() | _round_tomb(gone))
        return len(gone)


def release_presentation(presentation_id: str) -> int:
    """Release every round of one show. Each round is freed at that venue (every other record of the same round there goes too),
    so another show that used it cannot keep it locked. v32.1.8"""
    with _lock:
        recs = _load()
        mine = [r for r in recs if r.get("presentationId") == presentation_id]
        if not mine:
            return 0
        gone = [r for r in recs if r.get("presentationId") == presentation_id or any(_same_place_and_round(r, m) for m in mine)]
        gone_ids = {r.get("id") for r in gone}
        keep = [r for r in recs if r.get("id") not in gone_ids]
        _save(keep, _released() | _tomb(gone), _released_rounds() | _round_tomb(gone))
        return len(gone)


def release_all() -> int:
    with _lock:
        recs = _load()
        _save([], _released() | _tomb(recs), _released_rounds() | _round_tomb(recs))
        return len(recs)


def _released_rounds() -> set:
    """(venue key, round key) pairs an admin released. A saved show that used any spelling of that round at that venue must not
    re-create its lock when the usage file is rebuilt from the saved shows."""
    return set(tuple(x) for x in _read_doc().get("released_rounds", []) if isinstance(x, list) and len(x) == 2)


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


# ---------------------------------------------------------------- Cloud lock sync helpers (native/cloud_locks.py)
def cloud_is_tombstoned(location_id: str, location_name: str, file_name: str) -> bool:
    """True when an admin released this round at this venue on this PC."""
    gone = _released_rounds()
    locs = {norm_location(location_id), norm_location(location_name)} - {""}
    for l in list(locs):
        locs |= venue_identities(l)
    return any((l, k) in gone for l in locs for k in round_keys_for(file_name))


def cloud_add(*, location_id: str, location_name: str, file_name: str, round_type: str, used_at: Any, expires_at: Any,
              used_by: str, presentation_id: str, presentation_name: str, round_uid: Any = None) -> Optional[str]:
    """Add a lock another PC made. Returns the new record id, or None when this PC already has an equal-or-newer lock for the
    same round at the same venue (nothing is ever replaced or shortened)."""
    when = _parse(used_at) or _now()
    import round_uid as _ru
    uid = _ru.clean(round_uid)
    probe = {"location": location_name, "locationId": location_id, "roundFileName": norm_name(file_name), "roundFile": file_name,
             **({"roundUid": uid} if uid else {})}
    with _lock:
        recs = _load()
        for r in recs:
            if _same_place_and_round(r, probe):
                mine = _parse(r.get("usedDate"))
                if mine and mine >= when:
                    return None
        rid = str(uuid.uuid4())
        recs.append({"id": rid, "location": location_name or location_id, "locationId": location_id, "roundFile": file_name,
                     "roundFileName": norm_name(file_name), "roundType": round_type or "", "roundNumber": 0,
                     "usedDate": when.isoformat(),
                     "expiresDate": (_parse(expires_at) or (when + timedelta(days=LOCK_DAYS))).isoformat(),
                     "usedBy": used_by or "", "presentationId": presentation_id, "presentationName": presentation_name,
                     "source": "cloud", **({"roundUid": uid} if uid else {})})
        _save(recs)
        return rid


def cloud_release(location_name: str, location_id: str, file_name: str, released_at: Any, round_uid: Any = None) -> int:
    """Apply a release made in the Cloud: every lock of this round at this venue used on/before released_at goes (with tombstones,
    so a saved show cannot rebuild it). A newer use stays locked."""
    import round_uid as _ru
    cut = _parse(released_at)
    uid = _ru.clean(round_uid)
    probe = {"location": location_name, "locationId": location_id, "roundFileName": norm_name(file_name), "roundFile": file_name,
             **({"roundUid": uid} if uid else {})}
    with _lock:
        recs = _load()
        gone = []
        for r in recs:
            if _same_place_and_round(r, probe):
                used = _parse(r.get("usedDate"))
                if cut is None or used is None or used <= cut:
                    gone.append(r)
        if not gone:
            return 0
        ids = {r.get("id") for r in gone}
        _save([r for r in recs if r.get("id") not in ids], _released() | _tomb(gone), _released_rounds() | _round_tomb(gone))
        return len(gone)
