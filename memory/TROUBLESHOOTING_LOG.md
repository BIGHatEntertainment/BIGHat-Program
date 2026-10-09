# TROUBLESHOOTING LOG (append only; newest at the BOTTOM of each problem)
Format per line:  [MST date time] ALPHA | WHAT HAPPENED / WHAT WE TRIED | RESULT
MST = UTC minus 6. Source for commit times: `git log --format='%h %ad' --date=format:'%Y-%m-%d %H:%M'` (UTC).
Every fix attempt gets a line here BEFORE it is pushed, and the owner's test result gets a line AFTER. See also DO_NOT_REPEAT.md.

======================================================================
PROBLEM K-1: Karaoke song will not play on the TV (audience window)
Owner's PC: Windows, installed alpha build, TV window = Tauri window at http://127.0.0.1:<port>
======================================================================
[2026-10-06 17:14] alpha.89 | karaoke player first built: YT.Player on TV + second full-size "buffer holder" player + progress bar | released
[2026-10-07 16:31] alpha.94 | first singer did not load after the fullscreen gate; added automatic retry + host Retry | owner later reports playing worked
[2026-10-08 10:49] alpha.96 | explain YouTube error codes in plain words; host stays on Karaoke tab | LAST BUILD WHERE VIDEO PLAYED (owner: "earlier alphas had the videos working")
[2026-10-08 ~11:30] alpha.97 test | owner: "songs did not load in the player ... no next singer or song showing" | cause not found; assistant guessed
[2026-10-08 12:56] alpha.98 | assistant replaced YT.Player with a bare iframe "like the prototype", removed buffering gate, added a stopwatch clock | FAILED: TV shows "This video is unavailable" (YouTube error 153 family); owner: "step backwards", no pre-loading, no video on TV
[2026-10-08 ~12:40] research | Error 153 = YouTube gets no valid referrer/origin from the embed | explains #98 failure
[2026-10-08 14:25] alpha.99 | added referrerpolicy on iframes + page meta referrer, embeddable check on assign, host warm-up iframe, host-sent waiting list, TV debug strip | owner pushed; NOT proven; the bare iframe stayed
[2026-10-08 13:56-14:56] alpha.100 | TV iframe address trimmed to the prototype's exact string; host preview = muted video; search fallback | owner test: video still "unavailable"
   (tests for #99/#100 ran against a STALE karaoke bundle because build_aud.mjs is the BINGO page. Their "pass" meant nothing. See DO_NOT_REPEAT #5.)
[2026-10-08 ~14:20] diagnosis | git history: every alpha that played video used YT.Player (alpha.70 first port through 96). Bare iframe only existed in 98-100. Root cause = bare iframe sends no origin | CONFIRMED by history, not by running on the owner's PC
[2026-10-08 15:40] alpha.101 | YT.Player restored for the song, but the alpha.98 stopwatch clock and other extras still ran | owner screenshot: one song says owner does not allow outside play (a VIDEO block, error 101/150); owner angry that conflicting code was left in
[2026-10-08 ~17:15] alpha.102 build | restored alpha.96 TV page, host player, right panel, flow rules and tests; removed bare iframe, stopwatch, debug strip, referrer extras, assign-time check endpoint; replaced the alpha.89 full-size buffer with the FIRST PORT's 1px cued preload | all karaoke checks pass on fresh bundles; new preload checks proven able to fail
[2026-10-08 19:10] alpha.102 | PUSHED (owner said push at 18:10), commit 9d51418, tag v32.0.0-alpha.102 | WAITING FOR OWNER'S PC TEST (build status on GitHub not checked by assistant)

OPEN QUESTIONS (check next time):
 - Does alpha.102 play a song from an allowed channel (e.g. PARTY TYME KARAOKE CHANNEL)? If one song fails and others play, it is a blocked VIDEO, not the player.
 - If ALL songs fail on alpha.102: ask for a screenshot of the TV text (the page names the YouTube error code) before changing anything.
[2026-10-08 18:12] process | owner: PRD/changelog not kept in repo, no "do not repeat" file | admitted; docs backfilled in 384f31c (see failures/F-003)
[2026-10-08 18:40] process | added scripts/release_check.sh + pre-commit hook + memory/failures/ (14-section report per failure) | hook proven to block a version bump with no docs (8 reasons listed)
