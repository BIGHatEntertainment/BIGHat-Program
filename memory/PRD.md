# BIG Hat Entertainment Hub - PRD

## Original Problem Statement
Entertainment company in Phoenix, Arizona that specializes in live events (Trivia, Music Bingo & Karaoke). Merging several individually deployed apps (Trivia Presenter, Bingo, Schedule, Sponsor Portal) into one full-stack app with SSO abilities.

## Architecture
- **Frontend:** React (CRA + Tailwind CSS + Radix UI + Sonner)
- **Backend:** FastAPI (Python) with APScheduler
- **Database:** MongoDB (Motor async driver)
- **Auth:** Hub JWT (bcrypt, httpOnly cookies) + Schedule Host Login (name+password)
- **Design System:** Dark navy (#000e2a) + Gold (#fbdd68) theme

## User Personas
1. **Host** - Event host, views dashboard, claims events, accesses schedule tools
2. **Admin** - Manages users, events, venues, pricing
3. **Master Admin** - Nick Sellards (Sellards@bighat.live) - absolute authority

## What's Been Implemented (Jan 2026)

### Phase 1: Hub MVP
- JWT auth system with login, logout, token refresh
- Master admin seeded (Nick Sellards)
- Dashboard with app cards, chyron, schedule, resources
- Admin panel with user & event management (CRUD)
- Brute force protection, responsive layout

### Phase 2: Calendar-Scheduler Integration (Jan 2026)
- Full scheduler backend merged (1885 lines from Calendar-Scheduler-main)
- 5 employees seeded (Nick, Alex, Jordan, Casey, Taylor)
- 6 Phoenix-area venues seeded with pricing
- 24 recurring events seeded (Trivia, Bingo, Karaoke across 4 weeks)
- Schedule host login (name + password), admin passcode (121589)
- Event claiming/unclaiming with password confirmation
- Weekly schedule + monthly calendar views
- Venue pricing management
- Blackout dates system
- Venue roles (primary/secondary) with claiming rules
- Weekly & Monthly financial reports
- Payment acknowledgment system
- APScheduler for automated tasks (monthly archives, Friday/Monday emails)
- Chyron now shows real unclaimed events from schedule database

## Seeded Data
- **Employees:** Nick Sellards, Alex Rivera, Jordan Blake, Casey Morgan, Taylor Reed
- **Venues:** The Tap House, Rusty Nail Bar, Desert Ridge Tavern, Cactus Jack's, The Pint House, Copper Blues
- **Events:** 24 weekly recurring events (Trivia Tue/Thu/Sun, Bingo Wed/Sat, Karaoke Fri)

## Prioritized Backlog
### P0 - Critical
- Full Trivia game engine (user will upload zip)
- Full Bingo game engine (user will upload zip)

### P1 - Important
- Google OAuth social login
- Schedule notification emails (Resend integration)

### P2 - Nice to Have
- Karaoke app, Story Generator, Sponsor Portal, Training module
- Round Generator, Bingo Card Generator
- Scoreboard Tool

## Next Tasks
1. Integrate Trivia game engine when zip uploaded
2. Integrate Bingo game engine when zip uploaded
3. Add Google OAuth
4. Build out resource tools
