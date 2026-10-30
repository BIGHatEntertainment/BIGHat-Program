"""Cloud show bundles -> the Program (docs/PROGRAM_TASK_cloud_show_import.md). Real files on a real tmp disk, real round fixtures
(File Creator ZIPs) in the Cloud's exact bundle layout. Only the HTTP to the Cloud is faked."""
import asyncio, io, json, sys, zipfile
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import presentation_builder as pb  # noqa: E402
from native import cloud_shows  # noqa: E402

FX = ROOT / "tests" / "fixtures" / "bighat"
ROUNDS = {"MC": "mc-01-a.bighat", "REG": "animals-1.bighat", "MISC": "arizona-1.bighat", "MYS": "mystery-apples.bighat",
          "BIG": "big-cactus-league-easy.bighat"}


def run(c): return asyncio.run(c)


class _Cur:
    def __init__(self, rows): self.rows = rows
    async def to_list(self, n): return self.rows


class _Coll:
    def __init__(self, rows): self.rows = rows
    def find(self, q=None, proj=None): return _Cur(list(self.rows))
    async def find_one(self, q=None, proj=None):
        for r in self.rows:
            if all(r.get(k) == v for k, v in (q or {}).items()):
                return r
        return None


class FakeDb:
    def __init__(self, venues, locations, employees=()):
        self.venues, self.locations, self.employees, self.users = _Coll(venues), _Coll(locations), _Coll(list(employees)), _Coll([])


def bundle(types=("MC", "REG", "MISC", "MYS", "BIG"), host_email="test@example.com", venue="Test Bar", drop=None, version=1, extra=None):
    buf = io.BytesIO()
    rounds = []
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for i, t in enumerate(types):
            fn = ROUNDS[t] if types.count(t) == 1 else f"{t.lower()}-{i}.bighat"
            rounds.append({"order": i + 1, "type": t, "name": t + " round", "round_key": fn[:-7], "file": f"rounds/{t}/{fn}"})
            if drop != i:
                z.writestr(f"rounds/{t}/{fn}", (FX / ROUNDS[t]).read_bytes() if not extra else extra)
        z.writestr("manifest.json", json.dumps({"format": "bighat", "version": version, "type": "trivia-show-bundle", "plan_id": "plan1",
                                                 "name": "Friday Show", "round_count": len(types)}))
        z.writestr("payload.json", json.dumps({"host": {"name": "Test Host", "email": host_email, "employee_id": "e1"},
                                               "location": {"name": venue, "cloud_venue_id": "v1"}, "round_count": len(types), "rounds": rounds}))
    return buf.getvalue()


@pytest.fixture
def pc(tmp_path, monkeypatch):
    monkeypatch.setenv("BIGHAT_FILES_DIR", str(tmp_path))
    monkeypatch.setenv("BIGHAT_DATA_ROOT", str(tmp_path / "app"))
    monkeypatch.setenv("BIGHAT_CONFIG_PATH", str(tmp_path / "system_config.json"))
    hd = tmp_path / "Files" / "Hosts" / "host-001"; hd.mkdir(parents=True)
    (hd / "host.json").write_text(json.dumps({"id": "host-001", "display_name": "Test Host", "email": "test@example.com"}))
    ld = tmp_path / "Files" / "Locations" / "test-bar"; ld.mkdir(parents=True)
    (ld / "location.json").write_text(json.dumps({"id": "loc-001", "slug": "test-bar", "name": "Test Bar"}))
    (tmp_path / "Files" / "Trivia" / "Rounds").mkdir(parents=True)
    db = FakeDb([{"id": "v-local", "name": "Test Bar", "location_id": "loc-001"}], [{"id": "loc-001", "slug": "test-bar", "name": "Test Bar"}])
    return tmp_path, db


def test_a_real_bundle_imports_into_a_show_ready_to_host(pc):
    root, db = pc
    r = run(cloud_shows.import_bundle(db, bundle()))
    assert r["ok"], r
    assert r["rounds"] == 5 and r["new_round_files"] == 5 and r["location"] == "Test Bar"
    for t, fn in ROUNDS.items():
        assert (root / "Files" / "Trivia" / t / fn).read_bytes() == (FX / fn).read_bytes()      # byte for byte
    shows = list((root / "Files" / "Trivia" / "Rounds").glob("*.bighat"))
    assert len(shows) == 1
    doc = json.loads(shows[0].read_text(encoding="utf-8"))
    assert doc["host_name"] == "Test Host" and doc["location_name"] == "Test Bar" and [x["type"] for x in doc["roundFiles"]] == ["MC", "REG", "MISC", "MYS", "BIG"]


def test_the_180_day_lock_starts_at_import(pc):
    import round_usage
    root, db = pc
    assert run(cloud_shows.import_bundle(db, bundle()))["ok"]
    assert len(round_usage.list_records()) == 5
    again = run(cloud_shows.import_bundle(db, bundle()))
    assert not again["ok"] and again["code"] == "locked" and again["can_override"] is True


def test_locked_round_can_be_imported_after_an_admin_agrees(pc):
    root, db = pc
    run(cloud_shows.import_bundle(db, bundle()))
    r = run(cloud_shows.import_bundle(db, bundle(), allow_locked=True))
    assert r["ok"], r
    assert len(list((root / "Files" / "Trivia" / "Rounds").glob("*.bighat"))) == 2


