#!/bin/bash
# Real-app check of the 180-day lock as the Build Wizard and Round Roulette see it:
#  build -> lists -> re-uploaded copies (other file names) -> admin RELEASE (single / show / all) -> lists -> restart -> lists.
# Usage: e2e_lock_release.sh <port>
cd "$(dirname "$0")/.."
PORT=$1; D=/tmp/e2e_rel_$PORT; rm -rf $D; mkdir -p $D/home/Documents
export HOME=$D/home BIGHAT_PORT=$PORT
unset BIGHAT_DB_DIR BIGHAT_DATA_DIR BIGHAT_FILES_DIR LOCALAPPDATA BIGHAT_BACKUPS_DIR
U=$D/home/.local/share/BIGHat/data; mkdir -p $U
export BIGHAT_CONFIG_PATH=$U/system_config.json BIGHAT_DATA_ROOT=$U/app
F="$D/home/Documents/BIG Hat Entertainment/Files"
R='{"schema":"bighat-round/v1","name":"x","questions":[{"question":"q","answer":"a"}]}'
for t in MC REG MISC MYS BIG; do mkdir -p "$F/Trivia/$t"; for n in a b c d; do echo "$R" > "$F/Trivia/$t/$t-$n.bighat"; done; done
# the SAME round MC-a again under the other names a re-upload produces
echo "$R" > "$F/Trivia/MC/MC__MC-a.bighat"; echo "$R" > "$F/Trivia/MC/MC-a-3f9a1b2c.bighat"
mkdir -p "$F/Hosts/h@x.com" "$F/Locations/bar" "$F/Trivia/Rounds"
echo '{"email":"h@x.com","display_name":"H","id":"h@x.com"}' > "$F/Hosts/h@x.com/host.json"
echo '{"id":"loc-1","name":"Test Venue","slug":"bar"}' > "$F/Locations/bar/location.json"
start() { (timeout 280 python3 launcher.py >$D/log.txt 2>&1 &); for i in $(seq 1 70); do curl -s localhost:$PORT/health >/dev/null 2>&1 && return; sleep 1; done; echo "backend did not start"; tail -20 $D/log.txt; exit 1; }
stop() { pkill -f launcher.py; sleep 2; }
J='-H content-type:application/json'; A="userName=nick"
names() { python3 -c "import sys,json;d=json.load(sys.stdin);print(', '.join(sorted(x['name'] for x in d)))"; }
mc() { echo "   MC list ($1): $(curl -s "localhost:$PORT/api/trivia/round-files/mc?location=$2" | names)"; }
build() { curl -s -X POST localhost:$PORT/api/native/presentations/build $J -d "{\"name\":\"$1\",\"host_id\":\"h@x.com\",\"location_id\":\"loc-1\",\"round_count\":5,\"round_files\":[\"$2\",\"REG-$3\",\"MISC-$3\",\"MYS-$3\",\"BIG-$3\"]}" | python3 -c "import sys,json;d=json.load(sys.stdin);print('built' if d.get('id') else d.get('detail','?')[:70])"; }
rid() { curl -s "localhost:$PORT/api/admin/round-usage?$A" | python3 -c "import sys,json;print([r['id'] for r in json.load(sys.stdin) if r['roundFileName'].lower()=='$1'.lower()][0])"; }
LOC="location:loc-1"
start
mc "before any build" $LOC
echo "== 1 build a show that uses MC-a   -> $(build Show1 MC-a a)"
mc "after build: MC-a, MC__MC-a and the stamped copy must ALL be gone" $LOC
echo "   wizard sends the venue image url instead:  $(curl -s "localhost:$PORT/api/trivia/round-files/mc?location=/api/native/locations/loc-1/images/i1/raw" | names)"
echo "   building MC__MC-a (same round) again     -> $(build ShowX MC__MC-a b)   (expect refused)"
echo "== 2 admin releases MC-a ONCE   -> $(curl -s -X DELETE "localhost:$PORT/api/admin/round-usage/$(rid MC-a)?$A" | cut -c1-60)"
mc "after release: every spelling back" $LOC
echo "== 3 restart the app";  stop; start; mc "after restart (release must hold)" $LOC
echo "== 4 build MC-b, release the whole show, restart"
echo "   $(build Show2 MC-b c)"; mc "MC-b locked" $LOC
PID=$(curl -s "localhost:$PORT/api/admin/round-usage?$A" | python3 -c "import sys,json;print([r['presentationId'] for r in json.load(sys.stdin) if r['roundFileName'].lower()=='mc-b'][0])")
echo "   release show -> $(curl -s -X DELETE "localhost:$PORT/api/admin/round-usage/by-presentation/$PID?$A" | cut -c1-60)"
stop; start; mc "after release show + restart" $LOC
echo "== 5 build again after a release locks again -> $(build Show3 MC-b d)"; mc "MC-b locked again" $LOC
echo "== 6 release EVERYTHING -> $(curl -s -X POST "localhost:$PORT/api/admin/round-usage/release-all?$A" | cut -c1-60)"; stop; start; mc "after release-all + restart" $LOC
echo "   usage file: $(python3 -c "import json,glob;f=glob.glob('$D/home/Documents/*/Files/Trivia/round_usage.json')[0];d=json.load(open(f));print(len(d['records']),'records,',len(d['released_rounds']),'released round memories')")"
stop
