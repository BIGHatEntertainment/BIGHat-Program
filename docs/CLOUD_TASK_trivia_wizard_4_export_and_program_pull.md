# Cloud task 4 of 4: .bighat show export + Program pull (spec v0.1, 2026-10-25, DRAFT for owner approval)
Needs task 3. The Program side is built separately by the Program agent (docs/PROGRAM_TASK_cloud_show_import.md); this task defines the file and the endpoints it uses. Do not change the Program.

## The file: a ZIP named `<plan name>.bighat`, manifest type `trivia-show-bundle`
```
manifest.json   {format:"bighat", version:1, type:"trivia-show-bundle", app_version, plan_id, name, created_at, created_by, round_count}
payload.json    {host:{name,email,employee_id}, location:{name, cloud_venue_id}, round_count,
                 rounds:[{order,type,name,round_key,file:"rounds/<TYPE>/<file>.bighat"}]}
rounds/<TYPE>/<file>.bighat   the stored library files, byte for byte (each is itself a ZIP)
signature.txt   OPTIONAL: HMAC like the Program's existing signing scheme, only if the account has a signing key
```
The Program's existing `.bighat` rules apply (backend/routes/bighat_files.py): manifest + payload + assets, `pack`/`presentation` precedent. Do NOT invent a second container.

## Endpoints
- `GET /api/trivia/plans/{id}/bighat` (web session): builds and streams the file; re-validates the plan first (a missing round answers 409 with the list). Cap ~60 MB.
- Program key auth, scoped by account_id, only plans for venues assigned to that PC (same as the change feed):
  - `GET /api/program/trivia-plans?since=` -> `[{id, name, venue_id, venue_name, host_name, round_count, updated_at, size}]` (no bytes)
  - `GET /api/program/trivia-plans/{id}/bighat` -> the same file
  - Subscription lapsed -> 402 as every other program route. Rate-limit like the others.
- `POST /api/program/trivia-plans/{id}/imported` (Program reports it imported the show, `{program_id, imported_at}`); the plan shows "Imported on <PC>" in the UI. Informational only; failure is harmless.

## Rules
Never put credentials, other accounts' data or file paths of the Cloud server in the file. Round files are copied exactly: no re-encoding. Log counts, never content.

## Acceptance
1. Download from the web, open the ZIP: manifest, payload, N round files. 2. The Program endpoints list only this account's plans for this PC's venues and download the identical file. 3. A plan with a deleted library round returns 409 with the reason. 4. A PC with a lapsed subscription gets 402. 5. Another account's plan id returns 404.
