import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

ROOT_DIR = None


def _write_csv(path, rows, header=None):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if header:
            w.writerow(header)
        w.writerows(rows)


@pytest.fixture(autouse=True)
def bingo_folder(tmp_path, monkeypatch):
    """A fake 'Bingo folder on the user's PC' built fresh for every test."""
    root = tmp_path / "bingo_pc"
    for name in ("1980s", "Emo", "Tiny Theme", "No List", "Hidden 90s", "Loteria", "Bad Bunny Loteria", "Empty Loteria", "Small Loteria"):
        (root / name).mkdir(parents=True)
    titles = [f"Eighties Hit {i}" for i in range(1, 76)]
    _write_csv(root / "1980s" / "80s.csv", [[i, t, "Various"] for i, t in enumerate(titles, 1)], header=["Number", "Song", "Artist"])
    (root / "1980s" / "01_Song.mp4").write_bytes(b"x")
    _write_csv(root / "Emo" / "emo.csv", [[i, f"Emo Song {i}", f"Band {i % 7}"] for i in range(1, 41)])   # no header, no videos
    _write_csv(root / "Tiny Theme" / "t.csv", [[i, f"Tiny {i}", ""] for i in range(1, 11)])
    (root / "No List" / "01_x.mp4").write_bytes(b"x")
    _write_csv(root / "Hidden 90s" / "n.csv", [[i, f"Ninety {i}", ""] for i in range(1, 31)])
    from PIL import Image
    for theme, n in (("Loteria", 20), ("Bad Bunny Loteria", 30), ("Small Loteria", 10)):
        _write_csv(root / theme / ("Bingo List (%s).csv" % theme), [[i, "Card %d" % i, ""] for i in range(1, n + 1)])
        (root / theme / "Cards").mkdir()
        for i in range(1, n + 1):
            Image.new("RGB", (80 + i, 120), ((i * 37) % 255, (i * 91) % 255, (i * 13) % 255)).save(root / theme / "Cards" / ("%02d.png" % i))
    _write_csv(root / "Empty Loteria" / "Bingo List (Empty Loteria).csv", [[i, "Card %d" % i, ""] for i in range(1, 61)])
    (root / "Empty Loteria" / "Cards").mkdir()                       # like the screenshot: a Cards folder with 0 items
    settings = tmp_path / "bingo_settings.json"
    settings.write_text(json.dumps({"main_folder": str(root), "themes": {"Hidden 90s": {"enabled": False}}}))
    monkeypatch.setenv("BIGHAT_BINGO_SETTINGS", str(settings))
    global ROOT_DIR
    ROOT_DIR = str(root)


@pytest.fixture()
def c():
    from routes import bingo_setup as r
    api = APIRouter(prefix="/api")
    api.include_router(r.router)
    app = FastAPI()
    app.include_router(api)
    return TestClient(app)


def test_themes_list_only_enabled_with_a_song_list(c):
    d = c.get("/api/bingo/cards/themes").json()
    names = {t["id"]: t for t in d["themes"]}
    assert set(names) == {"1980s", "Emo", "Tiny Theme", "Loteria", "Bad Bunny Loteria", "Empty Loteria", "Small Loteria"}, names.keys()     # no 'No List', no switched-off 'Hidden 90s'
    assert names["1980s"]["songs"] == 75 and names["1980s"]["usable"]
    assert names["Emo"]["songs"] == 40 and names["Emo"]["usable"] and names["Emo"]["videos"] == 0   # cards do not need videos
    assert names["Tiny Theme"]["songs"] == 10 and not names["Tiny Theme"]["usable"]
    assert d["folder"] == ROOT_DIR and d["min_songs"] == 24

def test_generate_builds_pdf_from_that_theme_only(c):
    res = c.post("/api/bingo/cards/generate", json={"theme": "Emo", "count": 12})
    assert res.status_code == 200 and res.headers["content-type"] == "application/pdf"
    assert res.content[:5] == b"%PDF-" and res.headers["x-cards"] == "12" and res.headers["x-pages"] == "3"
    import pymupdf
    doc = pymupdf.open(stream=res.content, filetype="pdf"); assert len(doc) == 3
    text = " ".join(p.get_text() for p in doc)
    assert "Emo Song" in text and "Ninety" not in text and "Tiny" not in text      # only the chosen theme's songs

