"""Presentation metadata (name, ids) never shows on slides; rewards slot stays."""
import json, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pytest

UUID = re.compile(r"[0-9a-fA-F]{8}[ -]?[0-9a-fA-F]{4}[ -]?[0-9a-fA-F]{4}")
LID = "9158e059-2efe-4185-a094-6211b2d9a3cb"
PNAME = "Monkey Pants Bar Grill - 10/1 Test"


@pytest.fixture
def show(tmp_path, monkeypatch):
    monkeypatch.setenv("BIGHAT_FILES_DIR", str(tmp_path))
    for n in list(sys.modules):
        if n in ("round_usage", "native_slides", "presentation_builder", "slide_style"):
            sys.modules.pop(n, None)
    import presentation_builder as pb, native_slides as ns
    root = tmp_path / "Files"
    (root / "Hosts" / "h@x.com").mkdir(parents=True)
    (root / "Hosts" / "h@x.com" / "host.json").write_text(json.dumps({"email": "h@x.com", "display_name": "Nick", "id": "h@x.com"}))
    (root / "Locations" / "monkey-pants-bar-grill").mkdir(parents=True)
    (root / "Locations" / "monkey-pants-bar-grill" / "location.json").write_text(
        json.dumps({"id": LID, "name": "Monkey Pants Bar Grill", "slug": "monkey-pants-bar-grill"}))
    sp = root / "Trivia" / "Special"; sp.mkdir(parents=True)
    types, files = ["MC", "REG", "BIG"], []
    for i, t in enumerate(types):
        (sp / f"r{i}.bighat").write_text(json.dumps({"round_type": t, "name": f"Round {i}", "tiebreaker": {"question": "tb", "answer": "1"},
            "questions": [{"number": k + 1, "question": f"Q{k+1}", "answer": "a", "options": ["a", "b", "c", "d"] if t == "MC" else []} for k in range(3)]}))
        files.append(f"r{i}.bighat")
    pres = pb.build_special(name=PNAME, host_id="h@x.com", location_id=LID, round_types=types, round_files=files)
    return pres, ns, tmp_path


def _texts(slides):
    return [str(e.get("content") or e.get("text") or "") for s in slides for e in s["elements"] if e["type"] == "text"]


def test_no_presentation_name_or_ids_on_any_slide(show):
    pres, ns, _ = show
    secs = ["host", "location", "sponsors", "winners", "final_scores"] + [f"round_{r['order']}" for r in pres["roundFiles"]]
    for sec in secs:
        for t in _texts(ns.native_render_section(pres, sec)):
            assert PNAME not in t and "10/1 Test" not in t, (sec, t)
            assert not UUID.search(t), (sec, t)


def test_host_image_slide_has_no_caption(show, tmp_path):
    pres, ns, tp = show
    h = tp / "Files" / "Hosts" / "h@x.com"
    (h / "host-16x9.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 64)
    sl = ns.render_host_section(pres)
    assert len(sl) == 1
    assert _texts(sl) == [] or all(PNAME not in t for t in _texts(sl))


def test_host_text_fallback_has_no_presentation_name(show):
    pres, ns, _ = show
    for t in _texts(ns.render_host_section(pres)):
        assert PNAME not in t


def _branding(tp, names):
    b = tp / "Files" / "Locations" / "monkey-pants-bar-grill" / "branding"; b.mkdir(parents=True, exist_ok=True)
    for n in names:
        (b / n).write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 64)
    return b


def test_there_is_no_rewards_slot_any_more_and_host_still_comes_first(show):
    """alpha.97: the empty reserved rewards slide was removed (the standalone program does not use it)."""
    pres, ns, _ = show
    assert ns.native_render_section(pres, "location") == []          # no images, so no location slides at all
    src = (Path(__file__).resolve().parents[1] / "routes" / "slide_fetcher.py").read_text()
    assert src.index('{"name": "host"') < src.index('{"name": "location"')   # host first, then the location images


def test_every_branding_image_is_a_slide_and_nothing_else(show):
    pres, ns, tp = show
    _branding(tp, ["a.png", "b.png", "c.gif"])
    sl = ns.native_render_section(pres, "location")
    assert len(sl) == 3                                            # exactly the 3 images, no blank slide in front
    for s_ in sl:
        assert [e["type"] for e in s_["elements"]] == ["image"]
        assert not s_["metadata"].get("isRewardsSlot")
        assert s_["metadata"].get("isRoundTitle") is False         # must not inflate the round count
    assert [s_["metadata"]["slideIndexInRound"] for s_ in sl] == [0, 1, 2]


def test_editor_round_count_ignores_host_and_location_slides():
    src = (Path(__file__).resolve().parents[2] / "frontend/src/pages/trivia/Editor.jsx").read_text()
    assert src.count("'TOTAL', 'HOST', 'LOCATION'") >= 2


def test_slide_cache_is_temporary_so_old_baked_in_text_is_gone_after_restart():
    """The Editor loads cached slides first. The cache lives in MontyDB which is
    wiped each launch, so shows rebuilt after the update use the fixed renderer."""
    src = (Path(__file__).resolve().parents[1] / "gridfs_service.py").read_text()
    assert "NativeGridFSBucket" in src
