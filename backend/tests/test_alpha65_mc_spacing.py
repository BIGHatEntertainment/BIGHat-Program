from models import Slide, Element
from hybrid_pptx_converter import HybridPPTXConverter

def _el(c, y):
    return Element(type="text", content=c, x=160, y=y, width=1600, height=60, fontSize=40)

def _fmt(q):
    s = Slide(order=1, background="x", elements=[_el("Question 6", 110), _el(q, 260),
              _el("A. One", 720), _el("B. Two", 760), _el("C. Three", 800), _el("D. Four", 840)])
    slides = [Slide(order=0, background="x", elements=[_el("Title", 50)]), s]
    HybridPPTXConverter(use_rust=False)._apply_formatting_rules(slides, "MC", 1)
    return {e.content: e for e in slides[1].elements}

def test_mc_spacing_50px():
    for q in ["Short?", "A much longer question " * 6]:
        d = _fmt(q)
        num, qq, a, b = d["Question 6"], d[q], d["A. One"], d["B. Two"]
        assert num.y == 200                                  # lowered 50px from 150
        assert qq.y - (num.y + num.height) == 50             # 50px under the number
        assert a.y - (qq.y + qq.height) == 50                # 50px under the question
        assert b.y > a.y and num.color == "#FFFFFF"
