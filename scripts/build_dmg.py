#!/usr/bin/env python3
"""
BIG Hat Standalone V31 — macOS installer build orchestrator.

Mirrors `scripts/build_installer.py` for Windows. Produces:

    1. A self-contained `BIG Hat Standalone.app` bundle under `dist/macos/`
    2. A `.pkg` (component + product archive via pkgbuild + productbuild)
    3. A `.dmg` containing the .app, ready for distribution

Cross-platform parts (work on Linux/macOS):
  - .app bundle layout (Contents/MacOS, Contents/Resources)
  - Info.plist generation
  - Embedded relocatable CPython download (via python-build-standalone)
  - distribution.xml + postinstall script staging

macOS-only parts (auto-detected and gated):
  - pkgbuild + productbuild  → .pkg
  - hdiutil create           → .dmg
  - codesign                 → notarisation-ready signed .app/.pkg/.dmg
  - xcrun notarytool         → Apple notarisation (--notarize-profile)

Typical usage:
    # On a Linux dev box — produces .app + downloads runtime, stops before pkgbuild
    python scripts/build_dmg.py
    # On macOS CI — full pipeline
    python scripts/build_dmg.py \\
        --developer-id "Developer ID Application: BH Entertainment (TEAMID)" \\
        --installer-id "Developer ID Installer:    BH Entertainment (TEAMID)" \\
        --notarize-profile bighat
"""
from __future__ import annotations

import argparse
import hashlib
import logging
import os
import plistlib
import shutil
import stat
import subprocess
import sys
import tarfile
import urllib.request
from pathlib import Path

logger = logging.getLogger("build-dmg")

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
PACKAGING = ROOT / "packaging"
MACOS_PKG = PACKAGING / "macos"
DIST = ROOT / "dist"
MAC_DIST = DIST / "macos"
CACHE = DIST / ".cache"

APP_NAME = "BIG Hat Standalone"
APP_INTERNAL = "BIGHatStandalone"
APP_PUBLISHER = "BH Entertainment"
APP_BUNDLE_ID = "com.bhentertainment.bighatstandalone"

# Astral-managed python-build-standalone: relocatable CPython for macOS.
EMBED_PYTHON_VERSION = "3.11.9"
EMBED_PYTHON_RELEASE = "20240814"
EMBED_PYTHON_BASE_URL = (
    "https://github.com/astral-sh/python-build-standalone/releases/download/"
    f"{EMBED_PYTHON_RELEASE}"
)
# Per-arch artifact filenames; sha256 verified by fetching the .sha256 sidecar.
EMBED_ARCH_TO_TRIPLET = {
    "aarch64": "aarch64-apple-darwin",
    "x86_64":  "x86_64-apple-darwin",
}
# `pip download --platform <X>` tag for each arch — used to bake desktop
# wheels into the .app's site-packages without needing a macOS dev box.
EMBED_ARCH_TO_PIP_PLATFORMS = {
    # Apple Silicon: use macosx_11_0_arm64 wheels (and any earlier compatible).
    "aarch64": ["macosx_14_0_arm64", "macosx_13_0_arm64", "macosx_12_0_arm64", "macosx_11_0_arm64"],
    # Intel Macs: 10.9 baseline covers everything modern.
    "x86_64":  ["macosx_14_0_x86_64", "macosx_13_0_x86_64", "macosx_12_0_x86_64",
                "macosx_11_0_x86_64", "macosx_10_15_x86_64", "macosx_10_9_x86_64"],
}

PAYLOAD_EXCLUDES = {"__pycache__", "node_modules", ".pytest_cache", ".git", ".cache"}
PAYLOAD_EXCLUDE_NAMES = {"data", "tests", "test_reports"}


# ---------- file utilities (shared with build_installer.py philosophy) ----------
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
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file() and expected_sha256 and _sha256(dest) == expected_sha256:
        print(f"[build-dmg] cache hit: {dest.name}")
        return dest
    print(f"[build-dmg] downloading {url}")
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(url) as r, tmp.open("wb") as f:
        shutil.copyfileobj(r, f)
    if expected_sha256:
        got = _sha256(tmp)
        if got != expected_sha256:
            tmp.unlink(missing_ok=True)
            raise SystemExit(
                f"[build-dmg] sha256 mismatch for {url}\n"
                f"  expected {expected_sha256}\n  got      {got}"
            )
    tmp.replace(dest)
    return dest


