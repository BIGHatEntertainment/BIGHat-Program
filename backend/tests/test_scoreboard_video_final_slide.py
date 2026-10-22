"""v32.1.10: the scoreboard MP4 is drawn like the Trivia Player's FINAL SCORES slide. Old output: 14-56 px text on a 1080/1920 canvas, a
Linux-only font path (tiny default font on Windows), the top 10 teams as a still picture, a grid that scrolled once every 6 s."""
import asyncio, os, subprocess, sys
from pathlib import Path
import numpy as np
import pytest
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from native import scoreboard_video as sv

ROUNDS = [{"label": l, "multiplier": m} for l, m in [("MC", 1), ("REG", 1), ("BIG", 1), ("MISC", 1), ("MYS", 2), ("BIG", 3)]]


def teams(n, long_name=False):
    return [{"name": ("A very long team name that must never run over the score " * 2 if long_name and i == 0 else f"Team {i + 1}"),
             "total": 90 - i, "roundScores": [6, 7, 8, 9, 14, 3 + i]} for i in range(n)]


def test_a_real_font_is_found_for_every_role_even_without_system_fonts(monkeypatch):
    monkeypatch.setattr(sv, "_BOLD_CANDIDATES", ["/nope/a.ttf"]); monkeypatch.setattr(sv, "_MONO_CANDIDATES", ["/nope/b.ttf"])
    f = sv.font_files()
    assert f["title"].endswith("Lemonada-Bold.ttf") and f["bold"].endswith("Lemonada-Bold.ttf") and f["mono"].endswith("Lemonada-Bold.ttf")
    assert sv.Fonts().get("bold", 40).size == 40                       # a real TrueType font, never Pillow's tiny default


def test_windows_fonts_are_tried_first():
    assert sv._BOLD_CANDIDATES[0].lower().startswith("c:") and "segoeuib" in sv._BOLD_CANDIDATES[0].lower()


OLD = {"title": 56, "name": 26, "score": 40, "chip": 14}               # the pixel sizes the v32.1.9 renderer used


@pytest.mark.parametrize("W,H", [(1080, 1920), (1920, 1080)])
def test_text_is_much_larger_than_the_old_output(W, H):
    L = sv.Layout(W, H)
    assert L.f_title >= OLD["title"] * 1.2 and L.f_name >= OLD["name"] * 1.5 and L.f_total >= OLD["score"] * 1.5
    assert L.f_rlabel >= OLD["chip"] * 1.5 and L.f_rval >= OLD["chip"] * 2


def test_text_scales_with_the_canvas_height_like_the_slides_vh_units():
    a, b = sv.Layout(1920, 1080), sv.Layout(3840, 2160)
    assert abs(b.f_name / a.f_name - 2) < 0.05 and abs(b.f_total / a.f_total - 2) < 0.05


@pytest.mark.parametrize("n", [3, 5, 12, 40])
def test_every_team_is_in_the_strip(n):
    sc = sv.build_scene(1080, 1920, teams(n), "Cornish Pasty Co. (Glendale)", "10/20/2026", ROUNDS)
    assert sc["teams"] == n
    per_box = sc["strip"].height / n
    assert per_box > 150                                               # each team has a real box, not a thin row


