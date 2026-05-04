# BIG Hat Standalone — Transformation Roadmap

**Goal:** Transform the BIGHat-Fullstack webapp (`/app`) into a native standalone Windows program with full feature parity, while gating premium features behind a subscription.

**Approach:** Transform-in-place. Keep all 10K+ LOC of business logic. Replace infrastructure layer-by-layer (DB, auth, asset source, packaging). Each phase is independently testable and ships value.

**Stack target:**
- Python FastAPI backend (existing)
- React frontend, built once (`yarn build`) and served as static by FastAPI (single-process deploy)
- **SQLite** local DB (replacing MongoDB)
- **Local 3-tier auth**: Master Admin → Admin → Host (replacing Google OAuth; OAuth kept as optional cloud-mode toggle)
- **HWID + 5-seat licensing** (Rust core from V30)
- **Local-first asset storage** at `C:\BIG Hat\data\` with optional SharePoint pull when subscription active + online
- **Native installer** (VBS scripts from V30) + native launcher (Edge `--app` mode)

## Phases

| # | Phase | Deliverable | Premium gate? |
|---|-------|-------------|---------------|
| 0 | **Foundation** | Setup wizard, multi-tier local auth, SQLite layer, license/HWID, native-mode config flag, React build pipeline. App still boots; new "Master Admin Setup" wizard runs first time. | — |
| 1 | **Schedule module** | Venues, events, hosts, claims, time-off — all backed by SQLite. | — |
| 2 | **Trivia Core** | Presenter + Editor (2.6K-LOC) + Viewer + PPTX import + overlays — SQLite-backed. | Cloud round library = premium |
| 3 | **Round Maker** | PPTX round generator. | — |
| 4 | **Music Bingo** | Lobby + Host + Audience views, full game engine. | — |
| 5 | **Scoreboard** | Leaderboard + tournament brackets, animated. | — |
| 6 | **Story Generator** | FFmpeg 20-second reel pipeline. | **Premium** |
| 7 | **SharePoint Hybrid Sync** | Pull/push when subscription active + online. | **Premium** |
| 8 | **Admin** | User mgmt, license seats, sub-admin promotion. | — |
| 9 | **Packaging** | VBS installers, drive mapping, native launcher, build script. | — |

## Success criteria per phase

### Phase 0 (Foundation) — DONE when:
- [ ] First boot shows Master Admin Setup Wizard (license key, master admin, location, paths)
- [ ] After setup, login screen accepts master admin credentials
- [ ] Master admin can create Admin and Host users (3-tier RBAC)
- [ ] All existing webapp routes continue to function (regression-safe)
- [ ] `system_config.json` persists across restarts
- [ ] HWID computed by Rust core, recorded in license_status.active_seats
- [ ] CHANGELOG/ERRORS/STATE logs are kept current

### Phase 1 (Schedule) — DONE when:
- [ ] Venues, events, hosts CRUD works against SQLite
- [ ] Calendar view loads events from SQLite
- [ ] Claim workflow advances event status
- [ ] Existing webapp Mongo schedule code is shimmed via dual-write or replaced cleanly

### Phase 2 (Trivia) — DONE when:
- [x] Presentations stored in SQLite (slides as JSON blob via MontyDB)
- [x] Native GridFS shim — slide cache reads/writes against SQLite blob store
- [x] Trivia round/host/location/sponsor lookup served from local file system in native mode (no SharePoint creds required)
- [x] Asset factory transparently swaps SharePoint ↔ Local based on premium subscription + trivia_source flag
- [ ] PPTX-to-image conversion verified end-to-end against a real .pptx in the native asset root (dev container only has placeholder zero-byte files)
- [ ] Editor saves and loads slides via UI smoke test
- [ ] Presenter renders slides + overlays + TV view via UI smoke test

### Phase 3 (Round Maker) — DONE when:
- [x] PPTX generation works locally via `python-pptx`
- [x] Round CRUD persists in SQLite (`db.rounds` via MontyDB)
- [x] "Upload to SharePoint" copies into the local trivia library when in native local mode; round appears immediately in `/api/trivia/round-files/<type>`
- [x] REG title-card listing/preview/download work without SharePoint
- [x] `/sharepoint-status` reports `mode='local'` cleanly
- [x] `/reg-next-number/{category}` increments based on local files + DB

### Phase 6 (Story Generator) — DONE when:
- [x] Mutating endpoints 402 when native+no-premium
- [x] Read endpoints stay free
- [x] `/api/story-generator/status` reports availability + ffmpeg_ok + subscription
- [x] Gate is per-feature (story_generator_enabled)
- [ ] UI surfaces upgrade screen when `status.available=false`


### Phase 5 (Scoreboard) — DONE when:
- [x] Presets + Tournaments CRUD on SQLite (MontyDB)
- [x] SharePoint score-sync endpoints read from `<assets>/01_Scores/<venue>/*.json` in native mode

### Phase 5 (Scoreboard) — DONE:
- [x] Presets + Tournaments CRUD on SQLite
- [x] SharePoint score-sync reads from `<assets>/01_Scores/<venue>/*.json`
- [x] `/sharepoint/file/{file_id:path}` serves JSON with path-traversal guard
- [x] `/exports/*` + `/generate-video` premium-gated
- [x] `/api/scoreboard/status`
- [x] F821 on `/exports/upload.ext` fixed
- [ ] Frontend upgrade banner

- [x] `/sharepoint/file/{file_id:path}` serves JSON with path-traversal guard
- [x] `/exports/upload`, `/exports/image-to-video`, `/generate-video` premium-gated

### Phase 7 (SharePoint Hybrid Sync) — DONE:
- [x] `SyncService` engine, pull/push/plan/status
- [x] Premium-gated by `cloud_sync_enabled`
- [x] MontyDB `sync_state` persistence
- [x] Path traversal guard
- [x] Dev fixture via `BIGHAT_SYNC_REMOTE_FIXTURE`
- [ ] Frontend: "Last synced" pill + Sync Now button
- [ ] Optional hash-based diff mode

### Phase 8 (Admin + Hardening) — DONE:
- [x] `/api/native/admin/users` master-admin-only CRUD
- [x] Role promotion / demotion with is_admin derivation
- [x] Password reset propagates via native bridge
- [x] Master protection (delete/demote/revoke-current)
- [x] License seat rename + revoke
- [x] `TournamentCreate` validates `len(teams)+bye_count==total_teams`
- [x] `TournamentAdvance` Pydantic body with proper 422s
- [ ] `/advance` 404 on unknown match_id
- [ ] `_require_master_admin` setter-based wiring (decoupling)

- [x] `/api/scoreboard/status` exposes mode + subscription + local counts
- [x] Pre-existing F821 on `/exports/upload.ext` fixed

### Phase 9 (Packaging) — DONE:
- [x] `backend/launcher.py` single-process boot
- [x] SPA static-bundle mount in FastAPI
- [x] `scripts/build_standalone.py` with manifest preservation
- [x] Windows VBS installer templates + packaging/README.md
- [x] `/advance` 404 match_not_found
- [x] `admin_router.set_current_user_resolver`
- [ ] Signed Windows installer (MSI/NSIS)
- [ ] Auto-update channel

### Phase 4 (Music Bingo) — DONE:
- [x] Song lists from local xlsx files (native mode)
- [x] /available-decades scans local 03_Songs folder
- [x] /bingo-cards lists local PDFs by category
- [x] /bingo-cards/download/{cat}/{decade} streams local PDFs
- [x] /api/bingo/status endpoint
- [x] GameStateCreate accepts {mode, decade} aliases (mode='number' → bingo_type='traditional')
- [x] Game state lifecycle on SQLite via global db swap
- [x] WebSocket broadcasting unchanged
- [ ] Watchdog auto-refresh on song/card folder changes
- [ ] /status parse_health metric


- [ ] Frontend conditionally shows upgrade banner when `status.video_export_available=false`

### Phase 4, 7-9 — see per-phase plans created when reached.

## Sub-agent strategy

- **Phase 0**: main agent only (foundation is too fragile for delegation)
- **Phases 1-8**: each phase, delegate execution to a sub-agent with clear context (paste relevant existing webapp code + SQLite schema + acceptance criteria)
- **Testing**: backend testing agent after every phase; frontend testing agent on user request
- **Troubleshooting**: troubleshoot_agent if any single change fails 3+ times

## Out of scope (for now)
- Cross-platform (we target Windows; Linux dev mode works for development)
- Auto-update server (V30 stub kept; not implemented)
- Mobile app
- Real-time collaboration (single-user-at-a-time per seat)
