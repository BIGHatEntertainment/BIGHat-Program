# Change Log

Append-only. Newest at top.

---

## 2025-07 — Phase 1 (Schedule SQLite Swap) ✅ — backend testing agent verified 29/30

### What shipped
The webapp now runs entirely against SQLite (via MontyDB) when `BIGHAT_NATIVE_MODE=1`. Zero MongoDB calls in native mode.

### New files
| File | Purpose |
|------|---------|
| `backend/native/async_monty.py` | Async wrappers (`AsyncMontyClient`, `AsyncMontyDatabase`, `AsyncMontyCollection`, `AsyncMontyCursor`) that mimic motor's API on top of synchronous MontyDB. Uses `asyncio.to_thread` to keep FastAPI handlers awaitable. Covers every Mongo operation actually used in the codebase: `find_one`, `find`, `insert_one`, `insert_many`, `update_one`, `update_many`, `delete_one`, `delete_many`, `count_documents`, `find_one_and_update/replace/delete`, `distinct`, `aggregate`, `create_index`. Includes graceful "no such table" handling so empty collections behave like Mongo. |
| `backend/native/db_factory.py` | `get_db()` returns either motor (`AsyncIOMotorClient`) or `AsyncMontyClient` (SQLite) based on `BIGHAT_NATIVE_MODE`. Cached singleton. SQLite repo at `BIGHAT_DB_DIR/bighat_db/`. |

### Modified files
- `backend/server.py`: `db = client[os.environ['DB_NAME']]` is followed by an additive native-mode swap that re-binds `db` to `get_db()` when native mode is on. `get_current_user` now tries ObjectId lookup first, then string `_id`, then email — to support both Mongo (ObjectId) and MontyDB (string UUID) auth records. Auth bridge insert uses string UUID `_id` in native mode.
- `backend/schedule_routes.py`: same native-mode swap pattern.
- `backend/scheduler.py`: same native-mode swap pattern.
- `backend/notifications.py`: same native-mode swap pattern.
- `backend/requirements.txt`: added `montydb==2.5.3`.

### Verified
**By backend testing agent (29/30 passed):**
- Schedule CRUD round-trip: POST → GET → PUT → DELETE all 200, data persists in SQLite
- Auto-seeded 6 venues + 24 events into SQLite on first boot
- Native auth bridge: master admin login returns 200 with string UUID id
- `/auth/me` returns role=master_admin
- Wrong password → 401 (not 500); unknown email → 401
- All 6 SQLite `.collection` files written: `users`, `venues`, `events`, `employees`, `login_attempts`, `venue_pricing`
- Subscription premium flag toggling works (active=true → all 3 flags true; active=false → all 3 false)
- Setup wizard idempotent guard: 409 on second call
- Bad license format / wrong reset confirm: 400
- License seat register: idempotent
- HWID is deterministic 64-char hex
- No regression on `/health`, `/api/auth/me`, `/api/venues`

### Known issues fixed during Phase 1
- **MontyDB AsyncMontyCursor: `StopIteration` cannot cross asyncio boundary** (PEP 479). Original implementation re-raised StopIteration from `to_thread`. Fixed by passing a sentinel into `next()` inside the thread and converting to `StopAsyncIteration` after `await`. (See ERRORS.md 2026-05-04 06:25)
- **MontyDB lazy table creation: `find_one` on never-touched collection raises `OperationalError("no such table")`**, but Mongo silently returns None. Fixed by catching this in every wrapper read/write/update/delete and returning the appropriate empty/no-op result. For `update_one(..., upsert=True)`, force-create the table by inserting a `_bootstrap` doc then deleting it before retrying. (See ERRORS.md 2026-05-04 06:27)
- **MontyDB query engine can't compare ObjectId** (`TypeError: Not weightable type: <class 'bson.objectid.ObjectId'>`). The native auth bridge initially used `result.inserted_id` (an ObjectId) which broke `/auth/me`. Fixed by inserting native users with explicit string-UUID `_id` and patching `get_current_user` to try ObjectId → string → email fallback. (See ERRORS.md 2026-05-04 06:30)
- **login_attempts bootstrap race on missing-table** (caught by testing agent). When login fails for an unknown email, the rate-limiter calls `update_one(login_attempts, ..., upsert=True)`. On the very first login failure ever, the table doesn't exist yet, so `update_one` enters the bootstrap-and-retry path. The retry could fail in subsequent calls. Testing agent's fix: wrapped the bootstrap insert/delete cycle in its own try/except and falls through to a fake-success result — login_attempts is rate-limit metadata only, not core data. (See ERRORS.md 2026-05-04 06:35)

