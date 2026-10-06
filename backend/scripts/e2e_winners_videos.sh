#!/bin/bash
# alpha.87 real-app check: winners section slides + the 3 videos through the live server.
# usage: e2e_winners_videos.sh <port>
cd "$(dirname "$0")/.."
PORT=$1; D=/tmp/e2e_$PORT; rm -rf $D; mkdir -p $D/db $D/home/Documents $D/data $D/app
export HOME=$D/home BIGHAT_CONFIG_PATH=$D/system_config.json BIGHAT_DB_DIR=$D/db BIGHAT_DATA_DIR=$D/data BIGHAT_PORT=$PORT LOCALAPPDATA=$D/app
B=localhost:$PORT/api; J='Content-Type: application/json'
(timeout 200 python3 launcher.py >>$D/log.txt 2>&1 &); for i in $(seq 1 70); do curl -s localhost:$PORT/health >/dev/null 2>&1 && break; sleep 1; done
curl -s -X POST -H "$J" -d '{"license_key":"BHE-TEST-AAAA-BBBB-CCCC","offline_mode":true,"master_admin":{"email":"o@x.com","password":"OwnerPass1!","first_name":"O","last_name":"W"},"settings":{"location_name":"Test"}}' $B/native/setup/initialize >/dev/null
T=$(curl -s -X POST -H "$J" -d '{"email":"o@x.com","password":"OwnerPass1!"}' $B/auth/login | python3 -c "import sys,json;print(json.load(sys.stdin).get('token',''))"); H="Authorization: Bearer $T"
PID=e2e-winners-1
RD="$D/home/Documents/BIG Hat Entertainment/Files/Trivia/Rounds"; mkdir -p "$RD"
printf '{"schema":"bighat-presentation/v1","id":"%s","name":"E2E Trivia","createdBy":"o@x.com","roundFiles":[],"slides":[]}' $PID > "$RD/e2e-trivia.bighat"
echo "presentation id: ${PID:0:8}..."
echo "== the winners section, as the editor requests it"
curl -s -X POST -H "$H" -H "$J" -d '{}' $B/slide-fetcher/fetch-section/$PID/winners > $D/sec.json
head -c 200 $D/sec.json; echo
python3 - "$D/sec.json" <<'PY'
import sys,json
d=json.load(open(sys.argv[1])); print('status',d.get('status'),'slides',d.get('slidesCount'))
for s in d.get('slides',[]):
    m=s['metadata']; print('  slide',m.get('slideIndexInRound'),'place',m.get('place'),[(e['type'],e.get('videoSrc') or '', e.get('loop')) for e in s['elements'] if e['type']!='image'])
PY
echo "== the videos, with NO login (a <video> tag sends none), as the audience window asks"
for w in 1st 2nd 3rd; do
  echo "  $w full : $(curl -s -o /dev/null -w '%{http_code} %{content_type} %{size_download}B' $B/native/winners-video/$w)"
  echo "  $w range: $(curl -s -o /dev/null -w '%{http_code} %{size_download}B' -H 'Range: bytes=0-1023' $B/native/winners-video/$w)"
done
echo "  bad name : $(curl -s -o /dev/null -w '%{http_code}' $B/native/winners-video/4th)"
echo "  frozen-exe lookup path: $(python3 -c "
import sys; sys.path.insert(0,'.')
from native_slides import bundled_asset_path as b
print([bool(b('assets','slides','winners',f'place_{w}.mp4')) for w in ('1st','2nd','3rd')])")"
pkill -f launcher.py
