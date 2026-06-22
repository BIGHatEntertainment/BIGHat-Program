"""Always-on diagnostic endpoint for the cloud licensing service.

Unlike `license_router`, this router is registered **regardless of
`BIGHAT_CLOUD_MODE`**. Its purpose is to make production misconfigurations
self-diagnosable: a single `curl https://api.bighat.live/api/license/health`
tells you exactly which env var is missing without needing pod shell access.

Returns 200 with a status dict. Never raises. Designed to be safe to expose
publicly: it only surfaces booleans + non-secret prefixes / lengths.
"""
from __future__ import annotations

import os
import socket

from fastapi import APIRouter

from . import config

router = APIRouter(prefix="/api/license", tags=["cloud-licensing-diagnostic"])


def _masked(value: str, *, show: int = 4) -> str:
    """Return `re_jh***` for non-empty values, empty string otherwise.

    We expose only the configured prefix so an operator can confirm the
    right key is loaded without leaking the secret in logs / screenshots.
    """
    if not value:
        return ""
    return f"{value[:show]}***" if len(value) > show else "***"


@router.get("/health")
async def license_health() -> dict:
    """Cloud licensing self-check. Always 200.

    Use this from CI / monitoring / support to confirm the prod pod is
    running in cloud mode with all required secrets configured. The
    `ready` field is the single rollup: `true` only when every secret
    required to mint + email a license key is present.
    """
    cloud_mode = config.is_cloud_mode()
    native_mode = os.environ.get("BIGHAT_NATIVE_MODE") == "1"

    resend_key = config.resend_api_key()
    webhook_secret = config.squarespace_webhook_secret()
    jwt_secret = config.license_admin_secret()
    sa_key = config.squarespace_api_key()

    # ready = every dep needed to fire the webhook → mint → email pipeline
    ready = bool(
        cloud_mode
        and resend_key
        and webhook_secret
        and jwt_secret
    )

    # Why-not breakdown so the operator sees the missing piece at a glance.
    blockers: list[str] = []
    if not cloud_mode:
        blockers.append("BIGHAT_CLOUD_MODE must be set to '1' (currently unset/0)")
    if native_mode and cloud_mode:
        blockers.append(
            "BIGHAT_CLOUD_MODE and BIGHAT_NATIVE_MODE are both set; cloud "
            "deployments must unset BIGHAT_NATIVE_MODE"
        )
    if not resend_key:
        blockers.append("RESEND_API_KEY missing — license emails will NOT be sent")
    if not webhook_secret:
        blockers.append(
            "SQUARESPACE_WEBHOOK_SECRET missing — webhook will accept "
            "unsigned requests (dev-only behaviour)"
        )
    if not jwt_secret:
        blockers.append("JWT_SECRET / LICENSE_ADMIN_SECRET missing — admin routes unreachable")

    return {
        "ok": True,
        "ready": ready,
        "blockers": blockers,
        "modes": {
            "cloud_mode_enabled": cloud_mode,
            "native_mode_enabled": native_mode,
        },
        "integrations": {
            "resend_configured": bool(resend_key),
            "resend_api_key_prefix": _masked(resend_key),
            "sender_email": config.sender_email(),
            "support_email": config.support_email(),
            "squarespace_webhook_secret_configured": bool(webhook_secret),
            "squarespace_api_key_configured": bool(sa_key),
        },
        "routing": {
            "license_routes_mounted": cloud_mode,
            "webhook_endpoint": "/api/squarespace/webhook",
            "activate_endpoint": "/api/license/activate",
            "validate_endpoint": "/api/license/validate",
        },
        "skus": {
            "standalone": config.SKU_STANDALONE,
            "cloud_library": config.SKU_CLOUD_LIBRARY,
            "music_bingo": config.SKU_MUSIC_BINGO,
            "karaoke": config.SKU_KARAOKE,
        },
        "branding": {
            "brand_base_url": config.brand_base_url(),
            "api_base_url": config.api_base_url(),
            "current_release_version": config.current_release_version(),
        },
        "host": {
            "hostname": socket.gethostname(),
        },
    }
