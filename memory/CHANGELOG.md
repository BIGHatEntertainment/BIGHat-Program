# BIG Hat Entertainment — CHANGELOG

> **For the next agent: READ THIS BEFORE TOUCHING THE LAUNCHER.**
> The most recent entry describes how the app actually launches today.
> Older entries describe approaches that have been ripped out — they
> ARE NOT a fallback and must not be reinstated.

---

## 2026-06-23 — Phase 10.8: download-link fix + asset-resolver hardening

**P0 customer-facing bug:** First real Squarespace buyer (sellards@bighat.live,
license `BHE-E7GX-VGTT-TGGP-8S2G`) received the license email — pipeline
end-to-end works! — but the "Download BIG Hat Entertainment" button linked
to `https://bighat.live/download`, which is the Squarespace marketing
site and returns a 404 page. The actual download landing + smart redirect
live on `api.bighat.live`, not on the marketing domain.

### Fixes
1. **`backend/cloud/email_service.py`** — the license-key email's HTML
   button + text body now point to
   `{LICENSE_API_BASE_URL}/api/downloads/auto?key={key}` (smart OS-aware
   redirect to the right GitHub Releases artifact). The manual-pick
   fallback link goes to `{LICENSE_API_BASE_URL}/download`. The
   Squarespace `bighat.live/download` 404 URL is now permanently banned
   from email templates by regression test.

2. **`backend/.env`** — added `GITHUB_OWNER=BIGHatEntertainment` and
   `GITHUB_REPO=BIGHat-Program`. Before this, the resolver fell back to
   default version "31.0.0" with null artifact URLs, so the email's
   download link would have bounced to `/download?missing=windows`.

3. **`backend/cloud/downloads_resolver.py`** — full rewrite of the
   asset-name matcher. The old naive substring match conflated:
   * Windows `_x64-setup.exe` ↔ macOS Intel (both contain "x64")
   * macOS Apple `_aarch64.dmg` ↔ Tauri updater `_aarch64.app.tar.gz`
     (both contain "aarch64")
   New rules are extension-aware + forbid-list-aware + needle-aware
   with self-identifying-extension fallback:
   * `.exe`/`.msi` is ALWAYS Windows (no arch needle required)
   * `.dmg`/`.pkg` is ALWAYS macOS (arch needle disambiguates aarch64 vs intel)
   * `.zip` is ambiguous — needle required to disambiguate
   * `.tar.gz` is FORBIDDEN for end-user downloads (Tauri updater format)

4. **Tests:**
   * `backend/tests/test_phase10_8_email_download_links.py` (6 tests) —
     locks in the email URL contract. `bighat.live/download` is now
     a banned substring; CI will fail any future refactor that
     reintroduces it.
   * `backend/tests/test_phase10_8b_downloads_precision.py` (8 tests) —
     uses real v32.0.0-alpha.9 asset names as fixtures. Asserts that:
       - Windows UA never gets the `.dmg`
       - macOS UA never gets the Windows `.exe`
       - macOS Apple never gets the Tauri `.app.tar.gz` updater
       - `?platform=macos_intel` returns missing (no false fallback to .exe)
   * **93/93 cloud + setup + downloads + poller tests green.**

### Live verification (preview pod against real GitHub release)
```
$ curl /api/downloads/auto -A "Windows" → .../v32.0.0-alpha.9_x64-setup.exe  ✓
$ curl /api/downloads/auto -A "Apple Silicon Mac" → .../v32.0.0-alpha.9_aarch64.dmg  ✓
$ curl /api/downloads/auto?platform=macos_intel → /download?missing=macos_intel  ✓
```

### Lifetime-key activation guarantee
Verified end-to-end that a `owns_standalone=true` license is permanent:
* No expiration date on the LicenseKey model for standalone tier
* `activate()` and `validate()` have NO expiry checks for standalone
* 30-day offline grace covers transient network failures
* Standalone features (`story_generator_enabled`) are hard-coded as
  never-network-gated in `subscription.is_premium_active()`
* Phase 10.7's cloud-mode-wins-over-native-mode fix prevents the
  redeploy-wipes-license-DB bug from recurring.

### What customers experience now
1. Buy on Squarespace → poller picks up the order within 120s
2. Resend emails the key + a working download button
3. Click the button → auto-redirects to the right binary for their OS
4. Install + activate → key is bound (lifetime) + features unlocked
5. Future redeploys preserve all keys (MongoDB persistence)



## 2026-06-23 — Phase 10.7: production data-loss + offline-setup hot-fix

**P0 production-data-loss bug.** User installed v32.0.0-alpha.9, entered
the real license key `BHE-D6P3-8UM2-VS3E-AK69` I had minted on prod just
30 min earlier, and got **"We don't recognise that license key."** Then
the "Continue offline" path also failed with `unknown_key` at the very
end of setup.

### Root causes (two distinct bugs)
1. **Prod was running with BOTH `BIGHAT_CLOUD_MODE=1` AND
   `BIGHAT_NATIVE_MODE=1`.** The DB-factory check at server.py:62
   prioritised native mode, so prod's license database was a **MontyDB
   SQLite file inside the Kubernetes container's ephemeral filesystem.**
   Every redeploy → new container → SQLite file destroyed → every
   minted license vanishes. The user's redeploy to push the poller
   wiped the key I had minted earlier in the same session.
2. **"Continue offline" wasn't actually offline.** The Setup Wizard's
   `/api/native/setup/initialize` endpoint always called the cloud's
   authoritative `activate` path. Only `timeout` / `network_error` /
   `server_error` were tolerated as offline-deferrable. An authoritative
   `unknown_key` (e.g. from a wiped DB) was treated as a hard 400 reject,
   even when the user explicitly clicked the WifiOff button.

### Fixes shipped
1. **`backend/native/db_factory.py`** — added `_is_cloud_mode()` and made
   cloud mode ALWAYS win over native mode for DB selection. When both
   env vars are set, MongoDB is used (persistent across redeploys) and
   a loud `DB MODE: BIGHAT_NATIVE_MODE=1 IGNORED because BIGHAT_CLOUD_MODE=1`
   banner is logged at boot. The cloud pod can now safely have either or
   both env vars set and still persist licenses correctly.

2. **`backend/native/router.py`** — added `offline_mode: bool = False`
   to `SetupInitRequest`. When true, `/setup/initialize` skips the
   cloud activate call entirely, persists locally, and marks
   `pending_cloud_activation=True` so the 4-hour background refresh
   job retries activation once the cloud is reachable.

3. **`frontend/src/pages/SetupWizard.jsx`** — the "Continue offline"
   button now sets `verify.state = 'offline'`, and the submit handler
   passes `offline_mode: (verify.state === 'offline')` to the backend.

4. **`backend/cloud/health_router.py`** — `/api/license/health` now
   reports `effective_db_mode: "mongodb" | "montydb-sqlite"` and
   `native_mode_override_active: bool` so the operator can verify the
   cloud-wins-override took effect with a single curl. The
   `BIGHAT_NATIVE_MODE+CLOUD_MODE` conflict is no longer a `blocker`
   (the override handles it safely) but still surfaces in `modes`.

5. **`backend/server.py`** — cloud-mode server pods now skip mounting
   `/api/native/*` entirely (those endpoints exist for the desktop
   installer to call its OWN local sidecar, not for end users to hit
   api.bighat.live with).

6. **`backend/tests/test_phase10_7_offline_setup_and_db_mode.py`** —
   **7 new tests** locking in:
   * `offline_mode=true` skips cloud_client.activate entirely
   * `offline_mode` overrides authoritative `unknown_key` rejection
   * `offline_mode=false` (default) still surfaces `unknown_key` as 400
   * Network errors still auto-fall-back to offline-tolerant even
     without the explicit flag
   * `BIGHAT_CLOUD_MODE=1` overrides `BIGHAT_NATIVE_MODE=1` for DB
   * Native mode alone still uses MontyDB
   * Cloud mode alone uses MongoDB

### Result
**112/112 cloud + setup + poller tests green.** After the next prod
redeploy, license keys will persist across redeploys (in MongoDB) AND
the desktop's "Continue offline" button will actually let the customer
through even when the cloud is rejecting the key.



