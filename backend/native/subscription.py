"""
Subscription / premium-feature gate.

Usage in routes:

    from native.subscription import require_premium

    @api_router.get("/cloud/sync", dependencies=[Depends(require_premium())])
    async def cloud_sync(): ...

Or inline:

    if not is_premium_active():
        raise HTTPException(402, detail="premium_required")

Feature flags:
  - sharepoint_enabled
  - story_generator_enabled
  - cloud_sync_enabled
If any one flag is True the user has *some* premium access, but each route
can require a specific flag.

Phase 10.2 — Offline grace:
  When the desktop has previously seen a successful cloud activation
  (`last_cloud_validated_at`), we honour that snapshot for `OFFLINE_GRACE_DAYS`
  even if the cloud server is unreachable. Past the grace window, premium
  features re-gate to free until the next successful `cloud_validate()`.
  The standalone purchase is NEVER gated by network — owners keep all
  one-time-purchase features forever.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException

from .config import config_manager

ALL_FEATURES = (
    "sharepoint_enabled",
    "story_generator_enabled",
    "cloud_sync_enabled",
)

OFFLINE_GRACE_DAYS = int(os.environ.get("BIGHAT_OFFLINE_GRACE_DAYS", "30"))


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def get_subscription() -> dict:
    sub = dict(config_manager.config.get("subscription", {}))
    sub.setdefault("active", False)
    sub.setdefault("tier", "free")
    sub.setdefault("expires_at", None)
    for f in ALL_FEATURES:
        sub.setdefault(f, False)
    return sub


def is_premium_active(feature: Optional[str] = None) -> bool:
    sub = get_subscription()

    # Standalone-purchase features (e.g. story_generator_enabled) are NEVER
    # gated by network — once `owns_standalone=True` the customer keeps them.
    if feature == "story_generator_enabled" and sub.get("owns_standalone"):
        return True

    if not sub.get("active"):
        return False

    expires_at = sub.get("expires_at")
    if expires_at:
        try:
            exp = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
            if exp < _now_utc():
                return False
        except (ValueError, TypeError):
            return False

    # Offline grace: if we have a successful cloud validation in the past
    # `OFFLINE_GRACE_DAYS`, the cached subscription remains active even
    # without a fresh online check. Past the window we degrade to free.
    last_validated = sub.get("last_cloud_validated_at")
    if last_validated:
        try:
            seen = datetime.fromisoformat(str(last_validated).replace("Z", "+00:00"))
            if seen + timedelta(days=OFFLINE_GRACE_DAYS) < _now_utc():
                return False
        except (ValueError, TypeError):
            # Corrupt timestamp — fail closed for cloud-tier features only.
            return False

    if feature:
        return bool(sub.get(feature, False))
    return True


def require_premium(feature: Optional[str] = None):
    """Returns a FastAPI dependency that 402s when subscription is inactive."""
    async def _dep():
        if not is_premium_active(feature):
            raise HTTPException(
                status_code=402,
                detail={
                    "error": "premium_required",
                    "feature": feature,
                    "message": (
                        f"This feature ({feature}) requires an active subscription."
                        if feature
                        else "This feature requires an active subscription."
                    ),
                },
            )
        return True
    return _dep


def set_subscription(
    active: bool,
    tier: str = "premium",
    expires_at: Optional[str] = None,
    feature_flags: Optional[dict] = None,
) -> dict:
    cfg = config_manager.config
    sub = cfg.setdefault("subscription", {})
    sub["active"] = bool(active)
    sub["tier"] = tier
    sub["expires_at"] = expires_at
    sub["last_check"] = _now_utc().isoformat()
    if feature_flags:
        for k, v in feature_flags.items():
            if k in ALL_FEATURES:
                sub[k] = bool(v)
    elif active and tier in ("premium", "enterprise"):
        for f in ALL_FEATURES:
            sub[f] = True
    elif not active:
        for f in ALL_FEATURES:
            sub[f] = False
    config_manager.save_config()
    return sub
