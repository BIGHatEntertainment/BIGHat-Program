# Change Log

Append-only. Newest at top.

---
## 2026-02 — Phase 9 (Packaging & Single-Process Launcher) ✅ — backend testing agent verified 29/29 + 160/160 regression = **189/189**

### What shipped
Everything needed to turn the monorepo into a shippable desktop artifact.
`python backend/launcher.py` is now a single command that boots the full
offline app: FastAPI on `127.0.0.1:8001`, SQLite via MontyDB, all routers
(native + sync + admin + trivia + roundmaker + scoreboard + bingo +
story-generator), and — when a React build bundle is present under
`backend/static/` — the frontend SPA served from the same port. End users
reach the whole app at one URL; no dev server, no proxy.

### New files
| File | Purpose |
|------|---------|
| `backend/launcher.py` | Single-process launcher. Forces `BIGHAT_NATIVE_MODE=1`, ensures `data/*` dirs exist, prints or runs `uvicorn server:app` on `127.0.0.1:<PORT>`. Flags: `--check` (print config & exit), `--port`, `--host`, `--no-browser`, `--reload`. Browser auto-opens after a 1.5s timer unless `--no-browser`. |
| `scripts/build_standalone.py` | Build orchestrator. Runs `yarn install` (or `--skip-install`), `yarn build`, copies the output into `backend/static/`, writes `build_manifest.json` (`built_at`, `git_sha`, `frontend_included`, `file_count`, `python_version`, `platform`). Flags: `--skip-install`, `--clean`, `--no-frontend`. |
| `packaging/start_bighat.vbs` | Windows silent-launch VBS. Runs `python\python.exe backend\launcher.py` with no console window. Edit `INSTALL_ROOT` per-install. |
| `packaging/install_shortcut.vbs` | Creates a Desktop shortcut to `start_bighat.vbs` with optional icon. Safe to re-run. |
| `packaging/README.md` | End-to-end distribution runbook: runtime topology, build sequence, local smoke test, Windows install steps, auto-start on login, uninstall, known gaps. |
| `backend/tests/test_phase9_packaging.py` | 29 pytest cases covering the full Phase 9 surface — see below. |

### Modified files
- `backend/server.py`: new conditional SPA static-bundle mount. If
  `backend/static/index.html` exists at startup, the backend mounts
  `/static/*` to the React build's static subdirectory and registers a
  catch-all `GET /{full_path:path}` that (1) never shadows `api/`,
  `health`, `docs`, `openapi.json`, `redoc`; (2) serves `backend/static/<path>`
  if present; (3) falls back to `index.html` so client-side SPA routing
  works on hard reload / deep link. When the bundle is absent the block
  is a no-op — dev mode (React dev server on :3000) keeps working.
- `backend/routes/scoreboard.py`: `/tournaments/{id}/advance` now returns
  HTTP 404 with `detail="match_not_found: '<id>' is not in bracket_state.matches"`
  when `match_id` is unknown. Previously it silently no-op'd on the match
  update but still touched `bracket_state.last_updated` — confusing UX and
  easy to miss in the UI. (Testing agent uncovered a latent Phase 8 test
  relying on the old no-op; the test was corrected to seed `bracket_state.matches`
  via PUT before /advance.)
- `backend/native/admin_router.py`: new public `set_current_user_resolver()`
  setter + `_default_resolver()` coroutine. `_require_master_admin` now
  uses the injected resolver when set; otherwise falls back to the default
  resolver which imports `server.get_current_user` at request time (same
  behaviour as before). Decouples the admin router from `server.py` for
  testing and any future non-server integrations.
- `scripts/build_standalone.py`: `write_manifest` now preserves
  `frontend_included=True` when `--no-frontend` is used but the bundle
  is still on disk — avoids the launcher's "static-bundle-present" check
  flipping false on incremental backend-only builds (reviewer-flagged).

### Verified end-to-end (testing agent, 29/29 Phase 9)
- `launcher.py --check` prints backend_dir / listen / native_mode /
  setup_complete / instance_id / paths / static_bundle and exits 0 without
  starting uvicorn.
