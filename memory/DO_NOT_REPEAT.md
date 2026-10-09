# DO NOT REPEAT (read this BEFORE changing anything)

Each entry: what we tried, what actually happened, why, and the rule. Newest first. Times are MST (git shows UTC; subtract 6 hours).
If you are about to do something listed here, STOP and ask the owner first.

## KARAOKE VIDEO PLAYER (the TV / audience window)

### 1. NEVER play the song in a bare <iframe src="youtube.com/embed/...">  (tried alpha.98, 99, 100: ALL FAILED on the owner's PC)
- What happened: the TV showed "This video is unavailable" for every song. It worked fine in the web prototype.
- Why: the prototype runs in a browser at an https address. This program runs in a desktop window (Tauri/WebView2, http://127.0.0.1).
  A bare iframe sends YouTube no usable origin, so YouTube refuses it (error 153 family). YouTube's own player script adds the origin itself.
- RULE: the TV song player is `new YT.Player(...)` from https://www.youtube.com/iframe_api. This is how the FIRST port (alpha.70) did it and how
  every alpha that played video for the owner did it (70 to 96). Settings: width/height "100%", playerVars autoplay 1, controls 0, rel 0,
  modestbranding 1, playsinline 1, disablekb 1, fs 0.
- "Copy the prototype" means copy its LAYOUT, SEARCH and STORED LINK. It does NOT mean copy its bare iframe. We already tried. Do not try again.

### 2. NEVER add your own playback ideas on top of the first port (alpha.98 to 101 each added some)
- Things that were added and removed again: a stopwatch clock instead of the YouTube player's real time; a host-sent "waiting" list for the up-next bar;
  extra referrer settings (meta tag and iframe attributes); a TV debug strip; an assign-time YouTube "can this play" check and its endpoint.
- Why it is bad: each one was a guess that was never seen working on the owner's PC, and together they conflicted. The owner lost an afternoon.
- RULE: change ONE thing at a time, tied to a real error the owner reported. If the owner says "port it from the prototype", copy; do not reinterpret.

### 3. NEVER put a second full-size YouTube player over the video box (alpha.89 "buffer holder")
- It started the next song muted at full size, hidden over the song. Replaced in alpha.102 by the first port's preload:
  a 1px muted player with autoplay 0 that only CUES the next video (never plays it). When it is cued the TV tells the host "ready".

### 4. Songs YouTube will not play outside youtube.com (error 101/150) are the VIDEO's problem, not the player's
- The TV shows the reason in plain words (explainVideoError in karaokeFlow.js). The backend search drops videos whose status.embeddable is false (alpha.99, kept).
- RULE: before blaming the player, check whether it fails for ONE song or for ALL songs. One = blocked video. All = player/origin problem.

## TESTING (these cost hours on 2026-10-08)

### 5. Karaoke test bundles: use frontend/scripts/bingo/karaoke_all.build.mjs  (NOT build_aud.mjs)
- build_aud.mjs builds the BINGO audience page. Running it and then the karaoke test checks the OLD karaoke code. Test passes for alpha.99 and 100 were therefore meaningless.
- Procedure: copy karaoke_all.build.mjs, karaoke_aud.check.mjs, karaoke_player.check.mjs, karaoke_flow.check.mjs to /tmp/rtest (the build script writes
  /tmp/rtest/kaud.bundle.mjs and the host bundle), run the build, THEN the checks.
- RULE: after editing, prove a new test can FAIL (break the feature on purpose, see the red, restore). A test that never failed has proved nothing.

### 6. Never say "pushed" unless the release actually built (alpha.90 failed this way). Check the GitHub Actions run, or say plainly "I did not check the build".

### 7. A regression in a released build makes the owner very angry. Do not change files the owner locked (Trivia player, finished modules) without being asked.

## DATA
### 8. Anything the owner types must survive updates (re-entering data after updates is the number one complaint). Venues live in the Schedule only; backup copy in AppData\backups\schedule.
