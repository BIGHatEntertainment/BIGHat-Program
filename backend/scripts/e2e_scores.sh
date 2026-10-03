#!/bin/bash
# Real-app check: trivia scores saved on the PC. Usage: e2e_scores.sh <port>
cd "$(dirname "$0")/.."
PORT=$1; D=/tmp/e2e_$PORT; rm -rf $D; mkdir -p $D/db
export BIGHAT_FILES_DIR=$D/docs BIGHAT_CONFIG_PATH=$D/system_config.json BIGHAT_DB_DIR=$D/db BIGHAT_DATA_DIR=$D/data BIGHAT_PORT=$PORT LOCALAPPDATA=$D/app
B=localhost:$PORT/api; J='Content-Type: application/json'
start() { (timeout 100 python3 launcher.py >$D/log.txt 2>&1 &); for i in $(seq 1 70); do curl -s localhost:$PORT/health >/dev/null 2>&1 && return; sleep 1; done; }
stop() { pkill -f launcher.py; sleep 2; }
start
curl -s -X POST -H "$J" -d '{"license_key":"BHE-TEST-AAAA-BBBB-CCCC","offline_mode":true,"master_admin":{"email":"owner@example.com","password":"OwnerPass1!","first_name":"Owner"},"settings":{"location_name":"Test Pub"}}' $B/native/setup/initialize >/dev/null
BODY='{"locationName":"The Pub","presentationName":"Friday","presentationDate":"10/03/2026","presentationId":"p1","teams":[{"name":"Quizzly Bears","roundScores":[5,7],"total":12},{"name":"Brainstormers","roundScores":[4,6],"total":10}],"rounds":[{"label":"R1","multiplier":1},{"label":"R2","multiplier":2}]}'
echo "save #1: $(curl -s -w ' [%{http_code}]' -X POST -H "$J" -d "$BODY" $B/scores/save | cut -c1-200)"
echo "save #2 (same night): $(curl -s -X POST -H "$J" -d "$BODY" $B/scores/save | python3 -c 'import sys,json;print(json.load(sys.stdin)["path"])')"
echo "files on disk:"; find $D -name '*.json' -path '*Scores*' | sed "s#$D/##" | sort
echo "list: $(curl -s $B/scores/files | python3 -c 'import sys,json;d=json.load(sys.stdin);print([(g["location"],g["fileCount"]) for g in d])')"
stop; start
FID=$(curl -s $B/scores/files | python3 -c 'import sys,json;d=json.load(sys.stdin);print(d[0]["files"][0]["id"])')
echo "after restart, list: $(curl -s $B/scores/files | python3 -c 'import sys,json;d=json.load(sys.stdin);print([(g["location"],g["fileCount"]) for g in d])')"
echo "read one: $(curl -s $B/scores/files/$FID | python3 -c 'import sys,json;d=json.load(sys.stdin);print(d["rankings"][0])')"
echo "delete one: $(curl -s -X DELETE $B/scores/files/$FID)"
echo "list after delete: $(curl -s $B/scores/files | python3 -c 'import sys,json;d=json.load(sys.stdin);print([(g["location"],g["fileCount"]) for g in d])')"
echo "delete again -> $(curl -s -o /dev/null -w '%{http_code}' -X DELETE $B/scores/files/$FID)"
echo "path trick -> $(curl -s -o /dev/null -w '%{http_code}' -X DELETE "$B/scores/files/..%2F..%2Fx/a.json")"
grep -a "Traceback" $D/log.txt | head -2
stop