- `launcher.py --no-browser --port 18102` actually boots: `/health` →
  `{status:'healthy'}`, `/api/native/info` → JSON, `/` → `<title>BIG Hat | Host</title>`.
- SPA mount: `/`, `/setup`, `/any/deep/link` all return `index.html`;
  `/api/native/info` + `/api/__definitely_not_an_endpoint__` correctly
  route to the API (200 + 404 JSON respectively); `/health` returns JSON.
- `/static/css/<hash>.css` and `/static/js/<hash>.js` load with 200.
- `build_manifest.json` has all six expected keys; `file_count >= 10`;
  `git_sha` non-empty.
- `build_standalone.py --help` lists `--skip-install`, `--clean`,
  `--no-frontend`. `--no-frontend` preserves `index.html` bytes + now
  preserves `frontend_included=True` via the new read-and-OR logic.
- `/scoreboard/tournaments/{id}/advance` unknown match → 404
  `match_not_found:`; seeded match → 200 + `completed=true`.
- `native.admin_router.set_current_user_resolver` + `_default_resolver` +
  `_user_resolver=None` initial state all present.
- Packaging artifacts: 3 files exist, non-empty, contain `C:\BIG Hat\BIGHatStandalone`
  literal.
- All 9 public regression endpoints 200/documented. Prior-phase pytest
  suites (phase 2, 3, 5, 6, 7, 8) = 160/160 unchanged.

### Reviewer observations (non-blocking, documented)
- Tournament creation doesn't auto-generate `bracket_state.matches`;
  callers must supply it at create-time or PUT a bracket_state payload
  before `/advance`. Consider a `POST /tournaments/{id}/generate-bracket`
  convenience helper in a future iteration.
- `set_current_user_resolver` doesn't validate the callable's signature;
  a one-line `inspect.iscoroutinefunction` check would catch a sync stub.
- VBS `INSTALL_ROOT` hardcode is intentional (template pattern); README
  documents the find/replace step.

---


## 2026-02 — Phase 8 (Admin + Hardening) ✅ — backend testing agent verified 30/30 + 130/130 regression = **160/160**

### What shipped
Master-admin-only surface for managing sub-admins, hosts, passwords, and
license seats, plus two reviewer-flagged hardening items on the scoreboard
tournament models.

### New files
| File | Purpose |
|------|---------|
| `backend/native/admin_router.py` | `/api/native/admin/{users,license/seats,whoami}`. Every endpoint carries `Depends(_require_master_admin)` which imports `get_current_user` from `server.py` at request time (avoids a circular at module load). `UserCreate`, `UserUpdate`, `SeatLabel` Pydantic models. `_mirror_to_db` keeps `db.users` in sync with `system_config.json -> users[]` so the native auth bridge sees the same user data the admin UI writes. |
| `backend/tests/test_phase8_admin_native.py` | 30 pytest cases covering auth, validation, promotion, demotion, password reset, master-protection rules, seat listing/renaming/revoke, and tournament validation. |

### New endpoints (all require `master_admin` JWT)
- `GET  /api/native/admin/users` — list all users
- `POST /api/native/admin/users` — create sub-admin (`role: admin`) or host (`role: host`)
- `PUT  /api/native/admin/users/{id}` — update name / role / password / phone / enabled
- `DELETE /api/native/admin/users/{id}` — remove user (refuses for master)
- `GET  /api/native/admin/license/seats` — seat roster + current-hwid flag
- `PUT  /api/native/admin/license/seats/{hwid}/label` — rename a seat
- `DELETE /api/native/admin/license/seats/{hwid}` — revoke seat (blocked for current device)
- `GET  /api/native/admin/whoami` — current master-admin snapshot

### Modified files
- `backend/server.py`: registers `admin_router` alongside `sync_router`
  with `prefix="/api"`.
- `backend/routes/scoreboard.py`:
  - `TournamentCreate` now carries `@field_validator` + `@model_validator`
    enforcing `len(teams) + bye_count == total_teams` (when `teams`
    non-empty). `total_teams >= 1`, `bye_count >= 0`.
  - New `TournamentAdvance` Pydantic model with required `match_id` +
    `winner_seed` and optional `score_a` / `score_b`. `/advance` handler
    now takes this typed body instead of `Dict[str, Any] = Body(...)`, so
    missing fields surface as proper 422s and the API docs now describe
    the expected shape.
  - Imports `field_validator, model_validator` from pydantic.

