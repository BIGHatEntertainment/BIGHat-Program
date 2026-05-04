# Current State

**Active phase:** 6 — Story Generator Premium Gate (✅ complete; 84/84 tests via testing agent)

**Last completed work:**
- Phase 6 — Story Generator premium gate: 26/26 new tests + 58/58 Phase 2+3
  regression = **84/84 passed** (`/app/test_reports/iteration_6.json`,
  `/app/backend/tests/test_phase6_story_generator_native.py`).
- New `backend/native/feature_gate.py` — `require_native_premium(feature)`
  dependency, reusable for Phase 7/8.
- 8 mutating story-generator endpoints now gated; read endpoints stay free;
  `/api/story-generator/status` exposes `{available, mode, reason,
  subscription, ffmpeg_ok}` for the UI.
- Gate import tightened to `except ImportError` with ERROR-level logging.
- Phase 0/0.5/1/2/3 unchanged (all still verified).

**Next action:** user to choose Phase 4 (Music Bingo), Phase 7 (SharePoint
Hybrid Sync — unlocks the new `feature_gate.py` machinery), or Phase 8
(Admin + hardening).

**Then Phase 3 (Round Maker):** swap PPTX-round generator service to use the
asset factory + MontyDB, and route generated rounds back into the native
`local_trivia` folder.

**Blockers:** none.

**Open questions:**
- Phase 2 deferred items the user hasn't pushed back on yet:
  - Real PPTX-to-image conversion in native mode for the Presenter view
    (currently `routes/slide_fetcher.py` still calls
    `hybrid_pptx_converter.get_hybrid_converter()`; in local mode it can
    convert from disk fine, but we have only zero-byte placeholder pptx
    files in the dev seed).
  - Cloud-library upgrade flow (premium + `trivia_source=cloud`) needs Azure
    credentials in `.env` to actually fetch — out of scope until Phase 7.

**Test credentials (current state):**
- Native master admin: `master@bighat.local` / `BigHat2024!`
- Test license key: `BHE-TEST-1234-ABCD-WXYZ`
- Webapp Mongo+OAuth admin (only when `BIGHAT_NATIVE_MODE=0`): `Sellards@bighat.live` / `BigHat2024!`

**System config file:** `/app/backend/native/system_config.json`
**Asset root (native):** `/app/backend/native/data/assets`
**SQLite DB dir (native):** `/app/backend/native/data/bighat_db/test_database`
