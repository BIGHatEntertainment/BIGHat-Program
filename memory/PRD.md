# BIG Hat Entertainment Hub - PRD

## Architecture
- **Frontend:** React (CRA + Tailwind + Radix UI + Sonner + Framer Motion)
- **Backend:** FastAPI + APScheduler + WebSocket
- **Database:** MongoDB (Motor)
- **Auth:** Hub JWT + Schedule Host Login (SSO passthrough)
- **Services:** SharePoint (MSAL), Rust PPTX Parser, GridFS, Overlay Engine

## Integrated Apps
1. **Hub Dashboard** — SSO login, chyron, schedule, resources
2. **Calendar-Scheduler** — Events, venues, pricing, roles, reports
3. **Trivia Presenter** — Presentations, slide editor, score tracker, overlays
4. **Round Roulette** — Slot machine randomizer for trivia rounds
5. **Build Wizard** — Step-by-step trivia show builder
6. **Round Generator** — Create trivia rounds with PPTX generation
7. **Music Bingo** — Full bingo game engine with WebSocket, audience view

## Database Collections
users, employees, venues, events, venue_pricing, payment_acknowledgments, monthly_archives, blackout_dates, venue_roles, oauth_users, user_sessions, login_attempts, changelog, trivia_presentations, round_usage, trivia_hosts, trivia_locations, trivia_rounds, presentations, slides_metadata, trivia_scores, rounds (round generator), bingo_games

## Next Tasks
- Connect Round Generator SharePoint credentials
- Karaoke app (Coming Soon)
- Story Generator, Sponsor Portal, Scoreboard Tool