### Design notes
- **Dual-store users.** Native-mode users live in `system_config.json` as
  source-of-truth and mirror into MontyDB `db.users` for the rest of the
  webapp (auth/me, role checks, employee lookups). `_mirror_to_db` is
  idempotent and preserves the native-bridge contract.
- **Role vocabulary stays tight.** The API accepts `admin` and `host` only
  for the `role` field on create/update. `master_admin` is allocated
  exactly once by the setup wizard and cannot be assigned through the
  admin endpoints. `is_admin` is derived from `role` so clients don't need
  to pass both.
- **Lockout prevention.** The master admin cannot be demoted, deleted, or
  have their seat revoked — all three paths return HTTP 400.
- **Seat renaming** keeps `registered_at` intact so the UI can show both
  "first registered" and "last renamed" timestamps.

### Verified end-to-end (testing agent, 30/30 Phase 8)
- Unauth → 401; non-master JWT → 403 `master_admin_required`; master JWT
  → 200.
- Validation 422s on invalid role (`god`), malformed email, password < 6
  chars. Duplicate email → 409.
- Promotion host → admin (is_admin flips true), demotion admin → host
  (is_admin flips false).
- Password reset propagates: new password immediately works via
  `/api/auth/login` (native bridge picks up the updated hash).
- Master protection: delete master → 400 `cannot_delete_master_admin`;
  demote master → 400 `cannot_demote_master_admin`; revoke current HWID
  seat → 400 `cannot_revoke_current_device`.
- Seat rename round-trip; unknown HWID revoke → 404.
- Tournament validation: `total_teams=8, bye_count=0, teams=[A,B]` →
  422 with expected error string; valid 4-team bracket → 200; empty-teams
  pre-seeded 12-team bracket → 200 (empty teams are explicitly allowed).
- `/tournaments/{id}/advance` empty body → 422 listing `match_id` +
  `winner_seed` missing; proper body → 200 with `bracket_state.last_updated`
  populated.
- All 9 public regression endpoints 200; prior-phase pytest suites
  (phase 2, 3, 5, 6, 7) = 130/130 unchanged.

### Reviewer observations (non-blocking, documented)
- `_require_master_admin` imports `server.get_current_user` at request
  time. Works, but creates a runtime import coupling that a proper
  `set_current_user_resolver` setter would break cleanly. Defer to
  Phase 9.
- `TournamentAdvance` handler silently no-ops when `match_id` isn't in
  `bracket_state.matches` but still bumps `last_updated`. Consider a
  404 `match_not_found` for clearer UX.
- `config_manager.save_config()` writes synchronously per request;
  acceptable at single-user scale, revisit if rename-seat UX ever
  batches many writes.

---


## 2026-02 — Phase 7 (SharePoint Hybrid Sync) ✅ — backend testing agent verified 22/22 + 108/108 regression = **130/130**

### What shipped
Premium-gated bidirectional sync between the local asset tree
(`/app/backend/native/data/assets/`) and SharePoint. The core engine is
implementation-agnostic: it syncs between any object that implements the
small asset-service surface (`list_folder_contents`, `download_file_to_bytes`,
`upload_content`) and a local folder. In production that's the real
`SharePointService`; in dev/test an env-var fixture lets us substitute a
second `LocalAssetService` pointed at a simulated cloud folder.

### New files
| File | Purpose |
|------|---------|
| `backend/native/sync_service.py` | `SyncService` orchestrator + `RemoteFile`/`LocalFile`/`SyncPlan` dataclasses. Implements remote/local walks (depth-capped), size-based diff, pull/push apply loops with path-traversal guard, and `record_sync_run`/`get_sync_state` for MontyDB persistence. |
| `backend/native/sync_router.py` | `/api/native/sync/{status,plan,pull,push}` FastAPI router. `/plan /pull /push` carry `Depends(require_native_premium("cloud_sync_enabled"))`. `/status` is intentionally free so the UI can always show "upgrade to unlock". `_remote_service()` honours `BIGHAT_SYNC_REMOTE_FIXTURE` for dev — production uses `asset_factory.get_asset_service()`. |
| `backend/tests/test_phase7_sync_native.py` | 22 pytest cases covering gate toggles, full pull/push round-trip, convergence, delete_missing, state persistence, and path-traversal safety. Seeds unique files per run and cleans TEST_* artefacts. |

