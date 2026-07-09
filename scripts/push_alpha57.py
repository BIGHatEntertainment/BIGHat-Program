#!/usr/bin/env python3
"""Push v32.0.0-alpha.57. One build = one presentation; backend log visibility; widened cover recovery."""
from __future__ import annotations
import base64, json, time, urllib.request, urllib.error
from pathlib import Path

OWNER, REPO, BRANCH = "BIGHatEntertainment", "BIGHat-Program", "main"
TAG = "v32.0.0-alpha.57"
PAT = Path("/root/.bighat/secrets/release_pat.txt").read_text().strip()
API = f"https://api.github.com/repos/{OWNER}/{REPO}"
HDR = {"Authorization": f"Bearer {PAT}", "Accept": "application/vnd.github+json",
       "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "bighat"}


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
            last_err = e; time.sleep(4)
    print(f"!! gh {method} {path}: {last_err}", flush=True)
    return 0, {}


def put_file(local, remote, msg):
    b64 = base64.b64encode(Path(local).read_bytes()).decode()
    body = {"message": msg, "content": b64, "branch": BRANCH}
    code, existing = gh("GET", f"/contents/{remote}?ref={BRANCH}")
    if code == 200: body["sha"] = existing["sha"]
    code, res = gh("PUT", f"/contents/{remote}", body)
    assert code in (200, 201), f"{remote}: {code} {res}"
    print(f"  ✓ {remote}: {res['commit']['sha'][:7]}")


FILES = [
    ("/app/frontend/yarn.lock", "frontend/yarn.lock",
     "chore(alpha.57): sync yarn.lock (CI drift rule)"),
    ("/app/backend/VERSION.txt", "backend/VERSION.txt",
     "chore(release): bump -> 32.0.0-alpha.57"),
    ("/app/src-tauri/tauri.conf.json", "src-tauri/tauri.conf.json",
     "chore(release): bump tauri.conf.json -> 32.0.0-alpha.57"),
    ("/app/frontend/src/pages/Dashboard.js",
     "frontend/src/pages/Dashboard.js",
     "fix(alpha.57): skip legacy import-trivia when the hardcoded build "
     "succeeded — one build = ONE presentation, no more duplicates"),
    ("/app/frontend/src/components/trivia/SlotMachineRandomizer.jsx",
     "frontend/src/components/trivia/SlotMachineRandomizer.jsx",
     "fix(alpha.57): same duplicate-skip for roulette + ACL-safe confirm"),
    ("/app/backend/routes/trivia_viewer.py", "backend/routes/trivia_viewer.py",
     "fix(alpha.57): Presenter cards understand schema-v2 build docs "
     "(created_at/host_name/location_name/roundFiles) — no more "
     "'0 ROUNDS / Unknown / Invalid Date'"),
    ("/app/backend/native_slides.py", "backend/native_slides.py",
     "feat(alpha.57): title-card resolution diagnostics mirrored into the "
     "merchant debug log (cover-resolved / cover-MISS with searched dirs / "
     "per-round title-card outcome); recovery sweep widened to the docs "
     "tree + whole assets root (60k-file cap)"),
    ("/app/backend/routes/debug_log.py", "backend/routes/debug_log.py",
     "feat(alpha.57): debug export now appends backend.log tails"),
    ("/app/backend/launcher.py", "backend/launcher.py",
     "feat(alpha.57): mirror backend logging to Files/Logs/backend.log "
     "(rotating 2MBx2) on the user PC"),
    ("/app/backend/routes/roundmaker.py", "backend/routes/roundmaker.py",
     "feat(alpha.57): boot cover-backfill stats mirrored into debug log"),
    ("/app/memory/CHANGELOG.md", "memory/CHANGELOG.md",
     "docs(alpha.57): changelog entry"),
]


def main():
    print(f"→ Pushing {len(FILES)} files for {TAG}", flush=True)
    for local, remote, msg in FILES:
        put_file(local, remote, msg)
    _, ref = gh("GET", f"/git/ref/heads/{BRANCH}")
    head_sha = ref["object"]["sha"]
    print(f"→ HEAD: {head_sha[:7]}", flush=True)
    code, _ = gh("GET", f"/git/ref/tags/{TAG}")
    if code == 200:
        print(f"  ↺ deleting existing tag {TAG}", flush=True)
        gh("DELETE", f"/git/refs/tags/{TAG}"); time.sleep(2)
    code, res = gh("POST", "/git/refs", {"ref": f"refs/tags/{TAG}", "sha": head_sha})
    assert code in (200, 201), f"tag: {code} {res}"
    print(f"✓ Tag {TAG} → {head_sha[:7]}", flush=True)


if __name__ == "__main__":
    main()
