# Cloud task: permanent round ID (round_uid) stamped inside every trivia round file (spec v0.1, 2026-10-30, owner-approved design)
Read memory/SYNC_CONTRACT.md and docs/PLAN_round_id_stamp.md first. Additive only. The Program side is built (BIGHat-Program PR "round-uid").

## Owner decisions (2026-10-30)
1. The CLOUD stamps the ID. 2. Old files on PCs with no ID are NOT touched by anyone: the owner deletes them and downloads the stamped copy from the Cloud.
3. An edited / re-exported round KEEPS its ID, and keeps its round lock. One round = one ID, uploaded once, tracked from then on.

## The field
`manifest.json -> round_uid`: a lowercase UUID4 string, inside the round file's ZIP. It is NOT `content_id` (the File Creator makes a new content_id on every
export; it identifies an export). round_uid identifies the ROUND and never changes once stamped. Validate with ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ (anything else = not stamped; never trust or store junk).

## 1. Library upload stamps it (routes/trivia_library_routes.py, collection trivia_rounds)
For each uploaded round ZIP:
- If the file ALREADY has a valid round_uid: keep it. If another round in this account already has that uid with a different (type, round_key), reject that file with reason "round id belongs to another round" (never overwrite).
- If it has none: look for an existing library round in this account that is the same round: same round_type AND same round_key (round_locks.round_key). If found, INHERIT that round's uid (this is how an edited, re-exported round keeps its ID and its lock) and REPLACE the stored file. If not found, mint a new uuid4.
- Write the uid into manifest.json INSIDE the ZIP: rewrite the ZIP copying every other member byte for byte (same names, same order, same compression), changing only manifest.json (add "round_uid"). Never re-encode payload or assets. Keep `content_id` as it was.
- Store `round_uid` on the trivia_rounds document; unique index on (account_id, round_uid). The upload result per file says: added | replaced (kept its ID) | rejected(reason), plus the round_uid.
- Plain-JSON (non-ZIP) rounds are rejected as today; the library only holds stamped File Creator rounds.
- A bundle export (task 4) and the single-file download send the STAMPED file, so every PC gets files that carry the ID.

## 2. Locks carry the ID (round_locks.py, collection round_locks, routes/program_sync_routes.py)
- `lock` and `release` actions accept an optional `round_uid` (validate as above; ignore if invalid). Store it on the lock document and include it in change-feed items (`data.round_uid`). The item_id is NOT changed: it stays sha1(venue|round_key|presentation) (or the 40-hex id the Program sends), so an existing lock never duplicates.
- A release by round_uid frees every lock of that uid at that venue, whatever file name each was recorded under; a stale lock copy (used_at not after released_at) cannot re-lock it (same rule as names).
- The wizard/library `locked` flag and the plan validation: a round is locked at a venue when an ACTIVE lock there has the same round_uid OR the same round_key (names keep locking: old locks without an ID must never stop working).
- Back-fill: when a lock arrives without a uid, find the library round with the same (type-agnostic) round_key at this account; if exactly one match, store its uid on the lock. If zero or several, leave it without (never guess).

## 3. History import (wizard plan task 2)
Each imported row is mapped to a library round by round_key (and round_type); a match stamps the row's lock with that round's uid. No match = name-only lock, listed in the result.

## 4. The "files with no ID" list for the Cloud site
A page/list "Library rounds" shows each round's ID (short form) and which have none (should be none: the Cloud stamps on upload).

## Rules
Account isolation. Idempotent: uploading the same file twice changes nothing (second time: replaced, same uid). A bad file never stops the others. No file content is logged. Audit-log the stamping count per upload.

## Acceptance
1. Upload an unstamped round: stored file's manifest has round_uid; every other member is byte-identical to the upload; content_id unchanged.
2. Upload it again: same uid, status replaced. Upload an edited version (new content_id, same name+type): SAME uid.
3. Upload a stamped file whose uid belongs to a different round: rejected with a reason, nothing overwritten.
4. A lock sent with round_uid is stored and returned in the change feed; a release by uid frees a lock recorded under another file name; a stale lock copy does not re-lock it.
5. A lock with no uid still locks by name (old locks keep working) and is back-filled when exactly one library round matches.
6. The library `locked` flag is true for a renamed copy (same uid) and for a name match.
7. A bundle's round files carry round_uid. Another account never sees or matches this account's uids.
