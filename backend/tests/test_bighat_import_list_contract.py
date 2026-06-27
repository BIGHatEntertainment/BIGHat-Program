"""Contract test for v32.0.0-alpha.21: imported third-party `.bighat`
files MUST show up in `GET /api/roundmaker/rounds`.

The alpha.19 fix made `_parse_bighat` accept files that lacked a
`format` field but carried a round-type code (MC/BIG/REG/...) in
`manifest.type`. The import itself succeeded — the row landed in
`db.rounds` — but the dashboard kept reporting "No rounds yet".

Root cause: `_import_zip_bytes` inserted a doc missing the
`round_type` and `status` fields that `RoundResponse` declares
non-optional. Calling `RoundResponse(**r)` on that row threw a
Pydantic ValidationError. The list endpoint constructs every row
in one comprehension, so one bad row turned the whole response
into a 500 — silently rendered as an empty list by the
dashboard's `catch` block.

This test pins the contract on both sides:
  1. `_import_zip_bytes` writes a doc whose shape can be parsed by
     `RoundResponse`.
  2. `list_rounds` survives pre-fix legacy rows (status / round_type
     missing) by backfilling on read.
"""
from __future__ import annotations

import asyncio
import io
import json
import os
import zipfile

import pytest

# Use the lightweight mongomock-motor double so the test doesn't
# touch the real database. The desktop sidecar uses motor in the
# same way, so the contract holds.
mongomock_motor = pytest.importorskip("mongomock_motor")

from backend.routes import bighat_files as bf_module
from backend.routes import roundmaker as rm_module
from backend.routes.roundmaker import RoundResponse, list_rounds


def _build_third_party_bighat(*, round_type_code: str = "MC",
                              include_status: bool = False,
                              include_format: bool = False) -> bytes:
    """Replicate exactly what the customer's external generator
    produces: a ZIP with a manifest that carries the round-type code
    in `type`, NO `format`, NO `status`/`round_type` in the payload.
    """
    manifest = {
        "type": round_type_code,
        "version": 1,
        "name": f"BIG_Cactus League ({round_type_code})",
    }
    if include_format:
        manifest["format"] = "bighat"
    payload = {
        "name": f"BIG_Cactus League ({round_type_code})",
        "questions": [
            {"number": 1, "question": "What desert is the saguaro cactus from?",
             "answer": "Sonoran"},
        ],
    }
    if include_status:
        payload["status"] = "draft"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest))
        zf.writestr("payload.json", json.dumps(payload))
    return buf.getvalue()


@pytest.fixture
def fake_db(monkeypatch):
    """Wire both routers up to a fresh in-memory mongomock-motor DB."""
    client = mongomock_motor.AsyncMongoMockClient()
    db = client["bighat_test"]
    bf_module.set_database(db)
    rm_module.db = db
    return db


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


@pytest.mark.parametrize("round_type_code", ["MC", "BIG", "REG", "MISC", "MYS", "round"])
def test_third_party_bighat_imports_and_lists(fake_db, round_type_code):
    """The full customer journey: external generator ships a .bighat
    with no `format` and a round-type code in `type` — after import,
    the round MUST be in `list_rounds`."""
    payload = _build_third_party_bighat(round_type_code=round_type_code)

    # Import
    result = _run(bf_module._import_zip_bytes(payload))
    assert result.name.startswith("BIG_Cactus League")
    assert result.type == "round"

    # List
    rounds = _run(list_rounds())
    assert len(rounds) == 1, "imported round must appear in the dashboard list"
    r = rounds[0]
    assert isinstance(r, RoundResponse)
    assert r.id == result.id
    assert r.status == "draft"
    # For non-canonical aliases the alias is preserved in round_type;
    # for the canonical "round" type, the backfill picks MC.
    expected_rt = (round_type_code.upper()
                   if round_type_code.lower() != "round" else "MC")
    assert r.round_type == expected_rt, (
        f"expected round_type={expected_rt}, got {r.round_type} — the "
        f"third-party generator's round KIND must be preserved as the "
        f"`round_type` field so the Generator UI picks the right template."
    )


def test_list_rounds_tolerates_legacy_broken_rows(fake_db):
    """A pre-alpha.21 install will have rows in `db.rounds` that are
    missing `round_type` and `status` entirely. `list_rounds` must
    backfill them on read instead of 500-ing the whole endpoint."""
    # Insert a deliberately under-spec'd row that mirrors what the
    # alpha.19 import wrote.
    _run(fake_db.rounds.insert_one({
        "id": "legacy-round-1",
        "name": "Legacy Imported Round",
        "questions": [],
        "created_at": "2026-02-27T00:00:00+00:00",
    }))
    rounds = _run(list_rounds())
    assert len(rounds) == 1
    assert rounds[0].id == "legacy-round-1"
    assert rounds[0].status == "draft"
    assert rounds[0].round_type == "MC"


def test_list_rounds_skips_unrenderable_row(fake_db):
    """If a row is so broken even the backfill can't fix it (e.g. the
    `id` field is missing), the list endpoint logs and skips that row
    rather than 500-ing the whole response."""
    _run(fake_db.rounds.insert_one({
        "name": "No-id round",
        "questions": [],
        "created_at": "2026-02-27T00:00:00+00:00",
    }))
    _run(fake_db.rounds.insert_one({
        "id": "good-round-1",
        "name": "Good round",
        "questions": [],
        "created_at": "2026-02-27T00:01:00+00:00",
    }))
    rounds = _run(list_rounds())
    ids = {r.id for r in rounds}
    assert "good-round-1" in ids
    # The no-id row was silently skipped.
    assert len(rounds) == 1
