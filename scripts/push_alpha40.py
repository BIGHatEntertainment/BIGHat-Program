#!/usr/bin/env python3
"""Push + publish v32.0.0-alpha.40.

Locked-in policy (per merchant 2026-07-04):
  * Every release ships as PUBLIC (draft=false, prerelease=false).
  * Every release is marked LATEST (`make_latest=true`).
"""
from __future__ import annotations
import base64, json, sys, time, urllib.request, urllib.error
from pathlib import Path

OWNER, REPO, BRANCH = "BIGHatEntertainment", "BIGHat-Program", "main"
VERSION = "32.0.0-alpha.40"
TAG = f"v{VERSION}"
PAT = Path("/root/.bighat/secrets/release_pat.txt").read_text().strip()
API = f"https://api.github.com/repos/{OWNER}/{REPO}"
HDR = {
    "Authorization": f"Bearer {PAT}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "bighat-release-agent",
}


def gh(method, path, body=None):
    url = path if path.startswith("http") else API + path
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, method=method, headers=HDR, data=data)
    if data: req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


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
     "chore(release): bump -> 32.0.0-alpha.40"),
    ("/app/src-tauri/tauri.conf.json", "src-tauri/tauri.conf.json",
     "chore(release): bump tauri.conf.json -> 32.0.0-alpha.40"),
    ("/app/backend/routes/roundmaker.py", "backend/routes/roundmaker.py",
     "feat(alpha.40): Round Maker writes .bighat to Files/Trivia/<TYPE>/ + migration"),
    ("/app/backend/routes/trivia_viewer.py", "backend/routes/trivia_viewer.py",
     "feat(alpha.40): native slide-assembly endpoint (host→location→rounds→final)"),
    ("/app/backend/server.py", "backend/server.py",
     "feat(alpha.40): boot-time DB↔disk rounds migration"),
    ("/app/backend/tests/test_alpha37_presentation_and_files_tabs.py",
     "backend/tests/test_alpha37_presentation_and_files_tabs.py",
     "test(alpha.40): pin docs root in alpha.37 e2e test for hermetic runs"),
    ("/app/backend/tests/test_alpha40_disk_rounds_and_slides.py",
     "backend/tests/test_alpha40_disk_rounds_and_slides.py",
     "test(alpha.40): 16 regression tests for disk-first rounds + slide assembly"),
    ("/app/frontend/src/App.js", "frontend/src/App.js",
     "feat(alpha.40): add /trivia/play route"),
    ("/app/frontend/src/pages/trivia/TriviaPlay.jsx",
     "frontend/src/pages/trivia/TriviaPlay.jsx",
     "feat(alpha.40): native full-screen slide runner"),
    ("/app/frontend/src/pages/trivia/TriviaPresenterView.jsx",
     "frontend/src/pages/trivia/TriviaPresenterView.jsx",
     "feat(alpha.40): wire Play Now button to native TriviaPlay view"),
    ("/app/frontend/yarn.lock", "frontend/yarn.lock",
     "chore(alpha.40): refresh yarn.lock"),
    ("/app/.gitignore", ".gitignore",
     "chore(alpha.40): ignore secrets/PAT files"),
]


def main():
    print(f"→ Pushing {len(FILES)} files")
    for local, remote, msg in FILES:
        put_file(local, remote, msg)

    _, ref = gh("GET", f"/git/ref/heads/{BRANCH}")
    head_sha = ref["object"]["sha"]
    print(f"→ HEAD: {head_sha[:7]}")

    code, _ = gh("GET", f"/git/ref/tags/{TAG}")
    if code == 200:
        print(f"→ deleting existing tag {TAG}")
        gh("DELETE", f"/git/refs/tags/{TAG}")
        time.sleep(2)

    code, res = gh("POST", "/git/refs", {"ref": f"refs/tags/{TAG}", "sha": head_sha})
    assert code in (200, 201), f"tag: {code} {res}"
    print(f"✓ Tag {TAG} → {head_sha[:7]}")
    print(f"Watch: https://github.com/{OWNER}/{REPO}/actions")


if __name__ == "__main__":
    main()
