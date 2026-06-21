# Tauri sidecar binaries

This directory holds platform-specific PyInstaller-frozen builds of
`backend/launcher.py`. The Tauri config (`tauri.conf.json`) references
`binaries/bighat-backend` as an `externalBin`, and Tauri's bundler
automatically picks the file whose name matches the build target triple,
e.g.:

| Target triple                  | Filename                                       |
|--------------------------------|------------------------------------------------|
| `x86_64-pc-windows-msvc`       | `bighat-backend-x86_64-pc-windows-msvc.exe`    |
| `aarch64-apple-darwin`         | `bighat-backend-aarch64-apple-darwin`          |
| `x86_64-apple-darwin`          | `bighat-backend-x86_64-apple-darwin`           |
| `x86_64-unknown-linux-gnu`     | `bighat-backend-x86_64-unknown-linux-gnu`      |

## CI builds (the real source of these binaries)

`.github/workflows/release.yml` runs `scripts/build_sidecar.py` on each
runner (windows-latest, macos-13, macos-14) which uses PyInstaller to
freeze the backend into a single executable, then drops it here with
the triple suffix Tauri expects.

## DO NOT CHECK IN COMPILED BINARIES

The frozen sidecars are 30–80 MB each. They are produced fresh on every
release run and uploaded to the GitHub Release page; never committed to
git.
