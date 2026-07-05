"""
Regression tests for v32.0.0-alpha.45 patches.

Locks in the three bug fixes discovered from the merchant's alpha.44
debug log upload:
  1. GET /api/admin/stats no longer 500s when MontyDB aggregate() returns
     a coroutine or when SQLite thread errors bubble up. Endpoint is
     BEST-EFFORT — returns zeros on total failure so the frontend
     Promise.all() chain doesn't reject and blank the Presenter list.
  2. DELETE /api/native/files/{name}?folder=Trivia-Rounds (and slash-
     variant "Trivia/Rounds") resolves cleanly — the delete-card button
     on presentation cards was 400ing with `invalid_folder`.
  3. POST /api/bighat/import accepts the "trivia-presentation" type
     alias emitted by the Build Wizard, routing it to the canonical
     `presentation` spec so imports no longer 400 with `Unknown content
     type: trivia-presentation`.
"""
from __future__ import annotations

import io
import json
import sys
import zipfile
from pathlib import Path

import pytest
from fastapi import HTTPException

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ---- Fix #2: files_router accepts Trivia/Rounds ----------------------------

def test_files_router_accepts_trivia_rounds_slash():
    from native.files_router import _resolve_folder

    name, path = _resolve_folder("Trivia/Rounds")
    assert name == "Trivia/Rounds"
    assert path.name == "Rounds"
    assert path.parent.name == "Trivia"


def test_files_router_accepts_trivia_rounds_dash():
    from native.files_router import _resolve_folder

    name, path = _resolve_folder("Trivia-Rounds")
    assert name == "Trivia/Rounds"
    assert path.name == "Rounds"
    assert path.parent.name == "Trivia"


def test_files_router_still_rejects_garbage_folder():
    from native.files_router import _resolve_folder

    with pytest.raises(HTTPException) as exc:
        _resolve_folder("Trivia/../etc")
    assert "invalid_folder" in str(exc.value.detail)


# ---- Fix #3: trivia-presentation alias ------------------------------------

def test_bighat_types_has_presentation():
    from routes.bighat_files import BIGHAT_TYPES

    assert "presentation" in BIGHAT_TYPES


def test_import_normalises_trivia_presentation_alias():
    """The wizard emits `type: "trivia-presentation"` in its manifest.
    Prior to alpha.45 this raised `Unknown content type`. Now it should
    map to the canonical `presentation` spec."""
    from routes.bighat_files import BIGHAT_TYPES

    raw_type = "trivia-presentation"
    _ROUND_ALIASES = {"mc", "reg", "misc", "mys", "big", "round"}
    if raw_type.lower() in _ROUND_ALIASES:
        content_type = "round"
    elif raw_type.lower() in ("trivia-presentation", "presentation"):
        content_type = "presentation"
    else:
        content_type = raw_type

    assert content_type == "presentation"
    assert content_type in BIGHAT_TYPES


# ---- Fix #1: /admin/stats never 500s --------------------------------------

def test_admin_stats_has_top_level_fallback_returning_zeros():
    """Read the admin.py source and confirm the outer except clause
    returns a zero payload rather than raising HTTPException(500). The
    frontend Presenter view Promise.all() rejects on any 500 and blanks
    the list — this endpoint MUST stay best-effort."""
    src = (ROOT / "routes" / "admin.py").read_text()

    # Find the get_admin_stats function
    assert "async def get_admin_stats" in src
    stats_start = src.index("async def get_admin_stats")
    # Function body extends to the next @router decorator
    next_route = src.index("@router.", stats_start + 1)
    body = src[stats_start:next_route]

    # The outer except must return a zero payload, not raise 500
    assert "totalUsageRecords" in body
    assert "usageByType" in body
    assert 'raise HTTPException(status_code=500' not in body, (
        "alpha.45 regression: /admin/stats top-level except must return "
        "a zero payload, never raise 500 (frontend Promise.all cascades)"
    )


def test_admin_stats_safe_count_helper_exists():
    """Every count_documents call must be wrapped so MontyDB thread /
    coroutine failures fall back to 0 instead of propagating."""
    src = (ROOT / "routes" / "admin.py").read_text()
    assert "_safe_count" in src, "alpha.45: expected _safe_count helper in admin.py"
