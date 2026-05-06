#!/usr/bin/env python3
"""
BIG Hat Standalone V31 — Windows installer build orchestrator.

Replaces the legacy zip-and-copy distribution model. One command produces
a single signed `BIGHatStandalone-Setup-<version>.exe`:

    1. Reads version from `backend/VERSION.txt` (or `--version`).
    2. Assembles a payload tree under `dist/payload/`:
        - backend/  (everything from /app/backend except `__pycache__`,
                     `data/`, `static/build_manifest.json`, `*.pyc`)
        - packaging/ (start_bighat.vbs, install_shortcut.vbs, README.md,
                      bighat.ico if present)
        - python/   (skipped here — must be supplied via `--python-dir`
                     or pre-staged into `dist/payload/python/`)
        - VERSION.txt
    3. Runs `makensis` to compile the NSIS script
       (`packaging/installer/bighat-installer.nsi`).
    4. Optionally Authenticode-signs the resulting .exe via
       `osslsigncode` (cross-platform) when `--cert` + `--cert-password`
       (or env `BIGHAT_SIGNING_CERT_PFX` + `BIGHAT_SIGNING_PASSWORD`)
       are provided.

The script is platform-portable. On Windows you can use `signtool.exe`
instead by passing `--signer signtool`; otherwise `osslsigncode` is the
default and works on Linux/macOS CI runners.

Typical usage:
    python scripts/build_installer.py                    # build, no sign
    python scripts/build_installer.py --skip-frontend    # backend only
    python scripts/build_installer.py \\
        --cert /secrets/codesigning.pfx \\
        --cert-password "$BIGHAT_SIGNING_PASSWORD"
"""
from __future__ import annotations

import argparse
import hashlib
import logging
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

logger = logging.getLogger("build-installer")

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
PACKAGING = ROOT / "packaging"
INSTALLER_NSI = PACKAGING / "installer" / "bighat-installer.nsi"
DIST = ROOT / "dist"
PAYLOAD = DIST / "payload"
CACHE = DIST / ".cache"

# Windows embeddable CPython — pinned for reproducible builds.
EMBED_PYTHON_VERSION = "3.11.9"
EMBED_PYTHON_URL = (
    f"https://www.python.org/ftp/python/{EMBED_PYTHON_VERSION}/"
    f"python-{EMBED_PYTHON_VERSION}-embed-amd64.zip"
)
# Official sha256 from python.org for 3.11.9 amd64 embeddable.
EMBED_PYTHON_SHA256 = "009d6bf7e3b2ddca3d784fa09f90fe54336d5b60f0e0f305c37f400bf83cfd3b"

# pip wheel installer (get-pip.py) for bootstrapping pip into the embeddable runtime.
GET_PIP_URL = "https://bootstrap.pypa.io/get-pip.py"

# Files / dirs we never ship in the payload.
PAYLOAD_EXCLUDES = {
    "__pycache__", "node_modules", ".pytest_cache", ".git", ".cache",
}
PAYLOAD_EXCLUDE_NAMES = {"data", "tests", "test_reports"}  # backend subdirs to skip


def _read_version(explicit: str | None) -> str:
    if explicit:
        return explicit.strip().lstrip("vV ")
    p = BACKEND / "VERSION.txt"
    if not p.is_file():
        raise SystemExit(f"[build-installer] {p} missing; pass --version explicitly")
    return p.read_text(encoding="utf-8").strip()


def _which(cmd: str) -> str | None:
    return shutil.which(cmd)


