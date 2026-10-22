"""v32.1.10: the MC answer slide shows the letter with the answer ("3. B. Seinfeld") so a paper sheet with A/B/C/D bubbles can be graded.
The letter must come from the question's real data and must never be a guess."""
import json, sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import native_slides as ns


def q(answer, options, **kw):
    return {"number": 1, "question": "q", "answer": answer, "options": options, **kw}


OPTS = ["M*A*S*H", "Seinfeld", "Cheers", "Friends"]


@pytest.mark.parametrize("answer,letter", [("M*A*S*H", "A"), ("Seinfeld", "B"), ("Cheers", "C"), ("Friends", "D")])
def test_the_letter_follows_the_answer_text(answer, letter):
    assert ns.correct_letter(q(answer, OPTS)) == letter


@pytest.mark.parametrize("variant", ["seinfeld", "  Seinfeld  ", "SEINFELD", "Seinfeld.", "Sein  feld".replace("Sein  feld", "Seinfeld")])
def test_matching_ignores_case_spacing_and_a_trailing_dot(variant):
    assert ns.correct_letter(q(variant, OPTS)) == "B"


def test_internal_spacing_is_collapsed():
    assert ns.correct_letter(q("Mighty   Ducks", ["x", "Mighty Ducks", "y", "z"])) == "B"


def test_the_stored_marker_is_used_when_the_text_does_not_match():
    assert ns.correct_letter(q("the sitcom about nothing", OPTS, correctOption=1)) == "B"
    assert ns.correct_letter(q("", OPTS, correct_index=3)) == "D"


def test_the_answer_text_wins_when_the_marker_disagrees():
    """A wrong marker must not print the wrong letter next to the right answer."""
    assert ns.correct_letter(q("Cheers", OPTS, correctOption=0)) == "C"


def test_a_bare_letter_answer_is_accepted():
    assert ns.correct_letter(q("c", OPTS)) == "C" and ns.correct_letter(q("D", OPTS)) == "D"


def test_object_style_options_work():
    objs = [{"text": "M*A*S*H"}, {"label": "Seinfeld"}, {"value": "Cheers"}, {"option": "Friends"}]
    assert ns.correct_letter(q("Cheers", objs)) == "C"


@pytest.mark.parametrize("bad", [
    q("Nothing like these", OPTS),                        # answer matches no option, no marker
    q("Seinfeld", []), q("Seinfeld", ["only one"]),       # not a multiple-choice question
    q("", OPTS),                                          # no answer, no marker
    q("Seinfeld", ["Same", "Same", "Cheers", "Friends"]) | {"answer": "Same"},   # duplicate option text, no marker
    q("x", OPTS, correctOption=7),                        # marker out of range
    q("x", OPTS, correctOption=True),                     # a bool is not an index
])
def test_it_never_guesses(bad):
    assert ns.correct_letter(bad) == ""


def test_duplicate_option_text_is_resolved_by_the_marker_only():
    o = ["Same", "Other", "Same", "Third"]
    assert ns.correct_letter(q("Same", o, correctOption=2)) == "C"
    assert ns.correct_letter(q("Same", o)) == ""


def test_not_a_dict_is_safe():
    assert ns.correct_letter(None) == "" and ns.correct_letter("x") == ""


# ----------------------------------------------------------------- the slide itself, from a real file on disk
def render(tmp_path, rtype, questions):
    p = tmp_path / f"{rtype}__t.bighat"
    p.write_text(json.dumps({"schema": "bighat-round/v1", "round_type": rtype, "name": "t", "questions": questions}))
    r = ns.load_round_from_disk({"path": str(p), "type": rtype, "name": "t"})
    return ns.render_round_section(r, {"type": rtype, "name": "t", "path": str(p)})


def answer_lines(slides):
    a = [s for s in slides if s["metadata"].get("isAnswers")][0]
    return [e["content"] for e in a["elements"] if e["type"] == "text"]


def mc_questions(n=10):
    out = []
    for i in range(n):
        o = [f"Choice {i}-{j}" for j in range(4)]
        out.append({"n": i + 1, "prompt": f"Q{i + 1}", "answer": o[i % 4], "options": o, "correct_index": i % 4})
    return out


def test_the_mc_answer_slide_shows_the_letter_for_every_question(tmp_path):
    lines = answer_lines(render(tmp_path, "MC", mc_questions()))
    assert lines[0] == "1. A. Choice 0-0" and lines[1] == "2. B. Choice 1-1" and lines[3] == "4. D. Choice 3-3"
    assert len(lines) == 10 and all(l.split(". ")[1] in "ABCD" for l in lines)


def test_a_question_whose_letter_is_unknown_keeps_the_plain_answer(tmp_path):
    qs = mc_questions(3)
    qs[1]["answer"] = "matches nothing"
    qs[1]["correct_index"] = None
    assert answer_lines(render(tmp_path, "MC", qs))[1] == "2. matches nothing"


def test_a_file_with_no_marker_is_not_labelled_A(tmp_path):
    """The ZIP reader used to turn a missing marker into 0, which would have printed 'A' for every question."""
    qs = [{"n": 1, "prompt": "q", "answer": "off list", "options": ["w", "x", "y", "z"]}]
    assert answer_lines(render(tmp_path, "MC", qs))[0] == "1. off list"


@pytest.mark.parametrize("rtype", ["REG", "MISC", "MYS", "BIG"])
def test_other_round_types_are_unchanged(tmp_path, rtype):
    qs = [{"n": i + 1, "prompt": f"q{i}", "answer": f"ans{i}", "options": ["a", "b", "c", "d"], "correct_index": 1} for i in range(10)]
    lines = answer_lines(render(tmp_path, rtype, qs))
    assert not any(l.split(". ")[1:2] and l.split(". ")[1] in ("A", "B", "C", "D") and len(l.split(". ")) > 2 for l in lines)
    assert "ans0" in lines[0]


def test_the_letter_adds_only_three_characters_to_a_row(tmp_path):
    """A row is 1600px wide at 48px (about 50 characters). The letter adds 'B. ' = 3 characters, so an answer that fit before still fits;
    a very long answer wraps exactly as it did before the letter (that was already true and is not changed here)."""
    qs = mc_questions(10)
    sl = render(tmp_path, "MC", qs)
    el = [s for s in sl if s["metadata"].get("isAnswers")][0]["elements"][9]
    assert el["content"] == "10. B. Choice 9-1" and el["width"] == 1600 and el["fontSize"] == 48 and el["height"] >= 90
    plain = render(tmp_path, "REG", [{"n": i + 1, "prompt": "q", "answer": f"Choice {i}-{i % 4}"} for i in range(10)])
    pe = [s for s in plain if s["metadata"].get("isAnswers")][0]["elements"][9]
    assert (pe["x"], pe["y"], pe["width"], pe["height"], pe["fontSize"]) == (el["x"], el["y"], el["width"], el["height"], el["fontSize"])


def test_the_question_slide_letters_and_the_answer_letters_agree(tmp_path):
    sl = render(tmp_path, "MC", mc_questions(5))
    q3 = [s for s in sl if s["metadata"].get("questionNumber") == 3 and not s["metadata"].get("isReview")][0]
    shown = {e["content"][0]: e["content"][3:] for e in q3["elements"] if e["type"] == "text" and e["content"][1:3] == ". " and e["content"][0] in "ABCD"}
    ans = answer_lines(sl)[2]                                            # "3. C. Choice 2-2"
    letter, text = ans.split(". ")[1], ans.split(". ", 2)[2]
    assert shown[letter] == text
