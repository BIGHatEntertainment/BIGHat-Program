# BIG Hat Standalone V31 — Packaging & Distribution

This folder holds the Windows installer templates and the deployment runbook
for shipping BIG Hat Standalone to end-user machines.

## Runtime topology (production install)

```
C:\BIG Hat\BIGHatStandalone\
├── python\                 ← embedded CPython 3.11 runtime (copied in)
│   └── python.exe
├── backend\                ← backend source tree (as shipped from /app/backend)
│   ├── launcher.py         ← THE single entry point; native mode is forced on
│   ├── server.py
│   ├── static\             ← React build bundle (from `yarn build`)
│   │   ├── index.html
│   │   └── ...
│   ├── native\
│   │   └── system_config.json  ← persists local state (setup, users, license, subscription)
│   └── data\               ← created on first run by launcher.py
│       ├── bighat_db\
│       ├── assets\
│       └── generated\
├── packaging\
│   ├── start_bighat.vbs        ← silent launcher (hides console)
│   ├── install_shortcut.vbs    ← creates Desktop + Start-menu shortcuts
│   └── bighat.ico              ← (optional) branded shortcut icon
└── VERSION.txt
```

## Build sequence (developer machine, any OS)

```bash
# From the repo root (/app)
python scripts/build_standalone.py          # runs yarn install + yarn build + copies build/ into backend/static/
#  or, for incremental dev builds:
python scripts/build_standalone.py --skip-install --clean
```

This produces `backend/static/` and `backend/static/build_manifest.json`.
The backend serves everything under `/` from that folder (SPA fallback to
`index.html`) whenever the bundle is present. If `backend/static/index.html`
is missing the launcher still boots fine; the user just needs to open the
React dev server at `localhost:3000` in that case.

## Smoke-test locally

```bash
# From the repo root (/app)
python backend/launcher.py --check          # prints config + exits
python backend/launcher.py --port 18001 --no-browser &
curl -s http://127.0.0.1:18001/health       # → {"status":"healthy"}
curl -s http://127.0.0.1:18001/             # → index.html (if build exists)
```

## Windows distribution — NSIS installer (recommended)

The new pipeline produces a **single signed `.exe`** that supersedes the legacy
zip-and-copy flow.

### 1. Build it (Linux / macOS / Windows dev box)

```bash
# Prereqs: Python 3.11+, Node 18+, NSIS (`apt-get install nsis` / `brew install nsis`),
#          osslsigncode (Linux/mac, only needed for signing).
# From the repo root (/app)
python scripts/build_standalone.py        # builds the React bundle into backend/static/
python scripts/build_installer.py         # downloads embeddable CPython, runs makensis
```

That produces `dist/BIGHatStandalone-Setup-<version>.exe` (~35 MB,
fully self-contained — embedded CPython 3.11.9 is bundled).

### 2. Sign it (production CI)

```bash
export BIGHAT_SIGNING_CERT_PFX=/secrets/codesigning.pfx
export BIGHAT_SIGNING_PASSWORD='…'
python scripts/build_installer.py         # picks up the env vars and Authenticode-signs

# or pass flags explicitly:
python scripts/build_installer.py \
    --cert /secrets/codesigning.pfx \
    --cert-password "$BIGHAT_SIGNING_PASSWORD" \
    --timestamp-url http://timestamp.digicert.com
```

### 3. Common build flags

| Flag                  | Purpose                                                         |
|-----------------------|-----------------------------------------------------------------|
| `--no-embed-python`   | Skip downloading CPython (target machines must install it)      |
| `--skip-frontend`     | Reuse an already-built `backend/static/` bundle                 |
| `--skip-payload`      | Re-run `makensis` against an existing `dist/payload/` tree      |
| `--skip-makensis`     | Stage the payload only, don't compile the `.exe`                |
| `--no-sign`           | Build unsigned even if signing env vars are set                 |
| `--signer signtool`   | Use `signtool.exe` instead of `osslsigncode` (Windows CI)       |
| `--version 31.0.1`    | Override `backend/VERSION.txt`                                  |

### 4. What the installer does on the target machine

- Default install path: `C:\BIG Hat\BIGHatStandalone\`
- Optional sections (selectable on Components page):
  Desktop shortcut, Start Menu shortcut, Auto-start at login.
- Detects a previous install via `HKCU\Software\BH Entertainment\BIGHatStandalone`
  and **migrates `backend\data\` automatically** when installing into a new dir.
- Registers an uninstaller in **Programs and Features** (Publisher, Version,
  Estimated Size).
- Uninstall preserves user data under `backend\data\` and reports where it
  lives so admins can purge manually.

### 5. Legacy zip-and-copy (deprecated, still works)

The legacy `start_bighat.vbs` / `install_shortcut.vbs` workflow remains in
this folder for environments that can't run the NSIS installer (locked-down
machines, USB sneakernet). See "Manual install" below.

## Manual install (legacy)

### Copy the install root

Zip the whole `C:\BIG Hat\BIGHatStandalone\` tree from a reference machine
and unzip it on the target machine. Adjust `INSTALL_ROOT` inside
`packaging\start_bighat.vbs` and `packaging\install_shortcut.vbs` if you
chose a different location.

### Optional Desktop shortcut

Double-click `install_shortcut.vbs`. It drops **BIG Hat Standalone.lnk** on
the current user's Desktop pointing at `start_bighat.vbs`. Safe to re-run.

### Start the app

Double-click `start_bighat.vbs` (or the shortcut). The script silently runs
`python\python.exe backend\launcher.py`. No console window is shown.

## Uninstall

NSIS installer: use **Programs and Features → BIG Hat Standalone → Uninstall**.
Manual install: delete the install root.

## Known gaps (deferred)

- **macOS / Linux native packages** (`.dmg`, `.deb`, `.AppImage`) — backlog.
- **Code-signing certificate provisioning** — wired and tested with self-signed
  certs; production needs an EV cert from a trusted CA.