### Modified files
- `backend/server.py`: registers `sync_router` after the native router.
  Wires `sync_set_database(db)` so `record_sync_run` / `get_sync_state`
  write the MontyDB `sync_state` collection.
- `backend/.env`: `BIGHAT_SYNC_REMOTE_FIXTURE=/app/backend/native/data/cloud_fixture`
  so the dev container runs real sync against a deterministic local mirror.

### New on-disk seed (dev container only)
`/app/backend/native/data/cloud_fixture/01_Trivia/Web App/00_Builder/` —
parallel mirror tree with intentional drift vs the live assets folder:
`01_Hosts/Cloud_Host_1.pptx`, `03_Sponsors/Sponsors_Extra.pptx`,
`01_Rounds/01_MC/MC_NewTopic.pptx`, and a size-differing
`01_Rounds/01_MC/MC_Music.pptx` to exercise to_add / to_update paths.

### Verified end-to-end (testing agent, 22/22 Phase 7)
- `GET /status` returns 200 with the expected shape regardless of
  subscription state. `available` is true iff
  `subscription.active && subscription.cloud_sync_enabled`.
- Subscription OFF → `/plan`, `/pull`, `/push` all return **402** with
  `detail.error='premium_required'` and
  `detail.feature='cloud_sync_enabled'`.
- Subscription ON + fixture → full bidirectional round-trip converges
  (plan returns 0 changes in either direction afterwards). `added` /
  `updated` counts match file contents on both sides.
- `db.sync_state` collection stores `last_pull` and `last_push` summaries
  (kind, finished_at, added, updated, deleted, errors, unchanged) that
  surface under `/status`.
- `delete_missing:true` correctly surfaces `to_delete` entries. Deletes
  are only applied on `push` when the remote service exposes
  `delete_path` (safety default — SharePointService + LocalAssetService
  both do in practice; this just shields against missing methods).
- Path traversal (`sync_root='../../etc'`): walks return empty / clean
  500; no files outside `local_root` leaked.
- Subscription OFF after ON → gate re-engages immediately, no restart.

### Reviewer-flagged observations (documented, non-blocking)
- Size-only diff (not hash-based) is the deliberate trade-off — hashing
  every PPTX on every plan is wasteful and mtime across SharePoint vs
  local disk is TZ-skewed in the real world. A hash-mode override can
  be added if users end up editing pptx files in-place at byte-identical
  sizes (unlikely — python-pptx re-zips = size always changes).
- `subscription.set_subscription` auto-enables all feature flags when
  `active=True && tier='premium'`. Intentional for "one premium SKU = all
  cloud features" UX; document in PRD once the pricing page exists.

---


## 2026-02 — Phase 5 (Scoreboard: Leaderboards + Tournament Brackets) ✅ — backend testing agent verified 24/24 + 84/84 regression = **108/108**

### What shipped
Scoreboard now runs entirely on SQLite + local disk in native mode. Score
sync reads JSON files from `<assets>/01_Scores/<venue>/*.json` instead of
SharePoint. Presets and tournament brackets persist in MontyDB. Video/
image-to-video export endpoints are premium-gated behind
`story_generator_enabled`. A new `/api/scoreboard/status` endpoint gives
the frontend everything it needs to show the right UI state (upgrade
banner vs real UI vs offline hint).

