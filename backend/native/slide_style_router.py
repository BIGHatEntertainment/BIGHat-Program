"""/api/native/slide-style/* : global + per-location trivia slide style."""
from typing import Any, Dict

from fastapi import APIRouter, Body, HTTPException, Request

import slide_style
from . import locations_router as lr

router = APIRouter(prefix="/native", tags=["native-slide-style"])


@router.get("/slide-style/global")
async def get_global(request: Request) -> Dict[str, Any]:
    await lr._require_admin_or_master(request)
    return slide_style.load_global()


@router.put("/slide-style/global")
async def put_global(request: Request, payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    await lr._require_master(request)
    return slide_style.save_global(payload.get("background"))


@router.get("/locations/{location_id}/slide-style")
async def get_location_style(location_id: str, request: Request) -> Dict[str, Any]:
    _, loc = await lr._require_location_access(location_id, request)
    out = slide_style.load_location(loc["slug"])
    out["global"] = slide_style.load_global()["background"]
    return out


@router.put("/locations/{location_id}/slide-style")
async def put_location_style(location_id: str, request: Request,
                             payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    _, loc = await lr._require_location_access(location_id, request)
    return slide_style.save_location(
        loc["slug"], payload.get("use_global", True), payload.get("background"),
    )
