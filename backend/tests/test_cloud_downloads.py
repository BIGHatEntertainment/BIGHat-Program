"""Verify the OS-aware downloads endpoints:

  * GET /api/downloads/auto                — 302s to the right asset
  * GET /api/downloads/latest              — JSON with all platform URLs
  * GET /api/downloads/{platform}          — legacy single-platform JSON
  * GET /download                          — friendly HTML landing page

All four resolve the latest release from either env-var overrides or a
mocked GitHub `releases/latest` lookup."""
from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


GH_LATEST = {
    "tag_name": "v31.0.8",
    "assets": [
        {"name": "BIGHatStandalone-Setup-31.0.8.exe",
         "browser_download_url": "https://github.com/x/y/releases/download/v31.0.8/BIGHatStandalone-Setup-31.0.8.exe",
         "size": 110_000_000},
        {"name": "BIGHatEntertainment-31.0.8-Windows.zip",
         "browser_download_url": "https://github.com/x/y/releases/download/v31.0.8/BIGHatEntertainment-31.0.8-Windows.zip",
         "size": 110_000_000},
        {"name": "BIGHatEntertainment-31.0.8-macOS-AppleSilicon.zip",
         "browser_download_url": "https://github.com/x/y/releases/download/v31.0.8/BIGHatEntertainment-31.0.8-macOS-AppleSilicon.zip",
         "size": 95_000_000},
        {"name": "BIGHatEntertainment-31.0.8-macOS-Intel.zip",
         "browser_download_url": "https://github.com/x/y/releases/download/v31.0.8/BIGHatEntertainment-31.0.8-macOS-Intel.zip",
         "size": 96_000_000},
    ],
}


@pytest.fixture()
def cloud_client(monkeypatch):
    """Boot a TestClient with BIGHAT_CLOUD_MODE=1 so cloud router is mounted."""
    monkeypatch.setenv("BIGHAT_CLOUD_MODE", "1")
    monkeypatch.setenv("BIGHAT_NATIVE_MODE", "0")
    monkeypatch.setenv("GITHUB_OWNER", "BIGHatEntertainment")
    monkeypatch.setenv("GITHUB_REPO", "BIGHat-Program")
    monkeypatch.delenv("DOWNLOAD_URL_WINDOWS", raising=False)
    monkeypatch.delenv("DOWNLOAD_URL_MACOS", raising=False)
    monkeypatch.delenv("DOWNLOAD_URL_MACOS_INTEL", raising=False)

    # Force-reimport so server.py picks up BIGHAT_CLOUD_MODE=1.
    import importlib, sys
    for m in list(sys.modules):
        if m == "server" or m.startswith("cloud.") or m == "cloud":
            sys.modules.pop(m, None)
    import server  # noqa: E402
    importlib.reload(server)
    from cloud import downloads_resolver
    downloads_resolver._bust_cache()

    with TestClient(server.app) as c:
        with patch("cloud.downloads_resolver._fetch_latest_release", return_value=GH_LATEST):
            yield c


# ---------- /api/downloads/auto ----------

def test_auto_redirects_windows_ua_to_exe(cloud_client):
    r = cloud_client.get("/api/downloads/auto", headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }, follow_redirects=False)
    assert r.status_code == 302
    loc = r.headers["location"]
    assert loc.endswith("BIGHatStandalone-Setup-31.0.8.exe"), loc


def test_auto_redirects_mac_ua_to_apple_silicon_dmg(cloud_client):
    r = cloud_client.get("/api/downloads/auto", headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_6) AppleWebKit"
    }, follow_redirects=False)
    assert r.status_code == 302
    loc = r.headers["location"]
    assert "macOS-AppleSilicon" in loc, loc


def test_auto_unknown_ua_goes_to_landing(cloud_client):
    r = cloud_client.get("/api/downloads/auto", headers={
        "User-Agent": "weird-bot/1.0"
    }, follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"].endswith("/download")


def test_auto_explicit_platform_override(cloud_client):
    """Landing page sends a Mac user to Intel build via ?platform=intel."""
    r = cloud_client.get(
        "/api/downloads/auto?platform=intel",
        headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_6)"},
        follow_redirects=False,
    )
    assert r.status_code == 302
    assert "macOS-Intel" in r.headers["location"]