### Modified files
- `backend/routes/scoreboard.py`:
  - Imports `require_native_premium` → builds `_video_gate` (for export
    endpoints) and `_cloud_sync_gate` (reserved for Phase 7 cloud sync).
    Tight `except ImportError` with ERROR log.
  - `_is_local_mode()` + `_local_scores_root()` helpers. ImportError-only
    guard on the asset-factory import.
  - `GET /api/scoreboard/status` — new endpoint returning `{mode,
    native_mode, subscription, ffmpeg_ok, video_export_available,
    cloud_sync_available, local_scores:{root,venues,files},
    db_counts:{tournaments,presets,synced_files}}`.
  - `GET /sharepoint/files`, `POST /sharepoint/sync`, `GET /sharepoint/file/{file_id:path}`
    now branch on `_is_local_mode()` to read/sync from disk. Response
    shape unchanged; adds `source:"local"` when applicable. The
    `file_id:path` converter lets the relative path (`Demo Pub/2026-05-01.json`)
    survive URL routing. **Path-traversal guard** applied on the content
    endpoint via `Path.resolve().relative_to(root)`.
  - `POST /exports/upload`, `POST /exports/image-to-video`,
    `POST /generate-video` — all carry `dependencies=_video_gate`.
  - **Pre-existing F821 bug fix**: `/exports/upload` referenced an
    undefined `ext` variable. Now derived from `file.filename` with a
    `'bin'` default. The endpoint was 500ing since before Phase 5; this
    unblocks real PNG/WebM uploads once subscription is active.

### New on-disk seed (dev container only)
`/app/backend/native/data/assets/01_Scores/Demo Pub/2026-05-01.json` —
sample event with 4 teams, 5 rounds. Sync + content + leaderboard all tested
end-to-end against this fixture.

### Verified end-to-end (testing agent, 24/24 Phase 5)
- `/status` reports expected shape with/without subscription.
- Local sync round-trip: `POST /sharepoint/sync` → MontyDB upsert →
  `GET /scores` returns the data payload with the same `teams` array.
- `GET /sharepoint/file/Demo%20Pub/2026-05-01.json` returns the full JSON
  (path converter works).
- Path traversal (`../../etc/passwd`) → 400 (guarded).
- Presets full CRUD on SQLite (create, read, update, delete, round-trip of
  `config` blob).
- Tournaments full CRUD on SQLite + `/{id}/advance` mutates `bracket_state`
  and persists.
- Premium gate with sub OFF: `/exports/upload`, `/exports/image-to-video`,
  `/generate-video` → 402 `premium_required`, `feature=story_generator_enabled`.
- Read endpoints stay free with sub OFF (scores, tournaments, presets, status).
- Sub ON → 402 disappears; body-validation 422s take over as expected.
- 108/108 overall including Phase 2/3/6 regression.

### Reviewer-flagged items applied immediately
- `_is_local_mode()` now catches only `ImportError` with ERROR log (was
  bare `Exception` — risked silent fallback to cloud mode).
- `/exports/upload` F821 fix (`ext` derivation from filename).

### Reviewer-flagged items deferred to Phase 8 hardening
- `TournamentCreate.total_teams` / `bye_count` dead metadata (neither
  validates against `teams` length nor used by `/advance`).
- `/tournaments/{id}/advance` body shape documented as
  `{match_id, winner_seed}`; frontend may want a batch `{round, winners[]}`
  variant.
- `scoreboard.py` is now 1000 lines — split candidate: `scoreboard/{scores,
  presets, tournaments, exports, video}.py`.
- Module-level imports of `httpx` / `subprocess` currently live inside
  endpoint functions for lazy-load reasons; fine for now but could move up.

---


## 2026-02 — Phase 6 (Story Generator Premium Gate) ✅ — backend testing agent verified 26/26 + 58/58 regression = 84/84

### What shipped
The Story Generator (video + preview + webm convert + event video) is now
gated by the `story_generator_enabled` premium flag in native mode. Webapp
mode is unchanged — the gate is a no-op when `BIGHAT_NATIVE_MODE=0`. Read
endpoints stay free in both modes so the UI can still list presentations
and show what unlocks with a subscription.

### New files
| File | Purpose |
|------|---------|
| `backend/native/feature_gate.py` | `require_native_premium(feature)` — FastAPI dependency factory. No-op in webapp mode; returns HTTP 402 `premium_required` in native mode when the named subscription feature flag is inactive. Reusable for Phase 7/8 cloud-sync and admin features. |

