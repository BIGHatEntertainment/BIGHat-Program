# Program <-> Cloud sync plan (agreed 2026-10-20)

STATUS: Cloud Phase 1 (key accepted, /whoami, /changes) and venue assignment are deployed. Program Phase 3 (the pull, native/cloud_sync.py) is built, see CHANGELOG phase3-pull-v1. NOT built: Phase 2 item-by-item merge, Phase 4 push of claims, Phases 5-6 files.
Same file lives in BIGHat-Program and BIGHat-Cloud (memory/SYNC_PLAN.md). Keep both copies identical.

## Decision
Option A: the Cloud is the master. The Program keeps a local copy, pulls schedule, employees and venues down on a timer, and pushes back only what the host did (claims, unclaims, results).
Why: the Cloud serves a company with many hosts at many bars. The Program serves one or two bars that run on their own. The Cloud is also the backup for files (overlays, .bighat files, bingo videos) and notices when a file changes.

## Two lanes
1. DATA lane (schedule, employees, venues, pricing, venue roles): Cloud owns it. Program pulls every 5 minutes and at login using `since=<version>`. Program pushes only host actions.
2. FILE lane (overlays, .bighat files, bingo videos): Cloud holds the backup and the latest stamp. Program fetches a manifest at login, compares sha256, shows "N updates available" with Get or Replace per file. Nothing is overwritten silently; the old file is saved first.

## Rules (data safety)
- Disk first: sync state (version numbers, outbox) lives in AppData, atomic writes, damaged file kept as .bad (same pattern as cloud_link.json).
- A claim made offline waits in a saved outbox, each with an id, so a retry never double-claims.
- First link never deletes anything: show a preview, host chooses, backup before applying.
- Master admin and passwords are never synced.
- Offline is normal: the Program keeps working from its local copy. A lapsed subscription pauses sync and backup only.
- Each PC pulls only the venues the owner assigned to it (chain of venues, 2 or 3 PCs).
- Two PCs changing the same item: keep both versions and ask. Never last-writer-wins.
- Karaoke videos (yt-dlp) are never backed up. Only venue images are needed from the Cloud for karaoke.

## .bighat format (what exists today)
- backend/routes/bighat_files.py: format "bighat", version 2, zip with manifest.json, payload.json, assets/, optional signature.txt. Types: round, presentation, bingo, scoreboard. 50 MB cap per file. New type = one registry entry.
- backend/native/setup_package.py: a SEPARATE format ("bighat-setup-package", .bighatsetup) with a built-in preview (plan_apply). Refers to venues by name and people by email. Never includes passwords or keys.
- src-tauri/src/lib.rs route_for_bighat only knows round, presentation, pack, bingo.
- Decision: make the setup file a real .bighat of type "setup" (one format, one brand). Old .bighatsetup stays readable.
- Missing for sync: manifest has no stable id, revision or fingerprint.

## Phases (each its own small PR)
- 0. CONTRACT: one page both agents work from. Manifest additions: item_id (permanent), revision (+1 per save), sha256 (payload and assets), updated_at, updated_by, source (program:<pc code> or cloud). Endpoints, all authenticated with the Program access key: GET /api/program/manifest?since=n, GET /api/program/items/{id}, PUT /api/program/items/{id}, GET /api/program/changes?since=n. Conflict rule as above. NEXT STEP.
- 1. CLOUD accepts the Program access key (today NO route does; token is stored hashed and unused). Blocker for everything.
- 2. PROGRAM first link: merge with a preview, item by item, OR download a .bighat setup file to carry it over. Backup first.
- 3. PROGRAM ongoing pull on a timer (venues, employees, schedule).
- 4. PROGRAM push of claims and results via the outbox.
- 5. FILES manifest and the "updates available" notice at login.
- 6. FILES backup upload to the Cloud (real file storage, not the database; chunked upload for large files).

## Known gaps found 2026-10-20 (read-only investigation)
- Program never calls the Cloud after linking: get_token() has no callers.
- Cloud data routes accept only a browser login cookie. /api/program/sync, /pull, /push are 404.
- Setup Package calls /api/setup-package/* on api.bighat.live; that path returns 404 on both api.bighat.live and host.bighat.live. It was built for a server that was never deployed. The banner "could not do that right now" is this. Retire or re-point it as part of phase 2.
- "Connected" on both screens only means the handshake finished.
- Data shapes differ: Program keeps users in system_config.json plus a local DB; Cloud scopes everything by account_id.
- The Cloud's schedule is a separate copy from the Program's local schedule.
- Signature (HMAC) returns nothing when no signing key is set. Treat it as branding only; real trust is sha256 plus the access key.
- Largest files are bingo videos, 25 to 35 MB each. Fits the 50 MB cap for now.

## Where to pick up
Program: after Phase 3 is merged and tested against the real Cloud, build Phase 4 (outbox + POST /api/program/actions; Cloud side must exist first). Cloud still needs POST /api/program/actions, /snapshot and /manifest. Phase 2 (preview item by item) can replace the all-or-nothing Apply button.
