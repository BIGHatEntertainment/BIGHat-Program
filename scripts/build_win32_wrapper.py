#!/usr/bin/env python3
"""
BIG Hat Entertainment — BIGHat.exe cross-compiler.

Builds the Win32 wrapper under packaging/win32_wrapper/ into
dist/payload/BIGHat.exe using the MinGW-w64 cross toolchain. Embeds
the icon, manifest, and version info from the .rc file.

Usage (called automatically by scripts/build_installer.py):
    python scripts/build_win32_wrapper.py --version 31.0.0 \\
        --output /app/dist/payload/BIGHat.exe
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT / "packaging" / "win32_wrapper"
ICO = ROOT / "packaging" / "bighat.ico"


def _which_or_die(*candidates: str) -> str:
    for c in candidates:
        p = shutil.which(c)
        if p:
            return p
    raise SystemExit(
        f"[build-win32] none of {candidates} on PATH.\n"
        f"            Install with:  apt-get install mingw-w64"
    )


def _version_to_dot(version: str) -> str:
    """Coerce a semver-ish string into a comma-separated 4-tuple
    Windows VERSIONINFO can consume (FILEVERSION 31,0,0,0)."""
    cleaned = version.lstrip("vV ").split("+", 1)[0].split("-", 1)[0]
    parts = cleaned.split(".")
    while len(parts) < 4:
        parts.append("0")
    return ",".join(parts[:4])


def build(version: str, output: Path, *, keep_intermediate: bool = False) -> Path:
    gcc = _which_or_die("x86_64-w64-mingw32-gcc")
    windres = _which_or_die("x86_64-w64-mingw32-windres")

    if not (SRC_DIR / "bighat.c").is_file():
        raise SystemExit(f"[build-win32] missing source: {SRC_DIR / 'bighat.c'}")
    if not ICO.is_file():
        raise SystemExit(
            f"[build-win32] missing icon: {ICO}\n"
            "            Generate it from frontend/public/hat-logo.png:\n"
            "                python -c \"from PIL import Image; "
            "Image.open('frontend/public/hat-logo.png').save("
            "'packaging/bighat.ico', sizes=[(256,256),(128,128),(64,64),"
            "(48,48),(32,32),(16,16)])\""
        )

    # Compile resource (.rc -> .res). Because windres needs to find
    # bighat.ico AND bighat.manifest by relative path, run from SRC_DIR.
    res_path = SRC_DIR / "bighat.res"
    # Copy the icon into SRC_DIR so the .rc's `ICON "bighat.ico"` resolves
    # without absolute paths (windres's --include-dir is finicky).
    local_ico = SRC_DIR / "bighat.ico"
    shutil.copy2(ICO, local_ico)

    version_dot = _version_to_dot(version)
    rc_cmd = [
        windres,
        "-O", "coff",
        f"-DBIGHAT_VERSION_DOT={version_dot}",
        f"-DBIGHAT_VERSION_STR=\\\"{version}\\\"",
        "-i", "bighat.rc",
        "-o", "bighat.res",
    ]
    print(f"[build-win32] $ {' '.join(rc_cmd)}  (cwd={SRC_DIR})")
    subprocess.check_call(rc_cmd, cwd=SRC_DIR)

    # Compile + link
    output.parent.mkdir(parents=True, exist_ok=True)
    link_cmd = [
        gcc,
        "-O2", "-s",
        "-mwindows",
        "-municode",
        "-DUNICODE", "-D_UNICODE",
        "-static-libgcc",
        "-Wall", "-Wextra",
        str(SRC_DIR / "bighat.c"),
        str(res_path),
        "-lws2_32", "-lshlwapi",
        "-o", str(output),
    ]
    print(f"[build-win32] $ {' '.join(link_cmd)}")
    subprocess.check_call(link_cmd)

    if not keep_intermediate:
        for tmp in (res_path, local_ico):
            try:
                tmp.unlink()
            except OSError:
                pass

    size = output.stat().st_size
    print(f"[build-win32] built {output} ({size:,} bytes)")
    return output


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Build BIGHat.exe Win32 wrapper")
    p.add_argument("--version", required=True, help="semver, e.g. 31.0.0")
    p.add_argument("--output", required=True, type=Path,
                   help="path to write BIGHat.exe to (e.g. dist/payload/BIGHat.exe)")
    p.add_argument("--keep-intermediate", action="store_true",
                   help="don't delete bighat.res and the staged bighat.ico")
    args = p.parse_args(argv if argv is not None else sys.argv[1:])
    build(args.version, args.output, keep_intermediate=args.keep_intermediate)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
