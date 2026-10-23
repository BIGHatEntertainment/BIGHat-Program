# Task for the BIGHat-Cloud build agent: host images + user profiles/settings for linked Programs (cloud)

Read README.md, memory/RULES.md, memory/PRD.md, memory/SYNC_CONTRACT.md first. Work only on a new branch `feature/program-host-assets` in BIGHat-Cloud. Say which files you
touched and what you did NOT touch. Do not change the existing /api/files web routes, the existing /api/program/changes, /manifest or /files/{id} behaviour, or any
existing test. Everything below is ADDITIVE.

Why: the Program (standalone desktop app) now pulls venues, people, schedule, .bighat files and venue overlays/pictures from the Cloud. Two things it cannot pull yet
because the Cloud does not store them: (A) the HOST IMAGES and (B) each user's PROFILE and SETTINGS. The owner will set up individual profiles under one owner later;
the Program must be ready the moment they exist. The Program side is built by the Program assistant (NOT you); you only provide what is below, so keep the shapes EXACT.

## A. Host images

A host (a person in this account with the `host` role, or any employee the owner chooses) has up to THREE pictures. They are the SAME three the Program already
stores under `Files/Hosts/<host>/`:
- `avatar`     profile picture (png, jpg, gif, webp)
- `host-16x9`  the host slide for the trivia presentation, landscape (png, jpg, gif, webp; animated gif is normal)
- `host-9x16`  the host slide for the social story video, portrait (same types)

1. Storage: reuse Object Storage + `stored_files` exactly as routes/file_routes.py does (soft delete only, 100 MB cap, sha256 stamped). New area `hosts`, a new category per
   kind: `host_avatar`, `host_16x9`, `host_9x16`. Each file belongs to a PERSON: store the person's `item_id` (the same id the person has in /api/program/changes kind `person`).
   One file per person per category: uploading again REPLACES the previous (keep the old as soft-deleted).
2. Web routes (session cookie, same auth as /api/files; owner or an admin of the account only, or the person themself for their OWN pictures):
   - `POST /api/hosts/{person_id}/images/{kind}`  multipart `file`, kind = avatar | 16x9 | 9x16. 400 on a type outside png/jpg/gif/webp. 413 over 50 MB.
   - `GET  /api/hosts/{person_id}/images`          list `{kind, file_id, name, size, sha256, updated_at}`.
   - `GET  /api/hosts/{person_id}/images/{kind}/raw`  the bytes (for the web UI).
   - `DELETE /api/hosts/{person_id}/images/{kind}`  soft delete.
   Never accept a person_id from another account (404, same body as not found).
3. Program lane. ADD to the existing `GET /api/program/manifest` list, WITHOUT changing any existing entry or field: for every person visible to that program (the SAME
   visibility rule /api/program/changes uses for `person` items), one entry per picture:
   `{file_id, area:"hosts", category:"host_avatar"|"host_16x9"|"host_9x16", person_id, venue_id:null, name, size, sha256, updated_at}`.
   `GET /api/program/files/{file_id}` must serve them (same checks: Bearer key, account scope, subscription lapse -> 402, X-Content-Sha256 header).
   A program must NEVER receive another account's host pictures, and never a person its venue assignment does not allow.

## B. User profile and settings (the person's own, not the organization's)

Add to the user/person record, with a PATCH for the person themself and for an admin:
- `display_name`, `first_name`, `last_name`, `phone`, `home_city`            (strings; the Program already uses exactly these names in Files/Hosts/<slug>/host.json)
- `settings`: a small JSON object the person controls, stored as given, max 8 KB, only these keys accepted for now (reject unknown keys with 422 so it cannot become a
  dumping ground): `theme` (string, max 32), `default_aspect` ("landscape"|"portrait"), `default_venue_id` (a venue item_id the person can see), `notify_schedule` (bool),
  `language` (string, max 8).
- `PATCH /api/me/profile` (the person) and `PATCH /api/users/{id}/profile` (an admin of the same account). Audit-log row per change (action `profile_update`).
- Program lane: include these fields in the `person` item `data` of `/api/program/changes` (additive keys; the Program ignores keys it does not know). Bump the person's
  change_log seq when ANY of them changes, so the Program sees it. Never include password hashes, tokens or the 2FA secret (the existing allow-list rule).
- Program -> Cloud (later, the Program assistant will ask): `POST /api/program/actions` type `profile_update` for a person who is currently signed in on that PC. DO NOT build
  it now; just keep the shapes above stable.

## Rules to keep
1. account_id comes from the session or the program key only, never from a request body or query.
2. Nothing here changes who can log in. admin@bighat.live (platform master_admin) belongs to no organization and must never appear in a program list.
3. Subscription lapsed: web routes read-only as today; program lane answers 402 `subscription_lapsed` as today.
4. Rate limits as the existing program routes.

## Tests (required, real MongoDB as the existing tests do)
- upload each kind; second upload replaces and the old is soft-deleted; wrong type 400; over-size 413.
- another account cannot list, fetch or delete these pictures (404, identical body to not found).
- manifest contains the three categories for a visible person with correct sha256; a person outside the program's venue assignment is NOT listed; every EXISTING manifest
  entry is byte-for-byte unchanged (add a regression test that compares before/after).
- /api/program/files/{id} serves a host picture with X-Content-Sha256; wrong account 404; lapsed 402.
- settings: unknown key 422; too big 422; bad `default_aspect` 422; a person can edit their own but not another person's; an admin can edit anyone in the account only.
- profile change bumps seq, and /api/program/changes returns the new data once.
- no secret field (password_hash, totp, tokens) in any response.
Then update README.md, memory/PRD.md and CHANGELOG with TESTED and NOT VERIFIED lines, and report the branch name.

## Not in this task
- Pushing profile edits from the Program to the Cloud. - The organization login (already built, PR #31). - Web UI polish beyond a simple upload control on the person's page.
