# Program build agent task (api.bighat.live license/download server): serve the Intel Mac installer (2026-11-01)
Only for the agent that builds the license/download server. Do NOT touch the desktop app.

## Why
A customer has an Intel MacBook and could not download. The release workflow builds an Intel .dmg again (BIGHat-Program PR "macos-intel-build"), named like
`BIG.Hat.Entertainment_<ver>_x64.dmg` (Apple Silicon is `..._aarch64.dmg`). The desktop app's Update tool already asks for platform key `macos_intel` and
already handles a missing one (it opens the release page). So the SERVER must now return a real link for it.

## What to check and do
1. `GET /api/downloads/latest` must return `platforms.macos_intel = {url, version, filename}` pointing at the release's `*_x64.dmg` asset (match `x64.*\.dmg$` or `x86_64.*\.dmg$` or `intel.*\.dmg$`, case-insensitive; NOT the `*_x64-setup.exe`, which is Windows).
   `macos_apple` must keep matching only `aarch64|arm64 .dmg`.
2. `GET /api/downloads/{platform}` for `macos_intel` returns the same link. A release that has no Intel .dmg yet returns `url: null` (as today), never the Apple Silicon file.
3. The website/download page must show an "Intel Mac" button next to "Apple Silicon" (a short line: "Mac with an Intel chip: Apple menu > About This Mac shows Intel").
4. Cache: if the manifest is cached, refresh it when a new release is published (or keep the TTL short) so Intel users get the new .dmg.

## Acceptance
- With a release holding the three installers: windows -> .exe, macos_apple -> aarch64 .dmg, macos_intel -> x64 .dmg, each different.
- With a release holding no Intel .dmg: macos_intel url is null and macos_apple is unchanged.
- An Intel Mac running the desktop app's Update tool gets the x64 .dmg link.
