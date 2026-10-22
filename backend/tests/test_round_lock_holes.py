"""v32.1.7: the 180-day lock had two holes. (1) The Wizard/Roulette round lists were sent the location's image URL or
"location:<id>", which matched nothing, so used rounds were never hidden. (2) A refused build could be overridden through the
"legacy (unchecked)" path, which had no lock check and recorded no usage. Plus: a damaged usage file must never read as empty."""
import asyncio, json, os, sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
LID = "244b99b2-9006-4a1f-8fd8-06f1df2be2aa"
LNAME = "Cornish Pasty Co. (Glendale)"
FILES = [{"order": 1, "type": "MC", "file": "Files/Trivia/MC/mc-01-a.bighat"},
         {"order": 6, "type": "BIG", "file": "Files/Trivia/BIG/big-most-abundant-elements.bighat"}]


@pytest.fixture
def ru(tmp_path, monkeypatch):
    monkeypatch.setenv("BIGHAT_FILES_DIR", str(tmp_path))
    monkeypatch.setenv("BIGHAT_DATA_ROOT", str(tmp_path / "appdata"))
    for n in list(sys.modules):
        if n in ("round_usage", "native_slides") or n.startswith("native.data_map"):
            sys.modules.pop(n, None)
    import round_usage
    round_usage.backfill_from_presentations = lambda: 0
    round_usage.record_usage(location_id=LID, location_name=LNAME, round_files=FILES, used_by="Nick",
                             presentation_id="abb68cc6", presentation_name="Cornish 10/20")
    return round_usage


@pytest.mark.parametrize("sent", [
    LNAME, LID, f"location:{LID}",
    f"/api/native/locations/{LID}/images/img123/raw",
    f"http://127.0.0.1:8001/api/native/locations/{LID}/images/img123/raw",
])
def test_every_form_of_the_location_the_app_sends_finds_the_locked_rounds(ru, sent):
    assert {"mc-01-a", "big-most-abundant-elements"} <= ru.locked_names(sent)


def test_other_location_is_still_free(ru):
    assert ru.locked_names("location:some-other-id") == set()
    assert ru.locked_names("/api/native/locations/other/images/x/raw") == set()


def test_released_rounds_are_free_again(ru):
    rid = ru.list_records()[0]["id"]
    ru.release(rid)
    assert len(ru.locked_names(f"location:{LID}")) == 1


def test_expired_rounds_are_free(ru):
    doc = ru._read_doc()
    for r in doc["records"]:
        r["expiresDate"] = "2020-01-01T00:00:00+00:00"
    ru._write_main(doc)
    assert ru.locked_names(LNAME) == set()


def test_damaged_usage_file_is_kept_aside_and_the_locks_come_back(ru):
    p = ru._path()
    p.write_text("{ this is not json", encoding="utf-8")
    assert {"mc-01-a"} <= ru.locked_names(LNAME)                     # restored from the AppData copy, not read as empty
    assert p.with_suffix(".json.bad").read_text() == "{ this is not json"
    assert json.loads(p.read_text())["records"]                        # main file repaired


def test_a_save_after_damage_never_wipes_the_locks(ru):
    ru._path().write_text("garbage", encoding="utf-8")
    ru.record_usage(location_id="l2", location_name="Other Bar", round_files=[{"order": 1, "type": "REG", "file": "Files/Trivia/REG/reg-a.bighat"}],
                    used_by="x", presentation_id="p2", presentation_name="y")
    assert "mc-01-a" in ru.locked_names(LNAME) and "reg-a" in ru.locked_names("Other Bar")


def test_empty_file_is_restored_from_the_appdata_copy(ru):
    ru._path().write_text("", encoding="utf-8")                        # 0 bytes, e.g. after a crash mid-write
    assert "mc-01-a" in ru.locked_names(LNAME)


def test_a_missing_file_is_a_fresh_start_and_does_not_bring_old_locks_back(ru):
    ru._path().unlink()
    assert ru.locked_names(LNAME) == set()


def test_a_second_copy_is_kept_outside_documents(ru):
    b = ru._backup_file()
    assert b and b.is_file() and json.loads(b.read_text())["records"]


# ---- the builder and the legacy import path, through the real code ----
@pytest.fixture
def root(tmp_path, monkeypatch, ru):
    for t in ("MC", "REG", "MISC", "MYS", "BIG"):
        d = tmp_path / "Files" / "Trivia" / t
        d.mkdir(parents=True, exist_ok=True)
    (tmp_path / "Files" / "Trivia" / "Rounds").mkdir(exist_ok=True)
    return tmp_path


def test_legacy_import_refuses_locked_rounds_and_records_new_ones(root, ru):
    from fastapi import HTTPException
    from models import TriviaImportRequest
    from routes import presentations as pr
    pr.db = type("D", (), {"trivia_presentations": type("C", (), {"insert_one": staticmethod(lambda d: asyncio.sleep(0))})()})()
    nm = {"location": {"id": LID, "name": LNAME, "slug": "cornish"}, "host": {"name": "Nick"}}
    bad = TriviaImportRequest(userName="nick", host="h", location=f"location:{LID}", numRounds=5,
                              rounds=["Files/Trivia/MC/mc-01-a.bighat"], roundTypes=["MC"], roundNames=["mc-01-a"],
                              presentationName="again", nativeManifest=nm)
    with pytest.raises(HTTPException) as e:
        asyncio.run(pr._import_trivia_native(bad))
    assert e.value.status_code == 409 and "locked for this location" in e.value.detail
    ok = TriviaImportRequest(userName="nick", host="h", location=f"location:{LID}", numRounds=5,
                             rounds=["Files/Trivia/MC/mc-99-new.bighat"], roundTypes=["MC"], roundNames=["mc-99-new"],
                             presentationName="fresh", nativeManifest=nm)
    out = asyncio.run(pr._import_trivia_native(ok))
    assert out["rounds"] == 1 and "mc-99-new" in ru.locked_names(LNAME)          # its own rounds are locked now too
