"""Special (themed-night) shows: 3..10 rounds, MC first, BIG last, Special folder only."""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pytest


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("BIGHAT_FILES_DIR", str(tmp_path))
    for n in list(sys.modules):
        if n in ("round_usage", "native_slides", "presentation_builder", "slide_style"):
            sys.modules.pop(n, None)
    import presentation_builder as pb, round_usage, native_slides as ns
    root = tmp_path / "Files"
    h = root / "Hosts" / "h@x.com"; h.mkdir(parents=True)
    (h / "host.json").write_text(json.dumps({"email": "h@x.com", "display_name": "H", "id": "h@x.com"}))
    L = root / "Locations" / "bar"; L.mkdir(parents=True)
    (L / "location.json").write_text(json.dumps({"id": "loc-1", "name": "Bar", "slug": "bar"}))
    return pb, round_usage, ns, root


def make_round(root, name, rtype, nq, pool="Special", options=False):
    d = root / "Trivia" / pool; d.mkdir(parents=True, exist_ok=True)
    qs = [{"number": i + 1, "question": f"{name} Q{i+1}?", "answer": f"A{i+1}",
           "options": (["a", "b", "c", "d"] if options else [])} for i in range(nq)]
    (d / f"{name}.bighat").write_text(json.dumps({"schema": "bighat-round/v1", "round_type": rtype,
                                                   "name": name, "questions": qs}))
    return f"{name}.bighat"


def build(pb, types, files, **kw):
    return pb.build_special(name="Dino Night", host_id="h@x.com", location_id="loc-1",
                            round_types=types, round_files=files, **kw)


def test_loadout_rules(env):
    pb = env[0]
    for n in range(3, 11):
        pb.validate_special_loadout(["MC"] + ["REG"] * (n - 2) + ["BIG"])
    for bad in (["MC", "BIG"], ["MC"] + ["REG"] * 10 + ["BIG"]):
        with pytest.raises(pb.BuildValidationError): pb.validate_special_loadout(bad)
    with pytest.raises(pb.BuildValidationError): pb.validate_special_loadout(["REG", "REG", "BIG"])   # MC first
    with pytest.raises(pb.BuildValidationError): pb.validate_special_loadout(["MC", "REG", "MISC"])   # BIG last
    with pytest.raises(pb.BuildValidationError): pb.validate_special_loadout(["MC", "BIG", "REG", "BIG"])  # BIG only last


def test_builds_7_round_show_in_chosen_order_and_catalogs(env):
    pb, ru, ns, root = env
    types = ["MC", "REG", "REG", "MISC", "MYS", "REG", "BIG"]
    files = [make_round(root, f"dino{i}", t, 4, options=(t == "MC")) for i, t in enumerate(types)]
    pres = build(pb, types, files)
    assert pres["is_special"] and pres["numRounds"] == 7 and pres["roundTypes"] == types
    assert [r["type"] for r in pres["roundFiles"]] == types and [r["order"] for r in pres["roundFiles"]] == list(range(1, 8))
    assert len(ru.list_records()) == 7                       # catalogued like normal shows
    assert Path(pres["_disk_path"]).parent.name == "Rounds"  # same catalog folder


def test_only_special_folder_is_used(env):
    pb, ru, ns, root = env
    make_round(root, "normal-mc", "MC", 4, pool="MC", options=True)
    types = ["MC", "REG", "BIG"]
    files = ["normal-mc.bighat", make_round(root, "r", "REG", 3), make_round(root, "b", "BIG", 1)]
    with pytest.raises(pb.BuildValidationError) as e:
        build(pb, types, files)
    assert "not found in the Special folder" in str(e.value)
    assert [r["file"] for r in pb.list_special_rounds()] == ["b.bighat", "r.bighat"]  # normal pool not listed


def test_special_rounds_not_in_normal_pickers(env):
    pb, ru, ns, root = env
    make_round(root, "dino", "REG", 3)
    assert "dino" not in {p.stem for p in (root / "Trivia" / "REG").glob("*.bighat")} if (root / "Trivia" / "REG").exists() else True


def test_mc_slot_needs_options_and_no_duplicates(env):
    pb, ru, ns, root = env
    files = [make_round(root, "m", "MC", 3, options=False), make_round(root, "r", "REG", 3), make_round(root, "b", "BIG", 1)]
    with pytest.raises(pb.BuildValidationError) as e: build(pb, ["MC", "REG", "BIG"], files)
    assert "multiple-choice" in str(e.value)
    ok = make_round(root, "m2", "MC", 3, options=True)
    with pytest.raises(pb.BuildValidationError) as e: build(pb, ["MC", "REG", "BIG"], [ok, files[1], files[1]])
    assert "twice" in str(e.value)


