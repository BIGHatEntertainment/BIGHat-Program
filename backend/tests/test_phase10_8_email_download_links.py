"""Phase 10.8 — Email download-link regression.

The v32.0.0-alpha.9 customer report: the license email's "Download"
button linked to `bighat.live/download` (Squarespace marketing site)
which 404'd because the actual download landing page + smart redirect
live on `api.bighat.live`, not on the marketing domain.

Contract:
  * License-key email HTML download button → `{API_BASE}/api/downloads/auto?key=<key>`
  * License-key email text body → same URL
  * Manual-pick fallback link → `{API_BASE}/download`
  * NEVER use `{BRAND_BASE_URL}/download` (Squarespace 404)
"""
from __future__ import annotations

import re

import pytest

from cloud.email_service import _license_key_html, _license_key_text


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("BRAND_BASE_URL", "https://bighat.live")
    monkeypatch.setenv("LICENSE_API_BASE_URL", "https://api.bighat.live")
    monkeypatch.setenv("SUPPORT_EMAIL", "support@bighat.live")


KEY = "BHE-E7GX-VGTT-TGGP-8S2G"


class TestEmailDownloadLinks:
    def test_html_button_points_to_api_subdomain_with_key(self, env):
        html = _license_key_html(KEY, owns_standalone=True, cloud_library_active=False)
        # The primary button — must be the smart redirect.
        assert f'https://api.bighat.live/api/downloads/auto?key={KEY}' in html
        # And it must NOT point at the Squarespace site.
        assert 'https://bighat.live/download' not in html

    def test_text_body_also_uses_api_subdomain(self, env):
        text = _license_key_text(KEY, owns_standalone=True, cloud_library_active=False)
        assert f'https://api.bighat.live/api/downloads/auto?key={KEY}' in text
        assert 'https://bighat.live/download' not in text

    def test_html_has_manual_fallback_to_api_download_landing(self, env):
        html = _license_key_html(KEY, owns_standalone=True, cloud_library_active=False)
        assert 'https://api.bighat.live/download' in html

    def test_squarespace_marketing_url_is_NEVER_a_download_target(self, env):
        """Hard guard: no future refactor may put bighat.live/download
        back into the email — that's the Squarespace 404 page that broke
        the v32.0.0-alpha.9 customer."""
        for kw in [
            dict(owns_standalone=True, cloud_library_active=False),
            dict(owns_standalone=True, cloud_library_active=True,
                 owns_music_bingo=True, owns_karaoke=True),
            dict(owns_standalone=False, cloud_library_active=True),
        ]:
            html = _license_key_html(KEY, **kw)
            text = _license_key_text(KEY, **kw)
            assert 'bighat.live/download' not in html.replace('api.bighat.live', '')
            assert 'bighat.live/download' not in text.replace('api.bighat.live', '')

    def test_html_button_visible_for_addon_only_purchases(self, env):
        # Even a Music Bingo or Karaoke-only purchase needs a download link
        # (the customer still needs to install the base app to use the add-on).
        html = _license_key_html(KEY, owns_standalone=False, cloud_library_active=False,
                                  owns_music_bingo=True)
        assert 'api/downloads/auto' in html

    def test_lifetime_marker_appears_for_standalone(self, env):
        """Standalone purchases are LIFETIME — the email copy must reflect
        that so the customer doesn't worry about expiry. This is one of the
        contractual differences between standalone and cloud_library."""
        html = _license_key_html(KEY, owns_standalone=True, cloud_library_active=False)
        text = _license_key_text(KEY, owns_standalone=True, cloud_library_active=False)
        assert 'lifetime' in html.lower()
        assert 'lifetime' in text.lower()
