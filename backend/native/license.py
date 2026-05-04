"""
License / seat-management.

Ported from V30 `core/licensing.py` with:
- 5-seat default enforcement
- HWID-based seat slots (no soft slots; can't borrow seats)
- `register_seat` / `release_seat` operations
- Validation helpers used by FastAPI dependencies

License keys are intentionally simple offline strings of the form:
    BHE-XXXX-XXXX-XXXX-XXXX  (16 alphanumerics, dash-separated)
Real cryptographic key validation can be layered on later when we ship
the online activation server. For Phase 0 a structural check is sufficient.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from .config import config_manager
from .hwid import generate_hwid

LICENSE_RE = re.compile(r"^BHE(?:-[A-Z0-9]{4}){4}$")


def is_well_formed_license(key: str) -> bool:
    if not key:
        return False
    return bool(LICENSE_RE.match(key.strip().upper()))


def get_license_status() -> Dict[str, Any]:
    cfg = config_manager.config
    lic = dict(cfg.get("license_status", {}))
    seats: List[Dict[str, Any]] = lic.get("active_seats", []) or []
    lic["used_seats"] = len(seats)
    lic["total_seats_allowed"] = lic.get("total_seats_allowed", 5)
    lic["seats_remaining"] = max(0, lic["total_seats_allowed"] - lic["used_seats"])
    lic["current_hwid"] = generate_hwid()
    lic["current_hwid_registered"] = any(
        s.get("hwid") == lic["current_hwid"] for s in seats
    )
    # Hide raw key in the public payload
    if lic.get("key"):
        k = lic["key"]
        lic["key_masked"] = (k[:4] + "…" + k[-4:]) if len(k) > 8 else "…"
    return lic


def register_seat(label: Optional[str] = None) -> Tuple[bool, str]:
    """Try to register the current HWID as an active seat.

    Returns (ok, message). If already registered, ok=True with idempotent message.
    """
    cfg = config_manager.config
    lic = cfg.setdefault("license_status", {})
    seats: List[Dict[str, Any]] = lic.setdefault("active_seats", [])
    max_seats = int(lic.get("total_seats_allowed", 5))
    hwid = generate_hwid()

    # Already registered?
    for s in seats:
        if s.get("hwid") == hwid:
            return True, "seat_already_registered"

    if len(seats) >= max_seats:
        return False, "seat_limit_exceeded"

    seats.append(
        {
            "hwid": hwid,
            "label": label or "This computer",
            "registered_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    lic["is_active"] = True
    config_manager.save_config()
    return True, "seat_registered"


def release_seat(hwid: Optional[str] = None) -> Tuple[bool, str]:
    cfg = config_manager.config
    lic = cfg.setdefault("license_status", {})
    seats: List[Dict[str, Any]] = lic.setdefault("active_seats", [])
    target = (hwid or generate_hwid()).lower().strip()
    new_seats = [s for s in seats if s.get("hwid", "").lower() != target]
    if len(new_seats) == len(seats):
        return False, "seat_not_found"
    lic["active_seats"] = new_seats
    config_manager.save_config()
    return True, "seat_released"


def set_license_key(key: str, master_admin_email: Optional[str] = None) -> Tuple[bool, str]:
    key = (key or "").strip().upper()
    if not is_well_formed_license(key):
        return False, "invalid_license_format"
    cfg = config_manager.config
    lic = cfg.setdefault("license_status", {})
    lic["key"] = key
    if master_admin_email:
        lic["master_admin_email"] = master_admin_email
    lic.setdefault("total_seats_allowed", 5)
    config_manager.save_config()
    return True, "license_set"
