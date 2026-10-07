#!/bin/bash
# repro for "locations show up regardless of price / sometimes not at all / Failed to load locations"
cd "$(dirname "$0")/.."
PORT=$1; D=/tmp/e2e_$PORT; rm -rf $D; mkdir -p $D/db $D/home/Documents $D/data $D/app
export HOME=$D/home BIGHAT_CONFIG_PATH=$D/system_config.json BIGHAT_DB_DIR=$D/db BIGHAT_DATA_DIR=$D/data BIGHAT_PORT=$PORT LOCALAPPDATA=$D/app
B=localhost:$PORT/api; J='Content-Type: application/json'
L="$D/home/Documents/BIG Hat Entertainment/Files/Locations"; mkdir -p "$L/folder-only-bar" "$L/priced-bar" "$L/zero-bar"
(timeout 250 python3 launcher.py >>$D/log.txt 2>&1 &); for i in $(seq 1 70); do curl -s localhost:$PORT/health >/dev/null 2>&1 && break; sleep 1; done
curl -s -X POST -H "$J" -d '{"license_key":"BHE-TEST-AAAA-BBBB-CCCC","offline_mode":true,"master_admin":{"email":"o@x.com","password":"OwnerPass1!","first_name":"O","last_name":"W"},"settings":{"location_name":"Test"}}' $B/native/setup/initialize >/dev/null
T=$(curl -s -X POST -H "$J" -d '{"email":"o@x.com","password":"OwnerPass1!"}' $B/auth/login | python3 -c "import sys,json;print(json.load(sys.stdin).get('token',''))"); H="Authorization: Bearer $T"
pyj(){ python3 -c "import sys,json
d=json.load(sys.stdin)
print($1)" 2>&1; }
echo "venues in Schedule at start: $(curl -s -H "$H" $B/venues | pyj "sorted(v['name'] for v in d)")"
echo "== list trivia places x4 (the SAME answer each time?)"
for i in 1 2 3 4; do echo "  call $i: $(curl -s -w ' [%{http_code}]' -H "$H" "$B/native/locations?game=trivia" | python3 -c "
import sys
raw=sys.stdin.read(); body,code=raw.rsplit(' [',1)
import json
try: d=json.loads(body); print(sorted(x['name'] for x in d), '['+code)
except Exception: print('NOT JSON', body[:120], '['+code)")"; done
echo "venues in Schedule after listing: $(curl -s -H "$H" $B/venues | pyj "sorted(v['name'] for v in d)")"
echo "== set prices: priced-bar trivia 50, zero-bar all 0"
PB=$(curl -s -H "$H" $B/venues | pyj "[v['id'] for v in d if v['name']=='Priced Bar'][0] if any(v['name']=='Priced Bar' for v in d) else ''")
echo "  priced-bar venue id: ${PB:0:8}"
[ -n "$PB" ] && curl -s -X POST -H "$H" -H "$J" -d "{\"venue_id\":\"$PB\",\"trivia_price\":50,\"music_bingo_price\":0,\"karaoke_price\":0}" $B/venue_pricing -o /dev/null -w "  save price: %{http_code}\n"
for i in 1 2 3; do echo "  trivia call $i: $(curl -s -H "$H" "$B/native/locations?game=trivia" | pyj "sorted(x['name'] for x in d)")"; done
echo "  bingo  call: $(curl -s -H "$H" "$B/native/locations?game=bingo" | pyj "sorted(x['name'] for x in d)")"
echo "  no game   : $(curl -s -H "$H" "$B/native/locations" | pyj "sorted((x['name'], x.get('games')) for x in d)")"
grep -iE "error|traceback|failed" $D/log.txt | tail -4 | cut -c1-200
pkill -f launcher.py
