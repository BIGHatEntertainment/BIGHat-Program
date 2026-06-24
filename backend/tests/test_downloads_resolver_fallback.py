"""Unit tests for the walk-back fallback in
`cloud.downloads_resolver.resolve()` and the SPA-fallback exclusion in
`server.py` for the `/download` route.

We mock `_fetch_latest_release` and `_fetch_recent_releases` directly so
no real GitHub API call is made. `urllib.request.urlopen` is also
patched at the module level as an extra safety net.

Run:
    pytest /app/backend/tests/test_downloads_resolver_fallback.py -v
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Make /app/backend importable.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cloud import downloads_resolver  # noqa: E402


# -- shared fixtures ---------------------------------------------------------

LATEST_NO_WIN = {
    "tag_name": "v32.0.0-alpha.11",
    "draft": False,
    "assets": [
        # Only macOS assets, no .exe.
        {"name": "BIG.Hat.Entertainment_32.0.0-alpha.11_aarch64.dmg",
         "browser_download_url": "https://gh/v32.0.0-alpha.11/macos-as.dmg",
         "size": 95_000_000},
    ],
}

OLDER_WITH_WIN = {
    "tag_name": "v32.0.0-alpha.10",
    "draft": False,
    "assets": [
        {"name": "BIG.Hat.Entertainment_32.0.0-alpha.10_x64-setup.exe",
         "browser_download_url": "https://gh/v32.0.0-alpha.10/win.exe",
         "size": 138_000_000},
        {"name": "BIG.Hat.Entertainment_32.0.0-alpha.10_aarch64.dmg",
         "browser_download_url": "https://gh/v32.0.0-alpha.10/macos-as.dmg",
         "size": 95_000_000},
    ],
}

LATEST_FULL = {
    "tag_name": "v32.0.0-alpha.11",
    "draft": False,
    "assets": [
        {"name": "BIG.Hat.Entertainment_32.0.0-alpha.11_x64-setup.exe",
         "browser_download_url": "https://gh/v32.0.0-alpha.11/win.exe",
         "size": 138_000_000},
        {"name": "BIG.Hat.Entertainment_32.0.0-alpha.11_aarch64.dmg",
         "browser_download_url": "https://gh/v32.0.0-alpha.11/macos-as.dmg",
         "size": 95_000_000},
    ],
}


@pytest.fixture(autouse=True)
def _clean_env_and_cache(monkeypatch):
    """Force GitHub path (no env overrides) and reset the in-memory cache."""
    monkeypatch.delenv("DOWNLOAD_URL_WINDOWS", raising=False)
    monkeypatch.delenv("DOWNLOAD_URL_MACOS", raising=False)
    monkeypatch.delenv("DOWNLOAD_URL_MACOS_INTEL", raising=False)
    monkeypatch.setenv("GITHUB_OWNER", "BIGHatEntertainment")
    monkeypatch.setenv("GITHUB_REPO", "BIGHat-Program")
    downloads_resolver._bust_cache()
    # Safety net: block any real network call from this module.
    with patch.object(downloads_resolver.urllib.request, "urlopen",
                      side_effect=AssertionError("real urlopen called")):
        yield
    downloads_resolver._bust_cache()


# -- walk-back tests --------------------------------------------------------

def test_walkback_returns_older_release_when_latest_missing_windows():
    """Latest tag has no .exe → resolver walks back and returns the older
    release's .exe with is_fallback=True and latest_version annotated."""
    with patch.object(downloads_resolver, "_fetch_latest_release",
                      return_value=LATEST_NO_WIN), \
         patch.object(downloads_resolver, "_fetch_recent_releases",
                      return_value=[LATEST_NO_WIN, OLDER_WITH_WIN]):
        result = downloads_resolver.resolve("windows")

    assert result["url"] == "https://gh/v32.0.0-alpha.10/win.exe"
    assert result["is_fallback"] is True
    assert result["latest_version"] == "32.0.0-alpha.11"
    assert result["version"] == "32.0.0-alpha.10"
    assert result["platform"] == "windows"
    assert result["source"] == "github"
    assert result["filename"].endswith(".exe")
    assert result["size"] == 138_000_000


