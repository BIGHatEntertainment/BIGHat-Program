# Current State

**Active phase:** 3 — Round Maker (✅ complete; 58/58 tests via testing agent)

**Last completed work:**
- Phase 3 — Round Maker SQLite + local publish: 21/21 new tests + 37/37 Phase 2
  regression = **58/58 passed**. (See `/app/test_reports/iteration_4.json`,
  `/app/backend/tests/test_phase3_roundmaker_native.py`.)
- Round-maker generates PPTX locally, publishes into the local trivia round
  library, round appears immediately in `/api/trivia/round-files/<type>`.
- Title-card seed at `/app/backend/native/data/assets/01_Trivia/Web App/00_Builder/04_TitleCards/REG/`.
- `_upload_to_sharepoint_direct` and `_get_graph_token` callers now branch
  on `_is_local_mode()` so they never crash on missing Azure creds.
- Phase 0/0.5/1/2 unchanged (still verified).

**Next action:** propose Phase 4 (Music Bingo) to the user.

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
