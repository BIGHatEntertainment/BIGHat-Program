# Current State

**Active phase:** 7 — SharePoint Hybrid Sync (✅ complete; **130/130** tests via testing agent)

**Last completed work:**
- Phase 7 — SharePoint Hybrid Sync: 22/22 new tests + 108/108
  Phase 2+3+5+6 regression = **130/130 passed**
  (`/app/test_reports/iteration_8.json`,
  `/app/backend/tests/test_phase7_sync_native.py`).
- `backend/native/sync_service.py` + `sync_router.py`;
  `/api/native/sync/{status,plan,pull,push}` — plan/pull/push premium-gated
  by `cloud_sync_enabled`; status always free.
- `BIGHAT_SYNC_REMOTE_FIXTURE` env var in `/app/backend/.env` points to
  `/app/backend/native/data/cloud_fixture` for dev testing without real
  SharePoint creds.
- `db.sync_state` persists `last_pull` + `last_push` summaries.
- Phase 0/0.5/1/2/3/5/6 unchanged.

**Next action:** user to choose Phase 4 (Music Bingo — the last P1) or
Phase 8 (Admin + accumulated code-review hardening) or Phase 9 (Packaging).

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
