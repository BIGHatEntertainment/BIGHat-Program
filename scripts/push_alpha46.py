#!/usr/bin/env python3
"""Push v32.0.0-alpha.46. DISK IS TRUTH — native slide rendering.

Pushes:
  • Version bumps (VERSION.txt, tauri.conf.json)
  • backend/native_slides.py          — NEW module, 415 lines
  • backend/routes/slide_fetcher.py   — native render before SharePoint
  • backend/routes/presentations.py   — disk-fallback in get_presentation
  • backend/routes/trivia_viewer.py   — never 500s + disk-only fallback
  • backend/tests/test_alpha46_...py  — 12 regression tests
  • frontend/yarn.lock                — refreshed lockfile
  • memory/PRD.md                     — new DISK-TRUTH section (rule #1)
  • memory/CHANGELOG.md               — alpha.46 entry

Creates tag v32.0.0-alpha.46 which fires .github/workflows/release.yml.
"""
from __future__ import annotations
import base64, json, sys, time, urllib.request, urllib.error
from pathlib import Path

OWNER, REPO, BRANCH = "BIGHatEntertainment", "BIGHat-Program", "main"
TAG = "v32.0.0-alpha.46"
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
     "chore(release): bump -> 32.0.0-alpha.46"),
    ("/app/src-tauri/tauri.conf.json", "src-tauri/tauri.conf.json",
     "chore(release): bump tauri.conf.json -> 32.0.0-alpha.46"),
    ("/app/backend/native_slides.py", "backend/native_slides.py",
     "feat(alpha.46): native disk-based slide renderer (Editor-compatible output)"),
    ("/app/backend/routes/slide_fetcher.py", "backend/routes/slide_fetcher.py",
     "fix(alpha.46): fetch_section renders from .bighat before SharePoint; store-all accepts empty body; disk-fallback on sections-list"),
    ("/app/backend/routes/presentations.py", "backend/routes/presentations.py",
     "fix(alpha.46): /presentations/{id} scans Files/Trivia/Rounds/*.bighat before 404 (presentations survive app restart)"),
    ("/app/backend/routes/trivia_viewer.py", "backend/routes/trivia_viewer.py",
     "fix(alpha.46): /trivia-viewer/list never 500s (disk-only fallback for MontyDB thread errors)"),
    ("/app/backend/tests/test_alpha46_disk_truth_and_native_slides.py",
     "backend/tests/test_alpha46_disk_truth_and_native_slides.py",
     "test(alpha.46): 12 regression tests inc. e2e presentation-survives-restart"),
    ("/app/frontend/yarn.lock", "frontend/yarn.lock",
     "chore(alpha.46): refresh yarn.lock"),
    ("/app/memory/PRD.md", "memory/PRD.md",
     "docs(alpha.46): commit DISK-IS-TRUTH as PRD rule #1"),
    ("/app/memory/CHANGELOG.md", "memory/CHANGELOG.md",
     "docs(alpha.46): changelog entry"),
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
