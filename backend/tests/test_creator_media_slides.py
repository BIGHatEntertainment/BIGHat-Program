"""v32.1.7: .bighat files from the File Creator tool (PR #2) carry per-question media {image, video, poster} under assets/.
The Program must keep it on import AND show it on the slides, for every round type, from every file shape.
Fixtures are built with the Creator tool's OWN builder shape (manifest.json + payload.json + assets/qN.<ext>, qN_v.<ext>, qN_p.<ext>)."""
import io, json, sys, zipfile
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import native_slides as ns
from native import creator_bighat as cb

MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 2000
PNG = (b"\x89PNG\r\n\x1a\n" + b"\x00" * 40)
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 40
GIF = b"GIF89a" + b"\x00" * 40


def build(rtype, questions, assets, cover=True):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("manifest.json", json.dumps({"format_version": "1.0", "content_id": "cid-1", "type": "round",
                                                 "round_type": rtype, "round_name": f"{rtype}__t"}))
        z.writestr("payload.json", json.dumps({"name": "T", "round_type": rtype, "questions": questions,
                                               "cover_image": "assets/title_card.png" if cover else None}))
        for n, b in assets.items():
            z.writestr(n, b)
        if cover:
            z.writestr("assets/title_card.png", PNG)
    return buf.getvalue()


QS = [{"n": 1, "prompt": "img", "answer": "a", "media": {"image": "assets/q1.jpg"}},
      {"n": 2, "prompt": "gif", "answer": "b", "media": {"image": "assets/q2.gif"}},
      {"n": 3, "prompt": "vid+poster", "answer": "c", "media": {"video": "assets/q3_v.mp4", "poster": "assets/q3_p.jpg"}},
      {"n": 4, "prompt": "img+vid", "answer": "d", "media": {"image": "assets/q4.png", "video": "assets/q4_v.mp4"}},
      {"n": 5, "prompt": "none", "answer": "e"}]
ASSETS = {"assets/q1.jpg": JPG, "assets/q2.gif": GIF, "assets/q3_v.mp4": MP4, "assets/q3_p.jpg": JPG,
          "assets/q4.png": PNG, "assets/q4_v.mp4": MP4}


def sources(tmp_path, rtype):
    """The same round in the two shapes the Program meets: the Creator ZIP itself, and the converted JSON copy."""
    raw = build(rtype, QS, ASSETS)
    z = tmp_path / f"{rtype}_zip.bighat"
    z.write_bytes(raw)
    doc, why = cb.read_zip(raw, f"{rtype}__t.bighat")
    assert doc, why
    j = tmp_path / f"{rtype}_json.bighat"
    j.write_text(json.dumps(cb.normalise(doc)))
    return {"zip": z, "json": j}


def slides_for(path, rtype):
    r = ns.load_round_from_disk({"path": str(path), "type": rtype, "name": "T"})
    assert r, "round did not load"
    return ns.render_round_section(r, {"type": rtype, "name": "T", "path": str(path)})


def media_of(slide):
    return [(e["type"], (e.get("videoSrc") or e.get("src") or "").split(";")[0][5:]) for e in slide["elements"] if e["type"] in ("image", "video")]


def qslide(slides, n):
    return next(s for s in slides if s["metadata"].get("questionNumber") == n and not s["metadata"].get("isReview")
                and not s["metadata"].get("isAnswers"))


# -------------------------------------------------------------- importer keeps everything
def test_import_keeps_image_video_and_poster():
    doc, why = cb.read_zip(build("REG", QS, ASSETS), "REG__t.bighat")
    q = {x["n"]: x for x in doc["questions"]}
    assert q[1]["image_data_url"].startswith("data:image/jpeg")
    assert q[2]["image_data_url"].startswith("data:image/gif")
    assert q[3]["video_data_url"].startswith("data:video/mp4") and q[3]["poster_data_url"].startswith("data:image/jpeg")
    assert q[4]["image_data_url"].startswith("data:image/png") and q[4]["video_data_url"].startswith("data:video/mp4")
    assert not any(k in q[5] for k in ("image_data_url", "video_data_url", "poster_data_url"))


def test_a_video_over_the_size_limit_is_skipped_not_fatal(monkeypatch):
    monkeypatch.setattr(cb, "MAX_VIDEO_BYTES", 100)
    doc, _ = cb.read_zip(build("REG", QS, ASSETS), "REG__t.bighat")
    q3 = [x for x in doc["questions"] if x["n"] == 3][0]
    assert "video_data_url" not in q3 and q3["poster_data_url"]


