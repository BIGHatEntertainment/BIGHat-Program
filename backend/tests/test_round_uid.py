"""Permanent round ID (docs/PLAN_round_id_stamp.md): real round files on a real tmp disk, real round_usage.json, real cloud_locks."""
import io, json, sys, zipfile
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(Path(__file__).resolve().parent))
import round_uid  # noqa: E402

U1 = "11111111-1111-4111-8111-111111111111"
U2 = "22222222-2222-4222-8222-222222222222"


def mk(path: Path, uid=None, content_id="c1", junk=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    if junk:
        path.write_text('{"plain": "json round"}'); return path
    with zipfile.ZipFile(path, "w") as z:
        m = {"format_version": "1.0", "content_id": content_id, "type": "round"}
        if uid: m["round_uid"] = uid
        z.writestr("manifest.json", json.dumps(m)); z.writestr("payload.json", "{}")
    return path


round_usage = None          # set by the fixture: a fresh module each test (other test files drop it from sys.modules)


@pytest.fixture
def pc(tmp_path, monkeypatch):
    global round_usage
    for n in ("round_usage", "round_uid", "native_slides", "presentation_builder"):
        sys.modules.pop(n, None)                    # same pattern as tests/test_alpha62_round_usage_lock.py
    import native_slides, presentation_builder as pb
    import round_usage as _ru, round_uid as _uid
    globals()["round_uid"] = _uid
    round_usage = _ru
    monkeypatch.setattr(native_slides, "_docs_root", lambda: tmp_path)
    monkeypatch.setattr(pb, "_docs_root", lambda: tmp_path)
    monkeypatch.setattr(pb, "_files_root", lambda: tmp_path / "Files")
    _uid._cache.clear()
    return tmp_path / "Files" / "Trivia"


def use(venue, fname, n=1):
    return round_usage.record_usage(location_id=venue, location_name=venue, round_files=[{"order": n, "type": "REG", "file": fname}],
                                    used_by="s", presentation_id=f"p-{fname}-{n}", presentation_name="Show")


def locked(venue, fname): return round_usage.is_locked(fname, round_usage.locked_names(venue))


def test_reads_only_a_valid_uid(pc):
    assert round_uid.read_uid(mk(pc / "REG" / "a.bighat", U1)) == U1
    assert round_uid.read_uid(mk(pc / "REG" / "b.bighat")) is None                         # not stamped
    assert round_uid.read_uid(mk(pc / "REG" / "c.bighat", "not-a-uuid")) is None            # junk is never trusted
    assert round_uid.read_uid(mk(pc / "REG" / "d.bighat", junk=True)) is None              # old plain-JSON round
    assert round_uid.read_uid(pc / "REG" / "missing.bighat") is None
    assert round_uid.read_uid(mk(pc / "REG" / "e.bighat", U1.upper())) == U1                # case never splits one round into two


def test_a_renamed_copy_of_a_used_round_is_still_locked(pc):
    mk(pc / "REG" / "history-1.bighat", U1)
    use("pub", "history-1.bighat")
    mk(pc / "REG" / "my-new-name.bighat", U1)                    # same round, different file name
    assert locked("pub", "history-1.bighat") and locked("pub", "my-new-name.bighat")
    assert not locked("other-bar", "my-new-name.bighat")          # locks stay per venue


def test_an_edited_round_keeps_the_same_uid_and_the_same_lock(pc):
    mk(pc / "REG" / "r.bighat", U1, content_id="export-A")
    use("pub", "r.bighat")
    mk(pc / "REG" / "r.bighat", U1, content_id="export-B")       # edited + re-exported: new content_id, SAME round_uid
    sys.modules['round_uid']._cache.clear()
    assert locked("pub", "r.bighat")
    rec = round_usage._load()[0]
    assert rec["roundUid"] == U1


def test_a_different_round_with_the_same_name_is_still_caught_by_name_rule_so_nothing_is_lost(pc):
    """Names keep locking too (owner: never lose a lock). Uid only ADDS matches."""
    mk(pc / "REG" / "history.bighat", U1); use("pub", "history.bighat")
    mk(pc / "MYS" / "history.bighat", U2)
    assert locked("pub", str(pc / "MYS" / "history.bighat"))      # same bare name: still locked (safe side), documented in the plan


def test_old_locks_with_no_uid_keep_working_by_name(pc):
    mk(pc / "REG" / "old.bighat")                                 # unstamped
    use("pub", "old.bighat")
    rec = round_usage._load()[0]
    assert "roundUid" not in rec and locked("pub", "old.bighat") and locked("pub", "REG__old-1a2b3c4d.bighat")
    mk(pc / "REG" / "old.bighat", U1)                             # later replaced by the stamped copy from the Cloud
    sys.modules['round_uid']._cache.clear()
    assert locked("pub", "old.bighat")                            # the lock made before it was stamped still holds


def test_the_record_stores_the_uid_when_the_file_is_stamped(pc):
    mk(pc / "REG" / "s.bighat", U1); use("pub", "s.bighat")
    assert round_usage._load()[0]["roundUid"] == U1


def test_release_frees_the_round_under_its_uid_and_its_names(pc):
    mk(pc / "REG" / "a.bighat", U1); mk(pc / "REG" / "renamed.bighat", U1)
    use("pub", "a.bighat")
    rid = round_usage._load()[0]["id"]
    assert round_usage.release(rid) == 1
    assert not locked("pub", "a.bighat") and not locked("pub", "renamed.bighat")
    assert round_usage.cloud_is_tombstoned("pub", "pub", "renamed.bighat")        # the renamed copy cannot be re-locked by an old saved show


def test_cloud_add_stores_the_uid_and_locks_a_renamed_local_copy(pc):
    mk(pc / "REG" / "local-name.bighat", U1)
    rid = round_usage.cloud_add(location_id="pub", location_name="pub", file_name="cloud-name.bighat", round_type="REG",
                                used_at="2026-10-29T12:00:00+00:00", expires_at="2027-04-27T12:00:00+00:00", used_by="x",
                                presentation_id="p", presentation_name="n", round_uid=U1)
    assert rid and round_usage._load()[0]["roundUid"] == U1
    assert locked("pub", "local-name.bighat")                     # the Cloud knew it by another name; the id ties them together


def test_cloud_release_by_uid_frees_a_renamed_local_copy(pc):
    mk(pc / "REG" / "mine.bighat", U1); use("pub", "mine.bighat")
    assert round_usage.cloud_release("pub", "pub", "totally-other-name.bighat", None, round_uid=U1) == 1
    assert not locked("pub", "mine.bighat")


def test_a_bad_uid_from_the_cloud_is_ignored(pc):
    rid = round_usage.cloud_add(location_id="pub", location_name="pub", file_name="x.bighat", round_type="REG", used_at=None,
                                expires_at=None, used_by="", presentation_id="", presentation_name="", round_uid="'; DROP TABLE")
    assert rid and "roundUid" not in round_usage._load()[0]


def test_unstamped_files_are_listed_for_the_owner_to_delete(pc):
    mk(pc / "REG" / "good.bighat", U1); mk(pc / "REG" / "old.bighat"); mk(pc / "MC" / "j.bighat", junk=True)
    got = {(x["type"], x["file"]) for x in round_uid.unstamped_files()}
    assert got == {("REG", "old.bighat"), ("MC", "j.bighat")}


def test_the_program_never_writes_into_a_round_file(pc):
    p = mk(pc / "REG" / "keep.bighat"); before = p.read_bytes()
    use("pub", "keep.bighat"); locked("pub", "keep.bighat"); round_uid.unstamped_files()
    assert p.read_bytes() == before


def test_a_broken_file_never_stops_locks(pc):
    (pc / "REG").mkdir(parents=True, exist_ok=True); (pc / "REG" / "bad.bighat").write_bytes(b"\x00\x01 not a zip")
    assert use("pub", "bad.bighat") == 1 and locked("pub", "bad.bighat")


# ---- sync: the uid travels with the lock; item ids do NOT change (an existing lock never duplicates)
def test_cloud_sync_sends_and_receives_the_uid(pc, monkeypatch):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from native import cloud_locks
    mk(pc / "REG" / "w.bighat", U1); use("pub", "w.bighat")
    rec = round_usage._load()[0]
    st = cloud_locks._blank()
    venues = {"v1": {"ids": {"pub"}, "name": "Pub", "location_id": "pub"}}
    cloud_locks._plan(st, venues)
    act = next(a for k, a in st["outbox"].items() if k.startswith("lock:"))
    assert act["payload"]["round_uid"] == U1
    assert act["payload"]["item_id"] == cloud_locks.lock_item_id("v1", cloud_locks.round_key("w.bighat"), rec["presentationId"])   # unchanged id
    assert st["pushed"][rec["id"]]["uid"] == U1


def test_unstamped_list_endpoint_is_read_only(pc):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routes import trivia
    mk(pc / "REG" / "good.bighat", U1); old = mk(pc / "REG" / "old.bighat")
    app = FastAPI(); app.include_router(trivia.router, prefix="/api")
    r = TestClient(app).get("/api/trivia/round-files-without-id")
    assert r.status_code == 200 and r.json()["count"] == 1 and r.json()["files"][0]["file"] == "old.bighat"
    assert old.exists()                                            # listing never deletes anything
