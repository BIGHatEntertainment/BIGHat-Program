#!/usr/bin/env python3
"""Push + publish v32.0.0-alpha.41. Public + latest + not-prerelease."""
from __future__ import annotations
import base64, json, sys, time, urllib.request, urllib.error
from pathlib import Path

OWNER, REPO, BRANCH = "BIGHatEntertainment", "BIGHat-Program", "main"
VERSION = "32.0.0-alpha.41"
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
     "chore(release): bump -> 32.0.0-alpha.41"),
    ("/app/src-tauri/tauri.conf.json", "src-tauri/tauri.conf.json",
     "chore(release): bump tauri.conf.json -> 32.0.0-alpha.41"),
    ("/app/backend/routes/trivia_viewer.py", "backend/routes/trivia_viewer.py",
     "fix(alpha.41): inline docs-root resolver (frozen-build safe) + BIG round slides + tiebreaker + debug endpoint"),
    ("/app/backend/routes/roundmaker.py", "backend/routes/roundmaker.py",
     "fix(alpha.41): list_rounds dedupes by (type, slug) — hides draft when generated exists"),
    ("/app/backend/routes/bighat_files.py", "backend/routes/bighat_files.py",
     "feat(alpha.41): Import accepts plain JSON .bighat (wizard-generated), not just ZIP"),
    ("/app/frontend/src/pages/trivia/TriviaPlay.jsx",
     "frontend/src/pages/trivia/TriviaPlay.jsx",
     "feat(alpha.41): BIG question / BIG answers / tiebreaker slide renderers"),
    ("/app/backend/tests/test_alpha39_trivia_viewer_disk_scan.py",
     "backend/tests/test_alpha39_trivia_viewer_disk_scan.py",
     "test(alpha.41): update assertion for inline docs_root resolver"),
    ("/app/backend/tests/test_alpha40_disk_rounds_and_slides.py",
     "backend/tests/test_alpha40_disk_rounds_and_slides.py",
     "test(alpha.41): update slide-assembly assertions for BIG round changes"),
    ("/app/backend/tests/test_alpha41_dedup_bigrounds_and_debug.py",
     "backend/tests/test_alpha41_dedup_bigrounds_and_debug.py",
     "test(alpha.41): 12 regression tests — dedup, BIG splits, tiebreaker, debug endpoint"),
    ("/app/frontend/yarn.lock", "frontend/yarn.lock",
     "chore(alpha.41): refresh yarn.lock"),
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
