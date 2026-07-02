"""v32.0.0-alpha.32 regression:

  Alpha.31 shipped /api/trivia/hosts returning `path=""` when the master
  admin had not yet uploaded a 16:9 slide GIF. In the frontend the
  Trivia Builder Wizard renders each host as `<SelectItem value={host.path}>`.
  Radix UI throws when a SelectItem has value="" (it reserves the empty
  string for the placeholder), which cascaded up and blanked the whole
  app to a navy screen with no recovery.

  This test locks in:
    1. Every host row has a non-empty `path`.
    2. When no image is uploaded, `path` falls back to the sentinel
       `"host:<id>"` so the SelectItem stays valid.
    3. The backend error-report sink accepts arbitrary payloads and
       responds `{"ok": True}` (never 500s during frontend teardown).
"""
from __future__ import annotations
import asyncio


def _run_hosts():
    import sys
    sys.path.insert(0, "/app/backend")
    from routes.trivia import get_hosts
    return asyncio.run(get_hosts())


def test_every_host_has_non_empty_path():
    hosts = _run_hosts()
    assert isinstance(hosts, list)
    empties = [h for h in hosts if not h.get("path")]
    assert not empties, (
        f"host rows with empty path would crash Radix SelectItem: {empties!r}"
    )


def test_missing_image_falls_back_to_host_sentinel():
    """If any host has no host_image_16x9, its path must be the
    `host:<id>` sentinel so the SelectItem still renders."""
    hosts = _run_hosts()
    for h in hosts:
        img = h.get("host_image_16x9") or ""
        path = h.get("path") or ""
        if not img:
            assert path.startswith("host:"), (
                f"missing-image row {h.get('name')!r} must use host:<id> "
                f"sentinel, got path={path!r}"
            )


def test_error_report_endpoint_never_raises():
    """The error boundary posts fire-and-forget during React teardown.
    The route must accept malformed payloads without 500-ing."""
    import sys
    sys.path.insert(0, "/app/backend")
    from native.router import report_frontend_error

    async def _run():
        # Nominal payload
        out1 = await report_frontend_error({"message": "boom", "stack": "x"})
        assert out1 == {"ok": True}
        # Bizarre payload — must still return ok
        out2 = await report_frontend_error({})
        assert out2 == {"ok": True}
        # Non-string values — must still return ok
        out3 = await report_frontend_error({"message": 42, "stack": None,
                                            "componentStack": ["a","b"]})
        assert out3 == {"ok": True}

    asyncio.run(_run())
