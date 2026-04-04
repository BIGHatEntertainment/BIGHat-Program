# BIG Hat Entertainment Hub - PRD

## Original Problem Statement
Entertainment company in Phoenix, Arizona merging Trivia Presenter, Bingo, Schedule, and Sponsor Portal into one SSO hub.

## Architecture
- **Frontend:** React (CRA + Tailwind + Radix UI + Sonner)
- **Backend:** FastAPI + APScheduler
- **Database:** MongoDB (Motor)
- **Auth:** Hub JWT + Schedule Host Login (SSO passthrough)

## What's Been Implemented

### Phase 1: Hub MVP (Jan 2026)
- JWT auth, master admin (Nick Sellards), dashboard, admin panel, chyron

### Phase 2: Calendar-Scheduler Integration (Jan 2026)
- Full scheduler merged (employees, venues, events, pricing, blackouts, roles, reports)
- 11 real employees, 7 venues, 97 events imported from deployed app
- SSO passthrough - single login for all sections

### Phase 3: Design Consistency (Jan 2026)
- All pages use dark navy + gold design system
- Chyron: seamless loop, current week only, MST times, functional claim button

### Phase 4: Trivia Presenter Integration (Jan 2026) - NEW
- Trivia Dashboard at /trivia with 64 presentations, search, filter
- Admin "Round History" tab - view previously chosen rounds by location
- Round usage tracking: 333 records across 6 locations
- Color-coded round types: MC, REG, MISC, MYS, BIG
- Stats: Shows count, Rounds Used count in header

## Database Collections
- users, employees, venues, events, venue_pricing
- payment_acknowledgments, monthly_archives, blackout_dates, venue_roles
- oauth_users, user_sessions, login_attempts, changelog
- trivia_presentations, round_usage (NEW)

## Prioritized Backlog
### P0 - Full Bingo game engine
### P1 - Google OAuth, Notification emails
### P2 - Karaoke, Sponsor Portal, Story Generator, Training, Scoreboard Tool

## Next Tasks
1. Upload Bingo game engine zip for integration
2. Build out resource tools
