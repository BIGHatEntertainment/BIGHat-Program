#!/bin/bash
# fire many list calls AT THE SAME TIME and see whether the answers agree (and none fail)
cd "$(dirname "$0")/.."
PORT=$1; D=/tmp/e2e_$PORT; rm -rf $D; mkdir -p $D/db $D/home/Documents $D/data $D/app
export HOME=$D/home BIGHAT_CONFIG_PATH=$D/system_config.json BIGHAT_DB_DIR=$D/db BIGHAT_DATA_DIR=$D/data BIGHAT_PORT=$PORT LOCALAPPDATA=$D/app
B=localhost:$PORT/api; J='Content-Type: application/json'
L="$D/home/Documents/BIG Hat Entertainment/Files/Locations"; for n in a-bar b-bar c-bar d-bar e-bar f-bar; do mkdir -p "$L/$n"; done
(timeout 250 python3 launcher.py >>$D/log.txt 2>&1 &); for i in $(seq 1 70); do curl -s localhost:$PORT/health >/dev/null 2>&1 && break; sleep 1; done
curl -s -X POST -H "$J" -d '{"license_key":"BHE-TEST-AAAA-BBBB-CCCC","offline_mode":true,"master_admin":{"email":"o@x.com","password":"OwnerPass1!","first_name":"O","last_name":"W"},"settings":{"location_name":"Test"}}' $B/native/setup/initialize >/dev/null
T=$(curl -s -X POST -H "$J" -d '{"email":"o@x.com","password":"OwnerPass1!"}' $B/auth/login | python3 -c "import sys,json;print(json.load(sys.stdin).get('token',''))"); H="Authorization: Bearer $T"
for round in 1 2 3; do
  rm -f $D/r_*.txt
  for i in $(seq 1 12); do ( curl -s -o $D/r_$i.txt -w "%{http_code}\n" -H "$H" "$B/native/locations" > $D/c_$i.txt ) & done; wait
  codes=$(cat $D/c_*.txt | sort | uniq -c | tr '\n' ' ')
  shapes=$(for i in $(seq 1 12); do python3 -c "import sys,json
try: d=json.load(open('$D/r_$i.txt')); print(len(d), sorted(x['name'] for x in d)[:3])
except Exception: print('NOT-JSON')"; done | sort | uniq -c | tr '\n' ';')
  echo "burst $round: status [$codes] answers [$shapes]"
done
echo "venues: $(curl -s -H "$H" $B/venues | python3 -c "import sys,json;d=json.load(sys.stdin);print(len(d), 'unique names', len(set(v['name'] for v in d)))")"
echo "locations: $(curl -s -H "$H" $B/native/locations | python3 -c "import sys,json;d=json.load(sys.stdin);print(len(d), 'unique slugs', len(set(v['slug'] for v in d)))")"
pkill -f launcher.py
