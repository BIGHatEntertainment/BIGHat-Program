#!/bin/bash
# Real-app check: a user who already set up locations (with pictures) in Trivia Setup BEFORE venues were the master list.
# Usage: e2e_venue_migration.sh <port>
cd "$(dirname "$0")/.."
PORT=$1; D=/tmp/e2e_$PORT; rm -rf $D; mkdir -p $D/db $D/home/Documents
export HOME=$D/home BIGHAT_CONFIG_PATH=$D/system_config.json BIGHAT_DB_DIR=$D/db BIGHAT_DATA_DIR=$D/data BIGHAT_PORT=$PORT LOCALAPPDATA=$D/app
B=localhost:$PORT/api; J='Content-Type: application/json'
start() { (timeout 400 python3 launcher.py >$D/log.txt 2>&1 &); for i in $(seq 1 70); do curl -s localhost:$PORT/health >/dev/null 2>&1 && return; sleep 1; done; echo "SERVER DID NOT START"; }
stop() { pkill -f launcher.py; sleep 2; }
jq_() { python3 -c "import sys,json
try: d=json.load(sys.stdin)
except Exception: print('(no json)'); sys.exit()
print($1)" 2>/dev/null; }
start
curl -s -X POST -H "$J" -d '{"license_key":"BHE-TEST-AAAA-BBBB-CCCC","offline_mode":true,"master_admin":{"email":"owner@example.com","password":"OwnerPass1!","first_name":"Owner"},"settings":{"location_name":"Test Pub"}}' $B/native/setup/initialize >/dev/null
TOKEN=$(curl -s -X POST -H "$J" -d '{"email":"owner@example.com","password":"OwnerPass1!"}' $B/auth/login | jq_ "d.get('token','')"); H="Authorization: Bearer $TOKEN"
echo "== set up 3 places the OLD way (Trivia Setup), 2 with pictures"
for n in "Monkey Pants" "Roses By The Stairs" "Old Town Pub"; do
  LID=$(curl -s -X POST -H "$H" -H "$J" -d "{\"name\":\"$n\"}" $B/native/locations | jq_ "d.get('id')")
  [ "$n" != "Old Town Pub" ] && curl -s -X POST -H "$H" -F "file=@/tmp/loc_bingo.png" $B/native/locations/$LID/images >/dev/null
done
stop
echo "== simulate the pre-alpha.80 state: remove every venue + every venue link, as if upgrading"
python3 - <<P
import json, glob, os
# (a) location.json files lose their venue link
for f in glob.glob("$D/home/Documents/*/Files/Locations/*/location.json"):
    d=json.load(open(f)); d.pop("venue_id",None); json.dump(d,open(f,"w"))
print("   location.json files rewritten:", len(glob.glob("$D/home/Documents/*/Files/Locations/*/location.json")))
P
python3 - <<P
# (b) delete the venue rows + venue links in the database itself, through the app's own database layer
import os, sys, asyncio
sys.path.insert(0,'.')
os.environ.update(BIGHAT_NATIVE_MODE="1", BIGHAT_DB_DIR="$D/db", BIGHAT_DATA_DIR="$D/data", HOME="$D/home", LOCALAPPDATA="$D/app")
from native import db_factory
async def main():
    db = db_factory.get_db()
    if db is None:
        print("   (could not open the database directly)"); return
    await db.venues.delete_many({})
    await db.locations.update_many({}, {"\$unset": {"venue_id": ""}})
    print("   venues now:", await db.venues.count_documents({}), "| locations:", await db.locations.count_documents({}))
asyncio.run(main())
P
echo "== start the new version"
start
TOKEN=$(curl -s -X POST -H "$J" -d '{"email":"owner@example.com","password":"OwnerPass1!"}' $B/auth/login | jq_ "d.get('token','')"); H="Authorization: Bearer $TOKEN"
echo "   venues (Schedule):   $(curl -s $B/venues | jq_ "sorted((v['name'],v.get('address','')[:12]) for v in d)")"
echo "   locations (Setup):   $(curl -s -H "$H" $B/native/locations | jq_ "sorted((l['name'],len(l.get('branding_images',[]))) for l in d)")"
echo "== start AGAIN -> no duplicates"
stop; start
TOKEN=$(curl -s -X POST -H "$J" -d '{"email":"owner@example.com","password":"OwnerPass1!"}' $B/auth/login | jq_ "d.get('token','')"); H="Authorization: Bearer $TOKEN"
echo "   venues:    $(curl -s $B/venues | jq_ "len(d)")   locations: $(curl -s -H "$H" $B/native/locations | jq_ "len(d)")"
grep -a "venue-sync\|Traceback" $D/log.txt | head -3 | cut -c1-200
stop
