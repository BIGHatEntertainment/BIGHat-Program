# Cloud task 2 of 4: Import old venue/round history (spec v0.1, 2026-10-25, DRAFT for owner approval)
Read memory/SYNC_CONTRACT.md first. Reuses round_locks.py (PR #35). Can be built before task 1.

## Input (real sample from the owner; this is the Program's round_usage.json shape)
File may be `.txt` or `.json` (the owner's copy is a Notepad/WordPad .txt). Strip a BOM; accept either `{"records":[...]}` or a bare `[...]`. If it does not parse, say WHERE (line/column) and change nothing.
Each record: `{id, location, locationId, roundFile, roundFileName, roundType, roundNumber, usedDate, expiresDate, usedBy, presentationId, presentationName}`
e.g. location "Cornish Pasty Co. (Glendale)", roundFile "Files/Trivia/MC/mc-10-a.bighat", roundFileName "mc-10-a", usedDate "2026-10-07T00:23:18.711042+00:00", expiresDate "2027-04-05T...".
`locationId` is the OLD app's id and means nothing in the Cloud: match by NAME only.

## Flow (admin/account_owner only), preview first, nothing saved until Confirm
1. `POST /api/trivia/history/preview` (the file): returns row count, distinct venues found, how many match a Cloud venue (normalized name: lowercase, letters and digits only, the same rule the Program sync uses), the unmatched names with row counts, rows already past expiry, duplicates inside the file, and rows with a missing/unparseable date (skipped, listed).
2. Unmatched venues get a pick-list in the UI: map to a Cloud venue, or "skip this venue". The choice is saved in `trivia_history_venue_map {account_id, old_name_key, venue_id|null}` so the next upload remembers it.
3. `POST /api/trivia/history/confirm` writes:
   - EVERY valid row to `trivia_round_history` (venue_id, round_type, round_key, round_file_name, used_at, used_by, presentation_name, source:"import", import_id). Idempotent on sha1(venue_id|round_key|used_at).
   - Rows NOT yet expired also go through `round_locks.apply_lock(... source="import")` so they lock and reach every linked PC through the existing change feed. A round an admin RELEASED is NOT re-locked (apply_lock already answers rejected "released": count it as "kept released").
4. Result screen: written, already there, kept released, skipped (with reasons), per-venue counts. An audit_log row, and an `import_id` so the whole import can be undone: `DELETE /api/trivia/history/import/{import_id}` removes only what that import wrote (history rows, and the locks whose only source is that import).

## Rules
- Never write a lock for a venue that was not matched or mapped. Never touch locks from other sources. Idempotent: uploading the same file twice changes nothing. Cap 50,000 rows / 20 MB per file. One bad row never stops the rest. Account isolation.

## Acceptance
1. The sample above: 2 venues found; "Test Venue" shows as unmatched until mapped. 2. Upload twice: second run writes 0. 3. A row older than 180 days becomes history only, no lock. 4. An admin-released round is not re-locked. 5. After Confirm, a linked PC pulls the locks and its Wizard hides those rounds. 6. Undo removes exactly that import. 7. A host cannot import.
