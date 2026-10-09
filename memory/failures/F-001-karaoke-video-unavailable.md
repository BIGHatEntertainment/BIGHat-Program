# F-001  Karaoke songs do not play on the TV ("This video is unavailable")
Status: FIXED-UNCONFIRMED (alpha.102 pushed 2026-10-08 19:10 MST; waiting for the owner's PC test)      Severity: blocked
## 1. When (MST, with times)
- First reported by owner: 2026-10-08 ~11:30 (alpha.97 test: "the songs did not load in the player ... no information such as next singer or song was showing"). Same day 12:34 after alpha.98: "still refuses to play videos on our screen. theres no pre-loading ... and theres no videos on the audience screen".
- Release it appeared in: alpha.98 (commit 5b03302, 2026-10-08 12:56). Songs played in alpha.70 through alpha.96.
- Fix attempts: alpha.99 (b1beca3, 14:25) FAILED; alpha.100 (5ecb65e, 14:56) FAILED; alpha.101 (3d45d2f, 15:40) PARTIAL (YT.Player back, but old extras left in, one song showed an owner-block message); alpha.102 (9d51418, 19:10) restore of first port.
- Confirmed fixed by owner at: NOT YET.
## 2. What the owner saw (exact words)
- "still refuses to play videos on on our screen. theres no pre-loading ... and theres no videos on the audience screen"
- "the only thing that doesnt work is playing an actual video in the player. again, earlier alphas has the videos working!"
- Screenshots: TV box showed YouTube's "This video is unavailable" with "Watch on YouTube"; alpha.101 showed a message that the video owner does not allow it to be played outside YouTube.
## 3. What the owner expected
- The TV plays the song exactly as the prototype does and as earlier alphas did, with the next singer preloaded.
## 4. What actually happened (observed)
- Host showed the song running (progress "0:28 of 3:08, on the TV"), so the TV window was alive and reporting. The video area in the TV and the host preview was black or "unavailable". Up-next bar was empty in two screenshots.
## 5. Evidence
- git: `git log -S"youtube.com/embed" -- frontend/src` shows the bare iframe exists only in 5b03302, b1beca3, 5ecb65e. Alpha.70 (c644638) first port already used `new YT.Player` (frontend/src/pages/karaoke/KaraokeAudienceView.jsx).
- Prototype (BIGHat-Beta-Testing/frontend/src/pages/karaoke/KaraokeAudienceView.jsx, 214 lines) uses a bare iframe, but runs in a browser at an https address. This app's TV is a Tauri window at http://127.0.0.1 (frontend/src/lib/audienceWindow.js, line 5).
- Chrome measurement (sandbox): a page at http://127.0.0.1 sends Referer by default; a page with no-referrer sends none; an iframe referrerpolicy overrides it. This did NOT reproduce YouTube's behavior (sandbox cannot reach YouTube).
- tauri.conf.json csp is null and nothing in the app sets frame-blocking headers: the app does not block the iframe.
## 6. Root cause
- SUSPECTED, strongly supported by history (not proven on the owner's PC): the bare iframe (alpha.98) sends YouTube no origin; the desktop window needs YouTube's own player script, which adds the origin. Proven only that every build that played used YT.Player and the only builds that failed this way used the bare iframe.
- Separate, real, secondary cause for single songs: videos whose owners disallow playing outside YouTube (YouTube error 101/150). The search filter videoEmbeddable=true is approximate; status.embeddable is more exact (backend now drops those).
## 7. Why it was not caught earlier
- The assistant replaced a working player on a theory and could not run YouTube in the sandbox. Tests only used a fake player, so they could not show a real failure.
- Test bundles for alpha.99 and 100 were built with the wrong script (see F-002), so their "pass" results described old code.
- No timestamped log and no "do not repeat" file existed (see F-003), so the bare iframe was tried three times.
## 8. Every fix attempt
- alpha.98: replaced YT.Player with bare iframe + stopwatch clock + removed buffering gate. FAILED (video unavailable).
- alpha.99: added referrer attributes and meta tag, assign-time embeddable check + endpoint, host warm-up iframe, host-sent waiting list, TV debug strip. FAILED (bare iframe kept).
- alpha.100: made the iframe address exactly the prototype's, muted host preview, search fallback. FAILED (video still unavailable).
- alpha.101: YT.Player restored, stopwatch and extras left in. PARTIAL: one song showed the owner-block message. Owner angry about conflicting code left in.
- alpha.102: TV page, host player, right panel, flow rules and tests restored from alpha.96 (last build that played); extras removed; preload replaced with the first port's 1px cued player. Backend search filter kept. UNCONFIRMED.
## 9. What NOT to do again
- Do not use a bare iframe for the song. Do not add playback "ideas" without an owner-reported error. Do not claim parity with the prototype without a sourced line-by-line comparison. See DO_NOT_REPEAT.md #1 to #4.
## 10. Test that proves the fix
- frontend/scripts/bingo/karaoke_aud.check.mjs ("a new song creates one YouTube player for the right video", and the nine alpha.102 preload checks). Proof it can fail: the preload was changed back to a full-size autoplaying player; 5 checks failed; restored. Earlier proof for the YT.Player check: replaced `new YT.Player` with a stub; the test crashed at "opts".
## 11. Files touched
- frontend/src/pages/karaoke/KaraokeAudienceView.jsx, KaraokePlayer.jsx, KaraokeRightPanel.jsx, karaokeFlow.js, iframePlayback.js (added then deleted), frontend/public/index.html; backend/routes/karaoke.py; the three karaoke check scripts.
## 12. Still unknown / open questions
- Does alpha.102 play a song on the owner's PC? Does a song from an allowed channel play when a blocked one does not? What exactly does YouTube return for the failing songs (error code on the TV)?
## 13. Owner impact
- About 8 hours of Karaoke testing on 2026-10-08, five releases (98 to 102), repeated frustration ("i am sick of you not getting this right").
## 14. Process change made because of this
- memory/DO_NOT_REPEAT.md, memory/TROUBLESHOOTING_LOG.md, this failure folder, scripts/release_check.sh and the pre-commit hook.
