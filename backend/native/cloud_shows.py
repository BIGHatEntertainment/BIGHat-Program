"""Cloud show bundles (docs/CLOUD_TASK_trivia_wizard_4_export_and_program_pull.md, docs/PROGRAM_TASK_cloud_show_import.md).

A bundle is a ZIP: manifest.json (type "trivia-show-bundle"), payload.json (host, location, ordered rounds) and
rounds/<TYPE>/<file>.bighat (the round files, each itself a ZIP). Importing one unpacks the rounds into Files/Trivia/<TYPE>/
and writes the show exactly like the Build Wizard, so the Presenter lists it ready to host.

Rules:
  * EVERYTHING is checked before anything is written: manifest, host, venue, slot order, every round file present and a valid ZIP.
  * host is matched by EMAIL, the venue by the venue-name rule. If either is missing NOTHING is imported and the answer says which.
  * the 180-day lock starts HERE (owner decision 2026-10-25), through presentation_builder (record_usage). A round already locked at the
    venue stops the import with the list, unless allow_locked is sent after an admin agreed.
  * a failure part-way removes ONLY what this import created (new round files, the show file). Nothing existing is ever overwritten:
    a different file with the same name is kept as name-<8 hex>.
"""
import hashlib
import io
import json
import logging
import re
import uuid
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from . import cloud_link

logger = logging.getLogger("bighat-cloud-shows")
MAX_BUNDLE = 60 * 1024 * 1024            # the Cloud's cap
TYPES = ("MC", "REG", "MISC", "MYS", "BIG")


class ShowImportError(Exception):
    def __init__(self, code: str, message: str, **extra: Any):
        super().__init__(message)
        self.code, self.message, self.extra = code, message, extra

    def public(self) -> Dict[str, Any]:
        return {"ok": False, "code": self.code, "message": self.message, **self.extra}


