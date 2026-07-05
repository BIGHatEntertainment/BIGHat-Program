#!/usr/bin/env python3
"""Push v32.0.0-alpha.45. Three-bug hotfix over alpha.44.

Pushes:
  • Version bumps (VERSION.txt, tauri.conf.json)
  • backend/routes/admin.py       — /admin/stats never 500s
  • backend/native/files_router.py — Trivia/Rounds folder allowed
  • backend/routes/bighat_files.py — 'trivia-presentation' alias
  • backend/tests/test_alpha45_regressions.py — 7 unit tests
  • frontend/yarn.lock            — includes @tauri-apps/plugin-dialog@2.7.1
  • memory/CHANGELOG.md           — alpha.45 entry

Then creates tag v32.0.0-alpha.45 which fires .github/workflows/release.yml.
"""
from __future__ import annotations
import base64, json, sys, time, urllib.request, urllib.error
from pathlib import Path

OWNER, REPO, BRANCH = "BIGHatEntertainment", "BIGHat-Program", "main"
TAG = "v32.0.0-alpha.45"
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
    ("/app/backend/VERSION.txt", "backend/VERSION.txt",
     "chore(release): bump -> 32.0.0-alpha.45"),
    ("/app/src-tauri/tauri.conf.json", "src-tauri/tauri.conf.json",
     "chore(release): bump tauri.conf.json -> 32.0.0-alpha.45"),
    ("/app/backend/routes/admin.py", "backend/routes/admin.py",
     "fix(alpha.45): /admin/stats never 500s (MontyDB coroutine + SQLite thread fallback)"),
    ("/app/backend/native/files_router.py", "backend/native/files_router.py",
     "fix(alpha.45): _resolve_folder accepts Trivia/Rounds for delete-card"),
    ("/app/backend/routes/bighat_files.py", "backend/routes/bighat_files.py",
     "fix(alpha.45): import_content accepts 'trivia-presentation' alias"),
    ("/app/backend/tests/test_alpha45_regressions.py",
     "backend/tests/test_alpha45_regressions.py",
     "test(alpha.45): 7 regression tests locking in the three hotfixes"),
    ("/app/frontend/yarn.lock", "frontend/yarn.lock",
     "chore(alpha.45): refresh yarn.lock — adds @tauri-apps/plugin-dialog@2.7.1"),
    ("/app/memory/CHANGELOG.md", "memory/CHANGELOG.md",
     "docs(alpha.45): changelog entry"),
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
    print(f"→ release.yml should fire shortly. Run wait_and_publish_alpha45.py next.", flush=True)


if __name__ == "__main__":
    main()
