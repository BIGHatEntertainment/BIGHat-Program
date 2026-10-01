"""Global slides: company -> rules -> format, between location slides and round 1."""
import io, json, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pytest

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 200
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("BIGHAT_FILES_DIR", str(tmp_path))
    for n in list(sys.modules):
        if n in ("round_usage", "native_slides", "presentation_builder", "slide_style", "global_slides"):
            sys.modules.pop(n, None)
    import native_slides as ns, global_slides as gs, presentation_builder as pb
    return ns, gs, pb, tmp_path


def pres(types, names=None):
    names = names or [""] * len(types)
    return {"name": "x", "roundFiles": [{"order": i + 1, "type": t, "name": n, "file": "x"} for i, (t, n) in enumerate(zip(types, names))]}


def texts(sl):
    return [e["content"] for s in sl for e in s["elements"] if e["type"] == "text"]


# ---- Format slide ----
def test_one_pill_per_round_for_3_to_10_rounds(env):
    ns = env[0]
    for n in range(3, 11):
        types = ["MC"] + ["REG"] * (n - 2) + ["BIG"]
        sl = ns.native_render_section(pres(types), "format")
        assert len(sl) == 1 and len(texts(sl)) == n


def test_labels_points_and_order(env):
    ns = env[0]
    out = texts(ns.native_render_section(pres(["MC", "REG", "MISC", "MYS", "BIG"]), "format"))
    assert out == ["Multiple Choice - 1 Point each", "General Topic - 1 Point each", "Specific Topic - 1 Point each",
                   "Mystery Topic - 2 Points each", "The BIG Question - 3 Points each"]


def test_theme_shown_for_general_and_specific_only_never_mystery(env):
    ns = env[0]
    p = pres(["MC", "REG", "MISC", "MYS", "BIG"], ["MC_01_A (1)", "Animals_1", "Dino_Night_3", "Secret_Thing_2", "Big_5"])
    out = texts(ns.native_render_section(p, "format"))
    assert out[1] == "General Topic: Animals - 1 Point each"
    assert out[2] == "Specific Topic: Dino Night - 1 Point each"
    assert "Secret" not in " ".join(out)                         # Mystery stays a secret
    assert out[0] == "Multiple Choice - 1 Point each"            # MC never shows a name
    assert out[4] == "The BIG Question - 3 Points each"


def test_code_like_names_fall_back_to_generic(env):
    ns = env[0]
    for nm in ("REG_01_A", "REG 12", "MC_01_A (1)", "", "reg"):
        assert ns.clean_theme(nm) == "", nm
    assert ns.clean_theme("90s Music_4") == "90s Music"
    assert ns.clean_theme("Space-Race 2") == "Space Race"


def test_theme_can_be_switched_off(env):
    ns, gs, pb, _ = env
    s = gs.load(); s["format"]["show_themes"] = False; gs.save(s)
    out = texts(ns.native_render_section(pres(["MC", "REG", "BIG"], ["x", "Animals_1", "b"]), "format"))
    assert out[1] == "General Topic - 1 Point each"


def test_long_theme_text_shrinks_to_fit(env):
    ns = env[0]
    sl = ns.native_render_section(pres(["MC", "REG", "BIG"], ["x", "The Entire History Of The Wild West Frontier_1", "b"]), "format")
    sizes = [e["fontSize"] for e in sl[0]["elements"] if e["type"] == "text"]
    assert sizes[1] < sizes[0] and min(sizes) >= 22


def test_pill_colours_follow_round_type(env):
    ns = env[0]
    sl = ns.native_render_section(pres(["MC", "REG", "MISC", "MYS", "BIG"]), "format")
    imgs = [e for e in sl[0]["elements"] if e["type"] == "image"]
    assert len(imgs) == 1 + 5                                    # background + 5 pills
    assert len({e["src"] for e in imgs[1:]}) == 5                # 5 different colours
    for e in imgs[1:]:
        assert e["width"] == 590 and e["height"] == 58


def test_format_slide_is_manual_and_not_a_round(env):
    ns = env[0]
    m = ns.native_render_section(pres(["MC", "BIG", "REG"][:3]), "format")[0]["metadata"]
    assert m["roundType"] == "FORMAT" and m["isRoundTitle"] is False and m["isGlobalSlide"]


