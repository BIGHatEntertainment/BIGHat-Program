"""PR 3: this PC's own rounds go up to the Cloud for stamping. Real files + MontyDB + the real HTTP routes; only the Cloud (manifest + upload) is faked."""
import hashlib, io, json, sys, zipfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from test_cloud_files_pull import env, run  # noqa: F401
from test_round_duplicates import blob, put, A, B, _stamp  # noqa: F401


class Cloud:
    def __init__(self, env):
        self.env, self.names, self.posts, self.mode = env, [], [], "ok"
        env.mp.setattr(env.cf, "_fetch_manifest", self.manifest)
        from native import cloud_upload
        self.cu = cloud_upload
        env.mp.setattr(cloud_upload, "_post", self.post)
        env.mp.setattr(cloud_upload, "_pull_soon", self.nopull)

    async def manifest(self):
        if self.mode == "down":
            return {"ok": False, "error": "unreachable"}
        return {"ok": True, "files": [{"file_id": f"c{i}", "category": "bighat", "name": n, "sha256": "x"} for i, n in enumerate(self.names)]}

    async def post(self, name, data):
        if self.mode == "not_ready":
            return {"ok": False, "error": "cloud_not_ready"}
        if self.mode == "die_on_2" and len(self.posts) == 1:
            return {"ok": False, "error": "unreachable"}
        self.posts.append((name, hashlib.sha256(data).hexdigest()))
        return {"ok": True, "body": {"status": "added"}}

    async def nopull(self, db):
        return None


def cloud(env):
    from native import cloud_link
    env.mp.setattr(cloud_link, "get_token", lambda: "tok"); env.mp.setattr(cloud_link, "cloud_base_url", lambda: "https://cloud.test")
    return Cloud(env)


def test_only_unstamped_pc_only_rounds_are_offered(env):
    c = cloud(env)
    put(env, "mine.bighat", blob(q="Q1")); put(env, "stamped.bighat", _stamp(blob(q="Q2"), A))
    r = run(c.cu.check(env.db))
    assert r["ok"] and [x["file"] for x in r["send"]] == ["mine.bighat"] and r["can_upload"] == 1


def test_a_name_the_cloud_already_holds_is_never_sent_even_with_a_hex_tail_or_type_prefix(env):
    c = cloud(env); c.names = ["flowers.bighat"]
    put(env, "flowers.bighat", blob(q="Q1")); put(env, "flowers-7297fdd0.bighat", blob(q="Q2")); put(env, "mine.bighat", blob(q="Q3"))
    r = run(c.cu.check(env.db))
    assert [x["file"] for x in r["send"]] == ["mine.bighat"] and sorted(x["file"] for x in r["name_in_cloud"]) == ["flowers-7297fdd0.bighat", "flowers.bighat"]
    c.names = ["REG__mine.bighat"]
    r2 = run(c.cu.check(env.db))                                  # the File Creator's TYPE__ prefix is the same round
    assert [x["file"] for x in r2["name_in_cloud"]] == ["mine.bighat"] and sorted(x["file"] for x in r2["send"]) == ["flowers-7297fdd0.bighat", "flowers.bighat"]


def test_check_changes_nothing_and_upload_sends_exactly_the_listed_files_and_deletes_nothing(env):
    c = cloud(env)
    a = put(env, "mine.bighat", blob(q="Q1")); b = put(env, "mine2.bighat", blob(q="Q2"))
    before = {p.name: p.read_bytes() for p in (a, b)}
    chk = run(c.cu.check(env.db)); assert c.posts == []
    res = run(c.cu.upload(env.db, chk["token"]))
    assert res["ok"] and sorted(res["sent"]) == ["mine.bighat", "mine2.bighat"] and len(c.posts) == 2
    assert {p.name: p.read_bytes() for p in (a, b)} == before
    assert c.posts[0][1] == hashlib.sha256(before[c.posts[0][0]]).hexdigest()          # the Cloud got the exact bytes


