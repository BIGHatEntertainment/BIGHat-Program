"""
Native-Standalone module for BIG Hat Hub.

Provides the infrastructure layer that turns the BIGHat-Fullstack webapp into
a native standalone Windows program:

- `config`     — system_config.json manager (V30-style)
- `hwid`       — hardware-ID generator (SHA-256 of stable system fingerprint)
- `license`    — 5-seat license enforcement
- `subscription` — premium-feature gate (Local-First; cloud features behind sub)
- `router`     — `/api/native/*` HTTP endpoints (setup wizard, status, license)

Design principles:
- **Additive**: importing this module never breaks the existing webapp.
- **No Mongo dependency**: this module only touches the local file-system.
- **Native-mode flag**: env var `BIGHAT_NATIVE_MODE=1` enables full standalone
  behaviour (forces setup wizard on first boot, blocks Google OAuth,
  enforces seat licensing). Default OFF — webapp continues to behave normally.
"""
from .config import config_manager  # noqa: F401
from .subscription import is_premium_active, require_premium  # noqa: F401
from .hwid import generate_hwid  # noqa: F401