def _read_version(explicit: str | None) -> str:
    if explicit:
        return explicit.strip().lstrip("vV ")
    p = BACKEND / "VERSION.txt"
    if not p.is_file():
        raise SystemExit(f"[build-dmg] {p} missing; pass --version explicitly")
    return p.read_text(encoding="utf-8").strip()


def _copy_tree(src: Path, dst: Path, *, exclude_dirs: set[str], exclude_names: set[str] = frozenset()) -> int:
    n = 0
    for root, dirs, files in os.walk(src):
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        rel = Path(root).relative_to(src)
        if rel.parts and rel.parts[0] in exclude_names:
            continue
        target_dir = dst / rel
        target_dir.mkdir(parents=True, exist_ok=True)
        for f in files:
            if f.endswith((".pyc", ".pyo")):
                continue
            # SECURITY: never ship `.env*` (production secrets) into the bundle.
            if f == ".env" or f.startswith(".env."):
                continue
            shutil.copy2(Path(root) / f, target_dir / f)
            n += 1
    return n


# ---------- embedded CPython for macOS ----------
def fetch_embeddable_python_macos(target: Path, *, arch: str) -> Path:
    """Download python-build-standalone for the requested arch and extract
    only the install_only/python/ subtree into `target`.

    Returns the directory containing bin/python3."""
    if (target / "bin" / "python3").exists():
        print(f"[build-dmg] embedded python already staged at {target}")
        return target

    triplet = EMBED_ARCH_TO_TRIPLET.get(arch)
    if not triplet:
        raise SystemExit(f"[build-dmg] unsupported --arch '{arch}'; pick one of {sorted(EMBED_ARCH_TO_TRIPLET)}")

    fname = f"cpython-{EMBED_PYTHON_VERSION}+{EMBED_PYTHON_RELEASE}-{triplet}-install_only.tar.gz"
    url = f"{EMBED_PYTHON_BASE_URL}/{fname}"
    sha_url = url + ".sha256"

    tarball = CACHE / fname
    sha_file = CACHE / (fname + ".sha256")
    _download(sha_url, sha_file)
    expected = sha_file.read_text(encoding="utf-8").split()[0].strip().lower()
    if len(expected) != 64:
        raise SystemExit(f"[build-dmg] cannot parse sha256 sidecar at {sha_url}")
    _download(url, tarball, expected_sha256=expected)

    _safe_rmtree(target)
    target.mkdir(parents=True, exist_ok=True)
    print(f"[build-dmg] extracting embedded Python -> {target}")
    with tarfile.open(tarball, "r:gz") as tf:
        # The archive layout is `python/bin/python3`, etc. Strip that one
        # leading `python/` component so target/bin/python3 ends up where
        # the launcher.sh expects.
        members = []
        for m in tf.getmembers():
            if m.name == "python" or m.name.startswith("python/"):
                m.name = m.name[len("python"):].lstrip("/")
                if m.name:  # skip the now-empty root entry
                    members.append(m)
        tf.extractall(target, members=members, filter="data")

    if not (target / "bin" / "python3").exists():
        raise SystemExit(f"[build-dmg] extraction did not produce bin/python3 under {target}")
    print(f"[build-dmg] embedded python {EMBED_PYTHON_VERSION} ({triplet}) staged")
    return target


