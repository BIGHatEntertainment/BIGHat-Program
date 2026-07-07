#!/usr/bin/env python3
"""Push v32.0.0-alpha.53. HARDCODED 17-step build pipeline: Wizard,
Roulette, Intros library, overlay round-type tagging."""
from __future__ import annotations
import base64, json, time, urllib.request, urllib.error
from pathlib import Path

OWNER, REPO, BRANCH = "BIGHatEntertainment", "BIGHat-Program", "main"
TAG = "v32.0.0-alpha.53"
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
     "chore(release): bump -> 32.0.0-alpha.53"),
    ("/app/src-tauri/tauri.conf.json", "src-tauri/tauri.conf.json",
     "chore(release): bump tauri.conf.json -> 32.0.0-alpha.53"),
    ("/app/backend/presentation_builder.py",
     "backend/presentation_builder.py",
     "feat(alpha.53): HARDCODED 17-step build pipeline module (Wizard + "
     "Roulette + Intros CRUD + overlay round-type matcher)"),
    ("/app/backend/native/router.py", "backend/native/router.py",
     "feat(alpha.53): /api/native/presentations/build|roulette, "
     "/api/native/round-pool/{type}, /api/native/intros CRUD"),
    ("/app/backend/native/locations_router.py",
     "backend/native/locations_router.py",
     "feat(alpha.53): PATCH /overlays/{id}/tags — round-type tagging "
     "for per-round overlay compositing"),
    ("/app/backend/native_slides.py", "backend/native_slides.py",
     "feat(alpha.53): render_intros_section + _apply_location_overlays "
     "(Q+A slides only, tag-matched); slide-fetcher plumbing"),
    ("/app/backend/routes/slide_fetcher.py",
     "backend/routes/slide_fetcher.py",
     "feat(alpha.53): pre-fetch location overlays once per section"),
    ("/app/backend/tests/test_alpha53_build_pipeline_and_overlays.py",
     "backend/tests/test_alpha53_build_pipeline_and_overlays.py",
     "test(alpha.53): 24 tests covering all 17 spec steps + endpoints"),
    ("/app/frontend/src/components/trivia/TriviaBuilderWizard.jsx",
     "frontend/src/components/trivia/TriviaBuilderWizard.jsx",
     "feat(alpha.53): wizard POSTs to /api/native/presentations/build "
     "with continue-anyway modal on backend rejection"),
    ("/app/frontend/src/components/trivia/SlotMachineRandomizer.jsx",
     "frontend/src/components/trivia/SlotMachineRandomizer.jsx",
     "feat(alpha.53): roulette POSTs to /api/native/presentations/roulette "
     "with continue-anyway modal on backend rejection"),
    ("/app/frontend/src/components/trivia/TriviaIntrosTab.jsx",
     "frontend/src/components/trivia/TriviaIntrosTab.jsx",
     "feat(alpha.53): new Trivia Admin > Trivia Intro Slides tab (CRUD)"),
    ("/app/frontend/src/pages/trivia/TriviaDashboard.jsx",
     "frontend/src/pages/trivia/TriviaDashboard.jsx",
     "feat(alpha.53): mount Trivia Intro Slides sub-tab in Admin panel"),
    ("/app/memory/CHANGELOG.md", "memory/CHANGELOG.md",
     "docs(alpha.53): changelog entry — hardcoded 17-step pipeline"),
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
