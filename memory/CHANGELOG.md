# BIG Hat Entertainment — CHANGELOG

> **For the next agent: READ THIS BEFORE TOUCHING THE LAUNCHER.**
> The most recent entry describes how the app actually launches today.
> Older entries describe approaches that have been ripped out — they
> ARE NOT a fallback and must not be reinstated.

---

## NEVER-DO RULES (locked in by user 2026-05-20)

1. **THE APP MUST NEVER OPEN IN A REGULAR BROWSER TAB.** Not Chrome with
   tabs, not Edge with tabs, not Firefox, not anything that shows a URL
   bar / bookmarks bar / tab strip to the user. The user has been
   explicit about this multiple times across multiple builds. If you
   find yourself calling `webbrowser.open_new()` or `WshShell.Run
   "http://..."` as the PRIMARY launch path, you are wrong.

2. **The ONLY acceptable window for the app on Windows is a chromeless
   Chromium window via `msedge.exe --app=URL` (or Chrome / Brave with
   the same flag).** This gives a frameless window with no tab bar, no
   URL bar, no menu. It looks indistinguishable from a native window.
   It's what Slack / Discord / Notion's desktop apps do. Default-browser
   fallback is acceptable ONLY when no Chromium-family browser is
   present on the machine (which is essentially never on Windows 11 —
   Edge is preinstalled).

3. **The launch sequence MUST be: spawn backend → wait for port →
   open the chromeless window.** Not "spawn backend AND open window
   in parallel" — that's the race that broke v31.0.3.
   `packaging\start_bighat.vbs` owns this sequencing today.

4. **THE INSTALLER'S FINISH-PAGE CHECKBOX MUST AUTO-LAUNCH THE APP.**
   v31.0.4 had the run-function defined but it didn't fire. Today it
   uses the direct `MUI_FINISHPAGE_RUN` + `MUI_FINISHPAGE_RUN_PARAMETERS`
   pattern, which is the reliable NSIS MUI 2 idiom. If you change the
   wiring, smoke-test that the checkbox actually fires on install.

---

## v31.0.9 — 2026-05-27 (OS-aware download landing page + dynamic GitHub release lookup)

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
