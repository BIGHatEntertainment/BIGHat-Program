; NSIS pre-install hook — kill running BIG Hat Entertainment instances
; -----------------------------------------------------------------------
; Why this exists:
;   Tauri ships TWO Windows processes — the main `BIG Hat Entertainment.exe`
;   shell and the sidecar `bighat-backend.exe` (the frozen FastAPI server).
;   If a customer re-runs the installer to upgrade (e.g. alpha.10 → alpha.11)
;   while the app is still open, Windows refuses to overwrite the locked
;   `.exe` files and NSIS surfaces the dreaded
;
;     "Error opening file for writing:
;      C:\Program Files\BIG Hat Entertainment\bighat-backend.exe"
;
;   …and the only options are Abort / Retry / Ignore. None of those are
;   acceptable for a paying customer.
;
; The fix:
;   Before NSIS starts copying files, terminate both processes. taskkill /F
;   succeeds even if the process is unresponsive. /T also kills children
;   (the spawned sidecar). The redirect to nul keeps the installer log
;   clean when the processes weren't running in the first place (fresh
;   install scenario).
;
; This hook runs as Administrator (installMode=perMachine), so the kill
; has the rights it needs.

!macro NSIS_HOOK_PREINSTALL
  DetailPrint "Closing any running BIG Hat Entertainment processes..."
  nsExec::Exec 'cmd /c taskkill /F /T /IM "BIG Hat Entertainment.exe" 2>nul'
  Pop $0
  nsExec::Exec 'cmd /c taskkill /F /T /IM "bighat-backend.exe" 2>nul'
  Pop $0
  ; Brief pause so Windows fully releases the file handles before NSIS
  ; tries to overwrite them. Without this, the kill can succeed but the
  ; OS still reports the file as locked for a few hundred ms.
  Sleep 800
!macroend

!macro NSIS_HOOK_PREUNINSTALL
  DetailPrint "Closing any running BIG Hat Entertainment processes..."
  nsExec::Exec 'cmd /c taskkill /F /T /IM "BIG Hat Entertainment.exe" 2>nul'
  Pop $0
  nsExec::Exec 'cmd /c taskkill /F /T /IM "bighat-backend.exe" 2>nul'
  Pop $0
  Sleep 800
!macroend

; v32.0.0-alpha.18: hard reset on uninstall.
;
; Why this exists:
;   The persistent user-data dir lives at %LOCALAPPDATA%\BIGHat\ — outside
;   the install folder by design, so in-place UPDATES (alpha.17 → alpha.18)
;   keep system_config.json + the local SQLite DB + the cached license. NSIS
;   updates only touch C:\Program Files\BIG Hat Entertainment\, so user
;   data survives an upgrade automatically.
;
;   But when a customer goes through Apps & Features → Uninstall, they
;   expect the app to be GONE — config, license cache, MontyDB, every-
;   thing. Otherwise a subsequent fresh install silently rehydrates the
;   old state and SKIPS the Setup Wizard, which is exactly what the user
;   reported: "this was a clean install. old files were deleted but the
;   new install automatically recalled older data and skipped the
;   verification".
;
;   The contract from the user is explicit:
;     • Update (in-place install over existing version) → continuation,
;       keep all data. NSIS POSTUNINSTALL never fires for an update.
;     • Manual uninstall → wipe %LOCALAPPDATA%\BIGHat\ so the next
;       install runs Setup mandatorily from scratch.
;
;   POSTUNINSTALL runs after every uninstaller invocation. Tauri's
;   built-in updater installs ON TOP without running the uninstaller, so
;   updates won't trigger this hook.
!macro NSIS_HOOK_POSTUNINSTALL
  DetailPrint "Removing user data at %LOCALAPPDATA%\BIGHat..."
  ; /r = recursive. RMDir is a no-op when the path doesn't exist, so
  ; this is safe to leave permanently — never errors on a clean machine.
  RMDir /r "$LOCALAPPDATA\BIGHat"
!macroend
