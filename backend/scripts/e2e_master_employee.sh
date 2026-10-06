#!/bin/bash
# Real-app check: the master admin is also a Schedule employee and their password is never replaced.  Usage: e2e_master_employee.sh <port>
cd "$(dirname "$0")/.."
PORT=$1; D=/tmp/e2e_$PORT; rm -rf $D; mkdir -p $D/db $D/home/Documents
export HOME=$D/home BIGHAT_CONFIG_PATH=$D/system_config.json BIGHAT_DB_DIR=$D/db BIGHAT_DATA_DIR=$D/data BIGHAT_PORT=$PORT LOCALAPPDATA=$D/app BIGHAT_NATIVE_MODE=1
B=localhost:$PORT/api; J='Content-Type: application/json'
wipe_row() { stop; python3 - <<PY
import os, asyncio
os.environ["BIGHAT_NATIVE_MODE"]="1"
from native import db_factory
db = db_factory.get_db()
async def go():
    r = await db.employees.delete_many({"email": "sellards@bighat.live"}); print("   (db) removed master row:", r.deleted_count)
asyncio.run(go())
PY
}
start() { (timeout 250 python3 launcher.py >>$D/log.txt 2>&1 &); for i in $(seq 1 70); do curl -s localhost:$PORT/health >/dev/null 2>&1 && return; sleep 1; done; }
stop() { pkill -f launcher.py; sleep 2; }
login() { curl -s -o /dev/null -w '%{http_code}' -X POST -H "$J" -d "{\"email\":\"$1\",\"password\":\"$2\"}" $B/auth/login; }
tok() { curl -s -X POST -H "$J" -d '{"email":"sellards@bighat.live","password":"MyRealPass#1"}' $B/auth/login | python3 -c "import sys,json;print(json.load(sys.stdin).get('token',''))"; }
emps() { curl -s -H "Authorization: Bearer $(tok)" $B/employees | python3 -c "import sys,json;print(sorted((e['email'],e['is_admin']) for e in json.load(sys.stdin)))"; }
start
curl -s -X POST -H "$J" -d '{"license_key":"BHE-TEST-AAAA-BBBB-CCCC","offline_mode":true,"master_admin":{"email":"Sellards@BigHat.live","password":"MyRealPass#1","first_name":"Nick","last_name":"Sellards"},"settings":{"location_name":"Test Pub"}}' $B/native/setup/initialize >/dev/null
H="Authorization: Bearer $(tok)"
echo "== 1) right after setup the master is in the Schedule list"; echo "   $(emps)"
echo "== 2) try to add the master again (any case, spaces) -> refused, password untouched"
for e in "sellards@bighat.live" "  SELLARDS@BIGHAT.LIVE "; do echo "   -> $(curl -s -X POST -H "$H" -H "$J" -d "{\"name\":\"Nick\",\"email\":\"$e\",\"is_admin\":true}" $B/employees | cut -c1-110)"; done
echo "   real password still works: $(login sellards@bighat.live 'MyRealPass#1')"
echo "== 3) OLD INSTALL: master has NO employee row (as before this update), then update/start -> row appears, password kept"
wipe_row; start; echo "   list after start: $(emps)   real password: $(login sellards@bighat.live 'MyRealPass#1')"
echo "== 4) edit the master's row with a typed password (even from the Schedule) -> login password must not change"
EID=$(curl -s -H "$H" $B/employees | python3 -c "import sys,json;print(json.load(sys.stdin)[0]['id'])")
curl -s -X PUT -H "$H" -H "$J" -d '{"name":"Nick Sellards","email":"sellards@bighat.live","is_admin":true,"password":"Hacked-Pass-9"}' $B/employees/$EID | cut -c1-90; echo
echo "   real: $(login sellards@bighat.live 'MyRealPass#1')   typed-in-schedule: $(login sellards@bighat.live 'Hacked-Pass-9')   (want 200 / 401)"
echo "== 5) password reset endpoint on the master's row -> refused to change the login"
curl -s -X POST -H "$H" -H "$J" -d '{"new_password":"Reset-Pass-77"}' $B/employees/$EID/password/reset | cut -c1-90; echo
echo "   real: $(login sellards@bighat.live 'MyRealPass#1')   reset-pw: $(login sellards@bighat.live 'Reset-Pass-77')   (want 200 / 401)"
echo "== 6) a normal host still gets a temp password and can log in"
H="Authorization: Bearer $(tok)"; R=$(curl -s -X POST -H "$H" -H "$J" -d '{"name":"Pat Host","email":"pat@example.com","is_admin":false}' $B/employees); TP=$(echo "$R" | python3 -c "import sys,json;print(json.load(sys.stdin).get('temp_password',''))")
echo "   temp given: $([ -n "$TP" ] && echo yes || echo NO)   login with it: $(login pat@example.com "$TP")"
echo "== 7) RESTART -> still one master row, real password still works"
stop; start; echo "   real: $(login sellards@bighat.live 'MyRealPass#1')   list: $(emps)"
echo "== 8) OLD INSTALL, but this time the owner tries to add themselves BEFORE restarting"
wipe_row; start; wipe_row; start
H="Authorization: Bearer $(tok)"; echo "   (row was put back at start) add -> $(curl -s -X POST -H "$H" -H "$J" -d '{"name":"Nick","email":"sellards@bighat.live","is_admin":true}' $B/employees | cut -c1-150)"
echo "   real password: $(login sellards@bighat.live 'MyRealPass#1')   list: $(emps)"
stop
