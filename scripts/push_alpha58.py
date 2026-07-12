#!/usr/bin/env python3
"""Push v32.0.0-alpha.58. Pre-embedded seed rounds; MontyDB GridFS short-circuit; placeholder cleanup."""
from __future__ import annotations
import base64, json, time, urllib.request, urllib.error
from pathlib import Path

OWNER, REPO, BRANCH = "BIGHatEntertainment", "BIGHat-Program", "main"
TAG = "v32.0.0-alpha.58"
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
     "chore(alpha.58): sync yarn.lock (CI drift rule)"),
    ("/app/backend/VERSION.txt", "backend/VERSION.txt",
     "chore(release): bump -> 32.0.0-alpha.58"),
    ("/app/src-tauri/tauri.conf.json", "src-tauri/tauri.conf.json",
     "chore(release): bump tauri.conf.json -> 32.0.0-alpha.58"),
    ("/app/backend/routes/roundmaker.py", "backend/routes/roundmaker.py",
     "fix(alpha.58): _extract_gridfs_covers_to_disk short-circuits under "
     "standalone MontyDB ({'skipped': True, 'reason': "
     "'native_mode_no_gridfs'}) — no GridFS to read from natively"),
    ("/app/backend/launcher.py", "backend/launcher.py",
     "feat(alpha.58): first-boot _seed_bundled_rounds() copies bundled "
     "self-contained .bighat seeds into Documents/Files/Trivia — never "
     "overwrites user files (disk is truth)"),
    ("/app/backend/seed_rounds/MC/mc-01-a.bighat",
     "backend/seed_rounds/MC/mc-01-a.bighat",
     "feat(alpha.58): seed round MC_01_A with cover bytes embedded"),
    ("/app/backend/seed_rounds/REG/animals-1.bighat",
     "backend/seed_rounds/REG/animals-1.bighat",
     "feat(alpha.58): seed round Animals_1 with cover bytes embedded"),
    ("/app/scripts/build_installer.py", "scripts/build_installer.py",
     "feat(alpha.58): payload seed_rounds/ self-containment verification "
     "(build fails if a seed lacks cover_image_data_url)"),
    ("/app/scripts/build_sidecar.py", "scripts/build_sidecar.py",
     "feat(alpha.58): bundle seed_rounds/ into the PyInstaller sidecar"),
    ("/app/backend/tests/test_alpha58_seed_rounds_and_gridfs.py",
     "backend/tests/test_alpha58_seed_rounds_and_gridfs.py",
     "test(alpha.58): MontyDB short-circuit + seed self-containment + "
     "no-overwrite seeding"),
    ("/app/memory/CHANGELOG.md", "memory/CHANGELOG.md",
     "docs(alpha.58): changelog entry"),
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
