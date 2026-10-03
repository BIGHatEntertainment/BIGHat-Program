"""alpha.73: the secure credential ledger.

  <AppData>/secure/credentials.ledger      encrypted, append-only history of every login change
  <AppData>/secure/ledger.key              the key (owner-only file permissions)

What goes in: email, role, bcrypt HASH, who/when/why.  NEVER a readable password.
What it is for: (1) a tamper-evident history, (2) recovery - if system_config.json loses its users, they are rebuilt from here.

Honest limits: this keeps the file unreadable to other Windows users and to anyone who copies the Documents folder or
a backup of the config.  It is not a hardware vault: someone running as the SAME Windows user on the SAME PC can open both
the key and the file, like any desktop app.
"""
from __future__ import annotations

import hashlib
import json
import os
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from cryptography.fernet import Fernet, InvalidToken

from native import data_map

LEDGER_NAME = "credentials.ledger"
KEY_NAME = "ledger.key"


def _dir() -> Path:
    d = data_map.secure_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d


def _restrict(path: Path) -> None:
    """Owner-only. On Windows chmod only clears read-only, so the real protection there is the per-user AppData folder."""
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass


def _fernet() -> Fernet:
    kp = _dir() / KEY_NAME
    if not kp.exists():
        tmp = kp.with_suffix(".tmp")
        tmp.write_bytes(Fernet.generate_key())
        _restrict(tmp)
        os.replace(tmp, kp)
    return Fernet(kp.read_bytes().strip())


def _path() -> Path:
    return _dir() / LEDGER_NAME


def _read_events() -> List[Dict[str, Any]]:
    p = _path()
    if not p.exists():
        return []
    f = _fernet()
    out: List[Dict[str, Any]] = []
    for line in p.read_bytes().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(f.decrypt(line)))
        except (InvalidToken, ValueError):
            out.append({"event": "unreadable_line"})        # never crash on a damaged line; keep going
    return out


def _chain(prev_hash: str, body: Dict[str, Any]) -> str:
    return hashlib.sha256((prev_hash + json.dumps(body, sort_keys=True)).encode("utf-8")).hexdigest()


def record(event: str, email: str, *, role: Optional[str] = None, password_hash: Optional[str] = None,
           by: str = "system", extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Append one event.  `password_hash` must already be a bcrypt hash - a readable password is refused."""
    if password_hash is not None and not password_hash.startswith(("$2a$", "$2b$", "$2y$")):
        raise ValueError("ledger only stores bcrypt hashes, never a readable password")
    events = _read_events()
    prev = events[-1].get("hash", "") if events else ""
    body = {"event": event, "email": (email or "").strip().lower(), "role": role, "password_hash": password_hash,
            "by": by, "at": datetime.now(timezone.utc).isoformat(), "extra": extra or {}}
    body["hash"] = _chain(prev, {k: v for k, v in body.items() if k != "hash"})
    f = _fernet()
    p = _path()
    with open(p, "ab") as fh:
        fh.write(f.encrypt(json.dumps(body).encode("utf-8")) + b"\n")
    _restrict(p)
    return body


def history(email: Optional[str] = None) -> List[Dict[str, Any]]:
    """Events, newest last, WITHOUT the hashes (for showing a person what happened)."""
    ev = _read_events()
    if email:
        e = email.strip().lower()
        ev = [x for x in ev if x.get("email") == e]
    return [{k: v for k, v in x.items() if k not in ("password_hash", "hash")} for x in ev]


def current() -> Dict[str, Dict[str, Any]]:
    """Latest known state per email, replaying the ledger: {email: {role, password_hash}}.  Deleted users are gone."""
    state: Dict[str, Dict[str, Any]] = {}
    for x in _read_events():
        e = x.get("email")
        if not e:
            continue
        if x.get("event") == "removed":
            state.pop(e, None)
        elif x.get("event") in ("created", "password_set", "role_changed", "imported"):
            cur = state.setdefault(e, {"role": None, "password_hash": None})
            if x.get("role"):
                cur["role"] = x["role"]
            if x.get("password_hash"):
                cur["password_hash"] = x["password_hash"]
    return state


def verify_chain() -> Dict[str, Any]:
    """Has anyone edited, removed or reordered a line?"""
    events = _read_events()
    prev = ""
    for i, x in enumerate(events):
        if x.get("event") == "unreadable_line":
            return {"ok": False, "broken_at": i, "reason": "unreadable"}
        body = {k: v for k, v in x.items() if k != "hash"}
        if x.get("hash") != _chain(prev, body):
            return {"ok": False, "broken_at": i, "reason": "chain_mismatch"}
        prev = x["hash"]
    return {"ok": True, "events": len(events)}


def sync_from_config(users: List[Dict[str, Any]], by: str = "system") -> int:
    """Compare the live users list with the ledger and record what changed.  Returns events written.
    Called every time the config is saved, so no code path can change a login without the ledger noticing."""
    live: Dict[str, Dict[str, Any]] = {}
    for u in users or []:
        e = (u.get("email") or "").strip().lower()
        if e and u.get("password_hash"):
            live[e] = u
    known = current()
    n = 0
    for e, u in live.items():
        role = u.get("role")
        h = u.get("password_hash")
        if e not in known:
            record("created", e, role=role, password_hash=h, by=by)
            n += 1
            continue
        if known[e].get("password_hash") != h:
            record("password_set", e, role=role, password_hash=h, by=by)
            n += 1
        if role and known[e].get("role") != role:
            record("role_changed", e, role=role, by=by, extra={"from": known[e].get("role")})
            n += 1
    for e in list(known):
        if e not in live:
            record("removed", e, by=by)
            n += 1
    return n


def restore_users(existing_emails: List[str]) -> List[Dict[str, Any]]:
    """Users the ledger knows about that are NOT in the config (e.g. the config lost them).  Used for recovery."""
    have = {(e or "").strip().lower() for e in existing_emails}
    out = []
    for e, st in current().items():
        if e not in have and st.get("password_hash"):
            out.append({"email": e, "role": st.get("role") or "host", "password_hash": st["password_hash"]})
    return out
