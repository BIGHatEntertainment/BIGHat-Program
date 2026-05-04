"""Phase 5 — Scoreboard native swap (leaderboards + tournament brackets).

Covers:
  * /scoreboard/status — mode, subscription, ffmpeg, local counts.
  * /scoreboard/sharepoint/{files,sync,file/{path}} — local-disk branch.
  * Path-traversal guard on /sharepoint/file/{file_id:path}.
  * Presets CRUD round-trip against SQLite.
  * Tournaments CRUD + bracket_state persistence + advance.
  * Premium gate (402) on exports/upload, exports/image-to-video, generate-video
    with subscription OFF; gate-passes (422) when subscription ON.
  * Regression: /native/info, /trivia/hosts, /trivia/round-files/reg,
    /roundmaker/sharepoint-status, /story-generator/status, /venues, /events.
"""

import io
import os
import struct
import zlib
import urllib.parse

import pytest
import requests
from pathlib import Path


def _load_frontend_env_url() -> str:
    env_path = Path("/app/frontend/.env")
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError("REACT_APP_BACKEND_URL not set")


BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or _load_frontend_env_url()).rstrip("/")
API = f"{BASE_URL}/api"


# ------------------------------------------------------------------ helpers --
def _png_bytes(w: int = 2, h: int = 2) -> bytes:
    """Minimal valid PNG (still used where a real file is needed)."""
    sig = b"\x89PNG\r\n\x1a\n"

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    raw = b"".join(b"\x00" + b"\x00\x00\x00" * w for _ in range(h))
    idat = zlib.compress(raw)
    return sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


@pytest.fixture(scope="module", autouse=True)
def _ensure_sub_off_at_boundaries(s):
    """Force subscription OFF at module start AND teardown."""
    off = {
        "active": False,
        "tier": "free",
        "story_generator_enabled": False,
        "cloud_sync_enabled": False,
        "sharepoint_enabled": False,
    }
    try:
        s.post(f"{API}/native/subscription", json=off, timeout=10)
    except Exception:
        pass
    yield
    try:
        s.post(f"{API}/native/subscription", json=off, timeout=10)
    except Exception:
        pass


# ====================================================================== status
class TestStatus:
    def test_status_shape_native_local(self, s):
        r = s.get(f"{API}/scoreboard/status", timeout=10)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["native_mode"] is True
        assert d["mode"] == "local"
        assert d["ffmpeg_ok"] is True
        # Subscription OFF by default
        assert d["subscription"].get("active") is False
        assert d["video_export_available"] is False
        assert d["cloud_sync_available"] is False
        # Seeded fixture
        assert d["local_scores"]["venues"] >= 1
        assert d["local_scores"]["files"] >= 1


