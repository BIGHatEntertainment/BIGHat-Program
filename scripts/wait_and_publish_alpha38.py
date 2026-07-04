#!/usr/bin/env python3
"""Poll Windows leg every 45s. When complete → verify assets and publish."""
import json, time, sys, urllib.request
from pathlib import Path

PAT = Path("/app/memory/github_pat.txt").read_text().strip()
RUN = 28693635681
API = "https://api.github.com/repos/BIGHatEntertainment/BIGHat-Program"
HDR = {"Authorization": f"Bearer {PAT}", "Accept": "application/vnd.github+json", "User-Agent": "bighat"}
TAG = "v32.0.0-alpha.38"


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


start = time.time()
while True:
    _, res = gh("GET", f"/actions/runs/{RUN}/jobs")
    win = next((j for j in res["jobs"] if "Windows" in j["name"]), None)
    mac = next((j for j in res["jobs"] if "Apple Silicon" in j["name"]), None)
    elapsed = int((time.time() - start) / 60)
    print(f"[{elapsed}min] Windows={win['status']}/{win.get('conclusion')}  macOS_AS={mac['status']}/{mac.get('conclusion')}", flush=True)
    if win["status"] == "completed":
        break
    if elapsed > 80:
        print("!! timeout")
        sys.exit(1)
    time.sleep(45)

print("→ Windows leg done. Fetching release…", flush=True)
_, rel = gh("GET", f"/releases/tags/{TAG}")
if not rel or "id" not in rel:
    print(f"!! no release found at {TAG}: {rel}")
    sys.exit(1)

print(f"Release {rel['id']} — {len(rel['assets'])} assets:")
for a in rel["assets"]:
    size_mb = a["size"] / (1024 * 1024)
    print(f"  - {a['name']}  ({size_mb:.1f} MB)")

names = [a["name"].lower() for a in rel["assets"]]
has_win = any(("setup.exe" in n or n.endswith(".msi")) for n in names)
has_arm = any(("aarch64" in n) and n.endswith(".dmg") for n in names)
print(f"has_win={has_win}, has_arm={has_arm}")

if has_win and has_arm:
    # Publish
    code, res = gh("PATCH", f"/releases/{rel['id']}", {
        "draft": False, "prerelease": True, "make_latest": "true",
    })
    print(f"PATCH → {code} — draft={res.get('draft')}, url={res.get('html_url')}")
else:
    print("!! Missing required binaries — release stays in DRAFT")
    sys.exit(1)
