# Current State

**Active phase:** 8 — Admin + Hardening (✅ complete; **160/160** tests via testing agent)

**Last completed work:**
- Phase 8 — Admin + Hardening: 30/30 new tests + 130/130 Phase
  2+3+5+6+7 regression = **160/160 passed**
  (`/app/test_reports/iteration_9.json`,
  `/app/backend/tests/test_phase8_admin_native.py`).
- New `backend/native/admin_router.py` — master-admin-only UI:
  `/api/native/admin/{users,license/seats,whoami}`. User CRUD with
  role promotion, password reset; seat rename/revoke with
  current-device protection. Master admin cannot be
  deleted/demoted/seat-revoked.
- Scoreboard hardening: `TournamentCreate` validates
  `len(teams) + bye_count == total_teams`; `/tournaments/{id}/advance`
  now takes a `TournamentAdvance` Pydantic body.
- Phase 0/0.5/1/2/3/5/6/7 unchanged.

**Next action:** user to choose Phase 4 (Music Bingo — the last P1) or
Phase 9 (Packaging + small polish carry-overs from Phase 8).

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
