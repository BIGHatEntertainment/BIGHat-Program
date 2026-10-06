#!/bin/bash
# Real-app check: employee -> user. Usage: e2e_employees.sh <port> <label>
cd "$(dirname "$0")/.."
PORT=$1; LABEL=$2; D=/tmp/e2e_$PORT
rm -rf $D; mkdir -p $D
mkdir -p $D/db
export BIGHAT_CONFIG_PATH=$D/system_config.json BIGHAT_DB_DIR=$D/db BIGHAT_DATA_DIR=$D/data BIGHAT_PORT=$PORT LOCALAPPDATA=$D/app BIGHAT_KARAOKE_DIR=$D/k BIGHAT_KARAOKE_SETTINGS=$D/ks.json BIGHAT_WINNER_VIDEOS_DIR=$D/wv
B=localhost:$PORT/api; J='Content-Type: application/json'
start() { (timeout 110 python3 launcher.py >$D/log.txt 2>&1 &); for i in $(seq 1 70); do curl -s localhost:$PORT/health >/dev/null 2>&1 && return; sleep 1; done; }
stop() { pkill -f "BIGHAT_PORT=$PORT" 2>/dev/null; pkill -f launcher.py; sleep 2; }
start
curl -s -X POST -H "$J" -d '{"license_key":"BHE-TEST-AAAA-BBBB-CCCC","offline_mode":true,"master_admin":{"email":"owner@example.com","password":"OwnerPass1!","first_name":"Owner"},"settings":{"location_name":"Test Pub"}}' $B/native/setup/initialize | head -c 120; echo
TOKEN=$(curl -s -X POST -H "$J" -d '{"email":"owner@example.com","password":"OwnerPass1!"}' $B/auth/login | python3 -c "import sys,json;d=json.load(sys.stdin);print(d.get('access_token') or d.get('token') or '')")
echo "[$LABEL] logged in as owner: $([ -n "$TOKEN" ] && echo yes || echo NO)"
A="Authorization: Bearer $TOKEN"
users() { curl -s -H "$A" $B/users | python3 -c "import sys,json;d=json.load(sys.stdin);d=d if isinstance(d,list) else d.get('users',[]);print(sorted(u['email'] for u in d))"; }
echo "[$LABEL] users before:           $(users)"
curl -s -X POST -H "$J" -d '{"name":"Sam Host","email":"Sam.Host@Example.com","phone":"555-0101","is_admin":false,"password":"SamsPass99"}' $B/employees | python3 -c "import sys,json;d=json.load(sys.stdin);print('[$LABEL] employee saved:         ',d.get('email'),'| password in reply:','password' in d)"
echo "[$LABEL] employees list:         $(curl -s $B/employees | python3 -c "import sys,json;print(sorted(e['email'] for e in json.load(sys.stdin)))")"
echo "[$LABEL] users after (load #1):  $(users)"
echo "[$LABEL] users after (load #2):  $(users)"
echo "[$LABEL] Sam can log in:         $(curl -s -o /dev/null -w '%{http_code}' -X POST -H "$J" -d '{"email":"sam.host@example.com","password":"SamsPass99"}' $B/auth/login)"
echo "[$LABEL] duplicate email ->      $(curl -s -o /dev/null -w '%{http_code}' -X POST -H "$J" -d '{"name":"Sam Two","email":"sam.host@example.com","is_admin":false}' $B/employees)"
echo "[$LABEL] bad email ->            $(curl -s -o /dev/null -w '%{http_code}' -X POST -H "$J" -d '{"name":"Nope","email":"not-an-email","is_admin":false}' $B/employees)"
EID=$(curl -s $B/employees | python3 -c "import sys,json;print([e['id'] for e in json.load(sys.stdin) if e['email']=='sam.host@example.com'][0])")
curl -s -X PUT -H "$J" -d '{"name":"Sam Q Host","email":"sam.host@example.com","phone":"555-0202","is_admin":true}' $B/employees/$EID >/dev/null
echo "[$LABEL] after making Sam admin: $(curl -s -H "$A" $B/users | python3 -c "import sys,json;d=json.load(sys.stdin);d=d if isinstance(d,list) else d.get('users',[]);print([(u['email'],u['role']) for u in d if 'sam' in u['email']])")"
echo "[$LABEL] Sam still logs in (old pw kept): $(curl -s -o /dev/null -w '%{http_code}' -X POST -H "$J" -d '{"email":"sam.host@example.com","password":"SamsPass99"}' $B/auth/login)"
curl -s -X POST -H "$J" -d '{"name":"No Pw Nina","email":"nina@example.com","is_admin":false}' $B/employees >/dev/null
echo "[$LABEL] employee added with NO password uses the default host password: $(curl -s -o /dev/null -w '%{http_code}' -X POST -H "$J" -d '{"email":"nina@example.com","password":"'"$(python3 -c "import sys;sys.path.insert(0,'.');import os;os.environ.setdefault('MONGO_URL','x');from server import DEFAULT_HOST_PASSWORD as p;print(p)" 2>/dev/null)"'"}' $B/auth/login)"
curl -s -X POST -H "$J" -d '{"new_password":"BrandNew77"}' $B/employees/$EID/password/reset >/dev/null
echo "[$LABEL] after Reset password:   old pw=$(curl -s -o /dev/null -w '%{http_code}' -X POST -H "$J" -d '{"email":"sam.host@example.com","password":"SamsPass99"}' $B/auth/login) new pw=$(curl -s -o /dev/null -w '%{http_code}' -X POST -H "$J" -d '{"email":"sam.host@example.com","password":"BrandNew77"}' $B/auth/login)"
echo "[$LABEL] too-short reset ->       $(curl -s -o /dev/null -w '%{http_code}' -X POST -H "$J" -d '{"new_password":"abc"}' $B/employees/$EID/password/reset)"
stop
start
TOKEN=$(curl -s -X POST -H "$J" -d '{"email":"owner@example.com","password":"OwnerPass1!"}' $B/auth/login | python3 -c "import sys,json;d=json.load(sys.stdin);print(d.get('access_token') or d.get('token') or '')"); A="Authorization: Bearer $TOKEN"
echo "[$LABEL] AFTER RESTART employees: $(curl -s $B/employees | python3 -c "import sys,json;print(sorted(e['email'] for e in json.load(sys.stdin)))")"
echo "[$LABEL] AFTER RESTART users:     $(users)"
curl -s -X DELETE $B/employees/$EID >/dev/null
echo "[$LABEL] after deleting Sam:      employees=$(curl -s $B/employees | python3 -c "import sys,json;print(sorted(e['email'] for e in json.load(sys.stdin)))") users=$(users)"
echo "[$LABEL] Sam can still log in?    $(curl -s -o /dev/null -w '%{http_code}' -X POST -H "$J" -d '{"email":"sam.host@example.com","password":"SamsPass99"}' $B/auth/login)"
stop
