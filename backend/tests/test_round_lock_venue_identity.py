"""v32.1.10: the Wizard list was sent the venue id/image URL while a lock may be saved under the venue NAME (old or backfilled shows),
so the list offered a locked round and only the review page refused it. A venue's id, slug and name are now ONE place everywhere."""
import json, sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
LID, LN = "LOC-123", "Test Venue"
FILE = "Files/Trivia/MC/mc-a.bighat"


@pytest.fixture
def ru(tmp_path, monkeypatch):
    monkeypatch.setenv("BIGHAT_FILES_DIR", str(tmp_path / "Documents" / "BIG Hat Entertainment" / "Files"))
    monkeypatch.setenv("BIGHAT_DATA_ROOT", str(tmp_path / "appdata"))
    monkeypatch.setenv("HOME", str(tmp_path)); monkeypatch.setenv("USERPROFILE", str(tmp_path))
    for n in list(sys.modules):
        if n in ("round_usage", "native_slides") or n.startswith("native.data_map"):
            sys.modules.pop(n, None)
    import round_usage, native_slides
    round_usage.backfill_from_presentations = lambda: 0
    d = native_slides._docs_root() / "Files" / "Locations" / "test-venue"
    d.mkdir(parents=True)
    (d / "location.json").write_text(json.dumps({"id": LID, "slug": "test-venue", "name": LN}))
    return round_usage


SENT = [LN, LID, "test-venue", f"location:{LID}", f"/api/native/locations/{LID}/images/i1/raw", "123_Test Venue"]


@pytest.mark.parametrize("saved", [dict(location_id="", location_name=LN), dict(location_id=LID, location_name=""),
                                   dict(location_id="test-venue", location_name="")])
@pytest.mark.parametrize("sent", SENT)
def test_a_lock_is_found_whichever_form_saved_it_and_whichever_form_asks(ru, saved, sent):
    ru.record_usage(round_files=[{"order": 1, "type": "MC", "file": FILE}], used_by="n", presentation_id="p", presentation_name="t", **saved)
    assert "mc-a" in ru.locked_names(sent)


def test_another_venue_is_not_affected(ru):
    ru.record_usage(location_id="", location_name=LN, round_files=[{"order": 1, "type": "MC", "file": FILE}], used_by="n", presentation_id="p", presentation_name="t")
    for other in ("Other Bar", "location:zzz", "/api/native/locations/zzz/images/i/raw"):
        assert ru.locked_names(other) == set()


@pytest.mark.parametrize("sent", SENT)
def test_release_frees_it_for_every_form(ru, sent):
    ru.record_usage(location_id="", location_name=LN, round_files=[{"order": 1, "type": "MC", "file": FILE}], used_by="n", presentation_id="p", presentation_name="t")
    ru.record_usage(location_id=LID, location_name="", round_files=[{"order": 1, "type": "MC", "file": FILE}], used_by="n", presentation_id="q", presentation_name="t2")
    assert ru.release(ru.list_records()[0]["id"]) == 2                 # both spellings of the venue are one place: nothing keeps it locked
    assert ru.locked_names(sent) == set()


def test_unknown_venue_folder_does_not_break_the_list(ru):
    (ru._path().parent.parent.parent / "Locations" / "broken").mkdir(parents=True, exist_ok=True)
    assert ru.locked_names("Nowhere") == set()