@pytest.mark.parametrize("n_rounds", [5, 6, 8, 10])
@pytest.mark.parametrize("W", [1080, 1920])
def test_every_round_chip_fits_inside_its_box_and_none_is_dropped(n_rounds, W):
    """Count the chips actually drawn (dark navy plates) and make sure the last one ends inside the box."""
    H = 1920 if W == 1080 else 1080
    L = sv.Layout(W, H)
    width = W - 2 * L.pad_x
    box = sv._team_box(L, sv.Fonts(), {"name": "X", "total": 99, "roundScores": list(range(1, n_rounds + 1))}, 5, [{"label": f"R{i + 1}"} for i in range(n_rounds)], width)
    a = np.asarray(box)
    y = int(box.height - L.box_pad_y - (int(L.f_rval * 1.9) + int(L.vh)) // 2)           # the middle of the chip row
    row = a[y, :, :]
    plate = (row[:, 0] < 10) & (row[:, 1] < 10) & (row[:, 2] < 45) & (row[:, 3] > 150)
    runs, prev = 0, False
    for v in plate:
        runs += (v and not prev)
        prev = v
    # each chip is one dark plate that the text interrupts; count plates by gaps in the box background instead
    xs = np.where(plate)[0]
    assert xs.size, "no chip plates were drawn"
    assert xs.max() <= width - L.box_pad_x + 2, "a chip runs past the edge of its box"
    # the number of distinct plates equals the number of rounds (plates are separated by the gap between chips)
    gaps = np.where(np.diff(xs) > max(3, int(L.vh * 0.45)))[0]
    assert len(gaps) + 1 >= n_rounds, f"only {len(gaps) + 1} of {n_rounds} chips are drawn"


def test_the_fonts_class_draws_with_the_chosen_font_file_not_pillows_default(monkeypatch):
    monkeypatch.setattr(sv, "_BOLD_CANDIDATES", ["/nope"]); monkeypatch.setattr(sv, "_MONO_CANDIDATES", ["/nope"])
    fonts = sv.Fonts()
    f = fonts.get("bold", 40)
    assert isinstance(f, sv.ImageFont.FreeTypeFont) and f.size == 40
    assert os.path.basename(f.path) == "Lemonada-Bold.ttf"             # the bundled font, exactly
    d = ImageDraw.Draw(Image.new("RGB", (400, 100)))
    assert d.textlength("Second Place", font=f) > 150                  # Pillow's default bitmap font is ~70 px wide for this text at any size


def test_a_long_team_name_is_shrunk_or_cut_and_never_overlaps_the_score():
    L = sv.Layout(1080, 1920)
    fonts = sv.Fonts()
    d = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    txt, f = sv._fit(d, "A very long team name that must never run over the score " * 2, fonts.get, "bold", L.f_name, 500)
    assert d.textlength(txt, font=f) <= 500 and txt.endswith("...")
    short, f2 = sv._fit(d, "Short", fonts.get, "bold", L.f_name, 500)
    assert short == "Short" and f2.size == L.f_name


def test_scroll_rules_match_the_slide():
    assert [sv.scroll_seconds(n) for n in (1, 4, 12, 40, 100)] == [20, 20, 60, 150, 150]
    assert sv.video_seconds(5) == 12 and sv.video_seconds(12) == 36 and sv.video_seconds(200) == 60


def test_the_video_holds_scrolls_and_holds():
    sc = sv.build_scene(1080, 1920, teams(12), "Venue", "d", ROUNDS)
    f = lambda t: np.asarray(sv.frame_at(sc, t, 36))                    # noqa: E731
    assert (f(0) == f(1.5)).all()                                      # podium readable at the start
    assert not (f(10) == f(14)).all()                                  # it really moves
    assert (f(34) == f(35.99)).all()                                   # the last team rests at the bottom
    assert (f(9) != f(9.2)).any()                                      # smooth: consecutive frames differ


def test_a_short_night_does_not_scroll():
    sc = sv.build_scene(1080, 1920, teams(4), "Venue", "d", ROUNDS)
    assert (np.asarray(sv.frame_at(sc, 0, 12)) == np.asarray(sv.frame_at(sc, 11, 12))).all()


def test_the_grid_holds_still_and_the_boxes_cover_it():
    sc = sv.build_scene(1080, 1920, teams(12), "Venue", "d", ROUNDS)
    back = np.asarray(sc["back"])
    assert back.shape == (1920, 1080, 3)
    assert (np.asarray(sv.frame_at(sc, 0, 36))[1500:1900, :, :] != 0).any()


def test_encode_makes_a_real_mp4(tmp_path):
    from native.media_tools import ffmpeg_path
    out = str(tmp_path / "x.mp4")
    ok, err = sv.encode_mp4(out, 540, 960, teams(4), "Venue", "10/20/2026", ROUNDS, 2, 10, ffmpeg_path())
    assert ok, err
    info = subprocess.run([ffmpeg_path(), "-i", out], capture_output=True, text=True).stderr
    assert "h264" in info and "540x960" in info and "Duration: 00:00:02" in info


def test_a_missing_ffmpeg_is_reported_not_swallowed(tmp_path):
    with pytest.raises((FileNotFoundError, OSError)):
        sv.encode_mp4(str(tmp_path / "x.mp4"), 200, 200, teams(2), "V", "d", [], 1, 5, "ffmpeg-does-not-exist-xyz")


def test_the_route_returns_size_and_teams_and_refuses_an_empty_night(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path)); monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("BIGHAT_DATA_ROOT", str(tmp_path / "appdata"))
    monkeypatch.setenv("BIGHAT_FILES_DIR", str(tmp_path / "Documents" / "BIG Hat Entertainment" / "Files"))
    for n in list(sys.modules):
        if n.startswith("native.data_map") or n == "routes.scoreboard":
            sys.modules.pop(n, None)
    from routes import scoreboard as sb
    from fastapi import HTTPException
    loop = asyncio.new_event_loop()
    with pytest.raises(HTTPException) as e:
        loop.run_until_complete(sb.generate_scoreboard_video(sb.ScoreboardVideoRequest(teams=[], aspectRatio="portrait")))
    assert e.value.status_code == 400
    r = loop.run_until_complete(sb.generate_scoreboard_video(sb.ScoreboardVideoRequest(teams=teams(3), location="V", date="d", rounds=ROUNDS, aspectRatio="portrait", duration=8)))
    assert (r["width"], r["height"], r["teams"]) == (1080, 1920, 3) and r["size"] > 10_000 and (sb.EXPORTS_DIR / r["file_id"]).is_file()
    r2 = loop.run_until_complete(sb.generate_scoreboard_video(sb.ScoreboardVideoRequest(teams=teams(3), location="V", date="d", rounds=ROUNDS, aspectRatio="landscape", duration=8)))
    assert (r2["width"], r2["height"]) == (1920, 1080)
