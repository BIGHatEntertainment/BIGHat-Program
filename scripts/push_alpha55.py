#!/usr/bin/env python3
"""Push v32.0.0-alpha.55. Persistent title cards (real root cause) + verbatim v30 audience view."""
from __future__ import annotations
import base64, json, time, urllib.request, urllib.error
from pathlib import Path

OWNER, REPO, BRANCH = "BIGHatEntertainment", "BIGHat-Program", "main"
TAG = "v32.0.0-alpha.55"
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
     "chore(alpha.55): sync yarn.lock (CI drift rule)"),
    ("/app/backend/VERSION.txt", "backend/VERSION.txt",
     "chore(release): bump -> 32.0.0-alpha.55"),
    ("/app/src-tauri/tauri.conf.json", "src-tauri/tauri.conf.json",
     "chore(release): bump tauri.conf.json -> 32.0.0-alpha.55"),
    ("/app/backend/launcher.py", "backend/launcher.py",
     "fix(alpha.55): pin BIGHAT_ROUNDMAKER_UPLOADS/GENERATED to the "
     "persistent per-user data dir in frozen builds — cover images no "
     "longer evaporate with the _MEI temp dir on app close"),
    ("/app/backend/routes/roundmaker.py", "backend/routes/roundmaker.py",
     "fix(alpha.55): env-driven UPLOAD_DIR/GENERATED_DIR + embed "
     "cover_image_data_url inside every .bighat so round files are "
     "self-contained (disk is the absolute source of truth)"),
    ("/app/backend/native_slides.py", "backend/native_slides.py",
     "fix(alpha.55): recover evaporated title cards for ALL round types "
     "via stem match in the local assets 04_TitleCards tree; ZIP "
     ".bighat cover_image_id fallback"),
    ("/app/frontend/src/pages/trivia/TriviaAudienceView.jsx",
     "frontend/src/pages/trivia/TriviaAudienceView.jsx",
     "fix(alpha.55): audience view is now a VERBATIM v30 prototype port "
     "— font multipliers (MC +10%, REG/MISC/MYS +15%, answers +10%), "
     "clamp() vw font scaling, Y-sorted visibility answer reveal, "
     "prototype final-scores credit scroll, audience video audio ON"),
    ("/app/backend/tests/test_alpha55_title_card_persistence.py",
     "backend/tests/test_alpha55_title_card_persistence.py",
     "test(alpha.55): 12 tests — persistent uploads env, TitleCards "
     "recovery for all 5 round types, .bighat cover embedding, "
     "legacy-JSON + ZIP end-to-end slide 0"),
    ("/app/memory/CHANGELOG.md", "memory/CHANGELOG.md",
     "docs(alpha.55): changelog entry"),
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