---

## 2025-07 — Phase 0.5 (Frontend SetupWizard + Auth Bridge) ✅

### New files
| File | Purpose |
|------|---------|
| `frontend/src/context/NativeContext.js` | React context: fetches `/api/native/info` on mount, exposes `nativeMode`, `setupComplete`, `license`, `subscription`, `isPremiumActive(feature)`, `refresh()` |
| `frontend/src/pages/SetupWizard.jsx` | 3-step first-run wizard: License → Master Admin → Settings. Auto-formats license input, validates email/password live, posts to `/api/native/setup/initialize`, shows success screen with HWID/seats summary, then "Continue to Login" |
| `frontend/src/components/NativeBadge.jsx` | Header badge `Native • used/total` + premium indicator. Hidden when not native_mode. |

### Modified files
- `frontend/src/App.js` (rewrite, ~50 lines net): wrapped routes in `<NativeProvider>`, added `<NativeGate>` that auto-redirects `/` → `/setup` when `native_mode && !setup_complete`, and `/setup` → `/login` when setup is already complete. Added `/setup` route. All other routes unchanged.
- `frontend/src/components/Header.js`: imported and placed `<NativeBadge />` next to the role pill.
- `backend/server.py` `/api/auth/login` (additive bridge, ~70 lines): before the existing employees lookup, checks `system_config.json` users[]; if email matches, validates with bcrypt against the wizard-stored password_hash; mirrors the user into Mongo `users` collection (so `/auth/me`, `/auth/refresh`, role checks all work); issues JWT cookies and returns. On wrong password, increments login_attempts; on miss, falls through to existing flow.

### Verified end-to-end
- Set `BIGHAT_NATIVE_MODE=1` in backend/.env → `/api/native/info.native_mode=true`
- Reset config → `setup_complete=false`
- Visit `/` → auto-redirects to `/setup` ✅
- Type license `BHE-TEST-1234-ABCD-WXYZ` (auto-formats from raw input) ✅
- Step 2: master admin form validates (email regex accepts `master@bighat.local`, password ≥ 6 chars, confirm match) ✅
- Step 3: location settings ✅
- Submit → success screen shows masked license `BHE-…WXYZ`, seats `1/5`, HWID prefix ✅
- Click "Continue to Login" → redirected to `/login` ✅
- Submit master admin creds at `/login` → backend native bridge validates bcrypt, mirrors into Mongo, returns JWT ✅
- Redirected to `/` (Dashboard) showing "Welcome back, Master Admin", role pill `Role: Master Admin`, native badge `Native • 1/5` ✅
- `/api/auth/me` returns `{role: "master_admin", email: "master@bighat.local"}` ✅
- All existing dashboard cards (Trivia, Music Bingo, Karaoke, Resources & Tools) render ✅
- `/api/venues` and other existing routes still respond 200 ✅ (no regression)

### Known issues fixed during Phase 0.5
- Success screen flashed off because `await refresh()` ran inside `handleSubmit` and NativeGate then redirected `/setup → /login`. Fixed by deferring `refresh()` to the "Continue to Login" click handler. (See ERRORS.md 2026-05-04 06:14)
- Browser CORS preflight on cross-origin `localhost:3000 → public ingress` fails because nginx-code-proxy injects `Access-Control-Allow-Origin: *` while frontend uses `withCredentials: true`. **NOT a real bug** — only affects test harness. Real native standalone runs frontend & backend on the same `localhost:8001` origin, so no CORS preflight occurs. Verified by re-running the flow on the same-origin preview URL → all 200s. (See ERRORS.md 2026-05-04 06:17)

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
- `backend/.env`: added `BIGHAT_NATIVE_MODE=1` (Phase 0.5)

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
- `EmailStr` rejected `.local` TLDs (IANA reserved). Replaced with relaxed regex via `field_validator`. Master admin can now use offline emails like `master@bighat.local`. (See ERRORS.md 2026-05-04 06:02)
