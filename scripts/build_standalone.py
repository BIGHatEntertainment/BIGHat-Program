#!/usr/bin/env python3
"""
BIG Hat Standalone V31 — Build orchestrator.

Runs from any checkout to produce a self-contained bundle:

    1. cd frontend && yarn install (skippable)
    2. yarn build                  — produces frontend/build/
    3. Copy build/ into backend/static/ so the launcher serves it
    4. Write build_manifest.json  — version, git sha, file counts, timestamp

Typical one-liner from `/app`:

    python scripts/build_standalone.py --skip-install

Flags:
    --skip-install  skip `yarn install` (faster on CI re-runs)
    --clean         wipe backend/static before copying
    --no-frontend   skip frontend entirely; useful for backend-only dev
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"
BACKEND = ROOT / "backend"
STATIC_DIR = BACKEND / "static"
MANIFEST = BACKEND / "static" / "build_manifest.json"


def _run(cmd: list[str], cwd: Path) -> None:
    print(f"[build] $ {' '.join(cmd)} (cwd={cwd})")
    r = subprocess.run(cmd, cwd=cwd)
    if r.returncode != 0:
        raise SystemExit(f"[build] command failed (exit {r.returncode}): {' '.join(cmd)}")


def _git_sha() -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, stderr=subprocess.DEVNULL,
        )
        return out.decode().strip()
    except Exception:
        return "unknown"


def _which(cmd: str) -> str:
    """Find an executable on PATH (cross-platform)."""
    return shutil.which(cmd) or cmd


def _count_files(path: Path) -> int:
    return sum(1 for p in path.rglob("*") if p.is_file())


def build_frontend(skip_install: bool, clean: bool) -> Path:
    yarn = _which("yarn")
    if not skip_install:
        _run([yarn, "install", "--frozen-lockfile"], cwd=FRONTEND)
    _run([yarn, "build"], cwd=FRONTEND)

    build_dir = FRONTEND / "build"
    if not build_dir.is_dir():
        raise SystemExit(f"[build] expected {build_dir} after yarn build")

    if clean and STATIC_DIR.exists():
        print(f"[build] cleaning {STATIC_DIR}")
        shutil.rmtree(STATIC_DIR)
    STATIC_DIR.mkdir(parents=True, exist_ok=True)

    # Copy every file into backend/static/. We do a file-by-file copy rather
    # than `shutil.copytree(dirs_exist_ok=True)` so existing non-frontend
    # files (if any) aren't clobbered.
    for src in build_dir.rglob("*"):
        if not src.is_file():
            continue
        rel = src.relative_to(build_dir)
        dst = STATIC_DIR / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    print(f"[build] copied {_count_files(STATIC_DIR)} files into {STATIC_DIR}")
    return STATIC_DIR


def write_manifest(frontend_built: bool) -> None:
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    manifest = {
        "built_at": int(time.time()),
        "git_sha": _git_sha(),
        "frontend_included": frontend_built,
        "file_count": _count_files(STATIC_DIR),
        "python_version": sys.version.split()[0],
        "platform": sys.platform,
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"[build] manifest -> {MANIFEST}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="BIG Hat Standalone build orchestrator")
    p.add_argument("--skip-install", action="store_true")
    p.add_argument("--clean", action="store_true")
    p.add_argument("--no-frontend", action="store_true")
    args = p.parse_args(argv if argv is not None else sys.argv[1:])

    frontend_built = False
    if not args.no_frontend:
        build_frontend(skip_install=args.skip_install, clean=args.clean)
        frontend_built = True
    else:
        print("[build] --no-frontend set; skipping yarn build")

    write_manifest(frontend_built)

    print("[build] done. Start with:  python backend/launcher.py")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
