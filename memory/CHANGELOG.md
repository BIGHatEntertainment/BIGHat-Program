# BIG Hat Entertainment — CHANGELOG

> **For the next agent:** treat this file as the authoritative log of what
> launcher / installer / packaging strategy is currently in effect. The PRD
> describes what the product is; the CHANGELOG describes how it actually
> ships today. Read the **most recent** entry first — older entries may
> describe approaches that have since been ripped out.

---

## v31.0.4 — 2026-05-12 (Phase 10.9: VBS-only launch chain)

**TL;DR**: Removed BIGHat.exe Win32 wrapper AND the Edge `--app=` mode
attempt. ALL launches now go through `packaging\start_bighat.vbs`.

### What launches the app on Windows (canonical, 2026-05-12)

Desktop shortcut, Start Menu shortcut, optional Auto-start, and the
`.bighat` file association all resolve to:

```
C:\Windows\System32\wscript.exe "C:\BIG Hat\BIGHatStandalone\packaging\start_bighat.vbs" [optional_bighat_file]
```

The shortcuts override the icon to `packaging\bighat.ico`, so they show
the hat (not the generic VBS document icon).

### The VBS does these five things in order

1. Validates `python\pythonw.exe` + `backend\launcher.py` exist (errors via MsgBox if not).
2. Probes `127.0.0.1:8001` — if a launcher is already running, just opens
   the URL in the user's default browser and exits (single-instance UX).
3. Otherwise: `WshShell.Run "pythonw.exe backend\launcher.py --no-browser", 0, False`
   (hidden, fire-and-forget).
4. Polls `127.0.0.1:8001` for up to 25 s.
5. When the port is up, `WshShell.Run "http://127.0.0.1:8001..."` to open
   the user's default browser. If a `.bighat` file path was passed as
   `WScript.Arguments(0)`, it gets URL-encoded into a
   `/roundmaker?openFile=<path>` query string.

### What `launcher.py` does in v31.0.4

* `--no-browser` is the default behaviour from VBS. Launcher just boots
  uvicorn on a daemon thread and blocks on `threading.Event().wait()` so
  the parent process stays alive.
* When invoked directly (dev runs, diagnostic .bat), `webbrowser.open_new()`
  opens the default browser — same end state.
* `_open_native_window()` is a deprecated stub that returns False. Calls
  to it are still safe; nothing in the launch chain calls it anymore.

### What was REMOVED in this version

* `BIGHat.exe` (Win32 cross-compiled launcher) — the install no longer
  ships it. Builds before 31.0.4 had it; the new installer pre-deletes any
  stale copy on upgrade. The MinGW cross-compile + `bighat.c` source +
  `scripts/build_win32_wrapper.py` are kept on disk for reference but
  no longer invoked.
* All `pywebview`, `pythonnet`, `clr_loader` wheels — saved ~25 MB.
* The `msedge --app=` mode code in `launcher.py` (it lost a race vs.
  uvicorn binding 8001 on slow machines — see "Why this approach won"
  below).

### Why this approach won

| Approach tried | What broke |
|---|---|
| Phase 10.5: VBS + pythonw + open browser delayed in Python | Worked but the launcher.py timer was racy on slow machines. |
| Phase 10.6: Win32 BIGHat.exe spawning pythonw, polling port | Single-instance handoff was nice, but BIGHat.exe could fall out of the payload if the build box lacked MinGW. |
| Phase 10.8: pywebview chromeless window via Edge WebView2 | `start(gui='edgechromium')` silently fell back to WinForms on some Win 11 installs, then died on a `System.NullReferenceException`. |
| Phase 10.9: msedge --app=URL with isolated --user-data-dir | Edge launched before uvicorn finished binding port 8001 → `ERR_CONNECTION_REFUSED`. |
| **Phase 10.9b (current): VBS as canonical launcher** | The VBS owns the port-poll AND the browser-open in sequence, so the race can't happen. User explicitly identified this approach as working. |

### Files of interest

* `packaging/start_bighat.vbs` — the canonical launcher.
* `packaging/installer/bighat-installer.nsi` — NSIS script; all shortcuts
  + file association point at the VBS.
* `backend/launcher.py` — uvicorn-only headless boot; `--no-browser` default.
* `scripts/build_installer.py` — pre-deletes any stale BIGHat.exe from
  the payload to keep `--skip-payload` reuses clean.

### Lessons banked

1. **Browser-in-an-app is a race.** Whoever opens the URL must poll the
   port FIRST and open the URL AFTER. Splitting those two responsibilities
   across processes (launcher in Python, window-open in Edge) made it
   impossible to sequence reliably. VBS keeping both jobs in one place
   is what fixed it.
2. **--skip-payload is dangerous.** If MinGW (or any other dep) is
   missing during one build, subsequent `--skip-payload` rebuilds happily
   ship the missing-asset payload. The build script now hard-fails on
   missing critical artifacts rather than warning + continuing.
3. **CHANGELOG > internal memory.** Multiple prior phases relitigated
   the same launcher question because no agent had a single canonical
   reference for "what ships today". This file is that.

### How to ship a new release going forward

```bash
echo "31.0.X" > backend/VERSION.txt
python scripts/build_installer.py            # rebuilds everything cleanly
export GITHUB_TOKEN=<PAT with contents:write>
export GITHUB_OWNER=BIGHatEntertainment
export GITHUB_REPO=BIGHat-Program
python scripts/publish_github_release.py --replace-existing
```

Stable customer-facing download URL:
`https://github.com/BIGHatEntertainment/BIGHat-Program/releases/download/v31.0.X/BIGHatStandalone-Setup-31.0.X.exe`

---

## v31.0.0 → v31.0.3 — pre-Phase-10.9 attempts (DO NOT REINSTATE)

* v31.0.0: First customer-facing build. Embedded Python had no third-party deps baked in → silent crash on `import uvicorn`.
* v31.0.1: Wheels baked into `python\Lib\site-packages\`. Worked. Crashed on `webview.start(icon=...)` TypeError.
* v31.0.2: Cosmetic rename to "BIG Hat" everywhere. Still had the icon-kwarg bug because `--skip-payload` was used.
* v31.0.3: msedge `--app=URL` mode. Race with uvicorn boot → `ERR_CONNECTION_REFUSED`. Also BIGHat.exe got dropped from the payload during a previous `--skip-payload` rebuild.

All of these versions are obsolete. v31.0.4 is the current canonical build.
