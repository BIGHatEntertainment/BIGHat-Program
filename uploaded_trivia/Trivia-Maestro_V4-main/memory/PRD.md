# Trivia Presentation Builder - PRD

## Original Problem Statement
Build a comprehensive trivia presentation management application with:
- PowerPoint generation and editing capabilities
- SharePoint integration for file storage
- Story Generator for Instagram content creation (MP4 format)
- Multi-user support with role-based access

## User's Preferred Language
English

## Design System - LOCKED (Feb 2025)

### Color Palette (from BH Trivia GIF reference)
```css
--bh-navy-900: #000e2a;    /* Main background */
--bh-navy-600: #141b50;    /* Cards, panels */
--bh-gold-500: #fbdd68;    /* Primary gold accent */
--bh-muted: #8892b0;       /* Secondary text */
```

## Recent Bug Fixes (Feb 2025)

### Story Generator Data Flow Fix - COMPLETED
**Problem:** Users on other computers couldn't get round names and images in Story Generator.

**Root Cause:** 
1. MongoDB presentations didn't store `locationFolder`, `roundNames`, `roundTypes`, or `host` fields
2. Matching logic between presentations and SharePoint JSON files was too strict (1-day date diff)
3. Existing presentations had SharePoint item IDs instead of actual round names

**Fixes Applied:**
1. **Updated TriviaPresentation model** (`/app/backend/models.py`):
   - Added `locationFolder`, `host`, `roundNames`, `roundTypes`, `numRounds` fields

2. **Updated presentation save logic** (`/app/backend/routes/presentations.py`):
   - Now extracts and stores all new fields when creating presentations
   - Stores clean location names and host names

3. **Updated API response** (`/app/backend/routes/story_generator.py`):
   - Returns `locationFolder` for proper matching
   - Prioritizes stored `roundNames`/`roundTypes` over runtime resolution

4. **Improved matching logic** (`/app/frontend/src/addons/story-generator/pages/StoryGenerator.jsx`):
   - Method 1: Location folder + closest date within 7 days (was 1 day)
   - Method 2: Location folder + name similarity
   - Method 3: Only one build for location - use it
   - Method 4: Word matching across all builds
   - Added detailed console logging for debugging

5. **Created migration endpoint** (`/app/backend/routes/admin.py`):
   - `POST /api/admin/migrate-presentations` - backfills existing presentations
   - Migrated all 10 existing presentations successfully

**Verification:**
- Round names now display correctly: "Multiple Choice", "History_4", "World Records", "Mystery", "BIG_CollegeFootballStadium"
- Images and assets load from SharePoint

## Architecture

### Data Flow for Story Generator
```
1. User creates presentation → MongoDB stores presentation + SharePoint JSON saved
2. User opens Story Generator → Dashboard shows presentations from MongoDB
3. User clicks presentation → StoryGenerator.jsx:
   a. Fetch builds list from SharePoint
   b. Match presentation to build by locationFolder + date/name
   c. Load JSON with round names from matched build
   d. Fetch assets (location image, host GIF, background)
   e. Display preview with actual round names
```

### Key Files Modified
- `/app/backend/models.py` - TriviaPresentation model
- `/app/backend/routes/presentations.py` - Save logic
- `/app/backend/routes/story_generator.py` - API response
- `/app/backend/routes/admin.py` - Migration endpoint
- `/app/frontend/src/addons/story-generator/pages/StoryGenerator.jsx` - Matching logic

## Test Accounts
- **Admin Users:** Nick, Caelie, Tommy (no password required)

## Third-Party Integrations
- Microsoft SharePoint (MSAL)
- Framer Motion (animations)
- html2canvas (frame capture)
- FFmpeg (server-side video conversion)

## Recently Completed (Feb 2025)

### Smart Score Tracker Feature - COMPLETED
**Problem:** Hosts had to manually set the round count in the score tracker, even though this information was already available from the loaded presentation.

**Requirements:**
1. Auto-detect number of rounds (3, 5, or 6) from the presentation and set score tracker accordingly
2. Allow manual override if host wants to switch modes
3. For 6-round presentations, intelligently determine if the extra round is REG or MISC based on presentation data
4. Highlight team name when entering scores to prevent confusion

**Implementation:**
1. **Updated ScoreTrackerModal.jsx** (`/app/frontend/src/components/ScoreTrackerModal.jsx`):
   - Added `roundTypes` prop to receive presentation's round type configuration
   - Smart `currentRounds` memo that uses `roundTypes` when available, falls back to defaults
   - Added `focusedInput` state to track which score input is focused
   - Team name highlighting with yellow background and ring when entering scores
   - Auto-initialization on modal open based on `defaultRoundMode`
   - Arrow Up/Down keyboard navigation between team rows

2. **Updated Editor.jsx** (`/app/frontend/src/pages/Editor.jsx`):
   - Added `detectedRoundCount` memo that reads from: `presentation.numRounds` → `roundTypes.length` → slide metadata → default (5)
   - Added `detectedRoundTypes` memo that extracts round types from presentation data or slide metadata
   - Now fetches round config from trivia_presentations API
   - Fallback to story-builds JSON if trivia data doesn't have round info

3. **Updated trivia_viewer.py** (`/app/backend/routes/trivia_viewer.py`):
   - Now returns `numRounds`, `roundTypes`, `roundNames` in API response

**UI Fixes (Feb 2025):**
- ✅ Score input text changed to black (was yellow)
- ✅ Swag and Team Name headers changed to dark grey
- ✅ Round buttons: yellow (unselected), green (selected)
- ✅ X close button changed to red
- ✅ Arrow keys navigate between team rows (don't change number values)

**Features:**
- ✅ 3-round mode: REG, MISC, BIG(x3) - for Live Stream Shows
- ✅ 5-round mode: MC, REG, MISC, MYS(x2), BIG(x3) - standard format
- ✅ 6-round mode: MC, REG, REG/MISC (smart), MISC, MYS(x2), BIG(x3)
- ✅ Team name highlighting: Yellow background + ring when score input focused
- ✅ Manual override: Users can still switch modes with confirmation
- ✅ Data loaded from presentation JSON file (stored in MongoDB/SharePoint)

## Pending Tasks
None - All requested features are implemented.

### Story Generator MP4 Conversion - COMPLETED (Feb 2025)
**Problem:** Videos were being downloaded as WebM format, which is not compatible with social media platforms like Instagram.

**Solution:** 
1. The MP4 conversion via FFmpeg was already implemented but had a 120-second timeout that was too short for larger videos
2. Increased timeout to 300 seconds (5 minutes)
3. Optimized FFmpeg parameters for faster conversion (crf 28, threads 0)
4. Reduced video bitrate from 5 Mbps to 2.5 Mbps for smaller files
5. Added better progress messages during conversion
6. Added proper error handling with informative messages

**Files Modified:**
- `/app/backend/routes/story_generator.py` - FFmpeg conversion optimizations and timeout increase
- `/app/frontend/src/addons/story-generator/components/VideoEncoder.jsx` - Better progress UI and error handling

**Deployment Ready:** ✅ Yes - no hardcoded URLs, uses environment variables

## Backlog (P2-P3)
- Complete Rust migration for image extraction
- Package as Desktop App (Tauri/Electron)
- Performance refactoring: Break down large Editor.jsx component
