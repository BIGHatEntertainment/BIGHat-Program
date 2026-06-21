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
- **2026-06-21** — **v31.0.15: Blank-window root cause + ESLint guardrails**
  (`<Cloud />` icon referenced in `SetupWizard.jsx` without being
  imported → `Uncaught ReferenceError` on React mount, fully blanking
  the customer window). Root cause was deeper: `frontend/craco.config.js`
  had overridden CRA's ESLint to ONLY load `react-hooks/recommended`,
  silently dropping `no-undef` and `react/jsx-no-undef`. Fixed the
  import, hoisted a same-class `locationName` bug in
  `PresentationMode.jsx`, pinned `no-undef` + `react/jsx-no-undef` as
  hard ESLint errors in `craco.config.js`, and added
  `backend/tests/test_frontend_no_undef.py` regression guard that
  self-verifies on a missing import. NSIS installer now wipes
  `backend/static/` before laying down the new bundle so stale hashed
  JS files no longer accumulate across upgrades.
- **2026-06-21** — **v32.0.0 scaffold (in progress): Tauri native shell**
  User direction: LYRX-style fully chromeless desktop window, no
  browser, no tabs. Scaffold landed: `src-tauri/` Rust+Tauri 2.x
  project (Cargo.toml, tauri.conf.json, src/lib.rs + main.rs,
  capabilities/default.json, icon set), `splash.html` in
  `frontend/public/`, `.github/workflows/release.yml` builds on
  `windows-latest` + `macos-13` (Intel) + `macos-14` (Apple Silicon)
  via `tauri-apps/tauri-action`, and `scripts/build_sidecar.py`
  freezes `backend/launcher.py` into a PyInstaller sidecar per
  Rust target triple. Drops the VBS launcher entirely in v32.0.0.

## Implemented (earlier)
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
  offline-fallback, Step 2 admin form.
- **2026-02** — Phase 10.4 (Modular pricing model — Music Bingo + Karaoke
  add-ons): final pricing locked in for launch. **BIG Hat Entertainment
  base ($49.99 one-time, SKU `BHE-STANDALONE`)** bundles Main Hub +
  Trivia + Schedule + Story Generator + Scoreboard + Answer Sheets.
  **Music Bingo add-on ($24.99 one-time, SKU `BHE-MUSIC-BINGO`)** unlocks
  the Music Bingo event app + Bingo Story generator. **Karaoke add-on
  ($24.99 one-time, SKU `BHE-KARAOKE`)** unlocks Karaoke event app +
  Karaoke Story generator. **Cloud Library subscription ($5/mo, SKU
  `BHE-CLOUD-LIBRARY`)** stays untouched. SKUs are now **price-decoupled**
  (you can change Squarespace prices anytime without rebuilding installers).
  All add-ons require the standalone base to function — desktop gates
  enforce this with an `(owns_standalone AND owns_addon)` AND check.
  Add-ons inherit the base license's HWID seat count (3 standard, 5 with
  Cloud Library). New cloud method `mint_addon_purchase(addon, email,
  order_id)` (idempotent, supports both addons + customer who buys add-on
  before base). Webhook dispatcher recognises all 4 SKUs in one order.
  `LicenseKey` model gains `owns_music_bingo`, `owns_karaoke`,
  `squarespace_music_bingo_order_id`, `squarespace_karaoke_order_id`.
  Email template lists all owned tiers as bullets. Native subscription
  module gains `STANDALONE_FEATURES` map (4 new flags:
  `music_bingo_enabled`, `karaoke_enabled`, `bingo_story_enabled`,
  `karaoke_story_enabled`) with **legacy backward-compat** — pre-Phase
  10.4 subscriptions without `owns_standalone` key fall back to honouring
  raw feature flags so existing installs don't break. Frontend
  `AppCards.js` rebuilt: dynamic Owned/Locked states per app, "🛒 Add
  Music Bingo for $24.99" upsell buttons that open
  `bighat.live/shop/music-bingo` in new tab, "Activate BIG Hat
  Entertainment first to use add-ons" guidance for customers without
  base. Test suite `test_phase10_4_addons.py` — **15 tests** (SKU
  cleanliness audit, mint flows, idempotency, all-four-SKU order webhook,
  add-on-without-base, ownership AND gating, offline-grace immunity,
  cloud→local feature-flag mirror). Visually verified: 3-tile dashboard
  with locked badges + clear next-step CTAs. **353/353 always-on tests
  pass** (3 platform-gated).

