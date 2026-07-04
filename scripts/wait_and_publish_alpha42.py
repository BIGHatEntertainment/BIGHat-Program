#!/usr/bin/env python3
"""Wait for alpha.42 build → publish PUBLIC + LATEST."""
import json, time, sys, urllib.request, urllib.error
from pathlib import Path

PAT = Path("/root/.bighat/secrets/release_pat.txt").read_text().strip()
API = "https://api.github.com/repos/BIGHatEntertainment/BIGHat-Program"
HDR = {"Authorization": f"Bearer {PAT}", "Accept": "application/vnd.github+json", "User-Agent": "bighat"}
TAG = "v32.0.0-alpha.42"


def gh(method, path, body=None):
    url = path if path.startswith("http") else API + path
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, method=method, headers=HDR, data=data)
    if data: req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


print(f"→ Finding release.yml run for {TAG}…", flush=True)
run_id = None
for _ in range(30):
    _, res = gh("GET", "/actions/runs?event=push&per_page=10")
    for r in res.get("workflow_runs", []):
        if r.get("head_branch") == TAG:
            run_id = r["id"]
            print(f"  ✓ Found run #{run_id}: {r['html_url']}", flush=True)
            break
    if run_id: break
    time.sleep(10)
if not run_id:
    print("!! no run found"); sys.exit(1)

start = time.time()
while True:
    _, res = gh("GET", f"/actions/runs/{run_id}/jobs")
    win = next((j for j in res["jobs"] if "Windows" in j["name"]), None)
    mac = next((j for j in res["jobs"] if "Apple Silicon" in j["name"]), None)
    elapsed = int((time.time() - start) / 60)
    ws = f"{win['status']}/{win.get('conclusion') or '-'}" if win else "N/A"
    ms = f"{mac['status']}/{mac.get('conclusion') or '-'}" if mac else "N/A"
    print(f"[{elapsed}min] Windows={ws}  macOS_AS={ms}", flush=True)
    if (win and win["status"] == "completed") and (mac and mac["status"] == "completed"):
        break
    if elapsed > 80:
        print("!! timeout"); sys.exit(1)
    time.sleep(45)

_, releases = gh("GET", "/releases?per_page=5")
rel = next((r for r in releases if r["tag_name"] == TAG), None)
if not rel:
    print(f"!! no release found at {TAG}"); sys.exit(1)

names = [a["name"].lower() for a in rel["assets"]]
has_win = any("setup.exe" in n or n.endswith(".msi") for n in names)
has_arm = any("aarch64" in n and n.endswith(".dmg") for n in names)
if not (has_win and has_arm):
    print("!! Missing required binaries")
    sys.exit(1)

code, res = gh("PATCH", f"/releases/{rel['id']}", {
    "draft": False, "prerelease": False, "make_latest": "true", "name": TAG,
})
print(f"\nPATCH → {code}, draft={res.get('draft')}, prerelease={res.get('prerelease')}")
print(f"URL: {res.get('html_url')}")
_, latest = gh("GET", "/releases/latest")
print(f"✓ /releases/latest → {latest.get('tag_name')}")
for a in res.get("assets", []):
    print(f"  ✓ {a['name']} ({a['size']/1024/1024:.1f} MB)")
