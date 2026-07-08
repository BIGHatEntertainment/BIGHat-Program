"""Alpha.40 live integration test — hits the deployed backend and verifies
disk-first Round Maker behaviour and native slide assembly."""
from __future__ import annotations
import os
import json
import time
import uuid
from pathlib import Path

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://prototype-ui-audit.preview.emergentagent.com").rstrip("/")
DOCS_ROOT = Path("/root/Documents/BIG Hat Entertainment")
TRIVIA_ROOT = DOCS_ROOT / "Files" / "Trivia"


def _api(path: str) -> str:
    return f"{BASE_URL}/api{path}"


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def _cleanup_round(session, rid):
    try:
        session.delete(_api(f"/roundmaker/rounds/{rid}"), timeout=15)
    except Exception:
        pass


# ────────── Round Maker CRUD + disk ──────────

def test_create_round_writes_bighat_to_disk(session):
    name = f"TEST_alpha40_create_{uuid.uuid4().hex[:6]}"
    payload = {
        "round_type": "MC",
        "name": name,
        "questions": [
            {"number": 1, "question": "Live Q1?", "answer": "A1"},
            {"number": 2, "question": "Live Q2?", "answer": "A2"},
        ],
    }
    r = session.post(_api("/roundmaker/rounds"), json=payload, timeout=20)
    assert r.status_code in (200, 201), r.text
    data = r.json()
    rid = data["id"]

    try:
        # Find the file with the slugified name (may have -shortid suffix)
        mc_dir = TRIVIA_ROOT / "MC"
        slug_prefix = name.lower().replace("_", "-")
        matches = list(mc_dir.glob(f"{slug_prefix}*.bighat"))
        assert matches, f"No .bighat file found for {slug_prefix} in {mc_dir}"

        # Validate schema
        payload_on_disk = json.loads(matches[0].read_text())
        assert payload_on_disk.get("schema") == "bighat-round/v1"
        assert payload_on_disk.get("name") == name
        assert payload_on_disk.get("id") == rid
        assert len(payload_on_disk.get("questions", [])) == 2
    finally:
        _cleanup_round(session, rid)


def test_duplicate_round_writes_disk_with_copy_suffix(session):
    name = f"TEST_dup_{uuid.uuid4().hex[:6]}"
    orig = session.post(_api("/roundmaker/rounds"), json={
        "round_type": "REG",
        "name": name,
        "questions": [{"number": 1, "question": "q", "answer": "a"}],
    }, timeout=20).json()
    rid = orig["id"]
    dup_id = None
    try:
        r = session.post(_api(f"/roundmaker/rounds/{rid}/duplicate"), timeout=20)
        assert r.status_code in (200, 201), r.text
        dup = r.json()
        dup_id = dup["id"]
        assert "(Copy)" in dup["name"] or "Copy" in dup["name"]

        reg_dir = TRIVIA_ROOT / "REG"
        slug_prefix = name.lower().replace("_", "-")
        matches = list(reg_dir.glob(f"{slug_prefix}*.bighat"))
        # Should have BOTH the original and the copy
        assert len(matches) >= 2, f"Expected original+copy, got {[m.name for m in matches]}"
    finally:
        _cleanup_round(session, rid)
        if dup_id:
            _cleanup_round(session, dup_id)


def test_delete_round_removes_disk_file(session):
    name = f"TEST_del_{uuid.uuid4().hex[:6]}"
    r = session.post(_api("/roundmaker/rounds"), json={
        "round_type": "MISC",
        "name": name,
        "questions": [{"number": 1, "question": "q", "answer": "a"}],
    }, timeout=20)
    rid = r.json()["id"]

    misc_dir = TRIVIA_ROOT / "MISC"
    slug_prefix = name.lower().replace("_", "-")
    before = list(misc_dir.glob(f"{slug_prefix}*.bighat"))
    assert before, "File missing after create"

    dr = session.delete(_api(f"/roundmaker/rounds/{rid}"), timeout=20)
    assert dr.status_code in (200, 204), dr.text

    after = list(misc_dir.glob(f"{slug_prefix}*.bighat"))
    assert not after, f"File not removed after DELETE: {[m.name for m in after]}"


