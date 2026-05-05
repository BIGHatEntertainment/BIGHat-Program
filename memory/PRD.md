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
- **2026-02** — Phase 9.3 (macOS `.app` / `.pkg` / `.dmg`): `scripts/build_dmg.py`
  mirrors the Windows orchestrator — assembles `BIG Hat Standalone.app` bundle
  (Info.plist from `packaging/macos/Info.plist.in`, MacOS launcher.sh with
  exec bit + native-mode env, Resources/{backend,packaging,VERSION.txt,python}),
  downloads + sha256-verifies relocatable CPython from
  `astral-sh/python-build-standalone` (3.11.9, `aarch64-apple-darwin` /
  `x86_64-apple-darwin`), gated `pkgbuild` + `productbuild` produce a signed
  `.pkg` with postinstall (xattr quarantine strip + per-user
  `~/Library/Application Support/BIG Hat Standalone` data dir), gated
  `hdiutil create` produces a `.dmg` with `/Applications` drag symlink,
  optional `codesign --deep --options runtime --timestamp` + `xcrun notarytool
  submit --wait` + `xcrun stapler staple`. **Cross-platform parts run on
  Linux** (so CI can stage everything except the sign+package step on a Mac
  host). Test suite `test_phase9_3_macos_packaging.py` — 15 always-on static
  + bundle-assembly tests, 1 gated full pipeline test (macOS + `BIGHAT_RUN_PKGBUILD=1`).
  Verified end-to-end on this Linux container: 2318-file `.app` bundle with
  embedded CPython, valid Info.plist, exec-bit launcher, `PkgInfo=APPLBHat`.
  **269/269 always-on tests pass** (3 gated — 2 Windows-NSIS, 1 macOS).
- **2026-02** — Phase 10.0 (Cloud Licensing Service / SaaS storefront): new
  `backend/cloud/` package gated by `BIGHAT_CLOUD_MODE=1`. Implements:
  *(a)* HMAC-verified Squarespace webhook handler (`order.create`,
  `order.update`, `subscription.cancel`) with idempotent event dedupe;
  *(b)* unified per-customer license model — one `BHE-XXXX-XXXX-XXXX-XXXX`
  key carries `owns_standalone` (lifetime $24.99) + `cloud_library_status`
  ($5/mo subscription, expires_at, auto-extend, auto-cancel);
  *(c)* `/api/license/activate` HWID binding (max 3 seats standalone, 5
  with cloud library), `/validate` (7-day cadence + 30-day offline grace),
  `/deactivate` (move-to-new-machine), `/status/{key}` (public masked view);
  *(d)* `/api/downloads/{windows|macos}` returns the configured installer
  URL + version; *(e)* admin router at `/api/license/admin/*` with JWT
  auth (mint/list/get/revoke keys); *(f)* Resend email integration with
  HTML+text templates and graceful no-op when `RESEND_API_KEY` missing.
  Storage: MongoDB collections `license_keys` + `license_webhook_events`.
  Test suite `test_phase10_0_license_server.py` — **41 in-process tests**
  covering pure helpers (key gen, masking, signature verification, payload
  parsing), service-level integration via MontyDB SQLite (mint, idempotent
  replay, sub-then-standalone unification, seat limits, validate, revoke,
  deactivate, subscription lifecycle), and FastAPI TestClient integration
  for public + admin routes (webhook → mint → activate → validate → revoke
  end-to-end). Setup runbook: `packaging/SAAS_SETUP.md`.
- **2026-02** — Phase 10.1 (Secret-leakage prevention + product naming):
  **CRITICAL FIX** to Phase 9.2/9.3 build pipelines — `_copy_tree` in
  `build_installer.py` and `build_dmg.py` now strips `.env` and any
  `.env.*` file from payloads (previously the dev `backend/.env` with all
  production secrets was being shipped to every customer machine).
  Replaced with `packaging/.env.standalone` desktop-safe template (no
  secrets, just `BIGHAT_NATIVE_MODE=1`, stub Mongo URL, placeholder JWT).
  `launcher.py:_bootstrap_env_from_template()` copies template to
  `backend/.env` on first run and substitutes a fresh per-install
  `JWT_SECRET` (256-bit hex). Launcher also force-sets
  `BIGHAT_CLOUD_MODE=0` whenever native mode is on, defending against any
  stray cloud env var enabling licensing endpoints inside the customer
  install. Added `SQUARESPACE_API_KEY` (BIGHat-Program) to
  `backend/.env` (server-side only, never ships). Renamed product to
  **"BIG Hat Entertainment"** with SKU `BHE-STANDALONE-2499` (bundles main
  hub, trivia, schedule tool, story generator, scoreboard, answer sheets);
  cloud subscription SKU `BHE-CLOUD-LIBRARY-5MO`. Test suite
  `test_phase10_1_no_secret_leakage.py` — **10 tests** that build real
  Windows/macOS payloads then **byte-grep them for the live `.env` secret
  values** (catches accidental copies under any filename) + verify
  template safety + first-run JWT generation.
