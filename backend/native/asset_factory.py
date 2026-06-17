"""
Asset-service factory — `LOCAL ONLY` since v31.0.13.

Previously this module decided whether to talk to the BIG Hat-hosted
SharePoint or to the local file system based on the customer's premium
subscription. v31.0.13 removed the file-cloud distribution feature
entirely (premium content packs are now sold as .bighat files on
Squarespace instead), so this module now unconditionally returns the
LocalAssetService.

Kept as a thin shim so the dozen route files that import
`get_asset_service` / `can_use_cloud` continue to compile without
needing per-route changes. The host's own SharePoint integration (used
internally by Round Maker, Slide Fetcher, Story Builds for their own
asset library — NOT customer-facing content distribution) is unchanged
and still gated by the env-var-driven host setup.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Cached singleton — only one service exists now.
_local_svc = None


def can_use_cloud() -> bool:
    """v31.0.13: file-cloud distribution removed. Always returns False.
    Callers receive LocalAssetService and read from the local asset folder.
    """
    return False


def get_asset_service():
    """Always return the LocalAssetService."""
    global _local_svc
    if _local_svc is None:
        from .local_asset_service import LocalAssetService
        _local_svc = LocalAssetService()
    return _local_svc


def reset_cache() -> None:
    """For tests — drop the cached service instance."""
    global _local_svc
    _local_svc = None