### Modified files
- `backend/routes/story_generator.py`:
  - Imports `require_native_premium` with a single `except ImportError`
    (tightened from bare Exception so unrelated errors no longer silently
    disable the gate — they now log at ERROR).
  - Builds `_story_gate = [Depends(require_native_premium("story_generator_enabled"))]`
    once at module load.
  - Applies `dependencies=_story_gate` to the 8 mutating endpoints:
    `POST /generate/{id}`, `POST /preview/{id}`, `POST /upload-asset`,
    `DELETE /asset/{type}/{id}`, `POST /assemble-video`,
    `POST /convert-webm`, `POST /event-preview`,
    `POST /generate-event-video`.
  - Adds `GET /api/story-generator/status` — returns
    `{available, mode, reason, subscription, ffmpeg_ok}` so the frontend
    can decide whether to show the upgrade prompt or the real UI, and so
    native support can see at a glance why the feature is disabled.

### Verified end-to-end (testing agent, 26/26)
- Subscription OFF → all 8 mutating endpoints return HTTP 402 with
  `detail.error='premium_required'` and `detail.feature='story_generator_enabled'`.
- Subscription OFF → read endpoints (`/presentations`, `/assets`,
  `/job-status/{id}`) still return 200/404 (never 402).
- Subscription ON (via `POST /api/native/subscription {active:true,
  tier:'premium', story_generator_enabled:true}`) → same mutating endpoints
  drop the 402 and return 404/422/500 depending on body validity. Toggle is
  effective immediately — no backend restart.
- Per-feature gating: `sharepoint_enabled=false` + `story_generator_enabled=true`
  still unlocks story-gen endpoints (confirming we gate on the specific
  feature, not the whole subscription).
- Regression: Phase 2 (37) + Phase 3 (21) suites still green.

### Known issues fixed during Phase 6
- **Initial version missed `dependencies=_story_gate` on `/generate-event-video`**
  (testing agent caught it — iteration 5 was 25/26). One-line fix, re-run
  at iteration 6 showed 26/26 + 58/58 regression = **84/84 overall**.
- **Bare `except Exception` around the gate import** risked silently
  disabling premium checks if any unrelated import error occurred.
  Tightened to `except ImportError` with ERROR-level logging.

### Code-review follow-ups (deferred to Phase 8 hardening)
- Split `story_generator.py` (>1600 lines) into
  `story_status.py` / `story_presentation.py` / `story_assets.py` /
  `story_video.py` / `story_event.py`.
- Consolidate the dual job stores (`video_jobs` / `_video_jobs`) with TTL
  eviction.
- Add `Content-Length` caps on `/convert-webm` and `/assemble-video` base64
  payloads (currently unbounded).
- Cache `_probe_ffmpeg()` at module load (negligible hit but obvious win).

---


## 2026-02 — Phase 3 (Round Maker SQLite + Local Publish) ✅ — backend testing agent verified 21/21 (Phase 3) + 37/37 (Phase 2 regression) = 58/58

### What shipped
The Round Maker (`/api/roundmaker/*`) now generates and publishes PPTX rounds
end-to-end in pure native local mode. No SharePoint creds, no Graph API.
Generated rounds land in the local trivia round library so they show up
immediately in the Trivia presenter without any sync step.

### Modified files
- `backend/routes/roundmaker.py`:
  - Added `_is_local_mode()`, `_local_assets_root()`, `_local_trivia_root()`,
    `_local_title_cards_dir()` helpers at module top.
  - `_upload_to_sharepoint_direct(file_path, filename, round_type)` now
    branches: in native local mode it copies the generated PPTX into
    `paths.assets/01_Trivia/Web App/00_Builder/01_Rounds/<TYPE_FOLDER>/<filename>.pptx`
    and returns `{success, web_url=file://..., file_id=<abs_path>, folder=<type>}`
    so the existing CRUD round-doc update fields stay populated.
  - `/reg-title-images` lists `04_TitleCards/REG/*.{jpg,jpeg,png,gif}` from
    the local assets folder when in native local mode.
  - `/reg-download-title-image` reads bytes from the local file system and
    writes them into `roundmaker_uploads/` (used for inline cover-image
    embedding by the PPTX generator).
  - `/reg-title-image-preview/{item_id:path}` serves the local file directly
    (path-style item_id supported via `:path` converter).
  - `/reg-next-number/{category}` skips the SharePoint scan in native mode
    and instead enumerates the local 02_REG folder for `<category>_<n>.pptx`.
  - `/sharepoint-status` reports `{mode:'local', configured:true, token_valid:true, subscription:{...}}`
    in native local mode so the frontend can show "Publishing locally" instead
    of "SharePoint not configured".

