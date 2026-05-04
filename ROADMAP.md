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
- [ ] Presentations stored in SQLite (slides as JSON blob)
- [ ] PPTX import works against local C:\BIG Hat\data\trivia
- [ ] Editor saves and loads slides
- [ ] Presenter renders slides + overlays + TV view

### Phase 3-9 — see per-phase plans created when reached.

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
