"""Program -> Cloud: send this PC's own rounds to the Cloud so the Cloud can STAMP them (PR 3 of the one-source-of-truth work).

The Cloud's Files area stamps a round with a permanent round_uid (and keeps one stamp per round). A round that exists only on this PC has no
stamp, so a Cloud-built show cannot use it. This module offers those rounds to the Cloud, on the host's request only.

Safety rules (the owner has zero tolerance for silent data loss, on this PC or in the Cloud):
  * CHECK is read-only and lists exactly what would go up. UPLOAD sends only what that same check listed (it needs the check's token).
  * Only UNSTAMPED round files of a known type go up. A stamped round is already the Cloud's.
  * A round whose name matches one the Cloud already holds is NEVER sent: the Cloud would REPLACE that round and every other PC would then
    pull the changed copy. Those are listed as "name already in the Cloud" for the owner to decide.
  * The PC NEVER deletes, moves or overwrites a local file here. The stamped copy comes back through the normal file pull (PR 1 files it by
    its stamp); the plain copy is then an exact duplicate that the duplicate check (PR 2) offers to move aside.
  * One file at a time, written to the state file after each; a failure stops the run and nothing already sent is lost or repeated.
  * Offline / not linked / lapsed subscription: nothing is sent and it says why.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

import round_uid
import round_usage
from . import cloud_files, cloud_link

logger = logging.getLogger("bighat.cloud_upload")
MAX_BYTES = 50 * 1024 * 1024
UPLOAD_PATH = "/api/program/files/upload"
_LOCK = asyncio.Lock()


def _keys(name: str) -> set:
    return round_usage.same_round_keys(name)


def _pool_rel(p: Path) -> str:
    import presentation_builder as pb
    try:
        return p.relative_to(pb._docs_root()).as_posix()
    except ValueError:
        return p.name


def _plan_from(files: List[Path], cloud_names: List[str], already_sent: Dict[str, str]) -> Dict[str, Any]:
    cloud_keys = set()
    for n in cloud_names:
        cloud_keys |= _keys(n)
    send, clash, big, sent = [], [], [], []
    for f in files:
        if round_uid.read_uid(f):
            continue                                           # stamped: already the Cloud's identity
        try:
            size = f.stat().st_size
            sha = hashlib.sha256(f.read_bytes()).hexdigest()
        except OSError:
            continue
        row = {"file": f.name, "type": f.parent.name.upper(), "path": _pool_rel(f), "size": size, "sha256": sha}
        if already_sent.get(row["path"]) == sha:
            sent.append(row)                                   # this exact file was already uploaded; waiting for its stamped copy
        elif size > MAX_BYTES:
            big.append(row)
        elif _keys(f.name) & cloud_keys:
            clash.append(row)
        else:
            send.append(row)
    return {"send": send, "name_in_cloud": clash, "too_large": big, "already_sent": sent}


def _digest(plan: Dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(sorted((r["path"], r["sha256"]) for r in plan["send"])).encode()).hexdigest()[:24]


def _state_path() -> Path:
    return cloud_files._path().with_name("cloud_upload.json")


def _read_state() -> Dict[str, Any]:
    try:
        d = json.loads(_state_path().read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {"sent": {}}
    except (OSError, ValueError):
        return {"sent": {}}


def _write_state(st: Dict[str, Any]) -> None:
    cloud_files._atomic_write(_state_path(), json.dumps(st, indent=1).encode("utf-8"))


async def check(db=None) -> Dict[str, Any]:
    """Read-only. What would go up, what would not, and why."""
    if not cloud_link.get_token() or not cloud_link.cloud_base_url():
        return {"ok": False, "error": "not_linked", "message": "This computer is not linked to BIG Hat Cloud, so there is nothing to upload to."}
    m = await cloud_files._fetch_manifest()
    if not m["ok"]:
        why = {"unreachable": "Could not reach the Cloud.", "subscription_lapsed": "The Cloud subscription has lapsed.",
               "unauthorized": "The Cloud did not accept this computer's access key."}.get(m["error"], "The Cloud could not be read right now.")
        return {"ok": False, "error": m["error"], "message": why + " Nothing was sent."}
    names = [str(f.get("name") or "") for f in m["files"] if isinstance(f, dict) and f.get("category") == "bighat"]
    plan = _plan_from(round_uid.pool_files(), names, _read_state().get("sent", {}))
    out = {"ok": True, **{k: v for k, v in plan.items()}, "token": _digest(plan), "cloud_rounds": len(names),
           "can_upload": len(plan["send"])}
    parts = [f"{len(plan['send'])} to upload"]
    if plan["name_in_cloud"]:
        parts.append(f"{len(plan['name_in_cloud'])} not sent because a round with that name is already in the Cloud")
    if plan["already_sent"]:
        parts.append(f"{len(plan['already_sent'])} already sent, waiting for the stamped copy")
    out["message"] = ("Nothing to upload. " if not plan["send"] else "") + "; ".join(parts) + "."
    return out


async def _post(name: str, data: bytes) -> Dict[str, Any]:
    h = cloud_files._headers()
    if not h:
        return {"ok": False, "error": "unlinked"}
    try:
        async with httpx.AsyncClient(timeout=120.0) as c:
            r = await c.post(f"{cloud_link.cloud_base_url()}{UPLOAD_PATH}", headers=h,
                             files={"file": (name, data, "application/octet-stream")}, data={"category": "bighat"})
    except (httpx.HTTPError, ValueError):
        return {"ok": False, "error": "unreachable"}
    if r.status_code in (200, 201):
        try:
            return {"ok": True, "body": r.json() or {}}
        except ValueError:
            return {"ok": True, "body": {}}
    if r.status_code == 404:
        return {"ok": False, "error": "cloud_not_ready"}
    if r.status_code == 409:
        return {"ok": False, "error": "refused"}
    return {"ok": False, "error": cloud_files._error_for(r)}


async def upload(db, token: str) -> Dict[str, Any]:
    """Sends exactly the files the last check listed. Re-checks first: if anything changed since, nothing is sent."""
    if not token or not isinstance(token, str):
        return {"ok": False, "error": "no_token", "message": "Check first, then confirm."}
    if _LOCK.locked():
        return {"ok": False, "error": "busy", "message": "An upload is already running."}
    async with _LOCK:
        plan = await check(db)
        if not plan.get("ok"):
            return plan
        if plan["token"] != token:
            return {"ok": False, "error": "changed", "message": "The files or the Cloud changed since you checked. Nothing was sent. Check again."}
        st = _read_state()
        st.setdefault("sent", {})
        sent, refused = [], []
        for row in plan["send"]:
            p = _pool_root() / row["path"]
            try:
                data = p.read_bytes()
            except OSError:
                refused.append({"file": row["file"], "why": "could not be read"})
                continue
            if hashlib.sha256(data).hexdigest() != row["sha256"]:
                return {"ok": False, "error": "changed", "sent": sent, "message": f"{row['file']} changed while uploading. Stopped safely; nothing was removed."}
            res = await _post(row["file"], data)
            if res["ok"]:
                st["sent"][row["path"]] = row["sha256"]
                _write_state(st)                              # after every file: a crash never repeats or loses one
                sent.append(row["file"])
            elif res["error"] == "refused":
                refused.append({"file": row["file"], "why": "the Cloud refused it (its round id belongs to another round)"})
            else:
                msg = {"cloud_not_ready": "The Cloud does not accept uploads from this program yet. Nothing was sent.",
                       "unreachable": "The Cloud stopped answering. Stopped safely.", "subscription_lapsed": "The Cloud subscription has lapsed.",
                       "rate_limited": "The Cloud asked us to slow down. Try again shortly.", "unlinked": "This computer is no longer linked."}.get(res["error"], "The Cloud did not accept the upload.")
                return {"ok": False, "error": res["error"], "sent": sent, "refused": refused, "message": f"{msg} {len(sent)} sent before it stopped. Nothing local was changed."}
        if sent:
            asyncio.create_task(_pull_soon(db))
        return {"ok": True, "sent": sent, "refused": refused,
                "message": f"Sent {len(sent)} round(s) to the Cloud for stamping. The stamped copies arrive on the next file sync."
                           + (f" {len(refused)} could not be sent." if refused else "") + " Nothing on this computer was changed."}


def _pool_root() -> Path:
    import presentation_builder as pb
    return pb._docs_root()


async def _pull_soon(db) -> None:
    try:
        await asyncio.sleep(2)
        await cloud_files.pull_once(db)
    except Exception as e:                                     # noqa: BLE001
        logger.warning("[cloud-upload] follow-up pull failed: %s", e)
