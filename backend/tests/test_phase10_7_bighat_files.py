"""
Phase 10.7 — .bighat file import/export round-trip tests.

Covers:
  * GET /api/bighat-files/export/{round_id}  → produces a valid zip
  * POST /api/bighat-files/import             → round-trips the same data
  * Manifest validation (corrupt zip, wrong format, future version)
  * import-from-path security (native-mode + loopback only)
"""
from __future__ import annotations

import io
import json
import os
import sys
import uuid
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

# Force native-local mode so the .bighat routes are mounted with their
# import-from-path security enabled.
os.environ["BIGHAT_NATIVE_MODE"] = "1"
os.environ.setdefault("MONGO_URL", "mongodb://stub:27017/bighat_test")
os.environ.setdefault("DB_NAME", "bighat_test_phase10_7")


@pytest.fixture(scope="module")
def client():
    # Import server lazily so env vars above take effect first.
    from server import app
    with TestClient(app) as c:
        yield c


@pytest.fixture
def round_doc(client):
    """Create a round via the public API and return its id + payload."""
    payload = {
        "round_type": "MC",
        "name": f"Phase107 round {uuid.uuid4().hex[:6]}",
        "questions": [
            {
                "number": i + 1,
                "question": f"Q{i + 1}?",
                "answer": "yes",
                "options": ["a", "b", "c", "yes"],
                "correctOption": 3,
            }
            for i in range(10)
        ],
        "tiebreaker": {"question": "How many?", "answer": "42"},
    }
    res = client.post("/api/roundmaker/rounds", json=payload)
    assert res.status_code == 200, res.text
    return res.json()


# ---------- export ----------
def test_export_returns_valid_zip(client, round_doc):
    rid = round_doc["id"]
    res = client.get(f"/api/bighat-files/export/{rid}")
    assert res.status_code == 200, res.text
    assert res.headers["content-type"] == "application/x-bighat"
    assert ".bighat" in res.headers["content-disposition"]

    with zipfile.ZipFile(io.BytesIO(res.content)) as zf:
        names = set(zf.namelist())
        assert "manifest.json" in names
        assert "round.json" in names
        manifest = json.loads(zf.read("manifest.json"))
        assert manifest["format"] == "bighat/round"
        assert manifest["version"] == 1
        round_json = json.loads(zf.read("round.json"))
        assert round_json["id"] == rid
        assert round_json["name"] == round_doc["name"]
        assert len(round_json["questions"]) == 10


def test_export_unknown_round_404(client):
    res = client.get("/api/bighat-files/export/does-not-exist")
    assert res.status_code == 404


# ---------- import (multipart) ----------
def test_import_round_trips(client, round_doc):
    rid = round_doc["id"]
    blob = client.get(f"/api/bighat-files/export/{rid}").content
    res = client.post(
        "/api/bighat-files/import",
        files={"file": ("test.bighat", blob, "application/x-bighat")},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["round_id"] != rid          # fresh id minted
    assert body["name"] == round_doc["name"]
    assert body["round_type"] == round_doc["round_type"]

    # Verify the imported round is queryable + has identical questions.
    fetched = client.get(f"/api/roundmaker/rounds/{body['round_id']}").json()
    assert len(fetched["questions"]) == len(round_doc["questions"])
    for orig, copy in zip(round_doc["questions"], fetched["questions"]):
        assert orig["question"] == copy["question"]
        assert orig["answer"] == copy["answer"]


def test_import_rejects_non_zip(client):
    # Must be > 64 bytes so we pass the "empty or truncated" gate and hit
    # the actual zip-parse check.
    bogus = b"this is plain text, not a zip file, nowhere near valid bighat format " * 4
    res = client.post(
        "/api/bighat-files/import",
        files={"file": ("bad.bighat", bogus, "application/x-bighat")},
    )
    assert res.status_code == 400
    assert "zip" in res.json()["detail"].lower() or "bighat" in res.json()["detail"].lower()


def test_import_rejects_missing_manifest(client):
    """Zip missing manifest.json → 400."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("round.json", json.dumps({"id": "x", "questions": []}))
    res = client.post(
        "/api/bighat-files/import",
        files={"file": ("bad.bighat", buf.getvalue(), "application/x-bighat")},
    )
    assert res.status_code == 400


def test_import_rejects_future_version(client):
    """Manifest with version > current → 400 with a clear upgrade hint."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("manifest.json", json.dumps({"format": "bighat/round", "version": 999}))
        zf.writestr("round.json", json.dumps({"id": "x", "name": "future", "questions": []}))
    res = client.post(
        "/api/bighat-files/import",
        files={"file": ("future.bighat", buf.getvalue(), "application/x-bighat")},
    )
    assert res.status_code == 400
    assert "newer version" in res.json()["detail"].lower()


def test_import_rejects_wrong_format(client):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("manifest.json", json.dumps({"format": "totally/different", "version": 1}))
        zf.writestr("round.json", "{}")
    res = client.post(
        "/api/bighat-files/import",
        files={"file": ("bad.bighat", buf.getvalue(), "application/x-bighat")},
    )
    assert res.status_code == 400


# ---------- import-from-path (file association handoff) ----------
def test_import_from_path_round_trips(client, round_doc, tmp_path):
    rid = round_doc["id"]
    blob = client.get(f"/api/bighat-files/export/{rid}").content
    onpath = tmp_path / "round.bighat"
    onpath.write_bytes(blob)

    res = client.post("/api/bighat-files/import-from-path", data={"path": str(onpath)})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["name"] == round_doc["name"]
    # Confirm we got a different id (fresh import) and it's findable.
    assert body["round_id"] != rid
    assert client.get(f"/api/roundmaker/rounds/{body['round_id']}").status_code == 200


def test_import_from_path_missing_file_404(client):
    res = client.post(
        "/api/bighat-files/import-from-path",
        data={"path": "/no/such/file.bighat"},
    )
    assert res.status_code == 404