# -------------------------------------------------------------- slides, every type, both file shapes
@pytest.mark.parametrize("shape", ["zip", "json"])
@pytest.mark.parametrize("rtype", ["REG", "MISC", "MYS", "MC"])
def test_every_question_round_shows_its_media_on_its_own_slide(tmp_path, rtype, shape):
    sl = slides_for(sources(tmp_path, rtype)[shape], rtype)
    assert media_of(qslide(sl, 1)) == [("image", "image/jpeg")]
    assert media_of(qslide(sl, 2)) == [("image", "image/gif")]
    assert media_of(qslide(sl, 3)) == [("image", "image/jpeg"), ("video", "video/mp4")]      # poster behind the playing video
    assert media_of(qslide(sl, 4)) == [("image", "image/png"), ("video", "video/mp4")]
    assert media_of(qslide(sl, 5)) == []                                                      # no leakage into a slide with none


@pytest.mark.parametrize("shape", ["zip", "json"])
def test_media_never_leaks_to_other_slides(tmp_path, shape):
    sl = slides_for(sources(tmp_path, "REG")[shape], "REG")
    carrying = {s["metadata"].get("questionNumber") for s in sl if any(e["type"] == "video" or (e["type"] == "image" and e.get("width") == 508) for e in s["elements"])}
    assert carrying == {1, 2, 3, 4}


def test_mc_media_sits_above_the_options_and_does_not_cover_them(tmp_path):
    qs = [{"n": 1, "prompt": "p", "answer": "A", "options": ["A", "B", "C", "D"], "correct_index": 0, "media": {"image": "assets/q1.jpg"}}]
    z = tmp_path / "mc.bighat"
    z.write_bytes(build("MC", qs, {"assets/q1.jpg": JPG}))
    s = qslide(slides_for(z, "MC"), 1)
    img = [e for e in s["elements"] if e["type"] == "image"][0]
    opts = [e for e in s["elements"] if e["type"] == "text" and str(e.get("content", e.get("text", ""))).startswith(("A.", "B."))]
    assert img["y"] + img["height"] <= 720 and len(opts) == 2


@pytest.mark.parametrize("shape", ["zip", "json"])
def test_big_round_shows_media_on_clue_and_review_and_narrows_text_only_then(tmp_path, shape):
    qs = [{"n": 1, "prompt": "clue", "answer": "x", "media": {"image": "assets/q1.jpg"}}]
    z = tmp_path / "big.bighat"
    z.write_bytes(build("BIG", qs, {"assets/q1.jpg": JPG}))
    doc, _ = cb.read_zip(z.read_bytes(), "BIG__t.bighat")
    j = tmp_path / "bigj.bighat"; j.write_text(json.dumps(cb.normalise(doc)))
    sl = slides_for({"zip": z, "json": j}[shape], "BIG")
    clue = [s for s in sl if s["metadata"].get("slideIndexInRound") == 1][0]
    assert media_of(clue) == [("image", "image/jpeg")]
    assert max(e["width"] for e in clue["elements"] if e["type"] == "text" and e["y"] == 300) == 1180
    # a BIG round WITHOUT media keeps the old full-width layout
    z2 = tmp_path / "big2.bighat"
    z2.write_bytes(build("BIG", [{"n": 1, "prompt": "clue", "answer": "x"}], {}))
    clue2 = [s for s in slides_for(z2, "BIG") if s["metadata"].get("slideIndexInRound") == 1][0]
    assert max(e["width"] for e in clue2["elements"] if e["type"] == "text" and e["y"] == 300) == 1600


def test_older_rounds_still_work(tmp_path):
    """A converted copy made BEFORE this change (image_data_url only) and a round with a single media_url string."""
    doc = {"schema": "bighat-round/v1", "round_type": "REG", "name": "old", "questions": [
        {"number": 1, "question": "q", "answer": "a", "image_data_url": "data:image/gif;base64,R0lGOD"},
        {"number": 2, "question": "q", "answer": "a", "media": "assets/none.gif"}]}
    p = tmp_path / "old.bighat"; p.write_text(json.dumps(doc))
    sl = slides_for(p, "REG")
    assert media_of(qslide(sl, 1)) == [("image", "image/gif")] and media_of(qslide(sl, 2)) == []


def test_a_question_media_helper_is_the_single_source():
    assert ns.question_media({"video_data_url": "data:video/mp4;base64,A"})["video"].startswith("data:video")
    assert ns.question_media({"media_url": "data:video/mp4;base64,A"})["video"]
    assert ns.question_media({"media_url": "data:image/png;base64,A"})["image"]
    assert ns.question_media(None) == {"image": "", "video": "", "poster": ""}
