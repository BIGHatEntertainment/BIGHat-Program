#!/bin/bash
# Real-app persistence audit: save -> read -> RESTART -> read, for every area that stores data.
# Usage: e2e_persistence.sh <port> <label>
cd "$(dirname "$0")/.."
PORT=$1; LABEL=$2; D=/tmp/e2e_$PORT; rm -rf $D; mkdir -p $D/db
export BIGHAT_CONFIG_PATH=$D/system_config.json BIGHAT_DB_DIR=$D/db BIGHAT_DATA_DIR=$D/data BIGHAT_PORT=$PORT LOCALAPPDATA=$D/app BIGHAT_KARAOKE_DIR=$D/k BIGHAT_KARAOKE_SETTINGS=$D/ks.json BIGHAT_WINNER_VIDEOS_DIR=$D/wv
B=localhost:$PORT/api; J='Content-Type: application/json'
start() { (timeout 200 python3 launcher.py >$D/log.txt 2>&1 &); for i in $(seq 1 70); do curl -s localhost:$PORT/health >/dev/null 2>&1 && return; sleep 1; done; }
stop() { pkill -f launcher.py; sleep 2; }
jq_() { python3 -c "import sys,json;d=json.load(sys.stdin);$1" 2>/dev/null; }
start
curl -s -X POST -H "$J" -d '{"license_key":"BHE-TEST-AAAA-BBBB-CCCC","offline_mode":true,"master_admin":{"email":"owner@example.com","password":"OwnerPass1!","first_name":"Owner"},"settings":{"location_name":"Test Pub"}}' $B/native/setup/initialize >/dev/null
login() { curl -s -X POST -H "$J" -d '{"email":"owner@example.com","password":"OwnerPass1!"}' $B/auth/login | jq_ "print(d.get('access_token') or d.get('token') or '')"; }
TOKEN=$(login); A="Authorization: Bearer $TOKEN"
post() { curl -s -X POST -H "$J" -H "$A" -d "$2" "$B$1"; }
get()  { curl -s -H "$A" "$B$1"; }

# ---- SAVE
VID=$(post /venues '{"name":"The Rusty Nail","address":"1 Main St","city":"Phoenix","state":"AZ"}' | jq_ "print(d.get('id',''))")
EMP=$(post /employees '{"name":"Hal Host","email":"hal@example.com","phone":"555","is_admin":false}' | jq_ "print(d.get('id',''))")
EVT=$(post /events "{\"title\":\"Trivia Night\",\"event_type\":\"trivia\",\"venue_id\":\"$VID\",\"date\":\"2026-11-05T19:00:00Z\",\"duration_hours\":2,\"pay_rate\":60}" | jq_ "print(d.get('id',''))")
BLK=$(post /blackouts "{\"employee_id\":\"$EMP\",\"start_date\":\"2026-11-12\",\"end_date\":\"2026-11-14\"}" | jq_ "print(d.get('id',''))")
ROL=$(post /venue-roles "{\"venue_id\":\"$VID\",\"employee_id\":\"$EMP\",\"role_category\":\"trivia\",\"role_type\":\"primary\"}" | jq_ "print(d.get('id',''))")
PRC=$(post /venue_pricing "{\"venue_id\":\"$VID\",\"trivia_price\":150,\"music_bingo_price\":125,\"karaoke_price\":100}" | jq_ "print(d.get('id',''))")
post /events/$EVT/claim "{\"employee_id\":\"$EMP\"}" >/dev/null
UID_=$(post /native/admin/users '{"email":"newadmin@example.com","password":"Passw0rd!x","first_name":"New","last_name":"Admin","role":"admin"}' | jq_ "print((d.get('user') or d).get('id',''))")
echo "[$LABEL] saved ids: venue=${VID:0:6} employee=${EMP:0:6} event=${EVT:0:6} blackout=${BLK:0:6} role=${ROL:0:6} pricing=${PRC:0:6} user=${UID_:0:6}"

count() { get "$1" | jq_ "print(len(d) if isinstance(d,list) else len(d.get('$2',d)) if isinstance(d,dict) else 0)"; }
report() {
  echo "[$LABEL] $1 venues=$(count /venues) employees=$(count /employees) events=$(count /events) blackouts=$(count /blackouts) roles=$(count /venue-roles) pricing=$(count /venue_pricing) users=$(get /users | jq_ "d=d if isinstance(d,list) else d.get('users',[]);print(sorted(u['email'] for u in d))")"
  echo "[$LABEL] $1 event claimed by hal: $(get /events | jq_ "print([e.get('claimed_by') or e.get('employee_id') or e.get('claimed_by_id') for e in d if e['title']=='Trivia Night'])")"
}
report "BEFORE restart:"
stop; start; TOKEN=$(login); A="Authorization: Bearer $TOKEN"
report "AFTER restart: "
stop
