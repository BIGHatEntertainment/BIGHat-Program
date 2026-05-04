"""
Asset-service factory.

Trivia routes (rounds, hosts, locations, sponsors, presentation slides) used
to call `SharePointService` directly. In native mode we want to:

  - default to the local file system (offline-first)
  - upgrade to SharePoint when the user is online AND has an active premium
    subscription with `sharepoint_enabled == True`

This factory hides that decision. Callers do:

    from native.asset_factory import get_asset_service
    svc = get_asset_service()  # SharePoint OR LocalAsset depending on context

The returned object has the small SharePoint API surface used by the routes:
list_folder_contents, list_folder_contents_by_sharing_url, download_file,
download_file_to_bytes, parse_sharepoint_path, download_file_by_item_id,
download_file_by_sharing_url, upload_content, get_access_token, get_site_id,
get_drive_id.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from .config import config_manager
from .subscription import is_premium_active

logger = logging.getLogger(__name__)

# Cached singletons
_local_svc = None
_sharepoint_svc = None


def _is_native_mode() -> bool:
    return os.environ.get("BIGHAT_NATIVE_MODE", "0") in ("1", "true", "True", "yes")


def _trivia_source() -> str:
    return (
        config_manager.config.get("settings", {}).get("trivia_source")
        or config_manager.config.get("settings", {}).get("asset_source")
        or "local"
    )


def can_use_cloud() -> bool:
    """True iff in native mode we should reach SharePoint:
       premium subscription + sharepoint_enabled flag + trivia_source='cloud'.
    """
    if not _is_native_mode():
        return True  # webapp mode always uses SharePoint
    if _trivia_source() != "cloud":
        return False
    return is_premium_active("sharepoint_enabled")


def get_asset_service():
    """Return SharePointService or LocalAssetService based on context."""
    global _local_svc, _sharepoint_svc

    if can_use_cloud():
        if _sharepoint_svc is None:
            try:
                from sharepoint_service import SharePointService

                _sharepoint_svc = SharePointService()
            except Exception as e:
                logger.warning(
                    f"[ASSETS] SharePoint init failed ({e}); falling back to local"
                )
                _sharepoint_svc = None
        if _sharepoint_svc is not None:
            return _sharepoint_svc

    if _local_svc is None:
        from .local_asset_service import LocalAssetService

        _local_svc = LocalAssetService()
    return _local_svc


def reset_cache() -> None:
    """For tests / config reload — drop cached service instances."""
    global _local_svc, _sharepoint_svc
    _local_svc = None
    _sharepoint_svc = None
