"""Resend-backed email service for license-key delivery.

Gracefully no-ops when `RESEND_API_KEY` is not set (logs a warning and
returns `False`). Tests substitute a capturing fake via the `EmailSender`
protocol in `license_service`.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Optional

import resend

from . import config

logger = logging.getLogger("bighat-license-email")


# ---------- HTML templates (inline CSS; email-client friendly) ----------
_STYLE = """
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
         color: #111827; background: #f9fafb; margin: 0; padding: 24px; }
  .card { max-width: 560px; margin: 0 auto; background: #ffffff; border-radius: 12px;
          padding: 32px; border: 1px solid #e5e7eb; }
  h1 { font-size: 22px; margin: 0 0 16px 0; color: #111827; }
  p { font-size: 15px; line-height: 1.55; margin: 0 0 14px 0; color: #374151; }
  .key { font-family: 'SF Mono', ui-monospace, Menlo, monospace; font-size: 20px;
         letter-spacing: 2px; padding: 14px 18px; background: #f3f4f6;
         border: 1px solid #e5e7eb; border-radius: 8px; display: inline-block;
         user-select: all; color: #111827; }
  .btn { display: inline-block; padding: 12px 22px; background: #111827; color: #ffffff;
         text-decoration: none; border-radius: 8px; font-weight: 600; font-size: 15px;
         margin-top: 8px; }
  .small { font-size: 13px; color: #6b7280; }
  .divider { height: 1px; background: #e5e7eb; margin: 24px 0; border: 0; }
"""


def _license_key_html(key: str, *, owns_standalone: bool, cloud_library_active: bool,
                      owns_music_bingo: bool = False, owns_karaoke: bool = False) -> str:
    # IMPORTANT: download links MUST point at api.bighat.live (the FastAPI
    # pod that owns /api/downloads/auto and /download), NOT bighat.live
    # (the Squarespace marketing site, which has no /download route and
    # returns a 404 page).
    #
    # Encoding the customer's key into the download URL lets the landing
    # page deep-link straight into the Setup Wizard via the
    # `bighat://activate?key=…` protocol handler when the desktop app is
    # installed — eliminates a copy-paste step.
    api = config.api_base_url()
    brand = config.brand_base_url()
    support = config.support_email()
    download_url = f"{api}/api/downloads/auto?key={key}"
    tier_line = []
    if owns_standalone:
        tier_line.append("✓ BIG Hat Entertainment (lifetime)")
    if owns_music_bingo:
        tier_line.append("✓ Music Bingo add-on (lifetime)")
    if owns_karaoke:
        tier_line.append("✓ Karaoke add-on (lifetime)")
    if cloud_library_active:
        tier_line.append("✓ Cloud Library subscription (active)")
    tier_html = "<br/>".join(tier_line) or "No paid tier — manually issued"

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>{_STYLE}</style></head>
<body><div class="card">
  <h1>Your BIG Hat Entertainment license</h1>
  <p>Thanks for your purchase. Your license key is:</p>
  <p><span class="key">{key}</span></p>
  <p class="small">{tier_html}</p>
  <hr class="divider"/>
  <p><strong>Get the app</strong></p>
  <p><a class="btn" href="{download_url}">Download BIG Hat Entertainment</a></p>
  <p class="small">The button above auto-detects your OS and serves the latest installer
     (Windows .exe or macOS .dmg). If it doesn't open the right one, pick manually at
     <a href="{api}/download">{api.replace('https://','').replace('http://','')}/download</a>.</p>
  <p>On first launch, paste the key above into the Setup Wizard. The key binds
     to up to 3 machines (5 with an active Cloud Library subscription). All
     add-ons you've purchased unlock on every machine bound to this key. If
     you need to move it to a new computer, deactivate the old machine from
     <em>Settings → License</em>, or email us.</p>
  <hr class="divider"/>
  <p class="small">Questions? Reply to this email or write to <a href="mailto:{support}">{support}</a>.</p>
  <p class="small">— BIG Hat Entertainment</p>
</div></body></html>"""


def _license_key_text(key: str, *, owns_standalone: bool, cloud_library_active: bool,
                      owns_music_bingo: bool = False, owns_karaoke: bool = False) -> str:
    tier = []
    if owns_standalone:
        tier.append("- BIG Hat Entertainment (lifetime)")
    if owns_music_bingo:
        tier.append("- Music Bingo add-on (lifetime)")
    if owns_karaoke:
        tier.append("- Karaoke add-on (lifetime)")
    if cloud_library_active:
        tier.append("- Cloud Library subscription (active)")
    tier_s = "\n".join(tier) or "- No paid tier (manually issued)"
    return (
        f"Your BIG Hat Entertainment license\n\n"
        f"Thanks for your purchase. Your license key is:\n\n"
        f"    {key}\n\n"
        f"Tier:\n{tier_s}\n\n"
        f"Download the app at {config.api_base_url()}/api/downloads/auto?key={key}\n"
        f"(or pick manually at {config.api_base_url()}/download)\n"
        f"Paste the key into the Setup Wizard on first launch.\n\n"
        f"The key binds to up to 3 machines (5 with an active Cloud Library\n"
        f"subscription). All add-ons unlock on every bound machine.\n"
        f"Questions? {config.support_email()}\n\n"
        f"— BIG Hat Entertainment"
    )


def _subscription_canceled_html(key: str) -> str:
    support = config.support_email()
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>{_STYLE}</style></head>
<body><div class="card">
  <h1>Your Cloud Library subscription was canceled</h1>
  <p>We've processed the cancellation of your $5/mo Cloud Library subscription.
     Your desktop app will continue to work offline with all features you paid
     for on the one-time purchase tier.</p>
  <p class="small">License key: <span class="key">{key}</span></p>
  <p>You can resubscribe anytime from <a href="{config.brand_base_url()}/cloud-library">{config.brand_base_url()}/cloud-library</a>.</p>
  <hr class="divider"/>
  <p class="small">Didn't expect this? <a href="mailto:{support}">{support}</a></p>
</div></body></html>"""


# ---------- Service ----------
class ResendEmailSender:
    """Async wrapper around the synchronous Resend SDK.

    If `RESEND_API_KEY` is missing, every send logs a warning and returns
    `False` so the license flow can continue in dev/test without email.
    """

    def __init__(self, api_key: Optional[str] = None, sender: Optional[str] = None):
        self.api_key = api_key if api_key is not None else config.resend_api_key()
        self.sender = sender if sender is not None else config.sender_email()
        if self.api_key:
            resend.api_key = self.api_key

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    async def _send(self, *, to: str, subject: str, html: str, text: str) -> bool:
        if not self.enabled:
            logger.warning("RESEND_API_KEY not set; skipping email to %s (%s)", to, subject)
            return False
        params = {
            "from":    self.sender,
            "to":      [to],
            "subject": subject,
            "html":    html,
            "text":    text,
        }
        try:
            result = await asyncio.to_thread(resend.Emails.send, params)
            logger.info("sent email id=%s to=%s subject=%r",
                        result.get("id") if isinstance(result, dict) else "?",
                        to, subject)
            return True
        except Exception as e:
            logger.error("resend send failed for %s: %s", to, e)
            return False

    async def send_license_key_email(
        self,
        *,
        to: str,
        key: str,
        owns_standalone: bool,
        cloud_library_active: bool,
        owns_music_bingo: bool = False,
        owns_karaoke: bool = False,
    ) -> bool:
        subject = "Your BIG Hat Entertainment license"
        return await self._send(
            to=to, subject=subject,
            html=_license_key_html(key, owns_standalone=owns_standalone,
                                   cloud_library_active=cloud_library_active,
                                   owns_music_bingo=owns_music_bingo,
                                   owns_karaoke=owns_karaoke),
            text=_license_key_text(key, owns_standalone=owns_standalone,
                                   cloud_library_active=cloud_library_active,
                                   owns_music_bingo=owns_music_bingo,
                                   owns_karaoke=owns_karaoke),
        )

    async def send_subscription_canceled(self, *, to: str, key: str) -> bool:
        return await self._send(
            to=to,
            subject="Your Cloud Library subscription was canceled",
            html=_subscription_canceled_html(key),
            text=(f"Your $5/mo Cloud Library subscription was canceled. "
                  f"Desktop app keeps working for your lifetime tier.\n"
                  f"Key: {key}\nResubscribe: {config.brand_base_url()}/cloud-library"),
        )