## Roadmap (P0/P1/P2 features remaining)

🎉 **All 9 phases + 9.1 (auto-update) + 9.2 (Windows installer) + 9.3 (macOS
.app/.pkg/.dmg) + 10.0 (cloud licensing / SaaS storefront) shipped — full
product-to-customer pipeline operational.**

### v32.0.0 — Tauri native shell (CURRENT FOCUS, 2026-06-21)

**User direction (locked):** the app must launch from a desktop icon
into a single chromeless window with NO browser chrome, NO tabs, NO
URL bar — LYRX karaoke software is the visual reference. The browser
+ VBS launcher era ends with v32.0.0.

**Status:**
- ✅ Scaffold landed: `src-tauri/` (Tauri 2.x Rust project), icons,
  capabilities, splash.html, sidecar packaging spec.
- ✅ GitHub Actions workflow `.github/workflows/release.yml` builds on
  `windows-latest`, `macos-13` (Intel), `macos-14` (Apple Silicon).
  Trigger: push tag `v32.*` OR manual `workflow_dispatch`.
- ✅ `scripts/build_sidecar.py` — PyInstaller freezer for the backend.
- ⏳ First end-to-end CI build (requires user to push to GitHub +
  enable Actions).
- ⏳ Apple Developer ID signing + notarization for the macOS DMG
  (avoids Gatekeeper warning). Secrets `APPLE_CERTIFICATE`,
  `APPLE_ID`, `APPLE_PASSWORD`, `APPLE_TEAM_ID` need to land in the
  repo's Actions secrets.
- ⏳ Code-sign the Windows NSIS installer (`BIGHAT_SIGNING_CERT_PFX` +
  `BIGHAT_SIGNING_PASSWORD` already supported by the legacy script;
  needs wiring into the Tauri Actions workflow).
- ⏳ Custom title bar (LYRX-style, fully chromeless) — Phase 2 polish
  after the basic shell works. Current Tauri scaffold uses
  `decorations: true` (clean Windows chrome) to keep the first build
  predictable.
- ⏳ `.bighat` file association registers `BIGHatEntertainment.exe %1`
  with the Tauri shell argv-forwarding logic (already present in
  `src-tauri/src/lib.rs::extract_open_file_arg`).
- ⏳ Migrator: detect v31.x install dir on first v32.0.0 launch,
  prompt to uninstall v31.x cleanly, copy `backend/data/` over.

### v31.x maintenance (stable line until v32.0.0 ships)

- 🟢 P3 — Customer / License Admin Dashboard (manage licenses, HWIDs,
  revocations) — UI work blocks on Tauri shell decisions.
- 🟢 P4 — Re-enable Music Bingo as paid add-on (flip
  `ENABLE_MUSIC_BINGO=true`, gate on `owns_music_bingo`).
- 🟢 P4 — Audit log for admin actions.

### Storefront delivery — Squarespace Commerce Digital Products (Feb 2026)
After friction with the unlinked `/download` page workflow, the user
chose to attach all three installers (`BIGHatStandalone-Setup-31.0.0.exe`,
`BIGHatEntertainment-31.0.0-macOS-AppleSilicon.zip`,
`BIGHatEntertainment-31.0.0-macOS-Intel.zip`) directly to the
`BHE-STANDALONE` product in Squarespace Commerce. Squarespace mails
download links automatically; license keys are mailed in parallel by
Resend from `api.bighat.live`. Click-by-click guide:
`/app/packaging/SQUARESPACE_DELIVERY_QUICKSTART.md`.

