"""
Regression tests for v32.0.0-alpha.50 — verbatim port of the prototype's
slide-per-round structure.

Prototype spec (from `components/trivia/editor/PresentationMode.jsx`
which docs the slideIndexInRound layout the Presenter's answer-reveal +
auto-advance timer key off):

    MC/REG/MISC:  0=title, 1-10=questions, 11=review, 12=.gif(STOP), 13=answers
    MYS:          0=title, 1-9=questions,  10=review, 11=.gif(STOP), 12=answers
    BIG:          0=title, 1=question, 2=.gif(STOP), 3=review, 4=answers,
                  5=tiebreaker-question, 6=tiebreaker-answer

Answer slides MUST have NO title element — `getAnswerCount` counts ALL
text elements as answers. Adding a header offsets the reveal by 1.
"""
from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _fresh_native_slides():
    for name in list(sys.modules):
        if name.startswith("native_slides"):
            sys.modules.pop(name, None)
    from native_slides import render_round_section
    return render_round_section


def _make_questions(n: int):
    return [
        {
            "number": i + 1,
            "question": f"Question {i + 1}?",
            "options": ["A", "B", "C", "D"],
            "correctOption": 0,
            "answer": f"Answer {i + 1}",
        }
        for i in range(n)
    ]


# ---- Slide counts per type ----------------------------------------------

def test_mc_round_produces_exactly_14_slides(tmp_path, monkeypatch):
    monkeypatch.setenv("BIGHAT_FILES_DIR", str(tmp_path))
    render = _fresh_native_slides()
    slides = render(
        {"round_type": "MC", "questions": _make_questions(10), "name": "MC-01-A"},
        {"type": "MC", "name": "MC-01-A", "order": 1},
    )
    assert len(slides) == 14, f"MC prototype spec = 14 slides, got {len(slides)}"


def test_reg_round_produces_exactly_14_slides(tmp_path, monkeypatch):
    monkeypatch.setenv("BIGHAT_FILES_DIR", str(tmp_path))
    render = _fresh_native_slides()
    slides = render(
        {"round_type": "REG", "questions": _make_questions(10), "name": "REG-01-A"},
        {"type": "REG", "name": "REG-01-A", "order": 2},
    )
    assert len(slides) == 14, f"REG prototype spec = 14 slides, got {len(slides)}"


def test_misc_round_produces_exactly_14_slides(tmp_path, monkeypatch):
    monkeypatch.setenv("BIGHAT_FILES_DIR", str(tmp_path))
    render = _fresh_native_slides()
    slides = render(
        {"round_type": "MISC", "questions": _make_questions(10), "name": "MISC-01-A"},
        {"type": "MISC", "name": "MISC-01-A", "order": 3},
    )
    assert len(slides) == 14


def test_mys_round_produces_exactly_13_slides(tmp_path, monkeypatch):
    monkeypatch.setenv("BIGHAT_FILES_DIR", str(tmp_path))
    render = _fresh_native_slides()
    slides = render(
        {"round_type": "MYS", "questions": _make_questions(9), "name": "MYS-01-A"},
        {"type": "MYS", "name": "MYS-01-A", "order": 4},
    )
    assert len(slides) == 13, f"MYS prototype spec = 13 slides, got {len(slides)}"


def test_big_round_produces_7_slides_with_tiebreaker(tmp_path, monkeypatch):
    monkeypatch.setenv("BIGHAT_FILES_DIR", str(tmp_path))
    render = _fresh_native_slides()
    slides = render(
        {
            "round_type": "BIG",
            "questions": [{"number": 1, "question": "Name 5 states.",
                           "answer": "Ohio\nTexas\nIowa\nMaine\nUtah"}],
            "tiebreaker": {"question": "Year of moon landing?", "answer": "1969"},
            "name": "BIG-01-A",
        },
        {"type": "BIG", "name": "BIG-01-A", "order": 5},
    )
    assert len(slides) == 7, f"BIG prototype spec = 7 slides, got {len(slides)}"


def test_big_round_produces_5_slides_without_tiebreaker(tmp_path, monkeypatch):
    monkeypatch.setenv("BIGHAT_FILES_DIR", str(tmp_path))
    render = _fresh_native_slides()
    slides = render(
        {
            "round_type": "BIG",
            "questions": [{"number": 1, "question": "Name 5 states.",
                           "answer": "Ohio\nTexas\nIowa\nMaine\nUtah"}],
            "name": "BIG-01-A",
        },
        {"type": "BIG", "name": "BIG-01-A", "order": 5},
    )
    # Without tiebreaker: 0=title, 1=Q, 2=gif, 3=review, 4=answers → 5
    assert len(slides) == 5


# ---- Slide index positions per prototype -------------------------------

def test_mc_slide_positions_match_prototype(tmp_path, monkeypatch):
    monkeypatch.setenv("BIGHAT_FILES_DIR", str(tmp_path))
    render = _fresh_native_slides()
    slides = render(
        {"round_type": "MC", "questions": _make_questions(10), "name": "MC-01-A"},
        {"type": "MC", "name": "MC-01-A", "order": 1},
    )
    # slideIndexInRound field must match prototype positions
    assert slides[0]["metadata"]["slideIndexInRound"] == 0
    assert slides[0]["metadata"]["isRoundTitle"] is True
    for i in range(1, 11):
        assert slides[i]["metadata"]["slideIndexInRound"] == i
        assert slides[i]["metadata"]["questionNumber"] == i
    assert slides[11]["metadata"]["slideIndexInRound"] == 11
    assert slides[11]["metadata"].get("isReview") is True
    assert slides[12]["metadata"]["slideIndexInRound"] == 12
    assert slides[12]["metadata"].get("isGifStop") is True
    assert slides[13]["metadata"]["slideIndexInRound"] == 13
    assert slides[13]["metadata"].get("isAnswers") is True


