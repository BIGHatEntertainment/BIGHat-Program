"""Duplicate round files on this PC (PR 2 of the one-source-of-truth work).

A duplicate is only ever CERTAIN, never a guess:
  * "same stamp"   two files carry the same permanent round_uid, or
  * "same content" two UNSTAMPED files of one type have identical questions and answers.
A file that only shares a NAME with another is NEVER treated as a duplicate.

check() is read-only. retire() MOVES (never deletes) the extra copies into Files/_retired_duplicates/<date>/ where the owner can put them
back by hand. A copy is KEPT, and the report says why, when a saved show points at it, when the 180-day lockout tracks it by file name,
or when it is the only copy that carries a stamp.
"""
from __future__ import annotations

import hashlib
import json
import logging
import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import round_uid

logger = logging.getLogger("bighat.round_duplicates")
MAX_GROUPS = 200


def _content_key(path: Path) -> Optional[str]:
    """A fingerprint of a round's questions + answers, or None when it cannot be read. Names, ids and stamps are NOT part of it."""
    try:
        if zipfile.is_zipfile(path):
            with zipfile.ZipFile(path) as z:
                names = z.namelist()
                member = "payload.json" if "payload.json" in names else ("round.json" if "round.json" in names else None)
                if not member:
                    return None
                doc = json.loads(z.read(member).decode("utf-8-sig"))
        else:
            doc = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:                                           # noqa: BLE001  an unreadable file is never called a duplicate
        return None
    qs = doc.get("questions") if isinstance(doc, dict) else None
    if not isinstance(qs, list) or not qs:
        return None
    flat = []
    for q in qs:
        if not isinstance(q, dict):
            return None
        flat.append([str(q.get(k) if q.get(k) is not None else "").strip().lower()
                     for k in ("question", "prompt", "text", "answer", "correctAnswer", "correct_answer")])
    return hashlib.sha256(json.dumps([path.parent.name.upper(), flat], ensure_ascii=False).encode("utf-8")).hexdigest()


def _rel(p: Path) -> str:
    import presentation_builder as pb
    try:
        return p.relative_to(pb._docs_root()).as_posix()
    except ValueError:
        return p.name


async def _files_in_use(db) -> Dict[str, List[str]]:
    """relative file path (lowercase) -> names of the saved shows that point at it."""
    out: Dict[str, List[str]] = {}
    for coll in ("presentations", "trivia_presentations"):
        try:
            rows = await getattr(db, coll).find({}, {"_id": 0}).to_list(5000)
        except Exception:                                       # noqa: BLE001
            rows = []
        for p in rows:
            for r in (p.get("rounds") or p.get("round_files") or []):
                ref = (r.get("file") or r.get("path") or "") if isinstance(r, dict) else str(r or "")
                if ref:
                    out.setdefault(ref.replace("\\", "/").lower(), []).append(str(p.get("name") or p.get("title") or p.get("id") or "a show"))
    return out


def _locked_by_name() -> set:
    """Lock keys that are file NAMES (an unstamped round locks by its name)."""
    try:
        import round_usage
        return {x for x in round_usage.locked_names(None) if not str(x).startswith(round_usage.UID_PREFIX)}
    except Exception:                                           # noqa: BLE001
        return set()


def _modified(p: Path) -> float:
    try:
        return p.stat().st_mtime
    except OSError:
        return 0.0


