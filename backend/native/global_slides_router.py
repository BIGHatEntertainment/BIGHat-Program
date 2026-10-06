"""/api/native/global-slides/* : company, rules and Format slide settings.
Read: any signed-in user (previews). Write: Admin / Master Admin."""
from typing import Any, Dict

from fastapi import APIRouter, Body, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

import global_slides as gs

router = APIRouter(prefix="/native", tags=["native-global-slides"])


async def _user(request: Request) -> Dict[str, Any]:
    try:
        from server import get_current_user
        u = await get_current_user(request)
    except Exception:
        raise HTTPException(401, detail="Sign in required")
    if not u:
        raise HTTPException(401, detail="Sign in required")
    return u


async def _admin(request: Request) -> Dict[str, Any]:
    u = await _user(request)
    if u.get("role") not in ("admin", "master_admin"):
        raise HTTPException(403, detail="Admin access required")
    return u


@router.get("/global-slides")
async def get_settings(request: Request) -> Dict[str, Any]:
    await _user(request)
    return gs.load()


@router.put("/global-slides")
async def put_settings(request: Request, payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    await _admin(request)
    cur = gs.load()
    # only the toggles / order are editable here; files go through upload/delete
    for k in ("company", "rules", "sponsors"):
        if isinstance(payload.get(k), dict):
            if "enabled" in payload[k]:
                cur[k]["enabled"] = bool(payload[k]["enabled"])
            if isinstance(payload[k].get("images"), list):
                keep = [f for f in payload[k]["images"] if f in cur[k]["images"]]
                keep += [f for f in cur[k]["images"] if f not in keep]   # never drop files via reorder
                cur[k]["images"] = keep
    if isinstance(payload.get("format"), dict):
        for key in ("enabled", "show_themes"):
            if key in payload["format"]:
                cur["format"][key] = bool(payload["format"][key])
    return gs.save(cur)


@router.post("/global-slides/{kind}/upload")
async def upload(kind: str, request: Request, file: UploadFile = File(...)) -> Dict[str, Any]:
    await _admin(request)
    data = await file.read()
    try:
        return gs.add_image(kind, file.filename or "", data)
    except ValueError as e:
        raise HTTPException(400, detail=str(e))


@router.delete("/global-slides/file/{name}")
async def delete_file(name: str, request: Request) -> Dict[str, Any]:
    await _admin(request)
    try:
        return gs.remove_image(name)
    except ValueError as e:
        raise HTTPException(400, detail=str(e))


@router.get("/global-slides/file/{name}")
async def get_file(name: str, request: Request):
    await _user(request)
    p = gs.image_path(name)
    if p is None:
        raise HTTPException(404, detail="not found")
    return FileResponse(p)
