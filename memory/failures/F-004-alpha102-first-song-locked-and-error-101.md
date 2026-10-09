# F-004  alpha.102: first song never loaded (host lock) and the TV refused the song (error 101/150)
Status: FIXED-UNCONFIRMED (host lock removed in alpha.103; search ported from the prototype in alpha.104; waiting for the owner's PC test; TV refusal cause still not proven)      Severity: blocked
## 1. When (MST, with times)
- Reported by owner: 2026-10-08 18:59 (screenshots taken 18:41 and 18:43), after downloading alpha.102 (commit 9d51418).
- Release it appeared in: alpha.102.
- Fix attempts: alpha.103 (local) removed the host lock. TV cause not found.
- Confirmed fixed by owner at: NOT YET.
## 2. What the owner saw (exact words)
- "downloaded alpha.102 and immediately in the karaoke player the first song didnt even load (fix), started anyways and immediately it wouldnt play AGAIN! (fix). use these files directly from the prototype repo."
- Host screenshot: "Loading Nick's song... 0%", "The next song could not load", links "Retry loading" and "Start anyway".
- TV/host screenshot: "This song could not play on the TV. The owner of this video does not allow it to be played outside YouTube." for Nick, Foo Fighters - My Hero (Karaoke Version).
## 3. What the owner expected
- The first song loads and plays at once, exactly like the prototype.
## 4. What actually happened
- The TV's cued preload never reported ready, so the alpha.89 lock (preload under 100%) kept Next Singer disabled. The owner pressed "Start anyway". YouTube's own player then returned error 101 or 150 for the song.
## 5. Evidence
- karaokeFlow.js nextSingerState returned reason "loading" while preloadPercent < PRELOAD_READY (100). explainVideoError maps 101/150 to the "does not allow" text. The three prototype files supplied by the owner are byte-identical to BIGHat-Beta-Testing (diff -q).
- audienceWindow.js and tauri.conf.json are unchanged since alpha.96 (git diff v32.0.0-alpha.96 HEAD -- src-tauri/tauri.conf.json frontend/src/lib/audienceWindow.js shows only the version number).
## 6. Root cause
- HOST LOCK: PROVEN. The lock waits for a preload report that a failing preload never sends.
- TV REFUSAL: UNKNOWN. Error 101/150 means YouTube will not play that video in an embedded player in this context. It can be the video, or the origin of the window. Not proven which.
## 7. Why it was not caught earlier
- The sandbox cannot reach YouTube, so no test ever saw a real refusal. The alpha.102 notes said "not verified on a real PC", but the lock was kept anyway although the first port never had one.
## 8. Every fix attempt
- alpha.103 (local): removed the "loading" lock; Start anyway / Retry loading no longer needed; tests rewritten. The preload still runs and its status strip still shows.
## 8b. More fix attempts
- alpha.103 (790889b, 2026-10-08 ~19:15): host lock removed (works). Also changed the search to always drop blocked videos even to empty. WRONG: the prototype does the opposite (see 6c).
- alpha.104 (2026-10-08 ~19:50): the prototype's CURRENT search ported as written (yt-dlp, no key; embeddable filter only when a key is saved; never an empty list from filtering; providers first; 24h cache with 60 LRU; retry; fuzzy fallback; no-op pre-warm). yt-dlp added to the installer requirements. Real yt-dlp returned a real karaoke result from the sandbox.
## 9. What NOT to do again
- Do not gate the host on anything the TV must report (preload, buffer). The host must always be able to start a waiting singer. See DO_NOT_REPEAT.md #9.
## 10. Test that proves the fix
- karaoke_flow.check.mjs "a waiting singer with a song can ALWAYS start" and karaoke_player.check.mjs "Next Singer is usable at once". Proof they can fail: the lock was put back and the rules check failed.
## 11. Files touched
- frontend/src/pages/karaoke/karaokeFlow.js, frontend/scripts/bingo/karaoke_flow.check.mjs, karaoke_player.check.mjs.
## 6b. New evidence (2026-10-08 19:10, from the prototype PRD the owner found)
- Error 150/101 on a single song is a PER-VIDEO uploader restriction in the prototype's own history, fixed there by DROPPING videos with status.embeddable=false. My alpha.100 fallback (results = kept if kept else results) could put blocked videos back. Fixed locally in alpha.103 (backend only, 2 tests, proven able to fail). Whether the owner's failing song was blocked this way is still UNCONFIRMED.
## 6c. Correction (2026-10-08 19:20, from the CURRENT prototype backend the owner pasted)
- The prototype's _filter_embeddable ends with: never hand back an empty list purely due to filtering. My alpha.103 statement that the prototype drops blocked videos even when that empties the list was WRONG (I summarised a PRD note instead of reading the current file). The three attachments of 18:59 were older than the live prototype.
- The program's search used the YouTube Data API (needs a key, ~100 searches/day); the prototype uses yt-dlp. That is the real gap the owner had been pointing at.
## 12. Still unknown / open questions
- Does the song play in alpha.96, in the prototype, and on youtube.com? Is the refusal the video or the window origin?
## 13. Owner impact
- Another failed first-launch test on 2026-10-08.
## 14. Process change made because of this
- Owner-supplied files are diffed against the repo before anything is claimed; the test folder is rebuilt from the repo when the sandbox clears it.
