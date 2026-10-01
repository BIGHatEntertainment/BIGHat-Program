"""180-day round lockout (disk-backed). Mirrors the webapp prototype."""
import sys, json
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pytest


@pytest.fixture
def ru(tmp_path, monkeypatch):
    monkeypatch.setenv("BIGHAT_FILES_DIR", str(tmp_path))
    for n in list(sys.modules):
        if n in ("round_usage", "native_slides"):
            sys.modules.pop(n, None)
    import round_usage
    return round_usage


RF = [{"order": 1, "type": "MC", "file": "Files/Trivia/MC/mc-02-a.bighat"},
      {"order": 2, "type": "REG", "file": "Files/Trivia/REG/reg-space-1.bighat"}]


def rec(ru, loc="Monkey Pants Bar Grill", pid="p1"):
    return ru.record_usage(location_id="loc-1", location_name=loc, round_files=RF,
                           used_by="Nick", presentation_id=pid, presentation_name="Show")


def test_record_creates_locked_rounds(ru):
    assert rec(ru) == 2
    assert {"mc-02-a", "reg-space-1"} <= ru.locked_names("Monkey Pants Bar Grill")
    assert len(ru.list_records()) == 2


def test_idempotent_per_presentation(ru):
    rec(ru); assert rec(ru) == 0
    assert len(ru.list_records()) == 2


def test_lock_is_per_location(ru):
    rec(ru)
    assert ru.locked_names("Patent 139") == set()
    assert "mc-02-a" in ru.locked_names("monkey-pants-bar-grill")  # slug form matches


def test_expires_after_180_days(ru):
    rec(ru)
    p = ru._path(); d = json.loads(p.read_text())
    old = (datetime.now(timezone.utc) - timedelta(days=181)).isoformat()
    for r in d["records"]:
        r["usedDate"] = old
        r["expiresDate"] = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    p.write_text(json.dumps(d))
    assert ru.locked_names("Monkey Pants Bar Grill") == set()
    assert all(r["isExpired"] for r in ru.list_records())
    assert ru.cleanup_expired() == 2 and ru.list_records() == []


def test_admin_release_single_and_by_presentation(ru):
    rec(ru, pid="p1"); rec(ru, pid="p2")
    first = next(r for r in ru.list_records() if r["presentationId"] == "p1")["id"]
    assert ru.release(first) == 1
    assert ru.release_presentation("p2") == 2
    assert len(ru.list_records()) == 1
    assert ru.release("nope") == 0


def test_survives_restart_disk_is_truth(ru):
    rec(ru)
    sys.modules.pop("round_usage", None)
    import round_usage as again
    assert len(again.list_records()) == 2


def test_stats(ru):
    rec(ru)
    s = ru.stats()
    assert s["totalUsageRecords"] == 2 and s["activeRecords"] == 2 and s["usageByType"]["MC"] == 1


def test_builder_blocks_locked_and_allows_after_release(tmp_path, monkeypatch):
    monkeypatch.setenv("BIGHAT_FILES_DIR", str(tmp_path))
    for n in list(sys.modules):
        if n in ("round_usage", "native_slides", "presentation_builder"):
            sys.modules.pop(n, None)
    import presentation_builder as pb, round_usage
    root = tmp_path / "Files"
    for t, nm in (("MC", "mc-1"), ("REG", "reg-1"), ("MISC", "misc-1"), ("MYS", "mys-1"), ("BIG", "big-1")):
        (root / "Trivia" / t).mkdir(parents=True, exist_ok=True)
        (root / "Trivia" / t / f"{nm}.bighat").write_text("{}")
    h = root / "Hosts" / "h@x.com"; h.mkdir(parents=True)
    (h / "host.json").write_text(json.dumps({"email": "h@x.com", "display_name": "H", "id": "h@x.com"}))
    L = root / "Locations" / "bar"; L.mkdir(parents=True)
    (L / "location.json").write_text(json.dumps({"id": "loc-1", "name": "Bar", "slug": "bar"}))
    args = dict(name="S", host_id="h@x.com", location_id="loc-1", round_count=5,
                round_files=["mc-1", "reg-1", "misc-1", "mys-1", "big-1"])
    a = pb.build_from_wizard(**args)
    assert len(round_usage.list_records()) == 5
    with pytest.raises(pb.BuildValidationError) as e:
        pb.build_from_wizard(**args)
    assert "locked" in str(e.value).lower()
    round_usage.release_presentation(a["id"])
    pb.build_from_wizard(**args)  # allowed after admin release


def test_backfill_existing_show_and_release_sticks(tmp_path, monkeypatch):
    monkeypatch.setenv("BIGHAT_FILES_DIR", str(tmp_path))
    for n in list(sys.modules):
        if n in ("round_usage", "native_slides"):
            sys.modules.pop(n, None)
    import round_usage
    rd = tmp_path / "Files" / "Trivia" / "Rounds"; rd.mkdir(parents=True)
    (rd / "old.bighat").write_text(json.dumps({
        "id": "pres-old", "name": "Monkey Pants Bar Grill - 10/1", "location_id": "loc-1",
        "location_name": "Monkey Pants Bar Grill", "host_name": "Nick Sellards",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "roundFiles": [{"order": 1, "type": "MC", "file": "Files/Trivia/MC/MC_02_A.bighat"},
                       {"order": 2, "type": "REG", "file": "Files/Trivia/REG/REG__space-1.bighat"}]}))
    recs = round_usage.list_records()          # backfill happens here
    assert len(recs) == 2 and recs[0]["presentationName"].startswith("Monkey")
    assert "mc_02_a" in round_usage.locked_names("Monkey Pants Bar Grill")
    assert round_usage.release_presentation("pres-old") == 2
    assert round_usage.list_records() == []    # NOT resurrected by backfill
    assert round_usage.locked_names("Monkey Pants Bar Grill") == set()