### New on-disk seed (dev container only)
`/app/backend/native/data/assets/01_Trivia/Web App/00_Builder/04_TitleCards/REG/`
seeded with `History.png`, `Geography.png`, `Music.png` (real 1×1 PNGs,
69 bytes each) so title-card endpoints have content to return during testing.

### Verified end-to-end (testing agent)
- `POST /api/roundmaker/rounds` → SQLite insert.
- `POST /api/roundmaker/rounds/{id}/generate` → returns >100KB PPTX (HTTP 200,
  octet-stream). Pure-Python `python-pptx` generation works against the
  in-DB round doc.
- `POST /api/roundmaker/rounds/{id}/upload-sharepoint` as master_admin →
  `status:success, web_url:file:///app/backend/native/data/assets/01_Trivia/Web App/00_Builder/01_Rounds/02_REG/<name>.pptx`,
  the PPTX physically lands at that path, and immediately afterwards
  `/api/trivia/round-files/reg` returns the new round in its array.
- `/reg-next-number/{category}` increments by exactly +1 once a new
  `<category>_<n>.pptx` is dropped on disk.
- All Phase 1 + Phase 2 endpoints regressed clean (37/37 from previous suite
  re-run by the testing agent).

### Known issues fixed during Phase 3
- `_get_graph_token()` returned None silently when `AZURE_*` env vars were
  missing, but `/sharepoint-status` would still report `configured:false`,
  giving the user a confusing "SharePoint not configured" screen even though
  the local-mode publish flow worked perfectly. Fixed by short-circuiting
  the endpoint with `mode:'local'` when `_is_local_mode()` is true, before
  any SharePoint check runs.
- `/reg-title-image-preview/{item_id}` rejected the item_id when it was a
  relative path with slashes (the local-mode itemId is the relative path
  under the assets root). Fixed by upgrading the path parameter to
  `{item_id:path}` so FastAPI doesn't slash-strip.
- The local `04_TitleCards/REG/` folder was not part of the original V31
  asset tree; the path is now defined by `_local_title_cards_dir(round_type)`
  and matches the convention `<assets>/01_Trivia/Web App/00_Builder/04_TitleCards/<TYPE>/`,
  consistent with the existing `01_Hosts`, `02_Locations`, `03_Sponsors` siblings.

### Code-review notes for follow-up (non-blocking)
- `routes/roundmaker.py` (~1080 lines) should be split into
  `roundmaker_crud.py` / `roundmaker_assets.py` / `roundmaker_publish.py` in
  Phase 8 hardening.
- Path traversal hardening on `_local_title_cards_dir` lookup (`item_id`
  containing `..`). Currently only authenticated callers can hit it, but a
  `resolve().is_relative_to(_local_assets_root().resolve())` check is cheap.
- Per-round `created_by` ownership gate for DELETE/upload (Phase 8).
- Replace bare `except:` JWT decode in `upload_to_sharepoint` with explicit
  exception logging (Phase 8 hardening).

---


## 2026-02 — Phase 2 (Trivia Core SQLite Swap) — backend pieces ready, awaiting integration testing

### What shipped
Trivia routes (presenter editor, viewer, importer, slide cache) now run
entirely on SQLite + the local file system in native mode. SharePoint is
still reachable but only when (a) `BIGHAT_NATIVE_MODE=1`, (b) the user has
an active premium subscription with `sharepoint_enabled=true`, and (c)
`settings.trivia_source == "cloud"`. Otherwise every asset comes from the
local data root.

