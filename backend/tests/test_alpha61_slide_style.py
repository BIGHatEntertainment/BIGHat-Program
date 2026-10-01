import sys, importlib
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _fresh(tmp_path, monkeypatch):
    monkeypatch.setenv("BIGHAT_FILES_DIR", str(tmp_path))
    for n in list(sys.modules):
        if n in ("slide_style", "native_slides") or n.startswith("native_slides"):
            sys.modules.pop(n, None)
    import native_slides, slide_style
    return native_slides, slide_style


def test_default_keeps_blue(tmp_path, monkeypatch):
    ns, ss = _fresh(tmp_path, monkeypatch)
    sl = [{"background": ns.BG_BLUE}]
    assert ss.apply_to_slides(sl, "x-y", ns.BG_BLUE)[0]["background"] == ns.BG_BLUE


def test_global_applies_only_to_default_blue(tmp_path, monkeypatch):
    ns, ss = _fresh(tmp_path, monkeypatch)
    ss.save_global({"mode": "custom", "color": "#AA0000", "fill": "solid"})
    out = ss.apply_to_slides([{"background": ns.BG_BLUE}, {"background": ns.BG_DARK}], None, ns.BG_BLUE)
    assert out[0]["background"] == "#AA0000"
    assert out[1]["background"] == ns.BG_DARK


def test_location_override_and_revert(tmp_path, monkeypatch):
    ns, ss = _fresh(tmp_path, monkeypatch)
    ss.save_global({"mode": "custom", "color": "#AA0000", "fill": "solid"})
    ss.save_location("bar-one", False, {"mode": "custom", "color": "#00AA00", "fill": "solid"})
    assert ss.apply_to_slides([{"background": ns.BG_BLUE}], "bar-one", ns.BG_BLUE)[0]["background"] == "#00AA00"
    assert ss.apply_to_slides([{"background": ns.BG_BLUE}], "other", ns.BG_BLUE)[0]["background"] == "#AA0000"
    ss.save_location("bar-one", True, {"mode": "custom", "color": "#00AA00", "fill": "solid"})
    assert ss.apply_to_slides([{"background": ns.BG_BLUE}], "bar-one", ns.BG_BLUE)[0]["background"] == "#AA0000"


def test_bad_color_rejected(tmp_path, monkeypatch):
    _, ss = _fresh(tmp_path, monkeypatch)
    assert ss.clean_background({"mode": "custom", "color": "red;}"})["color"] == "#1657E8"


# ---- alpha.61: ANS overlay tag + 100 MB cap ----
def test_ans_overlay_only_on_answer_slides(tmp_path, monkeypatch):
    sys.modules.pop("presentation_builder", None)
    import presentation_builder as pb
    ovs = [
        {"id": "q", "applies_to_round_types": ["MC"], "order": 0},
        {"id": "a", "applies_to_round_types": ["ANS"], "order": 1},
        {"id": "legacy", "order": 2},
        {"id": "off", "applies_to_round_types": [], "order": 3},
    ]
    assert [o["id"] for o in pb.overlays_for_round_type(ovs, "MC", "question")] == ["q", "legacy"]
    assert [o["id"] for o in pb.overlays_for_round_type(ovs, "BIG", "question")] == ["legacy"]
    assert [o["id"] for o in pb.overlays_for_round_type(ovs, "BIG", "answer")] == ["a"]


def test_upload_cap_fits_22mb_gif():
    from native import locations_router as lr
    assert lr._MAX_IMAGE_BYTES >= 100 * 1024 * 1024
    assert 21.6 * 1024 * 1024 < lr._MAX_IMAGE_BYTES
