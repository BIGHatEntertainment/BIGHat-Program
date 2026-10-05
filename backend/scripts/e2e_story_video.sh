#!/bin/bash
# Real-app check: a Bingo/Karaoke story video on a PC with NO ffmpeg. Usage: e2e_story_video.sh <port>
cd "$(dirname "$0")/.."
PORT=$1; D=/tmp/e2e_$PORT; rm -rf $D; mkdir -p $D/db $D/home/Documents
export HOME=$D/home BIGHAT_CONFIG_PATH=$D/system_config.json BIGHAT_DB_DIR=$D/db BIGHAT_DATA_DIR=$D/data BIGHAT_PORT=$PORT LOCALAPPDATA=$D/app BIGHAT_IGNORE_SYSTEM_FFMPEG=1
B=localhost:$PORT/api; J='Content-Type: application/json'
start() { (timeout 400 python3 launcher.py >$D/log.txt 2>&1 &); for i in $(seq 1 70); do curl -s localhost:$PORT/health >/dev/null 2>&1 && return; sleep 1; done; echo "SERVER DID NOT START"; }
stop() { pkill -f launcher.py; sleep 2; }
jget() { python3 -c "import sys,json
try:
    d=json.load(sys.stdin)
except Exception:
    print('(no json)'); sys.exit()
print($1)" 2>/dev/null; }
start
curl -s -X POST -H "$J" -d '{"license_key":"BHE-TEST-AAAA-BBBB-CCCC","offline_mode":true,"master_admin":{"email":"owner@example.com","password":"OwnerPass1!","first_name":"Owner"},"settings":{"location_name":"Test Pub"}}' $B/native/setup/initialize >/dev/null
stop
python3 - <<P
import json
p="$D/system_config.json"; c=json.load(open(p)); c.setdefault("subscription",{})["story_generator_enabled"]=True; json.dump(c,open(p,"w"))
P
start
TOKEN=$(curl -s -X POST -H "$J" -d '{"email":"owner@example.com","password":"OwnerPass1!"}' $B/auth/login | jget "d.get('token','')"); H="Authorization: Bearer $TOKEN"
echo "login token: ${TOKEN:0:6}..."
echo "upload location: $(curl -s -X POST -H "$H" -F file=@/tmp/loc_bingo.png -F 'name=Roses By The Stairs' $B/story-generator/story-images/bingo | cut -c1-90)"
echo "upload host:     $(curl -s -X POST -H "$H" -F file=@/tmp/host_alex.gif -F 'name=Nick Sellards' $B/story-generator/story-images/hosts | cut -c1-90)"
curl -s -X POST -H "$H" -F file=@/tmp/loc_karaoke.png -F 'name=Roses By The Stairs' $B/story-generator/story-images/karaoke >/dev/null
for EV in bingo karaoke; do
  JOB=$(curl -s -X POST -H "$H" -H "$J" -d "{\"event_type\":\"$EV\",\"location_id\":\"Roses By The Stairs.png\",\"location_name\":\"Roses By The Stairs\",\"host_id\":\"Nick Sellards.gif\",\"host_name\":\"Nick Sellards\",\"host_is_gif\":true}" $B/story-generator/generate-event-video | jget "d.get('jobId') or str(d)[:100]")
  echo "== $EV job: $JOB"
  case "$JOB" in *premium*|*no\ json*|"") continue;; esac
  for i in $(seq 1 40); do sleep 3; S=$(curl -s $B/story-generator/job-status/$JOB | jget "str(d.get('status'))+' '+str(d.get('progress'))+' '+str(d.get('error') or '')[:120]"); echo "   $S"; case "$S" in completed*|failed*) break;; esac; done
  F=$(ls -t assets/generated/${EV}_story_*.mp4 2>/dev/null | head -1); [ -n "$F" ] && echo "   video: $(basename $F) $(ffprobe -v error -show_entries stream=width,height,duration,codec_name -of csv=p=0 "$F" 2>&1 | head -1)"
done
stop
