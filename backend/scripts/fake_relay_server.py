"""Local stand-in for api.bighat.live that runs the REAL cloud/relay_router.py (alpha.82 tests only).
Accepts one test license BHE-AAAA-BBBB-CCCC-DDDD from any machine.  Port = argv[1].
Control calls: POST /__revoke  (revoke the license)   POST /__expire_files  (expire every stored file now)"""
import os, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from fastapi import FastAPI
import uvicorn
from cloud import relay_router as rr

KEY = "BHE-AAAA-BBBB-CCCC-DDDD"


class Coll:
    def __init__(self): self.rows = []
    def _m(self, r, q):
        for k, v in q.items():
            if isinstance(v, dict):
                x = r.get(k)
                if "$lt" in v and not (x is not None and x < v["$lt"]): return False
            elif r.get(k) != v: return False
        return True
    async def insert_one(self, d): self.rows.append(dict(d))
    async def find_one(self, q, proj=None, sort=None):
        m = [r for r in self.rows if self._m(r, q)]
        if sort: m.sort(key=lambda r: r.get(sort[0][0], 0), reverse=sort[0][1] < 0)
        return dict(m[0]) if m else None
    def find(self, q, proj=None):
        coll = self
        class C:
            def __init__(s): s.m = [dict(r) for r in coll.rows if coll._m(r, q)]
            def sort(s, k, d=1): s.m.sort(key=lambda r: r.get(k, 0), reverse=d < 0); return s
            async def to_list(s, n): return s.m[:n]
        return C()
    async def update_one(self, q, u):
        for r in self.rows:
            if self._m(r, q): r.update(u.get("$set", {})); return
    async def delete_one(self, q):
        for i, r in enumerate(self.rows):
            if self._m(r, q): del self.rows[i]; return
    async def delete_many(self, q): self.rows = [r for r in self.rows if not self._m(r, q)]
    async def count_documents(self, q): return len([r for r in self.rows if self._m(r, q)])


class DB:
    def __init__(self): self.relay_files, self.relay_sessions, self.relay_requests = Coll(), Coll(), Coll()


class Svc:
    revoked = False
    async def validate(self, *, key, hwid):
        if key != KEY: return False, "unknown_key", None
        if self.revoked: return False, "revoked", None
        return True, "ok", object()


svc, db = Svc(), DB()
rr.set_runtime(service=svc, db=db, files_dir=tempfile.mkdtemp(prefix="relay_"))
app = FastAPI(); app.include_router(rr.router)

def _lic(b):
    from fastapi import HTTPException
    if b.get("key") != KEY or svc.revoked: raise HTTPException(status_code=400, detail="key not found or revoked")
    return dict(ok=True, owns_standalone=True, owns_music_bingo=True, owns_karaoke=True, cloud_library_active=False,
                cloud_library_expires_at=None, revalidate_after=None, max_seats=5, active_seats=1)

@app.post("/api/license/activate")
async def _act(b: dict): return _lic(b)

@app.post("/api/license/validate")
async def _val(b: dict): return _lic(b)

@app.post("/__revoke")
async def revoke(): svc.revoked = True; return {"ok": True}

@app.post("/__expire_files")
async def expire():
    for r in db.relay_files.rows: r["expires_at"] = "2000-01-01T00:00:00+00:00"
    return {"ok": True}

uvicorn.run(app, host="127.0.0.1", port=int(sys.argv[1]), log_level="warning")
