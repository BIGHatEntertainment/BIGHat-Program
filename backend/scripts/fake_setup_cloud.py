"""Local stand-in for api.bighat.live: runs the REAL cloud/setup_package_router.py plus license activate/validate (alpha.85 tests only).
Every key BHE-AAAA-BBBB-CCCC-DDDD maps to owner@example.com. Port = argv[1]."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from fastapi import FastAPI, HTTPException
import uvicorn
from cloud import setup_package_router as sp

KEYS = {"BHE-AAAA-BBBB-CCCC-DDDD": "owner@example.com", "BHE-EEEE-FFFF-GGGG-HHHH": "owner@example.com", "BHE-1111-2222-3333-4444": "other@example.com"}


class Lic:
    def __init__(self, e): self.email = e


class Coll:
    def __init__(self): self.rows = []
    def _m(self, r, q): return all(r.get(k) == v for k, v in q.items())
    async def insert_one(self, d): self.rows.append(dict(d))
    async def find_one(self, q, proj=None):
        for r in self.rows:
            if self._m(r, q):
                o = dict(r)
                if proj and proj.get("blob") == 0: o.pop("blob", None)
                return o
    async def replace_one(self, q, d):
        for i, r in enumerate(self.rows):
            if self._m(r, q): self.rows[i] = dict(d); return
    async def update_one(self, q, u):
        for r in self.rows:
            if self._m(r, q): r.update(u.get("$set", {})); return
    async def delete_many(self, q): self.rows = [r for r in self.rows if not self._m(r, q)]


class DB:
    def __init__(self): self.setup_packages, self.setup_transfers = Coll(), Coll()


class Svc:
    async def validate(self, *, key, hwid):
        return (True, "ok", Lic(KEYS[key])) if key in KEYS else (False, "unknown_key", None)


class Mail:
    async def _send(self, **kw): return True


sp.set_runtime(service=Svc(), db=DB(), mailer=Mail())
sp.PUBLISH_MIN_SECONDS = 0
app = FastAPI(); app.include_router(sp.router)

def _lic(b):
    if b.get("key") not in KEYS: raise HTTPException(status_code=400, detail="key not found or revoked")
    return dict(ok=True, owns_standalone=True, owns_music_bingo=True, owns_karaoke=True, cloud_library_active=False,
                cloud_library_expires_at=None, revalidate_after=None, max_seats=5, active_seats=1)

@app.post("/api/license/activate")
async def _a(b: dict): return _lic(b)

@app.post("/api/license/validate")
async def _v(b: dict): return _lic(b)

@app.get("/__ping")
async def _p(): return {"ok": True}

uvicorn.run(app, host="127.0.0.1", port=int(sys.argv[1]), log_level="warning")