def test_walkback_returns_none_when_no_release_has_asset():
    """Neither latest nor any older release has a Windows binary.
    resolve() must return url=None and MUST NOT set is_fallback."""
    older_mac_only = {
        "tag_name": "v32.0.0-alpha.10",
        "draft": False,
        "assets": [
            {"name": "BIG.Hat.Entertainment_32.0.0-alpha.10_aarch64.dmg",
             "browser_download_url": "https://gh/v32.0.0-alpha.10/macos-as.dmg",
             "size": 95_000_000},
        ],
    }
    with patch.object(downloads_resolver, "_fetch_latest_release",
                      return_value=LATEST_NO_WIN), \
         patch.object(downloads_resolver, "_fetch_recent_releases",
                      return_value=[LATEST_NO_WIN, older_mac_only]):
        result = downloads_resolver.resolve("windows")

    assert result["url"] is None
    assert result["filename"] is None
    assert "is_fallback" not in result, \
        "is_fallback must NOT be set when no fallback was found (no false positives)"
    assert result["platform"] == "windows"


def test_walkback_lazy_when_latest_has_matching_asset():
    """If the latest release HAS the platform's asset, _fetch_recent_releases
    must never be called (lazy walk-back)."""
    recent_mock = MagicMock()
    with patch.object(downloads_resolver, "_fetch_latest_release",
                      return_value=LATEST_FULL), \
         patch.object(downloads_resolver, "_fetch_recent_releases", recent_mock):
        result = downloads_resolver.resolve("windows")

    assert result["url"] == "https://gh/v32.0.0-alpha.11/win.exe"
    assert result.get("is_fallback") is None or result.get("is_fallback") is False
    recent_mock.assert_not_called()


def test_walkback_skips_release_with_same_version_as_latest():
    """`_fetch_recent_releases` returns the latest release first too. The
    walk-back must skip any release whose tag_name matches the latest
    (otherwise we'd return the same broken release as a 'fallback')."""
    # `_fetch_recent_releases` returns latest (no win) twice + then older.
    duplicate_latest = dict(LATEST_NO_WIN)
    with patch.object(downloads_resolver, "_fetch_latest_release",
                      return_value=LATEST_NO_WIN), \
         patch.object(downloads_resolver, "_fetch_recent_releases",
                      return_value=[duplicate_latest, OLDER_WITH_WIN]):
        result = downloads_resolver.resolve("windows")

    assert result["url"] == "https://gh/v32.0.0-alpha.10/win.exe"
    assert result["version"] == "32.0.0-alpha.10"
    assert result["latest_version"] == "32.0.0-alpha.11"


def test_walkback_works_for_macos_alias_via_intel_when_apple_silicon_missing():
    """Sanity: macos alias falls back to Intel within the older release if AS
    isn't there either."""
    older_intel_only = {
        "tag_name": "v32.0.0-alpha.10",
        "draft": False,
        "assets": [
            {"name": "BIG.Hat.Entertainment_32.0.0-alpha.10_x86_64.dmg",
             "browser_download_url": "https://gh/v32.0.0-alpha.10/intel.dmg",
             "size": 96_000_000},
        ],
    }
    latest_win_only = {
        "tag_name": "v32.0.0-alpha.11",
        "draft": False,
        "assets": [
            {"name": "BIG.Hat.Entertainment_32.0.0-alpha.11_x64-setup.exe",
             "browser_download_url": "https://gh/v32.0.0-alpha.11/win.exe",
             "size": 138_000_000},
        ],
    }
    with patch.object(downloads_resolver, "_fetch_latest_release",
                      return_value=latest_win_only), \
         patch.object(downloads_resolver, "_fetch_recent_releases",
                      return_value=[latest_win_only, older_intel_only]):
        result = downloads_resolver.resolve("macos")

    assert result["url"] == "https://gh/v32.0.0-alpha.10/intel.dmg"
    assert result["is_fallback"] is True
    assert result["latest_version"] == "32.0.0-alpha.11"


# -- caching tests ----------------------------------------------------------

