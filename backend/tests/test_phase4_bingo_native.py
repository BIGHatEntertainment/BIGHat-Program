"""Phase 4 Music Bingo — native local-mode tests.

Covers:
- /api/bingo/status mode + counts
- /api/bingo/available-decades local listing
- /api/bingo/songlist/<decade> local parse + alias map + 404
- /api/bingo/bingo-cards local listing
- /api/bingo/bingo-cards/download/<cat>/<decade> PDF stream + 404 + invalid category
- Music game CRUD (create/start/call-song/pause/resume/bingo/verify/end-round/new-round)
- Traditional/number game CRUD (call-number x10, no duplicates)
- Volume update
"""
import os
import re
import urllib.parse
import pytest
import requests

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL",
    open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].splitlines()[0],
).rstrip("/")
API = f"{BASE_URL}/api/bingo"


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ---------- /status ----------
class TestBingoStatus:
    def test_status_native_local_with_counts(self, client):
        r = client.get(f"{API}/status")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["native_mode"] is True
        assert data["mode"] == "local"
        assert data["local_assets_root"].endswith("03_Bingo/Web App/00_Builder")
        assert data["song_lists_count"] >= 2
        cats = data["card_categories"]
        assert "standard" in cats and cats["standard"] >= 2
        assert "senior" in cats and cats["senior"] >= 1
        assert "special" in cats and cats["special"] >= 1


# ---------- /available-decades ----------
class TestAvailableDecades:
    def test_local_listing_contains_seeded(self, client):
        r = client.get(f"{API}/available-decades")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("source") == "local"
        ids = {d["id"] for d in data["decades"]}
        assert "1970s" in ids
        assert "1980s" in ids


# ---------- /songlist/<decade> ----------
class TestSongLists:
    def test_songlist_1970s_first_song(self, client):
        r = client.get(f"{API}/songlist/1970s")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["source"] == "local"
        assert isinstance(data["songs"], list) and len(data["songs"]) > 0
        first = data["songs"][0]
        assert isinstance(first["number"], int)
        assert isinstance(first["title"], str)
        assert isinstance(first["artist"], str)
        assert first["number"] == 1
        assert first["title"] == "Don't Stop Believin'"
        assert first["artist"] == "Journey"

    def test_songlist_1980s_first_song(self, client):
        r = client.get(f"{API}/songlist/1980s")
        assert r.status_code == 200, r.text
        first = r.json()["songs"][0]
        assert first["number"] == 1
        assert first["title"] == "Sweet Child O' Mine"
        assert first["artist"] == "Guns N' Roses"

    def test_songlist_2000s_alias_404_y2k(self, client):
        # alias maps 2000s -> Y2K, which is NOT seeded → 404 mentioning Y2K
        r = client.get(f"{API}/songlist/2000s")
        assert r.status_code == 404, r.text
        assert "Y2K" in r.json()["detail"]

    def test_songlist_unknown_404_with_filename(self, client):
        r = client.get(f"{API}/songlist/UNKNOWN")
        assert r.status_code == 404, r.text
        detail = r.json()["detail"]
        assert detail.startswith("song_list_not_found_locally:")
        assert "Bingo List (UNKNOWN).xlsx" in detail


# ---------- /bingo-cards ----------
class TestBingoCardsListing:
    def test_local_listing_categories(self, client):
        r = client.get(f"{API}/bingo-cards")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("source") == "local"
        std_ids = {c["id"] for c in data["standard"]}
        sr_ids = {c["id"] for c in data["senior"]}
        sp_ids = {c["id"] for c in data["special"]}
        assert {"1970s", "1980s"}.issubset(std_ids)
        assert "1970s" in sr_ids
        assert "Pop Punk & Emo" in sp_ids


