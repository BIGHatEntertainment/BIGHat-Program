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

## v31.0.5 — 2026-05-20 (Phase 10.10: chromeless --app=, VBS-orchestrated)

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

* v31.0.0: First customer build. Embedded Python had no third-party deps baked in → silent crash on `import uvicorn`.
* v31.0.1: Wheels baked. Crashed on `webview.start(icon=...)` TypeError.
* v31.0.2: Cosmetic rename to "BIG Hat" everywhere. Still had icon-kwarg bug because `--skip-payload` was used.
* v31.0.3: msedge `--app=URL` called from launcher.py. Race with uvicorn boot → ERR_CONNECTION_REFUSED.
* v31.0.4: VBS-orchestrated launch but opened default browser. User saw a regular browser tab with their normal Chrome profile (multi-tab strip visible). Rejected by user — must use chromeless --app= mode instead. Also Finish-page auto-launch was broken (MUI_FINISHPAGE_RUN_FUNCTION didn't fire).

All of these are obsolete. v31.0.5 is the current canonical build.
