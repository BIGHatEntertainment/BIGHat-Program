"""alpha.67: the Bingo library - one main folder, one sub folder per theme."""
import json, sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from native import bingo_library as bl


@pytest.fixture
def lib(tmp_path, monkeypatch):
    monkeypatch.setenv("BIGHAT_BINGO_SETTINGS", str(tmp_path / "cfg" / "bingo_settings.json"))
    main = tmp_path / "Bingo"
    (main / "1980s").mkdir(parents=True)
    (main / "Emo").mkdir()
    (main / "Broken").mkdir()
    (main / "Empty Videos").mkdir()
    (main / "_ignored").mkdir()
    # 1980s: Excel, no header row
    import pandas as pd
    pd.DataFrame([[1, "Sweet Child O' Mine", "Guns N' Roses"], [2, "Like a Virgin", "Madonna"],
                  [3, "Take On Me", "a-ha"]]).to_excel(main / "1980s" / "Bingo List.xlsx", header=False, index=False)
    for n, name in ((1, "01_Sweet Child.mp4"), (2, "02 - Virgin.mp4"), (3, "3_take on me.MOV")):
        (main / "1980s" / name).write_bytes(b"0" * 50)
    # Emo: CSV WITH a header row, columns in a different order, semicolon-free but quoted comma
    (main / "Emo" / "list.csv").write_text(
        'Artist,Song Title,Number\nMy Chemical Romance,"Welcome to the Black Parade",10\nParamore,"Misery Business",11\n',
        encoding="utf-8")
    (main / "Emo" / "10_welcome.mp4").write_bytes(b"1" * 20)      # 11 has NO video
    # Broken: videos but no list
    (main / "Broken" / "01_x.mp4").write_bytes(b"2")
    # Empty Videos: list but no videos
    (main / "Empty Videos" / "s.csv").write_text("1,A,B\n", encoding="utf-8")
    (main / "_ignored" / "s.csv").write_text("1,A,B\n", encoding="utf-8")
    bl.save_settings(str(main), {})
    return main


def test_scan_finds_each_theme_and_its_problems(lib):
    res = bl.scan(str(lib))
    assert res["ok"]
    by = {t["id"]: t for t in res["themes"]}
    assert set(by) == {"1980s", "Emo", "Broken", "Empty Videos"}          # "_ignored" skipped
    assert by["1980s"]["ready"] and by["1980s"]["videos"] == 3 and by["1980s"]["song_list"] == "Bingo List.xlsx"
    assert by["Emo"]["ready"] and by["Emo"]["videos"] == 1
    assert not by["Broken"]["ready"] and "no song list" in by["Broken"]["problems"][0]
    assert not by["Empty Videos"]["ready"] and "no videos" in by["Empty Videos"]["problems"][0]


def test_scan_bad_folders():
    assert bl.scan("")["error"] == "no_folder"
    assert bl.scan("/definitely/not/here")["error"] == "folder_not_found"


def test_songs_from_excel_without_header(lib):
    r = bl.theme_songs("1980s")
    assert [(s["number"], s["title"], s["artist"]) for s in r["songs"]] == [
        (1, "Sweet Child O' Mine", "Guns N' Roses"), (2, "Like a Virgin", "Madonna"), (3, "Take On Me", "a-ha")]
    assert all(s["has_video"] for s in r["songs"]) and r["missing_videos"] == []


def test_songs_from_csv_with_header_in_any_column_order(lib):
    r = bl.theme_songs("Emo")
    assert [(s["number"], s["title"], s["artist"]) for s in r["songs"]] == [
        (10, "Welcome to the Black Parade", "My Chemical Romance"), (11, "Misery Business", "Paramore")]
    assert r["songs"][0]["has_video"] and not r["songs"][1]["has_video"]
    assert r["missing_videos"] == [11]


def test_video_lookup_by_leading_number(lib):
    assert bl.video_path("1980s", 1).name == "01_Sweet Child.mp4"
    assert bl.video_path("1980s", 2).name == "02 - Virgin.mp4"
    assert bl.video_path("1980s", 3).name == "3_take on me.MOV"
    assert bl.video_path("1980s", 99) is None
    assert bl.video_path("Emo", 11) is None


def test_cannot_escape_the_main_folder(lib):
    for bad in ("..", "../", "..\\", "1980s/../Emo", "/etc", "C:\\Windows", "", ".", "nope"):
        assert bl.theme_folder(bad) is None, bad
        assert bl.video_path(bad, 1) is None, bad


def test_available_themes_need_ready_and_switched_on(lib):
    assert {t["id"] for t in bl.available_themes()} == {"1980s", "Emo"}      # ready ones only
    bl.save_settings(str(lib), {"Emo": {"enabled": False}})
    assert {t["id"] for t in bl.available_themes()} == {"1980s"}
    bl.save_settings(str(lib), {"Emo": {"enabled": True}, "1980s": {"enabled": False}})
    assert {t["id"] for t in bl.available_themes()} == {"Emo"}


def test_settings_survive_reload_and_are_plain_json(lib):
    bl.save_settings(str(lib), {"Emo": {"enabled": False}})
    data = json.loads(bl.settings_path().read_text())
    assert data["main_folder"] == str(lib) and data["themes"]["Emo"]["enabled"] is False
    assert bl.load_settings()["themes"]["Emo"]["enabled"] is False
    bl.settings_path().write_text("{ not json")
    assert bl.load_settings() == {"main_folder": "", "themes": {}}           # corrupt file is not fatal


def test_csv_edge_cases(tmp_path):
    p = tmp_path / "s.csv"
    p.write_bytes("1;Café del Mar;Energy 52\n2;Song;\n2;Duplicate;X\nabc;Not a number;Y\n3;;NoTitle\n".encode("cp1252"))
    got = bl.parse_song_list(p)
    assert [(s["number"], s["title"], s["artist"]) for s in got] == [(1, "Café del Mar", "Energy 52"), (2, "Song", "")]
