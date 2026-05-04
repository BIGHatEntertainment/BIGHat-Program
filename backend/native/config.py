"""
Native system configuration manager.

Ports V30's `core/config_manager.py` and extends it with:
- subscription block (active, expires_at, tier, key)
- audit timestamps (created_at, updated_at)
- atomic write (tempfile + rename) so the config is never corrupted on crash

The config file lives at `BIGHAT_CONFIG_PATH` env var, or defaults to
`/app/backend/native/system_config.json` in dev. In production (Windows native),
the launcher overrides this to `C:\\BIG Hat\\system_config.json`.
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


DEFAULT_CONFIG_PATH = Path(
    os.environ.get(
        "BIGHAT_CONFIG_PATH",
        str(Path(__file__).parent / "system_config.json"),
    )
)


def _default_data_root() -> str:
    return os.environ.get(
        "BIGHAT_DATA_ROOT",
        str(Path(__file__).parent / "data"),
    )


def _default_config() -> Dict[str, Any]:
    _root = _default_data_root()
    return {
        "schema_version": 1,
        "setup_complete": False,
        "instance_id": str(uuid.uuid4()),
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "paths": {
            "data_root": _root,
            "local_trivia": os.environ.get("BIGHAT_TRIVIA_DIR", str(Path(_root) / "trivia")),
            "assets": os.environ.get("BIGHAT_ASSETS_DIR", str(Path(_root) / "assets")),
            "generated": os.environ.get("BIGHAT_GENERATED_DIR", str(Path(_root) / "generated")),
        },
        "settings": {
            "company_name": "BIG Hat Entertainment",
            "location_name": "",
            "city": "",
            "state": "AZ",
            "trivia_source": "local",  # 'local' | 'cloud'
            "asset_source": "local",   # 'local' | 'cloud'
        },
        "license_status": {
            "key": None,
            "master_admin_email": None,
            "total_seats_allowed": 5,
            "active_seats": [],   # list of {hwid, registered_at, label}
            "is_active": False,
        },
        "subscription": {
            "active": False,
            "tier": "free",  # 'free' | 'premium' | 'enterprise'
            "expires_at": None,
            "last_check": None,
            "sharepoint_enabled": False,
            "story_generator_enabled": False,
            "cloud_sync_enabled": False,
        },
        "users": [],  # populated by setup wizard — master admin first
    }


class ConfigManager:
    """Thread-safe JSON config persisted to disk with atomic writes."""

    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = Path(config_path or DEFAULT_CONFIG_PATH)
        self._lock = threading.RLock()
        self.config: Dict[str, Any] = self.load_config()

    # ----- I/O -----
    def load_config(self) -> Dict[str, Any]:
        with self._lock:
            if self.config_path.exists():
                try:
                    with open(self.config_path, "r", encoding="utf-8") as f:
                        cfg = json.load(f)
                    # Forward-compatible: merge missing keys from defaults
                    defaults = _default_config()
                    return _deep_merge(defaults, cfg)
                except (json.JSONDecodeError, OSError):
                    # Corrupted — back up and start fresh
                    backup = self.config_path.with_suffix(".corrupt.json")
                    try:
                        self.config_path.rename(backup)
                    except OSError:
                        pass
                    return _default_config()
            return _default_config()

    def save_config(self, new_config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        with self._lock:
            if new_config:
                self.config = _deep_merge(self.config, new_config)
            self.config["updated_at"] = _now_iso()
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            # Atomic write
            fd, tmp_path = tempfile.mkstemp(
                prefix=".sysconf-",
                suffix=".tmp",
                dir=str(self.config_path.parent),
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(self.config, f, indent=2, default=str)
                os.replace(tmp_path, self.config_path)
            except Exception:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
            return self.config

    # ----- Helpers -----
    def is_setup_required(self) -> bool:
        return not self.config.get("setup_complete", False)

    def is_native_mode(self) -> bool:
        return os.environ.get("BIGHAT_NATIVE_MODE", "0") in ("1", "true", "True", "yes")

    def public_view(self) -> Dict[str, Any]:
        """Return a safe-for-frontend view (no password hashes, no secrets)."""
        with self._lock:
            cfg = json.loads(json.dumps(self.config, default=str))  # deep copy
        # Strip secrets
        for u in cfg.get("users", []):
            u.pop("password_hash", None)
            u.pop("password", None)
        lic = cfg.get("license_status", {})
        if lic.get("key"):
            k = lic["key"]
            lic["key"] = (k[:4] + "…" + k[-4:]) if len(k) > 8 else "…"
        return cfg


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively merge override into base, returning a new dict."""
    out = dict(base)
    for k, v in override.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


# Singleton shared across the backend
config_manager = ConfigManager()
