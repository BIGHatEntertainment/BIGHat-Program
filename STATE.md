# Current State

**Active phase:** 5 — Scoreboard (✅ complete; **108/108** tests via testing agent)

**Last completed work:**
- Phase 5 — Scoreboard leaderboards + tournament brackets native swap:
  24/24 new tests + 84/84 Phase 2+3+6 regression = **108/108 passed**
  (`/app/test_reports/iteration_7.json`,
  `/app/backend/tests/test_phase5_scoreboard_native.py`).
- New `/api/scoreboard/status`; SharePoint score-sync branches to disk
  in native mode; `/exports/*` + `/generate-video` gated by
  `story_generator_enabled`; path-traversal guard on `/sharepoint/file`;
  pre-existing F821 in `/exports/upload` fixed.
- `_cloud_sync_gate` wired in scoreboard.py, ready for Phase 7 reuse.
- Phase 0/0.5/1/2/3/6 unchanged.

**Next action:** user to choose Phase 4 (Music Bingo), Phase 7 (SharePoint
Hybrid Sync — `_cloud_sync_gate` and `can_use_cloud()` are already wired),
or Phase 8 (Admin + the accumulated code-review hardening items).

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
