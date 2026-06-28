"""Contract test for v32.0.0-alpha.22 Trivia Setup: locations router.

Covers:
  • master_admin can create, edit, delete locations and assign admins
  • admin sees only locations they're assigned to
  • host gets 403 on every endpoint
  • image upload writes to disk + DB, raw fetch streams the bytes back
  • reorder rewrites .order and tolerates stale/missing IDs
  • delete location wipes both DB row and on-disk branding folder
"""
from __future__ import annotations

import asyncio
import io
import os
from pathlib import Path

import pytest

mongomock_motor = pytest.importorskip("mongomock_motor")
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from backend.native import locations_router as lr


# ---------- fixtures ----------
def _user(role: str, uid: str = "u-1", email: str = "u@example.com") -> dict:
    # Mirror `get_current_user`: canonical id is `_id` (stringified).
    return {"_id": uid, "id": uid, "role": role, "email": email, "name": "Test"}


@pytest.fixture
def app_with_user(tmp_path, monkeypatch):
    """Build a FastAPI app whose locations router is wired to a fresh in-
    memory DB. Auth is mocked via a query-string `?as=role:id` for
    convenience — each test composes the user it needs."""
    client = mongomock_motor.AsyncMongoMockClient()
    db = client["bighat_test"]
    lr.set_database(db)

    async def resolver(request: Request):
        spec = request.query_params.get("as") or "host:anon"
        role, _, uid = spec.partition(":")
        return _user(role or "host", uid or "anon", f"{uid or 'anon'}@example.com")
    lr.set_current_user_resolver(resolver)

    # Redirect on-disk asset root to the tmpdir so the test doesn't write
    # into the real Documents/BIGHat folder.
    monkeypatch.setenv("BIGHAT_ASSETS_DIR", str(tmp_path / "assets"))

    app = FastAPI()
    app.include_router(lr.router, prefix="/api")
    return TestClient(app), db, tmp_path


# ---------- auth ----------
def test_host_cannot_list_locations(app_with_user):
    client, _, _ = app_with_user
    r = client.get("/api/native/locations?as=host:h1")
    assert r.status_code == 403
    assert r.json()["detail"] == "admin_or_master_required"


def test_host_cannot_create(app_with_user):
    client, _, _ = app_with_user
    r = client.post("/api/native/locations?as=host:h1", json={"name": "Chicago"})
    assert r.status_code == 403


def test_admin_cannot_create(app_with_user):
    client, _, _ = app_with_user
    r = client.post("/api/native/locations?as=admin:a1", json={"name": "Chicago"})
    assert r.status_code == 403
    assert r.json()["detail"] == "master_admin_required"


# ---------- master_admin CRUD ----------
def test_master_creates_and_lists(app_with_user):
    client, _, _ = app_with_user
    r = client.post("/api/native/locations?as=master_admin:m1",
                    json={"name": "Phoenix East"})
    assert r.status_code == 201, r.text
    loc = r.json()
    assert loc["name"] == "Phoenix East"
    assert loc["slug"] == "phoenix-east"
    assert loc["assigned_user_ids"] == []
    assert loc["branding_images"] == []

    r = client.get("/api/native/locations?as=master_admin:m1")
    assert r.status_code == 200
    out = r.json()
    assert len(out) == 1 and out[0]["slug"] == "phoenix-east"


def test_slug_collisions_get_suffixed(app_with_user):
    client, _, _ = app_with_user
    a = client.post("/api/native/locations?as=master_admin:m1",
                    json={"name": "Chicago"}).json()
    b = client.post("/api/native/locations?as=master_admin:m1",
                    json={"name": "Chicago"}).json()
    c = client.post("/api/native/locations?as=master_admin:m1",
                    json={"name": "Chicago"}).json()
    assert a["slug"] == "chicago"
    assert b["slug"] == "chicago-2"
    assert c["slug"] == "chicago-3"


# ---------- admin scoping ----------
def test_admin_sees_only_assigned_locations(app_with_user):
    client, _, _ = app_with_user
    a = client.post("/api/native/locations?as=master_admin:m1",
                    json={"name": "Chicago"}).json()
    b = client.post("/api/native/locations?as=master_admin:m1",
                    json={"name": "Cleveland"}).json()
    # Assign admin a1 to Chicago only.
    r = client.patch(f"/api/native/locations/{a['id']}/admins?as=master_admin:m1",
                     json={"assigned_user_ids": ["a1"]})
    assert r.status_code == 200

    listing = client.get("/api/native/locations?as=admin:a1").json()
    assert {x["slug"] for x in listing} == {"chicago"}

    # Admin can read their own location, but its assigned_user_ids
    # is stripped from the view (admins shouldn't see peer assignments).
    r = client.get(f"/api/native/locations/{a['id']}?as=admin:a1")
    assert r.status_code == 200
    assert "assigned_user_ids" not in r.json()

    # And they can't touch the other one.
    r = client.get(f"/api/native/locations/{b['id']}?as=admin:a1")
    assert r.status_code == 403
    assert r.json()["detail"] == "not_assigned_to_location"


def test_admin_can_rename_assigned_location(app_with_user):
    client, _, _ = app_with_user
    a = client.post("/api/native/locations?as=master_admin:m1",
                    json={"name": "Chicago"}).json()
    client.patch(f"/api/native/locations/{a['id']}/admins?as=master_admin:m1",
                 json={"assigned_user_ids": ["a1"]})
    r = client.patch(f"/api/native/locations/{a['id']}?as=admin:a1",
                     json={"name": "Chicago Downtown"})
    assert r.status_code == 200
    assert r.json()["name"] == "Chicago Downtown"