# ---- company / rules uploads ----
def test_company_and_rules_follow_upload_order_and_can_be_toggled(env):
    ns, gs, pb, _ = env
    gs.add_image("company", "about.png", PNG)
    gs.add_image("rules", "r1.png", PNG); gs.add_image("rules", "r2.jpg", PNG)
    p = pres(["MC", "BIG", "REG"])
    assert len(ns.native_render_section(p, "company")) == 1
    r = ns.native_render_section(p, "rules")
    assert len(r) == 2 and [s["metadata"]["slideIndexInRound"] for s in r] == [0, 1]
    assert all(s["metadata"]["roundType"] == "RULES" and s["elements"][0]["type"] == "image" for s in r)
    s = gs.load(); s["rules"]["enabled"] = False; gs.save(s)
    assert ns.native_render_section(p, "rules") == []
    assert len(ns.native_render_section(p, "company")) == 1


def test_nothing_uploaded_renders_nothing_but_format_still_appears(env):
    ns = env[0]
    p = pres(["MC", "BIG", "REG"])
    assert ns.native_render_section(p, "company") == [] and ns.native_render_section(p, "rules") == []
    assert len(ns.native_render_section(p, "format")) == 1


def test_settings_persist_on_disk_across_a_restart(env):
    ns, gs, pb, tmp = env
    gs.add_image("company", "about.png", PNG)
    f = gs.load()["company"]["images"][0]
    assert (tmp / "Files" / "Trivia" / "GlobalSlides" / f).is_file()
    sys.modules.pop("global_slides", None)
    import global_slides as again
    assert again.load()["company"]["images"] == [f]


def test_upload_validation_and_path_safety(env):
    gs = env[1]
    with pytest.raises(ValueError): gs.add_image("company", "evil.exe", b"MZ")
    with pytest.raises(ValueError): gs.add_image("company", "a.png", b"")
    with pytest.raises(ValueError): gs.add_image("nope", "a.png", PNG)
    with pytest.raises(ValueError): gs.remove_image("../../etc/passwd")
    assert gs.image_path("../x.png") is None


def test_remove_deletes_file_and_reference(env):
    gs = env[1]
    gs.add_image("rules", "a.png", PNG)
    f = gs.load()["rules"]["images"][0]
    gs.remove_image(f)
    assert gs.load()["rules"]["images"] == [] and gs.image_path(f) is None


def test_missing_file_reference_is_dropped_not_crashing(env):
    ns, gs, pb, tmp = env
    gs.add_image("company", "a.png", PNG)
    f = gs.load()["company"]["images"][0]
    (tmp / "Files" / "Trivia" / "GlobalSlides" / f).unlink()
    assert gs.load()["company"]["images"] == []
    assert ns.native_render_section(pres(["MC", "BIG", "REG"]), "company") == []


# ---- placement ----
def test_sections_order_company_rules_format_after_location_before_round_1():
    src = (Path(__file__).resolve().parents[1] / "routes" / "slide_fetcher.py").read_text()
    loc = src.index('{"name": "location", "type": "location"}')
    glob = src.index('for _gname in ("company", "rules", "format")')
    rnd = src.index("round_files", glob)
    assert loc < glob < rnd


def test_editor_does_not_count_global_slides_as_rounds():
    src = (ROOT / "frontend/src/pages/trivia/Editor.jsx").read_text()
    assert src.count("'COMPANY', 'RULES', 'FORMAT'") >= 3


def test_special_show_gets_format_for_its_own_round_count(env):
    ns, gs, pb, tmp = env
    types = ["MC", "REG", "REG", "MISC", "MYS", "REG", "BIG"]
    out = texts(ns.native_render_section(pres(types), "format"))
    assert len(out) == 7 and out[0].startswith("Multiple") and out[-1].startswith("The BIG")


def test_assets_bundled_for_the_installer():
    sc = (ROOT / "scripts" / "build_sidecar.py").read_text()
    assert "'assets'}{os.pathsep}assets" in sc               # whole assets/ dir ships, incl. format/
    for c in ("green", "red", "blue", "purple", "gold", "grey"):
        assert (Path(__file__).resolve().parents[1] / "assets" / "slides" / "format" / f"pill-{c}.png").is_file()
    assert (Path(__file__).resolve().parents[1] / "assets" / "slides" / "format" / "format-bg-placeholder.png").is_file()


def test_routes_are_admin_only_for_writes():
    src = (Path(__file__).resolve().parents[1] / "native" / "global_slides_router.py").read_text()
    assert src.count("await _admin(request)") >= 3 and '"admin", "master_admin"' in src
