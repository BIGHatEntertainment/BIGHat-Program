# Investigation: Intel MacBook, "BIG Hat's backend started but never responded" (2026-11-04) — OPEN, needs the user's logs

## The report
An Intel MacBook user (v32.2.8+ Intel build) gets the dialog "BIG Hat — backend not responding ... Log file: /Users/JA/Library/Logs/BIGHat/tauri-shell.log".
Owner's theory: the Mac's files are being pointed at Windows directories / treated as Windows.

## What was checked (code + live CI data)
- NOT treated as Windows by the shell: the log path in the dialog (`~/Library/Logs/BIGHat/`) is chosen only on macOS (src-tauri/src/lib.rs log_dir). The words "a Windows security tool" in that
  dialog are one fixed message shown on EVERY platform (misleading on a Mac, but not evidence of Windows paths).
- The Python launcher is Mac-aware (backend/launcher.py `_user_data_dir`, macOS `~/Library/Application Support`) and writes `launcher_crash.log` in the data folder when startup fails.
  Earlier Windows-path bugs in this code (the `C:\Users\...` URI crash) were already fixed.
- The release builds the Intel backend NATIVELY on an Intel runner and smoke-tests it before publishing (v32.2.8: architecture check + start + /health + Scoreboard round trip passed).
  So a clean Intel machine can run the backend.

## Strongest lead (a hypothesis, NOT proven)
SPEED. The shell gives the backend 60 s to answer /health (`HEALTH_TIMEOUT_SECS`). The sidecar is a PyInstaller `--onefile` build, which unpacks itself into a temp folder on EVERY launch,
and macOS also scans the freshly unpacked files on first run. CI timings for the same smoke test (v32.2.8): Intel runner 87 s, Apple Silicon 29 s, and the Intel runner is a fast modern machine.
An older Intel MacBook can plausibly need more than 60 s. The two log files below separate "slow" from "crashed" at once.

## What is needed from the user (two files, nothing else)
1. `~/Library/Logs/BIGHat/tauri-shell.log`  (Finder > Go > Go to Folder... > paste the path). It already contains the backend's own output ("py-out"/"py-err") and, if the backend died,
   a line `sidecar terminated code=...`.
   - lines `health connect error attempt=...` and NO "terminated" line  => the backend was alive but SLOW (supports the speed theory).
   - a `sidecar terminated code=...` line, or Python errors above it     => it CRASHED (the error text says why).
2. `~/Library/Application Support/BIGHat/data/logs/launcher_crash.log`  (only exists if Python itself failed to start).
Also useful: the Mac model and year (Apple menu > About This Mac), and whether the app was opened from a downloaded .dmg or from Applications.

## Not changed on purpose
- `lib.rs` (the Rust shell) was NOT edited: there is no Rust toolchain in the dev sandbox and no cargo check in CI, so any edit would first be compiled by the release build; a typo would break the
  release for every platform. Raising the 60 s limit blindly could also hide a real crash.

## Ready-to-do once the log says which
- SLOW: raise HEALTH_TIMEOUT_SECS (e.g. 180) and say "still starting, first launch can take a few minutes" in the splash; consider PyInstaller `--onedir` for macOS (no unpack on every launch).
- CRASH: fix the error the log shows (it will name the file/module).
- Either way: make the dialog platform-specific (a Mac should not read "Windows security tool"), and say whether the backend was still running or had exited.
