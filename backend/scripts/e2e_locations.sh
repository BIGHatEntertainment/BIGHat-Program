#!/bin/bash
# Real-app check: do locations + images survive losing the app database? Usage: e2e_locations.sh <port> <label> [wipe-db|wipe-docs|none]
cd "$(dirname "$0")/.."
PORT=$1; LABEL=$2; MODE=${3:-wipe-db}; D=/tmp/e2e_$PORT; rm -rf $D; mkdir -p $D/db $D/docs
export BIGHAT_CONFIG_PATH=$D/system_config.json BIGHAT_DB_DIR=$D/db BIGHAT_DATA_DIR=$D/data BIGHAT_FILES_DIR=$D/docs BIGHAT_PORT=$PORT LOCALAPPDATA=$D/app BIGHAT_KARAOKE_DIR=$D/k BIGHAT_KARAOKE_SETTINGS=$D/ks.json
B=localhost:$PORT/api; J='Content-Type: application/json'
start() { (timeout 200 python3 launcher.py >$D/log.txt 2>&1 &); for i in $(seq 1 70); do curl -s localhost:$PORT/health >/dev/null 2>&1 && return; sleep 1; done; }
stop() { pkill -f launcher.py; sleep 2; }
jq_() { python3 -c "import sys,json;d=json.load(sys.stdin);$1" 2>/dev/null; }
python3 -c "
from PIL import Image
Image.new('RGB',(800,600),(200,30,30)).save('$D/a.png'); Image.new('RGB',(800,600),(30,30,200)).save('$D/b.png'); Image.new('RGB',(1920,1080),(30,200,30)).save('$D/ov.png')"
start
curl -s -X POST -H "$J" -d '{"license_key":"BHE-TEST-AAAA-BBBB-CCCC","offline_mode":true,"master_admin":{"email":"owner@example.com","password":"OwnerPass1!","first_name":"Owner"},"settings":{"location_name":"Test Pub"}}' $B/native/setup/initialize >/dev/null
TOKEN=$(curl -s -X POST -H "$J" -d '{"email":"owner@example.com","password":"OwnerPass1!"}' $B/auth/login | jq_ "print(d.get('access_token') or d.get('token') or '')"); A="Authorization: Bearer $TOKEN"
LID=$(curl -s -X POST -H "$J" -H "$A" -d '{"name":"The Rusty Nail"}' $B/native/locations | jq_ "print(d['id'])")
curl -s -X POST -H "$A" -F "file=@$D/a.png" $B/native/locations/$LID/images >/dev/null; curl -s -X POST -H "$A" -F "file=@$D/b.png" $B/native/locations/$LID/images >/dev/null
curl -s -X POST -H "$A" -F "file=@$D/ov.png" $B/native/locations/$LID/overlays >/dev/null
summary() { curl -s -H "$A" $B/native/locations | jq_ "print([(l['name'],len(l.get('branding_images',[])),len(l.get('overlay_images',[]))) for l in d])"; }
echo "[$LABEL] saved:           $(summary)   (name, branding images, overlays)"
echo "[$LABEL] folder on disk:  $(ls $D/docs/Files/Locations/ 2>/dev/null | tr '\n' ' ') | files: $(find $D/docs/Files/Locations -type f 2>/dev/null | wc -l)"
stop
case $MODE in
  wipe-db) rm -rf $D/db/*; echo "[$LABEL] >>> app database DELETED (like a reset / reinstall; Documents folder kept)";;
  wipe-docs) rm -rf $D/docs/Files/Locations; echo "[$LABEL] >>> Documents/Files/Locations DELETED";;
esac
start
TOKEN=$(curl -s -X POST -H "$J" -d '{"email":"owner@example.com","password":"OwnerPass1!"}' $B/auth/login | jq_ "print(d.get('access_token') or d.get('token') or '')"); A="Authorization: Bearer $TOKEN"
echo "[$LABEL] after restart:   $(summary)"
NID=$(curl -s -H "$A" $B/native/locations | jq_ "print(d[0]['id'] if d else '')")
[ -n "$NID" ] && echo "[$LABEL] first image still loads: $(curl -s -o /dev/null -w '%{http_code} %{size_download}B' -H "$A" $B/native/locations/$NID/images/$(curl -s -H "$A" $B/native/locations | jq_ "print(d[0]['branding_images'][0]['id'])")/raw)"
stop