# =============================================================== sharepoint/*
class TestSharepointLocal:
    def test_files_lists_seeded(self, s):
        r = s.get(f"{API}/scoreboard/sharepoint/files", timeout=10)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["source"] == "local"
        assert d["count"] >= 1
        ids = [f["file_id"] for f in d["files"]]
        assert "Demo Pub/2026-05-01.json" in ids

    def test_sync_writes_db(self, s):
        r = s.post(f"{API}/scoreboard/sharepoint/sync", timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["source"] == "local"
        assert d["count"] >= 1

        r2 = s.get(f"{API}/scoreboard/scores", timeout=10)
        assert r2.status_code == 200
        files = r2.json().get("files", [])
        assert any(
            f.get("file_name") == "2026-05-01.json"
            and isinstance(f.get("data"), dict)
            and f["data"].get("date") == "2026-05-01"
            and isinstance(f["data"].get("teams"), list)
            and len(f["data"]["teams"]) == 4
            for f in files
        ), f"Synced file payload missing/incomplete in {files!r}"

    def test_file_content_path_with_space(self, s):
        enc = urllib.parse.quote("Demo Pub/2026-05-01.json", safe="")
        r = s.get(f"{API}/scoreboard/sharepoint/file/{enc}", timeout=10)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("date") == "2026-05-01"
        assert d.get("event")
        assert d.get("host")
        assert isinstance(d.get("teams"), list) and len(d["teams"]) == 4

    def test_path_traversal_blocked(self, s):
        bad = urllib.parse.quote("../../etc/passwd", safe="")
        r = s.get(f"{API}/scoreboard/sharepoint/file/{bad}", timeout=10)
        assert r.status_code in (400, 404), (
            f"Expected 400/404 for path traversal, got {r.status_code}: {r.text}"
        )


# ===================================================================== presets
class TestPresetsCRUD:
    def test_roundtrip(self, s):
        payload = {
            "name": "TEST_phase5_preset",
            "mode": "leaderboard",
            "aspect_ratio": "landscape",
            "animation_speed": 1.25,
            "config": {"theme": "neon"},
        }
        r = s.post(f"{API}/scoreboard/presets", json=payload, timeout=10)
        assert r.status_code == 200, r.text
        created = r.json()
        pid = created["id"]
        assert created["name"] == payload["name"]

        try:
            r2 = s.get(f"{API}/scoreboard/presets", timeout=10)
            assert r2.status_code == 200
            assert any(p["id"] == pid for p in r2.json()["presets"])

            r3 = s.get(f"{API}/scoreboard/presets/{pid}", timeout=10)
            assert r3.status_code == 200
            assert r3.json()["name"] == payload["name"]

            updated = dict(payload, name="TEST_phase5_preset_v2", animation_speed=2.0)
            r4 = s.put(
                f"{API}/scoreboard/presets/{pid}", json=updated, timeout=10
            )
            assert r4.status_code == 200
            assert r4.json()["name"] == "TEST_phase5_preset_v2"
            assert r4.json()["animation_speed"] == 2.0
        finally:
            r5 = s.delete(f"{API}/scoreboard/presets/{pid}", timeout=10)
            assert r5.status_code == 200
            r6 = s.get(f"{API}/scoreboard/presets/{pid}", timeout=10)
            assert r6.status_code == 404


# ================================================================= tournaments
class TestTournamentsCRUD:
    def test_roundtrip_and_advance(self, s):
        payload = {
            "name": "TEST_phase5_tournament",
            "total_teams": 4,
            "bye_count": 0,
            "teams": [
                {"seed": 1, "name": "Alpha"},
                {"seed": 2, "name": "Bravo"},
                {"seed": 3, "name": "Charlie"},
                {"seed": 4, "name": "Delta"},
            ],
            "bracket_state": {
                "matches": {
                    "r1m1": {"a": 1, "b": 4, "completed": False},
                    "r1m2": {"a": 2, "b": 3, "completed": False},
                }
            },
        }
        r = s.post(f"{API}/scoreboard/tournaments", json=payload, timeout=10)
        assert r.status_code == 200, r.text
        tid = r.json()["id"]

        try:
            # GET list + single
            r2 = s.get(f"{API}/scoreboard/tournaments", timeout=10)
            assert r2.status_code == 200
            assert any(t["id"] == tid for t in r2.json()["tournaments"])

            r3 = s.get(f"{API}/scoreboard/tournaments/{tid}", timeout=10)
            assert r3.status_code == 200
            assert r3.json()["bracket_state"]["matches"]["r1m1"]["a"] == 1

            # PUT — update teams + bracket_state
            upd_teams = payload["teams"] + [{"seed": 5, "name": "Echo"}]
            upd_bracket = {
                "matches": {
                    "r1m1": {"a": 1, "b": 4, "completed": True, "winner_seed": 1},
                    "r1m2": {"a": 2, "b": 3, "completed": False},
                }
            }
            r4 = s.put(
                f"{API}/scoreboard/tournaments/{tid}",
                json={"teams": upd_teams, "bracket_state": upd_bracket},
                timeout=10,
            )
            assert r4.status_code == 200
            got = r4.json()
            assert len(got["teams"]) == 5
            assert got["bracket_state"]["matches"]["r1m1"]["winner_seed"] == 1

            # Re-GET to confirm persistence
            r5 = s.get(f"{API}/scoreboard/tournaments/{tid}", timeout=10)
            assert r5.status_code == 200
            assert r5.json()["bracket_state"]["matches"]["r1m1"]["completed"] is True

            # POST advance — body per implementation: match_id + winner_seed
            r6 = s.post(
                f"{API}/scoreboard/tournaments/{tid}/advance",
                json={
                    "round": 1,
                    "winners": [1, 2],
                    "match_id": "r1m2",
                    "winner_seed": 2,
                    "score_a": 21,
                    "score_b": 18,
                },
                timeout=10,
            )
            assert r6.status_code == 200, r6.text
            adv = r6.json()
            assert adv["bracket_state"]["matches"]["r1m2"]["winner_seed"] == 2
            assert adv["bracket_state"]["matches"]["r1m2"]["completed"] is True
        finally:
            r7 = s.delete(f"{API}/scoreboard/tournaments/{tid}", timeout=10)
            assert r7.status_code == 200
            r8 = s.get(f"{API}/scoreboard/tournaments/{tid}", timeout=10)
            assert r8.status_code == 404


# ================================================================= premium gate
class TestPremiumGateOff:
    """Subscription OFF (default) — mutating export endpoints must 402."""

    def test_generate_video_empty_body_402(self, s):
        r = s.post(
            f"{API}/scoreboard/generate-video",
            json={},
            timeout=10,
        )
        assert r.status_code == 402, f"{r.status_code} {r.text}"
        d = r.json().get("detail", {})
        assert d.get("error") == "premium_required"
        assert d.get("feature") == "story_generator_enabled"

    def test_exports_upload_402(self, s):
        # Use a fresh session w/o JSON header to send multipart.
        files = {"file": ("tiny.png", _png_bytes(), "image/png")}
        r = requests.post(
            f"{API}/scoreboard/exports/upload", files=files, timeout=15
        )
        assert r.status_code == 402, f"{r.status_code} {r.text}"
        d = r.json().get("detail", {})
        assert d.get("error") == "premium_required"
        assert d.get("feature") == "story_generator_enabled"

    def test_image_to_video_402(self, s):
        files = {"file": ("tiny.png", _png_bytes(), "image/png")}
        r = requests.post(
            f"{API}/scoreboard/exports/image-to-video",
            files=files,
            data={"duration": 2},
            timeout=15,
        )
        assert r.status_code == 402, f"{r.status_code} {r.text}"
        d = r.json().get("detail", {})
        assert d.get("error") == "premium_required"
        assert d.get("feature") == "story_generator_enabled"


class TestReadsStillWorkOff:
    @pytest.mark.parametrize(
        "path",
        [
            "/scoreboard/scores",
            "/scoreboard/tournaments",
            "/scoreboard/presets",
            "/scoreboard/status",
        ],
    )
    def test_read(self, s, path):
        r = s.get(f"{API}{path}", timeout=10)
        assert r.status_code == 200, f"{path} -> {r.status_code} {r.text}"


class TestPremiumGateOn:
    """Flip subscription ON, confirm gates pass (422 for missing body/file)."""

    def test_toggle_cycle(self, s):
        on = {
            "active": True,
            "tier": "premium",
            "story_generator_enabled": True,
            "cloud_sync_enabled": True,
        }
        r = s.post(f"{API}/native/subscription", json=on, timeout=10)
        assert r.status_code == 200, r.text

        try:
            # generate-video missing body -> 422, NOT 402
            r1 = s.post(
                f"{API}/scoreboard/generate-video",
                data=b"",  # empty body, no JSON
                headers={"Content-Type": "application/json"},
                timeout=10,
            )
            assert r1.status_code == 422, f"{r1.status_code} {r1.text}"

            # exports/upload without file -> 422
            r2 = requests.post(
                f"{API}/scoreboard/exports/upload", timeout=10
            )
            assert r2.status_code == 422, f"{r2.status_code} {r2.text}"

            # status reports availability
            r3 = s.get(f"{API}/scoreboard/status", timeout=10)
            assert r3.status_code == 200
            d = r3.json()
            assert d["video_export_available"] is True
            assert d["cloud_sync_available"] is True
        finally:
            off = {
                "active": False,
                "tier": "free",
                "story_generator_enabled": False,
                "cloud_sync_enabled": False,
                "sharepoint_enabled": False,
            }
            r4 = s.post(f"{API}/native/subscription", json=off, timeout=10)
            assert r4.status_code == 200


# ==================================================================== regression
class TestRegression:
    @pytest.mark.parametrize(
        "path",
        [
            "/native/info",
            "/trivia/hosts",
            "/trivia/round-files/reg",
            "/roundmaker/sharepoint-status",
            "/story-generator/status",
            "/venues",
            "/events",
        ],
    )
    def test_read_200(self, s, path):
        r = s.get(f"{API}{path}", timeout=15)
        assert r.status_code == 200, f"{path} -> {r.status_code} {r.text[:200]}"

    def test_roundmaker_reports_local(self, s):
        r = s.get(f"{API}/roundmaker/sharepoint-status", timeout=10)
        assert r.status_code == 200
        d = r.json()
        assert d.get("mode") == "local", f"expected mode=local got {d!r}"

    def test_story_generator_unavailable_sub_off(self, s):
        r = s.get(f"{API}/story-generator/status", timeout=10)
        assert r.status_code == 200
        d = r.json()
        assert d.get("available") is False, f"expected available=false got {d!r}"
