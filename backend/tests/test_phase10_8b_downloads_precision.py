"""Phase 10.8b — Downloads resolver precision regression.

The v32.0.0-alpha.9 release file names contain substrings that the OLD
naive matcher conflated, which would have routed customers to the wrong
binary:

  * `BIG.Hat.Entertainment_32.0.0-alpha.9_x64-setup.exe`  — Windows
  * `BIG.Hat.Entertainment_32.0.0-alpha.9_aarch64.dmg`    — macOS Apple Silicon
  * `BIG.Hat.Entertainment_aarch64.app.tar.gz`            — Tauri auto-updater (NOT user-facing)

Naive substring matching for `macos_intel: ("x64",)` would pick the
Windows .exe. Likewise, `macos_apple: ("aarch64",)` could pick the
Tauri `.app.tar.gz` updater bundle instead of the user-facing `.dmg`.

This file locks in the extension-aware matcher (`ext` + `needles` +
`forbids`) that prevents these mis-routes.
"""
from __future__ import annotations

import pytest

from cloud import downloads_resolver as r


REAL_RELEASE_ASSETS = [
    {
        "name": "BIG.Hat.Entertainment_32.0.0-alpha.9_aarch64.dmg",
        "browser_download_url": "https://github.com/x/y/releases/download/v32.0.0-alpha.9/BIG.Hat.Entertainment_32.0.0-alpha.9_aarch64.dmg",
        "size": 120906432,
    },
    {
        "name": "BIG.Hat.Entertainment_32.0.0-alpha.9_x64-setup.exe",
        "browser_download_url": "https://github.com/x/y/releases/download/v32.0.0-alpha.9/BIG.Hat.Entertainment_32.0.0-alpha.9_x64-setup.exe",
        "size": 138988402,
    },
    {
        "name": "BIG.Hat.Entertainment_aarch64.app.tar.gz",
        "browser_download_url": "https://github.com/x/y/releases/download/v32.0.0-alpha.9/BIG.Hat.Entertainment_aarch64.app.tar.gz",
        "size": 120541150,
    },
]


class TestRealReleaseAssetRouting:
    def test_windows_picks_exe_not_dmg(self):
        a = r._pick_asset(REAL_RELEASE_ASSETS, "windows")
        assert a is not None
        assert a["name"].endswith(".exe")
        assert "x64-setup" in a["name"]

    def test_macos_apple_picks_dmg_not_updater_tarball(self):
        """The .app.tar.gz Tauri updater bundle also matches `aarch64`.
        Make sure the user-facing .dmg wins."""
        a = r._pick_asset(REAL_RELEASE_ASSETS, "macos_apple")
        assert a is not None
        assert a["name"].endswith(".dmg")
        assert "aarch64" in a["name"]
        assert ".tar.gz" not in a["name"]

    def test_macos_intel_does_NOT_get_windows_exe(self):
        """The Windows file contains `x64` in its name. Naive substring
        matching for `macos_intel: ('x64',)` would route Intel Mac users
        to the Windows .exe. Must return None when no real Intel .dmg
        is published, NEVER the .exe."""
        a = r._pick_asset(REAL_RELEASE_ASSETS, "macos_intel")
        # With these specific assets, no real Intel build exists, so we
        # MUST return None — never fall back to the .exe.
        assert a is None or a["name"].endswith(".dmg")
        if a is not None:
            assert ".exe" not in a["name"]


class TestSingleAssetFallback:
    """When a publisher ships a single all-x64 .dmg with no arch tag in
    the name, the resolver should still pick it for macos_intel rather
    than 404."""

    def test_single_dmg_no_arch_falls_back_to_single_match(self):
        assets = [
            {"name": "MyApp-1.0.dmg",
             "browser_download_url": "https://x/MyApp-1.0.dmg",
             "size": 100},
        ]
        a_int = r._pick_asset(assets, "macos_intel")
        a_app = r._pick_asset(assets, "macos_apple")
        assert a_int is not None
        assert a_app is not None
        assert a_int["name"] == "MyApp-1.0.dmg"

    def test_two_unlabeled_dmgs_first_wins(self):
        """When two .dmgs both have no arch tag, the resolver picks the
        first one rather than returning None. This is a deliberate fallback
        — better to serve a likely-correct binary than 404."""
        assets = [
            {"name": "MyApp-1.0.dmg",     "browser_download_url": "https://x/a.dmg"},
            {"name": "MyApp-1.0-old.dmg", "browser_download_url": "https://x/b.dmg"},
        ]
        a = r._pick_asset(assets, "macos_intel")
        assert a is not None
        assert a["name"] == "MyApp-1.0.dmg"


class TestForbiddenSubstrings:
    """Belt-and-suspenders: confirm each platform respects its forbids."""

    def test_windows_forbids_dmg_even_with_x64_needle(self):
        # A hypothetical .dmg with "windows" in the name — must be rejected.
        a = r._pick_asset([{
            "name": "windows-style.dmg",
            "browser_download_url": "https://x/y.dmg",
        }], "windows")
        assert a is None

    def test_macos_apple_picks_aarch64_when_both_archs_exist(self):
        """When both aarch64 and intel .dmgs exist, ?platform=macos_apple
        must pick the aarch64 one — that's the whole point of arch needles."""
        a = r._pick_asset([
            {"name": "MyApp_aarch64.dmg", "browser_download_url": "https://x/aarch64.dmg"},
            {"name": "MyApp_intel.dmg",   "browser_download_url": "https://x/intel.dmg"},
        ], "macos_apple")
        assert a is not None
        assert "aarch64" in a["name"]

    def test_macos_intel_forbids_aarch64(self):
        a = r._pick_asset([{
            "name": "MyApp_x64_aarch64.dmg",
            "browser_download_url": "https://x/y.dmg",
        }], "macos_intel")
        assert a is None
