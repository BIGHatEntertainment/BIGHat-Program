# plan.md (Updated)

## 1) Objectives
- Confirm and document that the end-to-end pipeline is **working in production**:
  - **SharePoint (Microsoft Graph, app-only) ➝ JSON ➝ backend ➝ frontend animated render ➝ export (PNG/WebM) ➝ Live View**.
- Operate as a **two-mode MVP** for BIG Hat Entertainment:
  - **Regular Trivia Mode**: animated leaderboard with **Top 3 spotlighted**.
  - **Tournament Mode**: single-elimination bracket with **reseeding each round (highest vs lowest)**, configurable teams + byes.
- Maintain a **legally safe Phoenix sports-inspired** aesthetic:
  - Purple→orange desert sunset gradient, silhouettes (mountains/cacti/skyline), glass panels, broadcast readability.
- Shift goals from “build” to **stabilize + harden + extend**:
  - Operator reliability, repeatable exports, better state persistence for Live View, and optional next features.

**Current status (as of this update)**
- Phase 1 (POC): **Complete** — SharePoint integration proven end-to-end.
- Phase 2 (MVP): **Complete** — full backend + frontend built, themed, and tested.
- Deployment: **Live** at https://trivia-scoreboard.preview.emergentagent.com

---

## 2) Implementation Steps (Phased)

### Phase 1 — Core POC (Isolation: prove hardest parts) ✅ COMPLETE
**Core risk areas validated**: Microsoft Graph (app-only) + SharePoint shared folder traversal, JSON schema variability.

**POC results**
- Token acquisition via client credentials: ✅
- Sharing link resolution to DriveItem: ✅
- Folder exploration: ✅
- JSON download + parse: ✅
- Discovered structure: shared folder contains venue subfolders.
  - **6 JSON score files across 5 venue subfolders**.

**Observed JSON shape** (confirmed by real files)
- Top-level keys include:
  - `location`, `presentationName`, `date`, `presentationId`, `rounds[]`, `rankings[]`, `teams[]`
- Team objects include:
  - `rank`, `name`, `swag`, `roundScores[]`, `total`

**Deliverables produced**
- POC scripts in `/app/tests/` validating Graph and SharePoint access.

---

### Phase 2 — V1 App Development (MVP around proven core) ✅ COMPLETE

#### Backend (FastAPI + MongoDB) — Implemented
- SharePoint integration (Graph app-only):
  - Token caching (in-memory expiry)
  - Resolve shared link → drive + folder
  - Recursively list venue subfolders and JSON files
  - Download + parse JSON
- API endpoints delivered:
  - `GET /api/sharepoint/files` — fetch files live from SharePoint
  - `POST /api/sharepoint/sync` — sync files into MongoDB (`score_files`)
  - `GET /api/scores` and `GET /api/scores/{venue}` — retrieve stored score payloads
  - Presets CRUD:
    - `POST/GET/PUT/DELETE /api/presets`
  - Tournaments CRUD + advance:
    - `POST/GET/PUT/DELETE /api/tournaments`
    - `POST /api/tournaments/{id}/advance`

#### Frontend (React + Tailwind + shadcn/ui) — Implemented
- **Dashboard** (operator view):
  - Left rail controls: Mode, SharePoint fetch/sync, file picker, aspect ratio, animation controls, export, presets
  - Main area: scaled preview of fixed-pixel render stage
- **RenderStage**:
  - Exact pixel targets: **1920×1080 (16:9)** and **1080×1920 (9:16)**
  - Preview scaling via CSS transform
- **Leaderboard Render**:
  - Animated title + top 3 podium cards (glass panels)
  - Remaining teams list with staggered entrance
  - Uses SharePoint JSON `teams[]` for scores
- **Tournament Render**:
  - Single elimination bracket generation
  - **Reseeding each round** (highest vs lowest)
  - Animated connector lines + match cards
  - Operator “Record Results” quick-advance controls
- **Exports**:
  - PNG export (DOM → image)
  - WebM export (recorded frames → MediaRecorder)
- **Live Render View**:
  - Clean/no-chrome view for screensharing
  - Keyboard help overlay (toggle with `?`) and fullscreen toggle (`F`)
  - Live view receives last state via localStorage handoff

