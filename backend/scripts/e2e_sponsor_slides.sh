#!/bin/bash
# alpha.88 real-app check: global sponsor slides -> location sponsor slide -> final sponsor slide, across a restart.
# usage: e2e_sponsor_slides.sh <port>
cd "$(dirname "$0")/.."
PORT=$1; D=/tmp/e2e_$PORT; rm -rf $D; mkdir -p $D/db $D/home/Documents $D/data $D/app
export HOME=$D/home BIGHAT_CONFIG_PATH=$D/system_config.json BIGHAT_DB_DIR=$D/db BIGHAT_DATA_DIR=$D/data BIGHAT_PORT=$PORT LOCALAPPDATA=$D/app
B=localhost:$PORT/api; J='Content-Type: application/json'
start() { (timeout 250 python3 launcher.py >>$D/log.txt 2>&1 &); for i in $(seq 1 70); do curl -s localhost:$PORT/health >/dev/null 2>&1 && return; sleep 1; done; }
stop() { pkill -f launcher.py; sleep 2; }
jq_() { python3 -c "import sys,json
try: d=json.load(sys.stdin)
except Exception: print('(no json)'); sys.exit()
print($1)" 2>/dev/null; }
mkpng() { python3 -c "import sys;sys.stdout.buffer.write(b'\x89PNG\r\n\x1a\n'+bytes([$1])*400)" > $D/img$1.png; }
for n in 1 2 3 9; do mkpng $n; done
start
curl -s -X POST -H "$J" -d '{"license_key":"BHE-TEST-AAAA-BBBB-CCCC","offline_mode":true,"master_admin":{"email":"o@x.com","password":"OwnerPass1!","first_name":"O","last_name":"W"},"settings":{"location_name":"Test"}}' $B/native/setup/initialize >/dev/null
T=$(curl -s -X POST -H "$J" -d '{"email":"o@x.com","password":"OwnerPass1!"}' $B/auth/login | jq_ "d.get('token','')"); H="Authorization: Bearer $T"
echo "== 1) admin loads global sponsor slides (2) + the final slide, in the Global Slides panel"
for n in 1 2; do curl -s -H "$H" -F "file=@$D/img$n.png;type=image/png" $B/native/global-slides/sponsors/upload >/dev/null; done
curl -s -H "$H" -F "file=@$D/img3.png;type=image/png" $B/native/global-slides/sponsor_final/upload >/dev/null
echo "   settings: $(curl -s -H "$H" $B/native/global-slides | jq_ "{'images':len(d['sponsors']['images']),'final':bool(d['sponsors']['final']),'enabled':d['sponsors']['enabled']}")"
echo "== 2) a location with its OWN sponsor image (Trivia Setup)"
LID=$(curl -s -X POST -H "$H" -H "$J" -d '{"name":"Monkey Pants Bar Grill"}' $B/native/locations | jq_ "d['id']")
curl -s -H "$H" -F "file=@$D/img9.png;type=image/png" $B/native/locations/$LID/sponsor | jq_ "'uploaded ' + d['filename']"
echo "   preview fetch: $(curl -s -o /dev/null -w '%{http_code} %{content_type} %{size_download}B' -H "$H" $B/native/locations/$LID/sponsor/raw)"
mkdir -p "$D/home/Documents/BIG Hat Entertainment/Files/Trivia/Rounds"
printf '{"schema":"bighat-presentation/v1","id":"e2e-sp-1","name":"E2E","createdBy":"o@x.com","location_id":"%s","roundFiles":[],"slides":[]}' "$LID" > "$D/home/Documents/BIG Hat Entertainment/Files/Trivia/Rounds/e2e.bighat" 2>/dev/null || { mkdir -p "$D/home/Documents/BIG Hat Entertainment/Files/Trivia/Rounds"; printf '{"schema":"bighat-presentation/v1","id":"e2e-sp-1","name":"E2E","createdBy":"o@x.com","location_id":"%s","roundFiles":[],"slides":[]}' "$LID" > "$D/home/Documents/BIG Hat Entertainment/Files/Trivia/Rounds/e2e.bighat"; }
order() { curl -s -X POST -H "$H" -H "$J" -d '{}' $B/slide-fetcher/fetch-section/e2e-sp-1/sponsors | python3 -c "
import sys,json,base64
d=json.load(sys.stdin)
out=[]
for s in d.get('slides',[]):
    el=[e for e in s['elements'] if e['type']=='image']
    tag=base64.b64decode(el[0]['src'].split(',',1)[1])[-1] if el else '-'
    out.append((s['metadata'].get('sponsorKind','?'), tag))
print(d.get('status'), out)" 2>&1; }
echo "== 3) the show's sponsors section (kind, image tag): expect global 1, global 2, location 9, final 3"
echo "   $(order)"
echo "== 4) RESTART the app (the database is wiped on every launch): the same order must come back"
stop; start
T=$(curl -s -X POST -H "$J" -d '{"email":"o@x.com","password":"OwnerPass1!"}' $B/auth/login | jq_ "d.get('token','')"); H="Authorization: Bearer $T"
echo "   $(order)"
echo "== 5) replace the location image: only the NEW one plays"
curl -s -H "$H" -F "file=@$D/img1.png;type=image/png" $B/native/locations/$LID/sponsor >/dev/null
echo "   $(order)   files in sponsor folder: $(ls "$D/home/Documents/BIG Hat Entertainment/Files/Locations/monkey-pants-bar-grill/sponsor" | wc -l)"
echo "== 6) a different location sees only its own: (no image) -> global, global, final"
printf '{"schema":"bighat-presentation/v1","id":"e2e-sp-2","name":"E2E2","createdBy":"o@x.com","location_id":"nobody","roundFiles":[],"slides":[]}' > "$D/home/Documents/BIG Hat Entertainment/Files/Trivia/Rounds/e2e2.bighat"
curl -s -X POST -H "$H" -H "$J" -d '{}' $B/slide-fetcher/fetch-section/e2e-sp-2/sponsors | python3 -c "
import sys,json
d=json.load(sys.stdin); print('  ', [s['metadata'].get('sponsorKind') for s in d.get('slides',[])])"
echo "== 7) remove the final slide and the location image: global only"
FIN=$(curl -s -H "$H" $B/native/global-slides | jq_ "d['sponsors']['final']"); curl -s -X DELETE -H "$H" $B/native/global-slides/file/$FIN >/dev/null
curl -s -X DELETE -H "$H" $B/native/locations/$LID/sponsor -o /dev/null -w "   delete location image: %{http_code}\n"
echo "   $(order)"
stop
