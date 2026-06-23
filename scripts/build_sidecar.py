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

    # The CI workflow builds the React frontend into `frontend/build/`.
    # The standalone server expects to serve those files from
    # `<sidecar_root>/static/`. Copy them across right before freezing so
    # the SPA mount in server.py finds them at runtime.
    react_build = ROOT / "frontend" / "build"
    backend_static = BACKEND / "static"
    if react_build.is_dir():
        # Mirror frontend/build/ -> backend/static/ (overwriting stale files)
        if backend_static.exists():
            shutil.rmtree(backend_static)
        shutil.copytree(react_build, backend_static)
        print(f"[sidecar] mirrored {react_build} -> {backend_static} "
              f"({sum(1 for _ in backend_static.rglob('*') if _.is_file())} files)")
    else:
        print(f"[sidecar] WARNING: {react_build} not found — SPA bundle will be empty")

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
        # Hidden imports the native router needs (PyInstaller often misses
        # these — they're the usual cause of "Setup Wizard 405 Method Not
        # Allowed" because native/router.py fails to import inside the bundle).
        "--collect-all", "bcrypt",
        "--collect-all", "email_validator",
        "--collect-all", "dns",                  # dnspython (used by email_validator)
        "--collect-all", "httpx",                # used by cloud_client.py
        "--collect-all", "httpcore",
        "--collect-all", "h11",
        "--collect-all", "anyio",
        "--collect-all", "sniffio",
        "--collect-all", "idna",
        "--hidden-import", "email_validator",
        "--hidden-import", "bcrypt",
        "--hidden-import", "httpx",
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
