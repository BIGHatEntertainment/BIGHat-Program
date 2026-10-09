# F-003  PRD, changelog and "what not to do" were not kept in the repo
Status: FIXED-UNCONFIRMED (docs backfilled in commit 384f31c on 2026-10-08 ~18:30 MST; check added in the next commit)      Severity: harmful (repeated mistakes)
## 1. When (MST, with times)
- Gap began: 2026-10-06 ~09:57 (alpha.81). Owner called it out: 2026-10-08 18:12 ("you have not been updating the change log or memory prd file properly").
## 2. What the owner saw (exact words)
- "also I noticed that you have not been updating the change log or memory prd file properly or else we wouldn't have been running into the same errors like this. these rules are in your settings."
- "so what your telling me is that you knowingly went against your instructions in your memory settings 22 test cases ago?"
## 3. What the owner expected
- 1) detailed logs of the entire system with time stamps for troubleshooting; 2) a file in the build repo that states what doesn't work and what not to do again.
## 4. What actually happened
- memory/CHANGELOG.md in the repo stopped at alpha.80 and memory/PRD.md had no status after alpha.19. Release notes lived only in the assistant's own memory notes, which the build repo does not contain.
## 5. Evidence
- `wc -l memory/CHANGELOG.md` = 4053 lines, last entry "alpha.80"; `grep alpha memory/PRD.md | tail -1` = alpha.19; FILE_MAP.md had 14 lines and no Karaoke section.
## 6. Root cause
- PROVEN: the rule "always update the PRD memory" was read as "update my memory notes". The repo copies were not touched.
## 7. Why it was not caught earlier
- Nothing checked the repo docs at release time.
## 8. Every fix attempt
- 384f31c: CHANGELOG backfilled alpha.81 to 102 with MST times verified against git; TROUBLESHOOTING_LOG.md; DO_NOT_REPEAT.md; PRD status; FILE_MAP Karaoke map. Then: scripts/release_check.sh, scripts/install_hooks.sh (pre-commit hook) and this failure folder.
## 9. What NOT to do again
- Do not treat my own memory notes as the repo docs. Do not release without running scripts/release_check.sh.
## 10. Test that proves the fix
- bash scripts/release_check.sh. Proof it can fail: it blocked alpha.102 (missing TESTED/NOT VERIFIED/FILES/TIME lines) and then the missing failure reports, before they were written.
## 11. Files touched
- memory/CHANGELOG.md, PRD.md, TROUBLESHOOTING_LOG.md, DO_NOT_REPEAT.md, failures/*, FILE_MAP.md, scripts/release_check.sh, scripts/install_hooks.sh.
## 12. Still unknown / open questions
- Alpha.81 to 96 entries are one line each, back-filled from commit messages. Details of earlier problems (alpha.90 failed build, alpha.91 first-launch regressions) are not written as failure reports yet.
## 13. Owner impact
- Repeated errors across several releases; the owner's trust.
## 14. Process change made because of this
- A release cannot be committed until its docs exist: CHANGELOG block with TIME (MST), TESTED, NOT VERIFIED, FILES; PRD mention; TROUBLESHOOTING_LOG line; failure report for any fix or regression.
