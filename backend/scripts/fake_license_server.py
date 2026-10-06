"""Tiny stand-in for api.bighat.live, ONLY for local real-app tests.
Keys: BHE-AAAA-BBBB-CCCC-DDDD = base program; BHE-EEEE-FFFF-GGGG-HHHH = Music Bingo add-on;
BHE-KKKK-KKKK-KKKK-KKKK = Karaoke add-on; anything else = rejected. Port from argv[1]."""
import sys
from fastapi import FastAPI, HTTPException
import uvicorn

app = FastAPI()
KEYS = {
    "BHE-AAAA-BBBB-CCCC-DDDD": dict(owns_standalone=True),
    "BHE-EEEE-FFFF-GGGG-HHHH": dict(owns_music_bingo=True),
    "BHE-KKKK-KKKK-KKKK-KKKK": dict(owns_karaoke=True),
}
REVOKED = set()

def answer(key):
    if key in REVOKED or key not in KEYS:
        raise HTTPException(status_code=400, detail="key not found or revoked")
    base = dict(ok=True, owns_standalone=False, owns_music_bingo=False, owns_karaoke=False,
                cloud_library_active=False, cloud_library_expires_at=None, revalidate_after=None,
                max_seats=5, active_seats=1)
    base.update(KEYS[key]); return base

@app.post("/api/license/activate")
async def activate(b: dict): return answer(b["key"])

@app.post("/api/license/validate")
async def validate(b: dict): return answer(b["key"])

@app.post("/revoke/{key}")
async def revoke(key: str): REVOKED.add(key); return {"revoked": key}

uvicorn.run(app, host="127.0.0.1", port=int(sys.argv[1]), log_level="warning")
