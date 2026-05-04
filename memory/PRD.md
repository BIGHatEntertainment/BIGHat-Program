# BIG Hat Standalone V31 — Product Requirements

## Original Problem Statement
Convert the existing BIG Hat Hub full-stack web application (React + FastAPI
+ MongoDB) into a standalone native Windows program — "BIG Hat Standalone
V31" — with full feature parity to the webapp, while gating premium-only
features behind an active subscription.

### Hard requirements (from user)
1. **Full port** of every existing feature (Schedule, Trivia, Round Maker,
   Music Bingo, Scoreboard, Story Generator, Admin) into the native build.
2. **Hybrid frontend** — React stays the primary UI, served as static assets
   by the FastAPI process at the same `localhost` origin (no separate dev
   server needed at runtime).
3. **Local-first architecture.** All data and assets live on the local
   machine. Optional **SharePoint sync** is allowed only when the user is
   online AND has an active premium subscription with `sharepoint_enabled`.
4. **Multi-tier auth.** Local Master Admin (created by the first-run setup
   wizard) plus regular Admin and Host roles. JWT sessions; bcrypt password
   hashing. Optional Google OAuth retained as a cloud-mode toggle for the
   webapp.
5. **Local SQLite database** instead of MongoDB. The 10K+ LOC of existing
   Mongo queries should not be rewritten — use a Mongo-compatible shim.

## User personas
- **Master Admin** — owns the install, manages license seats, promotes
  Admins. One per machine.
- **Admin** — manages venues, events, hosts, content libraries.
- **Host** — runs trivia/bingo/karaoke nights from this machine; sees only
  their assigned events and content.

## Architecture (transform-in-place)
- **No rewrite.** All ~10K LOC of webapp logic stays. We layer native infra
  underneath: `db_factory`, `asset_factory`, `gridfs_shim`,
  `local_asset_service`, native router (`/api/native/*`).
- **MontyDB** = MongoDB-compatible API on top of SQLite. `AsyncMontyClient`
  wraps it with async semantics matching `motor.motor_asyncio` so existing
  routes call `await db.col.find_one(...)` unchanged.
- **`SharePointService.__new__` swap** — every existing `SharePointService()`
  call site auto-routes to `LocalAssetService` in native+local mode.
- **Setup wizard** (`/setup`) runs on first boot when
  `BIGHAT_NATIVE_MODE=1 && setup_complete=false`.
- **Premium gate** — `is_premium_active(feature)` in
  `backend/native/subscription.py`; `require_premium("feature_name")`
  FastAPI dependency returns HTTP 402 when subscription is inactive.

## Data flow
- **DB:** `BIGHAT_NATIVE_MODE=1` → `AsyncMontyClient` → SQLite at
  `/app/backend/native/data/bighat_db/test_database/*.collection`. All
  MongoDB calls in routes work unchanged.
- **Assets:** `paths.assets` (default `/app/backend/native/data/assets`) →
  served by `LocalAssetService` mirror of the SharePoint Graph API.
- **Slide cache (GridFS):** `NativeGridFSBucket` stores blobs base64-encoded
  in a `slides_files` MontyDB collection; metadata in `slides_metadata`.

## Implemented (with dates)
- **2025-07** — Phase 0 (Foundation): `/api/native/*` router, license/HWID,
  subscription, atomic `system_config.json`.
- **2025-07** — Phase 0.5 (Frontend SetupWizard + Auth Bridge).
- **2025-07** — Phase 1 (Schedule SQLite Swap). Testing agent: 29/30.
- **2026-02** — Phase 2 (Trivia Core SQLite Swap). Testing agent: 37/37.
- **2026-02** — Phase 3 (Round Maker SQLite + Local Publish). Testing
  agent: 21/21 + 37/37 regression = 58/58.
- **2026-02** — Phase 6 (Story Generator Premium Gate): `feature_gate.py`,
  `/api/story-generator/status`, 8 mutating endpoints gated. Testing
  agent: 26/26 + 58/58 regression = 84/84.
- **2026-02** — Phase 5 (Scoreboard: Leaderboards + Tournament Brackets):
  local disk score sync, SQLite presets + tournaments, video-export
  premium gate, `/api/scoreboard/status`, path-traversal guard, F821 fix
  on `/exports/upload`. Testing agent: 24/24 + 84/84 regression = 108/108.
- **2026-02** — Phase 7 (SharePoint Hybrid Sync): `SyncService` engine,
  `/api/native/sync/{status,plan,pull,push}`, premium-gated by
  `cloud_sync_enabled`, MontyDB `sync_state` persistence, dev fixture via
  `BIGHAT_SYNC_REMOTE_FIXTURE`. Testing agent: 22/22 + 108/108 regression
  = 130/130.