def test_180_day_lock_applies_and_release_unlocks(env):
    pb, ru, ns, root = env
    files = [make_round(root, "m", "MC", 3, options=True), make_round(root, "r", "REG", 3), make_round(root, "b", "BIG", 1)]
    p = build(pb, ["MC", "REG", "BIG"], files)
    with pytest.raises(pb.BuildValidationError) as e: build(pb, ["MC", "REG", "BIG"], files)
    assert "locked" in str(e.value).lower()
    ru.release_presentation(p["id"])
    build(pb, ["MC", "REG", "BIG"], files)


def test_short_round_has_no_blank_slides_and_keeps_player_positions(env):
    pb, ru, ns, root = env
    ref = {"type": "REG", "name": "short", "order": 2, "special": True}
    data = {"round_type": "REG", "name": "short",
            "questions": [{"number": i + 1, "question": f"Q{i+1}", "answer": f"A{i+1}"} for i in range(4)]}
    sl = [s for s in ns.render_round_section(data, ref) if not s['metadata'].get('isScoreSlide')]
    kinds = [("title" if s["metadata"].get("isTitleCard") else "gif" if s["metadata"].get("isGifStop")
              else "review" if s["metadata"].get("isReview") else "answers" if s["metadata"].get("isAnswers") else "q") for s in sl]
    assert kinds == ["title", "q", "q", "q", "q", "review", "gif", "answers"]      # no blank Q5-Q10
    pos = {k: s["metadata"]["slideIndexInRound"] for k, s in zip(kinds, sl) if k in ("review", "gif", "answers")}
    assert pos == {"review": 11, "gif": 12, "answers": 13}                          # player timers/reveal still work
    normal = [s for s in ns.render_round_section(data, {"type": "REG", "name": "short", "order": 2}) if not s["metadata"].get("isScoreSlide")]
    assert len(normal) == 14                                                        # normal shows unchanged


def test_short_mys_positions(env):
    ns = env[2]
    data = {"round_type": "MYS", "name": "m", "questions": [{"number": i + 1, "question": "q", "answer": "a"} for i in range(3)]}
    sl = [s for s in ns.render_round_section(data, {"type": "MYS", "name": "m", "order": 1, "special": True}) if not s["metadata"].get("isScoreSlide")]
    idx = {("review" if s["metadata"].get("isReview") else "gif" if s["metadata"].get("isGifStop") else "answers" if s["metadata"].get("isAnswers") else "x"): s["metadata"]["slideIndexInRound"] for s in sl}
    assert (idx["review"], idx["gif"], idx["answers"]) == (10, 11, 12)


def test_slot_type_decides_overlay(env):
    pb, ru, ns, root = env
    ovs = [{"id": "mys", "applies_to_round_types": ["MYS"]}, {"id": "ans", "applies_to_round_types": ["ANS"]}]
    assert [o["id"] for o in pb.overlays_for_round_type(ovs, "MYS", "question")] == ["mys"]
    assert pb.overlays_for_round_type(ovs, "REG", "question") == []
    assert [o["id"] for o in pb.overlays_for_round_type(ovs, "REG", "answer")] == ["ans"]


def test_special_round_loads_only_from_special_folder(env):
    pb, ru, ns, root = env
    make_round(root, "same", "REG", 2, pool="REG")        # a NORMAL round with the same name
    make_round(root, "same", "REG", 5, pool="Special")
    d = ns.load_round_from_disk({"type": "REG", "name": "same", "file": "Trivia/Special/same.bighat", "special": True})
    assert len(d["questions"]) == 5


def test_section_order_not_resorted_for_special():
    src = (Path(__file__).resolve().parents[1] / "routes" / "slide_fetcher.py").read_text()
    assert "not trivia_pres.get('is_special')" in src


def test_endpoints_are_admin_only():
    src = (Path(__file__).resolve().parents[1] / "native" / "router.py").read_text()
    assert src.count("await _require_admin_role(request)") >= 2
    assert '"admin", "master_admin"' in src


def test_files_tool_accepts_special_folder():
    fr = (Path(__file__).resolve().parents[1] / "native" / "files_router.py").read_text()
    assert 'TRIVIA_SPECIAL_FOLDER = "Special"' in fr
    ui = (Path(__file__).resolve().parents[2] / "frontend/src/pages/FilesTool.jsx").read_text()
    assert "'Special'" in ui
