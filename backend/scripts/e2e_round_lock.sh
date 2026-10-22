#!/bin/bash
# Real-app check of the 180-day lock: build a show, then ask for the round lists the way the Build Wizard and Round Roulette do.
# Usage: e2e_round_lock.sh <port>
cd "$(dirname "$0")/.."
PORT=$1; D=/tmp/e2e_lock_$PORT; rm -rf $D; mkdir -p $D/home/Documents
export HOME=$D/home BIGHAT_PORT=$PORT
unset BIGHAT_DB_DIR BIGHAT_DATA_DIR BIGHAT_FILES_DIR LOCALAPPDATA BIGHAT_BACKUPS_DIR
U=$D/home/.local/share/BIGHat/data; mkdir -p $U
export BIGHAT_CONFIG_PATH=$U/system_config.json BIGHAT_DATA_ROOT=$U/app
F="$D/home/Documents/BIG Hat Entertainment/Files"
for t in MC REG MISC MYS BIG; do mkdir -p "$F/Trivia/$t"; for n in a b; do echo '{"schema":"bighat-round/v1","name":"x","questions":[{"question":"q","answer":"a"}]}' > "$F/Trivia/$t/$t-$n.bighat"; done; done
mkdir -p "$F/Hosts/h@x.com" "$F/Locations/bar" "$F/Trivia/Rounds"
echo '{"email":"h@x.com","display_name":"H","id":"h@x.com"}' > "$F/Hosts/h@x.com/host.json"
echo '{"id":"loc-1","name":"Bar & Grill","slug":"bar"}' > "$F/Locations/bar/location.json"
start() { (timeout 200 python3 launcher.py >$D/log.txt 2>&1 &); for i in $(seq 1 70); do curl -s localhost:$PORT/health >/dev/null 2>&1 && return; sleep 1; done; echo "backend did not start"; tail -20 $D/log.txt; exit 1; }
stop() { pkill -f launcher.py; sleep 2; }
J='-H content-type:application/json'
count() { python3 -c "import sys,json;print(len(json.load(sys.stdin)))"; }
start
echo "REG list before build, location sent as the wizard does: $(curl -s "localhost:$PORT/api/trivia/round-files/reg?location=location:loc-1" | count) (expect 2)"
echo "build 1:   $(curl -s -X POST localhost:$PORT/api/native/presentations/build $J -d '{"name":"Show1","host_id":"h@x.com","location_id":"loc-1","round_count":5,"round_files":["MC-a","REG-a","MISC-a","MYS-a","BIG-a"]}' | cut -c1-60)"
for form in "location:loc-1" "/api/native/locations/loc-1/images/i1/raw" "Bar%20%26%20Grill" "loc-1"; do
  echo "REG list after build, location=$form: $(curl -s "localhost:$PORT/api/trivia/round-files/reg?location=$form" | count) (expect 1)"; done
echo "rebuild same rounds: $(curl -s -X POST localhost:$PORT/api/native/presentations/build $J -d '{"name":"Show2","host_id":"h@x.com","location_id":"loc-1","round_count":5,"round_files":["MC-a","REG-a","MISC-a","MYS-a","BIG-a"]}' | cut -c1-140)"
echo "legacy import of a locked round: $(curl -s -o /dev/null -w '%{http_code}' -X POST localhost:$PORT/api/presentations/import-trivia $J -d '{"userName":"n","host":"h","location":"location:loc-1","numRounds":5,"rounds":["Files/Trivia/REG/REG-a.bighat"],"roundTypes":["REG"],"roundNames":["REG-a"],"nativeManifest":{"location":{"id":"loc-1","name":"Bar & Grill","slug":"bar"},"host":{"name":"H"}}}') (expect 409)"
stop; start
echo "after restart, REG list: $(curl -s "localhost:$PORT/api/trivia/round-files/reg?location=location:loc-1" | count) (expect 1)"
echo "usage file on disk: $(find $D/home -name round_usage.json | sed "s|$D/home/||" | tr '\n' ' ')"
stop
