# F-002  Karaoke tests ran against stale code (wrong build script)
Status: CONFIRMED-FIXED (process; found and corrected by the assistant 2026-10-08 ~16:00 MST)      Severity: worked-around
## 1. When (MST, with times)
- Appeared: 2026-10-08 ~13:40 to 14:56 (alpha.99 and alpha.100 testing). Found: ~16:00 when a new test crashed on a missing player.
## 2. What the owner saw
- Nothing directly. The owner was told "tests pass" for alpha.99 and alpha.100; the video still failed on their PC.
## 3. What the owner expected
- That a passing test run means the new code was tested.
## 4. What actually happened
- The assistant ran `build_aud.mjs`, which prints "audience bundled", but that bundles the BINGO audience page. The Karaoke audience test imports /tmp/rtest/kaud.bundle.mjs, which was last built at 20:54 UTC and never rebuilt.
## 5. Evidence
- /tmp/rtest listing showed kaud.bundle.mjs dated before the edits; `grep -l kaud.bundle` found the real builder `frontend/scripts/bingo/karaoke_all.build.mjs`. After running it, tests that had "passed" showed real failures (e.g. "the host is told which song and why").
## 6. Root cause
- PROVEN: wrong script name used; the success message ("audience bundled") looks identical for any page.
## 7. Why it was not caught earlier
- No document said which script builds which bundle. A passing result was accepted without proving the test could fail.
## 8. Every fix attempt
- Copied karaoke_all.build.mjs to /tmp/rtest/build_karaoke_all.mjs and used it for every run after ~16:00.
## 9. What NOT to do again
- Never trust "checks ok" without first proving the test can fail. Never reuse a build script name from memory. See DO_NOT_REPEAT.md #5.
## 10. Test that proves the fix
- Procedure, not code: break the feature on purpose, see a red test, restore. Done for the preload, the YT.Player creation and the host preview checks.
## 11. Files touched
- None in the product. Docs: DO_NOT_REPEAT.md, FILE_MAP.md.
## 12. Still unknown / open questions
- The alpha.99 and alpha.100 results were never re-run on their own code (they were superseded by alpha.102).
## 13. Owner impact
- Two releases were announced as "tested" when they were not.
## 14. Process change made because of this
- Build and test procedure written into DO_NOT_REPEAT.md #5 and FILE_MAP.md.