## 2026-06-22 — Phase 10.6: Squarespace Orders poller (webhooks → polling)

**Decision:** Webhooks are dead, polling is in.

Squarespace's static API key (the kind a merchant generates via Settings →
Developer Tools → API Keys) is NOT allowed to create webhook subscriptions.
The `POST /1.0/webhook_subscriptions` endpoint requires an OAuth access
token, which in turn requires building a full Squarespace Extension and
shipping it through the Developer Platform — heavy overhead for a single-
merchant setup. Polling the Orders API every 2 minutes using the existing
static API key is more reliable anyway:

  * Naturally idempotent on `order.id`
  * Catches orders made while the service was down
  * No HMAC signature verification needed
  * No "missed webhook" failure modes
  * Works retroactively (just widen the time window to replay history)

### What shipped
- **`backend/cloud/squarespace_poller.py`** — the poller:
  * `resolve_tier(product_id, product_name)`: maps Squarespace line items
    to license tiers via `LICENSE_PRODUCT_MAP` env (productId→tier) with
    productName substring fallback. Default map includes the live
    standalone productId `69f95125f691fe20c13aef37`.
  * `process_order(order)`: idempotent on `order.id`, multi-SKU aware,
    routes to `mint_standalone_purchase`, `mint_addon_purchase`, or
    `mint_cloud_subscription`.
  * `fetch_orders()`: paginated Squarespace `/commerce/orders` client.
  * `run_once()`: full cycle with persisted high-water mark
    (`license_poll_state` collection).
  * `poll_forever()`: background `asyncio.create_task` started at app
    boot when `BIGHAT_CLOUD_MODE=1` + `SQUARESPACE_API_KEY` is set.

- **`backend/cloud/poller_router.py`** — JWT-gated admin endpoints:
  * `GET /api/license/admin/poller/status`
  * `POST /api/license/admin/poller/run`         (trigger run-once)
  * `POST /api/license/admin/poller/replay/{order_id}`  (force re-mint)

- **`backend/cloud/config.py`** — new env vars:
  * `SQUARESPACE_POLL_INTERVAL_SECONDS` (default 120)
  * `SQUARESPACE_POLL_LOOKBACK_HOURS` (default 168 = 7d backfill)
  * `LICENSE_PRODUCT_MAP` (JSON: `{"<productId>":"<tier>"}`)
  * `SQUARESPACE_API_BASE` (overridable for tests)

- **`backend/cloud/squarespace_webhook.py`** — fixed HMAC signature
  verification: Squarespace's secret is HEX, must be `bytes.fromhex(secret)`
  not `secret.encode("utf-8")`. (Only matters if you ever do switch back
  to webhooks via an Extension.)

- **`backend/tests/test_phase10_6_squarespace_poller.py`** — 12 tests:
  productId-map precedence, productName fallback, merch-skipping,
  mixed-cart routing, real-shape order #38 fixture, high-water mark
  advancement, HTTP-error resilience, MontyDB `_id` immutability fix.

### Manual mint hot-fix for order #38
Order #38 (`sellards@bighat.live`, $49.99, 2026-06-22) was minted manually
via `/api/license/admin/keys/mint` while polling was being built →
key `BHE-D6P3-8UM2-VS3E-AK69` emailed via Resend from production.

### Result
**83/83 cloud + license + setup-wizard tests green.** Every future
Squarespace purchase is automatically minted within 2 minutes and the
license email is sent via Resend. Idempotency is locked-in: no order
will ever be double-minted no matter how many times the poller restarts
or how many times Squarespace returns the same order in subsequent polls.



## 2026-06-22 — Phase 10.5: production webhook → email pipeline hardening

**P0 prod bug:** Squarespace buyers were not receiving license-key emails.
Root cause confirmed by curl-probing `api.bighat.live`:

```
$ curl -X POST https://api.bighat.live/api/license/activate -d '{}'
HTTP 405  (Allow: GET)
$ curl https://api.bighat.live/api/health
{"status":"unhealthy","database":"'MontyCollection' object is not callable"}
$ curl https://api.bighat.live/api/downloads/latest
{"detail":"not_found"}
```

Prod was running with `BIGHAT_NATIVE_MODE=1` (the desktop env file) and
`BIGHAT_CLOUD_MODE` unset, so the entire `/api/license/*` and
`/api/squarespace/webhook` router never mounted, and the DB was the
local MontyDB SQLite shim instead of MongoDB. Every customer purchase
fired the Squarespace webhook into a `405 Method Not Allowed`.

**The mistake was operational, not architectural** — `LicenseService.mint_*`
already calls `email.send_license_key_email` on the success path, with
idempotency and multi-SKU support. But the routes hosting that code
weren't loaded.

### Fixes shipped
1. **`backend/cloud/health_router.py`** — new always-on `/api/license/health`
   diagnostic. Registered UNCONDITIONALLY in `server.py` so an operator
   can `curl` the prod pod and see, in one JSON response, which env
   var is missing. Returns `ready: bool` rollup + human-readable
   `blockers` array + redacted prefixes of Resend / Squarespace keys.

2. **Loud startup banner in `backend/server.py`** — prints a 5-line
   `CLOUD LICENSING SERVICE: ONLINE/OFFLINE` block at boot. The
   OFFLINE variant tells the operator exactly what to set. The router
   mount `try/except` now `logger.error` + `logger.exception` when
   cloud mode is on but the import fails — silent warnings are how
   this bit prod.

3. **`packaging/PRODUCTION_DEPLOY_CHECKLIST.md`** — single source of
   truth for what `api.bighat.live` needs (env vars, Squarespace
   webhook config, Resend domain verification, post-deploy smoke
   tests).

4. **`backend/tests/test_phase10_5_webhook_email_pipeline.py`** — 8 new
   tests, all green:
   * `/api/license/health` returns 200 with blockers when cloud is off
   * `/api/license/health` returns `ready:true` only with every secret
   * Resend key prefix is redacted in the diagnostic response
   * Signed Squarespace `order.create` → mint + 1 email fired
   * Replay is idempotent (no second email)
   * Bad signature → 401, no mint
   * Multi-SKU cart (standalone + music_bingo + karaoke + cloud library
     in one order) → all tiers persisted, one summary email
   * Missing `RESEND_API_KEY` → mint succeeds, no-op email logs warning

5. **Full regression**: 107/107 cloud + license tests pass.

### Next action for the user
Set the following env vars on the Emergent prod pod for `api.bighat.live`
and redeploy:

```
BIGHAT_CLOUD_MODE=1
# unset BIGHAT_NATIVE_MODE
SQUARESPACE_WEBHOOK_SECRET=<from Squarespace admin>
RESEND_API_KEY=re_<prod key>
JWT_SECRET=<256-bit hex>
ADMIN_EMAIL=sellards@bighat.live
ADMIN_PASSWORD=<strong>
```

Then verify with `curl https://api.bighat.live/api/license/health | jq .ready`
— must be `true`.

Deployment_agent re-ran on 2026-06-22 and reports **PASS** — no remaining
blockers, supervisor.conf is auto-generated by Emergent (the previous
"missing supervisor config" alert was a false positive on the desktop-
codebase scan).



## NEW DIRECTION (locked in by user 2026-06-21) — Tauri native shell

The browser-tab + VBS launcher model is being retired. The user's
target experience is **LYRX-style**: a single chromeless desktop
window with no browser chrome whatsoever, launched from a desktop
icon. v32.0.0 ships the **Tauri** shell that replaces the VBS launcher
and `webbrowser.open_new()` entirely.

Until v32.0.0 lands, **v31.x continues to ship the VBS → default-browser
launcher** and must remain stable. All NEVER-DO RULES below still apply
to v31.x; v32.0.0 supersedes them by replacing the launcher entirely.

---

## NEVER-DO RULES (locked in by user 2026-05-20, scoped to v31.x)

1. **THE v31.x APP MUST NEVER OPEN IN A REGULAR BROWSER TAB without
   the user's default-browser approval.** This was relaxed in v31.0.6
   to "default-browser handoff IS acceptable" because the chromeless
   `--app=` mode caused two customer-blocking blank-screen incidents
   (v31.0.3 and v31.0.13). v32.0.0 (Tauri) is the long-term answer.

