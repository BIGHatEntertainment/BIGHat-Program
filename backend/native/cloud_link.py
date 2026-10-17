"""Cloud link: this PC's permanent 6-character code and its cloud access key.

Contract (set by BIGHat-Cloud, routes/program_routes.py). The program always talks first:
  1. announce     POST {cloud}/api/program/announce     {code, license_key, name, app_version}
  2. owner types the code in the Cloud app (Settings). It links only if the license key matches their account.
  3. claim-token  POST {cloud}/api/program/claim-token  {code, license_key} -> the access key, handed over ONCE.

Storage (survives updates, restarts and webview cache clears, same rules as the legal record and the credential ledger):
  <AppData>/secure/cloud_link.json   the code, link state, program_id, and the access key ENCRYPTED with the
                                     same Fernet key file the credential ledger uses (owner-only file).
Writes are atomic (temp file + os.replace). A bad or half-written file is never overwritten with an empty one:
an unreadable file is kept as cloud_link.json.bad and the code is rebuilt from it when possible.

The code is a label, not a secret. The license key is what proves the program and the account belong together.
The access key is NEVER returned to the browser, never logged, never written to the config or the database.
"""
from __future__ import annotations

import json
import logging
import os
import secrets
import stat
import sys
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import httpx
from cryptography.fernet import Fernet, InvalidToken

from native import data_map

logger = logging.getLogger("bighat-cloud-link")

# Same alphabet as the cloud (no 0 O 1 I L).
CODE_CHARS = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
FILE_NAME = "cloud_link.json"
KEY_NAME = "ledger.key"            # shared with credential_ledger.py on purpose: one key file to protect
_LOCK = threading.Lock()


def cloud_base_url() -> str:
    """Empty until the Cloud app is deployed. Order: env BIGHAT_CLOUD_BASE_URL > system config cloud_base_url."""
    url = os.environ.get("BIGHAT_CLOUD_BASE_URL", "").strip()
    if not url:
        try:
            from native.config import config_manager
            url = str((config_manager.config or {}).get("cloud_base_url", "") or "").strip()
        except Exception:
            url = ""
    return url.rstrip("/")


def _dir() -> Path:
    """<AppData>/secure. In the installed program the launcher pins BIGHAT_DATA_ROOT into the per-user data folder
    (%LOCALAPPDATA%\\BIGHat\\data\\app), so this survives updates. Refuse to write inside the program's own install
    folder: anything there is wiped by the next update, which would silently change this PC's code."""
    d = data_map.secure_dir()
    install = Path(__file__).resolve().parent.parent
    try:
        inside = d.resolve().is_relative_to(install)
    except (OSError, ValueError):
        inside = False
    if inside and getattr(sys, "frozen", False):
        raise RuntimeError("cloud link: refusing to store in the install folder")
    d.mkdir(parents=True, exist_ok=True)
    return d


def _path() -> Path:
    return _dir() / FILE_NAME


def _restrict(path: Path) -> None:
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


def new_code() -> str:
    return "".join(secrets.choice(CODE_CHARS) for _ in range(6))


def _app_version() -> str:
    here = Path(__file__).resolve().parent.parent
    for p in (here / "VERSION.txt", here.parent / "VERSION.txt"):
        try:
            v = p.read_text(encoding="utf-8").strip()
            if v:
                return v
        except OSError:
            continue
    return "unknown"


def _read() -> Optional[Dict[str, Any]]:
    p = _path()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        try:                                   # keep the damaged file; never silently replace it
            os.replace(p, p.with_suffix(".json.bad"))
        except OSError:
            pass
        return None


def _write(rec: Dict[str, Any]) -> None:
    path = _path()
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".cloudlink_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(rec, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        _restrict(Path(tmp))
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def get_or_create() -> Dict[str, Any]:
    """The permanent record. The code is made once and never changes on its own."""
    with _LOCK:
        rec = _read()
        if rec and isinstance(rec.get("code"), str) and len(rec["code"]) == 6:
            return rec
        # An unreadable file was moved to .bad above; if it held a code, keep it.
        code = ""
        bad = _path().with_suffix(".json.bad")
        try:
            old = json.loads(bad.read_text(encoding="utf-8"))
            if isinstance(old, dict) and isinstance(old.get("code"), str) and len(old["code"]) == 6:
                code = old["code"]
        except (OSError, ValueError):
            pass
        rec = {"code": code or new_code(), "created_at": datetime.now(timezone.utc).isoformat(),
               "status": "not_linked", "program_id": None, "token_enc": None, "linked_at": None, "last_check": None}
        _write(rec)
        return rec


