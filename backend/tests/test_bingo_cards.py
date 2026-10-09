import os, sys, random
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import pytest
from native import bingo_cards as bc

TITLES = [f"Song Number {i}" for i in range(1, 61)]

def test_clean_title_strips_quotes_notes_and_year_tags():
    assert bc.clean_title('"Careless Whisper"\u266a\u00a0(1985)') == "Careless Whisper"
    assert bc.clean_title('"Walk Like an Egyptian') == "Walk Like an Egyptian"
    assert bc.clean_title("Don\u2019t Stop Believin") == "Don't Stop Believin"
    assert bc.clean_title("  Africa  ") == "Africa"
    assert bc.clean_title("(Just Like) Starting Over") == "(Just Like) Starting Over"   # real parentheses stay
    assert bc.clean_title(None) == ""

def test_unique_titles_dedupes_ignoring_case_and_junk():
    songs = [{"title": '"Whip It"'}, {"title": "whip it"}, {"title": "Africa"}, {"title": ""}, {"title": "=SUM(A1)"}]
    assert bc.unique_titles(songs) == ["Whip It", "Africa"]

def test_every_card_has_free_centre_and_24_different_theme_songs():
    cards = bc.make_cards(TITLES, 50, random.Random(3))
    for g in cards:
        assert g[2][2] is None
        flat = [x for r in g for x in r if x]
        assert len(flat) == 24 and len(set(flat)) == 24 and set(flat) <= set(TITLES)

def test_no_two_cards_are_the_same():
    cards = bc.make_cards(TITLES, 100, random.Random(5))
    assert len({tuple(map(tuple, c)) for c in cards}) == 100

def test_theme_with_exactly_24_songs_works_and_23_is_refused():
    assert len(bc.make_cards(TITLES[:24], 3, random.Random(1))) == 3
    with pytest.raises(ValueError, match="need_24_songs"):
        bc.make_cards(TITLES[:23], 1)
    with pytest.raises(ValueError):
        bc.generate_pdf([{"title": t} for t in TITLES[:23]], 4)

def test_count_is_rounded_to_full_pages_and_capped():
    songs = [{"title": t} for t in TITLES]
    assert bc.generate_pdf(songs, 1)["cards"] == 4
    assert bc.generate_pdf(songs, 5)["cards"] == 8
    assert bc.generate_pdf(songs, 10**6)["cards"] == 200

def test_real_long_titles_never_break_inside_a_word():
    for t in ["Everybody Wants to Rule the World", "I Wanna Dance with Somebody (Who Loves Me)", "Karma Chameleon", "Ghostbusters",
              "Total Eclipse of the Heart", "Don't You (Forget About Me)", "Walk Like an Egyptian", "Girls Just Want to Have Fun"]:
        size, lines = bc.fit_title(t)
        assert " ".join(lines) == t and size >= 8, (t, size, lines)

def test_an_impossible_word_is_shrunk_then_cut_never_overflowing_the_square():
    size, lines = bc.fit_title("Supercalifragilisticexpialidocious Anthem")
    assert size == 4.5 and all(bc._text_width(l, size) <= bc.CELL_W - 3 + 0.01 for l in lines)

def test_pdf_is_valid_and_has_one_page_per_four_cards():
    import pymupdf
    out = bc.generate_pdf([{"title": t} for t in TITLES], 12)
    doc = pymupdf.open(stream=out["pdf"], filetype="pdf")
    assert out["pages"] == 3 and len(doc) == 3 and doc[0].rect.width == 612 and doc[0].rect.height == 792

def test_special_characters_in_titles_survive_into_the_pdf():
    import pymupdf
    songs = [{"title": t} for t in TITLES[:23]] + [{"title": "Mr. Brightside (Live) \\ Caf\u00e9 & Co"}]
    doc = pymupdf.open(stream=bc.generate_pdf(songs, 4)["pdf"], filetype="pdf")
    assert "Caf" in " ".join(p.get_text() for p in doc)


def _header_pdf(name, n=4):
    import pymupdf
    out = bc.generate_pdf([{"title": t} for t in TITLES], n, name)
    return pymupdf.open(stream=out["pdf"], filetype="pdf")

def test_theme_name_is_printed_centred_above_bingo_on_every_card():
    doc = _header_pdf("1980s")
    page = doc[0]
    hits = [w for w in page.get_text("words") if w[4] == "1980s"]
    assert len(hits) == 4                                   # one per card
    for w in hits:
        card_left = bc.CARD_X[0] if w[0] < 306 else bc.CARD_X[1]
        centre = (w[0] + w[2]) / 2
        assert abs(centre - (card_left + bc.CARD_W / 2)) < 1.0
        assert w[3] < bc.CARD_TOP[0 if w[1] < 400 else 1] + bc.HEADER_H * 0.45     # in the top part of the header

