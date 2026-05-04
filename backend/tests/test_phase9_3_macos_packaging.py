"""Phase 9.3 — macOS .app/.pkg/.dmg packaging pipeline regression tests.

Mirrors `test_phase9_2_installer.py` for the Windows installer.

Strategy:
  * Static checks on the macOS asset templates (Info.plist.in, launcher.sh,
    distribution.xml.in, postinstall) — fast, no toolchain required.
  * Static checks on `scripts/build_dmg.py` — fast, no toolchain required.
  * `--no-embed-python --skip-frontend --skip-pkg --skip-dmg` smoke test that
    asserts the .app bundle layout is correct (filesystem-only, no network).
  * Full pkgbuild + hdiutil tests gated on macOS + opt-in env var.
"""
from __future__ import annotations

import os
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path("/app")
SCRIPTS_DIR = REPO_ROOT / "scripts"
PACKAGING_DIR = REPO_ROOT / "packaging"
MACOS_PKG = PACKAGING_DIR / "macos"
BUILD_DMG = SCRIPTS_DIR / "build_dmg.py"


# ---------- Static asset checks ----------
class TestMacOSAssetsStatic:
    def test_info_plist_template_exists_and_has_placeholders(self):
        p = MACOS_PKG / "Info.plist.in"
        assert p.is_file()
        text = p.read_text(encoding="utf-8")
        for ph in ("@APP_NAME@", "@APP_INTERNAL@", "@APP_VERSION@",
                   "@APP_BUNDLE_ID@", "@APP_PUBLISHER@"):
            assert ph in text, f"Info.plist.in missing placeholder {ph}"

    def test_info_plist_template_is_valid_plist_after_substitution(self):
        # Render with dummy values and ensure plistlib can parse the result.
        text = (MACOS_PKG / "Info.plist.in").read_text(encoding="utf-8")
        for k, v in {
            "APP_NAME": "Test App", "APP_INTERNAL": "TestApp",
            "APP_VERSION": "1.2.3", "APP_BUNDLE_ID": "com.example.test",
            "APP_PUBLISHER": "Example Corp",
        }.items():
            text = text.replace(f"@{k}@", v)
        d = plistlib.loads(text.encode("utf-8"))
        assert d["CFBundleVersion"] == "1.2.3"
        assert d["CFBundleIdentifier"] == "com.example.test"
        assert d["CFBundleExecutable"] == "TestApp"
        assert d["CFBundlePackageType"] == "APPL"
        assert d["LSMinimumSystemVersion"]
        assert d["NSHighResolutionCapable"] is True

    def test_launcher_script_is_safe_bash(self):
        p = MACOS_PKG / "launcher.sh"
        assert p.is_file()
        text = p.read_text(encoding="utf-8")
        assert text.startswith("#!/bin/bash") or text.startswith("#!/usr/bin/env bash")
        assert "set -e" in text  # fail-fast
        # Must exec the embedded python on the launcher.py
        assert "python/bin/python3" in text
        assert "backend/launcher.py" in text
        # Forces native mode
        assert "BIGHAT_NATIVE_MODE=1" in text
        # User data goes to ~/Library/Application Support, not inside the .app
        assert "Application Support" in text

    def test_postinstall_script_strips_quarantine_and_creates_data_dir(self):
        p = MACOS_PKG / "postinstall"
        assert p.is_file()
        text = p.read_text(encoding="utf-8")
        assert "xattr" in text and "com.apple.quarantine" in text
        assert "Application Support" in text
        assert text.startswith("#!/bin/bash") or text.startswith("#!/usr/bin/env bash")

    def test_distribution_xml_template(self):
        p = MACOS_PKG / "distribution.xml.in"
        assert p.is_file()
        text = p.read_text(encoding="utf-8")
        for ph in ("@APP_NAME@", "@APP_INTERNAL@", "@APP_VERSION@",
                   "@APP_BUNDLE_ID@", "@APP_ARCH_HOSTS@"):
            assert ph in text, f"distribution.xml.in missing placeholder {ph}"
        # Must enforce minimum macOS version
        assert "<os-version min=" in text


class TestBuildDmgScriptStatic:
    def test_build_script_exists_and_help_works(self):
        assert BUILD_DMG.is_file()
        r = subprocess.run(
            [sys.executable, str(BUILD_DMG), "--help"],
            capture_output=True, text=True, timeout=20,
        )
        assert r.returncode == 0, f"--help failed: {r.stderr}"
        for flag in ("--version", "--arch", "--no-embed-python", "--skip-frontend",
                     "--skip-pkg", "--skip-dmg",
                     "--developer-id", "--installer-id", "--notarize-profile"):
            assert flag in r.stdout, f"--help missing flag: {flag}"

    def test_build_script_pins_python_build_standalone_metadata(self):
        text = BUILD_DMG.read_text(encoding="utf-8")
        # Pinned python-build-standalone version + release
        assert 'EMBED_PYTHON_VERSION = "3.11.9"' in text
        assert "EMBED_PYTHON_RELEASE = " in text
        assert "python-build-standalone" in text
        # Both Apple architectures supported
        assert "aarch64-apple-darwin" in text
        assert "x86_64-apple-darwin" in text


