# BIG Hat Presenter - Trivia Round Creator

## Problem Statement
Build a trivia round creation tool that allows users to create trivia rounds by entering questions and answers. The tool generates PowerPoint presentations saved to SharePoint for use in the existing BIG Hat Presenter trivia app.

## Architecture
- **Frontend**: React + Tailwind + shadcn/ui (dark navy theme matching existing trivia app)
- **Backend**: FastAPI + MongoDB + python-pptx
- **PowerPoint**: Auto-generated with proper slide structure per round type
- **SharePoint**: Integration pending Azure credentials

## User Personas
- Trivia hosts who create presentation content for live trivia events
- Need consistent PowerPoint formatting for the trivia app to parse correctly

## Core Requirements
- 5 round types: MC (10 Q's + A/B/C/D), REG (10 Q's), MISC (10 Q's), MYS (9 Q's + Theme?), BIG (1 Q + 8-15 answers + tiebreaker)
- Cover image upload (9:16 portrait)
- PowerPoint generation with specific slide structures
- Round naming conventions per type
- Save drafts to MongoDB
- Download generated .pptx files

## What's Been Implemented (March 18, 2026)
- Dashboard with 5 round type selection cards
- Dynamic round creator forms for all 5 types
- MC form: 10 questions with A/B/C/D options + answer
- REG/MISC form: 10 questions with answers
- MYS form: 9 questions + locked "Theme?" Q10 + answers
- BIG form: 1 question, 10 expandable answer lines (8-15), tiebreaker Q&A
- Cover image upload (9:16)
- Round naming with type-specific placeholders
- Full CRUD (create, list, get, delete rounds)
- PowerPoint generation with proper slide structure:
  - MC/REG/MISC: 14 slides (cover, Q1-Q10, review, gif, answers)
  - MYS: 13 slides (cover, Q1-Q9, review, gif, answers)
  - BIG: 7 slides (cover, question, gif, review, answers, tiebreaker, tiebreaker+answer)
- Download .pptx files
- Dark navy theme matching existing BIG Hat Presenter app
- 100% test pass rate (backend + frontend)

### SharePoint Integration (March 19, 2026)
- Azure AD authentication with client credentials flow (OAuth2)
- Microsoft Graph API integration for file upload
- Automatic folder routing: MC/REG/MISC/MYS/BIG files go to correct SharePoint folders
- "Save to SharePoint" button on round creator page
- SharePoint upload button on saved rounds in dashboard
- "On SharePoint" status badge for uploaded rounds
- Token validation on /api/sharepoint-status endpoint
- 100% test pass rate (20/20 backend + all frontend + SharePoint integration)

## Prioritized Backlog
### P0
- (DONE) SharePoint integration with Azure credentials

### P1
- PowerPoint template customization (fonts, colors, slide backgrounds)
- GIF image integration for the "Time's Up" slide
- Round editing capability

### P2
- Bulk round creation
- Preview slides in browser before generating
- SharePoint permission scoping (Sites.Selected)

## Next Tasks
1. Add actual GIF file support for the timer/transition slide
2. Add round editing capability (currently only create/delete)
3. Add slide preview feature
4. Fine-tune PowerPoint slide formatting to match existing templates
