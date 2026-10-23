"""Program side of the Cloud's person PROFILE and SETTINGS (Cloud PR #34, additive keys on the `person` item).

The Cloud sends, per person: display_name, first_name, last_name, home_city (phone was already pulled) and `settings`, a small object.
This module applies them to the person's login row on this PC (system_config.json users[], mirrored to db.users and to the host's
Files/Hosts/<slug>/host.json that the Wizard and the slides read).

Rules (the owner has zero tolerance for silent data loss; the master admin is never changed):
  * Only these text fields are taken, trimmed and capped. Settings keep ONLY the keys the Cloud allows, with the Cloud's own limits;
    an unknown key or a bad value is dropped here too, so a changed or hostile Cloud cannot put anything else on this PC.
  * A value changed on THIS PC since the last pull wins: the Cloud's value is skipped and logged as a conflict (same rule as the schedule).
  * An empty Cloud value never erases what is here.
  * The master admin and any person without a login row here are left alone.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional

TEXT_FIELDS = {"display_name": 120, "first_name": 80, "last_name": 80, "home_city": 120}
ASPECTS = ("landscape", "portrait")
SETTINGS_MAX_BYTES = 8 * 1024


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def clean_text(v: Any, cap: int) -> str:
    if not isinstance(v, str):
        return ""
    return " ".join(v.replace("\r", " ").replace("\n", " ").split())[:cap]


def clean_settings(raw: Any) -> Dict[str, Any]:
    """The Cloud's allow-list and limits, enforced again here: theme (str, 32), default_aspect (landscape|portrait),
    default_venue_id (str, 64), notify_schedule (bool), language (str, 8). Anything else is dropped."""
    if not isinstance(raw, dict):
        return {}
    out: Dict[str, Any] = {}
    t = raw.get("theme")
    if isinstance(t, str) and t.strip():
        out["theme"] = clean_text(t, 32)
    a = raw.get("default_aspect")
    if a in ASPECTS:
        out["default_aspect"] = a
    v = raw.get("default_venue_id")
    if isinstance(v, str) and v.strip():
        out["default_venue_id"] = clean_text(v, 64)
    n = raw.get("notify_schedule")
    if isinstance(n, bool):
        out["notify_schedule"] = n
    lang = raw.get("language")
    if isinstance(lang, str) and lang.strip():
        out["language"] = clean_text(lang, 8)
    if len(json.dumps(out)) > SETTINGS_MAX_BYTES:
        return {}
    return out


def extract(data: Dict[str, Any]) -> Dict[str, Any]:
    """The profile part of a Cloud `person` item, cleaned. Empty values are left out (they never erase anything)."""
    prof: Dict[str, Any] = {}
    for k, cap in TEXT_FIELDS.items():
        val = clean_text(data.get(k), cap)
        if val:
            prof[k] = val
    s = clean_settings(data.get("settings"))
    if s:
        prof["settings"] = s
    return prof


def fingerprint(user: Dict[str, Any]) -> str:
    blob = json.dumps({k: user.get(k) for k in list(TEXT_FIELDS) + ["settings"]}, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def snapshot(email: str) -> Optional[Dict[str, Any]]:
    """The profile fields of this person's login RIGHT NOW (before the schedule's name logic touches them), or None."""
    from native import employee_sync
    u = employee_sync.find_user(email)
    if not u or employee_sync.is_master(u):
        return None
    return {k: u.get(k) for k in list(TEXT_FIELDS) + ["settings"] if k in u}


def restore(email: str, snap: Optional[Dict[str, Any]]) -> None:
    """upsert_user_for_employee re-splits `name` into first/last/display_name on every pull. That is right for a person with no profile,
    but it would undo a real one, so the fields it overwrote are put back (the Cloud's values are then applied on top by apply_profile)."""
    from native import employee_sync, admin_router
    u = employee_sync.find_user(email)
    if not snap or not u or employee_sync.is_master(u):
        return
    changed = False
    for k in ("display_name", "first_name", "last_name"):
        if k in snap and u.get(k) != snap[k]:
            u[k] = snap[k]
            changed = True
    if changed:
        admin_router._save_config()


async def apply_profile(ctx, cid: str, email: str, data: Dict[str, Any], before: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """Apply one person's profile. Returns None, or a reason it was held back. Never raises."""
    from native import employee_sync, admin_router
    try:
        prof = extract(data)
        user = employee_sync.find_user(email)
        if not user or employee_sync.is_master(user):
            return None
        m = ctx.ids("person").get(cid) or {}
        last = m.get("pfp")
        if before is not None:
            restore(email, before)
        if not prof:
            return None
        cur_fp = fingerprint(user)
        if last and cur_fp != last:
            ctx.conflict("person", cid, f"the profile of '{user.get('display_name') or email}' was changed on this PC")
            return "changed_here"
        if all(user.get(k) == v for k, v in prof.items()):
            m["pfp"] = cur_fp
            ctx.ids("person")[cid] = {**m}
            return None
        for k, v in prof.items():
            user[k] = v
        if "display_name" in prof or "first_name" in prof or "last_name" in prof:
            user["display_name"] = user.get("display_name") or f"{user.get('first_name', '')} {user.get('last_name', '')}".strip()
        user["updated_at"] = _now()
        admin_router._save_config()
        try:
            await admin_router._mirror_to_db(user)
            if admin_router._db is not None and prof.get("home_city"):
                await admin_router._db.users.update_one({"email": email}, {"$set": {"home_city": prof["home_city"]}})
        except Exception:                                          # noqa: BLE001  the config file is the truth; the mirror rebuilds from it
            pass
        try:
            from native.files_router import write_host_profile_json
            write_host_profile_json(user)
        except Exception:                                          # noqa: BLE001
            pass
        ctx.ids("person")[cid] = {**m, "pfp": fingerprint(user)}
        return None
    except Exception:                                              # noqa: BLE001  one person's profile never stops the pull
        return "error"