- **2026-02** — Phase 10.2 (Desktop ↔ Cloud licensing wire-up): connects
  the desktop app's existing Setup Wizard + premium gates to the Phase
  10.0 cloud license server. New `backend/native/cloud_client.py` —
  async httpx wrapper (5s timeout, fail-soft on transport errors,
  tagged-dict responses) for `activate / validate / deactivate / status /
  downloads`. Three new endpoints in `native/router.py`:
  `POST /api/native/license/cloud/activate` (Setup Wizard target —
  validates key locally, calls `api.bighat.live`, mirrors authoritative
  response into `system_config.json` subscription/feature flags, registers
  HWID seat); `POST /api/native/license/cloud/validate` (7-day re-check
  — refreshes cached state on success, preserves cache on transport
  error); `POST /api/native/license/cloud/deactivate` (move-to-new-machine
  — frees seat both server-side and locally, even if cloud is unreachable).
  `is_premium_active()` extended with **30-day offline grace** —
  cloud-tier features (`cloud_sync_enabled`, `sharepoint_enabled`) honour
  the last successful cloud snapshot for `OFFLINE_GRACE_DAYS`, then
  degrade; standalone-tier (`story_generator_enabled` when
  `owns_standalone=True`) is **NEVER** network-gated so one-time
  purchasers keep features forever. `BIGHAT_LICENSE_API_BASE_URL` (default
  `https://api.bighat.live`) now ships in `.env.standalone`. Test suite
  `test_phase10_2_desktop_cloud_wireup.py` — **18 tests** covering
  cloud_client transport (200/4xx/timeout/network_error) +
  endpoint round-trips with mocked cloud + offline-grace boundary cases.
- **2026-02** — Phase 10.2.1 (Setup Wizard polish): rebuilt
  `frontend/src/pages/SetupWizard.jsx` to use the new cloud-activate
  endpoint with full state machine: `idle → verifying → success → error
  → offline`. Step 1 now collects an optional `purchase_email` (Squarespace
  order email for matching), shows a live "Verifying with bighat.live…"
  spinner, then a tier badge panel on success (✓ BIG Hat Entertainment
  lifetime / Cloud Library subscription with expiry / seats X of Y), or
  an amber "Cloud unreachable — we'll activate next time you're online"
  panel for transport errors. **"Continue offline" affordance** lets
  users complete setup even when the cloud is down — Phase 10.2's offline
  grace logic carries the rest. **"Next" is gated**: requires either
  cloud-success OR explicit offline opt-in. Branding updated to "BIG Hat
  Entertainment" throughout (header + footer + company-name default).
  Success screen now shows the verified tier badges. Full
  `data-testid` coverage on every interactive element. Visually verified
  end-to-end via Playwright screenshots: empty, filled, verifying,
  offline-fallback, Step 2 admin form. **338/338 always-on tests pass**
  (3 platform-gated; one pre-existing Phase 3 round-maker test is
  order-flaky and unrelated).

## Roadmap (P0/P1/P2 features remaining)

🎉 **All 9 phases + 9.1 (auto-update) + 9.2 (Windows installer) + 9.3 (macOS
.app/.pkg/.dmg) + 10.0 (cloud licensing / SaaS storefront) shipped — full
product-to-customer pipeline operational.**

### Optional P3 backlog
- **Phase 10.1**: Wire desktop SetupWizard to actually call
  `https://api.bighat.live/api/license/activate` in production (currently
  the desktop license code is local-stub; payloads/contracts already align).
- **Phase 10.2**: Move installer hosting from Squarespace digital downloads
  to S3 + CloudFront with signed URLs (better analytics + per-user audit).
- **Phase 10.3**: Customer Portal — let customers self-serve "deactivate
  a seat", "view receipts", "redownload installer" on bighat.live (Member
  Areas + small React widget hitting `/api/license/status/{key}`).
- **Linux native packaging** (`.deb`, `.AppImage`).
- Frontend wiring of `/api/native/admin/users` + `/api/native/sync/status`
  + `/api/scoreboard/status` + `/api/story-generator/status` +
  `/api/bingo/status` + `/api/native/updates/status` into a unified
  Settings/Diagnostics page.
- Provisioning of a real EV code-signing certificate (Windows) and an Apple
  Developer ID + notarytool keychain profile (macOS) — pipelines ready, just
  need the certs.
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