def test_theme_name_uses_the_same_font_and_size_as_song_titles():
    page = _header_pdf("Pop Punk & Emo")[0]
    spans = [sp for b in page.get_text("dict")["blocks"] if b.get("lines") for l in b["lines"] for sp in l["spans"]]
    name = [sp for sp in spans if sp["text"].strip() == "Pop Punk & Emo"]
    song = [sp for sp in spans if sp["text"].startswith("Song")]
    assert name and song and name[0]["font"] == song[0]["font"]
    assert abs(name[0]["size"] - 10.5) < 0.01 and any(abs(x["size"] - 10.5) < 0.01 for x in song)

def test_bingo_header_is_five_vector_letters_per_card_in_lemonada():
    page = _header_pdf("1980s")[0]
    black_fills = [d for d in page.get_drawings() if d.get("fill") == (0.0, 0.0, 0.0) and d["rect"].height > 12 and d["rect"].width < 30]
    assert len(black_fills) == 20                           # B, I, N, G, O on each of 4 cards
    assert set(bc._LEMONADA_BINGO) == set("BINGO")

def test_theme_name_keeps_years_and_long_names_fit_the_card():
    assert bc.clean_theme_name("Party (2024)") == "Party (2024)"
    long_name = "90s Hip-Hop & R&B Throwback Party Night Extravaganza Edition Two"
    size, lines = bc.fit_title(bc.clean_theme_name(long_name), max_w=bc.CARD_W - 16, max_h=14)
    assert all(bc._text_width(l, size) <= bc.CARD_W - 16 + 0.01 for l in lines)

def test_empty_theme_name_prints_no_name_line():
    page = _header_pdf("")[0]
    assert "1980s" not in page.get_text()


# ---------------- alpha.110: Loteria
def _pics(tmp_path, n, ext="png", start=1):
    from PIL import Image
    d = tmp_path / "Cards"; d.mkdir(exist_ok=True)
    for i in range(start, start + n):
        Image.new("RGB", (60 + i, 90), ((i * 40) % 255, (i * 70) % 255, 90)).save(d / ("%02d.%s" % (i, ext)))
    return d

def test_is_loteria_detects_the_word_in_any_round_name():
    for t in ("Loteria", "Bad Bunny Loteria", "LOTERIA 2024", "lotería navide\u00f1a", "Pokemon Loteria"):
        assert bc.is_loteria(t), t
    for t in ("1980s", "Pop Punk & Emo", "", None):
        assert not bc.is_loteria(t), t

def test_loteria_type_is_the_name_without_the_word_loteria():
    assert bc.loteria_type("Loteria") == ""
    assert bc.loteria_type("Bad Bunny Loteria") == "Bad Bunny"
    assert bc.loteria_type("Loteria - Pokemon") == "Pokemon"
    assert bc.loteria_type("Lotería Navide\u00f1a") == "Navide\u00f1a"
    assert bc.loteria_type("LOTERIA") == ""

def test_loteria_images_sorted_by_number_and_skip_non_pictures(tmp_path):
    d = tmp_path / "Cards"; d.mkdir()
    for n in ("10.png", "2.png", "01.png", "b.png", "A.png", "3_x.jpg", "100.png", "notes.txt", ".hidden.png", "~tmp.png"):
        (d / n).write_bytes(b"x")
    names = [os.path.basename(p) for p in bc.loteria_images(d)]
    assert names == ["01.png", "2.png", "3_x.jpg", "10.png", "100.png", "A.png", "b.png"]     # numbers first, in number order; then names
    assert bc.loteria_images(tmp_path / "nope") == [] and bc.loteria_images(None) == []

def test_loteria_card_is_4x4_of_16_different_pictures_no_free_space(tmp_path):
    imgs = bc.loteria_images(_pics(tmp_path, 30))
    cards = bc.make_loteria_cards(imgs, 40, random.Random(2))
    assert len(cards) == 40
    for g in cards:
        assert len(g) == 4 and all(len(r) == 4 for r in g)
        flat = [x for r in g for x in r]
        assert len(flat) == 16 and len(set(flat)) == 16 and set(flat) <= set(imgs) and None not in flat
    assert len({tuple(map(tuple, g)) for g in cards}) == 40