#### Design system — Implemented
- Phoenix Suns-inspired but legally safe:
  - Purple→orange gradient desert sky
  - Desert silhouettes (mountains/cacti/skyline)
  - Glass UI panels + broadcast legibility
  - Typography: Bebas Neue (display) + IBM Plex Sans (UI) + Azeret Mono (scores)

#### Testing — Completed
- Test agent results:
  - Backend: **100%** pass
  - Frontend: **95%** pass
- A file picker testability/integration issue was found and fixed:
  - Moved `data-testid="sharepoint-file-picker"` to the trigger
  - Added file count indicator + loading affordances

**Deliverables produced**
- Fully functional deployed MVP:
  - https://trivia-scoreboard.preview.emergentagent.com

---

### Phase 3 — Hardening + Operator Reliability (Next) ⏭️ PLANNED
Now that MVP is live, Phase 3 focuses on stability, workflows, and production readiness.

**User stories**
1. As an operator, I want “Latest file per venue” and better sorting so I can select tonight’s show instantly.
2. As an operator, I want a manual override editor so I can run a show if SharePoint is down.
3. As an operator, I want Live View to stay in sync with the Dashboard without refreshing.
4. As an operator, I want reliable, deterministic export (no missing fonts, consistent layout every time).
5. As an operator, I want per-round locking for tournaments so results can’t change mid-show.

**Adds / improvements**
- **SharePoint file selection quality**:
  - Sorting by date from filename or `data.date`
  - “Latest per venue” helper + quick filters
  - Optional polling + change detection
- **State persistence and Live View sync**:
  - Persist current selection + mode + aspect ratio + tournament state in MongoDB
  - Add “push” updates to Live View (SSE/WebSocket) *or* short polling
- **Tournament engine hardening**:
  - Clear round completion detection
  - Bracket lock/unlock per round
  - Better matchup labeling + champion reveal logic
- **Export reliability**:
  - Font preloading checks
  - Export duration presets (5s/8s/12s)
  - Optional server-side MP4 via ffmpeg (if required later)
- **Audit trail**:
  - Log sync events and exports (timestamp, venue, file, operator notes)

**Phase 3 testing**
- Regression tests for:
  - Reseeding correctness across multiple team counts
  - Bye handling
  - Export determinism across browsers
  - Live View syncing

---

### Phase 4 — Feature Expansion (Optional) ⏭️ PLANNED
**User stories**
1. As an operator, I want matchup cards (single game) for social posts.
2. As an operator, I want sponsor/logo slots per venue night.
3. As an operator, I want reusable theme variants (still within desert identity) for special events.

**Adds**
- Matchup-card renderer (portrait + landscape)
- Sponsor overlay configuration per preset
- Template gallery of render styles (same brand system)

---

### Phase 5 — Optional: Authentication + Roles (Only after approval) ⏭️ PLANNED
- Operator/admin roles
- Protect:
  - SharePoint sync
  - preset editing
  - tournament creation/editing

---

## 3) Next Actions
1. Add “**Latest per venue**” sorting + quick filters to the SharePoint file picker.
2. Improve **Live View persistence and syncing** (beyond localStorage handoff).
3. Add **manual override** editing for scores + bracket state (with “Revert to SharePoint”).
4. Add **round locking** for tournament mode.
5. Decide whether Phase 3 should include **server-side MP4** export (ffmpeg) or remain WebM-only.

---

## 4) Success Criteria (Updated)
- ✅ SharePoint integration works with real credentials:
  - Resolve shared folder, list venue subfolders, download and parse JSON.
- ✅ Leaderboard render:
  - Top 3 spotlighted, remaining teams animated in, readable at distance.
- ✅ Tournament render:
  - Single-elimination bracket with reseeding each round.
- ✅ Outputs:
  - Live views render correctly at **1080×1920** and **1920×1080**.
  - Exports produce **PNG** and **~8s WebM** without major glitches.
- ✅ Presets:
  - Save/load presets from MongoDB.
- ✅ Operator workflow:
  - Fetch/sync ➝ select file ➝ preview ➝ export completes quickly.
- Phase 3 success targets:
  - “Latest per venue” selection is one click.
  - Live View stays in sync during a show.
  - Manual overrides available as a fallback.
  - Tournament round locking prevents accidental changes mid-event.
