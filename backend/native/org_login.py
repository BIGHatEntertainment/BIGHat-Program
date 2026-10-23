"""Program side of the ORGANIZATION LOGIN (memory/SYNC_CONTRACT.md "Organization login"; Cloud PR #31, live on host.bighat.live).

Anyone in the Cloud organization may sign in on any linked PC. The Cloud is asked EVERY time (no offline Cloud login, owner decision
2026-10-21/22). The Cloud answers only yes/no and {email, name, role, is_admin, phone}: no password, no hash, no token ever reaches this PC.

What this module decides (server.py's /api/auth/login calls it; the local login runs first and is unchanged):
  * `cloud_check(email, password)`   one call to POST /api/program/auth/login, tagged result, never raises, never logs the password.
  * `should_ask_cloud(local_user)`   who may be sent to the Cloud:
        - no local account at all                                   -> yes (a Cloud person signing in for the first time)
        - a local account made by the Cloud pull that nobody has ever signed in to with a real password (temporary password)
                                                                    -> yes (the only thing they can be typing is their Cloud password)
        - a copied Cloud account (auth_method "cloud")              -> yes, and the Cloud decides FIRST (every time)
        - a HAND-MADE program account with a wrong password         -> NEVER (no extra guessing surface; contract rule)
        - the local master admin                                    -> NEVER
  * `role_for_cloud(role)`           account_owner -> admin (never master_admin), host -> host.
  * `adopt(...)`                     after a Cloud success: make the local account match (same password both places), never touch the master.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import httpx

from . import cloud_link

logger = logging.getLogger("bighat-org-login")

CLOUD_ROLE_TO_LOCAL = {"account_owner": "admin", "host": "host"}
MESSAGES = {
    "invalid_credentials": "Invalid email or password",
    "deactivated": "This account has been deactivated. Ask your account owner.",
    "unreachable": "Can't reach the BIG Hat Cloud to check this sign-in. Connect to the internet and try again.",
    "rate_limited": "Too many attempts. Try again in 15 minutes.",
    "subscription_lapsed": "This organization's Cloud subscription has lapsed. Ask your account owner.",
    "unlinked": "This computer is no longer linked to the BIG Hat Cloud.",
    "not_linked": "",
    "error": "Could not check this sign-in with the BIG Hat Cloud right now.",
}


def is_linked() -> bool:
    try:
        return bool(cloud_link.get_token() and cloud_link.cloud_base_url())
    except Exception:                                              # noqa: BLE001
        return False


def role_for_cloud(role: Any) -> Optional[str]:
    """Cloud role -> local role. Anything else (including a platform master_admin) is refused: returns None."""
    return CLOUD_ROLE_TO_LOCAL.get(str(role or "").strip().lower())


async def cloud_check(email: str, password: str) -> Dict[str, Any]:
    """Ask the Cloud. Returns {ok: True, user: {...}} or {ok: False, error: <key of MESSAGES>}. Never raises."""
    tok = cloud_link.get_token() if is_linked() else None
    if not tok:
        return {"ok": False, "error": "not_linked"}
    try:
        async with httpx.AsyncClient(timeout=15.0) as c:
            r = await c.post(f"{cloud_link.cloud_base_url()}/api/program/auth/login",
                             json={"email": str(email or "").strip().lower(), "password": str(password or "")},
                             headers={"Authorization": f"Bearer {tok}"})
    except (httpx.HTTPError, ValueError):
        return {"ok": False, "error": "unreachable"}
    code = ""
    body: Dict[str, Any] = {}
    try:
        body = r.json() or {}
        code = str(body.get("error") or "")
    except ValueError:
        pass
    if r.status_code == 200 and body.get("ok") is True and isinstance(body.get("user"), dict):
        u = body["user"]
        role = role_for_cloud(u.get("role"))
        if not role or not str(u.get("email") or "").strip():
            return {"ok": False, "error": "invalid_credentials"}       # a role this PC does not know (e.g. a platform account): never signed in
        # The Cloud's own is_admin decides (an account_owner is always admin; a host the owner flagged admin keeps that here).
        is_admin = bool(u.get("is_admin")) or role == "admin"
        return {"ok": True, "user": {"email": str(u["email"]).strip().lower(), "name": str(u.get("name") or "").strip(),
                                     "role": "admin" if is_admin else role, "is_admin": is_admin, "phone": u.get("phone") or None}}
    if r.status_code == 402 or code == "subscription_lapsed":
        return {"ok": False, "error": "subscription_lapsed"}
    if r.status_code == 429 or code == "rate_limited":
        return {"ok": False, "error": "rate_limited"}
    if r.status_code == 403 and code == "deactivated":
        return {"ok": False, "error": "deactivated"}
    if r.status_code == 401 and code in ("unlinked", "unauthorized"):
        return {"ok": False, "error": "unlinked"}
    if r.status_code == 401:
        return {"ok": False, "error": "invalid_credentials"}
    if r.status_code >= 500 or r.status_code == 404:
        return {"ok": False, "error": "unreachable"}
    return {"ok": False, "error": "error"}


async def pulled_with_temp_password(db, local_user: Dict[str, Any]) -> bool:
    """True for a person the Cloud pull made here and that nobody has signed in to with a real password yet.
    The data pull's id map points at the EMPLOYEE row it created ('created': true); that row's e-mail is the link to this login."""
    if (local_user.get("auth_method") or "local") != "local":
        return False
    try:
        from . import cloud_sync
        email = str(local_user.get("email") or "").strip().lower()
        if not email:
            return False
        for m in (cloud_sync._read().get("ids", {}).get("person") or {}).values():
            if not m.get("created") or not m.get("local_id"):
                continue
            emp = await db.employees.find_one({"id": m["local_id"]}, {"_id": 0, "email": 1})
            if emp and str(emp.get("email") or "").strip().lower() == email:
                return True
        return False
    except Exception:                                              # noqa: BLE001
        return False


async def should_ask_cloud(db, local_user: Optional[Dict[str, Any]], password_was_right: bool) -> bool:
    """See the module docstring. `password_was_right` is the result of the LOCAL check (False when there is no local account)."""
    if not is_linked():
        return False
    if local_user is None:
        return True
    if local_user.get("is_master") or local_user.get("role") == "master_admin":
        return False
    if (local_user.get("auth_method") or "local") == "cloud":
        return True                                                # copied Cloud account: the Cloud decides every time
    if password_was_right:
        return False                                               # a normal local login is untouched
    return await pulled_with_temp_password(db, local_user)


async def adopt(db, cloud_user: Dict[str, Any], password: str, existing: Optional[Dict[str, Any]], copy_account: bool) -> Optional[Dict[str, Any]]:
    """After a Cloud success. Returns the local (config) user to sign in as, or None when nothing is saved here (a one-visit sign-in).
      * a person already here (pulled or copied earlier): the local password is set to the one the Cloud just accepted ("same credentials in both"),
        the name/phone/role follow the Cloud, auth_method becomes "cloud". The master admin is never touched.
      * a person with no account here: created only when `copy_account` is true (the person said yes to "Copy my account to this computer?").
    The password goes into the local hash (bcrypt) and nowhere else; it is never logged."""
    from . import admin_router, employee_sync
    email = cloud_user["email"]
    if existing is not None and (existing.get("is_master") or existing.get("role") == "master_admin"):
        return None
    now = datetime.now(timezone.utc).isoformat()
    first, last = employee_sync._split_name(cloud_user.get("name") or "")
    if existing is not None:
        if (existing.get("auth_method") or "local") == "local" and not await pulled_with_temp_password(db, existing):
            return existing                                        # a hand-made program account is never rewritten by a Cloud sign-in
        existing["password_hash"] = employee_sync._hash(password)
        existing["auth_method"] = "cloud"
        existing["role"] = cloud_user["role"]
        existing["is_admin"] = bool(cloud_user.get("is_admin"))
        if cloud_user.get("name"):
            existing["first_name"], existing["last_name"] = first or existing.get("first_name", ""), last
            existing["display_name"] = existing.get("display_name") or cloud_user["name"]
        existing["updated_at"] = now
        admin_router._save_config()
        await admin_router._mirror_to_db(existing)
        return existing
    if not copy_account:
        return None
    import uuid
    from .config import config_manager
    user = {
        "id": str(uuid.uuid4()), "email": email, "password_hash": employee_sync._hash(password),
        "first_name": first, "last_name": last, "display_name": cloud_user.get("name") or email,
        "phone": cloud_user.get("phone"), "role": cloud_user["role"], "is_admin": bool(cloud_user.get("is_admin")),
        "is_master": False, "enabled": True, "auth_method": "cloud", "created_at": now,
    }
    config_manager.config.setdefault("users", []).append(user)
    admin_router._save_config()
    await admin_router._mirror_to_db(user)
    return user
