#!/bin/bash
# Real-app check: a File Creator .bighat with image/gif/video+poster is uploaded to the real Files tool, imported, built into a show,
# and the slides are read back from the real API. Usage: e2e_creator_media.sh <port> <dir with REG__media-test.bighat>
cd "$(dirname "$0")/.."
PORT=$1; SRC=$2; D=/tmp/e2e_media_$PORT; rm -rf $D; mkdir -p $D/home/Documents
export HOME=$D/home BIGHAT_PORT=$PORT
unset BIGHAT_DB_DIR BIGHAT_DATA_DIR BIGHAT_FILES_DIR LOCALAPPDATA BIGHAT_BACKUPS_DIR
U=$D/home/.local/share/BIGHat/data; mkdir -p $U
export BIGHAT_CONFIG_PATH=$U/system_config.json BIGHAT_DATA_ROOT=$U/app
F="$D/home/Documents/BIG Hat Entertainment/Files"
for t in MC REG MISC MYS BIG; do mkdir -p "$F/Trivia/$t"; done
mkdir -p "$F/Hosts/h@x.com" "$F/Locations/bar" "$F/Trivia/Rounds"
echo '{"email":"h@x.com","display_name":"H","id":"h@x.com"}' > "$F/Hosts/h@x.com/host.json"
echo '{"id":"loc-1","name":"Bar","slug":"bar"}' > "$F/Locations/bar/location.json"
for t in REG MC BIG; do cp "$SRC/${t}__media-test.bighat" "$F/Trivia/$t/"; done
start() { (timeout 200 python3 launcher.py >$D/log.txt 2>&1 &); for i in $(seq 1 70); do curl -s localhost:$PORT/health >/dev/null 2>&1 && return; sleep 1; done; echo "backend did not start"; tail -20 $D/log.txt; exit 1; }
start
echo "files in the REG folder after startup: $(ls "$F/Trivia/REG" | tr '\n' ' ')"
J='-H content-type:application/json'
# the Round Generator needs 5 rounds per show; one file per type is enough, the rest are plain filler files
for t in MC REG MISC MYS BIG; do for n in x y z w v u; do [ -e "$F/Trivia/$t/$t-$n.bighat" ] || echo '{"schema":"bighat-round/v1","round_type":"'$t'","name":"f","questions":[{"question":"q","answer":"a"}]}' > "$F/Trivia/$t/$t-$n.bighat"; done; done
CONV() { ls "$F/Trivia/$1" | grep -i "media-test" | grep -v _creator | head -1 | sed 's/.bighat$//'; }
for t in REG MC BIG; do
  case $t in REG) FILES="[\"MC-x\",\"$(CONV REG)\",\"MISC-x\",\"MYS-x\",\"BIG-x\"]";; MC) FILES="[\"$(CONV MC)\",\"REG-y\",\"MISC-y\",\"MYS-y\",\"BIG-y\"]";; BIG) FILES="[\"MC-z\",\"REG-z\",\"MISC-z\",\"MYS-z\",\"$(CONV BIG)\"]";; esac
  R=$(curl -s -X POST localhost:$PORT/api/native/presentations/build $J -d "{\"name\":\"Show-$t\",\"host_id\":\"h@x.com\",\"location_id\":\"loc-1\",\"round_count\":5,\"round_files\":$FILES}")
  PID=$(echo "$R" | python3 -c "import sys,json;print(json.load(sys.stdin).get('id',''))" 2>/dev/null)
  echo "[$t] build: ${R:0:80}"
  case $t in REG) N=2;; MC) N=1;; BIG) N=5;; esac
  curl -s -X POST localhost:$PORT/api/slide-fetcher/fetch-section/$PID/round_$N $J -d '{}' > $D/slides_$t.json
  python3 - $D/slides_$t.json <<'PY'
import sys, json
d = json.load(open(sys.argv[1]))
sl = d if isinstance(d, list) else (d.get("slides") or [])
print("   slides in the round section:", len(sl), "" if sl else str(d)[:200])
for s in sl:
    md = s.get("metadata") or {}
    if md.get("isReview") or md.get("isAnswers") or md.get("isGifStop") or md.get("isRoundTitle"):
        continue
    m = [(e["type"], (e.get("videoSrc") or e.get("src") or "")[5:15]) for e in s.get("elements", [])
         if e.get("type") in ("image", "video") and (e.get("width") or 0) < 1900]
    if m:
        print("    q", md.get("questionNumber"), m)
PY
done
pkill -f launcher.py