async def build(db) -> Dict[str, Any]:
    """Read-only. Groups of certain duplicates, which copy to keep, and which copies could be retired."""
    import round_usage
    files = round_uid.pool_files()
    in_use = await _files_in_use(db)
    locked = _locked_by_name()
    buckets: Dict[str, List[Path]] = {}
    for f in files:
        u = round_uid.read_uid(f)
        if u:
            buckets.setdefault("uid:" + u, []).append(f)
        else:
            k = _content_key(f)
            if k:
                buckets.setdefault("content:" + k, []).append(f)
    groups: List[Dict[str, Any]] = []
    for key, members in buckets.items():
        if len(members) < 2:
            continue
        # keep order: a stamped file first, then one a saved show uses, then the oldest (the original)
        def _locked(p: Path) -> bool:
            return round_usage.norm_name(p.name) in locked or round_usage.norm_name(p.stem) in locked

        # keep order: stamped first, then the copy the lockout tracks by name, then one a saved show uses, then the oldest, then the plainest name
        members.sort(key=lambda p: (round_uid.read_uid(p) is None, not _locked(p), _rel(p).lower() not in in_use, _modified(p), len(p.name), p.name))
        keep, extras = members[0], members[1:]
        rows = []
        for p in extras:
            why = ""
            rel = _rel(p).lower()
            if rel in in_use:
                why = "a saved show uses this copy: " + ", ".join(sorted(set(in_use[rel]))[:3])
            elif round_usage.norm_name(p.name) in locked or round_usage.norm_name(p.stem) in locked:
                why = "the 180-day lockout tracks this file name"
            rows.append({"file": p.name, "type": p.parent.name.upper(), "path": _rel(p), "can_retire": not why, "kept_because": why})
        groups.append({"basis": "same stamp" if key.startswith("uid:") else "same questions and answers",
                       "type": keep.parent.name.upper(), "keep": {"file": keep.name, "path": _rel(keep)}, "extras": rows})
    groups.sort(key=lambda g: (g["type"], g["keep"]["file"]))
    n_ret = sum(1 for g in groups for r in g["extras"] if r["can_retire"])
    return {"groups": groups[:MAX_GROUPS], "group_count": len(groups), "copies": sum(len(g["extras"]) for g in groups),
            "can_retire": n_ret, "kept": sum(len(g["extras"]) for g in groups) - n_ret,
            "files_scanned": len(files)}


def _digest(plan: Dict[str, Any]) -> str:
    keys = sorted(r["path"] for g in plan["groups"] for r in g["extras"] if r["can_retire"])
    return hashlib.sha256(json.dumps(keys).encode("utf-8")).hexdigest()[:24]


async def check(db) -> Dict[str, Any]:
    plan = await build(db)
    plan["token"] = _digest(plan)
    if not plan["group_count"]:
        plan["message"] = "No duplicate round files found."
    else:
        plan["message"] = (f"{plan['copies']} extra copies in {plan['group_count']} groups. {plan['can_retire']} can be moved aside "
                           f"(nothing is deleted); {plan['kept']} stay because something still uses them.")
    return plan


async def retire(db, token: str) -> Dict[str, Any]:
    """Moves the extra copies aside. Re-checks first: if anything changed since the check, nothing is moved."""
    if not token or not isinstance(token, str):
        return {"ok": False, "error": "no_token", "message": "Check for duplicates first, then confirm."}
    plan = await build(db)
    if _digest(plan) != token:
        return {"ok": False, "error": "changed", "message": "The files changed since you checked. Nothing was moved. Check again."}
    import presentation_builder as pb
    dest = pb._files_root() / "_retired_duplicates" / datetime.now().strftime("%Y%m%d-%H%M%S")
    moved: List[Dict[str, str]] = []
    for g in plan["groups"]:
        for r in g["extras"]:
            if not r["can_retire"]:
                continue
            src = pb._docs_root() / r["path"]
            if not src.is_file():
                continue
            d = dest / r["type"]
            try:
                d.mkdir(parents=True, exist_ok=True)
                target = d / src.name
                if target.exists():
                    target = d / f"{src.stem}-{hashlib.sha1(str(src).encode()).hexdigest()[:6]}{src.suffix}"
                shutil.move(str(src), str(target))
                moved.append({"file": src.name, "from": r["path"], "to": str(target)})
            except OSError as e:
                logger.warning("[round-duplicates] could not move %s: %s", src, e)
                return {"ok": False, "error": "move_failed", "moved": moved, "folder": str(dest),
                        "message": f"Stopped safely at {src.name} ({type(e).__name__}). {len(moved)} were moved first; nothing was deleted."}
    try:
        (dest / "WHAT_HAPPENED.txt").parent.mkdir(parents=True, exist_ok=True)
        (dest / "WHAT_HAPPENED.txt").write_text("These round files were exact duplicates. They were moved here, not deleted. To undo, move a file back to Files/Trivia/<TYPE>/.\n\n"
                                                + "\n".join(f"{m['file']}  <-  {m['from']}" for m in moved), encoding="utf-8")
    except OSError:
        pass
    return {"ok": True, "moved": len(moved), "folder": str(dest), "files": moved,
            "message": f"Done. {len(moved)} duplicate copies moved to {dest}. Nothing was deleted."}
