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


# ======================= v32.2.6: the Cloud's new format (round_uid stamped, shows split into parts) =======================
UIDS = {"MC": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "REG": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", "MISC": "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
        "MYS": "dddddddd-dddd-4ddd-8ddd-dddddddddddd", "BIG": "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"}


def stamped(t, uid=None):
    """The Cloud's stamp: ONLY manifest.json rewritten (round_uid added), every other member byte for byte."""
    src = zipfile.ZipFile(FX / ROUNDS[t]); out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for info in src.infolist():
            data = src.read(info.filename)
            if info.filename == "manifest.json":
                m = json.loads(data.decode("utf-8-sig")); m["round_uid"] = uid or UIDS[t]; data = json.dumps(m).encode()
            z.writestr(info.filename, data)
    return out.getvalue()


def parts_bundle(split=((0, 1, 2), (3, 4)), types=("MC", "REG", "MISC", "MYS", "BIG"), plan="planX", host_email="test@example.com",
                 venue="Test Bar", promise=None, skip_part=None, drop_member=None):
    """A show in the Cloud's new transfer format. split = which round indexes go in which part."""
    blobs = []
    rounds = []
    for pi, idxs in enumerate(split, 1):
        for i in idxs:
            t = types[i]
            rounds.append({"order": i + 1, "type": t, "name": t + " round", "round_key": t.lower(), "round_uid": (promise or UIDS)[t],
                           "part": pi, "file": f"rounds/{t}/{ROUNDS[t]}"})
    total = len(split)
    for pi, idxs in enumerate(split, 1):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("manifest.json", json.dumps({"format": "bighat", "version": 1, "type": "trivia-show-bundle", "plan_id": plan,
                                                     "name": "Friday Show", "part": pi, "parts_total": total, "round_count": len(types)}))
            if pi == 1:
                z.writestr("payload.json", json.dumps({"host": {"name": "Test Host", "email": host_email, "employee_id": "e1"},
                                                       "location": {"name": venue, "cloud_venue_id": "v1"}, "round_count": len(types),
                                                       "parts_total": total, "rounds": sorted(rounds, key=lambda r: r["order"])}))
            for i in idxs:
                if drop_member == i:
                    continue
                z.writestr(f"rounds/{types[i]}/{ROUNDS[types[i]]}", stamped(types[i]))
        blobs.append(buf.getvalue())
    if skip_part:
        blobs.pop(skip_part - 1)
    return blobs


def test_a_show_in_two_parts_imports_as_one_show(pc):
    root, db = pc
    r = run(cloud_shows.import_parts(db, parts_bundle()))
    assert r["ok"], r
    assert r["rounds"] == 5 and r["parts"] == 2 and r["new_round_files"] == 5
    assert r["round_uids"] == [UIDS[t] for t in ("MC", "REG", "MISC", "MYS", "BIG")]
    assert len(list((root / "Files" / "Trivia" / "Rounds").glob("*.bighat"))) == 1


def test_parts_can_arrive_in_any_order(pc):
    root, db = pc
    assert run(cloud_shows.import_parts(db, list(reversed(parts_bundle()))))["ok"]


def test_the_rounds_keep_their_cloud_stamp_byte_for_byte_and_the_lock_records_the_round_id(pc):
    import round_usage, round_uid
    root, db = pc
    blobs = parts_bundle()
    sent = {}                                                   # the exact bytes the Cloud put in each part
    for b in blobs:
        z = zipfile.ZipFile(io.BytesIO(b))
        for n in z.namelist():
            if n.startswith("rounds/"):
                sent[n.split("/")[1]] = z.read(n)
    assert run(cloud_shows.import_parts(db, blobs))["ok"]
    for t in ROUNDS:
        assert round_uid.read_uid(root / "Files" / "Trivia" / t / ROUNDS[t]) == UIDS[t]
        assert (root / "Files" / "Trivia" / t / ROUNDS[t]).read_bytes() == sent[t]                # exactly what the Cloud sent
    got = {r["roundType"]: r.get("roundUid") for r in round_usage.list_records()}
    assert got == UIDS                                                                          # both sides log the SAME round id


def test_a_missing_part_imports_nothing_and_says_which(pc):
    root, db = pc
    r = run(cloud_shows.import_parts(db, parts_bundle(skip_part=2)))
    assert not r["ok"] and r["code"] == "missing_part" and "part 2" in r["message"] and r["parts_total"] == 2
    assert not list((root / "Files" / "Trivia" / "Rounds").glob("*")) and not (root / "Files" / "Trivia" / "BIG" / ROUNDS["BIG"]).exists()


def test_parts_of_two_different_shows_are_refused(pc):
    a, b = parts_bundle(plan="A"), parts_bundle(plan="B")
    assert run(cloud_shows.import_parts(pc[1], [a[0], b[1]]))["code"] == "mixed_parts"


def test_the_same_part_twice_is_refused(pc):
    a = parts_bundle()
    assert run(cloud_shows.import_parts(pc[1], [a[0], a[0]]))["code"] == "duplicate_part"


