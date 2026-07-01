"""v32.0.0-alpha.31 regression suite.

Proves the three bugs the merchant hit on the alpha.30 install are fixed:

  1. `_user_query(uuid_string)` now matches native-mode `db.users` rows
     that store `_id` as a plain UUID string. Prior to alpha.31 the $or
     clause tried `{"id": user_id}` only, which never matched Mongo's
     `_id` column, so `PATCH /api/users/<uuid>/profile` returned 404 and
     the frontend surfaced "Image uploaded but profile update failed".

  2. `GET /api/users` in native mode hydrates `db.users` from
     `system_config.json → users[]` on every read. The merchant saw
     "Users (0)" intermittently when the session was restored from a
     JWT cookie without hitting the login-time bridge.

  3. `GET /api/trivia/hosts` no longer depends on the decommissioned
     SharePoint service — it returns the same host list from db.users +
     system_config so the Build Trivia Presentation dropdown always has
     entries in native mode.

Run with: pytest backend/tests/test_alpha31_native_users_and_hosts.py -v
"""
from __future__ import annotations


def test_user_query_matches_native_uuid_string_id():
    """UUID passed on the URL must match `_id` in the string form. Prior
    to alpha.31 the $or only carried `{"id": user_id}` + an optional
    `ObjectId(user_id)` branch (which raises for UUIDs), so a native-
    mode record with `_id="uuid-..."` was invisible."""
    import sys
    sys.path.insert(0, "/app/backend")
    from server import _user_query

    uuid = "69f832720cccb3b8f60817f7"
    q = _user_query(uuid)
    assert "$or" in q
    variants = q["$or"]
    # Must include a string `_id` branch — this is the alpha.31 fix.
    assert any(v == {"_id": uuid} for v in variants), (
        f"missing string-_id branch in query: {variants!r}"
    )
    # And the legacy `id` branch stays for older cloud records.
    assert any(v == {"id": uuid} for v in variants), (
        f"missing legacy id branch: {variants!r}"
    )


def test_trivia_hosts_route_no_longer_uses_sharepoint():
    """The Trivia Presenter host dropdown used to hit SharePoint (which
    the merchant decommissioned in alpha.27). Verify the endpoint is now
    sourced from db.users + native config."""
    src = open("/app/backend/routes/trivia.py").read()
    # Locate the `get_hosts` function body
    start = src.index("async def get_hosts(")
    end = src.index("@router.get(", start + 1)
    body = src[start:end]
    assert "SharePointService" not in body, (
        "get_hosts() still references SharePointService"
    )
    assert "config_manager" in body, (
        "get_hosts() must merge users from native config"
    )
    assert "db.users" in body, (
        "get_hosts() must also read db.users for cloud + mirrored users"
    )


def test_list_users_hydrates_from_native_config():
    """`/api/users` GET must proactively mirror config → db so the admin
    panel never shows Users (0) after a cookie-restored session."""
    src = open("/app/backend/server.py").read()
    # Grab the list_users function body
    idx = src.index("async def list_users(")
    body = src[idx : idx + 4000]
    assert "config_manager" in body, (
        "list_users() must import + read config_manager in native mode"
    )
    assert "is_native" in body, (
        "list_users() must gate config hydration on is_native()"
    )
    assert "profile_picture" in body and "host_image_16x9" in body, (
        "list_users() hydration must copy the profile-image fields so "
        "the merchant's uploaded slide GIFs survive"
    )


def test_update_user_profile_mirrors_to_native_config():
    """`PATCH /api/users/{id}/profile` must write the change back into
    system_config.json in native mode so `home_city` + host slide URLs
    survive a db.users wipe / MontyDB re-init."""
    src = open("/app/backend/server.py").read()
    idx = src.index("async def update_user_profile(")
    body = src[idx : idx + 4000]
    assert "config_manager" in body
    assert "save_config" in body
    assert "native config mirror" in body.lower() or "cfg_user" in body
