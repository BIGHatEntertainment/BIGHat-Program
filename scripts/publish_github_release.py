#!/usr/bin/env python3
"""BIG Hat Entertainment — GitHub Release publisher."""
from __future__ import annotations

import argparse
import json
import logging
import mimetypes
import os
import pathlib
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
BACKEND = ROOT / "backend"

logger = logging.getLogger("github-release")
GITHUB_API = "https://api.github.com"
GITHUB_UPLOADS = "https://uploads.github.com"


class GitHubError(Exception):
    pass


def _request(method, url, *, token, data=None, headers=None, content_type=None):
    h = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "bighat-release-publisher",
    }
    if content_type:
        h["Content-Type"] = content_type
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            body = resp.read()
            return json.loads(body.decode("utf-8")) if body else None
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise GitHubError(f"{method} {url} -> HTTP {e.code}\n{body}") from None


def _read_version(explicit):
    if explicit:
        return explicit.strip().lstrip("vV ")
    p = BACKEND / "VERSION.txt"
    if not p.is_file():
        raise SystemExit(f"[release] {p} missing; pass --version explicitly")
    return p.read_text(encoding="utf-8").strip()


def find_or_create_release(*, owner, repo, tag, name, body, token, draft, prerelease):
    try:
        return _request("GET",
            f"{GITHUB_API}/repos/{owner}/{repo}/releases/tags/{urllib.parse.quote(tag)}",
            token=token)
    except GitHubError as e:
        if "HTTP 404" not in str(e):
            raise
    print(f"[release] creating release {tag}")
    payload = json.dumps({
        "tag_name": tag, "name": name, "body": body,
        "draft": draft, "prerelease": prerelease,
    }).encode("utf-8")
    return _request("POST",
        f"{GITHUB_API}/repos/{owner}/{repo}/releases",
        token=token, data=payload, content_type="application/json")


def list_artifacts(version):
    patterns = [
        f"BIGHatStandalone-Setup-{version}.exe",
        f"BIGHatEntertainment-{version}-Windows.zip",
        f"BIGHatEntertainment-{version}-macOS-AppleSilicon.zip",
        f"BIGHatEntertainment-{version}-macOS-Intel.zip",
    ]
    return [DIST / pat for pat in patterns if (DIST / pat).is_file()]


def _verify_artifact(path: pathlib.Path) -> None:
    """v31.0.13 lessons learned: refuse to upload a truncated NSIS installer
    or zip. The integrity check failed on a customer machine because makensis
    got killed mid-write last time. Run a structural sanity check before any
    HTTP PUT."""
    if path.suffix.lower() == ".exe":
        # Minimum acceptable NSIS installer size. Anything smaller than the
        # baseline Python embeddable is by definition truncated.
        MIN_EXE = 40 * 1024 * 1024
        size = path.stat().st_size
        if size < MIN_EXE:
            raise SystemExit(f"[release] {path.name} is suspiciously small ({size/1e6:.1f}MB) — refusing to upload.")
        # 7z is normally present on macOS/Linux CI runners. If absent, skip;
        # otherwise verify the NSIS structure end-to-end.
        sevenz = shutil.which("7z")
        if sevenz:
            result = subprocess.run(
                [sevenz, "t", str(path)], capture_output=True, text=True, timeout=120,
            )
            if "Everything is Ok" not in result.stdout:
                raise SystemExit(
                    f"[release] {path.name} failed NSIS integrity check (7z t):\n"
                    f"--- stdout ---\n{result.stdout[-800:]}\n--- stderr ---\n{result.stderr[-400:]}"
                )
    elif path.suffix.lower() == ".zip":
        # zipfile.is_zipfile only checks the EOCD marker — sufficient to
        # detect a mid-write truncation since EOCD is the last record.
        import zipfile
        if not zipfile.is_zipfile(path):
            raise SystemExit(f"[release] {path.name} is not a valid zip — refusing to upload.")


