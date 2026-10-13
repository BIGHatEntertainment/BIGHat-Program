# BIG Hat Entertainment

Standalone desktop program (React + FastAPI + MontyDB/SQLite, wrapped in a Tauri shell) for trivia,
bingo, karaoke, scheduling, scoreboards, and round generation. Ships as a single
installer per platform; runs entirely offline once installed.

Current release: **v32.1.1** (2026-10-13). Release numbering is `v32.x.y`; the old `alpha.N` scheme is retired.

## Layout

```
backend/        FastAPI app (single uvicorn process serves API + SPA bundle)
  native/       Local-only services: SQLite, HWID, license seats, subscription,
                data_map.py (where data lives), legal_router.py (legal acceptance record)
  cloud/        api.bighat.live SaaS layer (Squarespace webhooks, license activation, Resend emails)
  routes/       Feature routers (trivia, bingo, scoreboard, roundmaker, ...)
  tests/        pytest suites
frontend/       React (CRA) — built once into backend/static/
src-tauri/      Tauri desktop shell, installer hooks (installer-hooks.nsh), legal PDFs
packaging/      Installer assets
scripts/        Build + release helpers; scripts/release_notes/<version>.md per release
memory/         PRD.md + CHANGELOG.md (source of truth for next agent / session)
```

## Where user data lives

- **AppData** `%LOCALAPPDATA%\BIGHat\data` (macOS: `~/Library/Application Support/BIGHat/data`): `system_config.json`, local database (`bighat_db`), `legal_acceptance.json`, backups, secure ledger.
- **Documents** `Documents\BIG Hat Entertainment\Files`: files the merchant can see and edit.
- Full map: `backend/native/data_map.py`.
- The database folder is set from `MONTYDB_DATA_DIR` (launcher) by `backend/native/db_factory.py`. Do not move it without a migration for existing installs.
- Uninstall deliberately wipes `%LOCALAPPDATA%\BIGHat` (`src-tauri/installer-hooks.nsh`). Updates installed over an existing install should not.

## Legal acceptance

The Terms, Privacy Policy and California addendum are shown once. Acceptance is stored by the backend
(`/api/native/system/legal/*`, file `legal_acceptance.json`) and is asked again only on a fresh install, after an
app update (`backend/VERSION.txt` changes), or when `LEGAL_VERSION` in `frontend/src/pages/LegalAcceptScreen.jsx` is bumped.

## Build a release

Releases are built by GitHub Actions (`.github/workflows/release.yml`) when a tag matching `v32.*` or `v33.*` is pushed.

1. Merge the PR into `main`.
2. Push the tag on the merge commit, e.g. `v32.1.1`.
3. The workflow writes the tag into `backend/VERSION.txt` and `src-tauri/tauri.conf.json`, builds Windows (x64 NSIS `.exe`) and macOS (Apple Silicon `.dmg`), and publishes the release as Latest only if both installers are present. If either is missing it demotes the release to a draft.

Intel Mac builds are retired (the macos-13 runner no longer exists).

Legacy manual builders still exist in `scripts/` (`build_installer.py`, `build_dmg.py`, `publish_github_release.py`) but the tag workflow is the normal path.

Release notes for each version go in `scripts/release_notes/<version>.md`.

## Local development

```bash
# Backend
cd backend && uvicorn server:app --reload --port 8001
# Frontend
cd frontend && yarn install && yarn start
```

The supervisor stack in the preview environment runs the same processes
behind ports 8001 (backend) and 3000 (frontend).

## Read before changing the launcher

`memory/CHANGELOG.md` — top of file has the locked-in **NEVER-DO RULES**
for the Windows launcher. Touch `start_bighat.vbs` only after reading
them.