2. **DO NOT REINSTATE `msedge.exe --app=URL`, Chrome `--app=`, or
   `pywebview` ANYWHERE in the v31.x launcher chain.** Guarded by
   `backend/tests/test_launcher_vbs_contract.py`.

3. **The launch sequence MUST be: spawn backend → wait for port →
   open browser/window.** Not "spawn backend AND open in parallel" —
   that's the race that broke v31.0.3. `packaging\start_bighat.vbs`
   owns this sequencing in v31.x; the Tauri shell will own it in
   v32.0.0.

4. **THE INSTALLER'S FINISH-PAGE CHECKBOX MUST AUTO-LAUNCH THE APP.**
   v31.0.4 had the run-function defined but it didn't fire. Today it
   uses the direct `MUI_FINISHPAGE_RUN` + `MUI_FINISHPAGE_RUN_PARAMETERS`
   pattern, which is the reliable NSIS MUI 2 idiom.

---

## v31.0.15 — 2026-06-21 (Critical: blank window — undefined `<Cloud />` icon)

**User report**: "the newest release still shows up blank in the window.
there's a blue background and then absolutely nothing." Console
screenshot exposed the true root cause that v31.0.14 missed:

```
Uncaught ReferenceError: Cloud is not defined
    at $Q (SetupWizard.jsx:573:24)
```

### Root cause

`SetupWizard.jsx` line 573 rendered `<Cloud />` (a lucide-react icon)
but never imported `Cloud`. React threw immediately on mount → blank
page (the deep-blue background is `body { background-color: #000e2a }`
from `index.css`, painted before React errors out).

Why didn't the previous build catch it? **`frontend/craco.config.js`
overrode the eslint config to ONLY enable `react-hooks/recommended`,
silently dropping `react/jsx-no-undef` and `no-undef` from the
release-build's lint pass.** A second instance of the same bug
(`locationName` referenced in a `catch` after being declared in `try`
at `PresentationMode.jsx:271`) was hiding in the same blind spot.

### Fix

1. `frontend/src/pages/SetupWizard.jsx` — added `Cloud` to the
   `lucide-react` imports.
2. `frontend/src/components/trivia/editor/PresentationMode.jsx` —
   hoisted `locationName` out of the `try` block so the `catch`
   branch can reference it.
3. `frontend/craco.config.js` — pinned `no-undef` and
   `react/jsx-no-undef` as hard ESLint errors for the build, plus
   declared the browser/node/jest globals the codebase actually uses.
   A missing import now FAILS the build, not the customer's machine.
4. `backend/tests/test_frontend_no_undef.py` — new pytest that runs
   ESLint 9 in flat-config mode and fails on any `no-undef` /
   `react/jsx-no-undef` violation. Self-verified: when `Cloud` is
   removed, the test fails with the exact line that caused this
   incident.

### Release

- VERSION bumped to 31.0.15.
- Frontend bundle rebuilt with `REACT_APP_BACKEND_URL=""` (new hash
  `main.8333f78f.js`) — verified the JS now contains an import for
  `Cloud` and renders the SetupWizard without throwing.
- v32.0.0 (Tauri) work begins in parallel — see next section.

---

## v32.0.0 — IN PROGRESS — Tauri native shell

User reference image: LYRX karaoke software (provided 2026-06-21). The
target is a fully chromeless, single-window native app launched from a
desktop icon — no browser, no tabs, no URL bar.

### Architecture

- `src-tauri/` — Rust + Tauri 2.x project. Spawns the Python backend
  as a sidecar, polls `127.0.0.1:8001`, then loads the React app in a
  borderless WebView2 (Windows) / WKWebView (macOS) window.
- Frontend (React) is unchanged — the same `frontend/build/` bundle
  is loaded over `http://127.0.0.1:8001/` so all FastAPI routes work
  identically to v31.x.
- VBS launcher is retired in v32.0.0. The `.bighat` file association
  rewires to `BIGHatTauri.exe %1` instead of `wscript.exe ... %1`.
- Build pipeline: GitHub Actions on Windows + macOS runners produce
  `BIGHatEntertainment-Setup-{version}.exe` (MSI/NSIS via Tauri
  bundler) and `BIGHatEntertainment-{version}.dmg`. Local
  `publish_github_release.py` is replaced by the Actions
  `release.yml` workflow.

### Status (2026-06-21)

- [x] User approved Path A (GitHub Actions builds)
- [x] `src-tauri/` scaffold (Cargo.toml, tauri.conf.json, main.rs)
- [x] `.github/workflows/release.yml` (build + release on tag push)
- [x] Sidecar builder (`scripts/build_sidecar.py`) — PyInstaller freezes
      `backend/launcher.py` per Rust target triple
- [x] **Phase 2 (2026-06-21): Chromeless title bar.** `tauri.conf.json`
      now has `decorations: false` on the main window. New
      `frontend/src/components/TitleBar.jsx` renders a 36px slim dark
      navy bar with hat logo + "BIG HAT ENTERTAINMENT" wordmark on the
      left, and minimize/maximize/close buttons on the right. Whole bar
      is `data-tauri-drag-region` except the buttons. Auto-detects
      Tauri runtime so dev-preview browsers stay clean. `splash.html`
      mirrors the same chrome with vanilla JS+CSS. Self-tested via
      Playwright with a fake `window.__TAURI__` global — title bar
      renders, body padding pushes routes down, all three controls
      expose the right `data-testid` hooks. Locked by
      `backend/tests/test_tauri_titlebar_contract.py` (4 checks).
- [ ] File-association handoff (`.bighat` double-click) — Rust
      `extract_open_file_arg()` already in place; needs end-to-end test.
- [ ] Migration installer that uninstalls v31.x cleanly before placing
      the Tauri build.

### Pending issue from v31.0.15 customer test (deferred to v32 cycle)

After installing v31.0.15 on a clean Windows machine, the user's React
app mounted (verifying the `Cloud is not defined` fix) but axios calls
to `/api/native/info` returned `Network Error` (no response from
127.0.0.1:8001 after 5 retries). Crash log was EMPTY → uvicorn didn't
raise an exception. Likely causes: (1) uvicorn cold-start race where
the VBS launcher's port-bound check passes before all routes finish
registering, (2) Windows Defender / firewall intercepting localhost
connections to embedded Python on first run, (3) some
process-tree-related quirk specific to `wscript.exe + pythonw.exe`
spawning. The user chose to deprioritise this and skip ahead to v32.0.0
since the Tauri shell will spawn the backend differently (PyInstaller
single-binary sidecar via Rust, not pythonw.exe via VBS), making the
underlying cause moot for the v32 release. Re-investigate ONLY if v32
Phase 1 (first end-to-end CI build) hits the same Network Error.

---



## v31.0.14 — 2026-05-27 (Critical: blank window on launch — Edge `--app=` mode regression)

**User report**: "Just redownloaded the newest version. Loaded the
files and launched the window but the window displayed nothing." —
screenshot showed a chromeless "BIG Hat | Host" window with a solid
deep-blue background and no content.

### Root cause

Two contributing failures:

1. **`packaging/start_bighat.vbs` was using Microsoft Edge's `--app=URL`
   chromeless mode again.** The v31.0.6 CHANGELOG explicitly listed
   this as a NEVER-DO RULE after an ERR_CONNECTION_REFUSED race +
   the user's hand-tested "no more browser windows (Edge/Chrome)"
   approval of the default-browser path. Some intervening change
   re-introduced `--app=` and the canonical-launch rule was never
   enforced in CI, so it slipped through.

2. **The `--app=` window suppresses the JavaScript console by default**
   (no F12 in chrome `--app=` mode), so any runtime issue in the
   chromeless window renders as a blank page with no visible
   diagnostic for the customer. The user has no way to report what
   actually went wrong.

### Fix

