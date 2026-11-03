"""v32.2.9: bingo auto-advance switch. Real routes over HTTP + real files on a tmp disk. The switch must be OFF by default, change only when the host
confirms, survive every other bingo save, and fail toward OFF on any doubt."""
import json, sys
from pathlib import Path
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("BIGHAT_NATIVE_MODE", "1")
    monkeypatch.setenv("BIGHAT_DB_DIR", str(tmp_path / "db"))
    monkeypatch.setenv("BIGHAT_BINGO_SETTINGS", str(tmp_path / "cfg" / "bingo_settings.json"))
    main = tmp_path / "Bingo"; (main / "1990s").mkdir(parents=True)
    (main / "1990s" / "songs.csv").write_text("1,Song One,Band One\n", encoding="utf-8")
    (main / "1990s" / "01_one.mp4").write_bytes(b"x" * 100)
    import importlib
    from native import db_factory
    db_factory._native_client = None
    importlib.reload(db_factory)
    from routes import bingo_setup, bingo
    importlib.reload(bingo)
    bingo.set_database(db_factory.get_db())
    app = FastAPI(); app.include_router(bingo_setup.router, prefix="/api"); app.include_router(bingo.router, prefix="/api")
    yield TestClient(app), main, tmp_path / "cfg"
    db_factory.close_all()


def get(c): return c.get("/api/bingo/auto-advance").json()
def put(c, enabled, confirmed=True): return c.post("/api/bingo/auto-advance", json={"enabled": enabled, "confirmed": confirmed})


def test_default_is_off_with_no_file(api):
    c, _, cfg = api
    assert get(c) == {"enabled": False, "changed_at": None, "confirmed": False}
    assert not (cfg / "bingo_auto_advance.json").exists()                  # reading never creates a file


def test_turning_it_on_needs_the_host_to_confirm(api):
    c, _, _ = api
    r = put(c, True, confirmed=False)
    assert r.status_code == 400 and "confirm" in r.json()["detail"] and get(c)["enabled"] is False
    assert put(c, True, confirmed=True).json()["enabled"] is True and get(c)["enabled"] is True


def test_turning_it_off_needs_no_confirmation(api):
    c, _, _ = api
    put(c, True)
    r = put(c, False, confirmed=False)
    assert r.status_code == 200 and r.json()["enabled"] is False and get(c)["enabled"] is False


@pytest.mark.parametrize("bad", ["true", "1", 1, "on", "yes", None, [], {}, 2])
def test_only_a_real_boolean_can_change_it(api, bad):
    c, _, _ = api
    r = c.post("/api/bingo/auto-advance", json={"enabled": bad, "confirmed": True})
    assert r.status_code == 400 and get(c)["enabled"] is False


@pytest.mark.parametrize("bad_confirm", ["true", 1, "yes", None])
def test_confirmation_must_be_a_real_true(api, bad_confirm):
    c, _, _ = api
    assert c.post("/api/bingo/auto-advance", json={"enabled": True, "confirmed": bad_confirm}).status_code == 400
    assert get(c)["enabled"] is False


def test_it_survives_a_restart_of_the_app(api):
    c, _, cfg = api
    put(c, True)
    import importlib; from native import bingo_auto_advance as aa
    importlib.reload(aa)                                                   # a fresh process reads the file
    assert aa.get()["enabled"] is True and json.loads((cfg / "bingo_auto_advance.json").read_text())["enabled"] is True


def test_the_setup_save_cannot_reset_it(api):
    c, main, _ = api
    put(c, True)
    for themes in ({}, {"1990s": {"enabled": True}}, {"1990s": {"enabled": False}}):
        assert c.post("/api/bingo/setup", json={"main_folder": str(main), "themes": themes}).status_code == 200
    assert get(c)["enabled"] is True


def test_playing_a_whole_game_cannot_reset_it(api):
    """create a real game, call numbers, pause/resume, start a new round, end it: the switch is untouched at every step."""
    c, main, _ = api
    c.post("/api/bingo/setup", json={"main_folder": str(main), "themes": {"1990s": {"enabled": True}}})
    put(c, True)
    steps = [("post", "/api/bingo/game/create", {"bingo_type": "traditional", "game_type": "regular", "round_type": "single", "call_interval": 20}),
             ("post", "/api/bingo/game/start", None), ("post", "/api/bingo/game/call-number", None), ("post", "/api/bingo/game/pause", None),
             ("post", "/api/bingo/game/resume", None), ("post", "/api/bingo/game/new-round", {})]
    ran = 0
    for _, path, body in steps:
        r = c.post(path, json=body) if body is not None else c.post(path)
        ran += 1 if r.status_code < 500 else 0
        assert get(c)["enabled"] is True, f"the switch changed after {path}"
    assert ran >= 5                                                          # most of the real game flow actually ran


def test_turning_it_off_is_not_undone_by_a_later_setup_save(api):
    c, main, _ = api
    put(c, True); put(c, False)
    c.post("/api/bingo/setup", json={"main_folder": str(main), "themes": {"1990s": {"enabled": True}}})
    assert get(c)["enabled"] is False


