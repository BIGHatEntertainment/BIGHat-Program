# Change Log

Append-only. Newest at top.

---

## 2025-07 — Phase 0 (Foundation) — backend infrastructure complete ✅

### Workspace setup
- Identified that `/app` is the live BIGHat-Fullstack webapp (10K+ LOC, MongoDB, Google OAuth, SharePoint).
- Copied V30 standalone reference to `/app/_reference/standalone_v30/` (VBS installers, license, hub_template, Rust HWID).
- Copied webapp source clone to `/app/_reference/webapp/` (read-only reference).
- Created `ROADMAP.md`, `CHANGELOG.md`, `ERRORS.md`, `STATE.md`.

### New native module: `/app/backend/native/`
Added a self-contained native-standalone infrastructure layer. Additive only —
zero changes to existing webapp behaviour.

| File | Purpose |
|------|---------|
| `__init__.py` | Public exports for `config_manager`, `is_premium_active`, `require_premium`, `generate_hwid` |
| `config.py` | Thread-safe `ConfigManager` with atomic writes; persists `system_config.json` (schema, setup_complete, paths, settings, license_status, subscription, users) |
| `hwid.py` | Pure-Python SHA-256 HWID over stable system fingerprint (mirrors V30 Rust core); env override `BIGHAT_HWID` for installer |
| `license.py` | 5-seat enforcement, `register_seat` / `release_seat`, `is_well_formed_license` (BHE-XXXX-XXXX-XXXX-XXXX) |
| `subscription.py` | `is_premium_active(feature)` + `require_premium(feature)` FastAPI dependency that 402s when subscription inactive. Premium feature flags: `sharepoint_enabled`, `story_generator_enabled`, `cloud_sync_enabled` |
| `router.py` | `/api/native/*` HTTP endpoints (info, setup status, setup initialize, setup reset, license, license/seat/{register,release}, subscription, hwid, config) |

### Modified files
- `backend/server.py` (1 additive block, 9 lines): mount native router after main `app.include_router(api_router)`. Failure to load is non-fatal (logged warning).

### Verified
- `GET /api/native/info` returns version, native_mode, setup state, license status, HWID, subscription — OK
- `GET /api/native/hwid` returns deterministic SHA-256 HWID — OK
- `GET /api/native/setup/status` returns `{setup_complete:false}` on first boot — OK
- `POST /api/native/setup/initialize` creates master admin, sets license, registers seat — OK
- `POST /api/native/setup/initialize` second call returns HTTP 409 (idempotent guard) — OK
- `POST /api/native/setup/initialize` with bad license returns HTTP 400 — OK
- `POST /api/native/subscription` flips premium flags atomically — OK
- `POST /api/native/setup/reset?confirm=RESET-NATIVE` wipes config; wrong confirm returns 400 — OK
- Existing webapp routes (`/health`, `/api/venues`, `/api/auth/me`) still respond with same status codes — OK regression
- Backend supervisor logs confirm `Native-Standalone router registered at /api/native/*`

### Known issues fixed during Phase 0
- `EmailStr` rejected `.local` TLDs (IANA reserved). Replaced with relaxed regex via `field_validator`. Master admin can now use offline emails like `master@bighat.local`. (See ERRORS.md entry 2026-05-04 06:02 P0/router.)

_Phase 0 frontend work (SetupWizard React page + login page integration) pending. Will be done in Phase 0.5 before moving to Phase 1._
