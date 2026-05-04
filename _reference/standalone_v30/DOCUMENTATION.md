# BIG Hat Entertainment Hub - System Documentation

## App Overview
Unified Hub for BIG Hat Entertainment — live events company specializing in Trivia, Music Bingo & Karaoke.

## Architecture
- **Frontend:** React (Tailwind + Radix UI + Framer Motion)
- **Backend:** FastAPI + SQLite (Local Proprietary DB)
- **Security:** Rust-based Hardware ID (HWID) + salted/hashed passwords
- **Standalone Mode:** 100% Offline capable with local asset storage

## Core Modules & Tools
1. **Hub Dashboard** — Master SSO login, venue greeting, and modular app launcher.
2. **Calendar-Scheduler** — Comprehensive management of events, venues, pricing, and host roles.
3. **Trivia Presenter** — Proprietary 16:9 slide engine with dual-monitor (TV View) support.
4. **Round Roulette** — Slot machine randomizer for selecting trivia rounds.
5. **Build Wizard** — Step-by-step automated trivia show builder.
6. **Round Generator** — Integrated tool for creating trivia rounds with PPTX assets.
7. **Music Bingo** — Full game engine with real-time song calling and cinematic winner videos.
8. **Scoreboard Tool** — Animated leaderboard and tournament brackets with synthwave themes.
9. **Story Generator** — Built-in FFmpeg engine for creating Instagram Story promotional videos.
10. **Sponsor Portal** — Direct integration for managing event partnerships.

## Database Structure
The standalone system uses a proprietary SQLite database (`data/bighat.db`) to track:
- Venues, Employees, and Events
- License Seats and HWID registration
- Trivia Presentations and Slide Metadata
- Game History and Lockout (6-month rule)

## Proprietary Features (SaaS Model)
- **5-Seat License:** Each product key allows for up to 5 concurrent installations.
- **Master Admin Ownership:** The primary license holder manages all sub-admins and data.
- **Update Engine:** One-click proprietary update tool for rolling out new features.
- **Native Drive Mapping:** System maps directly to the primary drive (C:\BIG Hat) for speed.

**Proprietary Property of BIG Hat Entertainment.**
