# CLOUD TASK: let a linked Program upload a round so the Cloud stamps it (BIGHat-Cloud)

Paste this to the Cloud build agent. Program side is done and waiting (BIGHat-Program PR 3, `backend/native/cloud_upload.py`).

## What is needed
ONE new route in `backend/routes/program_sync_routes.py` (router prefix is already `/api/program`):

    POST /api/program/files/upload        multipart form: file=<the .bighat>, category="bighat"
    Auth: `program_auth.require_program(request, db)` exactly like `GET /api/program/manifest` (the PC's access key, NOT a browser session).
    Success: HTTP 200 with the same JSON `POST /api/files/upload` returns (`{**_public(doc), "status": "added" | "replaced"}`).

## Do NOT write a second stamping path
`routes/file_routes.py` `upload_file` already does everything: size limit, `_round_fields(aid, name, data)` (reads the manifest, keeps an existing
round's `round_uid`, mints one if new, `stamp_zip`), replace-never-duplicate by (`round_type`, `round_key`), object storage, `stored_files` row, and the
`trivia_rounds_stamped` audit entry. Refactor that body into one shared function (for example `store_bighat_round(account_id, uploader_email, name, data, content_type)`)
and call it from BOTH `/api/files/upload` (browser) and the new Program route. The two must never be able to disagree about a round's identity.

## Rules (the owner has zero tolerance for silent data loss)
1. Only `category == "bighat"` and a name ending `.bighat`. Anything else: 400. A Program may not upload venue pictures or host images through this route.
2. `account_id` comes from the key (`prog["account_id"]`), never from the request.
3. The subscription / lapsed check that `require_program` already applies stays as is (a lapsed account gets the same 402 the manifest gives).
4. `uploaded_by` in the stored row: use something like `program:<link name or id>` (no email exists for a key). The audit entry must say it came from a Program.
5. If `_round_fields` returns an error ("round id belongs to another round"): HTTP 409 with `{"error": "refused", "message": ...}`. The Program reports it and keeps its file.
6. Replacing: the Program only sends a name the manifest did not list, so a replace should be rare; if it happens keep the existing round's `round_uid` (that is already what `_round_fields` does).
7. Rate limit it like the other `/api/program` routes. Max size = the existing `MAX_SIZE` (the Program stops at 50 MB itself).
8. Venue assignment: a Program with an assignment (`prog["venue_ids"]`) may still upload rounds (bighat files are account-wide, same as the manifest's rule).

## Tests to add (real database, no mocks of the stamping)
- Upload a plain round through the Program route: response has a `round_uid`; the stored file's manifest has it; `GET /api/program/manifest` now lists it; downloading it through `GET /api/program/files/{id}` returns the stamped bytes (sha matches `X-Content-Sha256`).
- Upload the same round again: `status == "replaced"`, same `round_uid`, ONE stored row.
- Upload through the browser route then the Program route with an edited copy of the same file name: same `round_uid`, one row (proves one shared path).
- A key from another account can never see or replace this account's round.
- Missing / wrong key: 401. Lapsed subscription: 402. Non-`.bighat` or other category: 400. Empty file: 400.
- The existing `/api/files/upload` tests must still pass unchanged.

## Report back
List the route, the shared function name, and the test results. Nothing else in the Cloud should change.
