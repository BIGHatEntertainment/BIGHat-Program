# Current State

**Active phase:** 4 — Music Bingo (✅ complete; **215/215** full regression)

**Last completed work:**
- Phase 4 — Music Bingo native local-mode + spec-friendly aliases:
  26/26 new + 29/29 Phase 9 retest + **215/215 full regression**
  (`/app/test_reports/iteration_12.json`,
  `/app/backend/tests/test_phase4_bingo_native.py`).
- All 9 transformation phases shipped: 0, 0.5, 1, 2, 3, 4, 5, 6, 7, 8, 9.
- `routes/bingo.py` reads songs / decade catalog / card PDFs from
  `<assets>/03_Bingo/...` in native mode; `/api/bingo/status` exposes
  mode + counts; `GameStateCreate` honours `{mode, decade}` aliases.
- Phase 9 stale assertion fixed (frontend_included preserved=True).

**Next action:** 🎉 native transformation is **feature-complete**. Only
optional P3 polish remains: frontend Settings/Diagnostics wiring, signed
Windows installer, auto-update channel, audit log, watchdog hot-reload,
hash-based sync diff. Wait for user direction.

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