def bake_desktop_wheels_macos(python_dir: Path, *, arch: str, requirements: Path) -> int:
    """Pre-install all desktop runtime wheels into the embedded macOS Python's
    `lib/python3.11/site-packages/` so the customer never needs internet on
    first launch.

    Like the Windows builder, we use cross-platform `pip install --target`
    against the macOS-specific wheel platform tags. The dev box can be Linux
    — pip resolves and downloads the macOS wheels, then copies their contents
    into the target directory. No execution of compiled Mac code happens
    locally.
    """
    if not requirements.is_file():
        raise SystemExit(f"[build-dmg] missing {requirements}")

    py_major_minor = "python" + ".".join(EMBED_PYTHON_VERSION.split(".")[:2])
    site_packages = python_dir / "lib" / py_major_minor / "site-packages"
    site_packages.mkdir(parents=True, exist_ok=True)

    marker = site_packages / ".bighat_wheels_baked"
    req_mtime = requirements.stat().st_mtime
    marker_value = f"{arch}:{req_mtime}"
    if marker.is_file() and marker.read_text().strip() == marker_value:
        n = sum(1 for _ in site_packages.rglob("*") if _.is_file())
        print(f"[build-dmg] wheels already baked for {arch} ({n} files); use --rebake to redo")
        return n

    # Wipe any prior arch's wheels — we mustn't mix archs in the same site-packages.
    for child in list(site_packages.iterdir()):
        if child.name.startswith(".") and child.name != ".bighat_wheels_baked":
            continue
        if child.name == ".bighat_wheels_baked":
            continue
        if child.is_dir():
            shutil.rmtree(child, ignore_errors=True)
        else:
            child.unlink()

    print(f"[build-dmg] baking macOS {arch} wheels into {site_packages}")
    platform_args: list[str] = []
    for tag in EMBED_ARCH_TO_PIP_PLATFORMS[arch]:
        platform_args += ["--platform", tag]

    cmd = [
        sys.executable, "-m", "pip", "install",
        "--target", str(site_packages),
        *platform_args,
        "--python-version", "3.11",
        "--implementation", "cp",
        "--abi", "cp311",
        "--only-binary=:all:",
        "--no-compile",
        "--upgrade",
        "-r", str(requirements),
    ]
    print(f"[build-dmg] $ {' '.join(cmd)}")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.stdout.write(r.stdout)
        sys.stderr.write(r.stderr)
        raise SystemExit(
            f"[build-dmg] pip install --target failed (exit {r.returncode}). "
            f"Common cause: a transitive dep missing a {arch} cp311 wheel — "
            f"pin a different version in backend/requirements-desktop.txt."
        )
    tail = "\n".join((r.stdout or "").splitlines()[-3:])
    if tail:
        print(tail)
    marker.write_text(marker_value, encoding="utf-8")
    n = sum(1 for _ in site_packages.rglob("*") if _.is_file())
    print(f"[build-dmg] baked {n} files into {site_packages.relative_to(python_dir)}")
    return n


# ---------- .app bundle ----------
def render_template(src: Path, dst: Path, mapping: dict[str, str]) -> None:
    text = src.read_text(encoding="utf-8")
    for k, v in mapping.items():
        text = text.replace(f"@{k}@", v)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(text, encoding="utf-8")


