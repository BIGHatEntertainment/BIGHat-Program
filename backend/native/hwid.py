"""
Hardware-ID generator.

Mimics the V30 Rust core (`generate_hwid`) using SHA-256 over a stable
system fingerprint. Pure Python so dev environments without Rust toolchain
still produce a deterministic ID. The Windows native installer can override
this with the compiled Rust DLL by exporting the env var BIGHAT_HWID.
"""
from __future__ import annotations

import hashlib
import os
import platform
import socket
import uuid


def _stable_fingerprint() -> str:
    """Build a deterministic, single-machine fingerprint."""
    parts = [
        platform.system(),
        platform.machine(),
        platform.node(),
        # MAC address (48-bit) of one NIC — stable across reboots
        f"{uuid.getnode():012x}",
        socket.gethostname(),
    ]
    # On Windows, prefer the SystemBiosVersion / disk serial via env if set
    for env_key in ("BIGHAT_MACHINE_ID", "COMPUTERNAME"):
        if os.environ.get(env_key):
            parts.append(f"{env_key}={os.environ[env_key]}")
    return "|".join(parts)


def generate_hwid(salt: str = "bighat-v1") -> str:
    """Return a 64-char hex SHA-256 HWID. Deterministic per machine."""
    override = os.environ.get("BIGHAT_HWID")
    if override:
        return override.lower().strip()
    fingerprint = f"{salt}::{_stable_fingerprint()}"
    return hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()
