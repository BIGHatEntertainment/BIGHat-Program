#!/usr/bin/env python3
"""Push v32.0.0-alpha.59. Host/location sections for build docs; generator cover library; per-round overlay assignment."""
from __future__ import annotations
import base64, json, time, urllib.request, urllib.error
from pathlib import Path

OWNER, REPO, BRANCH = "BIGHatEntertainment", "BIGHat-Program", "main"
TAG = "v32.0.0-alpha.59"
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
     "chore(alpha.59): sync yarn.lock (CI drift rule)"),
    ("/app/backend/VERSION.txt", "backend/VERSION.txt",
     "chore(release): bump -> 32.0.0-alpha.59"),
    ("/app/src-tauri/tauri.conf.json", "src-tauri/tauri.conf.json",
     "chore(release): bump tauri.conf.json -> 32.0.0-alpha.59"),
    ("/app/backend/routes/slide_fetcher.py", "backend/routes/slide_fetcher.py",
     "fix(alpha.59): _normalize_v2_pres — schema-v2 build docs were "
     "silently DROPPING the host and location sections (host_name/host_id "
     "vs host/hostName key mismatch)"),
    ("/app/backend/native_slides.py", "backend/native_slides.py",
     "fix(alpha.59): load_host_asset matches host folders by "
     "host_id/email/display_name/id via host.json scan"),
    ("/app/backend/launcher.py", "backend/launcher.py",
     "feat(alpha.59): _seed_bundled_covers copies the generator cover "
     "library into the persistent uploads dir on boot (never overwrites)"),
    ("/app/scripts/build_sidecar.py", "scripts/build_sidecar.py",
     "feat(alpha.59): bundle seed_covers/ into the PyInstaller sidecar"),
    ("/app/frontend/src/pages/admin/TriviaSetup.jsx",
     "frontend/src/pages/admin/TriviaSetup.jsx",
     "feat(alpha.59): per-overlay round assignment chips (MC/REG/MISC/MYS/"
     "BIG) in Admin Trivia Setup"),
    ("/app/frontend/src/lib/api.js", "frontend/src/lib/api.js",
     "feat(alpha.59): tagLocationOverlay API helper"),
    ("/app/backend/tests/test_alpha59_host_sections_and_seed_covers.py",
     "backend/tests/test_alpha59_host_sections_and_seed_covers.py",
     "test(alpha.59): v2 normalization, host asset scan, cover seeding"),
    ("/app/backend/seed_covers/1960s.jpg", "backend/seed_covers/1960s.jpg",
     "feat(alpha.59): bundled cover artwork from the round generator tool"),
    ("/app/backend/seed_covers/1970s.jpg", "backend/seed_covers/1970s.jpg",
     "feat(alpha.59): bundled cover artwork from the round generator tool"),
    ("/app/backend/seed_covers/1980s.jpg", "backend/seed_covers/1980s.jpg",
     "feat(alpha.59): bundled cover artwork from the round generator tool"),
    ("/app/backend/seed_covers/Music.jpg", "backend/seed_covers/Music.jpg",
     "feat(alpha.59): bundled cover artwork from the round generator tool"),
    ("/app/backend/seed_covers/Sports.jpg", "backend/seed_covers/Sports.jpg",
     "feat(alpha.59): bundled cover artwork from the round generator tool"),
    ("/app/backend/seed_covers/mc_title.jpg", "backend/seed_covers/mc_title.jpg",
     "feat(alpha.59): bundled cover artwork from the round generator tool"),
    ("/app/backend/seed_covers/times_up.gif", "backend/seed_covers/times_up.gif",
     "feat(alpha.59): bundled cover artwork from the round generator tool"),
    ("/app/memory/CHANGELOG.md", "memory/CHANGELOG.md",
     "docs(alpha.59): changelog entry"),
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
