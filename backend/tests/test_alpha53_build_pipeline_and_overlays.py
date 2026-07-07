"""v32.0.0-alpha.53 — HARDCODED Build Wizard + Round Roulette pipeline.

Merchant spec, 2026-02-06 (17-step flow). Every step becomes a test here.

Round rules:
  5 rounds: MC, REG, MISC, MYS, BIG
  6 rounds: MC, REG, (REG or MISC), MISC, MYS, BIG

This file locks in:
  Step 6:  round count 5 or 6 only
  Step 7:  MC first, only from MC folder
  Step 8:  REG second, only from REG folder
  Step 9:  MISC in slot 4 (6-round) or slot 3 (5-round); (REG-or-MISC) in slot 3 (6-round)
  Step 10: MYS second-to-last, only from MYS folder
  Step 11: BIG last, only from BIG folder
  Step 12: build_from_wizard() writes .bighat with all metadata
  Round Roulette: build_from_roulette() picks randomly + confirms
  Step 15: intros injected AFTER location, BEFORE round 1
  Step 17: location overlays composited on Q + A slides ONLY, tagged by round type
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import native_slides as ns  # noqa: E402
import presentation_builder as pb  # noqa: E402


# ---------------------------------------------------------------------------
# Fixture: mint a full docs-root with hosts, locations, and per-type rounds
# ---------------------------------------------------------------------------

@pytest.fixture
def docs_root(tmp_path, monkeypatch):
    docs = tmp_path
    monkeypatch.setenv("BIGHAT_FILES_DIR", str(docs))

    # Host
    hd = docs / "Files" / "Hosts" / "host-001"
    hd.mkdir(parents=True)
    (hd / "host.json").write_text(json.dumps({
        "id": "host-001", "display_name": "Test Host",
        "email": "test@example.com",
    }))

    # Location on-disk folder + a Mongo-shaped record we'll pass through body
    ld = docs / "Files" / "Locations" / "test-bar"
    (ld / "branding").mkdir(parents=True)
    (ld / "overlays").mkdir(parents=True)
    (ld / "location.json").write_text(json.dumps({
        "id": "loc-001", "slug": "test-bar", "name": "Test Bar",
    }))

    # One .bighat in each round-type folder
    for rt in ("MC", "REG", "MISC", "MYS", "BIG"):
        d = docs / "Files" / "Trivia" / rt
        d.mkdir(parents=True)
        (d / f"{rt.lower()}-01.bighat").write_text(json.dumps({
            "id": f"{rt}-1", "round_type": rt, "name": f"{rt} Round 1",
            "questions": [{"number": 1, "question": f"{rt} Q?", "answer": "A"}],
        }))
        # Second file for the (REG or MISC) test
        (d / f"{rt.lower()}-02.bighat").write_text(json.dumps({
            "id": f"{rt}-2", "round_type": rt, "name": f"{rt} Round 2",
            "questions": [{"number": 1, "question": f"{rt} Q?", "answer": "A"}],
        }))

    # Rounds output dir
    (docs / "Files" / "Trivia" / "Rounds").mkdir(parents=True)
    (docs / "Files" / "Trivia" / "Intros").mkdir(parents=True)

    return docs


# ---------------------------------------------------------------------------
# Step 6: round count validation
# ---------------------------------------------------------------------------

def test_step6_round_count_must_be_5_or_6():
    for bad in (0, 1, 2, 3, 4, 7, 8, 10, 99):
        with pytest.raises(pb.BuildValidationError, match="round count"):
            pb.validate_round_sequence(["MC"] * bad)


def test_step6_valid_5_and_6_round_sequences_pass():
    pb.validate_round_sequence(["MC", "REG", "MISC", "MYS", "BIG"])
    pb.validate_round_sequence(["MC", "REG", "REG", "MISC", "MYS", "BIG"])
    pb.validate_round_sequence(["MC", "REG", "MISC", "MISC", "MYS", "BIG"])


# ---------------------------------------------------------------------------
# Steps 7-11: fixed order, per-type folder isolation
# ---------------------------------------------------------------------------

def test_step7_mc_must_be_first():
    with pytest.raises(pb.BuildValidationError, match="slot 1"):
        pb.validate_round_sequence(["REG", "MC", "MISC", "MYS", "BIG"])


def test_step8_reg_must_be_second():
    with pytest.raises(pb.BuildValidationError, match="slot 2"):
        pb.validate_round_sequence(["MC", "MISC", "MISC", "MYS", "BIG"])


def test_step9_slot3_6round_accepts_reg_or_misc():
    pb.validate_round_sequence(["MC", "REG", "REG", "MISC", "MYS", "BIG"])
    pb.validate_round_sequence(["MC", "REG", "MISC", "MISC", "MYS", "BIG"])


def test_step9_slot3_6round_rejects_mc_mys_big():
    for bad in ("MC", "MYS", "BIG"):
        with pytest.raises(pb.BuildValidationError, match="slot 3"):
            pb.validate_round_sequence(["MC", "REG", bad, "MISC", "MYS", "BIG"])


def test_step10_mys_must_be_second_to_last():
    with pytest.raises(pb.BuildValidationError, match="slot 4"):
        pb.validate_round_sequence(["MC", "REG", "MISC", "REG", "BIG"])


def test_step11_big_must_be_last():
    with pytest.raises(pb.BuildValidationError, match="slot 5"):
        pb.validate_round_sequence(["MC", "REG", "MISC", "MYS", "MYS"])


# ---------------------------------------------------------------------------
# Cross-pool contamination MUST be forbidden — a MISC file can't be
# passed as the MC round, even if the wizard tried to sneak it through.
# ---------------------------------------------------------------------------

def test_cross_pool_picking_is_rejected(docs_root):
    # Try to use a MISC file as the MC round.
    with pytest.raises(pb.BuildValidationError):
        pb.build_from_wizard(
            name="Bad Show", host_id="host-001", location_id="loc-001",
            round_count=5,
            round_files=["misc-01.bighat", "reg-01.bighat", "misc-01.bighat",
                          "mys-01.bighat", "big-01.bighat"],
        )


# ---------------------------------------------------------------------------
# Step 12: successful wizard build writes .bighat with all metadata
# ---------------------------------------------------------------------------

def test_step12_wizard_writes_bighat_with_all_metadata(docs_root):
    pres = pb.build_from_wizard(
        name="My Test Show", host_id="host-001", location_id="loc-001",
        round_count=5,
        round_files=["mc-01.bighat", "reg-01.bighat", "misc-01.bighat",
                      "mys-01.bighat", "big-01.bighat"],
    )
    # Written to disk
    out = Path(pres["_disk_path"])
    assert out.exists() and out.parent.name == "Rounds"
    written = json.loads(out.read_text())
    # Every required field
    assert written["type"] == "trivia-presentation"
    assert written["host_id"] == "host-001"
    assert written["host_name"] == "Test Host"
    assert written["location_id"] == "loc-001"
    assert written["round_count"] == 5
    assert len(written["roundFiles"]) == 5
    assert [r["type"] for r in written["roundFiles"]] == [
        "MC", "REG", "MISC", "MYS", "BIG"
    ]
    assert [r["order"] for r in written["roundFiles"]] == [1, 2, 3, 4, 5]
    assert written["_source"] == "build-wizard"


def test_step12_wizard_6round_with_reg_in_slot3(docs_root):
    pres = pb.build_from_wizard(
        name="6Round Show", host_id="host-001", location_id="loc-001",
        round_count=6,
        round_files=["mc-01.bighat", "reg-01.bighat", "reg-02.bighat",
                      "misc-01.bighat", "mys-01.bighat", "big-01.bighat"],
    )
    assert [r["type"] for r in pres["roundFiles"]] == [
        "MC", "REG", "REG", "MISC", "MYS", "BIG"
    ]


# ---------------------------------------------------------------------------
# Round Roulette: slot machine + auto slot-3 for 6-round
# ---------------------------------------------------------------------------

def test_roulette_5round_picks_one_from_each_pool(docs_root):
    pres = pb.build_from_roulette(
        name="Roulette 5", host_id="host-001", location_id="loc-001",
        round_count=5,
        reg_pool=["reg-01.bighat", "reg-02.bighat"],
        misc_pool=["misc-01.bighat", "misc-02.bighat"],
        big_pool=["big-01.bighat"],
        seed=42,  # deterministic
    )
    picks = pres["_roulette_picks"]
    assert len(picks) == 5
    assert [p["type"] for p in picks] == ["MC", "REG", "MISC", "MYS", "BIG"]
    assert pres["_source"] == "round-roulette"


def test_roulette_6round_auto_picks_slot3_from_reg_or_misc(docs_root):
    pres = pb.build_from_roulette(
        name="Roulette 6", host_id="host-001", location_id="loc-001",
        round_count=6,
        reg_pool=["reg-01.bighat", "reg-02.bighat"],
        misc_pool=["misc-01.bighat", "misc-02.bighat"],
        big_pool=["big-01.bighat"],
        seed=1,
    )
    picks = pres["_roulette_picks"]
    assert len(picks) == 6
    # slot 3 MUST be REG or MISC — never MC/MYS/BIG
    assert picks[2]["type"] in ("REG", "MISC")


def test_roulette_seed_produces_deterministic_output(docs_root):
    p1 = pb.build_from_roulette(
        name="Det Show A", host_id="host-001", location_id="loc-001",
        round_count=5,
        reg_pool=["reg-01.bighat", "reg-02.bighat"],
        misc_pool=["misc-01.bighat", "misc-02.bighat"],
        big_pool=["big-01.bighat"],
        seed=777,
    )
    p2 = pb.build_from_roulette(
        name="Det Show B", host_id="host-001", location_id="loc-001",
        round_count=5,
        reg_pool=["reg-01.bighat", "reg-02.bighat"],
        misc_pool=["misc-01.bighat", "misc-02.bighat"],
        big_pool=["big-01.bighat"],
        seed=777,
    )
    assert [p["file"] for p in p1["_roulette_picks"]] == \
           [p["file"] for p in p2["_roulette_picks"]]


# ---------------------------------------------------------------------------
# Step 15: intros injected AFTER location, BEFORE round 1
# ---------------------------------------------------------------------------

def test_intros_are_injected_by_render_intros_section(docs_root, monkeypatch):
    pack = pb.save_intro_pack("Welcome Pack", slides=[
        {"index": 0, "background": "#000000", "elements": [
            {"type": "text", "content": "Welcome!", "x": 100, "y": 100,
             "width": 1720, "height": 200},
        ]},
        {"index": 1, "background": "#000000", "elements": [
            {"type": "text", "content": "Rules", "x": 100, "y": 100,
             "width": 1720, "height": 200},
        ]},
    ])
    pres = {"intro_pack_id": pack["id"]}
    slides = ns.render_intros_section(pres)
    assert len(slides) == 2
    for s in slides:
        assert s["metadata"]["_section"] == "intros"
        assert s["metadata"]["_verified_from_prototype"]


def test_intros_return_empty_when_no_pack_bound():
    assert ns.render_intros_section({}) == []
    assert ns.render_intros_section({"intro_pack_id": None}) == []


# ---------------------------------------------------------------------------
# Step 17: location overlays composited on Q + A slides ONLY, by round type
# ---------------------------------------------------------------------------

def test_overlays_tagged_by_round_type_only_apply_to_matching_rounds():
    overlays = [
        {"id": "ov-mc", "applies_to_round_types": ["MC"]},
        {"id": "ov-reg", "applies_to_round_types": ["REG"]},
        {"id": "ov-both", "applies_to_round_types": ["MC", "REG"]},
        {"id": "ov-untagged"},  # no key = applies everywhere
    ]
    mc_match = pb.overlays_for_round_type(overlays, "MC")
    assert {o["id"] for o in mc_match} == {"ov-mc", "ov-both", "ov-untagged"}
    reg_match = pb.overlays_for_round_type(overlays, "REG")
    assert {o["id"] for o in reg_match} == {"ov-reg", "ov-both", "ov-untagged"}
    big_match = pb.overlays_for_round_type(overlays, "BIG")
    assert {o["id"] for o in big_match} == {"ov-untagged"}


def test_overlays_composite_only_on_question_and_answer_slides():
    """Given a rendered MC round + one MC-tagged overlay, only Q+A slides
    should have the overlay image element appended."""
    doc = {
        "round_type": "MC", "name": "MC Test",
        "questions": [{"number": i, "question": f"Q{i}?", "answer": "A",
                        "options": ["A", "B", "C", "D"], "correctOption": 0}
                       for i in range(1, 11)],
    }
    slides = ns.render_round_section(doc, {"type": "MC", "name": "MC Test", "order": 1})
    overlays = [{"id": "ov-mc-01", "applies_to_round_types": ["MC"]}]
    out = ns._apply_location_overlays(
        slides, overlays, "loc-1", {"type": "MC"},
    )
    for s in out:
        md = s.get("metadata") or {}
        applied = md.get("_location_overlays_applied") or []
        is_q = md.get("questionNumber") is not None and not md.get("isAnswers") \
                and not md.get("isReview")
        is_a = bool(md.get("isAnswers"))
        if is_q or is_a:
            assert "ov-mc-01" in applied, \
                f"overlay MUST be applied to Q/A slide (slide {md.get('slideIndexInRound')})"
        else:
            assert not applied, (
                f"overlay MUST NOT be applied to non-Q/A slide "
                f"(slide {md.get('slideIndexInRound')}, md={md})"
            )


def test_overlays_never_apply_to_title_gif_or_review_slides():
    doc = {
        "round_type": "REG", "name": "REG Test",
        "questions": [{"number": i, "question": f"Q{i}?", "answer": "A"}
                       for i in range(1, 11)],
    }
    slides = ns.render_round_section(doc, {"type": "REG", "name": "REG Test", "order": 2})
    overlays = [{"id": "ov-reg", "applies_to_round_types": ["REG"]}]
    out = ns._apply_location_overlays(
        slides, overlays, "loc-1", {"type": "REG"},
    )
    forbidden = {"isRoundTitle", "isGifStop", "isReview"}
    for s in out:
        md = s.get("metadata") or {}
        applied = md.get("_location_overlays_applied") or []
        if any(md.get(k) for k in forbidden):
            assert not applied, (
                f"overlay applied to a forbidden slide-type: {md}"
            )


# ---------------------------------------------------------------------------
# Intro pack CRUD roundtrip
# ---------------------------------------------------------------------------

def test_intro_pack_crud_roundtrip(docs_root):
    pack = pb.save_intro_pack("Round 1 Intro", [
        {"index": 0, "background": "#111", "elements": []},
    ])
    listed = pb.list_intro_packs()
    assert any(p["id"] == pack["id"] for p in listed)
    loaded = pb.load_intro_pack(pack["id"])
    assert loaded is not None
    assert loaded["name"] == "Round 1 Intro"
    assert pb.delete_intro_pack(pack["id"]) is True
    assert pb.load_intro_pack(pack["id"]) is None


# ---------------------------------------------------------------------------
# API endpoints — thin contract tests
# ---------------------------------------------------------------------------

def test_build_endpoint_rejects_bad_round_count(docs_root):
    from fastapi.testclient import TestClient
    from fastapi import FastAPI
    from native.router import router
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    r = client.post("/api/native/presentations/build", json={
        "name": "Bad", "host_id": "host-001", "location_id": "loc-001",
        "round_count": 4,  # not 5 or 6
        "round_files": ["mc-01.bighat"] * 4,
    })
    assert r.status_code in (400, 422)


def test_build_endpoint_happy_path(docs_root):
    from fastapi.testclient import TestClient
    from fastapi import FastAPI
    from native.router import router
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    r = client.post("/api/native/presentations/build", json={
        "name": "Wizard E2E", "host_id": "host-001", "location_id": "loc-001",
        "round_count": 5,
        "round_files": ["mc-01.bighat", "reg-01.bighat", "misc-01.bighat",
                         "mys-01.bighat", "big-01.bighat"],
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["round_count"] == 5
    assert len(body["roundFiles"]) == 5


def test_roulette_endpoint_happy_path(docs_root):
    from fastapi.testclient import TestClient
    from fastapi import FastAPI
    from native.router import router
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    r = client.post("/api/native/presentations/roulette", json={
        "name": "Roulette E2E", "host_id": "host-001", "location_id": "loc-001",
        "round_count": 5,
        "reg_pool": ["reg-01.bighat", "reg-02.bighat"],
        "misc_pool": ["misc-01.bighat", "misc-02.bighat"],
        "big_pool": ["big-01.bighat"],
        "seed": 99,
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["_source"] == "round-roulette"
    assert len(body["_roulette_picks"]) == 5


def test_round_pool_endpoint_lists_type_only(docs_root):
    from fastapi.testclient import TestClient
    from fastapi import FastAPI
    from native.router import router
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    r = client.get("/api/native/round-pool/MC")
    assert r.status_code == 200
    body = r.json()
    assert body["round_type"] == "MC"
    assert body["count"] == 2
    # And REG files should NEVER appear in the MC listing
    assert all("reg" not in f.lower() for f in body["files"])


def test_intros_endpoint_lifecycle(docs_root):
    from fastapi.testclient import TestClient
    from fastapi import FastAPI
    from native.router import router
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    # create
    r = client.post("/api/native/intros", json={
        "name": "MC Intro Pack",
        "slides": [{"index": 0, "background": "#000", "elements": []}],
    })
    assert r.status_code == 200, r.text
    pid = r.json()["id"]

    # list
    r = client.get("/api/native/intros")
    assert r.status_code == 200
    assert any(p["id"] == pid for p in r.json()["packs"])

    # get
    r = client.get(f"/api/native/intros/{pid}")
    assert r.status_code == 200
    assert r.json()["name"] == "MC Intro Pack"

    # delete
    r = client.delete(f"/api/native/intros/{pid}")
    assert r.status_code == 204
    r = client.get(f"/api/native/intros/{pid}")
    assert r.status_code == 404
