"""alpha.88: sponsor slides = global sponsors (ordered) -> this location's sponsor -> FINAL sponsor slide."""
import base64, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pytest

def png(tag: int) -> bytes:                       # distinct bytes per image so order is checkable
    return b"\x89PNG\r\n\x1a\n" + bytes([tag]) * 300

def data_of(slide):
    src = [e for e in slide["elements"] if e["type"] == "image"][0]["src"]
    return base64.b64decode(src.split(",", 1)[1])

@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("BIGHAT_FILES_DIR", str(tmp_path))
    for n in list(sys.modules):
        if n in ("round_usage", "native_slides", "presentation_builder", "slide_style", "global_slides"):
            sys.modules.pop(n, None)
    import native_slides as ns, global_slides as gs
    return ns, gs, tmp_path

def make_location(ns, with_image=True, tag=9, mime="image/png", ext=".png"):
    d = ns._docs_root() / "Files" / "Locations" / "monkey-pants"
    (d / "sponsor").mkdir(parents=True, exist_ok=True)
    meta = {"id": "loc-1", "name": "Monkey Pants", "slug": "monkey-pants"}
    if with_image:
        (d / "sponsor" / f"abc{ext}").write_bytes(png(tag))
        meta["sponsor_image"] = {"id": "abc", "ext": ext, "mime": mime}
    (d / "location.json").write_text(json.dumps(meta))
    return {"location_id": "loc-1", "name": "x", "roundFiles": []}

def test_order_is_global_then_location_then_final(env):
    ns, gs, _ = env
    gs.add_image("sponsors", "a.png", png(1)); gs.add_image("sponsors", "b.png", png(2))
    gs.add_image("sponsor_final", "final.png", png(3))
    pres = make_location(ns, tag=9)
    sl = ns.native_render_section(pres, "sponsors")
    kinds = [s["metadata"]["sponsorKind"] for s in sl]
    assert kinds == ["global", "global", "location", "final"]
    assert [data_of(s)[-1] for s in sl] == [1, 2, 9, 3]
    assert [s["metadata"]["slideIndexInRound"] for s in sl] == [0, 1, 2, 3]
    assert all(s["metadata"]["roundType"] == "SPONSOR" for s in sl)

def test_final_slide_is_last_even_when_uploaded_first(env):
    ns, gs, _ = env
    gs.add_image("sponsor_final", "final.png", png(3))
    gs.add_image("sponsors", "a.png", png(1))
    sl = ns.native_render_section({"name": "x", "roundFiles": []}, "sponsors")
    assert [s["metadata"]["sponsorKind"] for s in sl] == ["global", "final"]

def test_no_location_image_just_skips_that_slot(env):
    ns, gs, _ = env
    gs.add_image("sponsors", "a.png", png(1)); gs.add_image("sponsor_final", "f.png", png(3))
    pres = make_location(ns, with_image=False)
    assert [s["metadata"]["sponsorKind"] for s in ns.native_render_section(pres, "sponsors")] == ["global", "final"]

def test_location_only_and_final_only(env):
    ns, gs, _ = env
    pres = make_location(ns)
    assert [s["metadata"]["sponsorKind"] for s in ns.native_render_section(pres, "sponsors")] == ["location"]
    gs.add_image("sponsor_final", "f.png", png(3))
    assert [s["metadata"]["sponsorKind"] for s in ns.native_render_section(pres, "sponsors")] == ["location", "final"]

def test_final_is_one_slot_a_new_upload_replaces_it(env):
    ns, gs, tmp = env
    s1 = gs.add_image("sponsor_final", "one.png", png(3))
    first = s1["sponsors"]["final"]
    s2 = gs.add_image("sponsor_final", "two.png", png(4))
    assert s2["sponsors"]["final"] != first
    assert gs.image_path(first) is None                       # old file removed
    sl = ns.native_render_section({"roundFiles": []}, "sponsors")
    assert len(sl) == 1 and data_of(sl[0])[-1] == 4

def test_removing_files_clears_slots(env):
    ns, gs, _ = env
    gs.add_image("sponsor_final", "f.png", png(3))
    f = gs.load()["sponsors"]["final"]
    assert gs.remove_image(f)["sponsors"]["final"] is None
    a = gs.add_image("sponsors", "a.png", png(1))["sponsors"]["images"][0]
    assert gs.remove_image(a)["sponsors"]["images"] == []

def test_disabled_gives_no_sponsor_slides(env):
    ns, gs, _ = env
    gs.add_image("sponsors", "a.png", png(1))
    cur = gs.load(); cur["sponsors"]["enabled"] = False; gs.save(cur)
    assert ns.native_render_section(make_location(ns), "sponsors") == []

def test_nothing_loaded_anywhere_keeps_the_placeholder(env):
    ns, gs, _ = env
    sl = ns.native_render_section({"roundFiles": []}, "sponsors")
    assert len(sl) == 1 and sl[0]["elements"][0]["content"] == "Thanks to our Sponsors"

def test_old_presentations_with_sponsorFiles_still_work(env):
    ns, gs, _ = env
    # a bare data URL has no image extension, so it falls back to the placeholder
    sl = ns.native_render_section({"roundFiles": [], "sponsorFiles": ["data:image/png;base64,AAAA"]}, "sponsors")
    assert len(sl) == 1 and sl[0]["elements"][0]["content"] == "Thanks to our Sponsors"
    sl = ns.native_render_section({"roundFiles": [], "sponsorFiles": ["x/y/logo.png"]}, "sponsors")
    assert len(sl) == 1 and sl[0]["metadata"]["sponsorKind"] == "legacy"

def test_missing_location_file_is_skipped_not_a_crash(env):
    ns, gs, _ = env
    pres = make_location(ns)
    (ns._docs_root() / "Files" / "Locations" / "monkey-pants" / "sponsor" / "abc.png").unlink()
    assert ns.native_render_section(pres, "sponsors")[0]["elements"][0]["type"] == "text"

def test_settings_put_keeps_order_and_never_drops_files(env):
    ns, gs, _ = env
    a = gs.add_image("sponsors", "a.png", png(1))["sponsors"]["images"][0]
    b = gs.add_image("sponsors", "b.png", png(2))["sponsors"]["images"][1]
    cur = gs.load()
    cur["sponsors"]["images"] = [b, a]; gs.save(cur)
    assert gs.load()["sponsors"]["images"] == [b, a]
