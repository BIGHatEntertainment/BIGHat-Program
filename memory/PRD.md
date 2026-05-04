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
- **2025-07** — Phase 0.5 (Frontend SetupWizard + Auth Bridge): React
  `SetupWizard`, `NativeBadge`, `NativeContext`, native auth bridge in
  `/api/auth/login`.
- **2025-07** — Phase 1 (Schedule SQLite Swap): `db_factory`, `async_monty`,
  schedule routes on SQLite. Backend testing agent: 29/30 passed.
- **2026-02** — Phase 2 (Trivia Core SQLite Swap): GridFS shim, local asset
  service, asset factory, SharePointService new swap, trivia route local
  short-circuits. Backend testing agent: **37/37 passed**.
- **2026-02** — Phase 3 (Round Maker SQLite + Local Publish): native PPTX
  publish into local trivia library, REG title cards from disk,
  `/sharepoint-status` mode=local. Backend testing agent: **21/21 +
  37/37 regression = 58/58 passed**.

## Roadmap (P0/P1/P2 features remaining)
- **P1 — Phase 4: Music Bingo** (lobby + host + audience views, full game engine)
- **P1 — Phase 5: Scoreboard** (leaderboard + tournament brackets)
- **P2 — Phase 6: Story Generator** (FFmpeg pipeline, premium-gated)
- **P2 — Phase 7: SharePoint Hybrid Sync** (premium-gated pull/push)
- **P2 — Phase 8: Admin** (user mgmt, license seats, sub-admin promotion)
- **P3 — Phase 9: Packaging** (VBS installers, native launcher, build script)

## Test credentials
See `/app/memory/test_credentials.md`. Native master admin:
`master@bighat.local` / `BigHat2024!`. Test license: `BHE-TEST-1234-ABCD-WXYZ`.

## Next agent — start here
1. Read `/app/STATE.md` for the most recent in-flight context.
2. Pick the next phase from the roadmap (currently **Phase 3 — Round Maker**).
3. Follow `/app/CHANGELOG.md` for the as-shipped record of every prior phase.
4. Open issues / known gaps live in `/app/ERRORS.md`.
