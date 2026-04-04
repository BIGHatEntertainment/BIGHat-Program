# STORY GENERATOR CHANGELOG — DO NOT DELETE
# This file tracks what is CORRECT and what has FAILED so changes are never reverted.

## CONFIRMED REQUIREMENTS (from user):
- Video: 25 seconds total, MP4 output
- Section 1 (Location image): 3 seconds
- Section 2 (Host .gif): 3 seconds  
- Section 3 (Rounds background + text): 19 seconds
- Framerate: 30fps (750 total frames for 25s)
- Frame timing: MediaRecorder uses WALL CLOCK time, so setTimeout must be ~33ms per frame
- Host images are .gif files on SharePoint at 01_Socials/02_Hosts/{Name}.gif
- Host images also have .png versions at same location
- Location images at 01_Socials/01_Locations/{folder}/{image}
- Background images at 01_Socials/03_Backgrounds/{folder}/{image}
- Background MUST NEVER be blank — use gradient fallback if image not found
- No placeholder/fake images — return null if not found, frontend shows warning
- QR code appears after video generation for mobile download

## KNOWN ISSUES FIXED:
- setTimeout(2) caused 2+ minute videos (wall clock timing)
- setTimeout(33) frame loop ALSO caused 40+ second videos (canvas draw overhead added to delay)
- FINAL FIX: captureStream(30) + requestAnimationFrame real-time loop = exact 25s video
- Missing backgrounds caused blank rounds section — added gradient fallback
- Host image lookup only checked .png/.jpg — NOW checks .gif FIRST, then .png
- _get_sharepoint_assets for hosts filtered out .gif files — FIXED to include .gif
- Placeholder images showed fake data (removed, returns null)
- WP Gilbert background file named "WP-Gilbert.jpg" (HYPHEN) didn't match "wp_gilbert" lookup
  FIX: All asset name matching now normalizes hyphens to underscores alongside spaces
- Background image was 3.5MB base64 — html2canvas FAILED to render it in an <img> tag
  FIX: Bypass html2canvas entirely for rounds section. Pre-load background as Image object,
  draw directly onto canvas with ctx.drawImage(), then draw round boxes with canvas 2D API.
  No more html2canvas dependency for the background section.
- ALL THREE sections (location, host, rounds) now use Canvas 2D API directly — html2canvas
  removed from entire video pipeline. Fixes mobile rendering failures.
- Font: Round name text uses 'Inter, Arial, sans-serif' (web-safe) instead of 'Lemonada, cursive'
  which wasn't loading on mobile canvas. document.fonts.load() called before rendering.
- Gradient fallback shows location/host NAME text if images fail to load.
- BASE64 DATA URLs TOO LARGE FOR MOBILE Image() OBJECTS — 3.5MB base64 strings fail silently.
  FIX: Added dataUrlToBlobUrl() helper that converts base64 to Blob → URL.createObjectURL().
  Blob URLs use native binary memory (not JS string heap), works reliably on mobile.
  All blob URLs tracked and cleaned up with URL.revokeObjectURL() after video generation.

## THINGS THAT MUST NOT BE CHANGED:
- Server-side FFmpeg assembly via POST /api/story-generator/assemble-video
- Frontend sends 3 JPEG frames + durations → backend FFmpeg concat → exact 30fps MP4
- NO browser MediaRecorder/captureStream — all timing is server-side FFmpeg
- FPS = 30 (in VideoEncoder.jsx and backend)
- Total duration = 25 seconds (3 + 3 + 19)
- Location = 3s, Host = 3s, Rounds = 19s
- VideoPreview.jsx SECTION_DURATIONS must match
- Host lookup: .gif FIRST, then .png fallback
- ALL sections use Canvas 2D API + blob URL image loading (no html2canvas)
- Background: gradient fallback if image not found

- GIF hosts caused FFmpeg hang: -ignore_loop 0 creates infinite stream that xfade cant process
  FIX: Pre-convert GIF to fixed-duration MP4 clip BEFORE xfade pipeline (takes ~2s)
  Then use the clip as regular video input — no infinite stream
