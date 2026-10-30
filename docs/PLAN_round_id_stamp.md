# Plan: a permanent round ID stamped INSIDE every trivia round file (investigation 2026-10-30, DRAFT for owner approval)

## What exists today (verified)
- Every File Creator round file (ZIP) has `manifest.json -> content_id` (a UUID). 5 of 5 fixtures have one, all different.
- BUT the File Creator mints a NEW random content_id on every export (CHANGELOG round-lock-same-round-v1, 2026-10-22). Re-exporting the same
  PowerPoint gives the same round a different id. So today's id identifies one EXPORT, not one ROUND. It cannot be the lock key as it is.
- Locks do NOT use it. Program (round_usage.same_round_keys) and Cloud (round_locks.round_key) both key on the FILE NAME (lowercase stem,
  `TYPE__` prefix and `-<8hex>` stamp removed). Sync item_id = sha1(venue id | round key | presentation id).
- Older plain-JSON round files (the Round Generator) have no manifest and no id at all (2 of 7 sample files).
- Program already treats a creator content_id as the round's identity on import (routes/bighat_files.py, alpha.74).

## What the name-only key gets wrong (reproduced with the real functions)
1. A renamed copy of the same round does NOT lock: `mc-01-a` vs `mc-01-a-renamed` -> not locked, so a used round can be re-run inside 180 days.
2. Two different rounds that share a name collide: the bare-name key `history` matches a REG and a MYS round, so one lock can block an unrelated round.
3. The Cloud library "replace on re-upload" and its `locked` flag also key on the file name.

## Proposed design
**Field:** `manifest.round_uid` (a UUID4, lowercase) inside every round file. NOT the name, NOT `content_id` (that one keeps meaning "this export").
**Minted once, never changed:** by the Cloud library at upload when the file has none; kept untouched when it already has one. A round that is re-exported
by the File Creator arrives without a round_uid and is matched to its existing library round (below) so it inherits the SAME uid.
**Lock identity (new):** `round_uid` first; file-name key stays as the fallback for files with no uid (old files, the 180 days of existing locks).
Both sides log the uid: usage record gets `roundUid`; Cloud lock item gets `round_uid`; item_id = sha1(venue | round_uid-or-round-key | presentation).
**Never lose a lock:** records without a uid keep working by name. A lock is added by name AND uid when both are known; a release frees both.

## Cloud side (tasks to write once the owner picks the options below)
1. Library upload stamps `round_uid` (rewrite manifest.json inside the ZIP, keep every other byte of every other member), stores it on `trivia_rounds`.
   Re-upload matches an existing round by round_uid, else by (type, round_key); on a match it KEEPS the uid.
2. `round_locks`: accept and store `round_uid` on lock/release actions and change-feed items; the `locked` flag on the library and the wizard check uid OR name.
3. History import (task 2 of the wizard plan): rows have only file names, so each row is mapped to a library round by name and given that round's uid when found.
4. Bundle export: round files are copied byte for byte, so they already carry the uid.
## Program side (mine)
1. Read `round_uid` from a round's manifest when the Wizard/Roulette/Cloud import writes the usage record; store `roundUid` on the record.
2. `is_locked` / release / cloud_locks: match by uid when both have one, else by name (today's rule). Send/receive `round_uid`.
3. Cloud show import: files are unpacked unchanged, so the uid arrives with them. Plain-JSON old rounds: name only (they have no manifest).
4. Never rewrite the owner's files on the PC. A PC only READS the uid.

## Questions for the owner (they change the build)
A. Who stamps? (1) the Cloud library stamps at upload (recommended: one place, nothing to change in the File Creator tool), or (2) also change the File Creator tool so new exports carry a stable uid per round.
B. Old round files already on PCs (no uid): (1) leave them on name matching until they are re-uploaded through the Cloud, or (2) the Program adds a uid next time it reads them (touches the owner's files; I advise against).
C. When a round is edited and re-exported, is it the SAME round for locks? Recommended yes: it inherits the uid of the library round with the same type + name.
