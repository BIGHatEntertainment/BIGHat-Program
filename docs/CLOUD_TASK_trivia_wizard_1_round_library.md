# Cloud task 1 of 4: Trivia round library (spec v0.1, 2026-10-25, DRAFT for owner approval)
Read memory/SYNC_CONTRACT.md and memory/RULES.md first. Additive only: do NOT touch routes/rounds.py (the SharePoint code) or anything outside Trivia.

## Why
The Cloud wizard (task 3) can only offer rounds the Cloud holds. Today the Cloud has no round files of its own.

## Data: collection `trivia_rounds` (per account_id, indexed)
`{id, account_id, round_type: MC|REG|MISC|MYS|BIG, name, file_name, round_key, size, content_id?, cover_thumb?, uploaded_by, uploaded_at, file_ref}`
- The file itself goes in GridFS (it is a ZIP of ~0.4 MB, up to ~5 MB). `file_ref` = GridFS id. Never store file bytes inside the document.
- `round_key` = the SAME function as round_locks.round_key (lowercase stem, TYPE__ prefix and -<8 hex> stamp removed). Unique on (account_id, round_type, round_key): uploading the same round again REPLACES it, never duplicates.

## Endpoints (Cloud web session; admin/account_owner to write, any host to read)
- `POST /api/trivia/library/upload` multipart, MANY files per request (cap 100 files, 25 MB each, 300 MB total). Must be a valid ZIP with manifest.json; round_type from manifest.round_type, else from the `TYPE__` file prefix, else the folder name sent with it, else REJECT that file with a reason (never guess). Result per file: added | replaced | rejected(reason).
- `GET /api/trivia/library?type=&q=&venue=` list (no bytes). With `venue=<cloud venue id>` each row carries `locked: bool` and `locked_until` using the existing round_locks collection and the SAME venue rule. Page it (limit 200).
- `GET /api/trivia/library/{id}/file` download the stored file. `DELETE /api/trivia/library/{id}` (admin, audit_log row).

## Tab
Trivia page gets a "Round library" panel: type tabs with counts, search, a multi-file drop zone, a results list after upload (added/replaced/rejected with reasons). Nothing is deleted without a confirm.

## Rules
Account A never sees Account B's rounds. Uploads are idempotent. A bad file never stops the others in the same batch. No file content is logged.

## Acceptance
1. 40 files in one drop: all listed with the right type; re-drop: all "replaced", count unchanged. 2. A non-ZIP and a ZIP with no type are rejected with a reason, the rest still land. 3. `?venue=` marks a round locked at that venue and not at another. 4. A host can list and download but not upload or delete. 5. Account isolation.

## Open question for the owner (answer before building)
Where do the round FILES come from? Suggested: the owner drops the contents of a PC's Files/Trivia/{MC,REG,MISC,MYS,BIG} folders into the upload zone once. (The old usage history is a different thing; see task 2.)
