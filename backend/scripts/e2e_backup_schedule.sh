#!/bin/bash
# Real-app check: is the SCHEDULE (events/venues/employees) in the daily backup, laid out like a real install?
# Usage: e2e_backup_schedule.sh <port>
cd "$(dirname "$0")/.."
PORT=$1; D=/tmp/e2e_$PORT; rm -rf $D; mkdir -p $D/home/Documents
export HOME=$D/home BIGHAT_PORT=$PORT           # NO other overrides: data goes where a real install puts it
unset BIGHAT_CONFIG_PATH BIGHAT_DB_DIR BIGHAT_DATA_DIR BIGHAT_FILES_DIR LOCALAPPDATA BIGHAT_BACKUPS_DIR BIGHAT_DATA_ROOT_FOR_BACKUP
B=localhost:$PORT/api; J='Content-Type: application/json'
start() { (timeout 300 python3 launcher.py >$D/log.txt 2>&1 &); for i in $(seq 1 70); do curl -s localhost:$PORT/health >/dev/null 2>&1 && return; sleep 1; done; echo "SERVER DID NOT START"; }
stop() { pkill -f launcher.py; sleep 2; }
start
curl -s -X POST -H "$J" -d '{"license_key":"BHE-TEST-AAAA-BBBB-CCCC","offline_mode":true,"master_admin":{"email":"owner@example.com","password":"OwnerPass1!","first_name":"Owner"},"settings":{"location_name":"Test Pub"}}' $B/native/setup/initialize >/dev/null
V=$(curl -s -X POST -H "$J" -d '{"name":"Monkey Pants","address":"1 Main","city":"Phoenix","state":"AZ"}' $B/venues | python3 -c "import sys,json;print(json.load(sys.stdin).get('id'))")
curl -s -X POST -H "$J" -d "{\"title\":\"Trivia Night\",\"event_type\":\"Trivia\",\"venue_id\":\"$V\",\"date\":\"2026-10-12T01:00:00.000Z\",\"duration_hours\":2}" $B/events >/dev/null
echo "data folder:  $(find $D/home -maxdepth 4 -type d -name data | head -1 | sed "s#$D/home/##")"
echo "files there:  $(ls $D/home/.local/share/BIGHat/data 2>/dev/null | tr '\n' ' ')"
TOKEN=$(curl -s -X POST -H "$J" -d '{"email":"owner@example.com","password":"OwnerPass1!"}' $B/auth/login | python3 -c "import sys,json;print(json.load(sys.stdin).get('token',''))")
echo "run backup:   $(curl -s -X POST -H "Authorization: Bearer $TOKEN" $B/native/backup/run | cut -c1-200)"
echo "config file:  $(find $D/home -name system_config.json | sed "s#$D/home/##" | head -2 | tr '\n' ' ') $(find /root/workspace/BIGHat-Program/backend -maxdepth 2 -name system_config.json | head -1)"
Z=$(ls $D/home/Documents/BIG*/Backups/*.zip 2>/dev/null | head -1); echo "zip: ${Z#$D/home/}"
python3 - <<P
import zipfile
z=zipfile.ZipFile("$Z"); n=z.namelist()
print("entries:", len(n))
for want in ("system_config.json","bighat_db"):
    hits=[x for x in n if want in x]
    print(f"  {want}: {len(hits)} file(s)", hits[:3])
P
stop