def test_a_round_that_is_not_the_one_the_show_promised_is_refused(pc):
    wrong = dict(UIDS); wrong["MYS"] = "99999999-9999-4999-8999-999999999999"                   # payload promises another round id
    r = run(cloud_shows.import_parts(pc[1], parts_bundle(promise=wrong)))
    assert not r["ok"] and r["code"] == "round_mismatch" and "MYS" in r["message"]


def test_a_round_missing_from_its_part_is_refused(pc):
    r = run(cloud_shows.import_parts(pc[1], parts_bundle(drop_member=4)))
    assert not r["ok"] and r["code"] == "missing_round"


def test_a_single_file_show_in_the_new_format_still_imports(pc):
    r = run(cloud_shows.import_bundle(pc[1], parts_bundle(split=((0, 1, 2, 3, 4),))[0]))
    assert r["ok"] and r["parts"] == 1


def test_the_generic_file_importer_refuses_one_part_of_several(pc):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routes import bighat_files
    bighat_files.db = pc[1]
    app = FastAPI(); app.include_router(bighat_files.router, prefix="/api")
    r = TestClient(app).post("/api/bighat-files/import", files={"file": ("p1.bighat", parts_bundle()[0], "application/octet-stream")})
    assert r.status_code == 409 and "2 parts" in r.json()["detail"]


def test_pull_downloads_every_part_before_importing(pc, monkeypatch):
    root, db = pc
    blobs = parts_bundle(); asked = []
    async def fake_get(path, params=None, raw=False):
        if not raw:
            return {"ok": True, "data": {"plans": []}}
        n = int((params or {}).get("part") or 1); asked.append(n)
        return {"ok": True, "content": blobs[n - 1], "parts_total": "2"}
    reported = []
    async def fake_report(pid): reported.append(pid)
    monkeypatch.setattr(cloud_shows, "_get", fake_get); monkeypatch.setattr(cloud_shows, "report_imported", fake_report)
    r = run(cloud_shows.pull_and_import(db, "planX"))
    assert r["ok"] and asked == [1, 2] and reported == ["planX"] and r["parts"] == 2


def test_a_part_that_will_not_download_imports_nothing(pc, monkeypatch):
    root, db = pc
    blobs = parts_bundle()
    async def fake_get(path, params=None, raw=False):
        n = int((params or {}).get("part") or 1)
        if n == 2:
            return {"ok": False, "error": "unreachable", "message": "Could not reach the Cloud."}
        return {"ok": True, "content": blobs[0], "parts_total": "2"}
    monkeypatch.setattr(cloud_shows, "_get", fake_get)
    r = run(cloud_shows.pull_and_import(db, "planX"))
    assert not r["ok"] and "Part 2" in r["message"] and "Nothing was imported" in r["message"]
    assert not list((root / "Files" / "Trivia" / "Rounds").glob("*"))


def test_the_multi_file_route_takes_all_the_parts_together(pc):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from native import cloud_link_router as clr
    clr._db = lambda: pc[1]
    app = FastAPI(); app.include_router(clr.router)
    files = [("files", (f"p{i}.bighat", b, "application/octet-stream")) for i, b in enumerate(parts_bundle(), 1)]
    res = TestClient(app).post(clr.router.prefix + "/shows/import-files", files=files)
    assert res.status_code == 200 and res.json()["ok"] and res.json()["parts"] == 2


def test_the_cloud_shows_card_reads_exactly_the_fields_the_cloud_list_sends():
    """The card (frontend/src/components/CloudShows.jsx) and the Cloud list (routes/trivia_plan_routes.py program list) must agree on names."""
    card = (ROOT.parent / "frontend" / "src" / "components" / "CloudShows.jsx").read_text(encoding="utf-8")
    cloud_sends = {"id", "name", "venue_name", "host_name", "round_count", "parts", "complete"}      # from the Cloud's program list
    used = {f for f in ("id", "name", "venue_name", "host_name", "round_count", "parts", "complete") if f"s.{f}" in card}
    assert used == cloud_sends
    import re
    assert set(re.findall(r"\bs\.([a-z_]+)", card)) <= cloud_sends | {"id"}                             # the card reads nothing else
    assert "api.cloudShows" in card and "api.cloudShowImport" in card and "import api from" in card       # default export, not a named one


def test_the_api_helpers_the_card_calls_exist_and_point_at_the_program_routes():
    js = (ROOT.parent / "frontend" / "src" / "lib" / "api.js").read_text(encoding="utf-8")
    assert "cloudShows:" in js and "/cloud-link/shows`" in js and "cloudShowImport:" in js and "/cloud-link/shows/${encodeURIComponent(planId)}/import" in js
    from native import cloud_link_router as clr
    paths = {r.path for r in clr.router.routes}
    assert any(p.endswith("/shows") for p in paths) and any(p.endswith("/shows/{plan_id}/import") for p in paths)
    assert any(p.endswith("/shows/import-files") for p in paths)
