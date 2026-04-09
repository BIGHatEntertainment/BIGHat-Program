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

## Credentials
- Master Admin: Sellards@bighat.live / BigHat2024!
- All hosts: default password B1GHat
- Azure SharePoint: configured in .env
