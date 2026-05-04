# Current State

**Active phase:** 2 — Trivia Core (backend native swap ✅; full editor/presenter UI smoke-tested only via login screen)

**Last completed work:**
- Phase 1 (Schedule on SQLite) — complete and verified.
- Phase 2 partial — Trivia Core native plumbing:
  - Native GridFS shim (`/app/backend/native/gridfs_shim.py`) — drop-in
    replacement for `AsyncIOMotorGridFSBucket` against MontyDB. Slide blobs
    persist in a regular `slides_files` collection; metadata in
    `slides_metadata`.
  - `gridfs_service.GridFSService` auto-detects `AsyncMontyDatabase` and
    swaps in the native bucket.
  - Local asset service (`/app/backend/native/local_asset_service.py`) —
    file-system mirror of the small `SharePointService` API used by the
    trivia routes.
  - Asset factory (`/app/backend/native/asset_factory.py`) — picks
    `SharePointService` (when premium + `sharepoint_enabled` + cloud trivia
    source) or `LocalAssetService` (default in native mode).
  - `SharePointService.__new__` transparently returns a `LocalAssetService`
    in native+local mode → every existing `SharePointService()` call site
    auto-routes to disk without code changes.
  - `routes/trivia.py` `/rounds*`, `/round-files/{type}`, `/hosts`,
    `/locations`, `/sponsors` work in local mode by reading the conventional
    folder layout under `<assets>/01_Trivia/Web App/00_Builder/`.
- Default `paths` in `system_config.json` now use absolute paths under
  `/app/backend/native/data/` so `cwd` doesn't matter.
- Seed asset tree at `/app/backend/native/data/assets/01_Trivia/Web App/...`
  for end-to-end testing in this dev container.

**Next action (Phase 2 wrap-up):**
1. Run testing-agent backend pass on:
   - `/api/trivia/{hosts,locations,sponsors,rounds,round-files/<type>}` in
     native local mode.
   - Slide cache round-trip: `POST /api/slide-fetcher/store-all/{id}` →
     `GET /api/trivia-import/slides-metadata/{id}` → `GET .../slides/{id}`.
   - Premium toggle: subscription on/off + `settings.trivia_source` switch
     should not crash even though Azure creds are missing in dev.
   - Regression: existing schedule + login + presentations CRUD still pass.
2. After tests pass, mark Phase 2 done in CHANGELOG/ROADMAP and propose
   Phase 3 (Round Maker) to user.

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
