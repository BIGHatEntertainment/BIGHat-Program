#!/usr/bin/env python3
"""Tauri sidecar builder — freezes `backend/launcher.py` into a single
self-contained executable using PyInstaller, then writes it into
`src-tauri/binaries/bighat-backend-<TARGET_TRIPLE>(.exe)`.

This script runs on EACH platform-specific GitHub Actions runner
(`windows-latest`, `macos-13` for Intel, `macos-14` for Apple Silicon),
because PyInstaller cannot cross-compile — the resulting binary must be
produced on the same OS+arch it targets.

Usage:
    python scripts/build_sidecar.py
    python scripts/build_sidecar.py --target x86_64-pc-windows-msvc
    python scripts/build_sidecar.py --target aarch64-apple-darwin
"""
from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
SIDECAR_DIR = ROOT / "src-tauri" / "binaries"
SIDECAR_NAME = "bighat-backend"


def detect_target_triple() -> str:
    """Best-effort default for the current platform if `--target` isn't given."""
    if sys.platform == "win32":
        return "x86_64-pc-windows-msvc"
    if sys.platform == "darwin":
        arch = platform.machine().lower()
        return "aarch64-apple-darwin" if arch in ("arm64", "aarch64") else "x86_64-apple-darwin"
    return "x86_64-unknown-linux-gnu"


def ensure_pyinstaller() -> None:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("[sidecar] installing pyinstaller into the active venv")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller>=6.6,<7"])


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Freeze backend/launcher.py for Tauri sidecar use")
    p.add_argument("--target", default=detect_target_triple(),
                   help="Rust target triple suffix appended to the binary name")
    args = p.parse_args(argv)

    target = args.target
    ext = ".exe" if "windows" in target else ""
    out_name = f"{SIDECAR_NAME}-{target}{ext}"
    out_path = SIDECAR_DIR / out_name

    SIDECAR_DIR.mkdir(parents=True, exist_ok=True)
    ensure_pyinstaller()

    # Install the backend deps into the current venv FIRST so PyInstaller
    # has them available to bundle. We deliberately use requirements-desktop.txt
    # (the desktop-only subset — no MongoDB driver etc).
    desktop_reqs = BACKEND / "requirements-desktop.txt"
    if desktop_reqs.is_file():
        print(f"[sidecar] installing {desktop_reqs} into current venv")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "-r", str(desktop_reqs)]
        )
    else:
        print(f"[sidecar] WARNING: {desktop_reqs} missing — sidecar may lack runtime deps")

    work_dir = ROOT / "dist" / "sidecar-build"
    dist_dir = ROOT / "dist" / "sidecar-dist"
    spec_dir = ROOT / "dist" / "sidecar-spec"
    for d in (work_dir, dist_dir, spec_dir):
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--name", SIDECAR_NAME,
        "--clean",
        "--noconfirm",
        "--workpath", str(work_dir),
        "--distpath", str(dist_dir),
        "--specpath", str(spec_dir),
        "--paths", str(BACKEND),
        "--collect-all", "fastapi",
        "--collect-all", "uvicorn",
        "--collect-all", "starlette",
        "--collect-all", "pydantic",
        "--collect-all", "pydantic_core",
        "--collect-all", "passlib",
        "--collect-all", "jose",
        "--collect-all", "montydb",
        "--collect-submodules", "native",
        "--collect-submodules", "routes",
        "--collect-submodules", "cloud",
        # Static SPA bundle + version + .env template ride along as data.
        "--add-data", f"{BACKEND / 'static'}{os.pathsep}static",
        "--add-data", f"{BACKEND / 'VERSION.txt'}{os.pathsep}.",
        str(BACKEND / "launcher.py"),
    ]
    print("[sidecar] $ " + " ".join(cmd))
    subprocess.check_call(cmd, cwd=ROOT)

    built = dist_dir / (f"{SIDECAR_NAME}.exe" if ext == ".exe" else SIDECAR_NAME)
    if not built.is_file():
        raise SystemExit(f"[sidecar] pyinstaller produced no binary at {built}")

    shutil.copy2(built, out_path)
    print(f"[sidecar] wrote {out_path} ({out_path.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
