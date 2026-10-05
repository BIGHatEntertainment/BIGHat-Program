#!/bin/bash
# Real-app check: add events the way the Schedule page does, read them back, restart, read again. Usage: e2e_schedule.sh <port>
cd "$(dirname "$0")/.."
PORT=$1; D=/tmp/e2e_$PORT; rm -rf $D; mkdir -p $D/db $D/home/Documents
export HOME=$D/home BIGHAT_CONFIG_PATH=$D/system_config.json BIGHAT_DB_DIR=$D/db BIGHAT_DATA_DIR=$D/data BIGHAT_PORT=$PORT LOCALAPPDATA=$D/app
B=localhost:$PORT/api; J='Content-Type: application/json'
start() { (timeout 300 python3 launcher.py >$D/log.txt 2>&1 &); for i in $(seq 1 70); do curl -s localhost:$PORT/health >/dev/null 2>&1 && return; sleep 1; done; echo "SERVER DID NOT START"; }
stop() { pkill -f launcher.py; sleep 2; }
start
curl -s -X POST -H "$J" -d '{"license_key":"BHE-TEST-AAAA-BBBB-CCCC","offline_mode":true,"master_admin":{"email":"owner@example.com","password":"OwnerPass1!","first_name":"Owner"},"settings":{"location_name":"Test Pub"}}' $B/native/setup/initialize >/dev/null
V1=$(curl -s -X POST -H "$J" -d '{"name":"Monkey Pants","address":"1 Main St","city":"Phoenix","state":"AZ"}' $B/venues | python3 -c "import sys,json;print(json.load(sys.stdin).get('id'))"); echo "venue 1: $V1"
V2=$(curl -s -X POST -H "$J" -d '{"name":"Roses By The Stairs","address":"2 Oak St","city":"Mesa","state":"AZ"}' $B/venues | python3 -c "import sys,json;print(json.load(sys.stdin).get('id'))"); echo "venue 2: $V2"
mk() { curl -s -X POST -H "$J" -d "$1" $B/events | python3 -c "import sys,json;d=json.load(sys.stdin);print({k:d.get(k) for k in ('title','event_type','venue_id','is_special_event','pay_rate','notes','duration_hours','status')} if 'id' in d else d)"; }
echo "--- add events exactly as the form sends them"
mk "{\"title\":\"Trivia Night\",\"event_type\":\"Trivia\",\"venue_id\":\"$V1\",\"date\":\"2026-10-12T01:00:00.000Z\",\"duration_hours\":2,\"pay_rate\":75,\"notes\":\"bring mic\",\"is_special_event\":false}"
mk "{\"title\":\"Music Bingo\",\"event_type\":\"Music Bingo\",\"venue_id\":\"$V2\",\"date\":\"2026-10-14T01:30:00.000Z\",\"duration_hours\":2.5,\"pay_rate\":null,\"notes\":null,\"is_special_event\":false}"
mk "{\"title\":\"Halloween Bash\",\"event_type\":\"Special\",\"venue_id\":\"$V1\",\"date\":\"2026-10-31T02:00:00.000Z\",\"duration_hours\":4,\"pay_rate\":150,\"notes\":\"costumes\",\"is_special_event\":true}"
mk "{\"title\":\"Karaoke\",\"event_type\":\"Karaoke\",\"venue_id\":\"$V2\",\"date\":\"2026-10-16T02:00:00.000Z\",\"duration_hours\":3}"
echo "--- bad ones"
echo "no venue: $(curl -s -o /dev/null -w '%{http_code}' -X POST -H "$J" -d '{"title":"x","event_type":"Trivia","venue_id":"nope","date":"2026-10-12T01:00:00.000Z"}' $B/events)"
echo "no date:  $(curl -s -o /dev/null -w '%{http_code}' -X POST -H "$J" -d "{\"title\":\"x\",\"event_type\":\"Trivia\",\"venue_id\":\"$V1\"}" $B/events)"
show() { curl -s "$B/events?include_past=true" | python3 -c "
import sys,json
d=json.load(sys.stdin); print(len(d),'events:')
for e in d: print('  ',e['date'][:16],'|',e['title'],'|',e['event_type'],'| venue',e['venue_id'][:6],'| special',e.get('is_special_event'),'| pay',e.get('pay_rate'),'|',e.get('notes'))"; }
echo "--- list"; show
echo "--- default list (what the Schedule page loads, no include_past)"; curl -s "$B/events" | python3 -c "import sys,json;print(len(json.load(sys.stdin)),'events')"
echo "--- edit the first event"
EID=$(curl -s "$B/events?include_past=true" | python3 -c "import sys,json;print(json.load(sys.stdin)[0]['id'])")
curl -s -X PUT -H "$J" -d "{\"title\":\"Trivia Night (edited)\",\"event_type\":\"Trivia\",\"venue_id\":\"$V2\",\"date\":\"2026-10-12T02:00:00.000Z\",\"duration_hours\":3,\"pay_rate\":80,\"notes\":\"changed\",\"is_special_event\":true}" $B/events/$EID | python3 -c "import sys,json;d=json.load(sys.stdin);print({k:d.get(k) for k in ('title','venue_id','duration_hours','pay_rate','notes','is_special_event')})"
stop; start
echo "--- AFTER RESTART"; show
stop