def test_a_second_run_does_not_send_the_same_file_again(env):
    c = cloud(env); put(env, "mine.bighat", blob(q="Q1"))
    run(c.cu.upload(env.db, run(c.cu.check(env.db))["token"]))
    r2 = run(c.cu.check(env.db))
    assert r2["can_upload"] == 0 and [x["file"] for x in r2["already_sent"]] == ["mine.bighat"] and len(c.posts) == 1


def test_a_file_edited_after_it_was_sent_is_offered_again(env):
    c = cloud(env); p = put(env, "mine.bighat", blob(q="Q1"))
    run(c.cu.upload(env.db, run(c.cu.check(env.db))["token"]))
    p.write_bytes(blob(q="Q1 edited"))
    assert run(c.cu.check(env.db))["can_upload"] == 1


def test_a_stale_or_missing_token_sends_nothing(env):
    c = cloud(env); put(env, "mine.bighat", blob(q="Q1"))
    assert run(c.cu.upload(env.db, ""))["error"] == "no_token"
    chk = run(c.cu.check(env.db)); put(env, "new.bighat", blob(q="Q9"))
    res = run(c.cu.upload(env.db, chk["token"]))
    assert res["ok"] is False and res["error"] == "changed" and c.posts == []


def test_the_run_stops_safely_when_the_cloud_dies_part_way_and_nothing_sent_is_repeated(env):
    c = cloud(env); c.mode = "die_on_2"
    for i in range(3): put(env, f"r{i}.bighat", blob(q=f"Q{i}"))
    res = run(c.cu.upload(env.db, run(c.cu.check(env.db))["token"]))
    assert res["ok"] is False and len(res["sent"]) == 1 and len(c.posts) == 1
    c.mode = "ok"
    again = run(c.cu.check(env.db)); assert again["can_upload"] == 2 and len(again["already_sent"]) == 1


def test_a_cloud_that_has_no_upload_route_yet_says_so_and_sends_nothing(env):
    c = cloud(env); c.mode = "not_ready"; put(env, "mine.bighat", blob(q="Q1"))
    res = run(c.cu.upload(env.db, run(c.cu.check(env.db))["token"]))
    assert res["ok"] is False and res["error"] == "cloud_not_ready" and "does not accept uploads" in res["message"]


def test_not_linked_and_offline_send_nothing_and_say_why(env):
    from native import cloud_link
    env.mp.setattr(cloud_link, "get_token", lambda: None)
    from native import cloud_upload
    assert run(cloud_upload.check(env.db))["error"] == "not_linked"
    c = cloud(env); c.mode = "down"
    assert run(c.cu.check(env.db))["error"] == "unreachable"


def test_the_stamped_copy_that_comes_back_is_then_offered_to_the_duplicate_check(env):
    c = cloud(env); mine = put(env, "mine.bighat", blob(q="Q1", a="A1"))
    run(c.cu.upload(env.db, run(c.cu.check(env.db))["token"]))
    put(env, "mine-from-cloud.bighat", _stamp(blob(q="Q1", a="A1"), A))                # what the next pull would file
    import round_duplicates
    d = run(round_duplicates.check(env.db))
    assert d["group_count"] == 1 and d["groups"][0]["keep"]["file"] == "mine-from-cloud.bighat" and mine.exists()


def test_the_real_http_routes(env):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    c = cloud(env)
    from native import cloud_link_router as clr
    import importlib; importlib.reload(clr)
    env.mp.setattr(clr, "_db", lambda: env.db)
    app = FastAPI(); app.include_router(clr.router); t = TestClient(app)
    mine = put(env, "mine.bighat", blob(q="Q1"))
    chk = t.post(clr.router.prefix + "/round-upload/check").json()
    assert chk["can_upload"] == 1 and c.posts == []
    assert t.post(clr.router.prefix + "/round-upload/send", json={"token": ""}).json()["error"] == "no_token"
    done = t.post(clr.router.prefix + "/round-upload/send", json={"token": chk["token"]}).json()
    assert done["ok"] and done["sent"] == ["mine.bighat"] and mine.exists()
