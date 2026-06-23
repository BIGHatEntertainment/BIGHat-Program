# v32.0.0-alpha.10 — Release Notes

**Highlights:** Setup Wizard "Continue offline" actually works now, license-key email reaches your inbox with a working Download button, and Intel Mac builds are back on the menu.

## Customer-visible changes

### 🔧 Setup Wizard "Continue offline" — no more cryptic `unknown_key`
When the cloud activate path returns an authoritative rejection (e.g. the cloud DB just got wiped on a redeploy and doesn't recognise your key yet), clicking the **Continue offline** button now actually accepts your setup and marks the license as `pending_cloud_activation`. The 4-hour background refresh job retries activation once the cloud catches up. Before alpha.10, this path bubbled the cloud's rejection straight to the wizard and blocked setup completion.

### 📧 License-key email Download button works
The "Download BIG Hat Entertainment" button in the purchase email used to point to `bighat.live/download` (Squarespace marketing site — 404). It now points to `api.bighat.live/api/downloads/auto` — auto-detects your OS and downloads the correct installer in a single click.

### 🖥️ Intel Mac builds ship again
This release publishes an `_x64.dmg` for Intel Macs alongside the Apple Silicon `_aarch64.dmg`. Previously only Apple Silicon was being published; the download landing page now serves both.

## Server-side / cloud changes (already live on api.bighat.live)

These were deployed independently to `api.bighat.live` and don't require this installer update:
* Squarespace Orders poller (replaces broken webhook subscriptions API)
* License DB persisted in MongoDB (no more redeploy-wipes-licenses)
* Admin `/api/license/admin/keys/{key}/resend-email` endpoint
* Always-on `/api/license/health` diagnostic
* Smart OS-aware `/api/downloads/auto` redirect

## Internal / dev notes

* Backend `VERSION.txt` and `src-tauri/tauri.conf.json` synced to `32.0.0-alpha.10`
* CI auto-syncs both files from the git tag — no manual maintenance needed
* The `.app.tar.gz` bundle in this release is the Tauri auto-updater format (not for end-user download); the resolver explicitly forbids serving it as a download

## Upgrade path

* **Fresh install:** Download from the GitHub release. Enter your license key when prompted.
* **Updating from alpha.9:** Reinstall over the existing app. Your `system_config.json` is preserved (license key, settings, master admin).
* **Customer who never received their email:** Contact support — we can now resend via the new admin endpoint without re-minting.