def test_two_rounds_same_name_get_unique_disk_files(session):
    name = f"TEST_dupname_{uuid.uuid4().hex[:6]}"
    r1 = session.post(_api("/roundmaker/rounds"), json={
        "round_type": "MYS", "name": name,
        "questions": [{"number": 1, "question": "q", "answer": "a"}]}, timeout=20).json()
    r2 = session.post(_api("/roundmaker/rounds"), json={
        "round_type": "MYS", "name": name,
        "questions": [{"number": 1, "question": "q", "answer": "a"}]}, timeout=20).json()
    try:
        mys_dir = TRIVIA_ROOT / "MYS"
        slug_prefix = name.lower().replace("_", "-")
        matches = list(mys_dir.glob(f"{slug_prefix}*.bighat"))
        assert len(matches) == 2, f"Expected 2 unique files, got {[m.name for m in matches]}"
    finally:
        _cleanup_round(session, r1["id"])
        _cleanup_round(session, r2["id"])


def test_list_rounds_merges_disk_only(session):
    """Drop a .bighat directly and confirm it shows up in list_rounds."""
    orphan_id = f"orphan-{uuid.uuid4().hex[:8]}"
    orphan_name = f"TEST_orphan_{uuid.uuid4().hex[:6]}"
    big_dir = TRIVIA_ROOT / "BIG"
    big_dir.mkdir(parents=True, exist_ok=True)
    path = big_dir / f"{orphan_name.lower().replace('_', '-')}.bighat"
    path.write_text(json.dumps({
        "schema": "bighat-round/v1",
        "id": orphan_id,
        "round_type": "BIG",
        "name": orphan_name,
        "questions": [{"number": 1, "question": "q", "answer": "a"}],
        "status": "draft",
        "created_at": "2026-01-01T00:00:00+00:00",
    }))
    try:
        r = session.get(_api("/roundmaker/rounds"), timeout=20)
        assert r.status_code == 200
        rounds = r.json()
        names = [x.get("name") for x in rounds]
        assert orphan_name in names, f"disk-only orphan not merged into list. Got {len(names)} rounds"
    finally:
        if path.exists():
            path.unlink()


@pytest.mark.parametrize("rtype", ["mc", "reg", "misc", "mys", "big"])
def test_round_files_endpoint_returns_bighat_files(session, rtype):
    r = session.get(_api(f"/trivia/round-files/{rtype}"), timeout=20)
    assert r.status_code == 200, f"[{rtype}] {r.status_code}: {r.text[:200]}"
    data = r.json()
    # Could be a list or {"files": [...]}
    files = data if isinstance(data, list) else data.get("files", data.get("rounds", []))
    assert isinstance(files, list), f"Unexpected shape for {rtype}: {type(data)}"


# ────────── Slide assembly (native) ──────────

