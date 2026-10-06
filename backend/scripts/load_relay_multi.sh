#!/bin/bash
# Same as load_relay.sh, but the load comes from several separate client processes so the load generator itself is not the bottleneck.
# usage: load_relay_multi.sh <venues> <seconds> <poll_seconds> <phones> <cache_seconds> <processes>
cd "$(dirname "$0")/.."
V=$1; S=$2; P=$3; PH=$4; CACHE=$5; N=${6:-4}; D=/tmp/loadtest; pkill -f "uvicorn server:app" 2>/dev/null; pkill -f "mongod --dbpath $D" 2>/dev/null; sleep 1
rm -rf $D; mkdir -p $D/mongo $D/home
mongod --dbpath $D/mongo --port 27098 --bind_ip 127.0.0.1 --fork --logpath $D/mongod.log >/dev/null 2>&1; sleep 3
export MONGO_URL=mongodb://127.0.0.1:27098 DB_NAME=loadtest HOME=$D/home BIGHAT_CLOUD_MODE=1 BIGHAT_NATIVE_MODE=1 BIGHAT_CONFIG_PATH=$D/cfg.json BIGHAT_DB_DIR=$D/db BIGHAT_DATA_DIR=$D/data JWT_SECRET=t LICENSE_ADMIN_SECRET=t RELAY_FILES_DIR=$D/relay RELAY_AUTH_CACHE_SECONDS=$CACHE RELAY_PHONE_COOLDOWN_SECONDS=1 RELAY_MAX_SESSIONS_PER_LICENSE=100000
(python3 -m uvicorn server:app --host 127.0.0.1 --port 8997 --log-level warning --workers ${WORKERS:-1} >$D/log.txt 2>&1 &)
for i in $(seq 1 45); do curl -s -m 2 localhost:8997/api/health >/dev/null 2>&1 && break; sleep 1; done
VENUES=$V python3 - <<'PY'
import asyncio, os
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient
def key_for(i): return "BHE-%04X-%04X-%04X-%04X" % (i // 65536, i % 65536, 0xABCD, 0x1234)
async def go():
    db = AsyncIOMotorClient("mongodb://127.0.0.1:27098")["loadtest"]; now = datetime.now(timezone.utc).isoformat()
    await db.license_keys.insert_many([{"key": key_for(i), "email": f"v{i}@test.com", "owns_standalone": True, "owns_music_bingo": True, "owns_karaoke": True, "cloud_library_status": "inactive", "max_seats": 3, "revoked": False, "active_hwids": [{"hwid": f"hw-{i}", "machine_name": "t", "activated_at": now, "last_seen_at": now}], "created_at": now, "updated_at": now} for i in range(int(os.environ["VENUES"]))])
asyncio.run(go())
PY
PER=$((V / N)); PIDS=""
for k in $(seq 0 $((N-1))); do FIRST_VENUE=$((k*PER)) python3 scripts/load_relay.py http://127.0.0.1:8997 $PER $S $P $PH > $D/out_$k.txt 2>&1 & PIDS="$PIDS $!"; done
SP=$(pgrep -f "uvicorn server:app" | head -1); sleep $((S/2)); echo "server cpu mid-run: $(ps -p $SP -o %cpu= | tr -d ' ')%"
wait $PIDS
python3 - $N <<'PY'
import re, sys, glob
n = int(sys.argv[1]); calls = 0; errs = 0; p95 = []; p99 = []; p50 = []; mx = 0
for k in range(n):
    t = open(f"/tmp/loadtest/out_{k}.txt").read()
    m = re.search(r"calls=(\d+).*errors=(\d+)", t); l = re.search(r"p50=(\d+)\s+p95=(\d+)\s+p99=(\d+)\s+max=(\d+)", t)
    if not (m and l): print(f"  process {k}: NO RESULT"); print(t[-300:]); continue
    calls += int(m.group(1)); errs += int(m.group(2)); p50.append(int(l.group(1))); p95.append(int(l.group(2))); p99.append(int(l.group(3))); mx = max(mx, int(l.group(4)))
print(f"  total calls={calls} errors={errs}   worst-process p50={max(p50, default=0)}ms p95={max(p95, default=0)}ms p99={max(p99, default=0)}ms max={mx}ms")
PY
pkill -f "uvicorn server:app"; pkill -f "mongod --dbpath $D"