def test_admin_cannot_delete(app_with_user):
    client, _, _ = app_with_user
    a = client.post("/api/native/locations?as=master_admin:m1",
                    json={"name": "Chicago"}).json()
    client.patch(f"/api/native/locations/{a['id']}/admins?as=master_admin:m1",
                 json={"assigned_user_ids": ["a1"]})
    r = client.delete(f"/api/native/locations/{a['id']}?as=admin:a1")
    assert r.status_code == 403


def test_admin_cannot_reassign(app_with_user):
    client, _, _ = app_with_user
    a = client.post("/api/native/locations?as=master_admin:m1",
                    json={"name": "Chicago"}).json()
    client.patch(f"/api/native/locations/{a['id']}/admins?as=master_admin:m1",
                 json={"assigned_user_ids": ["a1"]})
    r = client.patch(f"/api/native/locations/{a['id']}/admins?as=admin:a1",
                     json={"assigned_user_ids": ["a1", "a2"]})
    assert r.status_code == 403


# ---------- images ----------
_PNG_MAGIC = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc"
    b"\xf8\xcf\xc0\x00\x00\x00\x03\x00\x01\x16\xfc\xa1\xfb\x00\x00\x00\x00IEND\xaeB`\x82"
)


def test_image_upload_writes_disk_and_db(app_with_user):
    client, db, tmp_path = app_with_user
    a = client.post("/api/native/locations?as=master_admin:m1",
                    json={"name": "Chicago"}).json()
    r = client.post(
        f"/api/native/locations/{a['id']}/images?as=master_admin:m1",
        files={"file": ("logo.png", _PNG_MAGIC, "image/png")},
    )
    assert r.status_code == 201, r.text
    rec = r.json()
    assert rec["mime"] == "image/png"
    assert rec["size"] == len(_PNG_MAGIC)
    assert rec["order"] == 0

    # File hit disk under the expected slug path.
    disk = tmp_path / "assets" / "02_Locations" / "chicago" / "branding"
    files = list(disk.iterdir())
    assert len(files) == 1
    assert files[0].read_bytes() == _PNG_MAGIC

    # Streamed back from /raw.
    r = client.get(
        f"/api/native/locations/{a['id']}/images/{rec['id']}/raw?as=master_admin:m1"
    )
    assert r.status_code == 200
    assert r.content == _PNG_MAGIC
    assert r.headers["content-type"].startswith("image/png")


def test_image_upload_rejects_pdf(app_with_user):
    client, _, _ = app_with_user
    a = client.post("/api/native/locations?as=master_admin:m1",
                    json={"name": "Chicago"}).json()
    r = client.post(
        f"/api/native/locations/{a['id']}/images?as=master_admin:m1",
        files={"file": ("rules.pdf", b"%PDF-1.4 nope", "application/pdf")},
    )
    assert r.status_code == 415


def test_reorder_rewrites_indexes_and_keeps_missing_ids_at_end(app_with_user):
    client, _, _ = app_with_user
    a = client.post("/api/native/locations?as=master_admin:m1",
                    json={"name": "Chicago"}).json()
    ids = []
    for i in range(3):
        rec = client.post(
            f"/api/native/locations/{a['id']}/images?as=master_admin:m1",
            files={"file": (f"img{i}.png", _PNG_MAGIC, "image/png")},
        ).json()
        ids.append(rec["id"])

    # Reverse the order; include a stale UUID that the server must ignore.
    r = client.patch(
        f"/api/native/locations/{a['id']}/images/order?as=master_admin:m1",
        json={"image_ids": [ids[2], "ghost-id", ids[1], ids[0]]},
    )
    assert r.status_code == 200
    new_order = [i["id"] for i in r.json()["branding_images"]]
    assert new_order == [ids[2], ids[1], ids[0]]
    # Indexes were rewritten 0..N-1.
    assert [i["order"] for i in r.json()["branding_images"]] == [0, 1, 2]


def test_delete_image_removes_file_and_recomputes_order(app_with_user):
    client, _, tmp_path = app_with_user
    a = client.post("/api/native/locations?as=master_admin:m1",
                    json={"name": "Chicago"}).json()
    ids = []
    for i in range(3):
        rec = client.post(
            f"/api/native/locations/{a['id']}/images?as=master_admin:m1",
            files={"file": (f"img{i}.png", _PNG_MAGIC, "image/png")},
        ).json()
        ids.append(rec["id"])

    r = client.delete(
        f"/api/native/locations/{a['id']}/images/{ids[1]}?as=master_admin:m1"
    )
    assert r.status_code == 204

    loc = client.get(f"/api/native/locations/{a['id']}?as=master_admin:m1").json()
    remaining = [i["id"] for i in loc["branding_images"]]
    assert remaining == [ids[0], ids[2]]
    assert [i["order"] for i in loc["branding_images"]] == [0, 1]

    # And the deleted file is gone from disk.
    disk = tmp_path / "assets" / "02_Locations" / "chicago" / "branding"
    on_disk = {p.stem for p in disk.iterdir()}
    assert ids[1] not in on_disk


def test_delete_location_wipes_folder(app_with_user):
    client, _, tmp_path = app_with_user
    a = client.post("/api/native/locations?as=master_admin:m1",
                    json={"name": "Chicago"}).json()
    client.post(
        f"/api/native/locations/{a['id']}/images?as=master_admin:m1",
        files={"file": ("logo.png", _PNG_MAGIC, "image/png")},
    )
    folder = tmp_path / "assets" / "02_Locations" / "chicago"
    assert folder.is_dir() and any(folder.rglob("*.png"))

    r = client.delete(f"/api/native/locations/{a['id']}?as=master_admin:m1")
    assert r.status_code == 204
    assert not folder.exists()
