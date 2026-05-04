# Current State

**Active phase:** 2 — Trivia Core (backend native swap ✅; full editor/presenter UI smoke-tested only via login screen)

**Last completed work:**
- Phase 2 — Trivia Core SQLite swap: backend testing agent **37/37 passed**.
  (See `/app/test_reports/iteration_3.json` and
  `/app/backend/tests/test_phase2_trivia_native.py`.)
- Phase 1 (Schedule on SQLite) — complete and verified.
- Phase 2 ships:
  - Native GridFS shim (`/app/backend/native/gridfs_shim.py`).
  - `gridfs_service.GridFSService` auto-detects `AsyncMontyDatabase` and
    swaps in the native bucket.
  - Local asset service (`/app/backend/native/local_asset_service.py`).
  - Asset factory (`/app/backend/native/asset_factory.py`).
  - `SharePointService.__new__` transparently returns a `LocalAssetService`
    in native+local mode.
  - `routes/trivia.py` `/rounds*`, `/round-files/{type}`, `/hosts`,
    `/locations`, `/sponsors` work in local mode.
- Default `paths` in `system_config.json` use absolute paths under
  `/app/backend/native/data/`.

**Next action:** propose Phase 3 (Round Maker) to the user.

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
