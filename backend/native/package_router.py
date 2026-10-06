"""Setup Package routes (alpha.85). Admin Settings > Integrations > Setup Package."""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import Response

from . import package_client, setup_package
from .config import config_manager

logger = logging.getLogger("bighat-package-router")
router = APIRouter(prefix="/native/setup-package", tags=["setup-package"])

_db = None
_MAX_UPLOAD = 60 * 1024 * 1024


def set_db(db) -> None:
    global _db
    _db = db


def _need_db():
    if _db is None:
        raise HTTPException(status_code=503, detail="not_ready")
    return _db


async def _master(request: Request):
    from .admin_router import _require_master_admin
    return await _require_master_admin(request)


async def _admin(request: Request):
    from server import require_admin  # type: ignore
    return await require_admin(request)


def _state() -> Dict[str, Any]:
    return config_manager.config.setdefault("setup_package", {})


def _remember(version, digest, via: str) -> None:
    s = _state()
    s.update(version=int(version) if str(version or "").isdigit() else None, hash=digest, pulled_at=datetime.now(timezone.utc).isoformat(), via=via)
    config_manager.save_config()


def _err(res: Dict[str, Any]):
    """Turn a client failure into the same shape every time: plain message, never a stack trace."""
    return {"ok": False, "error": res.get("error"), "message": res.get("message") or "That did not work."}


# ---------------------------------------------------------------- check
@router.get("/check")
async def check(_=Depends(_admin)):
    """Is a package waiting, and does this computer already match it? (Never changes anything.)"""
    db = _need_db()
    st = await package_client.status()
    if not st.get("ok"):
        return {**_err(st), "reachable": st.get("error") not in ("offline", "timeout")}
    mine = _state()
    out = {"ok": True, "exists": st.get("exists", False), "version": st.get("version"), "published_at": st.get("published_at"),
           "published_by": st.get("published_by"), "counts": st.get("counts"), "this_computer_version": mine.get("version"), "differs": None}
    if st.get("exists"):
        if mine.get("hash") == st.get("hash"):
            out["differs"] = False                                  # pulled exactly this one before
        else:
            out["differs"] = True
            out["note"] = "This computer does not match the latest setup. Ask the master admin to pull it, or call them for help."
    return out


# ---------------------------------------------------------------- publish (master)
@router.post("/publish")
async def publish(_=Depends(_master)):
    db = _need_db()
    raw = await setup_package.build_package(db)
    res = await package_client.publish(raw, expected_version=str(_state().get("version") or ""), machine_label=config_manager.config.get("machine_name", "") or "")
    if not res.get("ok"):
        return _err(res)
    _remember(res.get("version"), res.get("hash"), "published")
    return {"ok": True, "version": res.get("version"), "counts": res.get("counts"), "size": res.get("size")}


# ---------------------------------------------------------------- pull (preview, then apply)
@router.post("/pull")
async def pull(apply: bool = False, overwrite_changed: bool = False, _=Depends(_admin)):
    """apply=false: download and show what WOULD change. apply=true: write it in."""
    db = _need_db()
    res = await package_client.pull()
    if not res.get("ok"):
        return _err(res)
    try:
        plan = await setup_package.plan_apply(db, res["raw"])
    except Exception:
        return {"ok": False, "error": "bad_package", "message": "The setup package could not be read."}
    if not apply:
        return {"ok": True, "applied": False, "version": res.get("version"), "plan": plan}
    try:
        done = await setup_package.apply_package(db, res["raw"], overwrite_changed=overwrite_changed)
    except Exception as e:                             # noqa: BLE001
        logger.exception("setup package apply failed")
        return {"ok": False, "error": "apply_failed", "message": "The setup could not be applied. Nothing more was changed after the problem."}
    _remember(res.get("version"), res.get("hash"), "pulled")
    return {"ok": True, "applied": True, "version": res.get("version"), "result": done}


# ---------------------------------------------------------------- file fallback (option A)
@router.get("/export")
async def export_file(_=Depends(_master)):
    """Download the package as a file to carry to another computer."""
    raw = await setup_package.build_package(_need_db())
    name = f"bighat-setup-{datetime.now().strftime('%Y-%m-%d')}.bighatsetup"
    return Response(content=raw, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.post("/import")
async def import_file(apply: bool = False, overwrite_changed: bool = False, file: UploadFile = File(...), _=Depends(_admin)):
    db = _need_db()
    raw = await file.read(_MAX_UPLOAD + 1)
    if len(raw) > _MAX_UPLOAD:
        return {"ok": False, "error": "too_big", "message": "That file is too big to be a setup package."}
    try:
        plan = await setup_package.plan_apply(db, raw)
    except Exception:
        return {"ok": False, "error": "bad_package", "message": "That file is not a BIG Hat setup package."}
    if not apply:
        return {"ok": True, "applied": False, "plan": plan}
    try:
        done = await setup_package.apply_package(db, raw, overwrite_changed=overwrite_changed)
    except Exception:
        logger.exception("setup package file import failed")
        return {"ok": False, "error": "apply_failed", "message": "The setup could not be applied."}
    _remember(None, hashlib.sha256(raw).hexdigest(), "file")
    return {"ok": True, "applied": True, "result": done}


# ---------------------------------------------------------------- move to another email (master)
@router.post("/transfer/start")
async def transfer_start(payload: Dict[str, Any] = Body(...), _=Depends(_master)):
    res = await package_client.transfer_start(str(payload.get("to_email") or ""))
    return _err(res) if not res.get("ok") else {"ok": True, "sent_to": res.get("sent_to"), "valid_minutes": res.get("valid_minutes")}


@router.post("/transfer/confirm")
async def transfer_confirm(payload: Dict[str, Any] = Body(...), _=Depends(_master)):
    res = await package_client.transfer_confirm(str(payload.get("code") or ""))
    return _err(res) if not res.get("ok") else {"ok": True, "moved_to": res.get("moved_to")}
