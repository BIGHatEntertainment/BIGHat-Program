#!/bin/bash
# Real-app check: Creator .bighat ZIP files -> Files tool + Round Generator. Usage: e2e_bighat_upload.sh <port> [dir with .bighat files]
cd "$(dirname "$0")/.."
PORT=$1; SRC=${2:-/tmp}; D=/tmp/e2e_$PORT; rm -rf $D; mkdir -p $D/db $D/home/Documents
export HOME=$D/home BIGHAT_CONFIG_PATH=$D/system_config.json BIGHAT_DB_DIR=$D/db BIGHAT_DATA_DIR=$D/data BIGHAT_PORT=$PORT LOCALAPPDATA=$D/app
B=localhost:$PORT/api; J='Content-Type: application/json'
start() { (timeout 120 python3 launcher.py >$D/log.txt 2>&1 &); for i in $(seq 1 70); do curl -s localhost:$PORT/health >/dev/null 2>&1 && return; sleep 1; done; }
stop() { pkill -f launcher.py; sleep 2; }
rounds() { curl -s $B/roundmaker/rounds | python3 -c "import sys,json;d=json.load(sys.stdin);print(len(d),[(r.get('name'),r.get('round_type'),len(r.get('questions',[])),'DISK' if r.get('_disk_path') else 'db') for r in d])" 2>&1 | cut -c1-260; }
files() { curl -s "$B/native/files?category=Trivia" | python3 -c "import sys,json;d=json.load(sys.stdin);d=d.get(\"files\",[]) if isinstance(d,dict) else d;print([(f.get('name'),f.get('folder'),(f.get('summary') or '')[:50]) for f in d])" 2>&1 | cut -c1-300; }
ondisk() { find $D/home/Documents -name '*.bighat' | sed "s#$D/##" | sort | tr '\n' ' '; echo; }
start
curl -s -X POST -H "$J" -d '{"license_key":"BHE-TEST-AAAA-BBBB-CCCC","offline_mode":true,"master_admin":{"email":"owner@example.com","password":"OwnerPass1!","first_name":"Owner"},"settings":{"location_name":"Test Pub"}}' $B/native/setup/initialize >/dev/null
echo "== A) Upload to the FILES tool (the 'Upload .bighat' button)"
for f in $SRC/MC_02_A.bighat $SRC/MC-01-A.bighat; do echo "  $(basename $f): $(curl -s -X POST -F "file=@$f" $B/native/files/upload | cut -c1-150)"; done
echo "  on disk:   $(ondisk)"; echo "  files tool:"; files
echo "  Round Generator list: $(rounds)"
echo "== B) Open the same files in the ROUND GENERATOR ('Open .bighat...')"
for f in $SRC/MC_02_A.bighat $SRC/MC-01-A.bighat; do echo "  $(basename $f): $(curl -s -X POST -F "file=@$f" $B/bighat-files/import | cut -c1-200)"; done
echo "  on disk:   $(ondisk)"; echo "  Round Generator list: $(rounds)"
stop; start
echo "== C) After a restart"; echo "  on disk:   $(ondisk)"; echo "  Round Generator list: $(rounds)"; files
grep -a "Traceback\|bad .bighat" $D/log.txt | head -4 | cut -c1-200
stop