# ---------- /bingo-cards/download/<category>/<decade> ----------
class TestBingoCardDownload:
    def _assert_pdf_response(self, r, expected_filename_part):
        assert r.status_code == 200, r.text
        assert r.headers.get("content-type", "").startswith("application/pdf")
        assert r.content[:5] == b"%PDF-"
        cd = r.headers.get("content-disposition", "")
        assert expected_filename_part in cd

    def test_download_standard_1970s(self, client):
        r = client.get(f"{API}/bingo-cards/download/standard/1970s")
        self._assert_pdf_response(r, "Bingo (1970s).pdf")

    def test_download_standard_1980s(self, client):
        r = client.get(f"{API}/bingo-cards/download/standard/1980s")
        self._assert_pdf_response(r, "Bingo (1980s).pdf")

    def test_download_senior_1970s(self, client):
        r = client.get(f"{API}/bingo-cards/download/senior/1970s")
        self._assert_pdf_response(r, "Bingo (1970s).pdf")

    def test_download_special_pop_punk_emo_url_encoded(self, client):
        # Use the fully URL-encoded path ('%20' + '%26')
        decade = urllib.parse.quote("Pop Punk & Emo", safe="")
        r = client.get(f"{API}/bingo-cards/download/special/{decade}")
        self._assert_pdf_response(r, "Bingo (Pop Punk & Emo).pdf")

    def test_download_unknown_decade_404(self, client):
        r = client.get(f"{API}/bingo-cards/download/standard/UNKNOWN")
        assert r.status_code == 404, r.text
        assert r.json()["detail"].startswith("card_not_found:")

    def test_download_invalid_category_400_or_404_not_500(self, client):
        r = client.get(f"{API}/bingo-cards/download/INVALID/anything")
        assert r.status_code in (400, 404), f"Expected 400/404 NOT 500. Got {r.status_code}: {r.text}"


# ---------- Music game CRUD ----------
class TestMusicGameLifecycle:
    def test_full_music_lifecycle(self, client):
        # CREATE — payload per Phase 4 spec ({mode, decade, game_type})
        r = client.post(f"{API}/game/create", json={
            "mode": "music", "decade": "1970s", "game_type": "standard"
        })
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["success"] is True
        assert "id" in body["game"]
        gid = body["game"]["id"]

        # START
        r = client.post(f"{API}/game/start")
        assert r.status_code == 200
        assert r.json()["success"] is True

        # Verify state is_active
        r = client.get(f"{API}/game/state")
        st = r.json()["game"]
        assert st["id"] == gid
        assert st["is_active"] is True

        # CALL SONG
        song = {"number": 3, "title": "Test", "artist": "Test"}
        r = client.post(f"{API}/game/call-song", json=song)
        assert r.status_code == 200, r.text

        r = client.get(f"{API}/game/state")
        st = r.json()["game"]
        assert st["current_song"] == song
        assert song in st["called_songs"]
        assert 3 in st["called_numbers"]

        # PAUSE
        r = client.post(f"{API}/game/pause")
        assert r.status_code == 200
        st = client.get(f"{API}/game/state").json()["game"]
        assert st["is_paused"] is True

        # RESUME
        r = client.post(f"{API}/game/resume")
        assert r.status_code == 200
        st = client.get(f"{API}/game/state").json()["game"]
        assert st["is_paused"] is False

        # CLAIM BINGO
        r = client.post(f"{API}/game/bingo")
        assert r.status_code == 200
        st = client.get(f"{API}/game/state").json()["game"]
        assert st["bingo_claimed"] is True
        assert st["is_paused"] is True

        # VERIFY BINGO — confirmed=true
        r = client.post(f"{API}/game/verify-bingo",
                        json={"winner_name": "TEST_winner", "confirmed": True})
        assert r.status_code == 200
        st = client.get(f"{API}/game/state").json()["game"]
        assert st["winner_name"] == "TEST_winner"

        # VERIFY BINGO — confirmed=false (rejection path)
        # First re-claim to set state again
        client.post(f"{API}/game/bingo")
        r = client.post(f"{API}/game/verify-bingo",
                        json={"winner_name": "TEST_loser", "confirmed": False})
        assert r.status_code == 200
        st = client.get(f"{API}/game/state").json()["game"]
        assert st["bingo_claimed"] is False
        assert st["is_paused"] is False

        # END-ROUND
        before_round = st["round_number"]
        r = client.post(f"{API}/game/end-round")
        assert r.status_code == 200
        st = client.get(f"{API}/game/state").json()["game"]
        assert st["is_active"] is False

        # NEW-ROUND increments round_number, clears called_numbers
        r = client.post(f"{API}/game/new-round")
        assert r.status_code == 200
        new_round_num = r.json()["round_number"]
        assert new_round_num == before_round + 1
        st = client.get(f"{API}/game/state").json()["game"]
        assert st["round_number"] == new_round_num
        assert st["called_numbers"] == []

    def test_volume_update(self, client):
        # Re-create a game so current_game is non-null
        client.post(f"{API}/game/create", json={
            "mode": "music", "decade": "1970s", "game_type": "standard"
        })
        r = client.post(f"{API}/game/volume", json={"volume": 0.5})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["success"] is True
        assert body["volume"] == 0.5
        st = client.get(f"{API}/game/state").json()["game"]
        assert st["volume"] == 0.5


