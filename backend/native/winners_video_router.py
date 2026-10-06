"""alpha.87: the three bundled winners videos (1st / 2nd / 3rd place).
Open route (a <video> tag cannot send a login token). Only three fixed names
are served, so no other file can be requested."""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from native_slides import bundled_asset_path

router = APIRouter()
_NAMES = {"1st", "2nd", "3rd"}


def winners_video_url(place: str) -> str:
    return f"/api/native/winners-video/{place}"


def _parse_range(header: str, size: int):
    """'bytes=0-99' -> (0, 99). Returns None if it is not a usable range."""
    try:
        unit, _, spec = header.partition("=")
        if unit.strip().lower() != "bytes" or "," in spec:
            return None
        start_s, _, end_s = spec.strip().partition("-")
        if start_s == "":                      # suffix: last N bytes
            n = int(end_s)
            if n <= 0:
                return None
            return max(0, size - n), size - 1
        start = int(start_s)
        end = int(end_s) if end_s else size - 1
        end = min(end, size - 1)
        if start > end or start >= size:
            return None
        return start, end
    except ValueError:
        return None


@router.get("/native/winners-video/{place}")
async def get_winners_video(place: str, request: Request):
    if place not in _NAMES:
        raise HTTPException(404, detail="not found")
    p = bundled_asset_path("assets", "slides", "winners", f"place_{place}.mp4")
    if p is None:
        raise HTTPException(404, detail="video missing")
    data = p.read_bytes()
    size = len(data)
    base = {"Accept-Ranges": "bytes", "Cache-Control": "public, max-age=86400"}
    rng = request.headers.get("range")
    if rng:
        r = _parse_range(rng, size)
        if r is None:
            return Response(status_code=416, headers={**base, "Content-Range": f"bytes */{size}"})
        start, end = r
        return Response(data[start:end + 1], status_code=206, media_type="video/mp4",
                        headers={**base, "Content-Range": f"bytes {start}-{end}/{size}"})
    return Response(data, media_type="video/mp4", headers=base)
