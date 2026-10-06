"""Product keys (alpha.80): lets the owner enter an add-on key later.

Rules:
  * The MAIN key is license_status.key. It is never replaced by an add-on key.
  * Any other key is kept in subscription.extra_keys and its add-ons are MERGED
    (OR-ed) into the owned flags, so nothing already unlocked is switched off.
  * Add-ons only work when the base program is owned (existing rule).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

from .config import config_manager
from .license import is_well_formed_license
from .subscription import get_subscription, set_subscription

logger = logging.getLogger(__name__)

ADDONS = ("music_bingo", "karaoke")


def _sub() -> Dict[str, Any]:
    return config_manager.config.setdefault("subscription", {})


def main_key() -> str:
    return ((config_manager.config.get("license_status") or {}).get("key") or "").upper()


def list_extra_keys() -> List[Dict[str, Any]]:
    return list(_sub().get("extra_keys") or [])


def mask(key: str) -> str:
    key = key or ""
    return key if len(key) <= 8 else key[:4] + "…" + key[-4:]


def merge_into_flags(resp: Dict[str, Any]) -> None:
    """OR the cloud answer for an extra key into the owned flags and re-derive
    the feature flags exactly like the main path does."""
    sub = _sub()
    owns_base = bool(sub.get("owns_standalone")) or bool(resp.get("owns_standalone"))
    owns_bingo = bool(sub.get("owns_music_bingo")) or bool(resp.get("owns_music_bingo"))
    owns_karaoke = bool(sub.get("owns_karaoke")) or bool(resp.get("owns_karaoke"))
    cloud_lib = bool(sub.get("cloud_library_active")) or bool(resp.get("cloud_library_active"))
    flags = {
        "sharepoint_enabled": cloud_lib,
        "story_generator_enabled": owns_base,
        "music_bingo_enabled": owns_base and owns_bingo,
        "karaoke_enabled": owns_base and owns_karaoke,
        "bingo_story_enabled": owns_base and owns_bingo,
        "karaoke_story_enabled": owns_base and owns_karaoke,
    }
    set_subscription(
        active=bool(owns_base or cloud_lib),
        tier="premium" if cloud_lib else "standalone" if owns_base else "free",
        expires_at=sub.get("expires_at") or resp.get("cloud_library_expires_at"),
        feature_flags=flags,
    )
    sub = _sub()
    sub["owns_standalone"] = owns_base
    sub["owns_music_bingo"] = owns_bingo
    sub["owns_karaoke"] = owns_karaoke
    sub["cloud_library_active"] = cloud_lib
    config_manager.save_config()


def remember_extra_key(key: str, resp: Dict[str, Any]) -> None:
    sub = _sub()
    extra = [e for e in (sub.get("extra_keys") or []) if e.get("key") != key]
    extra.append({
        "key": key,
        "added_at": datetime.now(timezone.utc).isoformat(),
        "unlocks": [a for a in ADDONS if resp.get(f"owns_{a}")],
    })
    sub["extra_keys"] = extra
    config_manager.save_config()


def public_status() -> Dict[str, Any]:
    sub = get_subscription() or {}
    s = _sub()
    return {
        "main_key": mask(main_key()),
        "owns_standalone": bool(s.get("owns_standalone")),
        "addons": {
            "music_bingo": bool(s.get("owns_music_bingo")),
            "karaoke": bool(s.get("owns_karaoke")),
        },
        "extra_keys": [
            {"key": mask(e.get("key", "")), "added_at": e.get("added_at"),
             "unlocks": e.get("unlocks", [])}
            for e in list_extra_keys()
        ],
        "last_checked": s.get("last_cloud_validated_at"),
        "tier": sub.get("tier"),
    }


def reapply_saved_extras() -> None:
    """After the main key refreshes the flags, put back what the saved add-on
    keys unlocked (the main key's answer does not know about them)."""
    for e in list_extra_keys():
        merge_into_flags({f"owns_{a}": True for a in e.get("unlocks", [])})
