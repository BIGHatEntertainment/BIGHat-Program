# Current State

**Active phase:** 9 — Packaging (✅ complete; **189/189** tests via testing agent)

**Last completed work:**
- Phase 9 — Packaging & single-process launcher: 29/29 new tests +
  160/160 Phase 2+3+5+6+7+8 regression = **189/189 passed**
  (`/app/test_reports/iteration_10.json`,
  `/app/backend/tests/test_phase9_packaging.py`).
- `backend/launcher.py`, `scripts/build_standalone.py`,
  `packaging/{start_bighat.vbs,install_shortcut.vbs,README.md}`.
- SPA static-bundle serving in `server.py` (conditional on
  `backend/static/index.html`).
- Phase 8 carry-overs: `/advance` returns 404 match_not_found on
  unknown match_id; `admin_router.set_current_user_resolver` setter.
- Build orchestrator manifest preserves `frontend_included=true` on
  `--no-frontend` if bundle is on disk.
- Phase 0/0.5/1/2/3/5/6/7/8 unchanged.

**Next action:** only Phase 4 (Music Bingo — the last P1) remains on the
roadmap. After that, the native transformation is feature-complete and
shippable.

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