def test_fetch_recent_releases_uses_cache_within_ttl():
    """A second call to _fetch_recent_releases within the TTL must NOT
    re-invoke urlopen."""
    fake_payload = [OLDER_WITH_WIN]

    call_count = {"n": 0}

    def fake_urlopen(req, timeout=8):
        call_count["n"] += 1
        m = MagicMock()
        m.__enter__ = lambda s: s
        m.__exit__ = lambda *a: False
        import json as _json
        m.read = lambda: _json.dumps(fake_payload).encode("utf-8")
        return m

    with patch.object(downloads_resolver.urllib.request, "urlopen",
                      side_effect=fake_urlopen):
        first = downloads_resolver._fetch_recent_releases(limit=5)
        second = downloads_resolver._fetch_recent_releases(limit=5)

    assert call_count["n"] == 1, \
        f"_fetch_recent_releases must cache; urlopen called {call_count['n']}x"
    assert first == second
    assert first[0]["tag_name"] == "v32.0.0-alpha.10"


def test_fetch_recent_releases_filters_drafts():
    """Drafts must be excluded — they can have incomplete asset uploads
    mid-build."""
    payload = [
        {"tag_name": "v99-draft", "draft": True, "assets": []},
        OLDER_WITH_WIN,
    ]

    def fake_urlopen(req, timeout=8):
        m = MagicMock()
        m.__enter__ = lambda s: s
        m.__exit__ = lambda *a: False
        import json as _json
        m.read = lambda: _json.dumps(payload).encode("utf-8")
        return m

    with patch.object(downloads_resolver.urllib.request, "urlopen",
                      side_effect=fake_urlopen):
        out = downloads_resolver._fetch_recent_releases(limit=5)

    assert len(out) == 1
    assert out[0]["tag_name"] == "v32.0.0-alpha.10"


# -- SPA fallback / static check --------------------------------------------

def test_spa_fallback_exclusion_includes_download_and_api():
    """Static check that server.py's SPA fallback excludes BOTH `api/` and
    the new `download` literal at the modified site."""
    server_path = Path(__file__).resolve().parents[1] / "server.py"
    text = server_path.read_text(encoding="utf-8")
    # The exclusion must mention both api/ and download in the same region.
    assert 'full_path.startswith("api/")' in text
    # The literal "download" must appear in the exclusion tuple.
    assert '"download"' in text
    # And both must be co-located in the SPA fallback block.
    spa_block_start = text.find("_spa_fallback")
    assert spa_block_start > 0, "_spa_fallback handler not found"
    snippet = text[spa_block_start:spa_block_start + 1500]
    assert '"download"' in snippet, "'download' literal missing from SPA fallback exclusion"
    assert 'api/' in snippet, "'api/' prefix missing from SPA fallback exclusion"


# -- live SPA fallback behaviour (TestClient, native mode) ------------------

def _make_native_client():
    """Reload server.py in pure-native mode (cloud router NOT mounted) and
    return a TestClient. This validates the SPA fallback fix in the very
    mode the review request specifies: /download must NOT return the
    React index.html shell."""
    os.environ.pop("BIGHAT_CLOUD_MODE", None)
    os.environ["BIGHAT_NATIVE_MODE"] = "1"
    import importlib
    for m in list(sys.modules):
        if m == "server" or m.startswith("cloud."):
            sys.modules.pop(m, None)
    import server  # noqa: E402
    importlib.reload(server)
    from fastapi.testclient import TestClient
    return TestClient(server.app)


def test_download_route_not_caught_by_spa_fallback_in_native_mode():
    """In native mode the cloud download_landing router is NOT mounted, so
    GET /download must 404 cleanly (NOT return the React index.html
    shell). This is the core bug fix being validated."""
    client = _make_native_client()
    try:
        r = client.get("/download")
        # Must NOT be 200 with React shell.
        # Acceptable: 404 (no route). Anything that's NOT the React shell.
        if r.status_code == 200:
            assert "<!doctype html" not in r.text.lower() or \
                   "react" not in r.text.lower(), \
                   f"/download was caught by SPA fallback: {r.text[:200]}"
            assert "id=\"root\"" not in r.text, \
                f"/download returned React shell with #root div: {r.text[:200]}"
        else:
            assert r.status_code == 404, \
                f"expected 404 for /download in native mode, got {r.status_code}"
    finally:
        client.close()


def test_download_with_querystring_not_caught_by_spa_fallback():
    """Query strings must not bypass the SPA exclusion."""
    client = _make_native_client()
    try:
        r = client.get("/download?missing=windows")
        if r.status_code == 200:
            assert "id=\"root\"" not in r.text, \
                f"/download?missing=windows returned React shell: {r.text[:200]}"
        else:
            assert r.status_code == 404
    finally:
        client.close()
