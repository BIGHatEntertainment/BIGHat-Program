# BIG Hat Entertainment

Standalone desktop program (React + FastAPI + MontyDB/SQLite) for trivia,
bingo, scheduling, scoreboards, and round generation. Ships as a single
installer per platform; runs entirely offline once installed.

## Layout

```
backend/        FastAPI app (single uvicorn process serves API + SPA bundle)
  native/       Local-only services: SQLite, HWID, license seats, subscription
  cloud/        api.bighat.live SaaS layer (Squarespace webhooks, license activation, Resend emails)
  routes/       Feature routers (trivia, bingo, scoreboard, roundmaker, ...)
  tests/        pytest suites (`phase{0..10}_*`)
frontend/       React (Vite/CRA) — built once into backend/static/
packaging/      Installer assets
  start_bighat.vbs                Windows launcher (boots backend, opens chromeless --app= window)
  installer/bighat-installer.nsi  Windows NSIS installer script
  macos/                          .app / .pkg / .dmg templates
scripts/        Build orchestrators (build_installer.py, build_dmg.py, build_standalone.py, publish_github_release.py)
memory/         PRD.md + CHANGELOG.md (source of truth for next agent / session)
```

## Build a release

### Windows installer

```bash
echo "31.X.Y" > backend/VERSION.txt
python scripts/build_installer.py
export GITHUB_TOKEN=<PAT with contents:write>
export GITHUB_OWNER=BIGHatEntertainment
export GITHUB_REPO=BIGHat-Program
python scripts/publish_github_release.py --replace-existing
```

### macOS — Apple Silicon (default)

```bash
python scripts/build_dmg.py                 # produces .app under dist/macos/
# Run on a macOS host for full .pkg/.dmg:
python scripts/build_dmg.py \
    --developer-id "Developer ID Application: BH Entertainment (TEAMID)" \
    --installer-id "Developer ID Installer:    BH Entertainment (TEAMID)" \
    --notarize-profile bighat
```

### macOS — Intel

```bash
python scripts/build_dmg.py --arch x86_64
```

Both Mac archs share the same `.app` template and `pkgbuild`/`productbuild`
flow; the only differences are the embedded CPython triplet and the
`pip download --platform` tags baked into `Resources/python/lib/.../site-packages/`.

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
