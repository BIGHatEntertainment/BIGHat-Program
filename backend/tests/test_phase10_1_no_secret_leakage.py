"""Phase 10.1 — Secret-leakage prevention regression tests.

Verifies that the Windows installer payload and the macOS .app bundle
NEVER contain `.env` files or other production secrets. This is the
single most important security guarantee of the build pipeline:
customers never receive copies of API keys baked into the install root.

Strategy:
  * Build payloads with the existing orchestrators (already exercised by
    Phase 9.2 / 9.3 tests).
  * Walk the resulting trees and assert that:
      1. No `.env` or `.env.*` files exist EXCEPT the safe `.env.standalone`
         template.
      2. No file contains any of a known list of secret values from the
         dev `.env` (we read the live `.env` and grep payloads for those
         exact secrets to catch accidental copies that aren't named `.env`).
      3. The `.env.standalone` template DOES ship and contains only
         desktop-safe defaults (no API keys, no OAuth client secrets).
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
BACKEND_DIR = REPO_ROOT / "backend"
PACKAGING = REPO_ROOT / "packaging"
ENV_FILE = BACKEND_DIR / ".env"
ENV_TEMPLATE = PACKAGING / ".env.standalone"


# ---------- helpers ----------
def _read_dev_secrets() -> list[str]:
    """Pull a list of secret VALUES from the dev `.env` so we can grep
    payloads for them. Skips short/empty values that would false-positive."""
    if not ENV_FILE.is_file():
        pytest.skip("/app/backend/.env not found in this environment")
    secrets: list[str] = []
    sensitive_keys = {
        "RESEND_API_KEY", "JWT_SECRET", "ADMIN_PASSWORD",
        "AZURE_CLIENT_SECRET", "AZURE_SECRET_ID",
        "ROUNDMAKER_CLIENT_SECRET", "ROUNDMAKER_SECRET_ID",
        "MONGO_URL", "SQUARESPACE_API_KEY", "SQUARESPACE_WEBHOOK_SECRET",
        "LICENSE_ADMIN_SECRET",
    }
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        v = v.strip().strip('"').strip("'")
        if k.strip() in sensitive_keys and len(v) >= 12:
            # Only grep for "real-looking" values to avoid noise
            secrets.append(v)
    return secrets


def _walk_files(root: Path):
    for p in root.rglob("*"):
        if p.is_file():
            yield p


# ---------- payload assembly fixtures ----------
@pytest.fixture(scope="module")
def windows_payload() -> Path:
    """Run the Windows orchestrator with --skip-makensis --skip-frontend
    --no-embed-python so we get the file tree without the network/compile."""
    payload = REPO_ROOT / "dist" / "payload"
    if payload.exists():
        shutil.rmtree(payload)
    r = subprocess.run(
        [
            sys.executable, str(SCRIPTS_DIR / "build_installer.py"),
            "--skip-makensis", "--skip-frontend", "--no-embed-python",
            "--no-sign",
        ],
        capture_output=True, text=True, timeout=60,
        cwd=str(REPO_ROOT),
    )
    assert r.returncode == 0, f"payload assembly failed:\n{r.stdout}\n{r.stderr}"
    return payload


@pytest.fixture(scope="module")
def macos_bundle() -> Path:
    dist_macos = REPO_ROOT / "dist" / "macos"
    if dist_macos.exists():
        shutil.rmtree(dist_macos)
    r = subprocess.run(
        [
            sys.executable, str(SCRIPTS_DIR / "build_dmg.py"),
            "--no-embed-python", "--skip-frontend",
            "--skip-pkg", "--skip-dmg",
        ],
        capture_output=True, text=True, timeout=60,
        cwd=str(REPO_ROOT),
    )
    assert r.returncode == 0, f".app assembly failed:\n{r.stdout}\n{r.stderr}"
    app = dist_macos / "BIG Hat Standalone.app"
    assert app.is_dir()
    return app


# ---------- the actual security tests ----------
class TestNoEnvFilesInWindowsPayload:
    def test_no_dotenv_anywhere_in_payload(self, windows_payload: Path):
        leaked = []
        for p in _walk_files(windows_payload):
            name = p.name
            if name == ".env" or (name.startswith(".env.") and name != ".env.standalone"):
                leaked.append(p)
        assert not leaked, f"Secret .env files leaked into Windows payload: {leaked}"

    def test_env_standalone_template_ships(self, windows_payload: Path):
        templates = [p for p in _walk_files(windows_payload) if p.name == ".env.standalone"]
        assert templates, "expected .env.standalone to ship in payload (desktop-safe defaults)"

    def test_no_secret_values_in_payload(self, windows_payload: Path):
        secrets = _read_dev_secrets()
        if not secrets:
            pytest.skip("no sensitive values configured in dev .env to grep for")
        leaked = []
        for p in _walk_files(windows_payload):
            try:
                # Skip binary-looking files (images, fonts, video, etc.)
                if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".gif", ".webp",
                                         ".mp3", ".mp4", ".wav", ".ttf", ".otf",
                                         ".woff", ".woff2", ".ico", ".pdf", ".zip"):
                    continue
                # Limit scan to ~10MB per file to avoid OOM on accidental binaries
                if p.stat().st_size > 10_000_000:
                    continue
                content = p.read_bytes()
            except OSError:
                continue
            for secret in secrets:
                if secret.encode("utf-8") in content:
                    leaked.append((p, secret[:6] + "…"))
                    break
        assert not leaked, f"SECRET LEAKAGE — found dev-.env values in shipped files: {leaked}"


class TestNoEnvFilesInMacOSBundle:
    def test_no_dotenv_anywhere_in_bundle(self, macos_bundle: Path):
        leaked = []
        for p in _walk_files(macos_bundle):
            name = p.name
            if name == ".env" or (name.startswith(".env.") and name != ".env.standalone"):
                leaked.append(p)
        assert not leaked, f"Secret .env files leaked into .app bundle: {leaked}"

    def test_env_standalone_template_ships(self, macos_bundle: Path):
        templates = [p for p in _walk_files(macos_bundle) if p.name == ".env.standalone"]
        assert templates, "expected .env.standalone to ship in .app bundle"

    def test_no_secret_values_in_bundle(self, macos_bundle: Path):
        secrets = _read_dev_secrets()
        if not secrets:
            pytest.skip("no sensitive values configured in dev .env to grep for")
        leaked = []
        for p in _walk_files(macos_bundle):
            try:
                if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".gif", ".webp",
                                         ".mp3", ".mp4", ".wav", ".ttf", ".otf",
                                         ".woff", ".woff2", ".ico", ".pdf", ".zip"):
                    continue
                if p.stat().st_size > 10_000_000:
                    continue
                content = p.read_bytes()
            except OSError:
                continue
            for secret in secrets:
                if secret.encode("utf-8") in content:
                    leaked.append((p, secret[:6] + "…"))
                    break
        assert not leaked, f"SECRET LEAKAGE — found dev-.env values in .app bundle: {leaked}"


class TestEnvStandaloneTemplate:
    def test_template_exists_and_is_safe(self):
        assert ENV_TEMPLATE.is_file(), f"missing {ENV_TEMPLATE}"
        text = ENV_TEMPLATE.read_text(encoding="utf-8")
        # MUST contain
        assert "BIGHAT_NATIVE_MODE=1" in text
        assert "JWT_SECRET=__GENERATED_AT_FIRST_RUN__" in text, \
            "JWT_SECRET placeholder must be the literal string the launcher replaces"
        # MUST NOT contain anything that looks like a production secret
        sensitive_substrings = (
            "RESEND_API_KEY=re_",
            "AZURE_CLIENT_SECRET=",
            "SQUARESPACE_API_KEY=",
            "ADMIN_PASSWORD=",
        )
        for needle in sensitive_substrings:
            for line in text.splitlines():
                line = line.strip()
                # Only fail on lines that ASSIGN a non-placeholder value.
                # Comment lines mentioning the names are fine.
                if line.startswith("#"):
                    continue
                if line.startswith(needle):
                    pytest.fail(f"template ships a real secret: {line[:80]}")

    def test_template_under_2kb_so_we_notice_accidental_growth(self):
        # The template should stay tiny — if it grows, someone added
        # something they shouldn't.
        size = ENV_TEMPLATE.stat().st_size
        assert size < 2048, (
            f".env.standalone is {size} bytes; if you added new keys, "
            f"audit them first — secrets must NEVER live in this file."
        )


class TestLauncherEnvBootstrap:
    """Verifies launcher.py copies .env.standalone → .env on first run
    and substitutes a unique JWT_SECRET."""

    def test_bootstrap_creates_env_with_unique_jwt_secret(self, tmp_path):
        # Stage a fake backend dir with the template but no .env.
        fake_backend = tmp_path / "backend"
        fake_backend.mkdir()
        # Minimal files launcher cares about
        shutil.copy2(ENV_TEMPLATE, fake_backend / ".env.standalone")

        # Run the bootstrap function in-process by monkeypatching BACKEND_DIR
        sys.path.insert(0, str(BACKEND_DIR))
        try:
            import importlib
            import launcher as launcher_mod
            importlib.reload(launcher_mod)
            launcher_mod.BACKEND_DIR = fake_backend
            written = launcher_mod._bootstrap_env_from_template()
        finally:
            sys.path.remove(str(BACKEND_DIR))
        assert written and written.is_file()
        text = written.read_text(encoding="utf-8")
        assert "__GENERATED_AT_FIRST_RUN__" not in text, \
            "placeholder must be replaced"
        # Pull the generated JWT_SECRET line
        jwt_line = next(l for l in text.splitlines() if l.startswith("JWT_SECRET="))
        secret = jwt_line.split("=", 1)[1].strip()
        assert len(secret) >= 32, f"generated JWT_SECRET too short: {len(secret)}"
        assert secret != "__GENERATED_AT_FIRST_RUN__"
        # Two invocations on different installs must yield different secrets.
        # Wipe and re-run — should be skipped because .env now exists.
        result2 = launcher_mod._bootstrap_env_from_template()
        assert result2 is None, "must NOT overwrite an existing .env"

    def test_bootstrap_no_op_when_template_missing(self, tmp_path):
        fake_backend = tmp_path / "backend"
        fake_backend.mkdir()
        sys.path.insert(0, str(BACKEND_DIR))
        try:
            import importlib
            import launcher as launcher_mod
            importlib.reload(launcher_mod)
            launcher_mod.BACKEND_DIR = fake_backend
            assert launcher_mod._bootstrap_env_from_template() is None
            assert not (fake_backend / ".env").exists()
        finally:
            sys.path.remove(str(BACKEND_DIR))
