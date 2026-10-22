#!/bin/bash
# Real-app check of the Phase 3 pull: a fake Cloud serves the change feed, the real launcher links, pulls, restarts and pulls only the delta.
# Usage: e2e_cloud_sync.sh <port>
cd "$(dirname "$0")/.."
PORT=$1; CP=$((PORT+1)); D=/tmp/e2e_sync_$PORT; rm -rf $D; mkdir -p $D/home/Documents
export HOME=$D/home BIGHAT_PORT=$PORT BIGHAT_CLOUD_BASE_URL=http://127.0.0.1:$CP
unset BIGHAT_DB_DIR BIGHAT_DATA_DIR BIGHAT_FILES_DIR LOCALAPPDATA BIGHAT_BACKUPS_DIR
U=$D/home/.local/share/BIGHat/data; mkdir -p $U
export BIGHAT_CONFIG_PATH=$U/system_config.json BIGHAT_DATA_ROOT=$U/app
cat > $D/fake.py <<'P'
import sys, json
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uvicorn
app = FastAPI(); SINCE = []
V = {"item_id": "v1", "kind": "venue", "revision": 1, "deleted": False, "updated_at": "x", "updated_by": "cloud",
     "data": {"id": "v1", "name": "Cloud Pub", "address": "1 Main", "city": "Mesa", "state": "AZ", "notes": None, "venue_pays_host_directly": False}}
Pp = {"item_id": "p1", "kind": "person", "revision": 1, "deleted": False, "updated_at": "x", "updated_by": "cloud",
      "data": {"name": "Sam Host", "email": "sam@x.com", "phone": "5", "role": "host", "is_admin": False}}
@app.get("/api/program/changes")
async def ch(request: Request, since: int = 0, limit: int = 500):
    SINCE.append(since)
    if request.headers.get("authorization") != "Bearer TESTKEY":
        return JSONResponse(status_code=401, content={"error": "unauthorized", "message": "no"})
    if since == 0: return {"seq": 2, "has_more": False, "items": [V, Pp]}
    return {"seq": since, "has_more": False, "items": []}
@app.get("/seen")
async def seen(): return SINCE
uvicorn.run(app, host="127.0.0.1", port=int(sys.argv[1]), log_level="warning")
P
(python3 $D/fake.py $CP >$D/fake.log 2>&1 &)
python3 - <<'P'
import sys; sys.path.insert(0, "."); import os
from native import cloud_link
rec = cloud_link.get_or_create()
enc = cloud_link._fernet().encrypt(b"TESTKEY").decode()
cloud_link._save(token_enc=enc, status="linked", program_id="p")
print("linked file:", cloud_link._path())
P
start() { (timeout 200 python3 launcher.py >$D/log.txt 2>&1 &); for i in $(seq 1 70); do curl -s localhost:$PORT/health >/dev/null 2>&1 && return; sleep 1; done; echo "backend did not start"; tail -20 $D/log.txt; exit 1; }
stop() { pkill -f "launcher.py"; sleep 2; }
S=localhost:$PORT/api/native/system/cloud-link
start
echo "sync-now:  $(curl -s -X POST $S/sync-now | cut -c1-260)"
echo "venues:    $(curl -s localhost:$PORT/api/venues | python3 -c 'import sys,json;print([v["name"] for v in json.load(sys.stdin)])')"
echo "logins:    $(curl -s -X POST $S/new-logins | python3 -c 'import sys,json;print([(l["email"],bool(l["temp_password"])) for l in json.load(sys.stdin)["logins"]])')"
echo "again:     $(curl -s -X POST $S/new-logins)"
stop; start
echo "restart:   $(curl -s -X POST $S/sync-now | cut -c1-200)"
echo "venues:    $(curl -s localhost:$PORT/api/venues | python3 -c 'import sys,json;print(len(json.load(sys.stdin)))') (must be 1)"
echo "asked for since= $(curl -s localhost:$CP/seen)"
echo "state file: $(find $D/home -name cloud_sync.json | sed "s|$D/home/||")  in-source: $(find "$(pwd)" -name cloud_sync.json 2>/dev/null | head -1)"
stop; pkill -f fake.py
