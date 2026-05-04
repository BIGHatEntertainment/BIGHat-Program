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

## macOS distribution — `.app` / `.pkg` / `.dmg`

Mirrors the Windows pipeline. **The cross-platform parts run anywhere** (Linux,
macOS, Windows); the `pkgbuild` / `productbuild` / `hdiutil` / `codesign` /
`notarytool` steps are auto-detected and only execute on a macOS host.

### 1. Build the `.app` (any OS)

```bash
# From the repo root (/app)
python scripts/build_standalone.py        # produces backend/static/
python scripts/build_dmg.py --arch aarch64   # Apple Silicon (default)
# or:
python scripts/build_dmg.py --arch x86_64    # Intel
```

That produces `dist/macos/BIG Hat Standalone.app/` with:
- `Contents/Info.plist` (validated as a real plist after template substitution)
- `Contents/MacOS/BIGHatStandalone` shell launcher (+x, execs the embedded Python)
- `Contents/Resources/python/` — relocatable CPython 3.11.9 from
  [`astral-sh/python-build-standalone`][pbs] (sha256 verified via the GitHub
  release `.sha256` sidecar file)
- `Contents/Resources/backend/` — full backend source tree
- `Contents/Resources/packaging/`, `VERSION.txt`, `PkgInfo`

[pbs]: https://github.com/astral-sh/python-build-standalone

### 2. Sign + notarise + ship (macOS CI only)

```bash
# Configure once: store an app-store-connect API key as a keychain profile.
xcrun notarytool store-credentials bighat \
    --apple-id you@example.com \
    --team-id  TEAMIDXXXX \
    --password app-specific-password

# Build, sign, package, notarise — single command:
python scripts/build_dmg.py \
    --arch aarch64 \
    --developer-id "Developer ID Application: BH Entertainment (TEAMIDXXXX)" \
    --installer-id "Developer ID Installer: BH Entertainment (TEAMIDXXXX)" \
    --notarize-profile bighat
```

That produces:
- `dist/BIGHatStandalone-<version>.pkg` — productbuild signed install package
- `dist/BIGHatStandalone-<version>.dmg` — disk image with a drag-to-Applications symlink

Both artifacts are notarised and stapled (Gatekeeper-friendly offline).

### 3. Common build flags

| Flag                        | Purpose                                                         |
|-----------------------------|-----------------------------------------------------------------|
| `--arch aarch64`/`x86_64`   | Target architecture (default `aarch64` = Apple Silicon)         |
| `--no-embed-python`         | Skip downloading CPython (rely on system `/usr/bin/python3`)    |
| `--skip-frontend`           | Reuse an already-built `backend/static/` bundle                 |
| `--skip-pkg`                | Build only the `.app` (no productbuild)                         |
| `--skip-dmg`                | Build only the `.app` + `.pkg` (no hdiutil)                     |
| `--developer-id "…"`        | Codesign identity for the `.app`                                |
| `--installer-id "…"`        | productbuild identity for the `.pkg`                            |
| `--notarize-profile bighat` | `xcrun notarytool` keychain profile name                        |
| `--entitlements file.plist` | Entitlements for hardened runtime                               |
| `--version 31.0.1`          | Override `backend/VERSION.txt`                                  |

### 4. What the user sees on their Mac

- **DMG flow:** drag the `.app` icon onto the `Applications` symlink shown in
  the disk image. Same UX as every other Mac app.
- **PKG flow:** double-click → guided installer → `.app` lands in `/Applications`,
  postinstall script strips the quarantine xattr and creates
  `~/Library/Application Support/BIG Hat Standalone/` for user data.
- **First launch:** the app honours `BIGHAT_DATA_ROOT=$HOME/Library/Application Support/BIG Hat Standalone`,
  so the bundle stays pristine (signature-stable) across upgrades.

## Manual install (legacy Windows)

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

- **Linux native packages** (`.deb`, `.AppImage`) — backlog.
- **Code-signing certificate provisioning** — Windows pipeline tested with
  self-signed certs; production needs an EV cert from a trusted CA. macOS
  pipeline tested up to template-substitution + .app assembly; production
  needs an Apple Developer ID + a notarytool keychain profile.