def test_slide_assembly_native_ordering(session):
    """Create rounds via API → import them into a manifest → assemble slides."""
    created_ids = []
    manifest_id = None
    try:
        specs = [
            ("MC", "TEST_slideMC", 3),
            ("REG", "TEST_slideREG", 2),
            ("BIG", "TEST_slideBIG", 1),
        ]
        rounds_refs = []
        round_types = []
        round_names = []
        for rtype, base, qcount in specs:
            name = f"{base}_{uuid.uuid4().hex[:6]}"
            r = session.post(_api("/roundmaker/rounds"), json={
                "round_type": rtype, "name": name,
                "questions": [{"number": i, "question": f"Q{i}", "answer": f"A{i}"}
                              for i in range(1, qcount + 1)],
            }, timeout=20).json()
            created_ids.append(r["id"])
            slug = name.lower().replace("_", "-")
            # find actual filename
            matches = list((TRIVIA_ROOT / rtype).glob(f"{slug}*.bighat"))
            assert matches, f"file not written for {name}"
            rounds_refs.append(f"{rtype}/{matches[0].name}")
            round_types.append(rtype)
            round_names.append(name)

        # Build presentation
        pres_name = f"TEST_alpha40_pres_{uuid.uuid4().hex[:6]}"
        r = session.post(_api("/presentations/import-trivia"), json={
            "userName": "Sellards",
            "host": "Sellards",
            "location": "TEST Bar",
            "rounds": rounds_refs,
            "roundTypes": round_types,
            "roundNames": round_names,
            "numRounds": len(rounds_refs),
            "presentationName": pres_name,
        }, timeout=30)
        assert r.status_code in (200, 201), r.text
        manifest = r.json()
        manifest_id = manifest.get("id") or manifest.get("presentation_id")
        assert manifest_id

        # Now assemble slides
        sr = session.get(_api(f"/trivia-viewer/{manifest_id}/slides"), timeout=30)
        assert sr.status_code == 200, sr.text
        result = sr.json()
        assert result.get("source") == "native-disk", f"source={result.get('source')}"
        slides = result.get("slides", [])
        assert slides, "no slides"
        types = [s["type"] for s in slides]

        assert types[0] == "host"
        assert types[1] == "location"
        assert types.count("round_cover") == 3
        assert types.count("review") == 3
        assert types.count("answers") == 3
        assert types.count("question") == 3 + 2 + 1
        assert types[-1] == "final_scores"
    finally:
        for rid in created_ids:
            _cleanup_round(session, rid)


def test_slide_assembly_placeholder_on_missing_file(session):
    """Manifest references a nonexistent .bighat → placeholder, not 500."""
    pres_name = f"TEST_broken_{uuid.uuid4().hex[:6]}"
    r = session.post(_api("/presentations/import-trivia"), json={
        "userName": "Sellards", "host": "", "location": "",
        "rounds": ["MC/definitely-does-not-exist-xyz.bighat"],
        "roundTypes": ["MC"], "roundNames": ["Ghost"],
        "numRounds": 1,
        "presentationName": pres_name,
    }, timeout=30)
    assert r.status_code in (200, 201), r.text
    mid = r.json().get("id") or r.json().get("presentation_id")
    sr = session.get(_api(f"/trivia-viewer/{mid}/slides"), timeout=30)
    assert sr.status_code == 200, f"expected graceful fallback, got {sr.status_code}: {sr.text[:200]}"
    result = sr.json()
    slides = result.get("slides", [])
    # Must contain a final_scores slide and placeholder cover
    types = [s.get("type") for s in slides]
    assert "final_scores" in types
    # placeholder subtitle marker
    placeholders = [s for s in slides if str(s.get("subtitle", "")).startswith("(round data not found")]
    assert len(placeholders) >= 1, f"no placeholder emitted; slides={types}"


# ────────── Alpha 38/39 regression ──────────

def test_regression_presentation_import_and_list(session):
    pres_name = f"TEST_reg_{uuid.uuid4().hex[:6]}"
    r = session.post(_api("/presentations/import-trivia"), json={
        "userName": "Sellards", "host": "Sellards", "location": "Regression Bar",
        "rounds": [], "roundTypes": [], "roundNames": [],
        "numRounds": 0, "presentationName": pres_name,
    }, timeout=30)
    assert r.status_code in (200, 201), r.text
    # Rounds/ folder should have a manifest
    rounds_dir = TRIVIA_ROOT / "Rounds"
    assert rounds_dir.exists()

    lr = session.get(_api("/trivia-viewer/list"), timeout=20)
    assert lr.status_code == 200
    lst = lr.json()
    entries = lst if isinstance(lst, list) else lst.get("presentations", [])
    names = [e.get("name") or e.get("presentation_name") for e in entries]
    assert pres_name in names, f"newly imported presentation not in list; found {len(names)}"
