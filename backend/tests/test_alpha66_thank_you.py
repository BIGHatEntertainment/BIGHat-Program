import native_slides as ns

def test_thank_you_image_is_bundled_and_real():
    p = ns.bundled_asset_path("assets", "slides", "thank_you.png")
    assert p is not None and p.stat().st_size > 50_000
    assert p.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"

def test_winners_section_is_the_thank_you_image():
    w = ns.render_winners_section()
    assert len(w) == 4                      # thank-you + 3rd + 2nd + 1st
    s = w[0]
    assert s["metadata"]["roundType"] == "WINNERS" and s["metadata"]["slideIndexInRound"] == 0
    assert s["metadata"]["isThankYou"] is True
    imgs = [e for e in s["elements"] if e["type"] == "image"]
    assert len(imgs) == 1 and imgs[0]["src"].startswith("data:image/png;base64,")
    assert (imgs[0]["x"], imgs[0]["y"], imgs[0]["width"], imgs[0]["height"]) == (0, 0, 1920, 1080)
    assert not [e for e in s["elements"] if e["type"] == "text"]      # image only

def test_dispatcher_serves_it_and_final_scores_follow():
    pres = {"roundFiles": []}
    w = ns.native_render_section(pres, "winners", {})
    f = ns.native_render_section(pres, "final_scores", {})
    assert w[0]["metadata"].get("isThankYou") and not f[0]["metadata"].get("isThankYou")
    assert f[0]["metadata"]["slideIndexInRound"] == 4                 # final scores slide unchanged

def test_sections_list_puts_thank_you_after_rounds_before_final_scores():
    import inspect
    from routes import slide_fetcher as sf
    src = inspect.getsource(sf.get_sections_list)
    assert src.index('"name": "winners"') < src.index('"name": "final_scores"')
    assert src.index("roundFiles") < src.index('"name": "winners"')


def test_winners_section_is_thank_you_then_3rd_2nd_1st():
    w = ns.render_winners_section()
    assert [s["metadata"]["slideIndexInRound"] for s in w] == [0, 1, 2, 3]
    assert all(s["metadata"]["roundType"] == "WINNERS" for s in w)
    assert w[0]["metadata"].get("isThankYou") and not w[0]["metadata"].get("isPlaceSlide")
    # alpha.87: each place slide is a full-screen VIDEO that says its own place
    # ("3rd" / "2nd" / "1st"), so there are no text labels any more.
    vids = [[e["videoSrc"] for e in s["elements"] if e["type"] == "video"] for s in w[1:]]
    assert vids == [["/api/native/winners-video/3rd"], ["/api/native/winners-video/2nd"],
                    ["/api/native/winners-video/1st"]]
    assert [s["metadata"]["place"] for s in w[1:]] == [3, 2, 1]

def test_place_slides_leave_the_top_free_for_the_injected_team_name():
    # alpha.87: the video's own top area holds the name; the slide itself must not
    # carry any text of its own (it would sit on top of the name), and must hold
    # no pre-made winner-* elements (the editor adds those).
    for s in ns.render_winners_section()[1:]:
        assert not [e for e in s["elements"] if e["type"] == "text"]
        assert not [e for e in s["elements"] if (e.get("id") or "").startswith("winner-")]


def test_final_scores_follow_the_place_slides_at_index_4():
    f = ns.native_render_section({"roundFiles": []}, "final_scores", {})
    assert f[0]["metadata"]["roundType"] == "WINNERS" and f[0]["metadata"]["slideIndexInRound"] == 4
