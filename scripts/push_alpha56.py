#!/usr/bin/env python3
"""Push v32.0.0-alpha.56. Real-machine fixes: host resolution unblocks 17-step build; path-key round trust; cover self-heal + boot backfill; Tauri dialog ACL."""
from __future__ import annotations
import base64, json, time, urllib.request, urllib.error
from pathlib import Path

OWNER, REPO, BRANCH = "BIGHatEntertainment", "BIGHat-Program", "main"
TAG = "v32.0.0-alpha.56"
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
     "chore(alpha.56): sync yarn.lock (CI drift rule)"),
    ("/app/backend/VERSION.txt", "backend/VERSION.txt",
     "chore(release): bump -> 32.0.0-alpha.56"),
    ("/app/src-tauri/tauri.conf.json", "src-tauri/tauri.conf.json",
     "chore(release): bump tauri.conf.json -> 32.0.0-alpha.56"),
    ("/app/backend/presentation_builder.py", "backend/presentation_builder.py",
     "fix(alpha.56): _load_host scans Files/Hosts/*/host.json by id OR "
     "email and falls back to config users — host folders are email-slug "
     "named, the wizard passes a UUID; this 400'd the 17-step build on "
     "every real install"),
    ("/app/backend/native/router.py", "backend/native/router.py",
     "fix(alpha.56): _ensure_host_on_disk materializes host.json from "
     "db.users before /presentations/build + /presentations/roulette"),
    ("/app/backend/native_slides.py", "backend/native_slides.py",
     "fix(alpha.56): honor round_ref['path'] (absolute) so the exact "
     "wizard-picked .bighat beats stale duplicates; SELF-HEAL inlined "
     "covers back into the .bighat at read time"),
    ("/app/backend/routes/roundmaker.py", "backend/routes/roundmaker.py",
     "fix(alpha.56): boot migration backfill_round_covers() embeds "
     "cover_image_data_url into every disk round that only has "
     "cover_image_id"),
    ("/app/backend/server.py", "backend/server.py",
     "chore(alpha.56): run round-cover backfill on boot"),
    ("/app/frontend/src/components/trivia/TriviaBuilderWizard.jsx",
     "frontend/src/components/trivia/TriviaBuilderWizard.jsx",
     "fix(alpha.56): normalize window.confirm (bool/Promise/ACL "
     "rejection) — Tauri routed it to the dialog plugin and denied it, "
     "silently forcing the legacy build path"),
    ("/app/src-tauri/capabilities/default.json",
     "src-tauri/capabilities/default.json",
     "fix(alpha.56): allow dialog confirm/ask/message via ACL"),
    ("/app/backend/tests/test_alpha56_real_machine_fixes.py",
     "backend/tests/test_alpha56_real_machine_fixes.py",
     "test(alpha.56): 5 tests locking in host lookup, path-key trust, "
     "self-heal + boot backfill"),
    ("/app/memory/CHANGELOG.md", "memory/CHANGELOG.md",
     "docs(alpha.56): changelog entry"),
    ("/app/memory/PRD.md", "memory/PRD.md",
     "docs(alpha.56): codify RUNS-ON-USER-PC principle"),
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