- **2026-02** — Phase 8 (Admin + Hardening): `/api/native/admin/{users,
  license/seats,whoami}`, master-admin-only JWT gate, user CRUD + role
  promotion + password reset, seat rename + revoke, `TournamentCreate`
  `len(teams)+bye_count==total_teams` validation, `TournamentAdvance`
  Pydantic body. Testing agent: 30/30 + 130/130 regression = 160/160.
- **2026-02** — Phase 9 (Packaging & Single-Process Launcher):
  `backend/launcher.py` + SPA static-bundle serving in FastAPI,
  `scripts/build_standalone.py` build orchestrator, Windows VBS
  installer templates, `packaging/README.md` distribution runbook,
  Phase 8 polish carry-overs (`/advance` 404 match_not_found,
  admin_router `set_current_user_resolver`). Testing agent: 29/29 +
  160/160 regression = 189/189.
- **2026-02** — Phase 4 (Music Bingo Native + Spec-Friendly Aliases):
  song lists / decade catalog / card PDFs from disk, `/api/bingo/status`,
  `GameStateCreate` accepts `{mode, decade}` aliases. Testing agent:
  26/26 + 29/29 Phase 9 retest + full regression 215/215.
- **2026-02** — Phase 9.1 (Auto-Update Channel): `/api/native/updates/{status,check,download,apply}`,
  `backend/VERSION.txt` source-of-truth, manifest fetch + sha256
  verify + staged apply with master-admin gate, dev fixture via
  `BIGHAT_UPDATE_MANIFEST_FIXTURE`, idempotent apply with `?force=true`
  override, launcher `--check` prints pending_apply marker. Testing
  agent: **25/25 + 215/215 regression = 240/240**.
- **2026-02** — Phase 9.2 (Signed NSIS Windows installer): `scripts/build_installer.py`
  one-shot orchestrator (assemble payload → download embeddable CPython 3.11.9
  pinned by sha256 → run `makensis` → optional Authenticode signing via
  `osslsigncode` / `signtool`), `packaging/installer/bighat-installer.nsi`
  with Welcome / Directory / Components / InstFiles / Finish pages,
  upgrade detection + auto-migration of `backend\data\` from prior installs,
  Programs-and-Features uninstall registration, optional Desktop / Start Menu /
  Auto-start sections, end-user gets a single self-contained `.exe` (~35 MB
  with embedded Python). Test suite `test_phase9_2_installer.py` — 14 fast
  static + payload tests always-on, 2 gated full-compile + signing tests
  (`BIGHAT_RUN_MAKENSIS=1`). Verified: makensis 0 warnings, full build
  produces 35 MB `.exe`, osslsigncode self-signed sign + verify pipeline OK.
  **254/254 tests pass (252 default + 2 gated).**

## Roadmap (P0/P1/P2 features remaining)

🎉 **All 9 phases + 9.1 + 9.2 shipped — native transformation + Windows
distribution feature-complete.**

### Optional P3 backlog
- **macOS native packaging** (`.dmg` via `pkgbuild` / `productbuild`) — next up.
- **Linux native packaging** (`.deb`, `.AppImage`).
- Frontend wiring of `/api/native/admin/users` + `/api/native/sync/status`
  + `/api/scoreboard/status` + `/api/story-generator/status` +
  `/api/bingo/status` + `/api/native/updates/status` into a unified
  Settings/Diagnostics page.
- Provisioning of a real EV code-signing certificate to remove SmartScreen
  warnings (signing pipeline already in place; just needs the cert).
- Audit-log collection for admin actions.
- Hash-based diff mode for `SyncService` (opt-in).
- Watchdog auto-refresh on local trivia/bingo asset folder changes.
- Move `/api/native/updates/{check,download}` behind master-admin
  (Phase 9.1 reviewer DoS concern).
- Pre-release tag-aware `parse_version` if pre-release update channel ever
  goes live.

## Test credentials
See `/app/memory/test_credentials.md`. Native master admin:
`master@bighat.local` / `BigHat2024!`. Test license: `BHE-TEST-1234-ABCD-WXYZ`.

## Next agent — start here
1. Read `/app/STATE.md` for the most recent in-flight context.
2. Pick the next phase from the roadmap (currently **Phase 3 — Round Maker**).
3. Follow `/app/CHANGELOG.md` for the as-shipped record of every prior phase.
4. Open issues / known gaps live in `/app/ERRORS.md`.
