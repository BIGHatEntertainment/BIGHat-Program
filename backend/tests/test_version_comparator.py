"""Contract test for the v32.0.0-alpha.20 version comparator.

The previous `parse_version` impl stripped any prerelease suffix
(`-alpha.18`), reducing every prerelease of `32.0.0` to the same tuple
`(32, 0, 0)`. As a result `is_newer("32.0.0-alpha.19", "32.0.0-alpha.18")`
returned False and the in-app Update tool showed "You're up to date"
while clearly displaying different version strings to the user.

These tests pin the alpha-prerelease ordering invariants so we never
ship a regression that breaks the auto-update prompt again.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from backend.native.updates_service import is_newer, parse_version


def test_consecutive_alphas_are_ordered():
    assert is_newer("32.0.0-alpha.19", "32.0.0-alpha.18")
    assert not is_newer("32.0.0-alpha.18", "32.0.0-alpha.19")


def test_alpha_beta_rc_ordering():
    assert is_newer("32.0.0-beta.1", "32.0.0-alpha.20")
    assert is_newer("32.0.0-rc.1", "32.0.0-beta.5")
    assert is_newer("32.0.0", "32.0.0-rc.99")


def test_same_version_is_not_newer():
    assert not is_newer("32.0.0-alpha.18", "32.0.0-alpha.18")
    assert not is_newer("32.0.0", "32.0.0")


def test_release_sorts_after_any_prerelease_of_same_triple():
    assert parse_version("32.0.0") > parse_version("32.0.0-alpha.999")
    assert parse_version("32.0.0") > parse_version("32.0.0-rc.5")


def test_major_minor_patch_still_dominate():
    assert is_newer("33.0.0-alpha.1", "32.0.0")
    assert is_newer("32.1.0-alpha.1", "32.0.0-alpha.999")
    assert is_newer("32.0.1-alpha.1", "32.0.0-rc.99")


def test_plain_string_handles_v_prefix():
    assert is_newer("v32.0.0-alpha.19", "32.0.0-alpha.18")


def test_unknown_suffix_still_orderable():
    # Unknown suffix gets a high prerelease rank — newer-numbered
    # unknowns still beat older-numbered known prereleases.
    assert is_newer("32.0.0-snapshot.5", "32.0.0-alpha.18")