def upload_asset(*, owner, repo, release_id, path, token, replace_existing):
    name = path.name
    existing = _request("GET",
        f"{GITHUB_API}/repos/{owner}/{repo}/releases/{release_id}/assets",
        token=token) or []
    for a in existing:
        if a.get("name") == name:
            if not replace_existing:
                print(f"[release] asset {name} already exists; skipping")
                return a
            print(f"[release] deleting existing asset {name}")
            _request("DELETE",
                f"{GITHUB_API}/repos/{owner}/{repo}/releases/assets/{a['id']}",
                token=token)
    mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
    upload_url = (
        f"{GITHUB_UPLOADS}/repos/{owner}/{repo}/releases/{release_id}/assets"
        f"?name={urllib.parse.quote(name)}"
    )
    size = path.stat().st_size
    print(f"[release] uploading {name} ({size:,} bytes)")
    with path.open("rb") as f:
        data = f.read()
    return _request("POST", upload_url, token=token, data=data,
                    content_type=mime,
                    headers={"Content-Length": str(size)})


def main(argv=None):
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser()
    p.add_argument("--owner", default=os.environ.get("GITHUB_OWNER"))
    p.add_argument("--repo", default=os.environ.get("GITHUB_REPO"))
    p.add_argument("--token", default=os.environ.get("GITHUB_TOKEN"))
    p.add_argument("--version", default=None)
    p.add_argument("--tag-prefix", default="v")
    p.add_argument("--name", default=None)
    p.add_argument("--draft", action="store_true")
    p.add_argument("--prerelease", action="store_true")
    p.add_argument("--replace-existing", action="store_true")
    args = p.parse_args(argv if argv is not None else sys.argv[1:])

    if not args.owner or not args.repo or not args.token:
        raise SystemExit("[release] need GITHUB_OWNER / GITHUB_REPO / GITHUB_TOKEN")

    version = _read_version(args.version)
    tag = f"{args.tag_prefix}{version}"
    name = args.name or f"BIG Hat Entertainment {version}"

    # Release body — includes per-release highlights when available, else a
    # generic line. Highlights live at scripts/release_notes/<version>.md so
    # CI / authors can drop a markdown file there next to the build.
    notes_path = ROOT / "scripts" / "release_notes" / f"{version}.md"
    if notes_path.is_file():
        highlights = notes_path.read_text(encoding="utf-8").rstrip() + "\n\n"
    else:
        highlights = (
            f"Embedded Python + all deps — no internet required after install.\n\n"
        )
    body = (
        f"# BIG Hat Entertainment {version}\n\n"
        + highlights
        + "### Installers\n"
        f"- **Windows**: `BIGHatStandalone-Setup-{version}.exe`\n"
        f"- **macOS Apple Silicon (M1/M2/M3)**: "
        f"`BIGHatEntertainment-{version}-macOS-AppleSilicon.zip`\n"
        f"- **macOS Intel (pre-2020 Macs)**: "
        f"`BIGHatEntertainment-{version}-macOS-Intel.zip`\n"
        f"- Windows portable (no installer): "
        f"`BIGHatEntertainment-{version}-Windows.zip`\n"
    )

    artifacts = list_artifacts(version)
    if not artifacts:
        raise SystemExit(f"[release] no installer artifacts for {version} under {DIST}")
    print(f"[release] target: {args.owner}/{args.repo} tag={tag}")
    for a in artifacts:
        print(f"           - {a.name} ({a.stat().st_size:,} bytes)")

    # Pre-flight integrity verification (added v31.0.13). Bails out early
    # rather than half-uploading a truncated installer that a customer would
    # later see as 'NSIS integrity check failed'.
    print("[release] verifying artifact integrity...")
    for a in artifacts:
        _verify_artifact(a)
        print(f"[release]   OK {a.name}")

    release = find_or_create_release(
        owner=args.owner, repo=args.repo,
        tag=tag, name=name, body=body, token=args.token,
        draft=args.draft, prerelease=args.prerelease)
    rid = release["id"]
    print(f"[release] release id={rid} url={release.get('html_url')}")
    for path in artifacts:
        try:
            up = upload_asset(owner=args.owner, repo=args.repo,
                              release_id=rid, path=path, token=args.token,
                              replace_existing=args.replace_existing)
            if up:
                print(f"[release]   OK {path.name} -> {up.get('browser_download_url')}")
        except GitHubError as e:
            print(f"[release]   FAIL {path.name}: {e}", file=sys.stderr)
            return 1
    print(f"[release] DONE {release.get('html_url')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