def _safe_rmtree(p: Path) -> None:
    if p.exists():
        shutil.rmtree(p)


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _download(url: str, dest: Path, *, expected_sha256: str | None = None) -> Path:
    """Download `url` to `dest` (cached). Verifies sha256 if provided."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file() and expected_sha256 and _sha256(dest) == expected_sha256:
        print(f"[build-installer] cache hit: {dest.name}")
        return dest
    print(f"[build-installer] downloading {url}")
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(url) as r, tmp.open("wb") as f:
        shutil.copyfileobj(r, f)
    if expected_sha256:
        got = _sha256(tmp)
        if got != expected_sha256:
            tmp.unlink(missing_ok=True)
            raise SystemExit(
                f"[build-installer] sha256 mismatch for {url}\n"
                f"   expected {expected_sha256}\n   got      {got}"
            )
    tmp.replace(dest)
    return dest


def fetch_embeddable_python(target: Path) -> Path:
    """Download and extract the Windows embeddable CPython distribution into `target`.

    Also enables `import site` in `python<ver>._pth` and adds the
    `Lib\\site-packages` search path so that wheels pre-installed by
    `bake_desktop_wheels()` are importable when the customer launches the app.
    """
    if target.is_dir() and (target / "python.exe").is_file():
        print(f"[build-installer] embeddable Python already staged at {target}")
        return target

    zip_path = CACHE / f"python-{EMBED_PYTHON_VERSION}-embed-amd64.zip"
    _download(EMBED_PYTHON_URL, zip_path, expected_sha256=EMBED_PYTHON_SHA256)

    _safe_rmtree(target)
    target.mkdir(parents=True, exist_ok=True)
    print(f"[build-installer] extracting embeddable Python -> {target}")
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(target)

    # Enable site-packages so that `pip install` works inside the embeddable runtime.
    # The file is named e.g. python311._pth; we uncomment the `import site` line and
    # explicitly add the Lib\\site-packages search path (the embed default omits it).
    pth_files = list(target.glob("python*._pth"))
    if not pth_files:
        raise SystemExit(f"[build-installer] no python*._pth found in {target}")
    pth = pth_files[0]
    text = pth.read_text(encoding="utf-8")
    if "#import site" in text:
        text = text.replace("#import site", "import site")
    if "Lib\\site-packages" not in text and "Lib/site-packages" not in text:
        # Insert before the `import site` line so the path is registered first.
        if "import site" in text:
            text = text.replace("import site", "Lib\\site-packages\nimport site")
        else:
            text = text.rstrip() + "\nLib\\site-packages\nimport site\n"
    pth.write_text(text, encoding="utf-8")
    print(f"[build-installer] enabled site-packages in {pth.name}")

    # Pre-create the site-packages dir so `pip download --target` lands cleanly.
    (target / "Lib" / "site-packages").mkdir(parents=True, exist_ok=True)
    return target


def bake_desktop_wheels(python_dir: Path, *, requirements: Path) -> int:
    """Pre-install all desktop runtime wheels into the embedded Python's
    `Lib/site-packages/` so the customer never needs internet on first launch.

    We use `pip install --target` against Windows wheels (`--platform win_amd64`,
    `--python-version 3.11`, `--only-binary=:all:`). The dev box can be Linux —
    `pip` resolves and downloads the Windows wheels, then copies their contents
    into the target dir. No execution of compiled Windows code happens locally.
    """
    if not requirements.is_file():
        raise SystemExit(f"[build-installer] missing {requirements}")
    site_packages = python_dir / "Lib" / "site-packages"
    site_packages.mkdir(parents=True, exist_ok=True)

    # Ensure python311._pth has site-packages + `import site` even when we're
    # baking into a pre-staged embed (fetch_embeddable_python is skipped on
    # cache hits but the .pth must still be correct).
    for pth in python_dir.glob("python*._pth"):
        text = pth.read_text(encoding="utf-8")
        original = text
        if "#import site" in text:
            text = text.replace("#import site", "import site")
        if "Lib\\site-packages" not in text and "Lib/site-packages" not in text:
            if "import site" in text:
                text = text.replace("import site", "Lib\\site-packages\nimport site")
            else:
                text = text.rstrip() + "\nLib\\site-packages\nimport site\n"
        if text != original:
            pth.write_text(text, encoding="utf-8")
            print(f"[build-installer] patched {pth.name} for site-packages")

    # If we've already baked, skip — keyed by requirements file mtime via a marker.
    marker = site_packages / ".bighat_wheels_baked"
    req_mtime = requirements.stat().st_mtime
    if marker.is_file() and float(marker.read_text().strip() or "0") >= req_mtime:
        n = sum(1 for _ in site_packages.rglob("*") if _.is_file())
        print(f"[build-installer] wheels already baked ({n} files); use --rebake to redo")
        return n

    # Clean old wheels (but keep the marker line writeable below).
    for child in site_packages.iterdir():
        if child.name == ".bighat_wheels_baked":
            continue
        if child.is_dir():
            shutil.rmtree(child, ignore_errors=True)
        else:
            child.unlink()

    print(f"[build-installer] baking Windows wheels into {site_packages}")
    cmd = [
        sys.executable, "-m", "pip", "install",
        "--target", str(site_packages),
        "--platform", "win_amd64",
        "--python-version", "3.11",
        "--implementation", "cp",
        "--abi", "cp311",
        "--only-binary=:all:",
        "--no-compile",
        "--upgrade",
        "-r", str(requirements),
    ]
    print(f"[build-installer] $ {' '.join(cmd)}")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.stdout.write(r.stdout)
        sys.stderr.write(r.stderr)
        raise SystemExit(
            f"[build-installer] pip install --target failed (exit {r.returncode}). "
            f"See output above; common cause is a transitive dep missing a "
            f"win_amd64 cp311 wheel — pin a different version in "
            f"backend/requirements-desktop.txt."
        )
    # Print only the trailing summary, not the 100s of "Collecting" lines.
    tail = "\n".join((r.stdout or "").splitlines()[-3:])
    if tail:
        print(tail)
    marker.write_text(str(req_mtime), encoding="utf-8")
    n = sum(1 for _ in site_packages.rglob("*") if _.is_file())
    print(f"[build-installer] baked {n} files into Lib/site-packages")
    return n


def _copy_tree(src: Path, dst: Path, *, exclude_dirs: set[str], exclude_names: set[str] = frozenset()) -> int:
    """Copy `src` into `dst`, skipping any dir whose name is in `exclude_dirs`
    and any top-level dir name in `exclude_names`. Returns file count."""
    n = 0
    for root, dirs, files in os.walk(src):
        # In-place mutate dirs to prune the walk
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        rel = Path(root).relative_to(src)
        if rel.parts and rel.parts[0] in exclude_names:
            continue
        target_dir = dst / rel
        target_dir.mkdir(parents=True, exist_ok=True)
        for f in files:
            if f.endswith((".pyc", ".pyo")):
                continue
            # SECURITY: never ship `.env*` (production secrets, API keys,
            # OAuth client secrets etc) to customer machines.
            if f == ".env" or f.startswith(".env."):
                continue
            shutil.copy2(Path(root) / f, target_dir / f)
            n += 1
    return n


def assemble_payload(*, python_dir: Path | None, skip_frontend: bool, embed_python: bool) -> int:
    _safe_rmtree(PAYLOAD)
    PAYLOAD.mkdir(parents=True, exist_ok=True)

    # backend/
    backend_files = _copy_tree(
        BACKEND, PAYLOAD / "backend",
        exclude_dirs=PAYLOAD_EXCLUDES,
        exclude_names=PAYLOAD_EXCLUDE_NAMES,
    )
    print(f"[build-installer] payload backend/  : {backend_files} files")

    # packaging/ (start_bighat.vbs, README, ico, etc — but not installer/ itself)
    packaging_files = _copy_tree(
        PACKAGING, PAYLOAD / "packaging",
        exclude_dirs=PAYLOAD_EXCLUDES,
        exclude_names={"installer"},
    )
    print(f"[build-installer] payload packaging/: {packaging_files} files")

    # python runtime
    target_py = PAYLOAD / "python"
    if python_dir:
        if not python_dir.is_dir():
            raise SystemExit(f"[build-installer] --python-dir not found: {python_dir}")
        n = _copy_tree(python_dir, target_py, exclude_dirs=PAYLOAD_EXCLUDES)
        print(f"[build-installer] payload python/   : {n} files (from {python_dir})")
    elif target_py.exists() and (target_py / "python.exe").is_file():
        print("[build-installer] payload python/   : pre-staged, leaving alone")
    elif embed_python:
        fetch_embeddable_python(target_py)
        n = sum(1 for _ in target_py.rglob("*") if _.is_file())
        print(f"[build-installer] payload python/   : {n} files (embeddable {EMBED_PYTHON_VERSION})")
    else:
        print("[build-installer] payload python/   : ABSENT — build will produce a runner-less installer")
        print("[build-installer]                       Pass --python-dir to embed CPython, or pre-stage it.")

    # Bake desktop runtime wheels (uvicorn, fastapi, pydantic, …) into the embed
    # so the customer's first launch never needs internet or pip.
    if (target_py / "python.exe").is_file():
        desktop_reqs = BACKEND / "requirements-desktop.txt"
        if desktop_reqs.is_file():
            bake_desktop_wheels(target_py, requirements=desktop_reqs)
        else:
            print(f"[build-installer] WARNING: {desktop_reqs} missing — installer will be missing all third-party deps")

    # VERSION.txt at the install root (separate from backend/VERSION.txt for visibility)
    version = _read_version(None)
    (PAYLOAD / "VERSION.txt").write_text(version + "\n", encoding="utf-8")

    # BIGHat.exe — Win32 wrapper that replaces the wscript.exe + .vbs launcher
    # chain with a polished, icon-bearing GUI executable. Cross-compiled with
    # MinGW-w64 on the Linux dev box.
    try:
        from importlib import import_module
        wrapper_mod = import_module("build_win32_wrapper")
    except ImportError:
        sys.path.insert(0, str(ROOT / "scripts"))
        try:
            from importlib import import_module as _im2
            wrapper_mod = _im2("build_win32_wrapper")
        except ImportError as e:
            wrapper_mod = None
            print(f"[build-installer] WARNING: cannot import build_win32_wrapper: {e}")
    if wrapper_mod is not None:
        try:
            wrapper_mod.build(version, PAYLOAD / "BIGHat.exe")
        except SystemExit as e:
            print(f"[build-installer] WARNING: BIGHat.exe build skipped: {e}")
        except subprocess.CalledProcessError as e:
            print(f"[build-installer] WARNING: BIGHat.exe build failed: {e}")
    else:
        print("[build-installer] WARNING: BIGHat.exe wrapper not built — "
              "install mingw-w64 to enable.")

    # SECURITY: ship the desktop-safe `.env.standalone` template in the place
    # where the launcher expects to find it on first run. The real `.env` is
    # generated per-install by `launcher.py` (with a unique JWT_SECRET).
    env_template_src = PACKAGING / ".env.standalone"
    if env_template_src.is_file():
        shutil.copy2(env_template_src, PAYLOAD / "backend" / ".env.standalone")
        print("[build-installer] payload .env.standalone shipped (desktop-safe template)")
    else:
        print(f"[build-installer] WARNING: {env_template_src} missing; "
              "first-run env bootstrap will fall back to defaults")

    # Frontend bundle (re-uses the existing build orchestrator)
    if not skip_frontend:
        bundle = BACKEND / "static"
        if not (bundle / "index.html").is_file():
            print("[build-installer] frontend bundle missing — running scripts/build_standalone.py")
            subprocess.check_call(
                [sys.executable, str(ROOT / "scripts" / "build_standalone.py"), "--skip-install"],
                cwd=ROOT,
            )
        if (bundle / "index.html").is_file():
            target = PAYLOAD / "backend" / "static"
            target.mkdir(parents=True, exist_ok=True)
            n = _copy_tree(bundle, target, exclude_dirs=PAYLOAD_EXCLUDES)
            print(f"[build-installer] payload frontend bundle: {n} files")

    total = sum(1 for _ in PAYLOAD.rglob("*") if _.is_file())
    print(f"[build-installer] payload TOTAL     : {total} files at {PAYLOAD}")
    return total


def run_makensis(*, version: str, output: Path) -> Path:
    makensis = _which("makensis")
    if not makensis:
        raise SystemExit(
            "[build-installer] `makensis` not on PATH. Install NSIS:\n"
            "    Linux: apt-get install nsis\n"
            "    macOS: brew install nsis\n"
            "    Windows: download from https://nsis.sourceforge.io"
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        makensis,
        f"-DAPP_VERSION={version}",
        f"-DSOURCE_ROOT={PAYLOAD}",
        f"-DOUTPUT_FILE={output}",
        "-V2",
        str(INSTALLER_NSI),
    ]
    print(f"[build-installer] $ {' '.join(cmd)}")
    r = subprocess.run(cmd)
    if r.returncode != 0:
        raise SystemExit(f"[build-installer] makensis failed (exit {r.returncode})")
    if not output.is_file():
        raise SystemExit(f"[build-installer] makensis exited 0 but {output} is missing")
    return output


def sign_executable(
    exe: Path,
    *,
    cert: Path,
    cert_password: str,
    timestamp_url: str,
    signer: str,
) -> None:
    """Authenticode-sign the .exe via osslsigncode (default) or signtool."""
    if signer == "osslsigncode":
        tool = _which("osslsigncode")
        if not tool:
            raise SystemExit("[build-installer] osslsigncode not on PATH")
        signed = exe.with_suffix(".signed.exe")
        cmd = [
            tool, "sign",
            "-pkcs12", str(cert),
            "-pass",   cert_password,
            "-n",      "BIG Hat Standalone",
            "-i",      "https://bighat.example",
            "-t",      timestamp_url,
            "-h",      "sha256",
            "-in",     str(exe),
            "-out",    str(signed),
        ]
        print("[build-installer] $ osslsigncode sign … (cert hidden)")
        r = subprocess.run(cmd)
        if r.returncode != 0:
            raise SystemExit(f"[build-installer] osslsigncode failed (exit {r.returncode})")
        signed.replace(exe)
        print(f"[build-installer] signed {exe}")
        # Verify
        v = subprocess.run(
            [tool, "verify", "-in", str(exe)],
            capture_output=True, text=True,
        )
        out = (v.stdout or "") + (v.stderr or "")
        if "Signature verification: ok" in out and "Number of verified signatures: 1" in out:
            print("[build-installer] verify OK (chain trusted)")
        elif "self-signed certificate" in out or "Verify error" in out:
            print("[build-installer] verify: signed correctly, but cert chain not trusted "
                  "(expected for self-signed dev certs)")
        else:
            tail = out.strip().splitlines()[-3:] if out.strip() else ["(no output)"]
            print("[build-installer] verify WARNING:")
            for line in tail:
                print(f"                   {line}")
    elif signer == "signtool":
        tool = _which("signtool") or _which("signtool.exe")
        if not tool:
            raise SystemExit("[build-installer] signtool not on PATH (Windows only)")
        cmd = [
            tool, "sign",
            "/f",  str(cert),
            "/p",  cert_password,
            "/fd", "sha256",
            "/tr", timestamp_url,
            "/td", "sha256",
            "/d",  "BIG Hat Standalone",
            "/du", "https://bighat.example",
            str(exe),
        ]
        print("[build-installer] $ signtool sign … (cert hidden)")
        r = subprocess.run(cmd)
        if r.returncode != 0:
            raise SystemExit(f"[build-installer] signtool failed (exit {r.returncode})")
        print(f"[build-installer] signed {exe}")
    else:
        raise SystemExit(f"[build-installer] unknown --signer: {signer}")


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser(description="Build the BIG Hat Standalone Windows installer")
    p.add_argument("--version", default=None, help="override VERSION.txt")
    p.add_argument("--python-dir", default=None, type=Path,
                   help="path to an embedded CPython tree to bundle as `python/`")
    p.add_argument("--output", default=None, type=Path,
                   help="explicit .exe path (default dist/BIGHatStandalone-Setup-<ver>.exe)")
    p.add_argument("--skip-frontend", action="store_true",
                   help="don't run scripts/build_standalone.py for the React bundle")
    p.add_argument("--no-embed-python", action="store_true",
                   help=f"skip downloading the embeddable CPython {EMBED_PYTHON_VERSION} runtime")
    p.add_argument("--skip-payload", action="store_true",
                   help="reuse an already-staged dist/payload tree")
    p.add_argument("--skip-makensis", action="store_true",
                   help="assemble payload + write metadata, but don't compile the .exe")
    # Signing
    p.add_argument("--cert", type=Path, default=os.environ.get("BIGHAT_SIGNING_CERT_PFX"),
                   help="path to .pfx code-signing certificate (also reads BIGHAT_SIGNING_CERT_PFX)")
    p.add_argument("--cert-password", default=os.environ.get("BIGHAT_SIGNING_PASSWORD"),
                   help="password for the .pfx (also reads BIGHAT_SIGNING_PASSWORD)")
    p.add_argument("--timestamp-url", default="http://timestamp.digicert.com",
                   help="Authenticode timestamp server")
    p.add_argument("--signer", choices=("osslsigncode", "signtool"), default="osslsigncode")
    p.add_argument("--no-sign", action="store_true",
                   help="explicitly skip signing (overrides --cert)")
    args = p.parse_args(argv if argv is not None else sys.argv[1:])

    version = _read_version(args.version)
    output = args.output or (DIST / f"BIGHatStandalone-Setup-{version}.exe")
    print(f"[build-installer] version: {version}")
    print(f"[build-installer] output : {output}")

    if not args.skip_payload:
        assemble_payload(
            python_dir=args.python_dir,
            skip_frontend=args.skip_frontend,
            embed_python=not args.no_embed_python,
        )
    else:
        print(f"[build-installer] reusing existing payload at {PAYLOAD}")

    if args.skip_makensis:
        print("[build-installer] --skip-makensis set; payload ready, exiting.")
        return 0

    exe = run_makensis(version=version, output=output)
    print(f"[build-installer] built {exe} ({exe.stat().st_size:,} bytes)")

    if args.no_sign:
        print("[build-installer] --no-sign set; skipping Authenticode signing.")
    elif args.cert:
        if not args.cert_password:
            raise SystemExit("[build-installer] --cert provided but no --cert-password / BIGHAT_SIGNING_PASSWORD")
        if not Path(args.cert).is_file():
            raise SystemExit(f"[build-installer] cert not found: {args.cert}")
        sign_executable(
            exe,
            cert=Path(args.cert),
            cert_password=args.cert_password,
            timestamp_url=args.timestamp_url,
            signer=args.signer,
        )
    else:
        print("[build-installer] no --cert provided; producing UNSIGNED installer.")
        print("                  Set BIGHAT_SIGNING_CERT_PFX + BIGHAT_SIGNING_PASSWORD on CI to enable signing.")

    print(f"[build-installer] DONE  -> {exe}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