* `packaging/start_bighat.vbs` reverted to the v31.0.5/v31.0.6
  user-approved path: `WshShell.Run TARGET_URL, 1, False`. The app
  now opens in the user's default browser (Chrome / Edge / Safari /
  Firefox) as a regular tab with the URL bar and DevTools accessible.
* The deep-link handoff branch (when a second launch happens while
  the backend is already running) was also using `--app=` plumbing.
  Same fix: just hand off to the default browser.

### Guardrail (NEW)

`backend/tests/test_launcher_vbs_contract.py` — four assertions that
fail if anyone reintroduces `--app=`, `msedge.exe` path lookup,
`chromiumExe` plumbing, or `pywebview` references into the VBS, OR
if the canonical default-browser launch line is removed. The test
strips VBS comments before scanning, so the NEVER-DO commentary in
the file itself doesn't trigger a false positive.

### Slack/Discord-style native window — what would it actually take?

A truly chromeless BIG Hat window (Slack/Discord aesthetic) is NOT
the same thing as `--app=` mode. The user-approved future path for
that is **Tauri** (or Electron) — a real native window wrapping the
existing React + FastAPI stack, +15 MB binary, ~2-3 days of work.
The `--app=` mode tried to be Tauri-on-the-cheap and the result is
the chromeless window appearing but being functionally broken
(invisible JS errors, AppData quirks). Tauri remains in the backlog
as an explicit P2 task — see `memory/PRD.md`.

### Verified

* `pytest tests/test_launcher_vbs_contract.py -v` — 4/4 green
* `7z t BIGHatStandalone-Setup-31.0.14.exe` — `Everything is Ok`,
  13,245 files
* Anonymous public download tested — same SHA256 as the local exe
* All 4 v31.0.14 artifacts pass the new pre-flight integrity gate
  in `publish_github_release.py`

### Customer remediation

Anyone on v31.0.13 should redownload v31.0.14 from
`https://github.com/BIGHatEntertainment/BIGHat-Program/releases/latest`.
Their license / setup state on disk is preserved across the
reinstall — no need to re-run the Setup Wizard.

---



**User decision**: premium content packs will be sold as `.bighat`
files on Squarespace going forward, so the SharePoint-backed file-cloud
distribution feature is no longer needed and is being removed entirely.

### What was deleted

* `backend/native/sync_router.py` — the `/api/native/sync/*` endpoints
  (pull, push, plan, status, manifest).
* `backend/native/sync_service.py` — the SharePoint pull/push manifest
  walker.
* `backend/tests/test_phase7_sync_native.py` — sync test suite.

### What was simplified

* `backend/native/asset_factory.py` rewritten as a thin shim that
  always returns `LocalAssetService`. `can_use_cloud()` always returns
  `False`. The 12 route files that import it continue to compile
  unchanged — they now silently take the local branch instead of the
  SharePoint branch when their gate flag is on. The HOST's own
  internal SharePoint integration (Round Maker upload, Slide Fetcher,
  Story Builds) is NOT touched — those use `sharepoint_service.py`
  directly via their own env-driven setup.
* `backend/native/subscription.py` — `cloud_sync_enabled` removed
  from `ALL_FEATURES`.
* `backend/native/config.py` — `cloud_sync_enabled` removed from the
  default config; `load_config()` scrubs the dead key from existing
  `system_config.json` on load so customers upgrading from v31.0.12
  get a clean state automatically.
* `backend/native/router.py` — removed `cloud_sync_enabled` from
  the `SubscriptionUpdateRequest` body, from the cloud-response
  mirror logic, and from the `/subscription` POST allow-list.
* `backend/server.py` — sync router mount commented out.
* `frontend/src/context/NativeContext.js` — docstring updated.
* `frontend/src/pages/SetupWizard.jsx` — "Cloud Library" tier badge
  removed from license-verify success view AND the all-set-up screen.
  Trivia-source picker collapsed from `local | cloud` to local-only
  (disabled). Removed unused `Cloud`, `CloudOff`, `formatExpiry`
  helpers.

### What was preserved (Option B from the user's choice menu)

* `api.bighat.live/api/license/activate` — still required for purchases.
* `/api/squarespace/webhook` — still mints license keys on purchase.
* Resend email integration — still emails license keys.
* HWID + seat-binding logic — still prevents over-deployment.
* `/api/downloads/auto` + `/download` landing page — still routes
  buyers to the right installer.
* `cloud_library_active` flag in the cloud's `/license/activate`
  response — still mirrors into `tier` and `sharepoint_enabled`
  for the host's own SharePoint feature gate.
* Setup wizard cloud-activation retry job (every 4h).

### Tests updated

* `tests/test_phase10_2_desktop_cloud_wireup.py` — removed
  `cloud_sync_enabled` assertions, replaced with
  `sharepoint_enabled` checks. 18/18 still green.
* All 112 license/cloud/credential/.bighat tests green.

### Customer-facing changes

Existing customers upgrading from v31.0.12 → v31.0.13:

* If they had no premium subscription: nothing changes.
* If they had `cloud_sync_enabled` premium: the flag is scrubbed on
  next boot. No content disappears from their local install — content
  was already mirrored locally by the sync system. Future cloud
  content (the unfilmed feature) won't arrive; .bighat packs from
  Squarespace replace it.

### Operator action items

1. **Stop accepting purchases on Squarespace for Cloud Library
   subscriptions** (if any were ever set up). Set the SKU to
   `unavailable` or repurpose for the new .bighat pack store.
2. If you had `BIGHAT_SHAREPOINT_*` env vars set on api.bighat.live
   purely for cloud-library content delivery, you can unset them.
   Keep them set if the host (you) still uses SharePoint for your
   own asset library.

### Build + ship

Same as before. All four artifacts at
`https://github.com/BIGHatEntertainment/BIGHat-Program/releases/tag/v31.0.13`.

---



**Feature**: Customers can now export Round Maker rounds, full trivia
presentations, bingo cards, and scoreboard themes as portable
`.bighat` files. Email them, back them up, sell them, double-click
to re-import. The Phase 10.7 v1 round-only format is now v2 with
multi-type support and HMAC signing for paid round packs.

### Backend (`backend/routes/bighat_files.py`)

* `BIGHAT_TYPES` registry maps a content-type string to its MongoDB
  collection + asset fields. Adding a new exportable type is one
  registry entry + (optionally) one helper. Today: `round`,
  `presentation`, `bingo`, `scoreboard`.
* `GET /api/bighat-files/types` — frontend introspection.
* `GET /api/bighat-files/export/{id}` — legacy v1 path (Round Maker
  uses this).
* `GET /api/bighat-files/export/{type}/{id}` — new v2 type-aware path.
* `POST /api/bighat-files/import` — multipart upload; rehydrates the
  document under a fresh UUID and marks `imported_from: ".bighat"`.
* `POST /api/bighat-files/inspect` — preview a `.bighat` before
  committing. Lets the frontend show "you're about to import 'X' —
  Y rounds, signed by BIG Hat Entertainment" before any DB write.
* `POST /api/bighat-files/import-from-path` — local-loopback only;
  used by Windows file association so double-clicking a `.bighat`
  in Explorer hands it off to the running app.
* HMAC-SHA256 signing under `BIGHAT_SIGNING_KEY` env var. When a
  signing key is set on the publisher side, every exported file
  includes `signature.txt` covering `manifest + payload + asset hashes`.
  When set on the importer side, signed files are verified before
  ingest — mismatched signatures get a 400 with "signature mismatch
  — file may be tampered or signed by a different publisher".
  Customers don't have the publisher key, so they can verify packs
  they bought from bighat.live but can't forge them.
* `MAX_BIGHAT_BYTES = 50 MB` hard cap.
* `BIGHAT_VERSION = 2` — v1 files (`format: bighat/round`, `round.json`
  payload) are still importable. v3+ files from a future release
  fail with a clear "update the app" message instead of partial
  import.

### Frontend (`frontend/src/components/BIGHatFileButtons.jsx`)

* Single reusable component. Pass `type` (one of 4) and optionally
  `itemId` + `itemName`. Renders an Export button (only when itemId
  is set) and an Import button. Import flow:
  1. User picks a `.bighat` file from disk.
  2. Frontend POSTs to `/inspect` and shows a confirmation modal
     with name, type, asset count, signed/unsigned badge, source
     version, and file size.
  3. User confirms → POST to `/import` → toast success → optional
     `onImported(result)` callback so the parent can refresh its list.
