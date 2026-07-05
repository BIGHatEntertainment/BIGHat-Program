#!/usr/bin/env python3
"""Wait for alpha.48 build → auto-cancel the Intel leg → publish PUBLIC + LATEST."""
import json, time, sys, urllib.request, urllib.error
from pathlib import Path

PAT = Path("/root/.bighat/secrets/release_pat.txt").read_text().strip()
API = "https://api.github.com/repos/BIGHatEntertainment/BIGHat-Program"
HDR = {"Authorization": f"Bearer {PAT}", "Accept": "application/vnd.github+json",
       "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "bighat"}
TAG = "v32.0.0-alpha.48"


def gh(method, path, body=None, retries=3):
    url = path if path.startswith("http") else API + path
    data = json.dumps(body).encode() if body else None
    last_err = None
    for _ in range(retries):
        req = urllib.request.Request(url, method=method, headers=HDR, data=data)
        if data: req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=25) as r:
                return r.status, json.loads(r.read() or b"null")
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")
        except (urllib.error.URLError, TimeoutError) as e:
            last_err = e; time.sleep(5)
    print(f"!! gh {method} {path}: {last_err}", flush=True)
    return 0, {}


print(f"→ Finding release.yml run for {TAG}…", flush=True)
run_id = None
for _ in range(30):
    _, res = gh("GET", "/actions/runs?event=push&per_page=10")
    for r in (res or {}).get("workflow_runs", []):
        if r.get("head_branch") == TAG:
            run_id = r["id"]
            print(f"  ✓ Found run #{run_id}", flush=True)
            break
    if run_id: break
    time.sleep(10)
if not run_id:
    print("!! no run found"); sys.exit(1)

# Auto-cancel the macOS Intel leg once — we ship arm64 only.
# NOTE (alpha.48 lesson learned): we DO NOT fall back to /runs/{id}/cancel
# if the job-level cancel returns non-2xx — that kills the whole run.
# If the job-level cancel fails, we just let Intel run/fail on its own
# (Windows + macOS_AS are what gate the publish).
intel_cancelled = False
start = time.time()
while True:
    _, res = gh("GET", f"/actions/runs/{run_id}/jobs")
    if not res:
        time.sleep(30); continue
    win = next((j for j in res["jobs"] if "Windows" in j["name"]), None)
    mac_as = next((j for j in res["jobs"] if "Apple Silicon" in j["name"]), None)
    mac_intel = next((j for j in res["jobs"]
                      if "Intel" in j["name"] or "x86_64-apple" in j["name"]), None)

    # Best-effort cancel of the Intel leg only. Never touch the run.
    if not intel_cancelled and mac_intel and mac_intel["status"] in ("queued", "in_progress"):
        code, _ = gh("POST", f"/actions/jobs/{mac_intel['id']}/cancel")
        intel_cancelled = True
        if code in (200, 202):
            print(f"  ↺ auto-cancelled macOS Intel leg (job #{mac_intel['id']})", flush=True)
        else:
            print(f"  ⚠ job-cancel returned {code}; letting Intel run naturally", flush=True)

    elapsed = int((time.time() - start) / 60)
    ws = f"{win['status']}/{win.get('conclusion') or '-'}" if win else "N/A"
    ms = f"{mac_as['status']}/{mac_as.get('conclusion') or '-'}" if mac_as else "N/A"
    ins = f"{mac_intel['status']}/{mac_intel.get('conclusion') or '-'}" if mac_intel else "N/A"
    print(f"[{elapsed}min] Windows={ws}  macOS_AS={ms}  macOS_Intel={ins}", flush=True)

    win_done = win and win["status"] == "completed"
    mac_done = mac_as and mac_as["status"] == "completed"
    if win_done and mac_done:
        # Fail fast if either critical leg blew up
        if win.get("conclusion") not in ("success",):
            print(f"!! Windows leg conclusion={win.get('conclusion')}"); sys.exit(2)
        if mac_as.get("conclusion") not in ("success",):
            print(f"!! macOS_AS leg conclusion={mac_as.get('conclusion')}"); sys.exit(2)
        break

    if elapsed > 80:
        print("!! timeout"); sys.exit(1)
    time.sleep(45)

_, releases = gh("GET", "/releases?per_page=5")
rel = next((r for r in releases if r["tag_name"] == TAG), None)
if not rel:
    print(f"!! no release found at {TAG}"); sys.exit(1)

code, res = gh("PATCH", f"/releases/{rel['id']}", {
    "draft": False, "prerelease": False, "make_latest": "true", "name": TAG,
})
print(f"\nPATCH → {code}, draft={res.get('draft')}, prerelease={res.get('prerelease')}")
print(f"URL: {res.get('html_url')}")
_, latest = gh("GET", "/releases/latest")
print(f"✓ /releases/latest → {latest.get('tag_name')}")
for a in res.get("assets", []):
    print(f"  ✓ {a['name']} ({a['size']/1024/1024:.1f} MB)")
