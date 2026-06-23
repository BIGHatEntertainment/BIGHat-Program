"""Resolves the latest installer URL per platform.

Two layers of lookup, in order:

1. Environment variables `DOWNLOAD_URL_WINDOWS` / `DOWNLOAD_URL_MACOS` /
   `DOWNLOAD_URL_MACOS_INTEL`. If set, used verbatim (escape hatch for
   ops to pin a specific build).
2. GitHub `releases/latest` lookup against `GITHUB_OWNER/GITHUB_REPO`.
   Uses an optional `GITHUB_RELEASES_TOKEN` for higher rate-limit
   (5000/h authenticated vs 60/h anonymous). Cached for 5 minutes so
   we don't hammer GitHub on every store click.

Asset selection (case-insensitive substring match on filename):
* windows         → "windows" or ".exe"
* macos_apple     → "macos-applesilicon" or "applesilicon" or "arm64" or "aarch64"
* macos_intel     → "macos-intel" or "intel" or "x86_64" or "x64"
* macos           → falls back to apple-silicon if both arches present
"""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request
from typing import Optional

from . import config

logger = logging.getLogger("bighat-downloads")

# In-memory cache: {key: (expires_at_epoch, value)}.
_CACHE: dict[str, tuple[float, dict]] = {}
_CACHE_TTL_SECONDS = 300


def _github_token() -> Optional[str]:
    return (
        os.environ.get("GITHUB_RELEASES_TOKEN")
        or os.environ.get("GITHUB_TOKEN")
        or None
    )


def _gh_owner_repo() -> tuple[Optional[str], Optional[str]]:
    return (
        os.environ.get("GITHUB_OWNER"),
        os.environ.get("GITHUB_REPO"),
    )


def _fetch_latest_release() -> dict:
    """Return the parsed `releases/latest` JSON for the configured repo,
    cached for 5 minutes. Returns `{}` on any failure so callers can
    gracefully degrade."""
    cached = _CACHE.get("latest")
    now = time.time()
    if cached and cached[0] > now:
        return cached[1]

    owner, repo = _gh_owner_repo()
    if not owner or not repo:
        logger.info("[downloads] GITHUB_OWNER/REPO not set; cannot resolve latest release")
        return {}

    url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "bighat-downloads-resolver",
    }
    tok = _github_token()
    if tok:
        headers["Authorization"] = f"Bearer {tok}"

    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        logger.warning(f"[downloads] GitHub HTTP {e.code} fetching latest release: {e.reason}")
        # Negative-cache for 30s so a brief 4xx doesn't tank every request.
        _CACHE["latest"] = (now + 30, {})
        return {}
    except Exception as e:
        logger.warning(f"[downloads] error fetching latest release: {e}")
        _CACHE["latest"] = (now + 30, {})
        return {}

    _CACHE["latest"] = (now + _CACHE_TTL_SECONDS, data)
    return data


# Asset-name matchers (case-insensitive substring).
_MATCHERS: dict[str, tuple[str, ...]] = {
    "windows":     ("windows", ".exe"),
    "macos_apple": ("macos-applesilicon", "applesilicon", "arm64", "aarch64"),
    "macos_intel": ("macos-intel", "-intel", "x86_64", "x64"),
}


def _pick_asset(assets: list[dict], platform_key: str) -> Optional[dict]:
    needles = _MATCHERS.get(platform_key, ())
    for a in assets:
        name = (a.get("name") or "").lower()
        if any(n in name for n in needles):
            return a
    return None


def resolve(platform: str) -> dict:
    """Resolve a download for a normalised platform string.

    `platform` ∈ {"windows", "macos", "macos_apple", "macos_intel"}.
    Returns: {"url": str|None, "version": str|None, "filename": str|None,
              "platform": platform, "size": int|None, "source": "env"|"github"|None}.
    """
    env_overrides = {
        "windows":     config.download_url_windows(),
        "macos":       config.download_url_macos(),
        "macos_apple": config.download_url_macos(),
        "macos_intel": os.environ.get("DOWNLOAD_URL_MACOS_INTEL", ""),
    }
    env_url = env_overrides.get(platform, "")
    if env_url:
        return {
            "url": env_url, "version": config.current_release_version(),
            "filename": env_url.rsplit("/", 1)[-1],
            "platform": platform, "size": None, "source": "env",
        }

    rel = _fetch_latest_release()
    if not rel:
        return {"url": None, "version": None, "filename": None,
                "platform": platform, "size": None, "source": None}

    version = (rel.get("tag_name") or "").lstrip("vV")
    assets = rel.get("assets") or []

    # For the generic "macos" alias, prefer Apple Silicon (current Mac default).
    lookup = platform if platform != "macos" else "macos_apple"
    asset = _pick_asset(assets, lookup)
    if not asset and platform == "macos":
        # Fall back to Intel if AS isn't published yet.
        asset = _pick_asset(assets, "macos_intel")

    if not asset:
        return {"url": None, "version": version, "filename": None,
                "platform": platform, "size": None, "source": "github"}

    return {
        "url":      asset.get("browser_download_url"),
        "version":  version,
        "filename": asset.get("name"),
        "platform": platform,
        "size":     asset.get("size"),
        "source":   "github",
    }


def detect_platform(user_agent: str) -> str:
    """Best-effort OS detection from a UA string.
    Returns one of {"windows", "macos_apple", "macos_intel", "unknown"}.

    Apple Silicon vs Intel detection from a UA is unreliable — modern
    Safari reports `Intel Mac OS X` even on M-series — so we default
    Mac to apple-silicon (newer, more common) and let the user pick
    Intel explicitly on the landing page if they need it.
    """
    ua = (user_agent or "").lower()
    if "windows" in ua or "win64" in ua or "win32" in ua:
        return "windows"
    if "mac os x" in ua or "macintosh" in ua or "macos" in ua:
        return "macos_apple"
    return "unknown"


def _bust_cache() -> None:
    """Clear the in-memory release cache. Useful for tests + ops."""
    _CACHE.clear()
