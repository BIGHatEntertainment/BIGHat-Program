"""Env-var surface + constants for the cloud licensing service."""
from __future__ import annotations

import os
from typing import Final

# ---- Mode gate ----------------------------------------------------------
def is_cloud_mode() -> bool:
    """True when the process is deployed as `api.bighat.live` (cloud license
    authority). Desktop installer processes have `BIGHAT_NATIVE_MODE=1` and
    should NEVER have `BIGHAT_CLOUD_MODE=1`."""
    return os.environ.get("BIGHAT_CLOUD_MODE") == "1"


# ---- Licensing SKUs -----------------------------------------------------
# These are the Squarespace product SKUs that map to our two tiers.
# You configure these in Squarespace → Products → Edit Product → SKU.
# Override via env if you prefer different SKU strings.
SKU_STANDALONE: Final[str] = os.environ.get("LICENSE_SKU_STANDALONE", "BH-STANDALONE-2499")
SKU_CLOUD_LIBRARY: Final[str] = os.environ.get("LICENSE_SKU_CLOUD_LIBRARY", "BH-CLOUD-LIBRARY-5MO")

# ---- License key format -------------------------------------------------
LICENSE_KEY_PREFIX: Final[str] = "BHE"          # BIG Hat Entertainment
LICENSE_KEY_GROUP_LEN: Final[int] = 4            # chars per group
LICENSE_KEY_GROUP_COUNT: Final[int] = 4          # groups after prefix
# Alphabet excludes visually ambiguous chars: 0/O, 1/I/L
LICENSE_KEY_ALPHABET: Final[str] = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"

# ---- Seat limits --------------------------------------------------------
DEFAULT_MAX_SEATS: Final[int] = 3  # standard comp: 3 HWID bindings per key
CLOUD_LIBRARY_MAX_SEATS: Final[int] = 5

# ---- Offline grace period -----------------------------------------------
# Desktop app stores validate() response; if network is down, it honours
# the last validation for up to this many days before degrading to free.
OFFLINE_GRACE_DAYS: Final[int] = 30

# ---- Re-validate cadence ------------------------------------------------
# Desktop app re-validates at this cadence. Server ALSO enforces by
# returning an `expires_at` hint inside the validate response.
VALIDATION_INTERVAL_DAYS: Final[int] = 7

# ---- Squarespace --------------------------------------------------------
def squarespace_webhook_secret() -> str:
    """HMAC secret for verifying Squarespace webhook signatures. Required
    for the webhook endpoint to accept any traffic in production."""
    return os.environ.get("SQUARESPACE_WEBHOOK_SECRET", "")


def squarespace_api_key() -> str:
    """Squarespace Commerce API key for optional order enrichment."""
    return os.environ.get("SQUARESPACE_API_KEY", "")


# ---- Email --------------------------------------------------------------
def resend_api_key() -> str:
    return os.environ.get("RESEND_API_KEY", "")


def sender_email() -> str:
    return os.environ.get("SENDER_EMAIL", "onboarding@resend.dev")


def support_email() -> str:
    return os.environ.get("SUPPORT_EMAIL", "support@bighat.live")


# ---- Public branding URLs for email copy --------------------------------
def brand_base_url() -> str:
    return os.environ.get("BRAND_BASE_URL", "https://bighat.live")


def api_base_url() -> str:
    """Self-URL used in email templates to deep-link back to the license server."""
    return os.environ.get("LICENSE_API_BASE_URL", "https://api.bighat.live")


# ---- Download URLs (versioned installers) -------------------------------
def download_url_windows() -> str:
    return os.environ.get("DOWNLOAD_URL_WINDOWS", "")


def download_url_macos() -> str:
    return os.environ.get("DOWNLOAD_URL_MACOS", "")


def current_release_version() -> str:
    """Version string shown in download responses. Set from CI when
    publishing a new installer."""
    return os.environ.get("CURRENT_RELEASE_VERSION", "31.0.0")


# ---- Admin JWT ----------------------------------------------------------
def license_admin_secret() -> str:
    """HMAC secret for admin JWTs on `/api/license/admin/*`. Falls back to
    JWT_SECRET (shared with webapp auth) for ops simplicity."""
    return os.environ.get("LICENSE_ADMIN_SECRET") or os.environ.get("JWT_SECRET", "")
