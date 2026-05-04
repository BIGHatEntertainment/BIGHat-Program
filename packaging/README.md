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

## Windows distribution

### 1. Copy the install root

Zip the whole `C:\BIG Hat\BIGHatStandalone\` tree from a reference machine
(or from a CI job that ran `scripts/build_standalone.py` + bundled an
embedded Python). Unzip it on the target machine to the same root path.
Adjust `INSTALL_ROOT` inside `packaging\start_bighat.vbs` and
`packaging\install_shortcut.vbs` if you chose a different location.

### 2. Optional Desktop shortcut

Double-click `install_shortcut.vbs`. It drops **BIG Hat Standalone.lnk** on
the current user's Desktop pointing at `start_bighat.vbs`. Safe to re-run.

### 3. Start the app

Double-click `start_bighat.vbs` (or the shortcut). The script silently runs
`python\python.exe backend\launcher.py`. No console window is shown. The
launcher:

1. Forces `BIGHAT_NATIVE_MODE=1`
2. Creates `data\*` if missing
3. Starts FastAPI at `http://127.0.0.1:8001/`
4. Opens the default browser to that URL

On first launch the React app detects `setup_complete=false` in
`system_config.json` and routes the user to the `/setup` wizard.

### 4. Auto-start on login (optional)

Put a shortcut to `start_bighat.vbs` into
`%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\` — the silent
launcher will boot the server in the background and expose it at
`http://127.0.0.1:8001/` for any browser tab to reach.

## Uninstall

Delete the install root. No registry keys, no services, no global config.

## Known gaps (deferred to V31.1)

- **Single-file installer (MSI / NSIS).** Current model is zip-and-copy.
- **Auto-update.** No update channel yet — admins replace the install root
  manually.
- **Code signing.** Unsigned `.vbs` and `.exe` raise SmartScreen warnings.
  Ship a signed bundle once the code-signing cert is provisioned.
- **Embedded Python** is Windows-specific; macOS/Linux users run from a
  venv directly. `launcher.py` itself is cross-platform.
