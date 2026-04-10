# BIG Hat Entertainment - Event Scheduling App

## Original Problem Statement
Entertainment business providing Trivia, Karaoke, and Music Bingo services needs a scheduling page for employees to pick events they want to work.

## Core Requirements
- Calendar view (week default + monthly) for events
- Event claiming (one employee per event) with confirmation
- Host login (Google OAuth primary, password fallback)
- Admin panel (universal passcode "121589" or admin personal password)
- Event management (CRUD, assign, unclaim)
- Location pricing per venue per event type
- Weekly & Monthly financial reports
- Blackout dates for host unavailability
- "Monkey Pants" franchise venue special logic ($150 flat, owner exclusion from outgoing)
- BIG Hat branding on all pages

## Architecture
- **Frontend:** React, Tailwind CSS, Shadcn/UI, Axios, date-fns
- **Backend:** Python FastAPI, Motor (async MongoDB driver)
- **Database:** MongoDB
- **Auth:** Google OAuth (via emergentintegrations), session-based tokens, password fallback

## What's Been Implemented

### Core Features (Complete)
- Google OAuth + password login
- Weekly schedule + monthly calendar views
- Event claiming/unclaiming with password confirmation
- Admin panel with all management tabs
- Venue pricing management
- Blackout dates (host + admin report)
- Weekly & Monthly financial reports
- Payment acknowledgment system

### Primary/Secondary Venue Role System (Feb 2026) — NEW
- `venue_roles` MongoDB collection
- Two role categories per venue: **Trivia** and **Bingo/Karaoke**
- Services determined by venue pricing (price > $0 = offered)
- One primary per category per venue, unlimited secondaries
- Primaries must be secondary at at least one other venue
- Full Profile page at `/profile` for hosts to view/manage their roles
- Admin "Roles" tab to assign/remove roles
- Validation warnings for unmet requirements

### Primary Claiming Rules (Feb 2026) — NEW
- **Early Access:** Primaries can claim events at their venue+category immediately when added
- **Blackout Auto-Release:** If primary has a blackout date on the event date, event opens to all
- **Sunday Deadline:** If primary hasn't claimed by the Sunday prior to the event, it opens to all
- Backend enforces rules (403 for non-primary on locked events)
- Frontend shows lock icon + "Reserved for [name]" + "Opens [date]" on locked events

### Email Notifications (Apr 2026) — NEW
- **Friday Primary Reports:** Automated email to primaries with venue events for following week (claimed/unclaimed/blackout status)
- **Monday Secondary Availability:** Automated email to secondaries listing open hosting spots for current week
- Using Resend API, scheduled via APScheduler (Friday 9AM, Monday 9AM MST)
- Admin can manually trigger from Roles tab; rate-limited (0.6s between sends)

### Monthly Income Breakdown & Timezone Fix (Apr 2026) — NEW
- Per-event-type income breakdown in Monthly Reports (count × price/event = subtotal)
- Displayed in both Incoming Revenue card and venue-specific section for full transparency
- **CRITICAL FIX:** Income API now uses MST (UTC-7) month boundaries to match the frontend calendar. Events near month edges (e.g., March 31 evening stored as April 1 UTC) were incorrectly counted in the wrong month, inflating revenue.

### Key API Endpoints
- `GET/POST /api/venue-roles` — CRUD for venue roles
- `GET /api/venue-roles/services` — Venue service offerings
- `GET /api/venue-roles/validate/{id}` — Validate secondary requirement
- `GET /api/venue-roles/employee/{id}` — Employee's roles
- `GET /api/venue-roles/venue/{id}` — Venue's roles
- `GET /api/events/claim-eligibility` — Batch claim status (primary_only vs open)
- `POST /api/events/{id}/claim` — Enforces primary claiming rules

## Prioritized Backlog

### P0
- Verify Monthly Report financial logic (owner payment exclusion, historical persistence)

### P1
- Fix React Hook useEffect dependency warnings

### P2
- Refactor backend/server.py into separate routers (auth, admin, events, reports)
- Simplify MonthlyReports.jsx into smaller components

## Key DB Collections
- `events`, `employees`, `venues`, `venue_pricing`
- `payment_acknowledgments`, `monthly_archives`
- `blackout_dates`, `venue_roles` (NEW)
- `oauth_users`, `user_sessions`

## Credentials
- Admin passcode: `121589`
- Default host password: `B1GHat`
- Owner email: `sellards@bighat.live`
