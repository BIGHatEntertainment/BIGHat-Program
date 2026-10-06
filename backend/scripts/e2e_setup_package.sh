#!/bin/bash
# alpha.85 real-app check: computer A publishes its setup, computer B pulls it. Uses the fake license/relay server as the "cloud".
# usage: e2e_setup_package.sh <portA>   (B uses portA+10, the cloud stand-in portA+5)
cd "$(dirname "$0")/.."
PA=$1; PB=$((PA+10)); PC=$((PA+5)); J='Content-Type: application/json'
export BIGHAT_LICENSE_API_BASE_URL=http://127.0.0.1:$PC
jq_() { python3 -c "import sys,json
try: d=json.load(sys.stdin)
except Exception: print('(no json)'); sys.exit()
print($1)" 2>/dev/null; }
mk() { local P=$1 D=/tmp/e2e_$1; rm -rf $D; mkdir -p $D/db $D/home/Documents; echo $D; }
DA=$(mk $PA); DB=$(mk $PB)
run() { local P=$1 D=/tmp/e2e_$1; (cd $PWD; HOME=$D/home BIGHAT_CONFIG_PATH=$D/system_config.json BIGHAT_DB_DIR=$D/db BIGHAT_DATA_DIR=$D/data BIGHAT_PORT=$P LOCALAPPDATA=$D/app timeout 280 python3 launcher.py >>$D/log.txt 2>&1 &); for i in $(seq 1 70); do curl -s localhost:$P/health >/dev/null 2>&1 && return; sleep 1; done; }
(timeout 280 python3 scripts/fake_setup_cloud.py $PC >/tmp/e2e_cloud_$PC.txt 2>&1 &); for i in $(seq 1 30); do curl -s localhost:$PC/__ping >/dev/null 2>&1 && break; sleep 1; done
run $PA; run $PB
setup() { curl -s -X POST -H "$J" -d "{\"license_key\":\"$2\",\"offline_mode\":true,\"master_admin\":{\"email\":\"$3\",\"password\":\"$4\",\"first_name\":\"$5\"},\"settings\":{\"location_name\":\"X\"}}" localhost:$1/api/native/setup/initialize >/dev/null; }
tok() { curl -s -X POST -H "$J" -d "{\"email\":\"$2\",\"password\":\"$3\"}" localhost:$1/api/auth/login | jq_ "d.get('token','')"; }
KEY=BHE-AAAA-BBBB-CCCC-DDDD
setup $PA $KEY owner@example.com 'OwnerA#pass1' Owen; setup $PB $KEY owner@example.com 'OwnerB#pass2' Owen
TA=$(tok $PA owner@example.com 'OwnerA#pass1'); TB=$(tok $PB owner@example.com 'OwnerB#pass2'); HA="Authorization: Bearer $TA"; HB="Authorization: Bearer $TB"
for P in $PA $PB; do curl -s -X POST -H "Authorization: Bearer $([ $P = $PA ] && echo $TA || echo $TB)" -H "$J" -d "{\"product_key\":\"$KEY\"}" localhost:$P/api/native/license/product-key >/dev/null; done
echo "== 0) tokens: A=${TA:0:5}.. B=${TB:0:5}.."
echo "== 1) seed computer A through the real API: 2 venues, pricing, an admin, 2 hosts, roles"
V1=$(curl -s -X POST -H "$HA" -H "$J" -d '{"name":"Monkey Pants","address":"1 Main St","city":"Phoenix","state":"AZ"}' localhost:$PA/api/venues | jq_ "d['id']")
V2=$(curl -s -X POST -H "$HA" -H "$J" -d '{"name":"Roses By The Stairs","address":"9 Oak Ave","city":"Tempe","state":"AZ","venue_pays_host_directly":true}' localhost:$PA/api/venues | jq_ "d['id']")
curl -s -X POST -H "$HA" -H "$J" -d "{\"venue_id\":\"$V1\",\"trivia_price\":125.5,\"music_bingo_price\":90,\"karaoke_price\":75}" localhost:$PA/api/venue_pricing >/dev/null
curl -s -X POST -H "$HA" -H "$J" -d "{\"venue_id\":\"$V2\",\"trivia_price\":100,\"music_bingo_price\":0,\"karaoke_price\":0}" localhost:$PA/api/venue_pricing >/dev/null
E1=$(curl -s -X POST -H "$HA" -H "$J" -d '{"name":"Alex Admin","email":"alex@example.com","phone":"555-0101","is_admin":true}' localhost:$PA/api/employees | jq_ "d.get('id') or d.get('employee',{}).get('id','')")
E2=$(curl -s -X POST -H "$HA" -H "$J" -d '{"name":"Sam Host","email":"sam@example.com","phone":"555-0102","is_admin":false}' localhost:$PA/api/employees | jq_ "d.get('id') or d.get('employee',{}).get('id','')")
curl -s -X POST -H "$HA" -H "$J" -d '{"name":"Pat Host","email":"Pat@Example.com","is_admin":false}' localhost:$PA/api/employees >/dev/null
EID2=$(curl -s -H "$HA" localhost:$PA/api/employees | jq_ "[e['id'] for e in d if e['email']=='sam@example.com'][0]")
R1=$(curl -s -X POST -H "$HA" -H "$J" -d "{\"venue_id\":\"$V1\",\"employee_id\":\"$EID2\",\"role_category\":\"trivia\",\"role_type\":\"primary\"}" localhost:$PA/api/venue-roles)
echo "   role created on A: $(echo "$R1" | jq_ "d.get('role_type') or d")"
EID3=$(curl -s -H "$HA" localhost:$PA/api/employees | jq_ "[e['id'] for e in d if e['email']=='pat@example.com'][0]")
curl -s -X POST -H "$HA" -H "$J" -d "{\"venue_id\":\"$V1\",\"employee_id\":\"$EID3\",\"role_category\":\"trivia\",\"role_type\":\"secondary\"}" localhost:$PA/api/venue-roles >/dev/null
LROOT="$DA/home/Documents/BIG Hat Entertainment/Files/Locations"; mkdir -p "$LROOT/monkey-pants/branding"; printf '\x89PNG-A-LOGO' > "$LROOT/monkey-pants/branding/logo.png"
# B already has an UNRELATED place that took the name "monkey-pants" (so B's Monkey Pants venue will get a different folder name)
curl -s -X POST -H "$HB" -H "$J" -d '{"name":"Monkey Pants"}' localhost:$PB/api/native/locations >/dev/null
echo "   A: venues=$(curl -s -H "$HA" localhost:$PA/api/venues | jq_ 'len(d)')  people=$(curl -s -H "$HA" localhost:$PA/api/employees | jq_ "sorted(e['email'] for e in d)")"
echo "== 2) A publishes the setup (master only)"
echo "   no login -> $(curl -s -o /dev/null -w '%{http_code}' -X POST localhost:$PA/api/native/setup-package/publish)"
echo "   master publish: $(curl -s -X POST -H "$HA" localhost:$PA/api/native/setup-package/publish | cut -c1-200)"
echo "== 3) B (a fresh install, same license email) checks the cloud and sees it differs"
echo "   $(curl -s -H "$HB" localhost:$PB/api/native/setup-package/check | cut -c1-300)"
B_BEFORE=$(curl -s -H "$HB" localhost:$PB/api/venues | jq_ 'len(d)')
B_PEOPLE_BEFORE=$(curl -s -H "$HB" localhost:$PB/api/employees | jq_ 'len(d)')
echo "== 4) B previews the pull (changes NOTHING)"
curl -s -X POST -H "$HB" "localhost:$PB/api/native/setup-package/pull?apply=false" | jq_ "{k:d['plan'][k] for k in ('venues_new','pricing_new','people_new','roles_new','images_new','differs')} if d.get('ok') else d"
echo "   B venues after preview: $(curl -s -H "$HB" localhost:$PB/api/venues | jq_ 'len(d)')   (was $B_BEFORE before the preview: unchanged = nothing written)"
echo "   B people after preview: $(curl -s -H "$HB" localhost:$PB/api/employees | jq_ 'len(d)') (was $B_PEOPLE_BEFORE)"
echo "== 5) B applies the pull"
curl -s -X POST -H "$HB" "localhost:$PB/api/native/setup-package/pull?apply=true" > $DB/apply.json; jq_ "{k:v for k,v in d['result'].items() if k!='people_added'} if d.get('ok') else d" < $DB/apply.json
echo "   people added (temp passwords shown once): $(jq_ "[(p['email'],p['role'],len(p['temp_password'])>=8) for p in d['result']['people_added']]" < $DB/apply.json)"
echo "== 6) B now matches A, by name and email (ids are different on each computer)"
echo "   B venues: $(curl -s -H "$HB" localhost:$PB/api/venues | jq_ "sorted((v['name'],v['city'],v.get('venue_pays_host_directly')) for v in d)")"
echo "   B pricing: $(curl -s -H "$HB" localhost:$PB/api/venue_pricing | jq_ "sorted((p.get('trivia_price'),p.get('music_bingo_price'),p.get('karaoke_price')) for p in d)")"
echo "   B people: $(curl -s -H "$HB" localhost:$PB/api/employees | jq_ "sorted((e['email'],e['is_admin']) for e in d)")"
echo "   B roles: $(curl -s -H "$HB" localhost:$PB/api/venue-roles | jq_ "[(r['role_category'],r['role_type']) for r in d]")"
echo "   image on disk, per folder: $(cd "/tmp/e2e_$PB/home/Documents/BIG Hat Entertainment/Files/Locations" 2>/dev/null && for d in */; do echo -n "${d%/}=$(ls "$d"branding 2>/dev/null | wc -l) "; done)"
echo "   no stray location (expect exactly 2 places, A has 2): count=$(curl -s -H "$HB" localhost:$PB/api/native/locations | jq_ 'len(d)')"
echo "   B locations (incl. image from A): $(curl -s -H "$HB" localhost:$PB/api/native/locations | jq_ "sorted((l['name'],len(l.get('branding_images') or [])) for l in d)")"
echo "== 7) PASSWORDS: B's master keeps its OWN password; new people log in with their temp password"
echo "   B master own password: $(curl -s -o /dev/null -w '%{http_code}' -X POST -H "$J" -d '{"email":"owner@example.com","password":"OwnerB#pass2"}' localhost:$PB/api/auth/login)   A's master password on B (must be 401): $(curl -s -o /dev/null -w '%{http_code}' -X POST -H "$J" -d '{"email":"owner@example.com","password":"OwnerA#pass1"}' localhost:$PB/api/auth/login)"
TP=$(jq_ "[p['temp_password'] for p in d['result']['people_added'] if p['email']=='sam@example.com'][0]" < $DB/apply.json); echo "   sam temp login: $(curl -s -o /dev/null -w '%{http_code}' -X POST -H "$J" -d "{\"email\":\"sam@example.com\",\"password\":\"$TP\"}" localhost:$PB/api/auth/login)"
echo "== 8) the package that left A contains no secrets (scan the real zip)"
curl -s -H "$HA" localhost:$PA/api/native/setup-package/export -o $DA/pkg.zip; python3 - $DA/pkg.zip <<'PY'
import sys, zipfile, json, re
z = zipfile.ZipFile(sys.argv[1]); names = z.namelist(); doc = json.loads(z.read("package.json"))
blob = z.read("package.json").decode().lower()
print("   files:", sorted(names))
print("   mentions password/hash/token/secret/key:", [w for w in ("password","hash","token","secret","api_key","license") if w in blob])
print("   A's password text anywhere:", any(b"OwnerA" in z.read(n) for n in names))
print("   roles:", doc["venue_roles"])
PY
echo "== 9) pulling again is safe (no duplicates) and B now reports it matches"
curl -s -X POST -H "$HB" "localhost:$PB/api/native/setup-package/pull?apply=true" | jq_ "{k:v for k,v in d['result'].items() if k!='people_added'}"
echo "   B counts: venues=$(curl -s -H "$HB" localhost:$PB/api/venues | jq_ 'len(d)') people=$(curl -s -H "$HB" localhost:$PB/api/employees | jq_ 'len(d)') roles=$(curl -s -H "$HB" localhost:$PB/api/venue-roles | jq_ 'len(d)')"
echo "   check: $(curl -s -H "$HB" localhost:$PB/api/native/setup-package/check | jq_ "{k:d.get(k) for k in ('exists','version','this_computer_version','differs')}")"
echo "== 9b) a plain HOST (not admin, not master) on B is refused everything"
curl -s -X POST -H "$J" -d "{\"email\":\"sam@example.com\",\"password\":\"$TP\"}" localhost:$PB/api/auth/login > $DB/host.json; HT=$(jq_ "d.get('token','')" < $DB/host.json); HH="Authorization: Bearer $HT"
echo "   host token obtained: $([ -n "$HT" ] && echo yes || echo NO)   role: $(jq_ "d.get('user',{}).get('role')" < $DB/host.json)"
for r in "GET check" "POST publish" "POST pull?apply=false" "GET export" "POST transfer/start"; do set -- $r; echo "   host $1 $2 -> $(curl -s -o /dev/null -w '%{http_code}' -X $1 -H "$HH" -H "$J" -d '{"to_email":"x@y.com"}' localhost:$PB/api/native/setup-package/$2)"; done
echo "   an ADMIN (alex) can check but not publish: check=$(curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $(curl -s -X POST -H "$J" -d "{\"email\":\"alex@example.com\",\"password\":\"$(jq_ "[p['temp_password'] for p in d['result']['people_added'] if p['email']=='alex@example.com'][0]" < $DB/apply.json)\"}" localhost:$PB/api/auth/login | jq_ "d.get('token','')")" localhost:$PB/api/native/setup-package/check)"
echo "== 10) a change on A is flagged on B"
curl -s -X PUT -H "$HA" -H "$J" -d '{"name":"Monkey Pants","address":"2 New St","city":"Phoenix","state":"AZ"}' localhost:$PA/api/venues/$V1 >/dev/null
curl -s -X POST -H "$HA" localhost:$PA/api/native/setup-package/publish | jq_ "('v%s' % d.get('version'))"
echo "   B check: $(curl -s -H "$HB" localhost:$PB/api/native/setup-package/check | jq_ "{k:d.get(k) for k in ('version','differs','note')}")"
echo "   B preview now: $(curl -s -X POST -H "$HB" "localhost:$PB/api/native/setup-package/pull?apply=false" | jq_ "{k:d['plan'][k] for k in ('venues_changed','differs')}")"
echo "   (existing venue address not overwritten unless the master says so) B address: $(curl -s -H "$HB" localhost:$PB/api/venues | jq_ "[v['address'] for v in d if v['name']=='Monkey Pants']")"
curl -s -X POST -H "$HB" "localhost:$PB/api/native/setup-package/pull?apply=true&overwrite_changed=true" >/dev/null; echo "   after master chooses 'update': $(curl -s -H "$HB" localhost:$PB/api/venues | jq_ "[v['address'] for v in d if v['name']=='Monkey Pants']")"
echo "== 11) FILE FALLBACK (option A): export from A, import into a clean third install"
echo "   $(curl -s -X POST -H "$HB" -F "file=@$DA/pkg.zip" "localhost:$PB/api/native/setup-package/import?apply=false" | jq_ "{k:d['plan'][k] for k in ('differs',)} if d.get('ok') else d")"
echo "   garbage file: $(curl -s -X POST -H "$HB" -F "file=@/etc/hostname" "localhost:$PB/api/native/setup-package/import?apply=true" | cut -c1-150)"
echo "== 12) CLOUD DOWN: pull fails with a plain message, nothing changes"
pkill -f fake_setup_cloud; sleep 1
echo "   $(curl -s -X POST -H "$HB" "localhost:$PB/api/native/setup-package/pull?apply=true" | cut -c1-230)"
echo "   check: $(curl -s -H "$HB" localhost:$PB/api/native/setup-package/check | cut -c1-200)"
echo "   B still has: venues=$(curl -s -H "$HB" localhost:$PB/api/venues | jq_ 'len(d)')"
pkill -f launcher.py; pkill -f fake_setup_cloud