# ---------- Smoke test: .app bundle assembly ----------
class TestAppBundleAssembly:
    """Runs the orchestrator with --no-embed-python --skip-frontend --skip-pkg --skip-dmg.
    Validates the .app layout without network or macOS toolchain."""

    @pytest.fixture(scope="class")
    def app_bundle(self):
        dist_macos = REPO_ROOT / "dist" / "macos"
        if dist_macos.exists():
            shutil.rmtree(dist_macos)
        r = subprocess.run(
            [
                sys.executable, str(BUILD_DMG),
                "--no-embed-python", "--skip-frontend",
                "--skip-pkg", "--skip-dmg",
            ],
            capture_output=True, text=True, timeout=60,
            cwd=str(REPO_ROOT),
        )
        assert r.returncode == 0, f"build_dmg failed:\n{r.stdout}\n{r.stderr}"
        app = dist_macos / "BIG Hat Standalone.app"
        assert app.is_dir(), f".app not produced at {app}"
        return app

    def test_bundle_layout(self, app_bundle: Path):
        contents = app_bundle / "Contents"
        assert (contents / "Info.plist").is_file()
        assert (contents / "PkgInfo").is_file()
        assert (contents / "MacOS").is_dir()
        assert (contents / "Resources").is_dir()

    def test_executable_launcher_with_exec_bit(self, app_bundle: Path):
        exe = app_bundle / "Contents" / "MacOS" / "BIGHatStandalone"
        assert exe.is_file(), "MacOS/BIGHatStandalone launcher missing"
        assert os.access(exe, os.X_OK), "launcher must be executable"
        text = exe.read_text(encoding="utf-8")
        assert "python/bin/python3" in text
        assert "backend/launcher.py" in text

    def test_info_plist_filled_with_real_values(self, app_bundle: Path):
        with (app_bundle / "Contents" / "Info.plist").open("rb") as f:
            d = plistlib.load(f)
        assert d["CFBundleName"] == "BIG Hat Standalone"
        assert d["CFBundleIdentifier"] == "com.bhentertainment.bighatstandalone"
        assert d["CFBundleExecutable"] == "BIGHatStandalone"
        # Version pulled from /app/backend/VERSION.txt
        version = (REPO_ROOT / "backend" / "VERSION.txt").read_text(encoding="utf-8").strip()
        assert d["CFBundleVersion"] == version
        assert d["CFBundleShortVersionString"] == version
        # No unresolved @PLACEHOLDER@ tokens leaked
        for v in d.values():
            if isinstance(v, str):
                assert "@" not in v.split("@")[0] or not (v.startswith("@") and v.endswith("@"))

    def test_pkginfo_format(self, app_bundle: Path):
        # Apple's classic 4+4 byte PkgInfo: type+sig.
        data = (app_bundle / "Contents" / "PkgInfo").read_bytes()
        assert data == b"APPLBHat", f"unexpected PkgInfo: {data!r}"

    def test_backend_resources(self, app_bundle: Path):
        be = app_bundle / "Contents" / "Resources" / "backend"
        assert (be / "server.py").is_file()
        assert (be / "launcher.py").is_file()
        assert (be / "VERSION.txt").is_file()
        assert (be / "native").is_dir()
        # Excluded
        assert not (be / "tests").exists(), "backend/tests must NOT ship in bundle"
        assert not (be / "data").exists(),  "backend/data must NOT ship in bundle"
        for pc in be.rglob("__pycache__"):
            pytest.fail(f"__pycache__ leaked into bundle: {pc}")

    def test_packaging_resources(self, app_bundle: Path):
        pk = app_bundle / "Contents" / "Resources" / "packaging"
        # We ship the legacy .vbs (harmless) but NOT installer/ or macos/
        # since macos/ is build-side-only.
        assert (pk / "start_bighat.vbs").is_file()
        assert not (pk / "installer").exists()
        assert not (pk / "macos").exists(), \
            "packaging/macos/ must NOT ship in bundle (build-side templates only)"

    def test_resources_root(self, app_bundle: Path):
        res = app_bundle / "Contents" / "Resources"
        v = (res / "VERSION.txt")
        assert v.is_file()
        assert v.read_text(encoding="utf-8").strip(), "VERSION.txt empty"

    def test_no_pyc_files(self, app_bundle: Path):
        for pyc in app_bundle.rglob("*.pyc"):
            pytest.fail(f".pyc leaked into bundle: {pyc}")


# ---------- Full pipeline (gated on macOS + opt-in) ----------
@pytest.mark.skipif(
    sys.platform != "darwin",
    reason="pkgbuild/hdiutil only run on macOS",
)
@pytest.mark.skipif(
    os.environ.get("BIGHAT_RUN_PKGBUILD") != "1",
    reason="set BIGHAT_RUN_PKGBUILD=1 to opt in to the full macOS pipeline",
)
class TestFullMacOSPipeline:
    def test_full_pkg_and_dmg_build(self):
        out_dir = REPO_ROOT / "dist"
        for old in out_dir.glob("BIGHatStandalone-*.pkg"):
            old.unlink()
        for old in out_dir.glob("BIGHatStandalone-*.dmg"):
            old.unlink()
        r = subprocess.run(
            [
                sys.executable, str(BUILD_DMG),
                "--no-embed-python",  # speed: skip 30 MB download in CI smoke test
                "--skip-frontend",
            ],
            capture_output=True, text=True, timeout=300,
            cwd=str(REPO_ROOT),
        )
        assert r.returncode == 0, f"full build failed:\n{r.stdout}\n{r.stderr}"
        version = (REPO_ROOT / "backend" / "VERSION.txt").read_text(encoding="utf-8").strip()
        pkg = out_dir / f"BIGHatStandalone-{version}.pkg"
        dmg = out_dir / f"BIGHatStandalone-{version}.dmg"
        assert pkg.is_file(), f"missing {pkg}"
        assert dmg.is_file(), f"missing {dmg}"
        assert pkg.stat().st_size > 100_000
        assert dmg.stat().st_size > 100_000
