#!/bin/bash
# Real-app check: a venue added in the Schedule shows up in the Story builders. Usage: e2e_story_venues.sh <port>
cd "$(dirname "$0")/.."
PORT=$1; D=/tmp/e2e_$PORT; rm -rf $D; mkdir -p $D/db $D/home/Documents
export HOME=$D/home BIGHAT_CONFIG_PATH=$D/system_config.json BIGHAT_DB_DIR=$D/db BIGHAT_DATA_DIR=$D/data BIGHAT_PORT=$PORT LOCALAPPDATA=$D/app BIGHAT_IGNORE_SYSTEM_FFMPEG=1
B=localhost:$PORT/api; J='Content-Type: application/json'
start() { (timeout 400 python3 launcher.py >$D/log.txt 2>&1 &); for i in $(seq 1 70); do curl -s localhost:$PORT/health >/dev/null 2>&1 && return; sleep 1; done; echo "SERVER DID NOT START"; }
stop() { pkill -f launcher.py; sleep 2; }
jq_() { python3 -c "import sys,json
try: d=json.load(sys.stdin)
except Exception: print('(no json)'); sys.exit()
print($1)" 2>/dev/null; }
start
curl -s -X POST -H "$J" -d '{"license_key":"BHE-TEST-AAAA-BBBB-CCCC","offline_mode":true,"master_admin":{"email":"owner@example.com","password":"OwnerPass1!","first_name":"Owner"},"settings":{"location_name":"Test Pub"}}' $B/native/setup/initialize >/dev/null
stop
python3 - <<P
import json
p="$D/system_config.json"; c=json.load(open(p)); c.setdefault("subscription",{})["story_generator_enabled"]=True; json.dump(c,open(p,"w"))
P
start
TOKEN=$(curl -s -X POST -H "$J" -d '{"email":"owner@example.com","password":"OwnerPass1!"}' $B/auth/login | jq_ "d.get('token','')"); H="Authorization: Bearer $TOKEN"
lst() { curl -s $B/story-generator/event-assets/$1 | jq_ "[(l['name'], l['has_image']) for l in d['locations']]"; }
echo "== add 2 venues in the SCHEDULE (no pictures yet)"
curl -s -X POST -H "$J" -d '{"name":"Roses By The Stairs","address":"2 Oak","city":"Mesa","state":"AZ"}' $B/venues >/dev/null
curl -s -X POST -H "$J" -d '{"name":"Monkey Pants","address":"1 Main","city":"Phoenix","state":"AZ"}' $B/venues >/dev/null
echo "   Bingo builder list:   $(lst bingo)"; echo "   Karaoke builder list: $(lst karaoke)"
echo "== upload a Bingo picture for Roses only (through the Story Images manager route)"
curl -s -X POST -H "$H" -F file=@/tmp/loc_bingo.png -F 'name=Roses By The Stairs' $B/story-generator/story-images/bingo | jq_ "d.get('filename')"
curl -s -X POST -H "$H" -F file=@/tmp/host_alex.gif -F 'name=Nick' $B/story-generator/story-images/hosts >/dev/null
echo "   Bingo builder list:   $(lst bingo)"; echo "   Karaoke builder list: $(lst karaoke)   <- Karaoke has its own picture"
echo "== generate a Bingo story for Roses (has a picture)"
ID=$(curl -s $B/story-generator/event-assets/bingo | jq_ "[l['id'] for l in d['locations'] if l['name']=='Roses By The Stairs'][0]")
JOB=$(curl -s -X POST -H "$H" -H "$J" -d "{\"event_type\":\"bingo\",\"location_id\":\"$ID\",\"location_name\":\"Roses By The Stairs\",\"host_id\":\"Nick.gif\",\"host_name\":\"Nick\",\"host_is_gif\":true}" $B/story-generator/generate-event-video | jq_ "d.get('jobId') or str(d)[:100]")
for i in $(seq 1 40); do sleep 3; S=$(curl -s $B/story-generator/job-status/$JOB | jq_ "str(d.get('status'))+' '+str(d.get('progress'))+' '+str(d.get('error') or '')[:100]"); case "$S" in completed*|failed*) break;; esac; done; echo "   job: $S"
echo "== a venue WITHOUT a picture (Monkey Pants): the preview comes back empty, not a crash"
echo "   -> $(curl -s -X POST -H "$H" -H "$J" -d '{"event_type":"bingo","location_id":"","host_id":"Nick.gif","host_is_gif":true}' $B/story-generator/event-preview | jq_ "{'locationImage': (d.get('locationImage') or '')[:5], 'hostImage': (d.get('hostImage') or '')[:15]}")"
echo "== rename the venue -> the Story list follows, the picture stays matched"
VID=$(curl -s $B/venues | jq_ "[v['id'] for v in d if v['name']=='Roses By The Stairs'][0]")
curl -s -X PUT -H "$J" -d '{"name":"Roses By The Stairs Pub","address":"2 Oak","city":"Mesa","state":"AZ"}' $B/venues/$VID >/dev/null
echo "   Bingo builder list:   $(lst bingo)"
stop
