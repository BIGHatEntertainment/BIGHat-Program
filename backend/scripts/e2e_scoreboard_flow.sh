#!/bin/bash
# Real-app check of the whole scoreboard flow:
#  Save & Exit (3-4) -> Fetch list (5-6) -> pick a night (7) -> video (10) -> download + QR (11), then restart and Fetch again.
# Usage: e2e_scoreboard_flow.sh <port> [licensed]     (licensed = write an active subscription into the test PC's config)
cd "$(dirname "$0")/.."
PORT=$1; LIC=$2; D=/tmp/e2e_sb_$PORT; rm -rf $D; mkdir -p $D/home/Documents
export HOME=$D/home BIGHAT_PORT=$PORT
unset BIGHAT_DB_DIR BIGHAT_DATA_DIR BIGHAT_FILES_DIR LOCALAPPDATA BIGHAT_BACKUPS_DIR
U=$D/home/.local/share/BIGHat/data; mkdir -p $U
export BIGHAT_CONFIG_PATH=$U/system_config.json BIGHAT_DATA_ROOT=$U/app
if [ "$LIC" = "licensed" ]; then python3 - <<'P'
import json, os
from datetime import datetime, timedelta, timezone
p = os.environ["BIGHAT_CONFIG_PATH"]
exp = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
json.dump({"subscription": {"active": True, "tier": "pro", "expires_at": exp, "story_generator_enabled": True,
                            "last_cloud_validated_at": datetime.now(timezone.utc).isoformat()}}, open(p, "w"))
P
fi
start() { (timeout 280 python3 launcher.py >$D/log.txt 2>&1 &); for i in $(seq 1 70); do curl -s localhost:$PORT/health >/dev/null 2>&1 && return; sleep 1; done; echo "backend did not start"; tail -20 $D/log.txt; exit 1; }
stop() { pkill -f launcher.py; sleep 2; }
J='-H content-type:application/json'; S="localhost:$PORT/api"
list() { python3 -c "import sys,json;d=json.load(sys.stdin);print(d['count'],'readable,',d.get('unreadable',0),'unreadable ->',[(f['venue'],f['data']['date'] if f['data'] else None,len(f['data']['teams']) if f['data'] else 0) for f in d['files']])"; }
start
echo "== 3-4 Save & Exit (what the final slide posts)"
for v in "Test Venue|10/20/2026" "Test Venue|10/27/2026" "Cornish Pasty Co. (Glendale)|10/21/2026"; do
  L=${v%%|*}; T=${v##*|}
  curl -s -X POST $S/scores/save $J -d "{\"locationName\":\"$L\",\"presentationName\":\"$L - $T\",\"presentationDate\":\"$T\",\"presentationId\":\"p-$RANDOM\",\"teams\":[{\"name\":\"Team A\",\"swag\":\"\",\"roundScores\":[5,6],\"total\":11},{\"name\":\"Team B\",\"swag\":\"\",\"roundScores\":[3,4],\"total\":7}],\"rounds\":[{\"label\":\"R1\",\"multiplier\":1},{\"label\":\"R2\",\"multiplier\":1}]}" > /dev/null
done
echo "   files on disk: $(cd "$D/home/Documents/BIG Hat Entertainment/Files" && find . -name '*.json' | wc -l)"
# a damaged file must be REPORTED, not hide the rest
echo '{ broken' > "$D/home/Documents/BIG Hat Entertainment/Files/Trivia/Scores/Test_Venue/broken.json"
echo "== 5-6 Fetch (ONE GET)"
echo "   $(curl -s $S/scoreboard/scores/local | list)"
echo "== 7 venue lookup by the NAME a host sees (spaces, dots, brackets)"
for v in "Test%20Venue" "Cornish%20Pasty%20Co.%20(Glendale)" "Test_Venue" "Co."; do echo "   '$v' -> $(curl -s "$S/scoreboard/scores/$v" | python3 -c "import sys,json;print(json.load(sys.stdin)['count'],'files')")"; done
echo "== 10 video"
R=$(curl -s -m 120 -w '|%{http_code}' -X POST $S/scoreboard/generate-video $J -d '{"teams":[{"name":"Team A","total":11,"rank":1,"roundScores":[5,6]},{"name":"Team B","total":7,"rank":2,"roundScores":[3,4]}],"location":"Test Venue","date":"10/20/2026","rounds":[],"aspectRatio":"landscape","duration":3}')
echo "   ${R:0:200}"
URL=$(echo "${R%|*}" | python3 -c "import sys,json;print(json.load(sys.stdin).get('url',''))" 2>/dev/null); FID=$(echo "${R%|*}" | python3 -c "import sys,json;print(json.load(sys.stdin).get('file_id',''))" 2>/dev/null)
if [ -n "$URL" ]; then
  echo "== 11 download: $(curl -s -o $D/out.mp4 -w '%{http_code} %{size_download} bytes %{content_type}' localhost:$PORT$URL); ffprobe: $(ffprobe -v error -show_entries stream=codec_name,width,height -of csv=p=0 $D/out.mp4 2>&1 | head -1)"
  echo "   QR publish: $(curl -s -m 30 -X POST $S/scoreboard/exports/$FID/qr-publish | cut -c1-160)"
fi
echo "== restart, Fetch again"; stop; start; echo "   $(curl -s $S/scoreboard/scores/local | list)"
stop
