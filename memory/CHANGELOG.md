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

## v31.0.6 — 2026-05-23 (Bingo: music-video flow hidden, traditional only)

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