def test_big_slide_positions_match_prototype(tmp_path, monkeypatch):
    monkeypatch.setenv("BIGHAT_FILES_DIR", str(tmp_path))
    render = _fresh_native_slides()
    slides = render(
        {"round_type": "BIG",
         "questions": [{"number": 1, "question": "Q?",
                        "answer": "A1\nA2\nA3"}],
         "tiebreaker": {"question": "TB?", "answer": "TBA"},
         "name": "BIG-01-A"},
        {"type": "BIG", "name": "BIG-01-A", "order": 5},
    )
    # 0=title, 1=Q, 2=gif, 3=review, 4=answers, 5=TB-Q, 6=TB-A
    assert slides[0]["metadata"]["slideIndexInRound"] == 0
    assert slides[1]["metadata"]["slideIndexInRound"] == 1
    assert slides[1]["metadata"]["questionNumber"] == 1
    assert slides[2]["metadata"]["slideIndexInRound"] == 2
    assert slides[2]["metadata"].get("isGifStop") is True
    assert slides[3]["metadata"]["slideIndexInRound"] == 3
    assert slides[3]["metadata"].get("isReview") is True
    assert slides[4]["metadata"]["slideIndexInRound"] == 4
    assert slides[4]["metadata"].get("isAnswers") is True
    assert slides[5]["metadata"]["slideIndexInRound"] == 5
    assert slides[5]["metadata"].get("isTiebreaker") is True
    assert slides[6]["metadata"]["slideIndexInRound"] == 6
    assert slides[6]["metadata"].get("isAnswers") is True


# ---- Critical prototype invariant: answer slides have NO title ---------

def test_mc_answer_slide_has_no_title_element(tmp_path, monkeypatch):
    """Per prototype `getAnswerCount`: 'Answer slides have NO title - ALL
    text elements are answers'. Adding a title/header offsets the
    progressive reveal by 1 and the whole grading UX breaks."""
    monkeypatch.setenv("BIGHAT_FILES_DIR", str(tmp_path))
    render = _fresh_native_slides()
    slides = render(
        {"round_type": "MC", "questions": _make_questions(10), "name": "MC-01-A"},
        {"type": "MC", "name": "MC-01-A", "order": 1},
    )
    answers_slide = slides[13]
    text_elements = [e for e in answers_slide["elements"] if e["type"] == "text"]
    # ALL text elements must be answers — 10 of them for MC.
    assert len(text_elements) == 10, (
        f"MC answers slide must have exactly 10 text elements (one per Q), "
        f"got {len(text_elements)}. Any additional text (like a title) "
        f"breaks the prototype's progressive-reveal count."
    )
    # None of them should be a "Round X" header or "Answers" title.
    for el in text_elements:
        content = (el.get("content") or "")
        assert "answers" not in content.lower() or content.strip().startswith(("1.", "2.", "3.", "4.", "5.", "6.", "7.", "8.", "9.", "10.")), (
            f"MC answers slide text element looks like a header, not an answer: {content!r}"
        )


def test_mys_answer_slide_has_no_title_element_9_answers(tmp_path, monkeypatch):
    monkeypatch.setenv("BIGHAT_FILES_DIR", str(tmp_path))
    render = _fresh_native_slides()
    slides = render(
        {"round_type": "MYS", "questions": _make_questions(9), "name": "MYS-01-A"},
        {"type": "MYS", "name": "MYS-01-A", "order": 4},
    )
    answers_slide = slides[12]
    text_elements = [e for e in answers_slide["elements"] if e["type"] == "text"]
    assert len(text_elements) == 9, (
        f"MYS answers slide must have exactly 9 text elements, got {len(text_elements)}"
    )


def test_big_answer_slide_has_no_title_element(tmp_path, monkeypatch):
    monkeypatch.setenv("BIGHAT_FILES_DIR", str(tmp_path))
    render = _fresh_native_slides()
    slides = render(
        {"round_type": "BIG",
         "questions": [{"number": 1, "question": "Q?",
                        "answer": "A1\nA2\nA3\nA4\nA5"}],
         "name": "BIG-01-A"},
        {"type": "BIG", "name": "BIG-01-A", "order": 5},
    )
    answers_slide = slides[4]
    text_elements = [e for e in answers_slide["elements"] if e["type"] == "text"]
    # 5 answer lines, no title
    assert len(text_elements) == 5
    for el in text_elements:
        assert not (el.get("content") or "").lower().startswith("answers")


# ---- Gif STOP slide is present at correct position ---------------------

def test_gif_stop_slide_present_and_flagged(tmp_path, monkeypatch):
    monkeypatch.setenv("BIGHAT_FILES_DIR", str(tmp_path))
    render = _fresh_native_slides()
    for round_type, expected_pos in (("MC", 12), ("REG", 12), ("MISC", 12), ("MYS", 11), ("BIG", 2)):
        n = 9 if round_type == "MYS" else (1 if round_type == "BIG" else 10)
        slides = render(
            {"round_type": round_type, "questions": _make_questions(n), "name": f"{round_type}-01-A"},
            {"type": round_type, "name": f"{round_type}-01-A", "order": 1},
        )
        gif_slide = slides[expected_pos]
        assert gif_slide["metadata"].get("isGifStop") is True, (
            f"{round_type} slide at position {expected_pos} must have isGifStop=True"
        )
        assert gif_slide["metadata"]["slideIndexInRound"] == expected_pos
