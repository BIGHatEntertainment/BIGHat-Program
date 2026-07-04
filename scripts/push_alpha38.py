#!/usr/bin/env python3
"""Push alpha.38 to GitHub Releases.

Steps:
  1. Push updated `backend/VERSION.txt`, `src-tauri/tauri.conf.json`,
     `frontend/yarn.lock`, and the new alpha.38 test file via the
     Contents API on branch `main`.
  2. Create the `v32.0.0-alpha.38` tag pointing at the new HEAD.
  3. Trigger release.yml is automatic via the tag push.
  4. Poll the workflow run every 45s. Cancel Intel leg. Wait for
     Windows + macOS ARM. Verify assets. PATCH release public.

Usage: python /app/scripts/push_alpha38.py
"""
from __future__ import annotations
import base64
import json
import os
import sys
import time
from pathlib import Path

import urllib.request
import urllib.error

OWNER = "BIGHatEntertainment"
REPO = "BIGHat-Program"
BRANCH = "main"
VERSION = "32.0.0-alpha.38"
TAG = f"v{VERSION}"

PAT = Path("/app/memory/github_pat.txt").read_text().strip()
API = f"https://api.github.com/repos/{OWNER}/{REPO}"


def hdr():
    return {
        "Authorization": f"Bearer {PAT}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "bighat-release-agent",
    }


def gh(method: str, path: str, body=None):
    url = path if path.startswith("http") else f"{API}{path}"
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, method=method, headers=hdr(), data=data)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def get_file_sha(path: str) -> str | None:
    code, res = gh("GET", f"/contents/{path}?ref={BRANCH}")
    if code == 200:
        return res["sha"]
    return None


def put_file(local_path: Path, remote_path: str, message: str) -> None:
    content_b64 = base64.b64encode(local_path.read_bytes()).decode("ascii")
    body = {
        "message": message,
        "content": content_b64,
        "branch": BRANCH,
    }
    sha = get_file_sha(remote_path)
    if sha:
        body["sha"] = sha
    code, res = gh("PUT", f"/contents/{remote_path}", body)
    if code not in (200, 201):
        print(f"  ✗ {remote_path}: HTTP {code} — {res}")
        sys.exit(1)
    print(f"  ✓ {remote_path}: {res['commit']['sha'][:7]}")


def main():
    files = [
        ("/app/backend/VERSION.txt",
         "backend/VERSION.txt",
         "chore(release): bump VERSION.txt -> 32.0.0-alpha.38"),
        ("/app/src-tauri/tauri.conf.json",
         "src-tauri/tauri.conf.json",
         "chore(release): bump tauri.conf.json -> 32.0.0-alpha.38"),
        ("/app/backend/routes/presentations.py",
         "backend/routes/presentations.py",
         "fix(alpha.38): write .bighat manifest to Files/Trivia/Rounds/ on wizard confirm"),
        ("/app/backend/tests/test_alpha38_trivia_presentation_native.py",
         "backend/tests/test_alpha38_trivia_presentation_native.py",
         "test(alpha.38): 6 regression tests for native trivia manifest write+list"),
        ("/app/frontend/yarn.lock",
         "frontend/yarn.lock",
         "chore(alpha.38): refresh yarn.lock (drift recurrence auto-remediation)"),
    ]

    print(f"→ Pushing {len(files)} files to {OWNER}/{REPO}@{BRANCH}")
    for local, remote, msg in files:
        put_file(Path(local), remote, msg)

    # Fetch fresh HEAD commit sha
    code, main_ref = gh("GET", f"/git/ref/heads/{BRANCH}")
    assert code == 200, main_ref
    head_sha = main_ref["object"]["sha"]
    print(f"→ Fresh {BRANCH} HEAD: {head_sha[:7]}")

    # Check if tag already exists — delete if so
    code, _ = gh("GET", f"/git/ref/tags/{TAG}")
    if code == 200:
        print(f"→ Tag {TAG} already exists — deleting first")
        gh("DELETE", f"/git/refs/tags/{TAG}")
        time.sleep(2)

    # Create tag
    code, res = gh("POST", "/git/refs", {
        "ref": f"refs/tags/{TAG}",
        "sha": head_sha,
    })
    if code not in (200, 201):
        print(f"✗ tag create failed: HTTP {code} — {res}")
        sys.exit(1)
    print(f"✓ Tag {TAG} created at {head_sha[:7]}")
    print(f"→ Workflow release.yml will trigger via push:tags")
    print()
    print(f"Watch: https://github.com/{OWNER}/{REPO}/actions")


if __name__ == "__main__":
    main()