@pytest.mark.parametrize("content", ["", "   ", "not json at all", "[1, 2, 3]", "null", '{"enabled": "true", "confirmed": true}',
                                     '{"enabled": true}', '{"enabled": true, "confirmed": "yes"}', '{"enabled": 1, "confirmed": true}'])
def test_a_damaged_or_hand_edited_file_reads_as_off(api, content):
    c, _, cfg = api
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "bingo_auto_advance.json").write_text(content, encoding="utf-8")
    assert get(c)["enabled"] is False


def test_a_damaged_file_is_kept_and_does_not_block_turning_it_on(api):
    c, _, cfg = api
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "bingo_auto_advance.json").write_text("{{{ broken", encoding="utf-8")
    assert get(c)["enabled"] is False and (cfg / "bingo_auto_advance.json.bad").exists()
    assert put(c, True).json()["enabled"] is True and get(c)["enabled"] is True


def test_a_failed_save_never_claims_it_is_on(api, monkeypatch):
    c, _, _ = api
    from native import bingo_auto_advance as aa
    monkeypatch.setattr(aa.os, "replace", lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(OSError):
        aa.set_enabled(True, True)
    assert get(c)["enabled"] is False


def test_the_file_never_holds_a_half_written_state(api):
    c, _, cfg = api
    put(c, True); put(c, False); put(c, True)
    assert not list(cfg.glob("*.tmp")) and json.loads((cfg / "bingo_auto_advance.json").read_text())["enabled"] is True


def test_the_two_bingo_files_sit_together(api):
    c, main, cfg = api
    c.post("/api/bingo/setup", json={"main_folder": str(main), "themes": {"1990s": {"enabled": True}}}); put(c, True)
    assert (cfg / "bingo_settings.json").exists() and (cfg / "bingo_auto_advance.json").exists()


# ---- the host screen wiring (source checks: the screen itself can only be tried in the real app) ----
HOST = (ROOT.parent / "frontend" / "src" / "pages" / "bingo" / "HostDashboard.jsx").read_text(encoding="utf-8")


def _effect_block():
    i = HOST.index("when a RUNNING timer runs out and the switch is on")
    return HOST[i:HOST.index("const saveAutoAdvance", i)]


def test_the_effect_uses_only_names_that_exist_and_are_declared_earlier():
    block = _effect_block(); pos = HOST.index("when a RUNNING timer runs out")
    for name in ("showBingoDialog", "showWinnerVideo", "showRoundOver", "songCooldown", "availableSongNumbers", "isMusicBingo",
                 "timerExpiredRef", "callActionRef", "lastAutoFireRef", "autoAdvance", "autoAdvanceReady"):
        assert name in block, name
        decl = HOST.index(f"const [{name}") if f"const [{name}" in HOST else HOST.index(f"const {name}")
        assert decl < pos, f"{name} is used before it is declared"
    assert "numbers_remaining" not in HOST and "remaining_numbers" in block          # the real game-state field, not a guess


def test_only_a_natural_expiry_sets_the_mark_and_every_stop_clears_it():
    assert HOST.count("timerExpiredRef.current = true") == 1
    i = HOST.index("timerExpiredRef.current = true")
    assert "prev <= 1" in HOST[i - 260:i] and "setTimerRunning(false)" in HOST[i - 260:i]          # inside the 'timer ran out' branch only
    stop = HOST[HOST.index("const stopTimer"):][:220]
    assert "timerExpiredRef.current = false" in stop and "setTimerRunning(false)" in stop            # pause / bingo / end round clear it
    assert "timerExpiredRef.current = false" in HOST[HOST.index("const startTimer"):][:160]          # a fresh timer starts clean


def test_the_decision_is_outside_the_timer_updater():
    """React may call a state updater twice (StrictMode). The advance must never be inside it."""
    upd = HOST[HOST.index("setTimerValue((prev)"):][:700] if "setTimerValue((prev)" in HOST else HOST[HOST.index("setTimerValue(prev"):][:700]
    assert "callActionRef" not in upd and "callNextSong" not in upd and "callNumber" not in upd and "decideAutoAdvance" not in upd


def test_it_acts_as_next_song_or_next_number_and_never_start_round():
    assert "callActionRef.current = isMusicBingo ? callNextSong : callNumber;" in HOST
    block = _effect_block()
    assert "startGame" not in block and "newRound" not in block and "startNextRound" not in block


def test_the_switch_is_in_both_the_music_and_the_traditional_controls_and_shows_the_saved_state():
    assert HOST.count("<AutoAdvanceSwitch") == 2 and 'mode="music"' in HOST and 'mode="traditional"' in HOST
    assert "setAutoAdvance(isOn(r.data))" in HOST and "setAutoAdvance(false)" in HOST            # shows what the server saved; a failure = off
    assert "confirmed: wantOn" in HOST
    sw = (ROOT.parent / "frontend" / "src" / "pages" / "bingo" / "AutoAdvanceSwitch.jsx").read_text(encoding="utf-8")
    assert "setConfirmOpen(true)" in sw and "onSave(false)" in sw                                  # on = ask first, off = one click