def test_count_rounds_up_to_full_page_and_is_capped(c):
    assert c.post("/api/bingo/cards/generate", json={"theme": "Emo", "count": 5}).headers["x-cards"] == "8"
    assert c.post("/api/bingo/cards/generate", json={"theme": "Emo", "count": 99999}).headers["x-cards"] == "200"

def test_refuses_bad_themes(c):
    assert c.post("/api/bingo/cards/generate", json={"theme": "Tiny Theme", "count": 8}).status_code == 422   # fewer than 24 songs
    assert c.post("/api/bingo/cards/generate", json={"theme": "Hidden 90s", "count": 8}).status_code == 404  # switched off
    assert c.post("/api/bingo/cards/generate", json={"theme": "No List", "count": 8}).status_code == 404
    assert c.post("/api/bingo/cards/generate", json={"theme": "../etc", "count": 8}).status_code == 404

def test_free_space_in_centre_of_every_card(c):
    import pymupdf
    res = c.post("/api/bingo/cards/generate", json={"theme": "1980s", "count": 4})
    doc = pymupdf.open(stream=res.content, filetype="pdf"); p = doc[0]
    yellow = [d["rect"] for d in p.get_drawings() if d.get("fill") and tuple(round(x) for x in d["fill"]) == (1, 1, 0)]
    assert len(yellow) == 4, len(yellow)       # one free square per card, four cards on the page


def test_loteria_themes_count_pictures_not_songs(c):
    names = {t["id"]: t for t in c.get("/api/bingo/cards/themes").json()["themes"]}
    assert names["Loteria"]["kind"] == "loteria" and names["Loteria"]["songs"] == 20 and names["Loteria"]["usable"]
    assert names["Bad Bunny Loteria"]["songs"] == 30 and names["Bad Bunny Loteria"]["usable"]
    assert names["Empty Loteria"]["songs"] == 0 and not names["Empty Loteria"]["usable"]       # empty Cards folder
    assert names["Small Loteria"]["songs"] == 10 and not names["Small Loteria"]["usable"]      # fewer than 16 pictures
    assert names["1980s"]["kind"] == "words" and names["1980s"]["need"] == 24 and names["Loteria"]["need"] == 16

def test_loteria_generate_makes_4x4_picture_cards_with_loteria_title(c):
    import pymupdf
    res = c.post("/api/bingo/cards/generate", json={"theme": "Bad Bunny Loteria", "count": 8})
    assert res.status_code == 200 and res.headers["x-cards"] == "8" and res.headers["x-pages"] == "4"      # 2 cards per landscape page
    doc = pymupdf.open(stream=res.content, filetype="pdf")
    page = doc[0]
    assert len([w for w in page.get_text("words") if w[4] == "Bad"]) == 2            # the type, once per card
    assert "Bunny" in page.get_text() and "Loteria" not in page.get_text()           # the word Loteria is the big letters, not text
    assert len(page.get_images()) >= 1
    placed = [i for i in page.get_image_info()]
    assert len(placed) == 2 * 16 and page.rect.width > page.rect.height              # 2 cards x 16 pictures on a landscape page, no free space

def test_plain_loteria_has_no_type_line(c):
    import pymupdf
    res = c.post("/api/bingo/cards/generate", json={"theme": "Loteria", "count": 4})
    assert res.status_code == 200
    assert pymupdf.open(stream=res.content, filetype="pdf")[0].get_text().strip() == ""    # no words at all

def test_loteria_refusals(c):
    assert c.post("/api/bingo/cards/generate", json={"theme": "Small Loteria", "count": 4}).status_code == 422
    assert c.post("/api/bingo/cards/generate", json={"theme": "Empty Loteria", "count": 4}).status_code == 422

def test_word_themes_are_not_affected_by_loteria(c):
    import pymupdf
    res = c.post("/api/bingo/cards/generate", json={"theme": "Emo", "count": 4})
    assert res.status_code == 200 and "Emo Song" in pymupdf.open(stream=res.content, filetype="pdf")[0].get_text()