# ---------- /api/downloads/latest ----------

def test_latest_manifest_returns_all_platforms(cloud_client):
    r = cloud_client.get("/api/downloads/latest")
    assert r.status_code == 200
    body = r.json()
    assert body["version"] == "31.0.8"
    p = body["platforms"]
    assert "windows" in p and p["windows"]["url"].endswith(".exe")
    assert "macos_apple" in p and "AppleSilicon" in p["macos_apple"]["url"]
    assert "macos_intel" in p and "Intel" in p["macos_intel"]["url"]


# ---------- /api/downloads/{platform} (legacy) ----------

def test_legacy_platform_endpoint_returns_macos_apple(cloud_client):
    r = cloud_client.get("/api/downloads/macos_apple")
    assert r.status_code == 200
    body = r.json()
    assert "AppleSilicon" in body["url"]
    assert body["version"] == "31.0.8"


def test_legacy_platform_endpoint_macos_alias_picks_apple_silicon(cloud_client):
    """The bare `macos` alias should default to Apple Silicon."""
    r = cloud_client.get("/api/downloads/macos")
    assert r.status_code == 200
    assert "AppleSilicon" in r.json()["url"]


# ---------- /download landing page ----------

def test_landing_page_shows_mac_primary_for_mac_ua(cloud_client):
    r = cloud_client.get("/download", headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_6)"
    })
    assert r.status_code == 200
    html_text = r.text
    assert 'data-testid="download-primary-macos_apple"' in html_text
    assert "Apple Silicon" in html_text
    assert "31.0.8" in html_text
    # Windows + Intel still shown as alt options
    assert 'data-testid="download-alt-windows"' in html_text
    assert 'data-testid="download-alt-macos_intel"' in html_text


def test_landing_page_shows_windows_primary_for_windows_ua(cloud_client):
    r = cloud_client.get("/download", headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64)"
    })
    assert r.status_code == 200
    assert 'data-testid="download-primary-windows"' in r.text
    assert "BIGHatStandalone-Setup-31.0.8.exe" in r.text


# ---------- Env-var override path ----------

def test_env_override_beats_github_lookup(cloud_client, monkeypatch):
    monkeypatch.setenv(
        "DOWNLOAD_URL_WINDOWS",
        "https://cdn.bighat.live/pinned/win-31.0.8.exe",
    )
    r = cloud_client.get("/api/downloads/auto", headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0)"
    }, follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "https://cdn.bighat.live/pinned/win-31.0.8.exe"


# ---------- No-release-on-github fallback ----------

def test_auto_redirects_to_landing_when_asset_missing(monkeypatch):
    """Force the GitHub lookup to return a release with NO mac assets — Mac
    user should land on /download?missing=… instead of a hard 404."""
    monkeypatch.setenv("BIGHAT_CLOUD_MODE", "1")
    monkeypatch.setenv("GITHUB_OWNER", "x")
    monkeypatch.setenv("GITHUB_REPO", "y")
    import importlib, sys
    for m in list(sys.modules):
        if m == "server" or m.startswith("cloud."):
            sys.modules.pop(m, None)
    import server  # noqa: E402
    importlib.reload(server)
    from cloud import downloads_resolver
    downloads_resolver._bust_cache()

    win_only = {
        "tag_name": "v31.0.8",
        "assets": [
            {"name": "BIGHatStandalone-Setup-31.0.8.exe",
             "browser_download_url": "https://gh/win.exe", "size": 1},
        ],
    }
    with TestClient(server.app) as c:
        with patch("cloud.downloads_resolver._fetch_latest_release", return_value=win_only):
            r = c.get("/api/downloads/auto", headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_6)"
            }, follow_redirects=False)
    assert r.status_code == 302
    assert "missing=macos_apple" in r.headers["location"]
