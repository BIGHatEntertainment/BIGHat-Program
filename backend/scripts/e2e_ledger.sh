#!/bin/bash
# Real-app check: credential ledger + lost-user recovery. Usage: e2e_ledger.sh <port>
cd "$(dirname "$0")/.."
PORT=$1; D=/tmp/e2e_$PORT; rm -rf $D; mkdir -p $D/db
export BIGHAT_CONFIG_PATH=$D/system_config.json BIGHAT_DB_DIR=$D/db BIGHAT_DATA_DIR=$D/data BIGHAT_PORT=$PORT LOCALAPPDATA=$D/app
B=localhost:$PORT/api; J='Content-Type: application/json'
start() { (timeout 100 python3 launcher.py >$D/log.txt 2>&1 &); for i in $(seq 1 70); do curl -s localhost:$PORT/health >/dev/null 2>&1 && return; sleep 1; done; }
stop() { pkill -f launcher.py; sleep 2; }
login() { curl -s -o /dev/null -w '%{http_code}' -X POST -H "$J" -d "{\"email\":\"$1\",\"password\":\"$2\"}" $B/auth/login; }
start
curl -s -X POST -H "$J" -d '{"license_key":"BHE-TEST-AAAA-BBBB-CCCC","offline_mode":true,"master_admin":{"email":"owner@example.com","password":"OwnerPass1!","first_name":"Owner"},"settings":{"location_name":"Test Pub"}}' $B/native/setup/initialize >/dev/null
curl -s -X POST -H "$J" -d '{"name":"Sam Host","email":"sam@example.com","is_admin":false,"password":"SamsPass99"}' $B/employees >/dev/null
L=$(find $D -name credentials.ledger | head -1)
echo "ledger file: ${L#$D/}"; echo "key file:    $(find $D -name ledger.key | head -1 | sed "s#$D/##")"
echo "ledger copies outside the secure folder: $(find $D -name 'credentials.ledger' -not -path '*/secure/*' | wc -l)"
echo "readable email/password inside ledger: $(grep -c -a 'sam@example.com\|SamsPass99\|owner@example.com' $L)"
echo "data map written: $(find $D -name file_map.json | head -1 | sed "s#$D/##")"
stop
python3 - <<P
import json
p="$D/system_config.json"; c=json.load(open(p))
c["users"]=[u for u in c["users"] if u["email"]!="sam@example.com"]; json.dump(c,open(p,"w"))
print("config users after simulated loss:", [u["email"] for u in c["users"]])
P
start
echo "Sam restored and can log in: $(login sam@example.com SamsPass99)"
echo "Owner still logs in:         $(login owner@example.com 'OwnerPass1!')"
grep -a "alpha.73" $D/log.txt | cut -c1-160 | head -3
stop