### Phase 10.5 — Installer dependency baking (Feb 2026, P0 hotfix)
First customer-machine install revealed every prior installer was broken:
the embedded Windows / macOS Python had **zero third-party packages**
installed, so `import uvicorn` in `launcher.py` died on first launch.
Because the desktop shortcut ran `pythonw.exe` (no console), the user
saw nothing. Fix:
- New `backend/requirements-desktop.txt` — runtime-only subset of
  `requirements.txt` (drops linters, AWS SDK, etc.).
- `scripts/build_installer.py` and `scripts/build_dmg.py` now run
  `pip install --target` against `--platform win_amd64` / macosx
  arm64+x86_64 wheels at build time, baking ~13k files into
  `python/Lib/site-packages` so the customer never needs internet.
- `backend/launcher.py` wraps `main()` in a top-level try/except that
  shows a Win32 `MessageBoxW` (Windows) or `osascript display dialog`
  (macOS) on failure, pointing at a crash-log path. No more silent dies.
- NSIS shortcuts (Desktop / Start Menu / Auto-start) now route through
  the new `BIGHat.exe` Win32 wrapper (Phase 10.6) so the health-check
  fires on every launch, not just from the installer's Finish page.
- Installer size grew from 34 MB → 106 MB (still well under
  Squarespace's 300 MB per-file limit).

### Phase 10.6 — Native Win32 launcher wrapper (Feb 2026)
Replaced the `wscript.exe + start_bighat.vbs` shortcut chain with a
real, icon-bearing Win32 GUI executable so paying customers see a
polished launch experience instead of "running a script". Components:
- `packaging/win32_wrapper/bighat.c` — 200 LOC C source that resolves
  the install root from `GetModuleFileNameW`, spawns
  `python\pythonw.exe backend\launcher.py` with `CREATE_NO_WINDOW |
  DETACHED_PROCESS` (no flashing console), polls TCP `127.0.0.1:8001`
  with non-blocking `connect()`+`select()` for up to 12 s, and surfaces
  `MessageBoxW` errors pointing at `backend\data\logs\launcher_crash.log`.
- `packaging/win32_wrapper/bighat.rc` + `bighat.manifest` — embed the
  multi-resolution `bighat.ico`, VERSIONINFO (so File Properties +
  Task Manager show the right metadata), Common Controls v6, and
  PerMonitorV2 DPI awareness.
- `packaging/bighat.ico` — generated from `frontend/public/hat-logo.png`
  at six sizes (16/32/48/64/128/256).
- `scripts/build_win32_wrapper.py` — wraps the `x86_64-w64-mingw32-gcc`
  +`windres` cross-compile (called automatically from
  `build_installer.py`).
- NSIS now uses `bighat.ico` for both installer and uninstaller, sets
  `DisplayIcon` in `Programs and Features`, and points all shortcuts
  + the Finish-page `LaunchApp` at `$INSTDIR\BIGHat.exe`. The
  `start_bighat.vbs` is kept on disk as a manual fallback only.
- Resulting `BIGHat.exe` is 75 KB; total installer is 106 MB.

### Phase 10.7 — `.bighat` portable round files + Windows file association (Feb 2026)
Customers can now save a Round Maker round as a single `.bighat` file
(zip archive: `manifest.json` + `round.json`), email it to a colleague,
back it up to OneDrive, or just double-click in Explorer to re-open it
in BIG Hat Entertainment. Round backups are now portable artifacts the
customer owns, not opaque rows in a SQLite database.
- `backend/routes/bighat_files.py` — three endpoints:
  * `GET  /api/bighat-files/export/{round_id}` → ZIP download
  * `POST /api/bighat-files/import` (multipart) → mints a fresh round id
  * `POST /api/bighat-files/import-from-path` (form `path=`) → reads
    a server-local file; restricted to native mode + loopback origin.
  Manifest validates `format == "bighat/round"` and rejects future
  versions with a "please update BIG Hat" upgrade hint.
- Frontend `RoundMakerDashboard.js` — new "Save .bighat" action button
  per round + "Open .bighat..." picker at the section header. On mount,
  reads `?openFile=` query param (set by `BIGHat.exe` when a `.bighat`
  is double-clicked), POSTs to `import-from-path`, then strips the
  param via `history.replaceState` so refresh doesn't re-import.
- `BIGHat.exe` (`bighat.c`) — accepts the file path as `argv[1]`,
  URL-encodes it, builds `http://127.0.0.1:8001/roundmaker?openFile=<path>`,
  and goes single-instance: if port 8001 is already listening, just
  `ShellExecuteW` the URL into the user's default browser; else spawn
  the launcher with `--no-browser`, wait for the port, then open the
  URL ourselves (no double-tab).
- NSIS installer registers `.bighat` under
  `HKCU\Software\Classes\.bighat` → `BIGHat.bighatfile` (default icon =
  `BIGHat.exe,0`; `shell\open\command` = `"BIGHat.exe" "%1"`), broadcasts
  `SHCNE_ASSOCCHANGED` so Explorer picks it up immediately, and removes
  both keys on uninstall.
- New regression `backend/tests/test_phase10_7_bighat_files.py` — 9
  tests: export-import round-trip, future-version rejection, corrupt
  zip, missing manifest, wrong format, import-from-path success +
  missing-file 404. **All passing.**
- Installer size unchanged at 106 MB.

### v31.0.13 — Cloud Library / file-cloud sync removed (2026-05-27)
- The SharePoint-backed file-cloud content distribution feature has
  been retired. Premium content packs are now sold as `.bighat` files
  on Squarespace.
- Deleted: `backend/native/sync_router.py`, `sync_service.py`, and
  the matching test suite. `/api/native/sync/*` endpoints are gone.
- Simplified: `asset_factory.py` always returns LocalAssetService.
  `cloud_sync_enabled` flag scrubbed from subscription model + config
  defaults + Setup Wizard UI + cloud-response mirror logic. Existing
  configs auto-scrub the dead key on next load.
- Preserved (Option B from user's choice): license activation,
  Squarespace webhook, Resend emails, HWID + seat tracking, OS-aware
  download page, host's own SharePoint pipeline.
- 112 cloud/license/.bighat tests green.

### v31.0.12 — .bighat file format v2 (2026-05-27)
- Customers can now export/import Round Maker rounds, full trivia
  presentations, bingo cards, and scoreboard themes as portable
  `.bighat` archives. One reusable React component
  (`BIGHatFileButtons`) drops Export/Import buttons into any
  dashboard. Confirmation dialog shows file name, type, asset count,
  signed badge, source version before committing.
- HMAC-SHA256 signing under `BIGHAT_SIGNING_KEY` for paid premium
  content packs sold via api.bighat.live. Unsigned personal exports
  still work; the badge is informational.
- Forward-compat: v3+ files fail with "update the app" message
  rather than partial import. v1 files (the original Phase 10.7
  round-only format) continue to import unchanged.
- 50MB hard cap. 10 round-trip + signing + forward-compat tests.

### v31.0.11 — Setup wizard guaranteed before first login (2026-05-27)
- `NativeContext.refresh()` no longer fail-opens to `native_mode=false,
  setup_complete=true` when `/api/native/info` is unreachable. On a
  native install build it retries 5x with backoff, then renders a
  dedicated "BIG Hat can't reach its background service" screen with
  a Retry button. Customers can never be silently funneled past Setup
  to a doomed login form anymore.
- `App.js — NativeGate` renders the connection-error screen ahead of
  the loading state.

### v31.0.10 — CRITICAL: installed apps couldn't authenticate + credential leak fix (2026-05-27)
- Two production-blocking bugs found by user:
  1. Every installed v31.0.5–v31.0.9 app talked to OUR preview env, not
     to its own embedded backend, because the React bundle had
     `REACT_APP_BACKEND_URL=https://standalone-tools.preview.emergentagent.com`
     baked in. Resulted in "LOG IN TO 127" Google OAuth screen + "Auth
     failed" on password login.
  2. Default employee password literal was hardcoded 11× in
     `server.py`, now visible in the public GitHub mirror.
- Fixed:
  - `build_installer.py` + `build_dmg.py` now force-build with
    `REACT_APP_BACKEND_URL=""` → relative URLs → installed app talks
    to `127.0.0.1:8001`.
  - All hardcoded default password literals (the "B-1-G-H-a-t" string and
    the "121589" admin code) replaced with `DEFAULT_HOST_PASSWORD` /
    `ADMIN_MASTER_PASSCODE` env-driven constants.
  - `/api/host/password/is-default/{id}` no longer returns the
    actual default password; `/api/host/login` now returns
    `is_default_password: bool` instead.
  - `backend/native/system_config.json` and `backend/static/static/`
    untracked from git + gitignored.
  - New pytest regression `test_no_plaintext_credentials.py` blocks
    any future reintroduction of known-leaked literals.
- Required prod ops: set `DEFAULT_HOST_PASSWORD`, `ADMIN_MASTER_PASSCODE`,
  `SEED_PW_*` env vars on `api.bighat.live` (Emergent Support).

### v31.0.9 — OS-aware download landing (2026-05-27)
- Squarespace store + bighat.live used to link directly at a stale
  Windows .exe on GitHub. Mac buyers got a Windows installer for a
  release that no longer existed.
- New `/api/downloads/auto` (UA-detected 302), `/api/downloads/latest`
  (JSON manifest), and `/download` (branded HTML landing page) on the
  cloud server. All three resolve from `releases/latest` on GitHub at
  request time so the link never goes stale.
- Asset matching covers Windows .exe, macOS Apple Silicon zip, and
  macOS Intel zip. 5-min in-memory cache. Env-var override path
  preserved.
- 11 new pytest cases (99/99 cloud tests green).
- Action required: change the Squarespace store button to
  `https://api.bighat.live/download` and set `GITHUB_OWNER` /
  `GITHUB_REPO` env vars on production. See CHANGELOG for details.

### v31.0.8 — Cloud license wired into setup (2026-05-27)
- `/api/native/setup/initialize` now calls `cloud_client.activate()`
  against `https://api.bighat.live/api/license/activate` server-side.
  Cloud is authoritative: 4xx rejects setup, 2xx mirrors flags, transport
  error proceeds offline with `pending_cloud_activation=true`.
- New `retry_pending_cloud_activation` APScheduler job (every 4 hours)
  picks up offline-completed setups and finishes activation when the
  network returns.
- 4 new pytest cases in `tests/test_setup_cloud_activation.py` cover the
  four cloud-response branches (88/88 license-suite green).
- Closes PRD Phase 10.1.

### v31.0.7 — Fresh-install fixes (2026-05-27)
- **Setup Wizard now actually runs on first install.** Builds before
  31.0.7 shipped the dev `backend/native/system_config.json` to
  customers (setup_complete=true, stale master admin + HWID), which
  short-circuited the wizard and caused unrecoverable login lockout.
  Fixed in `scripts/build_installer.py` + `scripts/build_dmg.py`
  (file-level exclusion in `_copy_tree`) and a one-shot launcher-side
  quarantine in `backend/launcher.py` so existing v31.0.6 installs
  auto-recover on next launch.
- **Google sign-in is hidden in native mode.** The chromeless `--app=`
  window would otherwise leave the BIG Hat origin and land on
  `auth.emergentagent.com` (showing "LOG IN TO 127" because the redirect
  hostname is `127.0.0.1`) with the OS window title flipping to
  "Emergent". Native standalone provisions the master admin offline via
  the wizard; Google OAuth stays available in webapp / cloud mode only.
  Fix in `frontend/src/pages/LoginPage.js` (gated on
  `useNative().nativeMode`).

### Optional P3 backlog
- **Phase 10.2**: Move installer hosting off Squarespace to Cloudflare R2
  (free egress) or S3 + CloudFront with signed URLs (better analytics +
  per-user audit) — only if Squarespace's 24h / 5-attempt download links
  ever become a customer-support pain point.
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
1. Read `/app/memory/CHANGELOG.md` for the most recent in-flight context
   and the canonical Windows-launcher rules (NEVER-DO RULES at the top).
2. Pick the next item from the **Pending / Backlog** section above.
3. `/app/memory/PRD.md` (this file) is the long-form spec.
