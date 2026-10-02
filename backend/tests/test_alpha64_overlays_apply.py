"""Overlays mapped in Trivia Setup must appear on the round slides even right
after a restart (DB empty, Trivia Setup never opened)."""
import json, shutil, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pytest
pytest.importorskip("montydb")
from fastapi import FastAPI
from fastapi.testclient import TestClient

GIF = b"GIF89a" + b"\x00" * 300


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setenv("BIGHAT_FILES_DIR", str(tmp_path))
    monkeypatch.setenv("BIGHAT_DB_DIR", str(tmp_path / "db"))
    monkeypatch.setenv("BIGHAT_NATIVE_MODE", "1")
    for n in list(sys.modules):
        if n in ("round_usage", "native_slides", "presentation_builder", "slide_style", "global_slides"):
            sys.modules.pop(n, None)
    from native import locations_router as lr
    import native.db_factory as dbf

    def boot():
        dbf._native_client = None
        lr.set_database(dbf.get_db())
        async def me(request): return {"id": "u1", "_id": "u1", "role": "master_admin", "email": "m@x.com"}
        lr.set_current_user_resolver(me)
        app = FastAPI(); app.include_router(lr.router, prefix="/api")
        return TestClient(app)
    return boot, tmp_path


def setup_show(boot, tmp_path):
    c = boot()
    loc = c.post("/api/native/locations", json={"name": "Monkey Pants Bar Grill"}).json()
    lid = loc["id"]
    ids = {}
    for name, tags in (("mc.gif", ["MC"]), ("reg.gif", ["REG"]), ("big.gif", ["BIG"]), ("ans.gif", ["ANS"])):
        oid = c.post(f"/api/native/locations/{lid}/overlays", files={"file": (name, GIF, "image/gif")}).json()["id"]
        c.patch(f"/api/native/locations/{lid}/overlays/{oid}/tags", json={"applies_to_round_types": tags})
        ids[name] = oid
    root = tmp_path / "Files"
    (root / "Hosts" / "h@x.com").mkdir(parents=True)
    (root / "Hosts" / "h@x.com" / "host.json").write_text(json.dumps({"email": "h@x.com", "display_name": "Nick", "id": "h@x.com"}))
    sp = root / "Trivia" / "Special"; sp.mkdir(parents=True)
    types = ["MC", "REG", "BIG"]
    for i, t in enumerate(types):
        (sp / f"r{i}.bighat").write_text(json.dumps({"round_type": t, "name": f"R{i}", "tiebreaker": {"question": "t", "answer": "1"},
            "questions": [{"number": k + 1, "question": f"Q{k+1}", "answer": "a", "options": ["a", "b"] if t == "MC" else []} for k in range(3)]}))
    import presentation_builder as pb
    pres = pb.build_special(name="S", host_id="h@x.com", location_id=lid, round_types=types, round_files=[f"r{i}.bighat" for i in range(3)])
    return lid, pres, ids


def overlay_count(slides):
    return sum(1 for s in slides for e in s["elements"] if e.get("type") == "image" and e.get("role") == "overlay"
               or (e.get("type") == "image" and (e.get("id") or "").startswith("overlay")))


def has_overlay(slide):
    return bool(slide["metadata"].get("_location_overlays_applied")) and any(
        "/overlays/" in str(e.get("src", "")) for e in slide["elements"])


def test_overlays_apply_after_restart_with_empty_db(world):
    boot, tmp_path = world
    lid, pres, ids = setup_show(boot, tmp_path)
    shutil.rmtree(tmp_path / "db", ignore_errors=True)            # restart: DB wiped, Setup never opened
    import native_slides as ns
    # what the slide fetcher used to hand over: nothing (empty DB)
    sl = ns.native_render_section(pres, "round_1", {})            # MC round, no DB overlays
    q = [s for s in sl if s["metadata"].get("slideIndexInRound") in range(1, 11) and not s["metadata"].get("isAnswers")]
    a = [s for s in sl if s["metadata"].get("isAnswers")]
    assert any(has_overlay(s) for s in q), "MC overlay missing on question slides"
    assert any(has_overlay(s) for s in a), "ANS overlay missing on answer slides"


def test_tags_decide_which_round_gets_which_overlay(world):
    boot, tmp_path = world
    lid, pres, ids = setup_show(boot, tmp_path)
    import native_slides as ns
    ov = ns.load_location_overlays(pres)
    assert {o["id"] for o in ov} == set(ids.values())
    assert {o["id"]: o["applies_to_round_types"] for o in ov}[ids["big.gif"]] == ["BIG"]
    import presentation_builder as pb
    assert [o["id"] for o in pb.overlays_for_round_type(ov, "MC", "question")] == [ids["mc.gif"]]
    assert [o["id"] for o in pb.overlays_for_round_type(ov, "BIG", "question")] == [ids["big.gif"]]
    assert [o["id"] for o in pb.overlays_for_round_type(ov, "REG", "answer")] == [ids["ans.gif"]]


def test_deleted_overlay_files_are_not_applied(world):
    boot, tmp_path = world
    lid, pres, ids = setup_show(boot, tmp_path)
    import native_slides as ns
    slug = "monkey-pants-bar-grill"
    for f in (tmp_path / "Files" / "Locations" / slug / "overlays").glob(f"{ids['mc.gif']}*"):
        f.unlink()
    assert ids["mc.gif"] not in {o["id"] for o in ns.load_location_overlays(pres)}


def test_no_overlays_means_slides_unchanged(world):
    boot, tmp_path = world
    import native_slides as ns
    assert ns.load_location_overlays({"location_id": "nope"}) == []


def test_big_overlay_on_question_review_answers_and_tiebreakers(world):
    """alpha.66: BIG overlay on BIG question, review, answers, tiebreaker Q and
    tiebreaker answer. Not on the title card or the grade GIF. Works after a
    restart (DB wiped)."""
    boot, tmp_path = world
    lid, pres, ids = setup_show(boot, tmp_path)
    shutil.rmtree(tmp_path / "db", ignore_errors=True)
    import native_slides as ns
    sl = ns.native_render_section(pres, "round_3", {})
    md = [s["metadata"] for s in sl]
    assert md[0].get("isRoundTitle") and not has_overlay(sl[0])
    for i, s in enumerate(sl):
        m = s["metadata"]
        if m.get("isGifStop") or m.get("isRoundTitle"):
            assert not has_overlay(s), f"slide {i} should have no overlay"
        else:
            assert has_overlay(s), f"slide {i} {m} missing BIG overlay"
            assert s["metadata"]["_location_overlays_applied"] == [ids["big.gif"]]
    kinds = [(m.get("isReview"), m.get("isAnswers"), m.get("isTiebreaker")) for m in md]
    assert (True, None, None) in kinds and any(k[2] and k[1] for k in kinds) and any(k[2] and not k[1] for k in kinds)


def test_mc_overlay_rules_unchanged_by_big_change(world):
    boot, tmp_path = world
    lid, pres, ids = setup_show(boot, tmp_path)
    import native_slides as ns
    sl = ns.native_render_section(pres, "round_1", {})
    review = [s for s in sl if s["metadata"].get("isReview")][0]
    assert not has_overlay(review)                      # MC review still has none
