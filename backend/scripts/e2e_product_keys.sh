#!/bin/bash
# Real-app check of the Product Key tab backend (fake license server).  Usage: e2e_product_keys.sh <port>
cd "$(dirname "$0")/.."
PORT=$1; LPORT=$((PORT+1)); D=/tmp/e2e_$PORT; rm -rf $D; mkdir -p $D/db $D/home/Documents
export HOME=$D/home BIGHAT_CONFIG_PATH=$D/system_config.json BIGHAT_DB_DIR=$D/db BIGHAT_DATA_DIR=$D/data BIGHAT_PORT=$PORT LOCALAPPDATA=$D/app
export BIGHAT_LICENSE_API_BASE_URL=http://127.0.0.1:$LPORT
B=localhost:$PORT/api; J='Content-Type: application/json'
jq_() { python3 -c "import sys,json
try: d=json.load(sys.stdin)
except Exception: print('(no json)'); sys.exit()
print($1)" 2>/dev/null; }
(timeout 300 python3 scripts/fake_license_server.py $LPORT >$D/lic.txt 2>&1 &)
(timeout 300 python3 launcher.py >$D/log.txt 2>&1 &)
for i in $(seq 1 70); do curl -s localhost:$PORT/health >/dev/null 2>&1 && break; sleep 1; done
curl -s -X POST -H "$J" -d '{"license_key":"BHE-AAAA-BBBB-CCCC-DDDD","offline_mode":true,"master_admin":{"email":"owner@example.com","password":"OwnerPass1!","first_name":"Owner"},"settings":{"location_name":"Test Pub"}}' $B/native/setup/initialize >/dev/null
TOKEN=$(curl -s -X POST -H "$J" -d '{"email":"owner@example.com","password":"OwnerPass1!"}' $B/auth/login | jq_ "d.get('token','')"); H="Authorization: Bearer $TOKEN"
# a plain (non-master) admin
curl -s -X POST -H "$H" -H "$J" -d '{"email":"sub@example.com","password":"SubPass123!","first_name":"Sub","last_name":"Admin","role":"admin"}' $B/native/admin/users >/dev/null
STOKEN=$(curl -s -X POST -H "$J" -d '{"email":"sub@example.com","password":"SubPass123!"}' $B/auth/login | jq_ "d.get('token','')"); SH="Authorization: Bearer $STOKEN"
show() { curl -s -H "$H" $B/native/license/product-keys | jq_ "('base=%s bingo=%s karaoke=%s extra=%s' % (d['owns_standalone'], d['addons']['music_bingo'], d['addons']['karaoke'], [e['key'] for e in d['extra_keys']]))"; }
gate() { curl -s -H "$H" $B/native/info | jq_ "{k:v for k,v in d['subscription'].items() if k in ('owns_music_bingo','owns_karaoke','music_bingo_enabled','karaoke_enabled')}"; }
add() { curl -s -w ' [%{http_code}]' -X POST -H "$1" -H "$J" -d "{\"product_key\":\"$2\"}" $B/native/license/product-key | cut -c1-230; echo; }
echo "== 0) master token ok: ${TOKEN:0:6}..  sub-admin token ok: ${STOKEN:0:6}.."
echo "== 1) no login -> refused";            echo "   $(curl -s -o /dev/null -w '%{http_code}' -X POST -H "$J" -d '{"product_key":"BHE-EEEE-FFFF-GGGG-HHHH"}' $B/native/license/product-key)"
echo "== 2) plain admin -> refused";         echo "   $(add "$SH" BHE-EEEE-FFFF-GGGG-HHHH)"
echo "== 3) before:"; echo "   $(show)"
echo "== 3b) enter the BASE key in the tab (as a new owner would)"; echo "   $(add "$H" BHE-AAAA-BBBB-CCCC-DDDD | cut -c1-30)"; echo "   $(show)"; echo "   gate: $(gate)"
echo "== 4) garbage key";                    echo "   $(add "$H" nonsense)"
echo "== 5) unknown key";                    echo "   $(add "$H" BHE-0000-0000-0000-0000)"
echo "== 6) Music Bingo add-on key (base already owned)";         echo "   $(add "$H" bhe-eeee-ffff-gggg-hhhh | cut -c1-40)"; echo "   $(show)"; echo "   gate: $(gate)"
echo "== 7) same key again (idempotent)";    echo "   $(add "$H" BHE-EEEE-FFFF-GGGG-HHHH | cut -c1-30)"; echo "   $(show)"
echo "== 8) Karaoke add-on key -> the dashboard Karaoke flag must turn on";             echo "   $(add "$H" BHE-KKKK-KKKK-KKKK-KKKK | cut -c1-30)"; echo "   $(show)"; echo "   gate: $(gate)"
echo "== 9) main key re-entered stays the main key"; echo "   $(add "$H" BHE-AAAA-BBBB-CCCC-DDDD | cut -c1-30)"; echo "   $(show)"
echo "== 10) periodic validate keeps add-ons"; curl -s -X POST -H "$H" $B/native/license/cloud/validate | jq_ "d['status']"; echo "   $(show)"
echo "== 11) license server goes OFFLINE then validate -> add-ons kept"
pkill -f fake_license_server; sleep 1; curl -s -X POST -H "$H" $B/native/license/cloud/validate | jq_ "d['status']"; echo "   $(show)"
echo "== 12) add a key while offline -> clear error, nothing changes"; echo "   $(add "$H" BHE-0000-1111-2222-3333 | cut -c1-200)"; echo "   $(show)"
echo "== 13) RESTART the app (license server still down) -> add-ons survive"
pkill -f launcher.py; sleep 2; (timeout 200 python3 launcher.py >>$D/log.txt 2>&1 &); for i in $(seq 1 70); do curl -s localhost:$PORT/health >/dev/null 2>&1 && break; sleep 1; done
TOKEN=$(curl -s -X POST -H "$J" -d '{"email":"owner@example.com","password":"OwnerPass1!"}' $B/auth/login | jq_ "d.get('token','')"); H="Authorization: Bearer $TOKEN"
echo "   $(show)"; echo "   gate: $(gate)"
echo "== 14) the secret never leaks in the status"; curl -s -H "$H" $B/native/license/product-keys | grep -c "EEEE-FFFF" | sed 's/^/   full-key occurrences: /'
pkill -f launcher.py; pkill -f fake_license_server
