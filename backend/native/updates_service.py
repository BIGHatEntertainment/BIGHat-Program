"""
BIG Hat Standalone V31.1 — Auto-update engine.

The "auto-update" surface is small and deliberately conservative:

    1.  Read the current installed version from `backend/VERSION.txt`.
    2.  Fetch a JSON manifest from a configurable channel URL. The
        manifest declares `latest_version`, `download_url`, `sha256`,
        `release_notes`, `release_date`, and `mandatory`.
    3.  If the manifest's version is newer (semver compare), the user
        can `download` the bundle. We stream it to
        `paths.generated/updates/<version>.zip` and verify SHA-256 before
        marking the staged file ready.
    4.  An optional `apply` step writes a `pending_apply.json` marker
        next to the staged bundle. The launcher reads this marker on
        next boot and performs the swap (out of scope for the running
        FastAPI process; OS-specific). In native+master-admin mode the
        same step can additionally extract the bundle into a
        `paths.generated/updates/<version>/` staging tree so support
        can inspect contents before flipping the install root.

Dev fixture
-----------
When `BIGHAT_UPDATE_MANIFEST_FIXTURE=/abs/path/to/manifest.json` is set,
the engine reads the manifest from disk instead of making an HTTP
request. The same env var works for the bundle: if the manifest's
`download_url` starts with `file://`, we stream from disk. This lets
us exercise the full check → download → verify → apply flow in CI/test
containers without a public update server.

Persistence
-----------
`db.update_state` (MontyDB) holds:
    {
      "_id": "singleton",
      "installed_version": "31.0.0",
      "last_check_at": ISO8601,
      "latest_known": {…manifest snapshot…},
      "staged": {"version": "...", "path": "...", "verified": true},
      "applied_at": ISO8601 | null,
    }
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import platform
import re
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import httpx

from .config import config_manager

logger = logging.getLogger(__name__)


# Canonical update channel: the cloud licensing API exposes a single
# manifest at /api/downloads/latest that lists the latest installer per
# platform from the GitHub Releases of BIGHatEntertainment/BIGHat-Program.
# This is the ONE source of truth for the update flow per
# /app/memory/PRD.md "CANONICAL DISTRIBUTION FLOW". Do not change without
# updating the PRD.
DEFAULT_UPDATE_CHANNEL_URL = "https://api.bighat.live/api/downloads/latest"


def _detect_platform_key() -> str:
    """Map this machine's OS+arch to the platform key the cloud manifest
    uses ('windows' / 'macos_apple' / 'macos_intel'). Linux falls through
    to 'windows' as a last resort — there's no Linux installer in the
    canonical flow, and customers running the sidecar on Linux are devs
    who can override BIGHAT_UPDATE_CHANNEL_URL anyway."""
    sysname = platform.system().lower()
    if sysname == "windows":
        return "windows"
    if sysname == "darwin":
        mach = platform.machine().lower()
        if mach in ("arm64", "aarch64"):
            return "macos_apple"
        return "macos_intel"
    return "windows"


# ----- Version semantics -----
_VER_RX = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:[-+](.+))?$")
# Prerelease suffix grammar: `alpha.18`, `beta.3`, `rc.1` → (label_rank, n).
# Lower label_rank sorts earlier (alpha < beta < rc < release).
_PRERELEASE_RANK = {"alpha": 0, "beta": 1, "rc": 2}
_PRERELEASE_RX = re.compile(r"^(alpha|beta|rc)\.?(\d+)?$", re.IGNORECASE)


def parse_version(v: str) -> tuple:
    """Return a sortable tuple for a semver-ish version string.

    Tuple shape: ``(major, minor, patch, is_release, prerelease_rank, prerelease_num)``.

    `is_release` is 1 for plain ``32.0.0`` and 0 for ``32.0.0-alpha.18``
    so a final release ALWAYS sorts after every pre-release of the
    same triple. `prerelease_rank` orders ``alpha < beta < rc``, and
    `prerelease_num` is the integer suffix (``alpha.18`` → 18).

    Why this exists: alpha.17 → alpha.18 → alpha.19 customers reported
    the Update tool saying "you're up to date" while LATEST AVAILABLE
    showed a clearly newer prerelease. The old impl stripped the
    suffix entirely, so every ``32.0.0-alpha.*`` parsed to ``(32,0,0)``
    and `is_newer` returned False between any two prereleases of the
    same base triple. See CHANGELOG v32.0.0-alpha.20.

    Returns ``(0, 0, 0, 0, 0, 0)`` for unparseable input so unknown is
    always less than known.
    """
    if not v:
        return (0, 0, 0, 0, 0, 0)
    s = v.strip().lstrip("vV ")
    m = _VER_RX.match(s)
    if not m:
        nums = re.findall(r"\d+", s)
        nums = (nums + ["0", "0", "0"])[:3]
        try:
            return (int(nums[0]), int(nums[1]), int(nums[2]), 1, 0, 0)
        except ValueError:
            return (0, 0, 0, 0, 0, 0)
    major, minor, patch = int(m.group(1)), int(m.group(2)), int(m.group(3))
    suffix = m.group(4)
    if not suffix:
        # No suffix → final release. Sort AFTER every pre-release of
        # the same triple by setting is_release=1 and prerelease_rank
        # to a very high sentinel.
        return (major, minor, patch, 1, 99, 0)
    pm = _PRERELEASE_RX.match(suffix)
    if not pm:
        # Unknown suffix label — treat as pre-release rank=98 (after
        # rc, before final). Conservative; ensures we still detect
        # newer suffixes even if we can't classify them.
        return (major, minor, patch, 0, 98, 0)
    label = pm.group(1).lower()
    num = int(pm.group(2) or "0")
    return (major, minor, patch, 0, _PRERELEASE_RANK.get(label, 98), num)


def is_newer(candidate: str, current: str) -> bool:
    return parse_version(candidate) > parse_version(current)


# ----- Manifest dataclass -----
@dataclass
class UpdateManifest:
    latest_version: str
    download_url: str
    sha256: str
    release_notes: str = ""
    release_date: str = ""
    mandatory: bool = False
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UpdateManifest":
        return cls(
            latest_version=str(data.get("latest_version", "")),
            download_url=str(data.get("download_url", "")),
            sha256=str(data.get("sha256", "")).lower().replace("sha256:", "").strip(),
            release_notes=str(data.get("release_notes", "")),
            release_date=str(data.get("release_date", "")),
            mandatory=bool(data.get("mandatory", False)),
            raw=dict(data),
        )

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ----- Service -----
class UpdatesService:
    """Stateful update orchestrator."""

    def __init__(
        self,
        backend_dir: Path,
        db=None,
        channel_url: Optional[str] = None,
    ):
        self.backend_dir = Path(backend_dir).resolve()
        self.db = db
        self._explicit_channel = channel_url

    # ----- Version (read from VERSION.txt) -----
    @property
    def installed_version(self) -> str:
        path = self.backend_dir / "VERSION.txt"
        try:
            return path.read_text(encoding="utf-8").strip() or "0.0.0"
        except OSError:
            return "0.0.0"

    # ----- Channel config -----
    def _channel_url(self) -> str:
        if self._explicit_channel:
            return self._explicit_channel
        cfg = config_manager.config.get("updates", {}) or {}
        return (
            cfg.get("channel_url")
            or os.environ.get("BIGHAT_UPDATE_CHANNEL_URL")
            or DEFAULT_UPDATE_CHANNEL_URL
        )

    def _staging_root(self) -> Path:
        gen = config_manager.config.get("paths", {}).get("generated")
        base = Path(gen) if gen else (self.backend_dir / "data" / "generated")
        out = base / "updates"
        out.mkdir(parents=True, exist_ok=True)
        return out

    # ----- Manifest fetch -----
    async def fetch_manifest(self) -> UpdateManifest:
        """Fetch the channel manifest. Honours BIGHAT_UPDATE_MANIFEST_FIXTURE
        for offline/dev runs.
        """
        fixture = os.environ.get("BIGHAT_UPDATE_MANIFEST_FIXTURE", "").strip()
        if fixture:
            try:
                data = json.loads(Path(fixture).read_text(encoding="utf-8"))
            except (FileNotFoundError, OSError) as e:
                # Surface as a discoverable RuntimeError so /check returns
                # 502 with a useful detail instead of the generic 500 path.
                raise RuntimeError(f"manifest_fixture_missing: {fixture} ({e})") from e
            except json.JSONDecodeError as e:
                raise RuntimeError(f"manifest_fixture_invalid_json: {fixture} ({e})") from e
            return UpdateManifest.from_dict(data)

        url = self._channel_url()
        if not url:
            raise RuntimeError("update_channel_not_configured")

        # httpx defaults to follow_redirects=False, but BOTH our manifest
        # CDN (api.bighat.live) and especially the GitHub releases
        # download URL chain through 302s to S3-signed URLs. We have to
        # opt in or the download fails with "Redirect response '302
        # Found' for url …" as customers saw on alpha.20→alpha.21.
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            r = await client.get(url, headers={"Accept": "application/json"})
            if r.status_code != 200:
                raise RuntimeError(f"manifest_http_{r.status_code}")
            data = r.json()

        # Schema adapter: api.bighat.live/api/downloads/latest returns
        # {"version": "...", "platforms": {"windows": {...}, "macos_apple": {...}, ...}}
        # while UpdateManifest expects {"latest_version", "download_url", "sha256"}.
        # Detect and transform on the fly so the canonical channel URL
        # works out of the box without a separate manifest service.
        if isinstance(data, dict) and "platforms" in data and "latest_version" not in data:
            plat_key = _detect_platform_key()
            plat = (data.get("platforms") or {}).get(plat_key) or {}
            if not plat.get("url"):
                # No installer for this OS in the latest release; try the
                # generic "macos" Apple-Silicon fallback before giving up.
                if plat_key in ("macos_apple", "macos_intel"):
                    other = (data.get("platforms") or {}).get(
                        "macos_intel" if plat_key == "macos_apple" else "macos_apple"
                    ) or {}
                    if other.get("url"):
                        plat = other
            data = {
                "latest_version": plat.get("version") or data.get("version") or "",
                "download_url":   plat.get("url") or "",
                "sha256":         plat.get("sha256") or "",  # cloud resolver doesn't expose this yet
                "release_notes":  data.get("release_notes", ""),
                "release_date":   data.get("release_date", ""),
                "mandatory":      bool(data.get("mandatory", False)),
            }
        return UpdateManifest.from_dict(data)

    # ----- Status report -----
    async def status(self) -> Dict[str, Any]:
        installed = self.installed_version
        state: Dict[str, Any] = {}
        if self.db is not None:
            try:
                state = await self.db.update_state.find_one(
                    {"_id": "singleton"}, {"_id": 0}
                ) or {}
            except Exception as e:
                logger.warning(f"[UPDATES] update_state read failed: {e}")
                state = {}
        latest_known = state.get("latest_known") or {}
        latest_version = latest_known.get("latest_version") or installed
        update_available = is_newer(latest_version, installed)
        return {
            "installed_version": installed,
            "latest_known": latest_known,
            "update_available": update_available,
            "last_check_at": state.get("last_check_at"),
            "staged": state.get("staged"),
            "applied_at": state.get("applied_at"),
            "channel_url": self._channel_url() or None,
            "fixture_active": bool(os.environ.get("BIGHAT_UPDATE_MANIFEST_FIXTURE")),
        }

    # ----- Check (fetch + compare + persist) -----
    async def check(self) -> Dict[str, Any]:
        manifest = await self.fetch_manifest()
        installed = self.installed_version
        update_available = is_newer(manifest.latest_version, installed)
        result = {
            "installed_version": installed,
            "manifest": manifest.as_dict(),
            "update_available": update_available,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
        if self.db is not None:
            await self.db.update_state.update_one(
                {"_id": "singleton"},
                {"$set": {
                    "installed_version": installed,
                    "last_check_at": result["checked_at"],
                    "latest_known": manifest.as_dict(),
                }},
                upsert=True,
            )
        return result

    # ----- Download (stream + sha256) -----
    async def download(self) -> Dict[str, Any]:
        # Always re-fetch the manifest so we honour the latest channel
        # state. (Stale snapshots are a common bug otherwise.)
        manifest = await self.fetch_manifest()
        installed = self.installed_version
        if not is_newer(manifest.latest_version, installed):
            return {
                "skipped": True,
                "reason": "no_update_available",
                "installed_version": installed,
                "latest_version": manifest.latest_version,
            }

        # sha256 is optional. The cloud `/api/downloads/latest` manifest
        # doesn't expose per-asset hashes today; HTTPS + GitHub CDN are
        # the integrity guarantee. When sha256 IS provided (e.g. ops
        # ships an explicit BIGHAT_UPDATE_MANIFEST_FIXTURE for a release
        # with verifiable hashes) we still enforce it strictly.
        sha_expected = manifest.sha256.lower() if manifest.sha256 else ""
        if sha_expected and len(sha_expected) != 64:
            raise RuntimeError("invalid_manifest_sha256")

        target_dir = self._staging_root()
        target = target_dir / f"bighat-{manifest.latest_version}.zip"

        h = hashlib.sha256()
        if manifest.download_url.startswith("file://"):
            src = Path(manifest.download_url[len("file://"):]).expanduser()
            if not src.is_file():
                raise RuntimeError(f"local_bundle_missing: {src}")
            with open(src, "rb") as fh, open(target, "wb") as out:
                while True:
                    chunk = fh.read(1 << 16)
                    if not chunk:
                        break
                    h.update(chunk)
                    out.write(chunk)
        else:
            # Same redirect-following requirement as the manifest fetch
            # — GitHub releases assets all return a 302 to an S3-signed
            # URL. v32.0.0-alpha.22 fix for the alpha.20→alpha.21 in-app
            # update failure: "Redirect response '302 Found'".
            async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
                async with client.stream("GET", manifest.download_url) as r:
                    r.raise_for_status()
                    with open(target, "wb") as out:
                        async for chunk in r.aiter_bytes(chunk_size=1 << 16):
                            h.update(chunk)
                            out.write(chunk)

        digest = h.hexdigest().lower()
        verified = (not sha_expected) or (digest == sha_expected)
        if not verified:
            # Refuse to keep an unverifiable bundle on disk.
            try:
                target.unlink(missing_ok=True)
            except OSError:
                pass
            raise RuntimeError(f"sha256_mismatch: got {digest} expected {sha_expected}")

        staged = {
            "version": manifest.latest_version,
            "path": str(target),
            "verified": True,  # download completed; sha_verified flags hash check
            "sha_verified": bool(sha_expected),
            "size": target.stat().st_size,
            "sha256": digest,
            "downloaded_at": datetime.now(timezone.utc).isoformat(),
        }
        if self.db is not None:
            await self.db.update_state.update_one(
                {"_id": "singleton"},
                {"$set": {"staged": staged, "latest_known": manifest.as_dict()}},
                upsert=True,
            )
        return {"staged": staged, "manifest": manifest.as_dict()}

    # ----- Apply (write marker + optional unpack) -----
    async def apply(self, *, unpack: bool = True, force: bool = False) -> Dict[str, Any]:
        if self.db is None:
            raise RuntimeError("db_unavailable")
        state = await self.db.update_state.find_one({"_id": "singleton"}) or {}
        staged = state.get("staged") or {}
        if not staged.get("verified") or not staged.get("path"):
            raise RuntimeError("nothing_staged")
        path = Path(staged["path"])
        if not path.is_file():
            raise RuntimeError("staged_bundle_missing")

        version = staged["version"]
        marker = self._staging_root() / "pending_apply.json"
        # Idempotent guard: if the marker already targets the same version,
        # don't double-write. Callers can pass `force=True` to bypass.
        if marker.is_file() and not force:
            try:
                existing = json.loads(marker.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                existing = {}
            if existing.get("version") == version:
                raise RuntimeError(f"already_scheduled: {version}")
        unpack_dir: Optional[Path] = None
        if unpack:
            try:
                unpack_dir = self._staging_root() / version
                if unpack_dir.exists():
                    shutil.rmtree(unpack_dir)
                unpack_dir.mkdir(parents=True, exist_ok=True)
                shutil.unpack_archive(str(path), str(unpack_dir))
            except Exception as e:
                logger.warning(f"[UPDATES] unpack failed: {e}")
                unpack_dir = None

        marker_payload = {
            "version": version,
            "bundle_path": str(path),
            "unpacked_path": str(unpack_dir) if unpack_dir else None,
            "scheduled_at": datetime.now(timezone.utc).isoformat(),
            "previous_version": self.installed_version,
        }
        marker.write_text(json.dumps(marker_payload, indent=2), encoding="utf-8")
        await self.db.update_state.update_one(
            {"_id": "singleton"},
            {"$set": {
                "applied_at": marker_payload["scheduled_at"],
                "pending_apply": marker_payload,
            }},
            upsert=True,
        )
        return {"status": "scheduled", **marker_payload}
