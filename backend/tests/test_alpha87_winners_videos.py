"""alpha.87: winners videos (1st/2nd/3rd) bundled, served with ranges, wired to slides."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi import FastAPI
from fastapi.testclient import TestClient
import native_slides as ns
from native.winners_video_router import router, _parse_range

app = FastAPI(); app.include_router(router, prefix="/api")
c = TestClient(app)
U = "/api/native/winners-video/"


def test_three_videos_served_and_others_refused():
    for p in ("1st", "2nd", "3rd"):
        r = c.get(U + p)
        assert r.status_code == 200 and r.headers["content-type"] == "video/mp4"
        assert r.content[4:8] == b"ftyp" and len(r.content) > 1_000_000
    for bad in ("4th", "place_1st", "..%2Fserver.py", "1st.mp4"):
        assert c.get(U + bad).status_code == 404


def test_range_requests():
    full = c.get(U + "2nd").content
    r = c.get(U + "2nd", headers={"Range": "bytes=0-99"})
    assert r.status_code == 206 and r.content == full[:100]
    assert r.headers["content-range"] == f"bytes 0-99/{len(full)}"
    r = c.get(U + "2nd", headers={"Range": "bytes=-50"})
    assert r.status_code == 206 and r.content == full[-50:]
    for bad in ("bytes=999999999-", "bytes=5-2", "junk", "bytes=0-1,5-6"):
        assert c.get(U + "2nd", headers={"Range": bad}).status_code == 416
    assert _parse_range("bytes=10-", 100) == (10, 99)


def test_each_place_slide_has_its_own_video_and_name_area():
    sl = ns.render_winners_section()
    by_idx = {s["metadata"]["slideIndexInRound"]: s for s in sl}
    expect = {1: "3rd", 2: "2nd", 3: "1st"}      # 3rd place slide shows 3rd video, etc.
    for idx, word in expect.items():
        s = by_idx[idx]
        assert s["metadata"]["place"] == 4 - idx
        vids = [e for e in s["elements"] if e["type"] == "video"]
        assert len(vids) == 1 and vids[0]["videoSrc"] == "/api/native/winners-video/" + word
        assert vids[0]["loop"] is False
        assert (vids[0]["width"], vids[0]["height"]) == (ns.STAGE_W, ns.STAGE_H)
        assert not [e for e in s["elements"] if e["type"] == "text"]  # video says the place


def test_falls_back_to_text_slide_if_video_file_missing(monkeypatch):
    real = ns.bundled_asset_path
    monkeypatch.setattr(ns, "bundled_asset_path",
                        lambda *a: None if "winners" in a else real(*a))
    for s in ns.render_winners_section()[1:]:
        assert [e for e in s["elements"] if e["type"] == "text"]
        assert not [e for e in s["elements"] if e["type"] == "video"]