def test_missing_host_imports_nothing_and_says_so(pc):
    root, db = pc
    r = run(cloud_shows.import_bundle(db, bundle(host_email="nobody@x.com")))
    assert not r["ok"] and r["code"] == "host_missing" and r["missing"] == "host" and "nobody@x.com" in r["message"]
    assert not list((root / "Files" / "Trivia" / "MC").glob("*")) and not list((root / "Files" / "Trivia" / "Rounds").glob("*"))


def test_missing_venue_imports_nothing_and_says_so(pc):
    root, db = pc
    r = run(cloud_shows.import_bundle(db, bundle(venue="Other Bar")))
    assert not r["ok"] and r["code"] == "venue_missing" and r["missing"] == "venue"
    assert not (root / "Files" / "Trivia" / "REG").exists() or not list((root / "Files" / "Trivia" / "REG").glob("*"))


def test_venue_matches_by_name_ignoring_case_and_punctuation(pc):
    root, db = pc
    assert run(cloud_shows.import_bundle(db, bundle(venue="TEST  bar!")))["ok"]


def test_a_round_missing_from_the_file_imports_nothing(pc):
    root, db = pc
    r = run(cloud_shows.import_bundle(db, bundle(drop=2)))
    assert not r["ok"] and r["code"] == "missing_round"
    assert not list((root / "Files" / "Trivia" / "Rounds").glob("*"))


def test_a_round_that_is_not_a_valid_file_imports_nothing(pc):
    r = run(cloud_shows.import_bundle(pc[1], bundle(extra=b"not a zip at all")))
    assert not r["ok"] and r["code"] == "bad_round"


def test_wrong_round_order_is_refused(pc):
    r = run(cloud_shows.import_bundle(pc[1], bundle(types=("REG", "MC", "MISC", "MYS", "BIG"))))
    assert not r["ok"] and r["code"] == "bad_rounds"


def test_not_a_bundle_and_newer_version_and_unsafe_paths(pc):
    assert run(cloud_shows.import_bundle(pc[1], b"hello"))["code"] == "not_a_bundle"
    assert run(cloud_shows.import_bundle(pc[1], bundle(version=2)))["code"] == "newer"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("../evil.txt", "x"); z.writestr("manifest.json", "{}"); z.writestr("payload.json", "{}")
    assert run(cloud_shows.import_bundle(pc[1], buf.getvalue()))["code"] == "unsafe"


def test_same_name_different_file_is_kept_not_overwritten(pc):
    root, db = pc
    mc = root / "Files" / "Trivia" / "MC"; mc.mkdir(parents=True, exist_ok=True)
    (mc / "mc-01-a.bighat").write_bytes(b"MY OWN DIFFERENT ROUND")
    r = run(cloud_shows.import_bundle(db, bundle()))
    assert r["ok"], r
    assert (mc / "mc-01-a.bighat").read_bytes() == b"MY OWN DIFFERENT ROUND"                      # untouched
    assert len(list(mc.glob("mc-01-a-*.bighat"))) == 1


def test_a_failure_part_way_removes_only_what_it_created(pc, monkeypatch):
    root, db = pc
    def boom(**kw): raise RuntimeError("disk full")
    import presentation_builder as live_pb                      # the module cloud_shows really imports (other tests reload it)
    monkeypatch.setattr(live_pb, "build_from_wizard", boom)
    r = run(cloud_shows.import_bundle(db, bundle()))
    assert not r["ok"] and r["code"] == "error"
    for t in ROUNDS:
        d = root / "Files" / "Trivia" / t
        assert not d.exists() or not list(d.glob("*.bighat"))


def test_pull_lists_and_imports_then_reports(pc, monkeypatch):
    root, db = pc
    calls = []
    async def fake_get(path, params=None, raw=False):
        calls.append(path)
        if raw: return {"ok": True, "content": bundle()}
        return {"ok": True, "data": {"plans": [{"id": "plan1", "name": "Friday Show", "venue_name": "Test Bar", "host_name": "Test Host", "round_count": 5, "size": 1, "complete": True}]}}
    async def fake_report(pid): calls.append("reported:" + pid)
    monkeypatch.setattr(cloud_shows, "_get", fake_get); monkeypatch.setattr(cloud_shows, "report_imported", fake_report)
    assert run(cloud_shows.list_shows())["shows"][0]["id"] == "plan1"
    assert run(cloud_shows.pull_and_import(db, "plan1"))["ok"]
    assert calls[-1] == "reported:plan1"


def test_offline_and_lapsed_leave_the_pc_alone(pc, monkeypatch):
    async def off(path, params=None, raw=False): return {"ok": False, "error": "subscription_lapsed", "message": "lapsed"}
    monkeypatch.setattr(cloud_shows, "_get", off)
    assert run(cloud_shows.list_shows()) == {"ok": False, "error": "subscription_lapsed", "message": "lapsed", "shows": []}
    r = run(cloud_shows.pull_and_import(pc[1], "plan1"))
    assert not r["ok"] and r["code"] == "subscription_lapsed"
    assert run(cloud_shows.pull_and_import(pc[1], "../../etc"))["code"] == "bad_id"
