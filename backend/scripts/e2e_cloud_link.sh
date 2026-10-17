#!/bin/bash
# Real-app check: the cloud-link code is permanent across a restart and lives in the per-user data folder.
# Usage: e2e_cloud_link.sh <port>
cd "$(dirname "$0")/.."
PORT=$1; D=/tmp/e2e_$PORT; rm -rf $D; mkdir -p $D/home/Documents
export HOME=$D/home BIGHAT_PORT=$PORT
unset BIGHAT_DB_DIR BIGHAT_DATA_DIR BIGHAT_FILES_DIR LOCALAPPDATA BIGHAT_BACKUPS_DIR BIGHAT_CLOUD_BASE_URL
# Do what the launcher does in the installed program: pin the config + data root into the per-user data folder.
U=$D/home/.local/share/BIGHat/data; mkdir -p $U
export BIGHAT_CONFIG_PATH=$U/system_config.json BIGHAT_DATA_ROOT=$U/app
B=localhost:$PORT/api/native/system/cloud-link
start() { (timeout 300 python3 launcher.py >$D/log.txt 2>&1 &); for i in $(seq 1 70); do curl -s localhost:$PORT/health >/dev/null 2>&1 && return; sleep 1; done; echo "backend did not start"; tail -20 $D/log.txt; exit 1; }
stop() { pkill -f launcher.py; sleep 2; }
start
S1=$(curl -s $B/status); echo "first start:  $S1"
C1=$(echo "$S1" | python3 -c "import sys,json;print(json.load(sys.stdin)['code'])")
F=$(find $D/home -name cloud_link.json | head -1); echo "file:         ${F#$D/home/}"
IN_SRC=$(find "$(pwd)" -name cloud_link.json 2>/dev/null | head -1); echo "in source tree: ${IN_SRC:-none}"
stop; start
C2=$(curl -s $B/status | python3 -c "import sys,json;print(json.load(sys.stdin)['code'])")
echo "after restart: $C2   (same as before: $([ "$C1" = "$C2" ] && echo YES || echo NO))"
echo "check with no cloud address: $(curl -s -X POST $B/check)"
stop
[ "$C1" = "$C2" ] && [ -n "$F" ] && [ -z "$IN_SRC" ] && echo RESULT: PASS || echo RESULT: FAIL
