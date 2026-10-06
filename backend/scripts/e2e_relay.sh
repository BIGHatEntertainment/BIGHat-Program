#!/bin/bash
# alpha.82 real-app check: Karaoke phone requests + Story/Scoreboard QR downloads through the cloud relay.  Usage: e2e_relay.sh <port>
cd "$(dirname "$0")/.."
PORT=$1; RP=$((PORT+1)); D=/tmp/e2e_$PORT; rm -rf $D; mkdir -p $D/db $D/home/Documents
export HOME=$D/home BIGHAT_CONFIG_PATH=$D/system_config.json BIGHAT_DB_DIR=$D/db BIGHAT_DATA_DIR=$D/data BIGHAT_PORT=$PORT LOCALAPPDATA=$D/app
export BIGHAT_LICENSE_API_BASE_URL=http://127.0.0.1:$RP
B=localhost:$PORT/api; R=127.0.0.1:$RP; J='Content-Type: application/json'
jq_() { python3 -c "import sys,json
try: d=json.load(sys.stdin)
except Exception: print('(no json)'); sys.exit()
print($1)" 2>/dev/null; }
startrelay() { (timeout 280 python3 scripts/fake_relay_server.py $RP >$D/relay.txt 2>&1 &); for i in $(seq 1 30); do curl -s $R/d/x >/dev/null 2>&1 && return; sleep 1; done; }
startapp() { (timeout 280 python3 launcher.py >>$D/log.txt 2>&1 &); for i in $(seq 1 70); do curl -s localhost:$PORT/health >/dev/null 2>&1 && return; sleep 1; done; }
startrelay; startapp
curl -s -X POST -H "$J" -d '{"license_key":"BHE-AAAA-BBBB-CCCC-DDDD","offline_mode":true,"master_admin":{"email":"owner@example.com","password":"OwnerPass1!","first_name":"Owner"},"settings":{"location_name":"Test Pub"}}' $B/native/setup/initialize >/dev/null
TOKEN=$(curl -s -X POST -H "$J" -d '{"email":"owner@example.com","password":"OwnerPass1!"}' $B/auth/login | jq_ "d.get('token','')"); H="Authorization: Bearer $TOKEN"
curl -s -X POST -H "$H" -H "$J" -d '{"product_key":"BHE-AAAA-BBBB-CCCC-DDDD"}' $B/native/license/product-key >/dev/null
echo "== 0) before any night: QR link is the PC's own address (phone can NOT open it)"
echo "   $(curl -s $B/karaoke/request-info)"
echo "== 1) host starts a Karaoke night"
echo "   $(curl -s -X POST -H "$J" -d '{"location":"Monkey Pants","qr_enabled":true}' $B/karaoke/session/create | jq_ "('qr=%s' % d.get('qr'))" | cut -c1-200)"
INFO=$(curl -s $B/karaoke/request-info); URL=$(echo "$INFO" | jq_ "d['url']")
echo "   request-info: $INFO"
echo "== 2) the 'phone' opens the QR link (no login) and gets the request page"
curl -s -o $D/page.html -w '   page http %{http_code}\n' "$URL"; echo "   page has form: $(grep -c 'Request this song' $D/page.html)   venue shown: $(grep -c 'Monkey Pants' $D/page.html)"
SID=$(echo "$URL" | sed 's#.*/k/##')
echo "== 3) phone sends a request (in a messy way) -> the PC's list gets it within a few seconds"
RESP=$(curl -s -X POST -H "$J" -d '{"singer_name":"  Sam  ","song_title":"<b>Africa</b>","song_artist":"Toto"}' $R/api/relay/karaoke/$SID/request); echo "   phone got: $RESP"; RID=$(echo "$RESP" | jq_ "d.get('request_id','')")
sleep 6
echo "   PC requests: $(curl -s $B/karaoke/requests/pending | jq_ "[(x['singer_name'],x['song_title'],x['status'],x.get('source')) for x in (d if isinstance(d,list) else d.get('requests',[]))]")"
echo "== 4) a second poll does not duplicate it"; sleep 7; echo "   count: $(curl -s $B/karaoke/requests/pending | jq_ "len(d if isinstance(d,list) else d.get('requests',[]))")"
LOCALID=$(curl -s $B/karaoke/requests/pending | jq_ "(d if isinstance(d,list) else d.get('requests',[]))[0]['id']")
echo "== 5) phone status before the host answers: $(curl -s $R/api/relay/karaoke/$SID/status/$RID)"
echo "== 6) host ACCEPTS -> the phone is told"; curl -s -X POST $B/karaoke/requests/$LOCALID/accept | cut -c1-90; echo; sleep 7
echo "   phone status: $(curl -s $R/api/relay/karaoke/$SID/status/$RID)"
echo "== 7) a second song, host REJECTS"
RESP2=$(curl -s -X POST -H "$J" -H "X-Forwarded-For: 9.9.9.9" -d '{"singer_name":"Kim","song_title":"Cats in the Cradle"}' $R/api/relay/karaoke/$SID/request); RID2=$(echo "$RESP2" | jq_ "d.get('request_id','')"); sleep 7
L2=$(curl -s $B/karaoke/requests/pending | jq_ "[x['id'] for x in (d if isinstance(d,list) else d.get('requests',[])) if x['singer_name']=='Kim'][0]"); curl -s -X POST $B/karaoke/requests/$L2/reject >/dev/null; sleep 7
echo "   phone status: $(curl -s $R/api/relay/karaoke/$SID/status/$RID2)"
echo "== 8) INTERNET DROPS (relay stopped) for a while, then returns -> request sent meanwhile is NOT lost"
pkill -f fake_relay_server; sleep 2
echo "   app still answers while offline: $(curl -s -o /dev/null -w '%{http_code}' $B/karaoke/requests/pending)   request-info: $(curl -s $B/karaoke/request-info | cut -c1-140)"
sleep 8
startrelay
echo "   (relay restarted: it forgot the night, as if it had been redeployed) PC re-opens one by itself:"; sleep 26
INFO2=$(curl -s $B/karaoke/request-info); echo "   request-info: $INFO2"
URL2=$(echo "$INFO2" | jq_ "d['url']"); echo "   new link works for a phone: $(curl -s -o /dev/null -w '%{http_code}' "$URL2")"
echo "== 9) host ends the night -> the QR page closes"
curl -s -X POST $B/karaoke/session/end >/dev/null; sleep 2; echo "   old link: $(curl -s -o /dev/null -w '%{http_code}' "$URL2")   request-info now: $(curl -s $B/karaoke/request-info | cut -c1-110)"
echo "== 10) STORY QR: store a video on the PC, publish it, a phone downloads it"
head -c 200000 /dev/urandom > $D/v.bin; python3 - <<PY
import base64,json;open("$D/store.json","w").write(json.dumps({"video_data":"data:video/mp4;base64,"+base64.b64encode(open("$D/v.bin","rb").read()).decode(),"filename":"qr_test"}))
PY
SR=$(curl -s -X POST -H "$J" --data @$D/store.json $B/story-generator/store-temp); FID=$(echo "$SR" | jq_ "d['file_id']"); echo "   stored: $(echo $SR | cut -c1-90)"
PUB=$(curl -s -X POST $B/story-generator/qr-publish/$FID); echo "   publish: $(echo $PUB | cut -c1-170)"; LINK=$(echo "$PUB" | jq_ "d.get('url','')")
curl -s -o $D/dl.bin -w '   phone download http %{http_code}, type %{content_type}\n' "$LINK"; echo "   bytes identical: $(cmp -s $D/v.bin $D/dl.bin && echo yes || echo NO)"
echo "== 11) SCOREBOARD QR: an exported PNG -> published -> phone downloads"
python3 -c "
import struct,zlib
def png(w,h):
    raw=b''.join(b'\x00'+bytes([40,80,200])*w for _ in range(h))
    def ch(t,d): c=struct.pack('>I',len(d))+t+d; return c+struct.pack('>I',zlib.crc32(t+d)&0xffffffff)
    return b'\x89PNG\r\n\x1a\n'+ch(b'IHDR',struct.pack('>IIBBBBB',w,h,8,2,0,0,0))+ch(b'IDAT',zlib.compress(raw))+ch(b'IEND',b'')
open('$D/s.png','wb').write(png(64,64))"
UP=$(curl -s -X POST -F "file=@$D/s.png;filename=score.png" $B/scoreboard/exports/upload); EID=$(echo "$UP" | jq_ "d['file_id']"); echo "   exported: $(echo $UP | cut -c1-100)"
PUB2=$(curl -s -X POST $B/scoreboard/exports/$EID/qr-publish); LINK2=$(echo "$PUB2" | jq_ "d.get('url','')"); echo "   publish: $(echo $PUB2 | cut -c1-150)"
curl -s -o $D/dl.png -w '   phone download http %{http_code}, type %{content_type}\n' "$LINK2"; echo "   bytes identical: $(cmp -s $D/s.png $D/dl.png && echo yes || echo NO)"
echo "== 12) safety: path tricks and unknown ids are refused"
echo "   story bad id: $(curl -s -o /dev/null -w '%{http_code}' -X POST "$B/story-generator/qr-publish/..%2F..%2Fetc%2Fpasswd")   missing: $(curl -s -o /dev/null -w '%{http_code}' -X POST $B/story-generator/qr-publish/doesnotexist123)"
echo "   scoreboard dotdot: $(curl -s -o /dev/null -w '%{http_code}' -X POST "$B/scoreboard/exports/..%2Fsystem_config.json/qr-publish")   missing: $(curl -s -o /dev/null -w '%{http_code}' -X POST $B/scoreboard/exports/nothere.png/qr-publish)"
echo "== 13) links EXPIRE: expire everything on the relay, the phone link dies"
curl -s -X POST $R/__expire_files >/dev/null; echo "   story link now: $(curl -s -o /dev/null -w '%{http_code}' "$LINK")   scoreboard link now: $(curl -s -o /dev/null -w '%{http_code}' "$LINK2")"
echo "== 14) OFFLINE publish gives a plain message, nothing crashes"
pkill -f fake_relay_server; sleep 2
echo "   $(curl -s -X POST $B/story-generator/qr-publish/$FID | cut -c1-200)"; echo "   $(curl -s -X POST $B/scoreboard/exports/$EID/qr-publish | cut -c1-200)"
echo "== 15) REVOKED license cannot use the relay"
startrelay; curl -s -X POST $R/__revoke >/dev/null
echo "   $(curl -s -X POST $B/scoreboard/exports/$EID/qr-publish | cut -c1-200)"
pkill -f launcher.py; pkill -f fake_relay_server
