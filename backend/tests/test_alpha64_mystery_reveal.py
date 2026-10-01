import native_slides as ns

def _mys():
    qs=[{"number":i,"question":f"Q{i}","answer":f"A{i}"} for i in range(1,11)]
    qs[9]={"number":10,"question":"Theme","answer":"Pizza"}
    return ns.render_round_section({"questions":qs,"name":"Mystery","type":"MYS"},
                                   {"type":"MYS","name":"Mystery","order":5})

def _texts(slide):
    return [(e.get("text") or e.get("content"), e.get("color")) for e in slide["elements"]]

def test_review_has_yellow_theme_line():
    r=[s for s in _mys() if s["metadata"].get("isReview")][0]
    t=_texts(r)
    assert t[-1][0]=="10. Mystery Theme?" and t[-1][1].lower()=="#f4c430"

def test_answers_reveal_order():
    a=[s for s in _mys() if s["metadata"].get("isAnswers")][0]
    t=[x[0] for x in _texts(a)]
    assert t[8]=="9. A9" and t[9]=="Mystery Theme?" and t[10]=="10. Pizza" and len(t)==11
