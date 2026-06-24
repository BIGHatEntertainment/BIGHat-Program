"""Iteration 18 — Update channel default URL + cloud platforms-schema adapter.

Verifies the iter-18 fixes in /app/backend/native/updates_service.py:
  * DEFAULT_UPDATE_CHANNEL_URL = https://api.bighat.live/api/downloads/latest
  * _channel_url() precedence: explicit > BIGHAT_UPDATE_CHANNEL_URL env > config > default
  * fetch_manifest() adapts the {version, platforms:{windows,macos_apple,macos_intel}}
    cloud schema into a populated UpdateManifest based on the local OS/arch
  * Platform fallback: macos_apple host with no AS url falls back to macos_intel
  * Legacy direct-manifest schema is a no-op
  * download() treats manifest.sha256 as optional (no hash -> sha_verified=False,
    verified=True). Length-64 sha is enforced strictly; other lengths raise.
  * _detect_platform_key returns the right key on Windows / Darwin+arm64 /
    Darwin+x86_64 / Linux-fallback
  * Frontend static asserts on UpdateTool.jsx (installed_version, no current_version,
    nuanced channel_not_configured helper text)
  * Live smoke GET /api/
"""
from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import requests

sys.path.insert(0, "/app/backend")

from native.updates_service import (  # noqa: E402
    DEFAULT_UPDATE_CHANNEL_URL,
    UpdateManifest,
    UpdatesService,
    _detect_platform_key,
)
from native import updates_service as us_mod  # noqa: E402

BACKEND_DIR = Path("/app/backend")
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://127.0.0.1:8001").rstrip("/")
UPDATE_TOOL_JSX = Path("/app/frontend/src/pages/UpdateTool.jsx")


# ---------- Fixtures ----------
@pytest.fixture
def clean_env(monkeypatch):
    """Remove BOTH update env vars so we test true defaults / pure mocks.
    Also clears any updates config so config-file precedence is neutral."""
    monkeypatch.delenv("BIGHAT_UPDATE_MANIFEST_FIXTURE", raising=False)
    monkeypatch.delenv("BIGHAT_UPDATE_CHANNEL_URL", raising=False)
    # Neutralise updates section in the singleton config_manager
    monkeypatch.setattr(
        us_mod.config_manager,
        "config",
        {**us_mod.config_manager.config, "updates": {}},
        raising=True,
    )
    yield


def _svc(channel_url=None):
    return UpdatesService(backend_dir=BACKEND_DIR, db=None, channel_url=channel_url)


