"""alpha.74: .bighat files made by the BIGHat File Creator (ZIP) work everywhere in the program."""
import io, json, sys, zipfile
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from native import creator_bighat as cb

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 300


def make(name="MC_02_A", rt="MC", cid="cid-1", n=10, img=False, cover=True, extra_manifest=None, payload_extra=None):
    qs = []
    for i in range(n):
        q = {"n": i + 1, "category": "Movies", "prompt": f"{name} Q{i+1}?", "answer": "B", "points": 1,
             "options": ["A one", "B two", "C three", "D four"], "correct_index": 1, "media": {}}
        if img and i == 0:
            q["media"] = {"image": "assets/q1.png"}
        qs.append(q)
    man = {"format_version": "1.0", "content_id": cid, "created_by": "BIGHat File Creator v1.0", "type": "round",
           "round_type": rt, "round_name": name, **(extra_manifest or {})}
    pl = {"name": name, "round_type": rt, "questions": qs, **({"cover_image": "assets/cover.png"} if cover else {}), **(payload_extra or {})}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", json.dumps(man)); z.writestr("payload.json", json.dumps(pl))
        if cover: z.writestr("assets/cover.png", PNG)
        if img: z.writestr("assets/q1.png", PNG)
    return buf.getvalue()


def test_reads_a_creator_file_into_the_programs_round_shape():
    doc, why = cb.load_any(make(img=True), "MC_02_A.bighat")
    assert why == "" and doc["schema"] == "bighat-round/v1" and doc["round_type"] == "MC" and doc["name"] == "MC_02_A"
    assert doc["id"] == "cid-1" and len(doc["questions"]) == 10
    q = doc["questions"][0]
    assert q["question"] == "MC_02_A Q1?" and q["options"][1] == "B two" and q["correctOption"] == 1 and q["answer"] == "B two" and q["number"] == 1
    assert q["image_data_url"].startswith("data:image/png;base64,") and doc["cover_image_data_url"].startswith("data:image/png")


@pytest.mark.parametrize("rt", ["MC", "REG", "MISC", "MYS", "BIG"])
def test_every_round_type_is_recognised(rt):
    doc, why = cb.load_any(make(name=f"{rt}_01", rt=rt), f"{rt}__x.bighat")
    assert doc and doc["round_type"] == rt


def test_round_type_falls_back_to_the_file_name():
    doc, _ = cb.load_any(make(name="x", rt="", extra_manifest={"round_type": None}), "REG-Animals.bighat")
    assert doc and doc["round_type"] == "REG"


def test_bad_files_return_a_reason_and_never_raise():
    for blob in (b"", b"PK\x03\x04garbage", b"\x00\xff\x9e" * 50, b"hello"):
        doc, why = cb.load_any(blob, "x.bighat")
        assert doc is None and why
    bad = io.BytesIO()
    with zipfile.ZipFile(bad, "w") as z:
        z.writestr("manifest.json", "{not json"); z.writestr("payload.json", "{}")
    assert cb.load_any(bad.getvalue(), "x.bighat")[0] is None
    evil = io.BytesIO()
    with zipfile.ZipFile(evil, "w") as z:
        z.writestr("manifest.json", "{}"); z.writestr("payload.json", "{}"); z.writestr("../evil.txt", "x")
    d, why = cb.load_any(evil.getvalue(), "x.bighat")
    assert d is None and "unsafe" in why


def test_a_missing_asset_does_not_break_the_round():
    doc, why = cb.load_any(make(cover=False, payload_extra={"cover_image": "assets/nope.png"}), "MC_1.bighat")
    assert doc and "cover_image_data_url" not in doc


def test_programs_own_json_round_still_loads():
    own = json.dumps({"schema": "bighat-round/v1", "id": "x", "round_type": "MC", "name": "Mine", "questions": []}).encode()
    doc, why = cb.load_any(own, "mine.bighat")
    assert doc and doc["name"] == "Mine"


# ---- the folder reader (this is what crashed with a 500 before) ----
@pytest.fixture
def folder(tmp_path, monkeypatch):
    monkeypatch.setenv("BIGHAT_FILES_DIR", str(tmp_path / "Files"))
    monkeypatch.setenv("HOME", str(tmp_path))
    import routes.roundmaker as rm
    d = tmp_path / "Files" / "Files" / "Trivia" / "MC"
    d.mkdir(parents=True)
    monkeypatch.setattr("native.files_router._docs_root", lambda: tmp_path / "Files")
    return rm, d


def test_folder_reader_converts_a_creator_zip_and_keeps_the_original(folder):
    rm, d = folder
    (d / "MC_02_A.bighat").write_bytes(make(img=True))
    rounds = rm._read_all_disk_rounds()
    assert [r["name"] for r in rounds] == ["MC_02_A"] and len(rounds[0]["questions"]) == 10
    assert (d / "_creator_originals" / "MC_02_A.bighat").read_bytes()[:2] == b"PK"      # original kept
    assert json.loads((d / "mc-02-a.bighat").read_text())["schema"] == "bighat-round/v1"   # now the program's own JSON
    assert not (d / "MC_02_A.bighat").exists() or (d / "MC_02_A.bighat").read_bytes()[:1] == b"{"
    assert [r["name"] for r in rm._read_all_disk_rounds()] == ["MC_02_A"]                # second pass: same, no copies


def test_one_broken_file_never_breaks_the_list(folder):
    rm, d = folder
    (d / "good.bighat").write_bytes(make(name="Good", cid="g1"))
    (d / "junk.bighat").write_bytes(b"\x00\xff\x9e\x80" * 40)
    (d / "empty.bighat").write_bytes(b"")
    (d / "half.bighat").write_bytes(make(name="Half", cid="h1")[:200])
    names = sorted(r["name"] for r in rm._read_all_disk_rounds())
    assert names == ["Good"]


def test_two_rounds_with_the_same_name_are_both_kept(folder):
    rm, d = folder
    (d / "a.bighat").write_bytes(make(name="MC_01", cid="id-a"))
    (d / "b.bighat").write_bytes(make(name="MC_01", cid="id-b"))
    got = rm._read_all_disk_rounds()
    assert sorted(r["id"] for r in got) == ["id-a", "id-b"]


def test_reimporting_the_same_creator_file_gives_one_round(folder):
    rm, d = folder
    (d / "x.bighat").write_bytes(make(name="MC_09", cid="same"))
    rm._read_all_disk_rounds()
    (d / "x.bighat").write_bytes(make(name="MC_09", cid="same"))       # user uploads the same file again
    got = rm._read_all_disk_rounds()
    assert len(got) == 1 and got[0]["id"] == "same"
    assert len(list(d.glob("*.bighat"))) == 1


def test_files_tool_summary_reads_both_formats(folder):
    from native.files_router import _summarise_bighat
    rm, d = folder
    z = d / "z.bighat"; z.write_bytes(make(name="MC_03", cid="z1"))
    assert "10 questions" in _summarise_bighat(z)["summary"]
    rm._read_all_disk_rounds()
    j = d / "mc-03.bighat"
    s = _summarise_bighat(j)
    assert s["type"] == "round" and "10 questions" in s["summary"] and "Unreadable" not in s["summary"]
