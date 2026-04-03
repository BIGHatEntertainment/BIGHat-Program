# BIG Hat Entertainment Hub - PRD

## Original Problem Statement
Entertainment company in Phoenix, Arizona that specializes in live events (Trivia, Music Bingo & Karaoke). Merging several individually deployed apps (Trivia Presenter, Bingo, Schedule, Sponsor Portal) into one full-stack app with SSO abilities. The app serves as a streamlined single sign-on hub for all hosts to operate their events.

## Architecture
- **Frontend:** React (CRA + Tailwind CSS + Radix UI)
- **Backend:** FastAPI (Python)
- **Database:** MongoDB (Motor async driver)
- **Auth:** JWT (bcrypt hashing, httpOnly cookies + localStorage fallback)
- **Design System:** Dark navy (#000e2a) + Gold (#fbdd68) theme from DESIGN-SYSTEM.md

## User Personas
1. **Host** - Regular event host, can view dashboard, claim events, access tools
2. **Admin** - Can manage users, create/edit events, access admin settings
3. **Master Admin** - Nick Sellards (Sellards@bighat.live) - absolute authority over all app functions

## Core Requirements (Static)
- [x] SSO Authentication (JWT + role-based access)
- [x] Dashboard with event app cards (Trivia, Bingo, Karaoke)
- [x] Scrolling chyron for unclaimed events
- [x] Schedule section with upcoming events
- [x] Resources & Tools grid (Trivia Tools, Bingo Tools, Socials, Business)
- [x] Admin Settings (User Management, Event Management)
- [x] Master Admin seeding
- [x] Role-based access control (host, admin, master_admin)
- [ ] Google OAuth integration
- [ ] Full Trivia game engine
- [ ] Full Bingo game engine
- [ ] Karaoke app (Coming Soon)

## What's Been Implemented (Jan 2026)
- Complete JWT auth system with login, logout, token refresh
- Master admin seeded (Nick Sellards)
- Dashboard with app cards, chyron, schedule, resources
- Admin panel with user & event management (CRUD)
- Brute force protection on login
- Sample events seeded
- Dark navy + gold design system fully applied
- Responsive layout with mobile support

## Prioritized Backlog
### P0 - Critical
- Full Trivia game engine (user will upload zip files)
- Full Bingo game engine (user will upload zip files)

### P1 - Important
- Google OAuth social login
- Event claiming workflow refinement
- Schedule app integration (for chyron data)

### P2 - Nice to Have
- Karaoke app implementation
- Story Generator (Instagram stories)
- Sponsor Portal
- Training module
- Scoreboard Tool
- Round Generator AI
- Bingo Card Generator

## Next Tasks
1. Integrate Trivia game engine when zip uploaded
2. Integrate Bingo game engine when zip uploaded
3. Add Google OAuth as secondary auth method
4. Build out resource tools (Round Generator, Bingo Card Generator, etc.)