def _make_response(json_payload, status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json = MagicMock(return_value=json_payload)
    return resp


# ---------- Default channel URL ----------
class TestChannelURLPrecedence:
    def test_default_channel_url_constant(self):
        assert DEFAULT_UPDATE_CHANNEL_URL == "https://api.bighat.live/api/downloads/latest"

    def test_default_used_when_no_env_no_explicit_no_config(self, clean_env):
        svc = _svc()
        assert svc._channel_url() == DEFAULT_UPDATE_CHANNEL_URL

    def test_env_var_overrides_default(self, clean_env, monkeypatch):
        monkeypatch.setenv("BIGHAT_UPDATE_CHANNEL_URL", "https://example.test/manifest")
        assert _svc()._channel_url() == "https://example.test/manifest"

    def test_explicit_channel_overrides_env_and_default(self, clean_env, monkeypatch):
        monkeypatch.setenv("BIGHAT_UPDATE_CHANNEL_URL", "https://env.test/manifest")
        svc = _svc(channel_url="https://explicit.test/manifest")
        assert svc._channel_url() == "https://explicit.test/manifest"

    @pytest.mark.asyncio
    async def test_status_returns_default_channel_url(self, clean_env):
        st = await _svc().status()
        assert st["channel_url"] == DEFAULT_UPDATE_CHANNEL_URL
        assert "installed_version" in st
        assert "current_version" not in st, "field must be installed_version, not current_version"
        assert st["fixture_active"] is False


# ---------- _detect_platform_key ----------
class TestPlatformDetect:
    def test_windows(self):
        with patch("native.updates_service.platform.system", return_value="Windows"):
            assert _detect_platform_key() == "windows"

    def test_darwin_arm64(self):
        with patch("native.updates_service.platform.system", return_value="Darwin"), \
             patch("native.updates_service.platform.machine", return_value="arm64"):
            assert _detect_platform_key() == "macos_apple"

    def test_darwin_aarch64(self):
        with patch("native.updates_service.platform.system", return_value="Darwin"), \
             patch("native.updates_service.platform.machine", return_value="aarch64"):
            assert _detect_platform_key() == "macos_apple"

    def test_darwin_x86_64(self):
        with patch("native.updates_service.platform.system", return_value="Darwin"), \
             patch("native.updates_service.platform.machine", return_value="x86_64"):
            assert _detect_platform_key() == "macos_intel"

    def test_linux_falls_back_to_windows(self):
        with patch("native.updates_service.platform.system", return_value="Linux"), \
             patch("native.updates_service.platform.machine", return_value="x86_64"):
            assert _detect_platform_key() == "windows"


# ---------- fetch_manifest schema adapter ----------
CLOUD_PAYLOAD = {
    "version": "32.0.0",
    "platforms": {
        "windows": {
            "version": "32.0.0",
            "url": "https://github.com/BIGHatEntertainment/BIGHat-Program/releases/download/v32.0.0/BIG.Hat.Entertainment_32.0.0_x64-setup.exe",
        },
        "macos_apple": {
            "version": "32.0.0",
            "url": "https://github.com/BIGHatEntertainment/BIGHat-Program/releases/download/v32.0.0/BIG.Hat.Entertainment_32.0.0_aarch64.dmg",
        },
        "macos_intel": {
            "version": "32.0.0",
            "url": "https://github.com/BIGHatEntertainment/BIGHat-Program/releases/download/v32.0.0/BIG.Hat.Entertainment_32.0.0_x64.dmg",
        },
    },
    "release_notes": "Initial canonical release",
    "release_date": "2026-01-01",
}


class _AsyncClientCM:
    """Minimal async-context-manager that mimics httpx.AsyncClient(timeout=...)
    and exposes an async .get() returning a fake response."""
    def __init__(self, payload, status=200):
        self._payload = payload
        self._status = status

    async def __aenter__(self):
        client = MagicMock()
        client.get = AsyncMock(return_value=_make_response(self._payload, self._status))
        return client

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _patch_httpx(payload, status=200):
    return patch(
        "native.updates_service.httpx.AsyncClient",
        return_value=_AsyncClientCM(payload, status),
    )


class TestSchemaAdapter:
    @pytest.mark.asyncio
    async def test_windows_picks_windows_url(self, clean_env):
        with patch("native.updates_service._detect_platform_key", return_value="windows"), \
             _patch_httpx(CLOUD_PAYLOAD):
            m = await _svc()._wrapped_fetch() if False else await _svc().fetch_manifest()
        assert isinstance(m, UpdateManifest)
        assert m.latest_version == "32.0.0"
        assert m.download_url == CLOUD_PAYLOAD["platforms"]["windows"]["url"]
        assert m.sha256 == ""
        assert m.release_notes == "Initial canonical release"

    @pytest.mark.asyncio
    async def test_macos_apple_picks_apple_url(self, clean_env):
        with patch("native.updates_service._detect_platform_key", return_value="macos_apple"), \
             _patch_httpx(CLOUD_PAYLOAD):
            m = await _svc().fetch_manifest()
        assert m.download_url == CLOUD_PAYLOAD["platforms"]["macos_apple"]["url"]

    @pytest.mark.asyncio
    async def test_macos_intel_picks_intel_url(self, clean_env):
        with patch("native.updates_service._detect_platform_key", return_value="macos_intel"), \
             _patch_httpx(CLOUD_PAYLOAD):
            m = await _svc().fetch_manifest()
        assert m.download_url == CLOUD_PAYLOAD["platforms"]["macos_intel"]["url"]

    @pytest.mark.asyncio
    async def test_macos_apple_falls_back_to_intel(self, clean_env):
        # Apple Silicon build leg failed -> only intel url present
        payload = {
            "version": "32.0.1",
            "platforms": {
                "windows": {"version": "32.0.1", "url": "https://example.test/win.exe"},
                "macos_apple": {"version": "32.0.1", "url": ""},
                "macos_intel": {"version": "32.0.1", "url": "https://example.test/intel.dmg"},
            },
        }
        with patch("native.updates_service._detect_platform_key", return_value="macos_apple"), \
             _patch_httpx(payload):
            m = await _svc().fetch_manifest()
        assert m.download_url == "https://example.test/intel.dmg"
        assert m.latest_version == "32.0.1"

    @pytest.mark.asyncio
    async def test_legacy_direct_manifest_is_noop(self, clean_env):
        legacy = {
            "latest_version": "31.5.0",
            "download_url": "https://example.test/legacy.zip",
            "sha256": "a" * 64,
            "release_notes": "legacy",
        }
        with _patch_httpx(legacy):
            m = await _svc().fetch_manifest()
        assert m.latest_version == "31.5.0"
        assert m.download_url == "https://example.test/legacy.zip"
        assert m.sha256 == "a" * 64
        assert m.release_notes == "legacy"

    @pytest.mark.asyncio
    async def test_check_no_longer_raises_channel_not_configured(self, clean_env):
        """With default URL + mocked httpx returning cloud payload, /check works."""
        with patch("native.updates_service._detect_platform_key", return_value="windows"), \
             _patch_httpx(CLOUD_PAYLOAD):
            result = await _svc().check()
        assert result["manifest"]["latest_version"] == "32.0.0"
        assert result["manifest"]["download_url"].endswith(".exe")
        assert "installed_version" in result


# ---------- Download with optional sha256 ----------
class TestDownloadOptionalSha:
    @pytest.mark.asyncio
    async def test_empty_sha_streams_and_marks_sha_unverified(self, clean_env, tmp_path, monkeypatch):
        """When manifest.sha256 == '', download() must succeed (verified=True,
        sha_verified=False) instead of raising invalid_manifest_sha256."""
        # Force staging root into tmp
        monkeypatch.setattr(
            us_mod.config_manager,
            "config",
            {**us_mod.config_manager.config, "paths": {"generated": str(tmp_path)}, "updates": {}},
            raising=True,
        )
        # Local file:// bundle so we avoid real httpx streaming
        bundle = tmp_path / "src_bundle.zip"
        payload_bytes = b"PK\x03\x04fake-zip-bytes-iter18"
        bundle.write_bytes(payload_bytes)
        expected_digest = hashlib.sha256(payload_bytes).hexdigest()

        manifest_dict = {
            "latest_version": "99.0.0",  # newer than VERSION.txt (31.0.0)
            "download_url": f"file://{bundle}",
            "sha256": "",
        }
        svc = _svc()
        async def fake_fetch():
            return UpdateManifest.from_dict(manifest_dict)
        svc.fetch_manifest = fake_fetch  # type: ignore

        out = await svc.download()
        staged = out["staged"]
        assert staged["verified"] is True
        assert staged["sha_verified"] is False
        assert staged["version"] == "99.0.0"
        assert staged["sha256"] == expected_digest
        assert Path(staged["path"]).is_file()

    @pytest.mark.asyncio
    async def test_valid_64_hex_sha_enforced(self, clean_env, tmp_path, monkeypatch):
        monkeypatch.setattr(
            us_mod.config_manager,
            "config",
            {**us_mod.config_manager.config, "paths": {"generated": str(tmp_path)}, "updates": {}},
            raising=True,
        )
        bundle = tmp_path / "src_bundle.zip"
        payload_bytes = b"verify-me-iter18"
        bundle.write_bytes(payload_bytes)
        expected_digest = hashlib.sha256(payload_bytes).hexdigest()

        manifest_dict = {
            "latest_version": "99.0.0",
            "download_url": f"file://{bundle}",
            "sha256": expected_digest,
        }
        svc = _svc()
        async def fake_fetch():
            return UpdateManifest.from_dict(manifest_dict)
        svc.fetch_manifest = fake_fetch  # type: ignore
        out = await svc.download()
        assert out["staged"]["sha_verified"] is True
        assert out["staged"]["sha256"] == expected_digest

    @pytest.mark.asyncio
    async def test_invalid_sha_length_raises(self, clean_env, tmp_path, monkeypatch):
        monkeypatch.setattr(
            us_mod.config_manager,
            "config",
            {**us_mod.config_manager.config, "paths": {"generated": str(tmp_path)}, "updates": {}},
            raising=True,
        )
        bundle = tmp_path / "src_bundle.zip"
        bundle.write_bytes(b"x")
        manifest_dict = {
            "latest_version": "99.0.0",
            "download_url": f"file://{bundle}",
            "sha256": "shorthex",
        }
        svc = _svc()
        async def fake_fetch():
            return UpdateManifest.from_dict(manifest_dict)
        svc.fetch_manifest = fake_fetch  # type: ignore
        with pytest.raises(RuntimeError, match="invalid_manifest_sha256"):
            await svc.download()


# ---------- Frontend static asserts ----------
class TestUpdateToolJSX:
    def test_jsx_exists(self):
        assert UPDATE_TOOL_JSX.is_file(), f"missing {UPDATE_TOOL_JSX}"

    def test_uses_installed_version_not_current_version(self):
        text = UPDATE_TOOL_JSX.read_text(encoding="utf-8")
        assert "status?.installed_version" in text or "status.installed_version" in text
        assert "current_version" not in text, "JSX must not reference status.current_version"

    def test_latest_known_latest_version_path(self):
        text = UPDATE_TOOL_JSX.read_text(encoding="utf-8")
        assert "latest_known?.latest_version" in text or "latest_known.latest_version" in text
        assert "manifest?.latest_version" in text or "manifest.latest_version" in text

    def test_channel_not_configured_helper_text_is_nuanced(self):
        text = UPDATE_TOOL_JSX.read_text(encoding="utf-8")
        assert "channel_not_configured" in text, "must branch on channel_not_configured"
        # The channel_not_configured branch must reference re-install, NOT the
        # generic "connected to the internet" advice.
        idx = text.find("channel_not_configured")
        # Take a 400-char window after the marker — that's the conditional body.
        window = text[idx: idx + 400]
        assert ("Re-install" in window) or ("re-install" in window) or ("reinstall" in window.lower()), \
            f"channel_not_configured branch must suggest re-install. window={window!r}"


# ---------- Live smoke ----------
class TestBackendSmoke:
    def test_api_root_200(self):
        r = requests.get(f"{BASE_URL}/api/", timeout=10)
        assert r.status_code == 200, r.text
