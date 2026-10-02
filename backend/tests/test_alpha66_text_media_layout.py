from models import Slide, Element
from hybrid_pptx_converter import HybridPPTXConverter

COL_L, COL_R = 706, 706 + 508

def _t(c, y):
    return Element(type="text", content=c, x=160, y=y, width=1600, height=60, fontSize=40)

def _fmt(rtype, q, media=None):
    els = [_t("Question 1", 110), _t(q, 260)]
    if media == "gif":
        els.append(Element(type="image", src="data:image/gif;base64,AAAA", x=400, y=700, width=1000, height=600))
    if media == "video":
        els.append(Element(type="video", videoSrc="data:video/mp4;base64,AAAA", x=300, y=650, width=1200, height=700))
    slides = [Slide(order=0, background="x", elements=[_t("Title", 50)]),
              Slide(order=1, background="x", elements=els)]
    HybridPPTXConverter(use_rust=False)._apply_formatting_rules(slides, rtype, 2)
    return slides[1]

def _by(slide):
    return {e.content: e for e in slide.elements if e.type == "text"}

def test_text_spacing_all_three_round_types():
    for rt in ("REG", "MISC", "MYS"):
        for q in ("Short?", "A much longer question " * 6):
            d = _by(_fmt(rt, q))
            num, qq = d["Question 1"], d[q]
            assert num.y == 200, rt
            assert qq.y - (num.y + num.height) == 50, rt
            assert num.x == 706 and qq.width == 508

def test_media_sits_50px_under_text_inside_column():
    for rt in ("REG", "MISC", "MYS"):
        for kind in ("gif", "video"):
            s = _fmt(rt, "What is shown here?", kind)
            qq = _by(s)["What is shown here?"]
            m = [e for e in s.elements if e.type in ("image", "video")][0]
            assert m.y - (qq.y + qq.height) == 50, (rt, kind)
            assert m.x >= COL_L and m.x + m.width <= COL_R, (rt, kind)
            assert m.y + m.height <= 905, (rt, kind)