def _save(**changes: Any) -> Dict[str, Any]:
    """Update the record. Always starts from the stored record so the permanent code can never change here."""
    rec = get_or_create()
    with _LOCK:
        rec = _read() or rec
        rec.update(changes)
        _write(rec)
        return rec


def public_view() -> Dict[str, Any]:
    """Everything the screen may see. The access key is never included."""
    rec = get_or_create()
    return {
        "code": rec["code"],
        "status": rec.get("status", "not_linked"),
        "linked_at": rec.get("linked_at"),
        "last_check": rec.get("last_check"),
        "has_token": bool(rec.get("token_enc")),
        "cloud_configured": bool(cloud_base_url()),
    }


def get_token() -> Optional[str]:
    """For the program's own future sync calls only. Never expose through an API."""
    rec = _read()
    enc = rec.get("token_enc") if rec else None
    if not enc:
        return None
    try:
        return _fernet().decrypt(enc.encode("utf-8")).decode("utf-8")
    except (InvalidToken, ValueError):
        logger.warning("cloud link: stored access key could not be decrypted")
        return None


def _license_key() -> str:
    from native.config import config_manager
    return str(((config_manager.config or {}).get("license_status") or {}).get("key") or "").strip().upper()


async def _post(path: str, body: dict) -> dict:
    base = cloud_base_url()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(f"{base}{path}", json=body)
        if r.status_code == 429:
            return {"ok": False, "error": "too_many_attempts"}
        if r.status_code >= 400:
            return {"ok": False, "error": "rejected", "status_code": r.status_code}
        data = r.json()
        return {"ok": True, **(data if isinstance(data, dict) else {})}
    except (httpx.HTTPError, ValueError):
        return {"ok": False, "error": "unreachable"}


async def check() -> Dict[str, Any]:
    """Announce this PC, then collect the access key once the owner has linked it. Safe to call repeatedly."""
    rec = get_or_create()
    if not cloud_base_url():
        return {**public_view(), "message": "The cloud app is not available yet."}
    key = _license_key()
    if not key:
        return {**public_view(), "message": "Enter your product key first (Admin, Product Key)."}
    name = (os.environ.get("COMPUTERNAME") or "").strip()[:60]
    ann = await _post("/api/program/announce", {"code": rec["code"], "license_key": key, "name": name, "app_version": _app_version()})
    now = datetime.now(timezone.utc).isoformat()
    if not ann.get("ok"):
        _save(last_check=now)
        return {**public_view(), "message": "Could not reach the cloud. Your link is unchanged."}
    if rec.get("token_enc"):                       # already holds its key: nothing more to collect
        _save(last_check=now, status="linked")
        return {**public_view(), "message": "Linked."}
    if ann.get("status") != "linked":
        _save(last_check=now, status="waiting")
        return {**public_view(), "message": "Waiting for you to enter this code in the cloud app."}
    claim = await _post("/api/program/claim-token", {"code": rec["code"], "license_key": key})
    if claim.get("ok") and claim.get("status") == "linked" and claim.get("token"):
        enc = _fernet().encrypt(str(claim["token"]).encode("utf-8")).decode("utf-8")
        _save(token_enc=enc, program_id=claim.get("program_id"), status="linked", linked_at=now, last_check=now)
        return {**public_view(), "message": "Linked."}
    if claim.get("status") == "already_claimed":
        _save(status="linked", last_check=now)     # linked, but the one-time key was taken earlier
        return {**public_view(), "message": "Linked. The access key was already issued to this code."}
    _save(last_check=now, status="waiting")
    return {**public_view(), "message": "Waiting for you to enter this code in the cloud app."}
