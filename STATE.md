# Current State

**Active phase:** 0 — Foundation (backend infra ✅ complete; frontend SetupWizard pending)

**Last completed work:** 
- Native infrastructure module shipped at `/app/backend/native/` (config, hwid, license, subscription, router)
- `/api/native/*` endpoints live and verified end-to-end
- Existing webapp regression-tested: still healthy
- ROADMAP, CHANGELOG, ERRORS up to date

**Next action (Phase 0.5):**
1. Build React `SetupWizard` page (3-step wizard: License key → Master admin → Settings/paths)
2. On `App` mount, fetch `/api/native/info`. If `native_mode === true` AND `setup_complete === false` → force redirect to `/setup`. Otherwise behave as today.
3. Add a `<NativeBadge />` indicator (top-right of dashboard when native_mode=true)
4. Wire the existing local-bcrypt login page to also accept the master admin created by setup wizard
5. Frontend smoke test: open root with `BIGHAT_NATIVE_MODE=1` → wizard appears; submit wizard → redirected to login; log in with master admin

**Then Phase 1 (Schedule module):** swap MongoDB collections (`events`, `venues`, `employees`, `claims`) to MontyDB (Mongo-compatible SQLite shim) so the data lives in `bighat.db` next to `system_config.json`.

**Blockers:** none

**Open questions:** none. User confirmed all 5 Phase-0 design questions on 2026-05-04.

**Test credentials (current state):**
- Webapp Mongo+OAuth admin: `Sellards@bighat.live` / `BigHat2024!`
- Native master admin (after wizard): `master@bighat.local` / `BigHat2024!` (test fixture; recreated each setup)
- Test license key (offline-only, well-formed): `BHE-TEST-1234-ABCD-WXYZ`

**System config file:** `/app/backend/native/system_config.json`
