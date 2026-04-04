# APP STATE — SINGLE SOURCE OF TRUTH
# Last updated: 2026-03-01
# Read this file BEFORE making ANY changes. Update AFTER every change.

## VERIFIED WORKING (DO NOT BREAK THESE):
- Presentation builder (Build Trivia wizard + Slot Machine)
- Presentation editor (slide viewing, thumbnails)
- Score tracker (team names, round scores, localStorage persistence, debounced saves)
- Score sending to slides (handleSendScores with double-click guard)
- Overlay loading (all 6 locations, including BIG.gif)
- Post-overlay review formatting (MC/REG/MISC posInRound 11, MYS posInRound 10)
- Answer slide formatting (MC/REG/MISC posInRound 13, MYS posInRound 12) — MUST NOT be touched by review formatter
- BIG round Python parser with recursive group shape extraction
- Presentation mode (host + audience views)
- Final scores display with scrolling
- End Presentation button (saves scores to SharePoint by location)
- QR code for mobile video download
- Slide formatting state machine (slideOp: idle/formatting/overlaying)
- Video element support (mp4/webm extracted from PPTX, autoplay+loop, audio on audience only)

## STORY GENERATOR SPEC (LOCKED):
- Total duration: 25 seconds (3s location + 3s host + 19s rounds)
- Framerate: 30fps — captureStream(30) on user's hardware
- CLIENT-SIDE recording: Canvas + MediaRecorder per section (step by step)
- Server only does: 1) fetch assets (build-asset-urls), 2) WebM→MP4 transcode (convert-webm)
- Host: .gif FIRST (via build-asset-urls), .png fallback
- Each section records independently — no single long recording
- WebM recorded on client → sent to server → fast MP4 transcode → download + QR
- Output: MP4 <15MB, works on all social media

## FORMATTING RULES (LOCKED):
- Review slides (MC/REG/MISC pos 11, MYS pos 10): Full width (x=25, w=1870), 36px font, 50px gap
- Answer slides: ANSWER_X=831, ANSWER_SPACING=75, 30px font — NEVER caught by review formatter
- Question slides: 9:16 centered area (CONTENT_X=706, CONTENT_W=508)
- BIG round: Content-aware formatting — classifies 3 text boxes by content:
  1. Instruction text ("X Points each. No order.") → yellow, top + 50px
  2. Question text (longest content) → white, 100px below instruction
  3. Points text ("For XX Points") → white, 100px below question
  Answer slides: left-aligned numbered items (unchanged)
- Post-overlay pass: posInRound ONLY detection — NO content-based fallback
- Auto-format runs on EVERY load (setShouldAutoFormat=true unconditionally)

## SHAREPOINT PATHS:
- Overlays: 01_Trivia/Web App/00_Builder/02_Locations/{NN_Location}/
- Story assets: 01_Trivia/Web App/01_Socials/01_Locations/, 02_Hosts/, 03_Backgrounds/
- Build JSONs: 01_Trivia/Web App/00_Builder/02_Locations/{NN_Location}/00_Built/
- Scores: Saved via sharing URL, organized by clean location name

## RACE CONDITION PROTECTIONS:
- slideOp state machine (idle/formatting/overlaying) — single useEffect
- sendingScoresRef guard on handleSendScores
- Debounced localStorage writes (300ms) in ScoreTrackerModal
- No auto-save during score updates (deferred to End Presentation)
- captureStream(30) for video — browser controls frame timing, not setTimeout

## FILES OF IMPORTANCE:
- /app/frontend/src/pages/Editor.jsx — formatting, overlays, score handling
- /app/frontend/src/components/PresentationMode.jsx — presentation + audience
- /app/frontend/src/components/ScoreTrackerModal.jsx — score input
- /app/frontend/src/addons/story-generator/components/VideoEncoder.jsx — video generation
- /app/frontend/src/addons/story-generator/components/VideoPreview.jsx — SECTION_DURATIONS
- /app/frontend/src/addons/story-generator/pages/StoryGenerator.jsx — asset loading
- /app/backend/hybrid_pptx_converter.py — PPTX parsing (BIG uses Python with recursive shapes)
- /app/backend/routes/story_generator.py — asset URL endpoint
- /app/backend/story_generator_service.py — SharePoint asset lookup
- /app/backend/routes/scores.py — score saving to SharePoint
- /app/backend/routes/story_builds.py — build JSON saving (validates location folder prefix)
