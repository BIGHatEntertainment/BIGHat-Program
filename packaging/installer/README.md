# BIG Hat Standalone — Signed Windows Installer Build

This subfolder holds the **NSIS-based MSI-class installer** that supersedes
the legacy zip-and-copy distribution. The output is a single
`BIGHatStandalone-Setup-<version>.exe` that:

- Installs to `C:\BIG Hat\BIGHatStandalone\` by default (configurable in
  the wizard).
- Embeds the Python runtime, the FastAPI backend, the React build, and
  the launcher in one file.
- Creates Desktop + Start Menu shortcuts pointing at the launcher
  through `pythonw.exe` (no console window).
- Optionally registers a Startup-folder shortcut (`Auto-start at login`
  section, off by default).
- Detects prior installs and **migrates `backend/data/` automatically**
  on upgrade so user data, system_config.json, and the SQLite DB
  survive.
- Writes registry entries for **Programs and Features** so users can
  uninstall through the standard Windows UI.
- Ships an `Uninstall.exe` that removes shortcuts + program files but
  **preserves `backend/data/`** unless the user deletes it manually.
- Is **Authenticode-signable** via `osslsigncode` (Linux/macOS CI) or
  `signtool.exe` (Windows).

## Files

| File | Purpose |
|------|---------|
| `bighat-installer.nsi` | NSIS source. Modern UI 2, sectioned, upgrade-aware, registry-aware, signed-friendly. |
| `../README.md` | Higher-level distribution runbook. |

The build orchestrator is `/app/scripts/build_installer.py`.

## Quick build (unsigned, dev box)

```bash
# Linux / macOS dev container (NSIS available via apt-get install nsis)
python scripts/build_installer.py
# -> dist/BIGHatStandalone-Setup-31.0.0.exe (unsigned)
```

If you don't have an embedded Python tree handy, the orchestrator will
warn and produce a runner-less installer — fine for layout testing,
not for end users.

## Production build (signed)

Provide a code-signing `.pfx` via env vars **or** flags:

```bash
export BIGHAT_SIGNING_CERT_PFX=/secrets/codesigning.pfx
export BIGHAT_SIGNING_PASSWORD='…'

python scripts/build_installer.py \
    --python-dir /opt/bighat/python311-embed \
    --timestamp-url http://timestamp.digicert.com
```

Or:

```bash
python scripts/build_installer.py \
    --cert /secrets/codesigning.pfx \
    --cert-password "$BIGHAT_SIGNING_PASSWORD" \
    --signer osslsigncode
```

CI matrix:

- **Linux (default)**: `--signer osslsigncode` — works with a `.pfx`
  exported from any CA (DigiCert, Sectigo, GlobalSign, etc).
- **Windows**: `--signer signtool` — uses the bundled `signtool.exe`
  from the Windows SDK. Same flags otherwise.

After signing, `osslsigncode verify -in dist/BIGHatStandalone-Setup-…exe`
should report `Number of verified signatures: 1`.

## Upgrade story

The installer reads `HKCU\Software\BH Entertainment\BIGHatStandalone\InstallDir`
to detect prior installs:

- **Same install dir** (default): files are overwritten in place. The
  user's `backend/data/` is untouched (NSIS only writes paths the
  installer's `File /r` lists, and `data/` is excluded from the payload).
- **Different install dir**: the new install completes, then
  `backend/data/*` from the old root is copied over only if the new
  `data/` is empty. The old install is left alone (user can uninstall
  it from Programs and Features).

## Rollback

The signed installer is the rollback unit. Each successful build is
versioned in `dist/`. To roll back:

1. Run `Uninstall.exe` (or use Programs and Features).
2. Run an earlier `BIGHatStandalone-Setup-<old>.exe`.
3. The data-migration logic copies `backend/data/` forward, so even a
   downgrade preserves user state.

## CI integration

GitHub Actions example (`.github/workflows/release.yml`):

```yaml
name: Release Windows Installer

on:
  push:
    tags: ["v*"]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: sudo apt-get update && sudo apt-get install -y nsis osslsigncode
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - uses: actions/setup-node@v4
        with: { node-version: "18" }
      - run: pip install -r backend/requirements.txt
      - run: cd frontend && yarn install --frozen-lockfile
      - name: Stage payload + build installer (signed)
        env:
          BIGHAT_SIGNING_CERT_PFX: ${{ secrets.SIGNING_CERT_PFX_PATH }}
          BIGHAT_SIGNING_PASSWORD: ${{ secrets.SIGNING_CERT_PFX_PASSWORD }}
        run: python scripts/build_installer.py --python-dir /opt/python311-embed
      - uses: actions/upload-artifact@v4
        with:
          name: BIGHatStandalone-Setup
          path: dist/BIGHatStandalone-Setup-*.exe
```

`SIGNING_CERT_PFX_PATH` should point at a path where you `cat`'d the
base64-decoded `.pfx` earlier in the job (Azure Key Vault → file is the
typical pattern).

## Verifying a release

End-user:

```powershell
# Right-click the .exe -> Properties -> Digital Signatures
# Should show "BH Entertainment" with a green checkmark.
```

Developer:

```bash
osslsigncode verify -in dist/BIGHatStandalone-Setup-31.0.0.exe
# Number of verified signatures: 1
# Signer: BH Entertainment (or whatever your CN is)
# Timestamp: <yyyy-mm-dd>
```

## Replacing the old VBS distribution

The legacy `start_bighat.vbs` + `install_shortcut.vbs` files **are still
shipped inside the installer** (they live under `<install>\packaging\`)
because the Finish-page launcher and the auto-start shortcut both invoke
`start_bighat.vbs` for its silent-launch behaviour.

You can stop publishing `.zip` snapshots once the signed installer is
the canonical release. The runtime topology and on-disk layout are
identical — the installer just automates the steps that used to be
"unzip, double-click `install_shortcut.vbs`".
