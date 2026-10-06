#!/bin/bash
# Real-app check: the Schedule's venues are the single list of places.  Usage: e2e_venues.sh <port>
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
locs() { curl -s -H "$H" $B/native/locations | jq_ "sorted(l['name'] for l in d) if isinstance(d,list) else d"; }
vens() { curl -s $B/venues | jq_ "sorted(v['name'] for v in d)"; }
echo "token: ${TOKEN:0:6}.."
echo "== 1) add venues in the SCHEDULE"
curl -s -X POST -H "$J" -d '{"name":"Monkey Pants","address":"1 Main St","city":"Phoenix","state":"AZ"}' $B/venues | jq_ "d.get('name'), 'location_id' in d"
curl -s -X POST -H "$J" -d '{"name":"Roses By The Stairs","address":"2 Oak","city":"Mesa","state":"AZ"}' $B/venues >/dev/null
echo "   venues:    $(vens)"; echo "   locations: $(locs)   <- Trivia/Karaoke Setup list"
echo "== 2) duplicate venue (different case/spacing)"
echo "   -> $(curl -s -X POST -H "$J" -d '{"name":"monkey  pants","address":"x","city":"x","state":"AZ"}' $B/venues | jq_ "d.get('detail')")"
echo "== 3) upload a picture to the location, then RENAME the venue"
LID=$(curl -s -H "$H" $B/native/locations | jq_ "[l['id'] for l in d if l['name']=='Monkey Pants'][0]")
curl -s -X POST -H "$H" -F "file=@/tmp/loc_bingo.png" $B/native/locations/$LID/images | jq_ "'uploaded image' if d.get('id') else d"
VID=$(curl -s $B/venues | jq_ "[v['id'] for v in d if v['name']=='Monkey Pants'][0]")
curl -s -X PUT -H "$J" -d '{"name":"Monkey Pants Tavern","address":"1 Main St","city":"Phoenix","state":"AZ"}' $B/venues/$VID | jq_ "d.get('name')"
echo "   locations: $(locs)"
echo "   images kept: $(curl -s -H "$H" $B/native/locations | jq_ "[len(l.get('branding_images',[])) for l in d if l['name']=='Monkey Pants Tavern']")"
echo "== 4) rename from Trivia Setup -> the venue follows"
curl -s -X PATCH -H "$H" -H "$J" -d '{"name":"Monkey Pants Bar"}' $B/native/locations/$LID | jq_ "d.get('name')"
echo "   venues: $(vens)"
echo "== 5) add a place in Trivia Setup -> it gets a venue"
curl -s -X POST -H "$H" -H "$J" -d '{"name":"Old Town Pub"}' $B/native/locations | jq_ "d.get('name')"
echo "   venues: $(vens)"
echo "== 6) delete a venue that HAS events -> refused"
curl -s -X POST -H "$J" -d "{\"title\":\"Trivia\",\"event_type\":\"Trivia\",\"venue_id\":\"$VID\",\"date\":\"2026-10-12T01:00:00.000Z\",\"duration_hours\":2}" $B/events >/dev/null
echo "   -> $(curl -s -X DELETE $B/venues/$VID | jq_ "d.get('detail')")"
echo "== 7) delete from Trivia Setup while it is a venue -> refused with a pointer"
echo "   -> $(curl -s -X DELETE -H "$H" $B/native/locations/$LID -w '%{http_code}' | head -c 200)"
echo "== 8) delete an EMPTY venue (Roses) -> its location hides, pictures kept"
RID=$(curl -s $B/venues | jq_ "[v['id'] for v in d if v['name']=='Roses By The Stairs'][0]")
RLID=$(curl -s -H "$H" $B/native/locations | jq_ "[l['id'] for l in d if l['name']=='Roses By The Stairs'][0]")
curl -s -X POST -H "$H" -F "file=@/tmp/loc_karaoke.png" $B/native/locations/$RLID/images >/dev/null
curl -s -X DELETE $B/venues/$RID >/dev/null
echo "   venues:    $(vens)"; echo "   locations: $(locs)"
echo "   picture still on disk: $(find $D/home -path '*Locations/roses-by-the-stairs/branding/*' -type f | wc -l) file(s)"
echo "== 9) add it back by name -> the pictures come back"
curl -s -X POST -H "$J" -d '{"name":"Roses by the stairs","address":"2 Oak","city":"Mesa","state":"AZ"}' $B/venues >/dev/null
echo "   locations: $(locs)"
echo "   pictures: $(curl -s -H "$H" $B/native/locations | jq_ "[len(l.get('branding_images',[])) for l in d if 'oses' in l['name']]")"
echo "== 10) restart -> nothing duplicated, nothing lost"
stop; start
TOKEN=$(curl -s -X POST -H "$J" -d '{"email":"owner@example.com","password":"OwnerPass1!"}' $B/auth/login | jq_ "d.get('token','')"); H="Authorization: Bearer $TOKEN"
echo "   venues:    $(vens)"; echo "   locations: $(locs)"
echo "   events:    $(curl -s "$B/events?include_past=true" | jq_ "len(d)")"
grep -a "Traceback" $D/log.txt | head -2
stop
