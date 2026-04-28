# BIG Hat Entertainment Hub - PRD

## App Overview
Unified SSO hub for BIG Hat Entertainment (Phoenix, AZ) — live events company specializing in Trivia, Music Bingo & Karaoke.

## Architecture
- **Frontend:** React (CRA + Tailwind + Radix UI + Sonner + Framer Motion)
- **Backend:** FastAPI + APScheduler + WebSocket
- **Database:** MongoDB (Motor async)
- **Auth:** JWT (bcrypt, httpOnly cookies + localStorage)
- **Services:** SharePoint (MSAL + Rust PPTX Parser), GridFS, FFmpeg

## Integrated Apps (9 tools + 1 external link)
1. **Hub Dashboard** — SSO login, chyron ticker, schedule, resources
2. **Calendar-Scheduler** — Events, venues, pricing, roles, reports, blackouts
3. **Trivia Presenter** — Slide editor, SharePoint PPTX conversion, score tracker
4. **Round Roulette** — Slot machine randomizer for trivia rounds
5. **Build Wizard** — Step-by-step trivia show builder
6. **Round Generator** — Create trivia rounds with PPTX generation
7. **Music Bingo** — Full game engine with WebSocket, audience TV view
8. **Scoreboard Tool** — Animated leaderboard + tournament brackets
9. **Story Generator** — Instagram Story video creation (FFmpeg)
10. **Sponsor Portal** → External link to sponsor.bighat.live

## Database (23 collections)
users, employees, venues, events, venue_pricing, payment_acknowledgments, blackout_dates, venue_roles, login_attempts, changelog, trivia_presentations, round_usage, trivia_hosts, trivia_locations, trivia_rounds, presentations, story_builds, story_gen_presentations, rounds, games, section_status, sponsors, sponsor_locations

## Completed Work (Latest)
- **2026-04-28:** Scoreboard Synthwave grid rewritten — parallel vertical/horizontal lines with fixed 10-step CSS mask fade to 0% at the gold horizon. Uses SVG grid + `mask-image` gradient for smooth scrolling fade effect.
- **2026-04-28:** Bingo & Karaoke Story Generator added — SharePoint sharing URL resolution, event asset listing, preview images, 20s video generation (10s location + 10s host GIF), QR code for mobile download. Both event types use separate SharePoint folders with correct accent colors (purple for Bingo, red for Karaoke).

## Pending
- Karaoke app integration (P1 — currently "Coming Soon" placeholder)
- Training tool integration (P2 — currently "Coming Soon" placeholder)

## Credentials
- Master Admin: Sellards@bighat.live / BigHat2024!
- All hosts: default password B1GHat
- Azure SharePoint: configured in .env
