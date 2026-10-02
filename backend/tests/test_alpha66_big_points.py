import native_slides as ns

def _big(answer):
    return ns.render_round_section(
        {"questions": [{"number": 1, "question": "Name them?", "answer": answer}],
         "name": "BIG", "type": "BIG", "tiebreaker": {"question": "TQ", "answer": "TA"}},
        {"type": "BIG", "name": "BIG", "order": 6})

def _texts(slide):
    return [e["content"] for e in slide["elements"] if e["type"] == "text"]

def test_points_follow_answer_count_capped_at_10():
    cases = {"a,b,c,d,e,f,g,h": 24, "a,b,c,d,e,f,g,h,i,j,k,l": 30, "a,b,c,d,e,f,g,h,i,j": 30, "a": 3}
    for ans, pts in cases.items():
        sl = _big(ans)
        for idx in (1, 3):                                   # question + review
            t = _texts(sl[idx])
            assert t[0] == "3 Points Each. No Order."
            assert t[1] == "Name them?"
            assert t[2] == f"For {pts} Points."

def test_newline_separated_answers_count_too():
    assert _texts(_big("a\nb\nc\nd")[1])[2] == "For 12 Points."

def test_answers_and_tiebreakers_unchanged():
    sl = _big("a,b,c")
    assert _texts(sl[4]) == ["1. a", "2. b", "3. c"]         # answers slide: numbered, in reveal order
    assert not any("points" in x.lower() for x in _texts(sl[5]))


MARVEL = ("Iron Man,The Incredible Hulk,Iron Man 2,Thor,Captain America: The First Avenger,"
          "The Avengers,Iron Man 3,Thor: The Dark World,Captain America: The Winter Soldier,"
          "Guardians of the Galaxy")

def _answer_els(ans):
    return [e for e in _big(ans)[4]["elements"] if e["type"] == "text"]

def test_answer_slide_numbered_in_order_and_fits_column():
    for ans in (MARVEL, MARVEL + ",Doctor Strange,Ant-Man,Black Panther,Wasp"):
        els = _answer_els(ans)
        names = ans.split(",")
        assert [e["content"] for e in els] == [f"{i+1}. {n}" for i, n in enumerate(names)]
        ys = [e["y"] for e in els]
        assert ys == sorted(ys) and len(set(ys)) == len(ys)       # strictly top to bottom = reveal order
        for a, b in zip(els, els[1:]):
            assert a["y"] + a["height"] <= b["y"]                  # no overlap between answers
        assert els[0]["y"] >= 225 and els[-1]["y"] + els[-1]["height"] <= 905
        assert all(706 <= e["x"] and e["x"] + e["width"] <= 706 + 508 for e in els)
        assert all(e["fontSize"] >= 18 for e in els)               # still readable

def test_long_answers_get_room_to_wrap():
    els = _answer_els(MARVEL)
    long_ = [e for e in els if "Winter Soldier" in e["content"]][0]
    short = [e for e in els if e["content"].endswith("Thor")][0]
    assert long_["height"] > short["height"]


def test_answer_boxes_fit_audience_plus_10_percent_font():
    import math
    for ans in (MARVEL, MARVEL + ",Doctor Strange,Ant-Man,Black Panther,Wasp"):
        for e in _answer_els(ans):
            eff = e["fontSize"] * 1.10
            lines = math.ceil(len(e["content"]) * eff * 0.55 / e["width"])
            assert e["height"] >= lines * eff * 1.2 - 1, e["content"]
