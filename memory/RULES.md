# RULES for build agents (BIG Hat Entertainment)

Read this, README.md, memory/PRD.md and memory/SYNC_CONTRACT.md before every task. Same file in BIGHat-Program and BIGHat-Cloud.

## Scope
1. Work only in the repo the task names. (program) = BIGHat-Program, (cloud) = BIGHat-Cloud.
2. Touch only the files the task lists. If another file must change, stop and ask first.
3. Never refactor, restructure or rename unless the task says so.
4. Work only on the branch the task names. Never push to main.
5. Before touching anything, say which files you will touch.

## Stop, do not work around
6. If something cannot be done, stop and report why. Never use a workaround silently.
7. If an action would affect more than the files named, stop and ask.
8. Never claim something works unless you ran it. Say TESTED and NOT VERIFIED separately.

## Data safety (the owner has zero tolerance for silent data loss)
9. Disk is the source of truth. Anything that must survive an update goes in AppData (Program) or the database (Cloud), never in the browser.
10. Writes are atomic. A damaged file is kept aside (.bad), never replaced by an empty one.
11. Never delete user data without a preview and a backup.
12. Every Cloud query is scoped by account_id.

## Security
13. Never put a secret in code, a log, a response or a commit. Secrets come from the environment.
14. Never return a full license key or access key. Mask all but the last 4 characters.
15. Do not change the response shapes of /api/program/announce and /api/program/claim-token (status, token, program_id). Installed programs depend on them.

## Delivery
16. Do not deploy until the tests pass.
17. After the work, update README.md and memory/PRD.md and add a CHANGELOG entry with TESTED and NOT VERIFIED lines.
18. Save to a new branch and report the branch name. If saving to GitHub fails, paste the full contents of every file changed.
19. Log what was done and what was skipped, and why, in your final report.
