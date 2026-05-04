"""Phase 9.2 — Windows NSIS installer build pipeline regression tests.

These tests verify the `scripts/build_installer.py` orchestrator and the
`packaging/installer/bighat-installer.nsi` config without a full end-to-end
network build (which downloads a ~10MB CPython embeddable + runs makensis).

Strategy:
  * Static checks on the NSI script (presence of required defines, sections,
    upgrade/migrate flow, uninstall flow) — fast, no toolchain required.
  * Static checks on the build script (CLI flags, helpers, sha256 pinning) —
    fast, no toolchain required.
  * `--skip-makensis --skip-frontend --no-embed-python` smoke test that
    asserts payload assembly works (filesystem-only, no network, no NSIS).
  * Full `makensis` compile test, gated on `nsis` being installed AND env
    `BIGHAT_RUN_MAKENSIS=1` (so CI without NSIS doesn't fail).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path("/app")
SCRIPTS_DIR = REPO_ROOT / "scripts"
PACKAGING_DIR = REPO_ROOT / "packaging"
BUILD_INSTALLER = SCRIPTS_DIR / "build_installer.py"
NSI = PACKAGING_DIR / "installer" / "bighat-installer.nsi"


# ---------- Static config checks ----------
class TestNsiScriptStatic:
    def test_nsi_file_exists(self):
        assert NSI.is_file(), f"missing NSIS config: {NSI}"

    def test_nsi_has_required_defines(self):
        text = NSI.read_text(encoding="utf-8")
        for token in ("APP_VERSION", "SOURCE_ROOT", "OUTPUT_FILE"):
            assert f"!ifndef {token}" in text, f"NSI missing defensive !ifndef for {token}"
            assert f"-D{token}=" in text or token in text, f"NSI missing reference to {token}"

    def test_nsi_has_required_sections(self):
        text = NSI.read_text(encoding="utf-8")
        for section in (
            "Section \"Core (required)\"",
            "Section \"Desktop shortcut\"",
            "Section \"Start Menu shortcut\"",
            "Section /o \"Auto-start at login\"",
            "Section \"Uninstall\"",
        ):
            assert section in text, f"NSI missing section: {section}"

    def test_nsi_has_components_page_for_descriptions(self):
        # Required for MUI_DESCRIPTION_TEXT macros to resolve cleanly (no warnings).
        text = NSI.read_text(encoding="utf-8")
        assert "MUI_PAGE_COMPONENTS" in text, (
            "MUI_PAGE_COMPONENTS missing — section descriptions will warn at compile time"
        )

    def test_nsi_has_upgrade_migrate_flow(self):
        text = NSI.read_text(encoding="utf-8")
        # Reads previous install dir and migrates user data\
        assert "PreviousInstallDir" in text
        assert "Migrating user data" in text
        assert "backend\\data" in text

    def test_nsi_has_uninstaller_with_data_preservation(self):
        text = NSI.read_text(encoding="utf-8")
        assert 'WriteUninstaller "$INSTDIR\\Uninstall.exe"' in text
        assert "User data under" in text  # detail-print preservation notice
        # We must NOT recursively rmdir the data folder.
        assert 'RMDir /r "$INSTDIR\\backend\\data"' not in text, (
            "Uninstaller must NOT delete user data under backend\\data"
        )

    def test_nsi_writes_uninstall_registry_keys(self):
        text = NSI.read_text(encoding="utf-8")
        for key in ("DisplayName", "DisplayVersion", "Publisher",
                    "InstallLocation", "UninstallString", "EstimatedSize"):
            assert f'"{key}"' in text, f"Uninstall registry missing {key}"

    def test_nsi_versioninfo_metadata(self):
        text = NSI.read_text(encoding="utf-8")
        for key in ("ProductName", "CompanyName", "FileDescription",
                    "FileVersion", "ProductVersion"):
            assert f'"{key}"' in text


class TestBuildInstallerScriptStatic:
    def test_build_script_exists_and_is_executable_python(self):
        assert BUILD_INSTALLER.is_file()
        # Should at least parse (--help) without errors.
        r = subprocess.run(
            [sys.executable, str(BUILD_INSTALLER), "--help"],
            capture_output=True, text=True, timeout=20,
        )
        assert r.returncode == 0, f"--help failed: {r.stderr}"
        for flag in ("--version", "--python-dir", "--skip-frontend",
                     "--no-embed-python", "--skip-payload", "--skip-makensis",
                     "--cert", "--cert-password", "--no-sign", "--signer"):
            assert flag in r.stdout, f"--help missing flag: {flag}"

    def test_pinned_python_embeddable_metadata(self):
        # The build script MUST pin both URL and sha256 so builds are reproducible.
        text = BUILD_INSTALLER.read_text(encoding="utf-8")
        assert 'EMBED_PYTHON_VERSION = "3.11.9"' in text
        assert 'python-{EMBED_PYTHON_VERSION}-embed-amd64.zip' in text
        # 64 hex chars
        import re
        m = re.search(r'EMBED_PYTHON_SHA256 = "([0-9a-f]{64})"', text)
        assert m, "EMBED_PYTHON_SHA256 must be a pinned 64-char hex sha256"


# ---------- Smoke test: payload assembly only ----------
class TestPayloadAssembly:
    """Runs the orchestrator with --skip-makensis --no-embed-python --skip-frontend.
    Verifies file layout without the network / NSIS toolchain."""

    @pytest.fixture(scope="class")
    def assembled(self, tmp_path_factory):
        # Use the real /app/dist/payload (script doesn't accept an override),
        # but clean it up so we don't pollute prior state.
        dist = REPO_ROOT / "dist"
        payload = dist / "payload"
        if payload.exists():
            shutil.rmtree(payload)
        r = subprocess.run(
            [
                sys.executable, str(BUILD_INSTALLER),
                "--skip-makensis", "--skip-frontend", "--no-embed-python",
                "--no-sign",
            ],
            capture_output=True, text=True, timeout=60,
            cwd=str(REPO_ROOT),
        )
        assert r.returncode == 0, f"payload assembly failed:\n{r.stdout}\n{r.stderr}"
        return payload

    def test_payload_root_files(self, assembled: Path):
        assert (assembled / "VERSION.txt").is_file()
        assert (assembled / "VERSION.txt").read_text().strip()  # non-empty

    def test_payload_backend_tree(self, assembled: Path):
        be = assembled / "backend"
        assert (be / "server.py").is_file()
        assert (be / "launcher.py").is_file()
        assert (be / "VERSION.txt").is_file()
        assert (be / "native").is_dir()
        # Excluded
        assert not (be / "tests").exists(), "tests/ must NOT ship in payload"
        assert not (be / "data").exists(), "data/ must NOT ship in payload"
        # No __pycache__ leakage
        for pc in be.rglob("__pycache__"):
            pytest.fail(f"__pycache__ leaked into payload: {pc}")

    def test_payload_packaging_tree(self, assembled: Path):
        pk = assembled / "packaging"
        assert (pk / "start_bighat.vbs").is_file()
        assert (pk / "install_shortcut.vbs").is_file()
        # The installer/ subdir is excluded (we don't ship the .nsi).
        assert not (pk / "installer").exists(), \
            "packaging/installer/ must NOT ship in payload"

    def test_payload_no_pyc_files(self, assembled: Path):
        for pyc in assembled.rglob("*.pyc"):
            pytest.fail(f"compiled .pyc leaked: {pyc}")


# ---------- Optional full makensis compile (gated) ----------
@pytest.mark.skipif(
    not shutil.which("makensis"),
    reason="makensis not installed",
)
@pytest.mark.skipif(
    os.environ.get("BIGHAT_RUN_MAKENSIS") != "1",
    reason="set BIGHAT_RUN_MAKENSIS=1 to opt in to the full installer compile",
)
class TestMakensisCompile:
    def test_unsigned_installer_compiles(self):
        out = REPO_ROOT / "dist" / "BIGHatStandalone-Setup-test.exe"
        if out.exists():
            out.unlink()
        # Skip frontend (already built) and python embed (network) for speed.
        # We rely on --skip-payload reusing the assembled tree from the test above
        # if it ran, otherwise we assemble fresh without the python runtime.
        r = subprocess.run(
            [
                sys.executable, str(BUILD_INSTALLER),
                "--skip-frontend", "--no-embed-python", "--no-sign",
                "--output", str(out),
            ],
            capture_output=True, text=True, timeout=180,
            cwd=str(REPO_ROOT),
        )
        assert r.returncode == 0, f"makensis build failed:\n{r.stdout}\n{r.stderr}"
        assert out.is_file(), f"installer not produced at {out}"
        # Sanity: NSIS PE installers are at least a couple MB.
        assert out.stat().st_size > 500_000, "installer suspiciously small"
        # No warnings should appear in compile output.
        assert "warning" not in r.stdout.lower(), (
            f"makensis emitted warnings:\n{r.stdout}"
        )


@pytest.mark.skipif(
    not (shutil.which("osslsigncode") and shutil.which("openssl")),
    reason="osslsigncode or openssl not installed",
)
@pytest.mark.skipif(
    os.environ.get("BIGHAT_RUN_MAKENSIS") != "1",
    reason="set BIGHAT_RUN_MAKENSIS=1 to opt in to the full signing test",
)
class TestSigningPipeline:
    def test_self_signed_signing_pipeline(self, tmp_path: Path):
        """End-to-end: build -> sign with self-signed PFX -> osslsigncode reports
        the file is signed (chain validation will fail on self-signed, that's OK)."""
        # 1. Generate self-signed PFX.
        key = tmp_path / "test.key"
        crt = tmp_path / "test.crt"
        pfx = tmp_path / "test.pfx"
        subprocess.check_call([
            "openssl", "req", "-x509", "-newkey", "rsa:2048",
            "-keyout", str(key), "-out", str(crt),
            "-days", "1", "-nodes",
            "-subj", "/CN=BIGHat Test/O=BH Entertainment",
        ], stderr=subprocess.DEVNULL)
        subprocess.check_call([
            "openssl", "pkcs12", "-export",
            "-out", str(pfx), "-inkey", str(key), "-in", str(crt),
            "-password", "pass:testpass", "-name", "BIGHat Test",
        ])

        # 2. Build + sign reusing the existing payload.
        out = REPO_ROOT / "dist" / "BIGHatStandalone-Setup-signtest.exe"
        if out.exists():
            out.unlink()
        r = subprocess.run(
            [
                sys.executable, str(BUILD_INSTALLER),
                "--skip-frontend", "--skip-payload",
                "--cert", str(pfx),
                "--cert-password", "testpass",
                "--output", str(out),
            ],
            capture_output=True, text=True, timeout=180,
            cwd=str(REPO_ROOT),
        )
        assert r.returncode == 0, f"sign build failed:\n{r.stdout}\n{r.stderr}"
        assert out.is_file()
        assert "Succeeded" in r.stdout, f"osslsigncode did not report Succeeded:\n{r.stdout}"

        # 3. Independent verify: PE has a valid signature blob.
        v = subprocess.run(
            ["osslsigncode", "verify", "-in", str(out)],
            capture_output=True, text=True, timeout=30,
        )
        out_text = (v.stdout or "") + (v.stderr or "")
        assert "Signer #0:" in out_text, "no signer found in signed PE"
        assert "/CN=BIGHat Test" in out_text, "embedded subject mismatch"
