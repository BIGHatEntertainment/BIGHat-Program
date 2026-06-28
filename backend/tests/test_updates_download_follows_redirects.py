"""Contract test for v32.0.0-alpha.22: in-app updater follows 302
redirects from GitHub release asset URLs.

What the customer saw on alpha.20: clicking "Download update" returned
`download_failed: Redirect response '302 Found' for url '...'` because
httpx defaults to `follow_redirects=False` and GitHub's release-asset
URLs all 302 to an S3-signed download. Without follow_redirects=True
the client raises on the redirect status before reading bytes.

This test pins the behaviour: spin up a local aiohttp server that
issues a 302 to a second endpoint serving the actual bytes, point the
UpdatesService at it, and assert the file lands on disk with the
correct sha256. If anyone removes `follow_redirects=True` from the
download path again, this test fails with the same error message the
customer reported.
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import socket
import threading
import time
from pathlib import Path

import pytest

aiohttp = pytest.importorskip("aiohttp")
from aiohttp import web

from backend.native.updates_service import UpdateManifest, UpdatesService


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


@pytest.fixture
def redirect_server(tmp_path):
    """Two-endpoint aiohttp server: /asset → 302 → /real-asset →
    real bytes. Mirrors the GitHub-releases → S3-signed-URL flow."""
    payload = b"BIG Hat alpha.21 fake bundle " + os.urandom(512)
    sha = hashlib.sha256(payload).hexdigest()
    port = _free_port()

    async def real_asset(_request):
        return web.Response(body=payload, content_type="application/octet-stream")

    async def asset(_request):
        # 302 mirrors github.com/.../releases/download/<tag>/<file>
        raise web.HTTPFound(location=f"http://127.0.0.1:{port}/real-asset")

    app = web.Application()
    app.router.add_get("/asset", asset)
    app.router.add_get("/real-asset", real_asset)

    loop = asyncio.new_event_loop()
    runner = web.AppRunner(app)

    def start():
        asyncio.set_event_loop(loop)
        loop.run_until_complete(runner.setup())
        site = web.TCPSite(runner, "127.0.0.1", port)
        loop.run_until_complete(site.start())
        loop.run_forever()

    thread = threading.Thread(target=start, daemon=True)
    thread.start()
    time.sleep(0.2)        # wait for the loop to spin up

    yield {"port": port, "payload": payload, "sha": sha}

    # Teardown — stop the loop cleanly.
    loop.call_soon_threadsafe(loop.stop)
    thread.join(timeout=2)


def test_download_follows_github_style_302(redirect_server, tmp_path, monkeypatch):
    monkeypatch.setenv("BIGHAT_GENERATED_DIR", str(tmp_path / "generated"))

    # Stage a VERSION.txt + manifest fixture so the service self-fetches
    # an older "installed" version and resolves the redirecting download
    # URL through the manifest path it ships with.
    (tmp_path / "VERSION.txt").write_text("32.0.0-alpha.20", encoding="utf-8")
    fixture = tmp_path / "manifest.json"
    import json as _json
    fixture.write_text(_json.dumps({
        "latest_version": "32.0.0-alpha.21",
        "download_url":   f"http://127.0.0.1:{redirect_server['port']}/asset",
        "sha256":         redirect_server["sha"],
        "release_notes":  "",
        "release_date":   "",
        "mandatory":      False,
    }), encoding="utf-8")
    monkeypatch.setenv("BIGHAT_UPDATE_MANIFEST_FIXTURE", str(fixture))

    svc = UpdatesService(backend_dir=tmp_path, db=None)
    result = asyncio.get_event_loop().run_until_complete(svc.download())
    staged = result["staged"]
    assert staged["sha_verified"] is True
    assert staged["sha256"] == redirect_server["sha"]
    on_disk = Path(staged["path"]).read_bytes()
    assert on_disk == redirect_server["payload"], (
        "The downloaded file must match the bytes served behind the 302, "
        "proving the client followed the redirect."
    )
