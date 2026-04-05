# Music Bingo App — PRD

## Original Problem Statement
BIG Hat Entertainment wants a music bingo application. The app should support dual game modes (Traditional Bingo with numbers, Music Bingo with songs/videos), dual views (Host control panel + Audience TV display), and integration with SharePoint for song lists.

## Core Requirements
1. **Lobby** with Quick Play and Custom Setup wizard
2. **Host Dashboard** — manages game, video player, controls
3. **Audience View** — separate window for TV display, mirrors host video via BroadcastChannel
4. **SharePoint Integration** — fetches song list Excel files from company SharePoint
5. **Timer settings** — Lightning: 10/15s, Regular: 30/45/60s

## Architecture
- **Frontend**: React + Tailwind CSS + Shadcn/UI + Framer Motion
- **Backend**: FastAPI (Python)
- **Database**: MongoDB (game state), SharePoint (song lists)
- **Real-time**: API polling (WebSockets disabled in environment)
- **Cross-window**: BroadcastChannel API for video mirroring

## What's Been Implemented
- [x] Full Lobby with Quick Play and Custom Setup wizard (Feb 2026)
- [x] Host Dashboard for both Traditional and Music Bingo (Feb 2026)
- [x] Audience View with BroadcastChannel video mirroring (Feb 2026)
- [x] SharePoint integration — verified working, returns real song data (Feb 2026)
- [x] Timer intervals: Lightning 10/15s, Regular 30/45/60s (Feb 2026)
- [x] Game CRUD API (create, start, pause, resume, bingo, verify, end, new round)
- [x] Back button navigation from Host to Lobby
- [x] UI animations (ball rolling, confetti on bingo)

- [x] "Song Info on TV" toggle in host controls — broadcasts to Audience View via BroadcastChannel (Feb 2026)

## Remaining Backlog

### P0
- None currently

### P1
- Sound effects for game events (round start, bingo win)
- Alternate bingo round types backend logic (4-Corners, 7, Blackout)

### P2
- Lightning Bingo game mode clarification
- Player leaderboard/profile system
- State management refactoring (custom hooks)