def test_loteria_needs_16_pictures(tmp_path):
    imgs = bc.loteria_images(_pics(tmp_path, 15))
    with pytest.raises(ValueError, match="need_16_pictures"):
        bc.make_loteria_cards(imgs, 1)
    with pytest.raises(ValueError, match="need_16_pictures"):
        bc.generate_loteria_pdf(tmp_path / "Cards", 4, "Loteria")
    assert len(bc.make_loteria_cards(bc.loteria_images(_pics(tmp_path, 1, start=16)), 2)) == 2          # exactly 16 works

def test_broken_pictures_are_skipped_not_fatal(tmp_path):
    d = _pics(tmp_path, 16)
    (d / "99.png").write_bytes(b"this is not an image")
    out = bc.generate_loteria_pdf(d, 4, "Loteria", random.Random(1))
    assert out["songs_used"] == 16 and out["cards"] == 4
    (d / "01.png").write_bytes(b"now this one is broken too")                       # only 15 good pictures left
    with pytest.raises(ValueError):
        bc.generate_loteria_pdf(d, 4, "Loteria")

def test_loteria_pdf_stores_each_picture_once_and_handles_odd_formats(tmp_path):
    import pymupdf
    from PIL import Image
    d = _pics(tmp_path, 16)
    Image.new("RGBA", (50, 50), (200, 0, 0, 0)).save(d / "17.png")                    # fully transparent PNG
    Image.new("RGB", (400, 100), "blue").save(d / "18.webp")                          # wide, webp
    Image.new("L", (30, 90), 128).save(d / "19.jpg")                                  # greyscale jpg
    out = bc.generate_loteria_pdf(d, 40, "Bad Bunny Loteria", random.Random(3))
    doc = pymupdf.open(stream=out["pdf"], filetype="pdf")
    assert len(doc) == 20 and out["songs_used"] == 19                                  # 40 cards, 2 per page
    xrefs = {im[0] for p in doc for im in p.get_images()}
    assert len(xrefs) <= 19                                                           # one stored copy per picture, not per use
    assert len(out["pdf"]) < 400_000


def test_loteria_pages_are_landscape_with_two_cards_and_a_dashed_line_down_the_middle(tmp_path):
    import pymupdf
    d = _pics(tmp_path, 20, ext="jpg")
    out = bc.generate_loteria_pdf(d, 5, "Bad Bunny Loteria", random.Random(1))
    assert out["cards"] == 6 and out["pages"] == 3                                     # 5 rounds up to 6: 2 cards on every page
    doc = pymupdf.open(stream=out["pdf"], filetype="pdf")
    for page in doc:
        assert page.rect.width == 792 and page.rect.height == 612                      # US Letter, landscape
        assert len(page.get_image_info()) == 2 * 16                                    # 2 cards x 16 pictures
        dashed = [x for x in page.get_drawings() if x.get("dashes") and x["dashes"].replace(" ", "").startswith("[43]")]
        assert len(dashed) == 1, "expected exactly one dashed cut line"
        r = dashed[0]["rect"]
        assert r.x0 == r.x1 == 396.0                                                   # exactly the middle of the page
        assert r.y0 <= 10 and r.y1 >= page.rect.height - 10                            # runs the whole height, so the cut is easy to follow
        boxes = sorted((i["bbox"][0], i["bbox"][2]) for i in page.get_image_info())
        left = [b for b in boxes if b[1] <= 396]; right = [b for b in boxes if b[0] >= 396]
        assert len(left) == 16 and len(right) == 16                                    # one card each side, nothing crosses the line

def test_portrait_jpgs_fill_their_squares(tmp_path):
    import pymupdf
    from PIL import Image
    d = tmp_path / "Cards"; d.mkdir()
    for i in range(1, 17):
        Image.new("RGB", (430, 610), (i * 10, 120, 200)).save(d / ("%d.jpg" % i))
    page = pymupdf.open(stream=bc.generate_loteria_pdf(d, 2, "Loteria", random.Random(1))["pdf"], filetype="pdf")[0]
    for info in page.get_image_info():
        w, h = info["bbox"][2] - info["bbox"][0], info["bbox"][3] - info["bbox"][1]
        assert w > 80 and h > 115 and w < bc.LOTERIA_CELL_W and h < bc.LOTERIA_CELL_H      # almost the full 90 x 128 square

def test_word_cards_are_still_portrait_four_per_page():
    doc = _header_pdf("1980s", 8)
    assert len(doc) == 2 and doc[0].rect.width == 612 and doc[0].rect.height == 792
