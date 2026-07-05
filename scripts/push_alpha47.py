#!/usr/bin/env python3
"""Push v32.0.0-alpha.47. Audience View mirror for the bar TVs.

Pushes:
  • Version bumps (VERSION.txt, tauri.conf.json)
  • frontend/src/pages/trivia/TriviaAudienceView.jsx   — NEW route
  • frontend/src/App.js                                — route registered
  • frontend/src/components/trivia/editor/PresentationMode.jsx
        — BroadcastChannel + Tauri WebviewWindow (654 lines of inline
          document.write blob DELETED)
  • backend/tests/test_alpha47_audience_view.py        — 10 regression tests
  • memory/CHANGELOG.md                                — alpha.47 entry

Creates tag v32.0.0-alpha.47 which fires .github/workflows/release.yml.
"""
from __future__ import annotations
import base64, json, sys, time, urllib.request, urllib.error
from pathlib import Path

OWNER, REPO, BRANCH = "BIGHatEntertainment", "BIGHat-Program", "main"
TAG = "v32.0.0-alpha.47"
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
     "chore(release): bump -> 32.0.0-alpha.47"),
    ("/app/src-tauri/tauri.conf.json", "src-tauri/tauri.conf.json",
     "chore(release): bump tauri.conf.json -> 32.0.0-alpha.47"),
    ("/app/frontend/src/pages/trivia/TriviaAudienceView.jsx",
     "frontend/src/pages/trivia/TriviaAudienceView.jsx",
     "feat(alpha.47): TriviaAudienceView — fixed 1920x1080 stage, BroadcastChannel, zero host chrome"),
    ("/app/frontend/src/App.js", "frontend/src/App.js",
     "feat(alpha.47): register /trivia/audience route"),
    ("/app/frontend/src/components/trivia/editor/PresentationMode.jsx",
     "frontend/src/components/trivia/editor/PresentationMode.jsx",
     "feat(alpha.47): host uses BroadcastChannel + Tauri WebviewWindow; 654 lines of inline audience-HTML blob removed"),
    ("/app/backend/tests/test_alpha47_audience_view.py",
     "backend/tests/test_alpha47_audience_view.py",
     "test(alpha.47): 10 regression tests for audience view wiring"),
    ("/app/memory/CHANGELOG.md", "memory/CHANGELOG.md",
     "docs(alpha.47): changelog entry"),
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
