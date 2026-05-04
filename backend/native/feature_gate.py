"""
Native-mode feature gate dependency.

`require_native_premium(feature)` returns a FastAPI dependency that:
- Is a no-op in webapp mode (native_mode=False) — the feature is always
  available in cloud-hosted mode.
- In native mode, returns HTTP 402 `premium_required` unless the named
  subscription feature flag is active.

Typical usage::

    from native.feature_gate import require_native_premium

    @router.post("/generate", dependencies=[Depends(require_native_premium("story_generator_enabled"))])
    async def generate(...): ...

When `feature` is None the gate only checks that subscription.active is
True (any premium tier).
"""
from __future__ import annotations

import os
from typing import Optional

from fastapi import Depends, HTTPException  # noqa: F401 — Depends re-exported

from .subscription import is_premium_active


def _is_native_mode() -> bool:
    return os.environ.get("BIGHAT_NATIVE_MODE", "0") in ("1", "true", "True", "yes")


def require_native_premium(feature: Optional[str] = None):
    """Factory: returns a FastAPI dependency callable."""

    async def _dep():
        # In webapp mode everything is available — no gating.
        if not _is_native_mode():
            return True
        if is_premium_active(feature):
            return True
        raise HTTPException(
            status_code=402,
            detail={
                "error": "premium_required",
                "feature": feature,
                "mode": "native",
                "message": (
                    f"{feature} requires an active premium subscription."
                    if feature
                    else "This feature requires an active premium subscription."
                ),
            },
        )

    return _dep