* Wired into:
  * `pages/trivia/TriviaDashboard.jsx` — header (import only — for
    bulk re-importing shared presentations).
  * `pages/bingo/Lobby.jsx` — under the page title.
  * `pages/scoreboard/ScoreboardDashboard.js` — top bar next to the
    SYNCED indicator.
  * Round Maker Dashboard already had per-row Export/Import buttons
    from the v1 Phase 10.7 release — those keep working unchanged.

### Tests (`backend/tests/test_bighat_files_v2.py`)

10 cases — round-trip for all four content types, `/inspect`
preview, signed-import-with-matching-key, signed-rejected-with-key-
mismatch, forward-compatibility future-version error, oversize file
rejection, types registry. All 13 file-format + credential tests
green alongside the other 102 suite tests.

### Cleanup (related)

* Removed the obsolete `frontend/public/downloads/` mirror step from
  `scripts/build_dmg.py` (already removed from `build_installer.py`
  in v31.0.10). Another process was depositing v31.0.11 zips here,
  inflating every subsequent build by 180MB. Now gitignored.

### Build + ship

Same as previous versions. All 4 artifacts at
`https://github.com/BIGHatEntertainment/BIGHat-Program/releases/tag/v31.0.12`.

### Future hooks

The file-association infrastructure exists in
`packaging/installer/bighat-installer.nsi` for `.bighat`. Wiring the
double-click handoff to the running app via
`/api/bighat-files/import-from-path` is a half-day follow-up. The
`/bighat-files/types` endpoint is the foundation for a future
"Browse premium packs" tab in the dashboard that pulls a catalog
from `api.bighat.live`.

---



**User report**: "I thought the first thing that should happen upon
first open is the Setup Wizard. It's hard for the master admin to log
in with any credentials if setup has been skipped."

### Why this kept happening

The gate logic in `App.js — NativeGate` was correct:
```js
if (nativeMode && !setupComplete && location.pathname !== '/setup') {
  return <Navigate to="/setup" replace />;
}
```

But it depended on `nativeMode` being truthful. `NativeContext.refresh()`
fail-opened with `native_mode: false, setup_complete: true` whenever
`/api/native/info` failed for *any* reason — broken baked URL (the
v31.0.10 root cause), slow backend startup, network blip, anything.
The fail-open lied to the gate, the gate did nothing, and the customer
landed on `/login` with no master admin to log in as.

### Fix

* `NativeContext.refresh()` now retries up to 5 times with linear
  backoff (500ms → 2500ms). The desktop launcher takes 2-3 seconds to
  start the backend, so the first React fetch frequently races the
  listener. Five attempts covers up to ~7s of startup lag.
