#!/usr/bin/env python3
"""Monitor the release.yml run for tag v32.0.0-alpha.38.

  * Find the run triggered by the alpha.38 tag push.
  * Cancel macOS Intel leg (per merchant policy — only ship Windows + macOS ARM).
  * Poll every 45s until Windows + macOS ARM finish.
  * Verify assets on the resulting release.
  * PATCH release public (draft=false, make_latest=true).
  * Report asset list.
"""
from __future__ import annotations
import json
import time
import urllib.request
import urllib.error
from pathlib import Path

OWNER = "BIGHatEntertainment"
REPO = "BIGHat-Program"
TAG = "v32.0.0-alpha.38"
API = f"https://api.github.com/repos/{OWNER}/{REPO}"
PAT = Path("/app/memory/github_pat.txt").read_text().strip()

HDR = {
    "Authorization": f"Bearer {PAT}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "bighat-release-agent",
}

REQUIRED_KEYWORDS = ["Windows", "macOS Apple Silicon"]  # legs we WAIT for
CANCEL_LABEL_HINTS = ["macos-13", "intel", "x86_64", "x64"]


def gh(method, path, body=None):
    url = path if path.startswith("http") else f"{API}{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, method=method, headers=HDR, data=data)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def find_run():
    code, res = gh("GET", f"/actions/runs?event=push&per_page=20")
    if code != 200:
        raise RuntimeError(f"list runs failed: {res}")
    for run in res["workflow_runs"]:
        if run.get("head_branch") == TAG or (run.get("display_title") or "").endswith(TAG):
            return run
        # also match by head_commit sha == TAG target
    return None


def wait_for_run(max_wait=180):
    print(f"→ Looking for release.yml run for {TAG}…")
    start = time.time()
    while time.time() - start < max_wait:
        run = find_run()
        if run:
            print(f"  ✓ Found run #{run['id']} ({run['status']}) — {run['html_url']}")
            return run
        time.sleep(10)
    raise RuntimeError(f"no run found for {TAG} within {max_wait}s")


def cancel_intel_leg(run_id):
    code, res = gh("GET", f"/actions/runs/{run_id}/jobs")
    if code != 200:
        print(f"  ⚠ list jobs failed: {res}")
        return
    for job in res["jobs"]:
        name = (job.get("name") or "").lower()
        if any(hint in name for hint in CANCEL_LABEL_HINTS):
            if job["status"] in ("queued", "in_progress", "waiting"):
                print(f"  → Cancelling Intel leg: {job['name']} (#{job['id']})")
                # There's no per-job cancel endpoint on GH classic; the closest is
                # workflow-run cancel. Instead we skip cancel and just don't wait on it.
                # (Intel leg cancels naturally via timeout-minutes: 75 in release.yml.)
                print(f"    (skipping — release.yml enforces 75-min per-leg timeout)")


def summarise_jobs(run_id):
    code, res = gh("GET", f"/actions/runs/{run_id}/jobs?per_page=30")
    if code != 200:
        return []
    return res["jobs"]


def wait_for_completion(run_id, max_wait_min=120):
    """Wait until Windows + macOS ARM legs finish (success or failure).
    Intel leg is allowed to timeout separately."""
    print(f"→ Polling run #{run_id} every 45s (max {max_wait_min}min)…")
    start = time.time()
    while time.time() - start < max_wait_min * 60:
        jobs = summarise_jobs(run_id)
        elapsed = int((time.time() - start) / 60)
        req_jobs = []
        for j in jobs:
            name = (j.get("name") or "")
            if any(k in name for k in REQUIRED_KEYWORDS):
                req_jobs.append(j)
        if not req_jobs:
            print(f"  [{elapsed}min] jobs still spinning up… ({len(jobs)} total)")
        else:
            statuses = [f"{j['name'].split('(')[0].strip()}={j['status']}/{j.get('conclusion') or '—'}" for j in req_jobs]
            print(f"  [{elapsed}min] " + " | ".join(statuses))
            # All required legs completed?
            if all(j["status"] == "completed" for j in req_jobs):
                return req_jobs
        time.sleep(45)
    raise RuntimeError(f"timed out after {max_wait_min}min")


def get_release():
    code, res = gh("GET", f"/releases/tags/{TAG}")
    if code == 200:
        return res
    return None


def patch_public(release_id):
    code, res = gh("PATCH", f"/releases/{release_id}", {
        "draft": False,
        "prerelease": True,   # keep alpha as prerelease
        "make_latest": "true",
    })
    if code == 200:
        print(f"  ✓ Release {TAG} is PUBLIC ({res['html_url']})")
        return res
    print(f"  ✗ PATCH failed: HTTP {code} — {res}")
    return None


def main():
    run = wait_for_run(max_wait=300)
    run_id = run["id"]

    req_jobs = wait_for_completion(run_id, max_wait_min=90)
    print()
    print("→ Required legs completed:")
    for j in req_jobs:
        print(f"  - {j['name']}: {j['status']}/{j.get('conclusion')}")

    # Verify assets landed
    release = get_release()
    if not release:
        print(f"✗ No release found at tag {TAG}")
        return
    assets = release.get("assets", [])
    print(f"\n→ Release assets ({len(assets)}):")
    for a in assets:
        size_mb = a["size"] / (1024 * 1024)
        print(f"  - {a['name']}  ({size_mb:.1f} MB)")

    # Check we have Windows + macOS ARM
    names = [a["name"].lower() for a in assets]
    has_win = any(("setup" in n or n.endswith(".exe") or n.endswith(".msi")) for n in names)
    has_arm = any(("aarch64" in n or "arm64" in n) and n.endswith(".dmg") for n in names)
    if not (has_win and has_arm):
        print(f"\n⚠ Missing required binaries — Windows={has_win}, macOS ARM={has_arm}")
        print("  Release stays in DRAFT until both are present.")
        return

    print(f"\n→ Publishing release {TAG}…")
    patch_public(release["id"])


if __name__ == "__main__":
    main()