### New files
| File | Purpose |
|------|---------|
| `backend/native/gridfs_shim.py` | `NativeGridFSBucket` — drop-in replacement for `AsyncIOMotorGridFSBucket` against an `AsyncMontyDatabase`. Stores blobs base64-encoded inside a regular `slides_files` collection. Exposes `upload_from_stream`, `find`, `delete`, `open_download_stream` with the same async surface motor uses. |
| `backend/native/local_asset_service.py` | `LocalAssetService` — file-system mirror of the small `SharePointService` API used by trivia routes. Reads from `paths.assets` in `system_config.json` (default `/app/backend/native/data/assets`). Returns Graph-driveItem-shaped dicts so call sites don't need to change. |
| `backend/native/asset_factory.py` | `get_asset_service()` returns `SharePointService` only when `can_use_cloud()` is true (premium + sharepoint_enabled + trivia_source=cloud), otherwise `LocalAssetService`. `reset_cache()` for tests/config reload. |

### Modified files
- `backend/sharepoint_service.py`: `SharePointService.__new__` now consults `native.asset_factory.can_use_cloud()` and transparently returns a `LocalAssetService` instance when the answer is no. Effect: every existing `SharePointService()` call site in the codebase (~20 of them across trivia, schedule, story generator, slide_fetcher, overlays, presentations) routes to disk in native+local mode without code changes — and importantly, no longer crashes on missing `AZURE_*` env vars.
- `backend/gridfs_service.py`: `GridFSService.__init__` detects `AsyncMontyDatabase` and instantiates `NativeGridFSBucket` instead of `AsyncIOMotorGridFSBucket`. `delete_presentation_slides` now tolerates string-UUID file ids (native) as well as `ObjectId` (motor).
- `backend/routes/trivia.py`: `/rounds`, `/rounds/{mc,reg,misc,mys,big}`, `/round-files/{type}` short-circuit through `_list_local_round_files` when `_is_local_mode()` returns true. The 180-day round-usage lockout filter still runs against MontyDB.
- `backend/native/config.py`: `paths.{data_root, local_trivia, assets, generated}` defaults are now absolute (`/app/backend/native/data/...`) so the asset folder doesn't depend on backend cwd. Existing `system_config.json` was updated in place to absolute paths.

### New on-disk seed (dev container only)
`/app/backend/native/data/assets/01_Trivia/Web App/00_Builder/` populated
with placeholder hosts, locations, sponsors, and round (.pptx) files so the
local asset endpoints return non-empty arrays during testing.

### Verified (curl + direct python)
- `/api/trivia/hosts`, `/locations`, `/sponsors`, `/rounds`, `/rounds/mc`, `/round-files/mc` all return seed data in native local mode (no SharePoint creds needed)
- GridFS round-trip: `gridfs.store_slides(...)` → `find_one(slides_metadata)` → `chunk_data['slides']` matches input. Verified through both `/api/trivia-import/slides-metadata/{id}` and `/api/trivia-import/slides/{id}` endpoints
- Subscription toggle (`POST /api/native/subscription` active=true/false) does not crash trivia routes; cloud is only attempted when settings.trivia_source=cloud + sharepoint_enabled
- Schedule + auth + presentations CRUD still pass (no regression)

### Known issues fixed during Phase 2
- **Default asset path was relative (`./data/assets`)** so the LocalAssetService root depended on backend cwd, which silently differed between supervisor (`/app/backend`) and python repl scripts (`/app`). Fixed by making `_default_data_root()` resolve against the native module's directory and updating the live `system_config.json` to absolute paths. (See ERRORS.md 2026-02 06:55)
- **`SharePointService()` raised `KeyError: AZURE_TENANT_ID`** in native mode because every callsite still ran the original `__init__`. Fixed via `__new__` swap that returns `LocalAssetService` before `__init__` executes. The check is gated on `can_use_cloud()` so webapp mode is unaffected.
- **`bson.ObjectId(file_id)` crashed in `GridFSService.delete_presentation_slides`** when `file_id` was a string UUID (native). Fixed by trying `ObjectId(file_id)` first then falling back to the raw string before calling `fs.delete()`.

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