* New `IS_NATIVE_BUILD = !process.env.REACT_APP_BACKEND_URL` constant
  — a native-build asset bundle always has an empty `REACT_APP_BACKEND_URL`
  (per v31.0.10's `build_installer.py` / `build_dmg.py` change). The
  webapp deploy at `standalone-tools.preview.emergentagent.com` has it
  set, so `IS_NATIVE_BUILD === false` there.
* On terminal failure:
  * If `IS_NATIVE_BUILD`: do NOT fail-open to `{native_mode: false}`.
    Instead stay in `loading: true, error: <msg>` so the gate renders
    a dedicated "Backend Unreachable" screen with a Retry button and a
    support code. Customer never gets dropped at `/login`.
  * If webapp build (cloud): keep the original fail-open behaviour —
    api.bighat.live doesn't have `/api/native/*` routes by design and
    the webapp should still work.
* `App.js — NativeGate` adds a new branch above the normal loading
  state that renders the connection-error screen when
  `loading && isNativeBuild && error`.

### Result

* On a fresh v31.0.11 install: launcher boots → backend listens →
  React loads → `/api/native/info` returns `native_mode: true,
  setup_complete: false` → gate redirects to `/setup` → wizard runs →
  master admin creates credentials → login works.
* On a v31.0.11 install where the backend is genuinely down or slow:
  retry loop covers most startup races. If the backend is hard down,
  customer sees the friendly error screen with a Retry button and is
  told to relaunch from the Start Menu. They never see a misleading
  "Authentication failed" error.

### Files of interest

* `frontend/src/context/NativeContext.js` — retry loop + fail-closed
  for native builds + new `isNativeBuild` exposed in context value.
* `frontend/src/App.js` — `NativeGate` renders the connection-error
  screen ahead of the normal loading state.

### Build + ship

Same as v31.0.10. All four artifacts in this release.

---



**Two production-blocking issues reported by the user**:

1. Customer's installed Windows app shows "LOG IN TO 127" on the Google
   sign-in screen + "Authentication failed. Please try again." on the
   password form, even with the correct credentials.
2. Default password (`B1GHat`) for 5 employee accounts was hardcoded in
   `server.py` and visible in the now-public GitHub mirror.

### Root cause of Issues 1 & 2 (same bug)

The frontend build orchestrator was running `yarn build` with the
preview environment's `REACT_APP_BACKEND_URL` baked into the JS bundle
(`https://standalone-tools.preview.emergentagent.com`). On a customer
machine:

* `axios.get('https://standalone-tools.preview.emergentagent.com/api/native/info')`
  — they have no access to our preview env. `NativeContext.refresh()`
  failed → fail-open path set `native_mode=false`. The LoginPage
  `!nativeMode` gate (added in v31.0.7 to hide the Google button on
  desktop installs) then rendered the Google button anyway, sending
  the user to the Emergent OAuth page that titles itself "LOG IN TO
  127" (the redirect hostname `127.0.0.1` is truncated visually).
* `axios.post('https://standalone-tools.preview.emergentagent.com/api/auth/login')`
  — same target. Our preview server has no user named
  `sellards@bighat.live`, so it returned 401. The customer's actual
  `sellards@bighat.live` lives in their LOCAL Mongo / MontyDB, which
  the bundle never tried to talk to.

The previous v31.0.7 fix for "Google login should be hidden on native"
was correct in code — but invisible behind this baked-URL bug.

### Root cause of Issue 3

The public repo had eleven hardcoded literals of the default password
in `backend/server.py`, plus a hardcoded admin master passcode, plus
the dev `backend/native/system_config.json` (with a bcrypt hash of the
test password) committed to git, plus the compiled
`backend/static/static/js/main.*.js` bundle which baked the default
password literal from the JSX placeholder strings.

### Fixes (v31.0.10)

**Customer-blocking build fix**

* `scripts/build_installer.py` + `scripts/build_dmg.py` now set
  `REACT_APP_BACKEND_URL=""` explicitly when invoking the frontend
  build orchestrator. CRA picks up the empty string from the shell
  env → all axios calls compile to relative paths (`/api/...`) →
  installed app talks to its own embedded backend at `127.0.0.1:8001`.
* Both scripts now do `--clean` rebuilds of `backend/static` so a
  stale bundle (with a bad baked URL) can never sneak through.
* Removed the obsolete `frontend/public/downloads/` mirror step that
  was inflating every subsequent macOS build by 280MB of stale
  installer copies AND was the channel by which the bad baked URL
  got preserved across builds. Customer-facing downloads now resolve
  via `/api/downloads/auto` against GitHub Releases (added in v31.0.9).

**Security hardening**

* `backend/server.py` — replaced all eleven `"B1GHat"` and three
  `"121589"` literals with `DEFAULT_HOST_PASSWORD` and
  `ADMIN_MASTER_PASSCODE` module-level constants. Both read from env
  vars (`DEFAULT_HOST_PASSWORD`, `ADMIN_MASTER_PASSCODE`,
  `SEED_PW_SELLARDS|ALEX|JORDAN|CASEY|TAYLOR`). When env values are
  missing the server generates a random `secrets.token_urlsafe(12)`
  per boot and logs it ONCE so the operator can rotate.
* `GET /api/host/password/is-default/{id}` no longer returns the
  default password in its response — only the `is_default: bool` flag.
* `POST /api/host/login` now includes `is_default_password: bool` in
  its response so the client can show the "change your default
  password" prompt without comparing against a baked literal.
* `frontend/src/components/schedule/HostLogin.jsx` — removed the
  `password === 'B1GHat'` literal compare; reads
  `is_default_password` from the login response instead.
* `git rm --cached backend/native/system_config.json` +
  `git rm --cached -r backend/static/static/` — both now in
  `.gitignore`. They contain per-install secrets / build artifacts
  that should never have been tracked.
* New `memory/test_credentials.md` is gitignored, references no
  literal passwords, and documents the env-var contract.
* New regression test `backend/tests/test_no_plaintext_credentials.py`
  scans every tracked file for known-leaked literals (`B1GHat`,
  `BigHat2024!`), bcrypt hash signatures, GitHub PATs, OpenAI keys,
  Resend keys. Also enforces that `system_config.json` and
  `backend/static/static/` stay untracked. Run on every CI / pre-push.

### Customer remediation

* All v31.0.9 and earlier installed customers are dead in the water
  (login fails). Push them to `v31.0.10`. The Setup Wizard's
  pending-cloud-activation retry job (every 4h) will continue to
  try, so when the new build talks to the cloud the existing license
  state should pick up automatically.
* **Operator action items on `api.bighat.live`**: set environment
  variables before next deploy:
  ```
  DEFAULT_HOST_PASSWORD=<strong, ≥16 chars, rotate quarterly>
  ADMIN_MASTER_PASSCODE=<strong, ≥10 chars, distinct from above>
  SEED_PW_SELLARDS=<per-host>
  SEED_PW_ALEX=<per-host>
  SEED_PW_JORDAN=<per-host>
  SEED_PW_CASEY=<per-host>
  SEED_PW_TAYLOR=<per-host>
  ```
  Missing env vars → random fallback (logged once).

### Build + ship

```bash
echo "31.0.10" > backend/VERSION.txt
yarn --cwd frontend build  # rebuilds with REACT_APP_BACKEND_URL=""
python scripts/build_installer.py --no-sign
python scripts/build_dmg.py --arch aarch64 --skip-pkg --skip-dmg
python scripts/build_dmg.py --arch x86_64 --skip-pkg --skip-dmg
python scripts/publish_github_release.py --replace-existing
```

### Lessons-learned guardrails (so it doesn't happen again)

1. `test_no_plaintext_credentials.py` catches any reintroduction of
   the known-leaked literals OR any bcrypt hash in tracked source.
2. The compiled frontend bundle and the dev system_config are now
   gitignored — they will NEVER be re-tracked unless someone manually
   `git add -f`s them.
3. `build_installer.py` / `build_dmg.py` always rebuild the frontend
   bundle with `REACT_APP_BACKEND_URL=""` — preserves a single,
   blessed baked URL value (empty = relative) per release. No way to
   accidentally bake a dev preview URL into a customer build.

---



**Customer-reported bug**: A developer bought BIG Hat from the Squarespace
store on a Mac and was sent to a hardcoded GitHub asset URL for
`BIGHatStandalone-Setup-31.0.5.exe` — a Windows installer, for a stale
version (v31.0.5 was superseded), via a signed/private asset link
(`release-assets.githubusercontent.com/.../?expires=...&signature=...`)
that 404'd because the asset had been replaced.

### Root cause

The store's "Download" button was a hardcoded URL pointing at a
specific .exe asset on a specific GitHub release. That URL:
  1. Was OS-blind — every customer got the same Windows installer
     regardless of what machine they were on.
  2. Was version-pinned to a release that no longer exists.
  3. Was a signed CDN URL (not the stable `/releases/download/...` form)
     so it expired even while v31.0.5 was current.

`/api/downloads/{platform}` existed in the cloud API but returned 404
in production because `DOWNLOAD_URL_WINDOWS` / `DOWNLOAD_URL_MACOS` env
vars were never set.

### Fixes

* **New `backend/cloud/downloads_resolver.py`** — two-layer resolver:
  1. Env-var override (`DOWNLOAD_URL_WINDOWS`, `DOWNLOAD_URL_MACOS`,
     `DOWNLOAD_URL_MACOS_INTEL`) if ops needs to pin a specific build.
  2. Live `GET /repos/{owner}/{repo}/releases/latest` lookup against
     `GITHUB_OWNER` / `GITHUB_REPO`, cached 5 min. Reads the stable
     `browser_download_url` (NOT the signed CDN form), so the link
     remains valid as long as the asset exists. Asset-name matching
     handles all three artifacts: Windows `.exe`, macOS Apple Silicon,
     macOS Intel.

* **New endpoint `GET /api/downloads/auto`** (cloud router) — sniffs
  `User-Agent`, picks the platform, 302-redirects to the latest asset.
  Optional `?platform=…` for explicit override (`windows`, `mac`,
  `intel`, `applesilicon`, etc.). Unknown UA / missing asset → 302 to
  the friendly landing page instead of a hard 404.

* **New endpoint `GET /api/downloads/latest`** (cloud router) — JSON
  manifest of all platform URLs at the latest version. Used by the
  landing page and by support tooling.

* **New endpoint `GET /download`** (cloud-only, HTML) —
  `backend/cloud/download_landing.py`. Self-contained, server-side
  rendered. Detects OS from UA, renders a large primary button for the
  detected platform + secondary "Other platforms" panel for the other
  two. Branded BIG Hat theme, zero external assets. If
  `/api/downloads/auto` couldn't resolve an asset, it redirects here
  with `?missing=…` so the page can show "X not yet available, email
  support" instead of 404.

* **`cloud/license_router.py`** — existing `/api/downloads/{platform}`
  endpoint now also goes through the resolver, so the desktop updater
  always sees the current release. Accepts `windows`, `macos`,
  `macos_apple`, `macos_intel` aliases.

* **`cloud/license_models.py`** — widened `DownloadInfo.platform`
  Literal to include the macos-arch variants.

* **`tests/test_cloud_downloads.py`** — 11 new pytest cases covering
  UA detection (Windows + Mac + unknown), explicit platform override,
  env-var override beats GitHub lookup, missing-asset → landing-page
  redirect, and the landing page itself. All 99 cloud tests green.

### Action items for the store / production ops

These changes ship in `v31.0.9` but the Squarespace store + bighat.live
still point at the old hardcoded GitHub URL. You need to:

1. **Update Squarespace store**: change the "Download" button URL from
   the GitHub assets URL to **`https://api.bighat.live/api/downloads/auto`**
   (direct redirect) or **`https://api.bighat.live/download`** (branded
   page with explicit platform choice). The branded page is the better
   default because Mac users can pick Apple Silicon vs Intel — the
   `auto` endpoint defaults to Apple Silicon for Macs which is correct
   ~95% of the time but isn't bulletproof for the few customers on
   pre-2020 Intel hardware.

2. **Set the production env vars on `api.bighat.live`**:
     - `GITHUB_OWNER=BIGHatEntertainment`
     - `GITHUB_REPO=BIGHat-Program`
     - `GITHUB_RELEASES_TOKEN=<a PAT with the `public_repo` scope only>`
       (optional — pushes rate-limit from 60/h to 5000/h, important if
       you're getting any kind of store traffic).
3. **Publish v31.0.9 with all three artifacts on the same release**:
   ```bash
   python scripts/build_installer.py            # Windows .exe
   python scripts/build_dmg.py                  # macOS Apple Silicon
   python scripts/build_dmg.py --arch x86_64    # macOS Intel
   python scripts/publish_github_release.py --replace-existing
   ```
   The publish script already uploads all three asset filenames the
   resolver knows how to match.

### Why this fixes it for every future buyer

* Store button → `bighat.live/download` (or `/api/downloads/auto`).
* `/download` renders Mac primary button for Mac UA, Windows primary
  for Windows UA, both for unknown.
* Each button links to the **current** release's asset, resolved live
  from GitHub at request time. No store config change required when
  shipping v31.1.0 / v31.1.1 / etc — as long as the new release has
  the three expected asset filenames, the page auto-updates.
* Customer on Apple Silicon → gets `…AppleSilicon.zip`.
* Customer on Intel Mac → clicks the Intel card → gets `…Intel.zip`.
* Customer on Windows → gets `BIGHatStandalone-Setup-…exe`.

---



**What changed**: the desktop SetupWizard's `/api/native/setup/initialize`
endpoint now talks to the production cloud license authority at
`https://api.bighat.live/api/license/activate` directly, server-side,
during first-run setup. Previously the cloud call was issued only by
the wizard frontend (Step 1) and could be bypassed by anyone POSTing
to `setup/initialize` with a well-formed-but-fake key.

### Why

PRD backlog Phase 10.1: "Wire desktop SetupWizard to actually call
`https://api.bighat.live/api/license/activate` in production (currently
the desktop license code is local-stub; payloads/contracts already
align)." The wiring existed in the frontend Step 1 + the
`/api/native/license/cloud/activate` endpoint, but `setup/initialize`
didn't enforce the cloud's authoritative answer — so a malicious or
offline customer could finish setup with no real license bound to the
cloud.

### Behaviour matrix (now)

| Cloud response                              | Setup result | Local state |
|---------------------------------------------|--------------|-------------|
| 2xx — `owns_standalone:true`                | 200 OK       | subscription mirrored; `pending_cloud_activation=false` |
| 2xx — `owns_standalone:false`               | 200 OK       | free tier; user can still log in |
| 4xx — `unknown_key` / `revoked` / `seat_limit` | 400        | NO master admin written; setup remains incomplete |
| Transport error (timeout / network / 5xx)   | 200 OK       | master admin written; `pending_cloud_activation=true`; background retry every 4h |

### Files of interest

* `backend/native/router.py` — `initialize_setup`:
  - Calls `cloud_client.activate()` BEFORE writing any local state.
  - 4xx from cloud → `HTTPException(400, …)`, no master admin created.
  - Transport error → setup proceeds with `pending_cloud_activation` flag.
  - 2xx → `_apply_cloud_response_to_local_state` mirrors flags (same path
    the existing `/api/native/license/cloud/activate` endpoint uses).
* `backend/scheduler.py` — new APScheduler job
  `retry_pending_cloud_activation` runs every 4 hours (first run +2 min
  after boot). When the flag is set it re-attempts cloud activation;
  clears the flag on success, records `cloud_activation_error` on
  authoritative rejection, leaves alone on transient transport errors.
* `backend/tests/test_setup_cloud_activation.py` — 4 new pytest cases
  covering the four behaviour-matrix rows. All passing alongside the
  existing 84 license/cloud-wireup tests (88/88).

### Network requirements (customer-facing)

The desktop install now needs **outbound HTTPS to `api.bighat.live`**
the first time a customer runs the Setup Wizard. Corporate firewalls
that block this still get a working install (offline path) but premium
features stay locked until the retry job lands a successful activation.
Document this in the bighat.live FAQ.

### Build + ship

```bash
echo "31.0.8" > backend/VERSION.txt
yarn --cwd frontend build
python scripts/build_installer.py
python scripts/publish_github_release.py --replace-existing
```

---



**Customer-reported bugs**:
1. Brand new install lands the user on `/login` immediately. No matter what
   credentials they enter, login fails. They never see the Setup Wizard.
2. Clicking "Sign in with Google" opens a chromeless window pointing at
   `auth.emergentagent.com` that reads **LOG IN TO 127** (truncated from
   the redirect hostname `127.0.0.1`). The OS window title also flips to
   "Emergent" while on that page. Both make customers think they're
   logging into the wrong app.

### Root causes

1. **Dev seed `backend/native/system_config.json` was being shipped in the
   installer payload.** That file has `setup_complete: true`, a master
   admin (`master@bighat.local`) with the dev password hash, and an
   active license seat bound to a dev HWID. On a customer machine the
   wizard short-circuits, the email is unknown to them, the password
   hash they enter doesn't match, and even if it did the HWID wouldn't.
   Result: unrecoverable lockout.

2. **The Google sign-in button was visible in native standalone mode.**
   Native is offline-first — the master admin is provisioned by the
   Setup Wizard with a local password. Google OAuth is a webapp / cloud
   mode concept. Showing the button on the desktop install (a) sends the
   user to a hosted page whose UX we don't control ("LOG IN TO 127",
   "Emergent" in the title bar), and (b) the chromeless `--app=` window
   leaves the BIG Hat origin, so the OS window title flips to whatever
   that page sets.

### Fixes

* **`scripts/build_installer.py` + `scripts/build_dmg.py`** `_copy_tree`
  now skips two more filename patterns alongside `.env*`:
  * `system_config.json` — the per-install config gets regenerated by
    `ConfigManager` on first boot when the file is absent, so the
    Setup Wizard runs.
  * `*.corrupt.json` — backup files dropped by the config manager when
    it recovers from a corrupted JSON. Internal diagnostic data, never
    shipped.
* **`frontend/src/pages/LoginPage.js`** — pulls `nativeMode` from
  `useNative()`. When `nativeMode === true` it hides the Google sign-in
  button, the "Secure login using your Google account" subhead, and the
  "OR USE PASSWORD" divider. Customers on the desktop install see only
  the email + password form. They never navigate away from
  `http://127.0.0.1:8001/`, so the window title stays "BIG Hat | Host".

### What I did NOT change (intentional)

* The Google sign-in code path is **preserved** — webapp / cloud mode
  (`api.bighat.live`, the preview environment, and any future hosted
  variant) still shows the button. Only native installs hide it.
* The Setup Wizard pages, NativeContext, NativeGate redirect — all
  unchanged. They were already correct; the dev `system_config.json`
  was the only thing preventing them from running.
* The cloud admin path that uses `Sellards@bighat.live` is unaffected.
  That account exists in the webapp Mongo store, not in
  `system_config.json`.

### Files of interest

* `scripts/build_installer.py` (`_copy_tree` filename filter)
* `scripts/build_dmg.py` (same filter mirrored)
* `frontend/src/pages/LoginPage.js` (native-mode Google button gate)
* `backend/native/config.py` — already produces `setup_complete=false`
  defaults when no JSON exists. No change needed.

### Build + ship

```bash
echo "31.0.7" > backend/VERSION.txt
yarn --cwd frontend build
python scripts/build_installer.py
python scripts/publish_github_release.py --replace-existing
```

Customer upgrade path: on next launch, the v31.0.7 launcher auto-detects
the dev-seed `system_config.json` (signature: instance_id
`75d181a8-50f3-4032-90d4-7ecfd7cf44a7` or `master@bighat.local` as
master admin) and renames it to `system_config.dev-seed.json`. The
Setup Wizard then runs on first request. No manual cleanup required —
just install v31.0.7 over the top.

---



**Product change**: Music-video bingo (with playlists, decade picker, song
recognition) is temporarily removed from the user-facing UI. Traditional
number bingo is the only mode shown. Music bingo will return as a paid
add-on in a future release — the code is preserved behind a feature flag,
NOT deleted.

### Where the toggle lives

* `frontend/src/pages/bingo/Lobby.jsx` — top-of-file `const
  ENABLE_MUSIC_BINGO = false;`. Flip to `true` to bring music bingo back
  with zero other file changes. Everything that's hidden is wrapped in
  conditionals against that flag.

### What the flag affects

| Surface | When flag is `false` (today) | When flag is `true` (future) |
|---|---|---|
| Dashboard card title | "Bingo" | "Music Bingo" |
| Dashboard card description | "Run traditional number bingo nights..." | "Run music bingo nights..." |
| Dashboard card entitlement | Bundled with standalone (`story_generator_enabled`) | Add-on (`music_bingo_enabled`, $24.99 store path) |
| Lobby page header | "Bingo" | "Music Bingo" |
| Quick Play / Custom Setup mode select | Skipped — wizard starts in Custom mode | Shown |
| Wizard step 0 ("Choose Bingo Type") | Skipped — initial step is 1 (Game Type) | Shown with both options |
| Wizard step indicator dots | 3 dots (steps 1, 2, 3 visible) | 4 or 5 dots depending on selected type |
| Wizard "Music Decade" step | Skipped | Shown when type=music |
| `settings.bingoType` initial value | `"traditional"` | `"music"` |
| Back button on first visible step | Returns to /home | Returns to mode-select |

### What I did NOT change (intentional)

* `backend/routes/bingo.py` is untouched. The backend can still service
  music-bingo API calls (`/api/bingo/songs`, etc.); we just never offer
  them in the UI. Keeping the routes mounted means re-enabling is a
  one-line flag flip with no backend migration required.
* The "music_bingo" entry stays in `LICENSE_FEATURE_MATRIX`. License
  records keep their `owns_music_bingo` flag — customers who already paid
  for the add-on won't lose anything when we re-enable the UI.
* Music-related lobby strings (`Disc3` icon import, `"music"` id in
  `allBingoTypes`, `musicDecade` setting in initial state) are preserved.
  They're just filtered out or short-circuited.

### Files of interest

* `frontend/src/pages/bingo/Lobby.jsx` (top of file — feature flag)
* `frontend/src/components/AppCards.js` (dashboard tile metadata)

### Build + ship

Bumped `backend/VERSION.txt` from 31.0.5 → 31.0.6. Built the React
bundle (`yarn build` in `frontend/`), synced into `backend/static/`,
then ran `makensis` directly because the wheel cache is intact and a
full `build_installer.py` run would have re-baked all 248 wheels for
no reason. Final installer: 106 MB, lint clean.

---



**TL;DR**: VBS still owns the launch sequence (boot pythonw, poll port),
but instead of opening the user's default browser, it locates msedge.exe
or chrome.exe and launches them with `--app=URL --user-data-dir=...`
to get a chromeless window. Fixed the NSIS Finish-page auto-launch.

### The canonical launch path on Windows

1. Customer double-clicks the "BIG Hat" desktop shortcut, OR ticks the
   "Launch BIG Hat now" box on the installer's Finish page, OR
   double-clicks any `.bighat` file in Explorer.
2. Shortcut target: `wscript.exe "<install>\packaging\start_bighat.vbs" [optional .bighat path]`.
3. VBS:
   a. Probes `127.0.0.1:8001`. If already up → single-instance handoff:
      spawn a new chromeless `--app=` window pointing at the URL and exit.
   b. Else: `WshShell.Run "pythonw.exe backend\launcher.py --no-browser", 0, False`.
   c. Polls `127.0.0.1:8001` for up to 25 s.
   d. When port is up, locates first available of: msedge / chrome /
      brave in standard Program Files paths.
   e. Spawns `<browser>.exe --app="http://127.0.0.1:8001..."
      --user-data-dir="<install>\backend\data\browser_profile"
      --no-first-run --no-default-browser-check`. Result: a frameless
      Chromium window. Zero browser chrome visible to the user.
   f. Falls back to default browser ONLY if no Chromium-family browser
      is found (essentially never on Win 11).

### NSIS Finish-page fix

Replaced `MUI_FINISHPAGE_RUN_FUNCTION LaunchApp` (which silently no-op'd
on some installs) with the direct pattern:

```
!define MUI_FINISHPAGE_RUN "$SYSDIR\wscript.exe"
!define MUI_FINISHPAGE_RUN_PARAMETERS '"$INSTDIR\packaging\start_bighat.vbs"'
!define MUI_FINISHPAGE_RUN_TEXT "Launch BIG Hat now"
```

This is the NSIS MUI 2 idiom for "run this program with these args when
the user ticks the checkbox". Reliably fires on every install.

### Why earlier attempts were wrong (don't re-litigate)

| Phase | Approach | Why it broke |
|---|---|---|
| 10.8 | pywebview + pythonnet (EdgeChromium backend) | `webview.start(gui='edgechromium')` silently fell back to WinForms on some Win 11 installs, then died on `System.NullReferenceException`. |
| 10.9-A | msedge --app= called from launcher.py | Python launched Edge in parallel with uvicorn → ERR_CONNECTION_REFUSED. |
| 10.9-B (v31.0.4) | VBS polls port, then opens default browser | Worked, but opened a regular browser tab with the user's normal Chrome profile (full tab bar, all their open tabs visible). User rejected this. |
| **10.10 (v31.0.5, current)** | VBS polls port, then spawns msedge --app=URL | VBS owns sequencing → no race. --app= mode → no chrome visible. Isolated --user-data-dir → no profile leakage. |

### Files of interest

* `packaging/start_bighat.vbs` — the canonical launcher.
  - Finds msedge / chrome / brave and spawns `--app=` mode.
  - Handles `.bighat` file argv for file-association handoff.
* `packaging/installer/bighat-installer.nsi`
  - `MUI_FINISHPAGE_RUN` + `_PARAMETERS` for auto-launch on install.
  - All shortcuts (Desktop / Start Menu / Auto-start) point at
    `wscript.exe start_bighat.vbs` with the hat-icon override.
  - `.bighat` file association → `wscript.exe start_bighat.vbs "%1"`.
* `backend/launcher.py` — pure backend boot. Defaults to `--no-browser`
  behaviour from VBS. Direct invocation (dev) falls through to
  `webbrowser.open_new()` for convenience but THIS IS NOT THE
  CUSTOMER PATH.

### How to ship a new release

```bash
echo "31.0.X" > backend/VERSION.txt
python scripts/build_installer.py            # full clean rebuild
export GITHUB_TOKEN=<PAT with contents:write>
export GITHUB_OWNER=BIGHatEntertainment
export GITHUB_REPO=BIGHat-Program
python scripts/publish_github_release.py --replace-existing
```

Public stable URL:
`https://github.com/BIGHatEntertainment/BIGHat-Program/releases/download/v31.0.X/BIGHatStandalone-Setup-31.0.X.exe`

---

## v31.0.0 → v31.0.4 — pre-Phase-10.10 attempts (DO NOT REINSTATE)

(v31.0.5 details below this section — the launcher infrastructure they
fixed is still in effect today. Read v31.0.5 before touching any
launcher / installer / packaging files.)

### v31.0.5 — 2026-05-20 (Phase 10.10: chromeless --app=, VBS-orchestrated)

**TL;DR**: VBS owns the launch sequence (boot pythonw, poll port), then
locates msedge.exe or chrome.exe and launches them with `--app=URL
--user-data-dir=...` for a chromeless window. NSIS Finish-page wired
with both `MUI_FINISHPAGE_RUN ""` + `MUI_FINISHPAGE_RUN_FUNCTION LaunchApp`
(both required — MUI silently no-ops if only the function is defined).

**Launch path** (still current under v31.0.6):
1. Shortcut → `wscript.exe start_bighat.vbs [optional .bighat path]`.
2. VBS probes 127.0.0.1:8001 — if up, single-instance handoff: spawn a
   new chromeless `--app=` window at the URL.
3. Else: `WshShell.Run "pythonw.exe backend\launcher.py --no-browser"`.
4. Polls port for up to 25 s.
5. When port is up, locates first available of msedge / chrome / brave
   in standard Program Files paths and spawns
   `<browser>.exe --app="http://127.0.0.1:8001/..."
    --user-data-dir="<install>\backend\data\browser_profile"
    --no-first-run --no-default-browser-check`.
6. Falls back to default browser only if no Chromium-family browser exists.

---

* v31.0.0: First customer build. Embedded Python had no third-party deps baked in → silent crash on `import uvicorn`.
* v31.0.1: Wheels baked. Crashed on `webview.start(icon=...)` TypeError.
* v31.0.2: Cosmetic rename to "BIG Hat" everywhere. Still had icon-kwarg bug because `--skip-payload` was used.
* v31.0.3: msedge `--app=URL` called from launcher.py. Race with uvicorn boot → ERR_CONNECTION_REFUSED.
* v31.0.4: VBS-orchestrated launch but opened default browser. User saw a regular browser tab with their normal Chrome profile (multi-tab strip visible). Rejected by user — must use chromeless --app= mode instead. Also Finish-page auto-launch was broken (MUI_FINISHPAGE_RUN_FUNCTION didn't fire).

All of these are obsolete. v31.0.5 is the current canonical build.
