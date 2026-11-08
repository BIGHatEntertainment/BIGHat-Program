"""A round's permanent ID (round_uid, stamped by the Cloud) is its identity on the PC: the same ID is one round, one file, and the stamp
survives the save. Real MontyDB, real importer, real files. An unstamped round behaves exactly as before."""
import glob, io, json, zipfile
from pathlib import Path
from test_cloud_files_pull import env, run  # noqa: F401

A = "11111111-2222-3333-4444-555555555555"
B = "99999999-2222-3333-4444-555555555555"


def rnd(name="Flowers", uid=A, q="q"):
    m = {"type": "REG", "name": name, "format_version": 1}
    if uid:
        m["round_uid"] = uid
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("manifest.json", json.dumps(m))
        z.writestr("round.json", json.dumps({"type": "REG", "name": name, "round_type": "REG",
                   "questions": [{"number": 1, "question": q, "answer": "a", "options": ["a", "b", "c", "d"], "correctOption": 0}]}))
    return buf.getvalue()


def go(env, *blobs):
    from routes import bighat_files
    bighat_files.db = env.db
    for b in blobs:
        run(bighat_files._import_zip_bytes(b))
    files = sorted(Path(p) for p in glob.glob(str(env.tmp) + "/**/Trivia/REG/*.bighat", recursive=True))
    import round_uid
    return files, [round_uid.read_uid(f) for f in files], run(env.db.rounds.count_documents({}))


def test_the_same_stamped_round_twice_is_one_file_and_keeps_its_stamp(env):
    files, uids, n = go(env, rnd(), rnd())
    assert [f.name for f in files] == ["flowers.bighat"] and uids == [A] and n == 1


def test_a_changed_cloud_copy_updates_the_one_round_in_place(env):
    files, uids, n = go(env, rnd(q="old"), rnd(q="new"))
    assert len(files) == 1 and uids == [A] and n == 1 and "new" in files[0].read_text()


def test_a_renamed_cloud_round_still_replaces_the_file_that_holds_its_stamp(env):
    files, uids, n = go(env, rnd("Flowers"), rnd("Flowers Renamed"))
    assert len(files) == 1 and uids == [A] and n == 1


def test_two_different_stamps_with_the_same_name_stay_two_rounds(env):
    files, uids, n = go(env, rnd(uid=A), rnd(uid=B))
    assert len(files) == 2 and sorted(uids) == sorted([A, B]) and n == 2


def test_unstamped_rounds_behave_exactly_as_before(env):
    files, uids, n = go(env, rnd(uid=None), rnd(uid=None))
    assert len(files) == 2 and uids == [None, None] and n == 2
