import native_slides as ns

def _round(t, n=10):
    qs=[{"number":i,"question":f"Q{i}","options":["a","b","c","d"],"answer":"A"} for i in range(1,n+1)]
    return ns.render_round_section({"questions":qs,"name":t,"type":t,"tiebreaker":{"question":"x","answer":"y"}},
                                   {"type":t,"name":t,"order":2})

def test_score_slide_last_for_non_big():
    for t in ("MC","REG","MISC","MYS"):
        sl=_round(t)
        flagged=[i for i,s in enumerate(sl) if s["metadata"].get("isScoreSlide")]
        assert flagged==[len(sl)-1], t
        assert sl[-1]["elements"]==[]
        assert sl[-1]["metadata"]["roundNumber"]==2

def test_no_score_slide_for_big():
    assert not any(s["metadata"].get("isScoreSlide") for s in _round("BIG",1))

def test_score_slide_does_not_look_like_answers():
    sl=_round("MC")
    assert sl[-1]["metadata"].get("slideIndexInRound") is None
