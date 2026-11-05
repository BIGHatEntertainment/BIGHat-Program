"""PR 2: duplicate round files. Real files, real MontyDB. A duplicate is only ever certain (same stamp, or identical questions+answers);
a same-NAME file is never one; nothing is deleted; a copy a saved show uses is never moved."""
import io, json, zipfile
from pathlib import Path
from test_cloud_files_pull import env, run  # noqa: F401

A = "11111111-2222-3333-4444-555555555555"
B = "99999999-2222-3333-4444-555555555555"


def blob(name="Flowers", uid=None, q="Top flower?", a="Rose", rtype="REG"):
    m = {"type": rtype, "name": name, "format_version": 1}
    if uid:
        m["round_uid"] = uid
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("manifest.json", json.dumps(m))
        z.writestr("payload.json", json.dumps({"name": name, "round_type": rtype, "questions": [{"question": q, "answer": a}]}))
    return buf.getvalue()


def put(env, fname, data, rtype="REG"):
    import presentation_builder as pb
    d = pb._round_pool_dir(rtype); d.mkdir(parents=True, exist_ok=True)
    (d / fname).write_bytes(data)
    return d / fname


def mod(env):
    import round_duplicates as rd
    return rd


def test_two_files_with_the_same_stamp_are_one_group_and_nothing_is_deleted(env):
    a = put(env, "flowers.bighat", blob(uid=A)); b = put(env, "flowers-7297fdd0.bighat", blob(uid=A))
    r = run(mod(env).check(env.db))
    assert r["group_count"] == 1 and r["copies"] == 1 and r["groups"][0]["basis"] == "same stamp"
    assert a.exists() and b.exists()


def test_identical_unstamped_files_are_a_group_but_same_name_alone_is_not(env):
    put(env, "a.bighat", blob(q="Q1", a="A1")); put(env, "a-copy.bighat", blob(q="Q1", a="A1"))
    put(env, "same-name-1.bighat", blob(name="Same", q="Different one", a="x")); put(env, "same-name-2.bighat", blob(name="Same", q="Different two", a="y"))
    r = run(mod(env).check(env.db))
    assert r["group_count"] == 1 and r["groups"][0]["basis"] == "same questions and answers"


def test_different_types_are_never_grouped(env):
    put(env, "x.bighat", blob(q="Q", a="A"), "REG"); put(env, "x.bighat", blob(q="Q", a="A", rtype="MC"), "MC")
    assert run(mod(env).check(env.db))["group_count"] == 0


def test_retire_moves_never_deletes_and_writes_a_note(env):
    keep = put(env, "flowers.bighat", blob(uid=A)); dup = put(env, "flowers-7297fdd0.bighat", blob(uid=A))
    import os; os.utime(keep, (1, 1))   # the original is older
    data = dup.read_bytes()
    rd = mod(env); chk = run(rd.check(env.db)); res = run(rd.retire(env.db, chk["token"]))
    assert res["ok"] and res["moved"] == 1 and keep.exists() and not dup.exists()
    moved = list(Path(res["folder"]).rglob("flowers-7297fdd0.bighat"))
    assert len(moved) == 1 and moved[0].read_bytes() == data and (Path(res["folder"]) / "WHAT_HAPPENED.txt").exists()


def test_a_copy_a_saved_show_points_at_is_kept_and_the_other_is_moved(env):
    import presentation_builder as pb
    a = put(env, "flowers.bighat", blob(uid=A)); b = put(env, "flowers-7297fdd0.bighat", blob(uid=A))
    rel = b.relative_to(pb._docs_root()).as_posix()
    run(env.db.presentations.insert_one({"id": "p1", "name": "Friday Show", "rounds": [{"type": "REG", "file": rel}]}))
    rd = mod(env); chk = run(rd.check(env.db))
    kept = chk["groups"][0]
    assert kept["keep"]["file"] == "flowers-7297fdd0.bighat"           # the one the show uses is the one kept
    res = run(rd.retire(env.db, chk["token"]))
    assert res["ok"] and b.exists() and not a.exists()


def test_a_file_the_lockout_tracks_by_name_is_not_moved(env):
    import round_usage
    a = put(env, "flowers.bighat", blob(q="Q", a="A")); b = put(env, "flowers-copy.bighat", blob(q="Q", a="A"))
    env.mp.setattr(round_usage, "locked_names", lambda loc: {round_usage.norm_name("flowers-copy.bighat"), round_usage.norm_name("flowers-copy")})
    rd = mod(env); chk = run(rd.check(env.db))
    assert chk["groups"][0]["keep"]["file"] == "flowers-copy.bighat"     # the copy the lockout tracks is the one kept
    res = run(rd.retire(env.db, chk["token"]))
    assert res["ok"] and b.exists() and not a.exists()                    # the locked name is never moved


def test_when_both_copies_are_locked_by_name_neither_is_moved(env):
    import round_usage
    a = put(env, "flowers.bighat", blob(q="Q", a="A")); b = put(env, "flowers-copy.bighat", blob(q="Q", a="A"))
    env.mp.setattr(round_usage, "locked_names", lambda loc: {round_usage.norm_name("flowers"), round_usage.norm_name("flowers-copy")})
    rd = mod(env); chk = run(rd.check(env.db))
    assert chk["can_retire"] == 0 and "lockout" in json.dumps(chk)
    run(rd.retire(env.db, chk["token"]))
    assert a.exists() and b.exists()


def test_retire_needs_a_fresh_matching_token_and_changes_nothing_when_stale(env):
    put(env, "flowers.bighat", blob(uid=A)); put(env, "flowers-2.bighat", blob(uid=A))
    rd = mod(env)
    assert run(rd.retire(env.db, ""))["error"] == "no_token"
    chk = run(rd.check(env.db))
    put(env, "more.bighat", blob(uid=B)); put(env, "more-2.bighat", blob(uid=B))     # the folder changed after the check
    res = run(rd.retire(env.db, chk["token"]))
    assert res["ok"] is False and res["error"] == "changed" and len(list(Path(put(env, "z.bighat", blob(q="z", a="z")).parent).glob("*.bighat"))) == 5


def test_an_unreadable_file_is_never_called_a_duplicate(env):
    put(env, "junk1.bighat", b"not a zip"); put(env, "junk2.bighat", b"not a zip")
    assert run(mod(env).check(env.db))["group_count"] == 0


def test_the_real_http_routes_check_then_retire(env):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from native import cloud_link_router as clr
    import importlib; importlib.reload(clr)
    env.mp.setattr(clr, "_db", lambda: env.db)
    app = FastAPI(); app.include_router(clr.router); c = TestClient(app)
    keep = put(env, "flowers.bighat", blob(uid=A)); dup = put(env, "flowers-7297fdd0.bighat", blob(uid=A))
    import os; os.utime(keep, (1, 1))
    chk = c.post(clr.router.prefix + "/round-duplicates/check").json()
    assert chk["group_count"] == 1 and keep.exists() and dup.exists()          # the check changed nothing
    assert c.post(clr.router.prefix + "/round-duplicates/retire", json={"token": ""}).json()["error"] == "no_token"
    done = c.post(clr.router.prefix + "/round-duplicates/retire", json={"token": chk["token"]}).json()
    assert done["ok"] and done["moved"] == 1 and keep.exists() and not dup.exists()
    assert c.post(clr.router.prefix + "/round-duplicates/check").json()["group_count"] == 0