def assemble_app_bundle(
    *,
    version: str,
    arch: str,
    embed_python: bool,
    skip_frontend: bool,
) -> Path:
    """Build the .app bundle tree under MAC_DIST/<APP_NAME>.app/."""
    _safe_rmtree(MAC_DIST)
    MAC_DIST.mkdir(parents=True, exist_ok=True)

    app = MAC_DIST / f"{APP_NAME}.app"
    contents = app / "Contents"
    macos_dir = contents / "MacOS"
    res = contents / "Resources"
    macos_dir.mkdir(parents=True, exist_ok=True)
    res.mkdir(parents=True, exist_ok=True)

    # 1. Info.plist
    render_template(
        MACOS_PKG / "Info.plist.in",
        contents / "Info.plist",
        {
            "APP_NAME":        APP_NAME,
            "APP_INTERNAL":    APP_INTERNAL,
            "APP_VERSION":     version,
            "APP_BUNDLE_ID":   APP_BUNDLE_ID,
            "APP_PUBLISHER":   APP_PUBLISHER,
        },
    )
    # Validate plist parses (catches typos in the template).
    with (contents / "Info.plist").open("rb") as f:
        plistlib.load(f)
    print(f"[build-dmg] Info.plist written ({(contents / 'Info.plist').stat().st_size} bytes)")

    # 2. PkgInfo (legacy 4-byte type + 4-byte signature, padded with NUL)
    (contents / "PkgInfo").write_bytes(b"APPLBHat")

    # 3. MacOS/<APP_INTERNAL>  ← shell launcher, +x
    launcher = macos_dir / APP_INTERNAL
    shutil.copy2(MACOS_PKG / "launcher.sh", launcher)
    launcher.chmod(launcher.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    # 4. Resources/backend/, Resources/packaging/
    n = _copy_tree(BACKEND, res / "backend",
                   exclude_dirs=PAYLOAD_EXCLUDES,
                   exclude_names=PAYLOAD_EXCLUDE_NAMES)
    print(f"[build-dmg] resources backend/  : {n} files")
    n = _copy_tree(PACKAGING, res / "packaging",
                   exclude_dirs=PAYLOAD_EXCLUDES,
                   exclude_names={"installer", "macos"})
    print(f"[build-dmg] resources packaging/: {n} files")

    # 5. VERSION.txt at the bundle Resources root
    (res / "VERSION.txt").write_text(version + "\n", encoding="utf-8")

    # SECURITY: ship the desktop-safe `.env.standalone` template; the launcher
    # generates the per-install `.env` (with a unique JWT_SECRET) on first run.
    env_template_src = PACKAGING / ".env.standalone"
    if env_template_src.is_file():
        shutil.copy2(env_template_src, res / "backend" / ".env.standalone")
        print("[build-dmg] resources .env.standalone shipped (desktop-safe template)")

    # 6. Frontend bundle (already lives at backend/static/, copied as part of backend/)
    if not skip_frontend and not (res / "backend" / "static" / "index.html").is_file():
        print("[build-dmg] frontend bundle missing — running scripts/build_standalone.py")
        subprocess.check_call(
            [sys.executable, str(ROOT / "scripts" / "build_standalone.py"), "--skip-install"],
            cwd=ROOT,
        )
        bundle = BACKEND / "static"
        if (bundle / "index.html").is_file():
            target = res / "backend" / "static"
            target.mkdir(parents=True, exist_ok=True)
            n = _copy_tree(bundle, target, exclude_dirs=PAYLOAD_EXCLUDES)
            print(f"[build-dmg] resources frontend bundle: {n} files")

    # 7. Embedded Python under Resources/python/
    if embed_python:
        fetch_embeddable_python_macos(res / "python", arch=arch)
        # Bake desktop runtime wheels (uvicorn, fastapi, pydantic, …) into the
        # embed so first launch never needs internet or pip.
        desktop_reqs = BACKEND / "requirements-desktop.txt"
        if desktop_reqs.is_file():
            bake_desktop_wheels_macos(res / "python", arch=arch, requirements=desktop_reqs)
        else:
            print(f"[build-dmg] WARNING: {desktop_reqs} missing — .app will be missing all third-party deps")
        n = sum(1 for _ in (res / "python").rglob("*") if _.is_file())
        print(f"[build-dmg] resources python/   : {n} files (embeddable {EMBED_PYTHON_VERSION} {arch})")
    else:
        print("[build-dmg] resources python/   : SKIPPED (--no-embed-python). "
              "App will require system Python 3.11+ at /usr/bin/python3.")

    total = sum(1 for _ in app.rglob("*") if _.is_file())
    print(f"[build-dmg] .app TOTAL          : {total} files at {app}")
    return app


# ---------- pkgbuild + productbuild (macOS only) ----------
def run_pkgbuild_productbuild(
    *,
    app: Path,
    version: str,
    arch: str,
    installer_identity: str | None,
) -> Path:
    pkgbuild = _which("pkgbuild")
    productbuild = _which("productbuild")
    if not (pkgbuild and productbuild):
        raise SystemExit(
            "[build-dmg] pkgbuild/productbuild not on PATH (macOS only).\n"
            "            Run this on a macOS host or in macOS CI."
        )

    component_pkg = MAC_DIST / f"{APP_INTERNAL}-component.pkg"
    product_pkg = DIST / f"BIGHatStandalone-{version}.pkg"
    scripts_dir = MAC_DIST / "scripts"
    _safe_rmtree(scripts_dir)
    scripts_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(MACOS_PKG / "postinstall", scripts_dir / "postinstall")
    (scripts_dir / "postinstall").chmod(0o755)

    cmd = [
        pkgbuild,
        "--component", str(app),
        "--install-location", "/Applications",
        "--scripts", str(scripts_dir),
        "--identifier", APP_BUNDLE_ID,
        "--version", version,
        str(component_pkg),
    ]
    print(f"[build-dmg] $ {' '.join(cmd)}")
    subprocess.check_call(cmd)

    distribution = MAC_DIST / "distribution.xml"
    arch_hosts = {"aarch64": "arm64", "x86_64": "x86_64"}.get(arch, "arm64")
    render_template(
        MACOS_PKG / "distribution.xml.in",
        distribution,
        {
            "APP_NAME":        APP_NAME,
            "APP_INTERNAL":    APP_INTERNAL,
            "APP_VERSION":     version,
            "APP_BUNDLE_ID":   APP_BUNDLE_ID,
            "APP_ARCH_HOSTS":  arch_hosts,
        },
    )

    cmd = [
        productbuild,
        "--distribution", str(distribution),
        "--package-path",  str(MAC_DIST),
        "--version", version,
    ]
    if installer_identity:
        cmd += ["--sign", installer_identity]
    cmd.append(str(product_pkg))
    print(f"[build-dmg] $ {' '.join(cmd)}")
    subprocess.check_call(cmd)

    print(f"[build-dmg] built {product_pkg} ({product_pkg.stat().st_size:,} bytes)")
    return product_pkg


# ---------- hdiutil .dmg (macOS only) ----------
def build_dmg(*, app: Path, version: str) -> Path:
    hdiutil = _which("hdiutil")
    if not hdiutil:
        raise SystemExit(
            "[build-dmg] hdiutil not on PATH (macOS only).\n"
            "            Run this on a macOS host or in macOS CI."
        )
    dmg = DIST / f"BIGHatStandalone-{version}.dmg"
    if dmg.exists():
        dmg.unlink()
    # Stage a folder with the .app + a /Applications symlink for drag-to-install UX.
    stage = MAC_DIST / "dmg-stage"
    _safe_rmtree(stage)
    stage.mkdir(parents=True, exist_ok=True)
    # Symlink to /Applications
    (stage / "Applications").symlink_to("/Applications")
    # Reference (not copy) the .app via -srcfolder; hdiutil will combine.
    cmd = [
        hdiutil, "create",
        "-volname",   APP_NAME,
        "-srcfolder", str(stage),
        "-srcfolder", str(app),
        "-format",    "UDZO",
        "-fs",        "HFS+",
        "-imagekey",  "zlib-level=9",
        "-quiet",
        str(dmg),
    ]
    print(f"[build-dmg] $ {' '.join(cmd)}")
    subprocess.check_call(cmd)
    print(f"[build-dmg] built {dmg} ({dmg.stat().st_size:,} bytes)")
    return dmg


# ---------- codesign + notarise (macOS only) ----------
def codesign_app(*, app: Path, identity: str, entitlements: Path | None = None) -> None:
    codesign = _which("codesign")
    if not codesign:
        raise SystemExit("[build-dmg] codesign not on PATH (macOS only)")
    cmd = [
        codesign, "--force", "--deep", "--options", "runtime",
        "--timestamp", "--sign", identity,
    ]
    if entitlements:
        cmd += ["--entitlements", str(entitlements)]
    cmd.append(str(app))
    print(f"[build-dmg] $ codesign … {app.name}")
    subprocess.check_call(cmd)
    # Verify
    subprocess.check_call([codesign, "--verify", "--deep", "--strict", "--verbose=2", str(app)])
    print("[build-dmg] codesign verify OK")


def notarize(*, artifact: Path, profile: str) -> None:
    xcrun = _which("xcrun")
    if not xcrun:
        raise SystemExit("[build-dmg] xcrun not on PATH (macOS only)")
    cmd = [
        xcrun, "notarytool", "submit", str(artifact),
        "--keychain-profile", profile,
        "--wait",
    ]
    print("[build-dmg] $ xcrun notarytool submit … --wait")
    subprocess.check_call(cmd)
    # Staple the notarisation ticket so Gatekeeper accepts the artifact offline.
    subprocess.check_call([xcrun, "stapler", "staple", str(artifact)])
    print(f"[build-dmg] notarized + stapled {artifact.name}")


# ---------- main ----------
def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser(description="Build the BIG Hat Standalone macOS .app/.pkg/.dmg")
    p.add_argument("--version", default=None, help="override VERSION.txt")
    p.add_argument("--arch", default="aarch64", choices=sorted(EMBED_ARCH_TO_TRIPLET),
                   help="target macOS architecture (default aarch64 = Apple Silicon)")
    p.add_argument("--no-embed-python", action="store_true",
                   help="skip downloading the embedded CPython runtime")
    p.add_argument("--skip-frontend", action="store_true",
                   help="don't run scripts/build_standalone.py for the React bundle")
    p.add_argument("--skip-pkg", action="store_true",
                   help="don't run pkgbuild/productbuild (still builds the .app)")
    p.add_argument("--skip-dmg", action="store_true",
                   help="don't run hdiutil (still builds the .app and .pkg)")
    # Signing / notarisation
    p.add_argument("--developer-id", default=os.environ.get("BIGHAT_MACOS_DEVELOPER_ID"),
                   help="codesign identity for the .app (Developer ID Application)")
    p.add_argument("--installer-id", default=os.environ.get("BIGHAT_MACOS_INSTALLER_ID"),
                   help="productbuild identity for the .pkg (Developer ID Installer)")
    p.add_argument("--notarize-profile", default=os.environ.get("BIGHAT_MACOS_NOTARIZE_PROFILE"),
                   help="`xcrun notarytool` keychain profile name; if set, .pkg + .dmg get notarised")
    p.add_argument("--entitlements", default=None, type=Path,
                   help="optional entitlements .plist for codesign")
    args = p.parse_args(argv if argv is not None else sys.argv[1:])

    version = _read_version(args.version)
    print(f"[build-dmg] version : {version}")
    print(f"[build-dmg] arch    : {args.arch}")
    print(f"[build-dmg] sysname : {sys.platform}")

    # ---- 1. .app bundle (always works on Linux/macOS) ----
    app = assemble_app_bundle(
        version=version,
        arch=args.arch,
        embed_python=not args.no_embed_python,
        skip_frontend=args.skip_frontend,
    )

    # ---- 2. codesign .app (macOS only) ----
    if args.developer_id:
        if sys.platform != "darwin":
            print("[build-dmg] --developer-id ignored (codesign only runs on macOS)")
        else:
            codesign_app(app=app, identity=args.developer_id, entitlements=args.entitlements)

    # ---- 3. pkgbuild + productbuild (macOS only) ----
    pkg: Path | None = None
    if args.skip_pkg:
        print("[build-dmg] --skip-pkg set; not building .pkg")
    elif sys.platform != "darwin":
        print(f"[build-dmg] skipping pkgbuild/productbuild (sys.platform={sys.platform}); "
              "run on a macOS host to produce the .pkg")
    else:
        pkg = run_pkgbuild_productbuild(
            app=app, version=version, arch=args.arch,
            installer_identity=args.installer_id,
        )
        if args.notarize_profile and pkg:
            notarize(artifact=pkg, profile=args.notarize_profile)

    # ---- 4. .dmg (macOS only) ----
    dmg: Path | None = None
    if args.skip_dmg:
        print("[build-dmg] --skip-dmg set; not building .dmg")
    elif sys.platform != "darwin":
        print(f"[build-dmg] skipping hdiutil (sys.platform={sys.platform}); "
              "run on a macOS host to produce the .dmg")
    else:
        dmg = build_dmg(app=app, version=version)
        if args.notarize_profile and dmg:
            notarize(artifact=dmg, profile=args.notarize_profile)

    print("[build-dmg] DONE")
    print(f"           .app : {app}")
    if pkg:
        print(f"           .pkg : {pkg}")
    if dmg:
        print(f"           .dmg : {dmg}")
    if not pkg and not dmg and sys.platform != "darwin":
        print("           (.pkg/.dmg deferred to macOS CI — .app bundle is ready to upload)")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