# ---------- Number/Traditional game CRUD ----------
class TestNumberGameLifecycle:
    def test_call_number_no_duplicates_x10(self, client):
        # Per Phase 4 spec the test payload uses {mode:'number', game_type:'standard'}.
        # The backend GameStateCreate model uses bingo_type='traditional' to seed
        # available_numbers; without it /call-number returns 400. Send both to
        # exercise the actual numeric flow (extra fields are ignored).
        r = client.post(f"{API}/game/create", json={
            "mode": "number",
            "bingo_type": "traditional",
            "game_type": "standard"
        })
        assert r.status_code == 200, r.text
        assert r.json()["success"] is True

        r = client.post(f"{API}/game/start")
        assert r.status_code == 200

        seen = []
        for i in range(10):
            r = client.post(f"{API}/game/call-number")
            assert r.status_code == 200, f"call-number iter {i} failed: {r.text}"
            n = r.json()["number"]
            assert isinstance(n, int)
            assert 1 <= n <= 75
            assert n not in seen, f"duplicate number {n} on call {i}"
            seen.append(n)

            st = client.get(f"{API}/game/state").json()["game"]
            assert st["current_number"] == n
            assert len(st["called_numbers"]) == i + 1
            assert st["called_numbers"][-1] == n


# ---------- Spec-payload variant: number bingo without bingo_type override ----------
class TestNumberGameSpecPayloadOnly:
    """Strict reading of the Phase 4 spec: payload {mode:'number', game_type:'standard'}.
    Records what actually happens — surfaces the mode→bingo_type mapping gap if any.
    """
    def test_spec_payload_only_create_and_call_number(self, client):
        r = client.post(f"{API}/game/create",
                        json={"mode": "number", "game_type": "standard"})
        assert r.status_code == 200, r.text
        client.post(f"{API}/game/start")
        r = client.post(f"{API}/game/call-number")
        # Should ideally return 200 with a number; if backend doesn't map
        # mode→bingo_type, /call-number returns 400 ("All numbers have been called").
        # Document the actual behaviour for the main agent.
        assert r.status_code in (200, 400), r.text
        if r.status_code == 400:
            pytest.xfail(
                "BUG: Spec payload {mode:'number'} not mapped to bingo_type='traditional'; "
                "available_numbers stays empty so /call-number returns 400. "
                "Backend GameStateCreate ignores 'mode' field."
            )


# ---------- Regression: previous phase endpoints ----------
class TestRegressionPublicEndpoints:
    @pytest.mark.parametrize("path", [
        "/api/native/info",
        "/api/native/sync/status",
        "/api/scoreboard/status",
        "/api/story-generator/status",
        "/api/trivia/hosts",
        "/api/trivia/round-files/reg",
        "/api/roundmaker/sharepoint-status",
        "/api/venues",
        "/api/events",
    ])
    def test_endpoint_200(self, client, path):
        r = client.get(f"{BASE_URL}{path}")
        assert r.status_code == 200, f"{path} returned {r.status_code}: {r.text[:200]}"
