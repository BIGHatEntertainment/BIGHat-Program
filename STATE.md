# Current State

**Active phase:** 9.1 — Auto-Update Channel (✅ complete; **240/240** full regression)

**Last completed work:**
- Phase 9.1 — Auto-update channel: 25/25 new tests + 215/215 prior
  baseline regression = **240/240 passed**
  (`/app/test_reports/iteration_13.json`,
  `/app/backend/tests/test_phase9_1_updates_native.py`).
- New `backend/VERSION.txt`, `native/updates_service.py`,
  `native/updates_router.py`. `/api/native/updates/{status,check,download,apply}`.
- Master-admin gate on `/apply`; idempotent re-apply with `?force=true`.
- `/api/native/info` reads VERSION.txt (was hardcoded `31.0.0-phase0`).
- Launcher `--check` prints installed_ver + pending_apply marker.
- Reviewer fixes applied post-test: `manifest_fixture_missing` /
  `manifest_fixture_invalid_json` discoverable RuntimeErrors;
  `already_scheduled` 409 with `?force=true` bypass.
- All 9 phases + 9.1 shipped.

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
