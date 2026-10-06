#!/bin/bash
# alpha.86 real-app check: the Schedule's venues are the source of truth; a venue is on for a game only when that game's price is above $0.
# usage: e2e_price_rule.sh <port>
cd "$(dirname "$0")/.."
PORT=$1; D=/tmp/e2e_$PORT; rm -rf $D; mkdir -p $D/db "$D/home/Documents/BIG Hat Entertainment/Files/Locations/monkey-pants-bar-grill/branding" "$D/home/Documents/BIG Hat Entertainment/Files/Story/Bingo" "$D/home/Documents/BIG Hat Entertainment/Files/Story/Karaoke"
LR="$D/home/Documents/BIG Hat Entertainment/Files/Locations"; printf 'PNG' > "$LR/monkey-pants-bar-grill/branding/a.png"
export HOME=$D/home BIGHAT_CONFIG_PATH=$D/system_config.json BIGHAT_DB_DIR=$D/db BIGHAT_DATA_DIR=$D/data BIGHAT_PORT=$PORT LOCALAPPDATA=$D/app
B=localhost:$PORT/api; J='Content-Type: application/json'
jq_() { python3 -c "import sys,json
try: d=json.load(sys.stdin)
except Exception: print('(no json)'); sys.exit()
print($1)" 2>/dev/null; }
start() { (timeout 280 python3 launcher.py >>$D/log.txt 2>&1 &); for i in $(seq 1 70); do curl -s localhost:$PORT/health >/dev/null 2>&1 && return; sleep 1; done; }
start
curl -s -X POST -H "$J" -d '{"license_key":"BHE-TEST-AAAA-BBBB-CCCC","offline_mode":true,"master_admin":{"email":"o@x.com","password":"OwnerPass1!","first_name":"O"},"settings":{"location_name":"Test"}}' $B/native/setup/initialize >/dev/null
T=$(curl -s -X POST -H "$J" -d '{"email":"o@x.com","password":"OwnerPass1!"}' $B/auth/login | jq_ "d.get('token','')"); H="Authorization: Bearer $T"
names() { jq_ "sorted(x['name'] for x in (d if isinstance(d,list) else d.get('locations',[])))"; }
screens() {
  echo "     Schedule venues        : $(curl -s -H "$H" $B/venues | names)"
  echo "     Trivia Setup  (trivia) : $(curl -s -H "$H" "$B/native/locations?game=trivia" | names)"
  echo "     Build wizard           : $(curl -s -H "$H" $B/trivia/locations | jq_ "sorted(x['name'] for x in (d if isinstance(d,list) else d.get('locations',[])))")"
  echo "     Karaoke Setup/player   : $(curl -s -H "$H" "$B/native/locations?game=karaoke" | names)"
  echo "     Bingo (bingo)          : $(curl -s -H "$H" "$B/native/locations?game=bingo" | names)"
  echo "     Story Bingo dropdown   : $(curl -s $B/story-generator/event-assets/bingo | names)"
  echo "     Story Karaoke dropdown : $(curl -s $B/story-generator/event-assets/karaoke | names)"
}
price() { curl -s -X POST -H "$H" -H "$J" -d "{\"venue_id\":\"$1\",\"trivia_price\":$2,\"music_bingo_price\":$3,\"karaoke_price\":$4}" $B/venue_pricing >/dev/null; }
echo "== 1) YOUR SCREENSHOT: a place exists only as a folder on disk. Open a list: it must now be a Schedule venue (no restart)"
curl -s -H "$H" $B/native/locations >/dev/null
echo "   Schedule venues: $(curl -s -H "$H" $B/venues | names)"
V1=$(curl -s -H "$H" $B/venues | jq_ "[v['id'] for v in d if v['name']=='Monkey Pants Bar Grill' or 'Monkey' in v['name']][0]"); echo "   venue id found: $([ -n "$V1" ] && [ "$V1" != "(no json)" ] && echo yes || echo NO)"
echo "== 2) no prices set yet: it is a venue, but on for NO game"; screens
echo "== 3) trivia price only (\$100)"; price $V1 100 0 0; screens
echo "== 4) bingo price only (\$90)"; price $V1 0 90 0; screens
echo "== 5) karaoke price only (\$75)"; price $V1 0 0 75; screens
echo "== 6) all three"; price $V1 100 90 75; screens
echo "== 7) a SECOND venue added in the Schedule with only a karaoke price: found everywhere karaoke is used, nowhere else"
V2=$(curl -s -X POST -H "$H" -H "$J" -d '{"name":"Roses By The Stairs","address":"9 Oak","city":"Tempe","state":"AZ"}' $B/venues | jq_ "d['id']"); price $V2 0 0 60; screens
echo "== 8) price set back to \$0 hides it again (and a tiny price counts: \$0.01)"; price $V2 0 0 0; echo "   karaoke: $(curl -s -H "$H" "$B/native/locations?game=karaoke" | names)"; price $V2 0 0 0.01; echo "   karaoke at \$0.01: $(curl -s -H "$H" "$B/native/locations?game=karaoke" | names)"
echo "== 9) the Story picture stays attached, and an earlier-uploaded picture for a \$0 venue is NOT offered"
printf 'GIF89a' > "$D/home/Documents/BIG Hat Entertainment/Files/Story/Karaoke/Old Closed Bar.png"
echo "   Story Karaoke (picture for a place that is not a venue): $(curl -s $B/story-generator/event-assets/karaoke | names)"
echo "== 10) RESTART: nothing changes, nothing duplicates"; pkill -f launcher.py; sleep 2; start
T=$(curl -s -X POST -H "$J" -d '{"email":"o@x.com","password":"OwnerPass1!"}' $B/auth/login | jq_ "d.get('token','')"); H="Authorization: Bearer $T"
echo "   venues: $(curl -s -H "$H" $B/venues | names)   locations(all): $(curl -s -H "$H" $B/native/locations | names)"
echo "== 11) bad game name is refused; the wizard never lists a deleted venue"
echo "   game=nope -> $(curl -s -o /dev/null -w '%{http_code}' -H "$H" "$B/native/locations?game=nope")"
curl -s -X DELETE -H "$H" $B/venues/$V2 >/dev/null; echo "   after deleting Roses: wizard=$(curl -s -H "$H" $B/trivia/locations | jq_ "sorted(x['name'] for x in (d if isinstance(d,list) else d.get('locations',[])))")  karaoke=$(curl -s -H "$H" "$B/native/locations?game=karaoke" | names)"
pkill -f launcher.py
