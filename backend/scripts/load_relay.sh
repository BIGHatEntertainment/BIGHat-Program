#!/bin/bash
# Starts the REAL cloud server (cloud mode, throwaway MongoDB) with one known license, then runs load_relay.py.
# usage: load_relay.sh <venues> <seconds> <poll_seconds> <phones> [cache_seconds]
cd "$(dirname "$0")/.."
V=$1; S=$2; P=$3; PH=$4; CACHE=${5:-300}; D=/tmp/loadtest; pkill -f "uvicorn server:app" 2>/dev/null; pkill -f "mongod --dbpath $D" 2>/dev/null; sleep 1
rm -rf $D; mkdir -p $D/mongo $D/home
mongod --dbpath $D/mongo --port 27098 --bind_ip 127.0.0.1 --fork --logpath $D/mongod.log >/dev/null 2>&1; sleep 3
export MONGO_URL=mongodb://127.0.0.1:27098 DB_NAME=loadtest HOME=$D/home BIGHAT_CLOUD_MODE=1 BIGHAT_NATIVE_MODE=1 BIGHAT_CONFIG_PATH=$D/cfg.json BIGHAT_DB_DIR=$D/db BIGHAT_DATA_DIR=$D/data JWT_SECRET=t LICENSE_ADMIN_SECRET=t RELAY_FILES_DIR=$D/relay RELAY_AUTH_CACHE_SECONDS=$CACHE RELAY_PHONE_COOLDOWN_SECONDS=1 RELAY_MAX_SESSIONS_PER_LICENSE=100000
(python3 -m uvicorn server:app --host 127.0.0.1 --port 8997 --log-level warning >$D/log.txt 2>&1 &)
for i in $(seq 1 45); do curl -s -m 2 localhost:8997/api/health >/dev/null 2>&1 && break; sleep 1; done
# one license per venue (one machine each), straight into the throwaway database
VENUES=$V python3 - <<'PY'
import asyncio, os
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient
def key_for(i): return "BHE-%04X-%04X-%04X-%04X" % (i // 65536, i % 65536, 0xABCD, 0x1234)
async def go():
    db = AsyncIOMotorClient("mongodb://127.0.0.1:27098")["loadtest"]
    now = datetime.now(timezone.utc).isoformat()
    docs = [{"key": key_for(i), "email": f"v{i}@test.com", "owns_standalone": True, "owns_music_bingo": True, "owns_karaoke": True,
             "cloud_library_status": "inactive", "max_seats": 3, "revoked": False,
             "active_hwids": [{"hwid": f"hw-{i}", "machine_name": "t", "activated_at": now, "last_seen_at": now}],
             "created_at": now, "updated_at": now} for i in range(int(os.environ["VENUES"]))]
    await db.license_keys.insert_many(docs)
asyncio.run(go())
PY
python3 scripts/load_relay.py http://127.0.0.1:8997 $V $S $P $PH
echo "license-record writes during the run (last_seen_at touches are what the cache avoids):"
mongosh --quiet --port 27098 loadtest --eval 'print("  relay_requests stored: "+db.relay_requests.countDocuments({})+"   sessions: "+db.relay_sessions.countDocuments({}))' 2>&1 | tail -1
pkill -f "uvicorn server:app"; pkill -f "mongod --dbpath $D"