def _key(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def _safe_member(name: str) -> bool:
    n = name.replace("\\", "/")
    return not (n.startswith("/") or ".." in n.split("/") or re.match(r"^[A-Za-z]:", n))


def read_bundle(data: bytes) -> Dict[str, Any]:
    """Parse and fully check a bundle. Returns {manifest, payload, rounds:[{order,type,name,file,bytes}]}. Writes nothing."""
    if len(data) > MAX_BUNDLE:
        raise ShowImportError("too_big", "This show file is larger than 60 MB.")
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise ShowImportError("not_a_bundle", "This is not a BIG Hat show file (not a ZIP).")
    names = zf.namelist()
    if any(not _safe_member(n) for n in names):
        raise ShowImportError("unsafe", "This show file has unsafe file paths and was not opened.")
    try:
        manifest = json.loads(zf.read("manifest.json").decode("utf-8-sig"))
        payload = json.loads(zf.read("payload.json").decode("utf-8-sig"))
    except (KeyError, ValueError):
        raise ShowImportError("not_a_bundle", "This show file is missing its manifest or payload.")
    if manifest.get("type") != "trivia-show-bundle":
        raise ShowImportError("not_a_bundle", f"This is not a trivia show bundle (type {manifest.get('type')!r}).")
    if int(manifest.get("version") or 0) > 1:
        raise ShowImportError("newer", "This show was made by a newer version of BIG Hat. Update the program and try again.")
    spec = payload.get("rounds") or []
    count = int(payload.get("round_count") or len(spec))
    if count not in (5, 6) or len(spec) != count:
        raise ShowImportError("bad_rounds", f"A show needs 5 or 6 rounds; this one lists {len(spec)}.")
    import presentation_builder as pb
    types = [str(r.get("type") or "").upper() for r in sorted(spec, key=lambda r: r.get("order", 0))]
    try:
        pb.validate_round_sequence(types)
    except Exception as e:                                           # noqa: BLE001
        raise ShowImportError("bad_rounds", f"The round order is not valid: {e}")
    rounds: List[Dict[str, Any]] = []
    for r in sorted(spec, key=lambda r: r.get("order", 0)):
        member = str(r.get("file") or "")
        if member not in names:
            raise ShowImportError("missing_round", f"Round {r.get('order')} ({r.get('name')}) is not inside the file.")
        blob = zf.read(member)
        if not zipfile.is_zipfile(io.BytesIO(blob)):
            raise ShowImportError("bad_round", f"Round {r.get('order')} ({r.get('name')}) is not a valid round file.")
        t = str(r.get("type") or "").upper()
        if t not in TYPES:
            raise ShowImportError("bad_rounds", f"Round {r.get('order')} has an unknown type {t!r}.")
        fn = Path(member).name
        if not fn.lower().endswith(".bighat"):
            raise ShowImportError("bad_round", f"Round {r.get('order')} ({fn}) is not a .bighat file.")
        rounds.append({"order": len(rounds) + 1, "type": t, "name": r.get("name") or Path(fn).stem, "file_name": fn, "bytes": blob})
    return {"manifest": manifest, "payload": payload, "rounds": rounds}


async def _find_host(db, payload: Dict[str, Any]) -> Dict[str, Any]:
    email = str((payload.get("host") or {}).get("email") or "").strip().lower()
    name = (payload.get("host") or {}).get("name") or "the host"
    if not email:
        raise ShowImportError("host_missing", f"The show has no host email, so {name} cannot be matched.", missing="host")
    try:
        import presentation_builder as pb
        h = pb._load_host(email)
        if h:
            return h
    except Exception:                                                # noqa: BLE001
        pass
    u = await db.users.find_one({"email": email}, {"_id": 0}) if hasattr(db, "users") else None
    if u:
        return {k: u.get(k) for k in ("id", "email", "name", "display_name", "first_name", "last_name") if u.get(k)} | {"id": u.get("id") or email}
    e = await db.employees.find_one({"email": email}, {"_id": 0})
    if e:
        return {"id": e.get("id") or email, "email": email, "name": e.get("name"), "display_name": e.get("name")}
    raise ShowImportError("host_missing", f"The host {name} ({email}) is not on this PC yet. Run a Cloud sync, then try again.", missing="host")


async def _find_location(db, payload: Dict[str, Any]) -> Dict[str, Any]:
    loc = payload.get("location") or {}
    name = loc.get("name") or ""
    want = _key(name)
    if not want:
        raise ShowImportError("venue_missing", "The show has no venue name.", missing="venue")
    for v in await db.venues.find({}, {"_id": 0}).to_list(5000):
        if _key(v.get("name")) == want:
            lid = v.get("location_id")
            l = await db.locations.find_one({"id": lid}, {"_id": 0}) if lid else None
            if l:
                return l
    for l in await db.locations.find({}, {"_id": 0}).to_list(5000):
        if _key(l.get("name")) == want:
            return l
    raise ShowImportError("venue_missing", f"The venue {name} is not on this PC yet. Run a Cloud sync, then try again.", missing="venue")


def _place(pool: Path, r: Dict[str, Any]) -> Path:
    """Where the round goes. Identical bytes already there = reuse; a different file with the same name = name-<8hex>."""
    dest = pool / r["file_name"]
    if not dest.exists():
        return dest
    if hashlib.sha256(dest.read_bytes()).hexdigest() == hashlib.sha256(r["bytes"]).hexdigest():
        return dest
    stem = Path(r["file_name"]).stem
    return pool / f"{stem}-{hashlib.sha256(r['bytes']).hexdigest()[:8]}.bighat"


async def import_bundle(db, data: bytes, *, allow_locked: bool = False, owner_email: Optional[str] = None) -> Dict[str, Any]:
    """Import one bundle. Never half-imports. Returns {ok, ...} (also for the expected refusals)."""
    import presentation_builder as pb
    try:
        b = read_bundle(data)
        host = await _find_host(db, b["payload"])
        loc = await _find_location(db, b["payload"])
        created: List[Path] = []
        try:
            refs: List[str] = []
            for r in b["rounds"]:
                pool = pb._round_pool_dir(r["type"])
                pool.mkdir(parents=True, exist_ok=True)
                dest = _place(pool, r)
                if not dest.exists():
                    dest.write_bytes(r["bytes"])
                    created.append(dest)
                refs.append(dest.relative_to(pb._docs_root()).as_posix())
            try:
                pres = pb.build_from_wizard(
                    name=str(b["manifest"].get("name") or b["payload"].get("name") or "Cloud show"), host_id=str(host.get("id") or host.get("email")),
                    location_id=str(loc.get("id") or loc.get("slug")), round_count=len(refs), round_files=refs,
                    owner_email=owner_email or host.get("email"), allow_locked=allow_locked)
            except pb.BuildValidationError as e:
                msg = str(e)
                if "locked for this location" in msg:
                    raise ShowImportError("locked", msg, can_override=True)
                raise ShowImportError("build_failed", msg)
            return {"ok": True, "id": pres.get("id"), "name": pres.get("name"), "location": loc.get("name"),
                    "host": host.get("display_name") or host.get("name") or host.get("email"), "rounds": len(refs),
                    "new_round_files": len(created), "plan_id": b["manifest"].get("plan_id")}
        except Exception:
            for p in created:                                        # undo ONLY what this import wrote
                try:
                    p.unlink()
                except OSError:
                    pass
            raise
    except ShowImportError as e:
        return e.public()
    except Exception as e:                                           # noqa: BLE001
        logger.error("cloud show import failed: %s: %s", type(e).__name__, e)
        return {"ok": False, "code": "error", "message": f"The import stopped safely ({type(e).__name__}). Nothing was changed."}


# ------------------------------------------------------------------ talking to the Cloud (list / download / report)
async def _get(path: str, params: Optional[dict] = None, raw: bool = False) -> Dict[str, Any]:
    tok, base = cloud_link.get_token(), cloud_link.cloud_base_url()
    if not tok or not base:
        return {"ok": False, "error": "unlinked", "message": "This computer is not linked to BIG Hat Cloud."}
    try:
        async with httpx.AsyncClient(timeout=120.0 if raw else 20.0) as c:
            r = await c.get(f"{base}{path}", params=params, headers={"Authorization": f"Bearer {tok}"})
    except (httpx.HTTPError, ValueError):
        return {"ok": False, "error": "unreachable", "message": "Could not reach the Cloud. Everything on this PC still works."}
    if r.status_code == 200:
        return {"ok": True, "content": r.content} if raw else {"ok": True, "data": r.json()}
    if r.status_code == 402:
        return {"ok": False, "error": "subscription_lapsed", "message": "The Cloud subscription has lapsed. Cloud shows are paused; this PC keeps working."}
    if r.status_code == 404:
        return {"ok": False, "error": "not_found", "message": "That show is no longer in the Cloud."}
    if r.status_code == 409:
        try:
            msg = r.json().get("detail") or ""
        except ValueError:
            msg = ""
        return {"ok": False, "error": "incomplete", "message": msg or "The show is missing rounds in the Cloud."}
    return {"ok": False, "error": "rejected", "message": "The Cloud could not give the show right now."}


async def list_shows() -> Dict[str, Any]:
    r = await _get("/api/program/trivia-plans")
    if not r["ok"]:
        return {**r, "shows": []}
    return {"ok": True, "shows": (r["data"] or {}).get("plans") or []}


async def pull_and_import(db, plan_id: str, allow_locked: bool = False, owner_email: Optional[str] = None) -> Dict[str, Any]:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", plan_id or ""):
        return {"ok": False, "code": "bad_id", "message": "That is not a valid show id."}
    r = await _get(f"/api/program/trivia-plans/{plan_id}/bighat", raw=True)
    if not r["ok"]:
        return {"ok": False, "code": r["error"], "message": r["message"]}
    out = await import_bundle(db, r["content"], allow_locked=allow_locked, owner_email=owner_email)
    if out.get("ok"):
        await report_imported(plan_id)                               # informational; a failure here is harmless
    return out


async def report_imported(plan_id: str) -> None:
    tok, base = cloud_link.get_token(), cloud_link.cloud_base_url()
    if not tok or not base:
        return
    try:
        async with httpx.AsyncClient(timeout=15.0) as c:
            await c.post(f"{base}/api/program/trivia-plans/{plan_id}/imported", json={}, headers={"Authorization": f"Bearer {tok}"})
    except Exception:                                                # noqa: BLE001
        pass
