# Program <-> Cloud sync contract v0.1 (Phase 0)

STATUS: CONTRACT ONLY, no code yet. Same file in BIGHat-Program and BIGHat-Cloud (memory/SYNC_CONTRACT.md). Keep identical.
Read memory/SYNC_PLAN.md first. Owner decisions of 2026-10-21 are at the bottom.

## Auth (every call)
- Header: `Authorization: Bearer <program access key>`. The Cloud hashes it, finds the active program row, takes account_id from it. Every query is scoped by account_id.
- Errors: `{error, message}`. Codes: unauthorized, unlinked, subscription_lapsed, rate_limited, conflict, too_large, bad_request.
- subscription_lapsed: Program keeps working from its local copy; sync and backup pause. unlinked: card returns to "Not linked".

## Data lane
- `GET /api/program/changes?since=N&limit=500` -> `{seq, has_more, items:[{item_id, kind, revision, deleted, updated_at, updated_by, data}]}`.
- kinds: venue, person, venue_pricing, venue_role, event. seq = per-account counter, +1 on every change. Program stores last seq.
- A PC receives only the venues the owner assigned to it (Cloud Settings).
- `POST /api/program/actions` batch of `{action_id, type: claim|unclaim|result, event_id, at, payload}`. Each returns applied | duplicate | rejected(reason, e.g. already_claimed + who). action_id is the idempotency key.
- Program schedule is READ-ONLY except claims, unclaims and results, and only when the PC is linked.

## File lane
- `GET /api/program/manifest?since=N` -> `[{item_id, kind, name, revision, sha256, size, updated_at, updated_by, source}]`.
- `GET /api/program/files/{item_id}` downloads the .bighat (sha256 in ETag).
- `PUT /api/program/files/{item_id}` uploads; sends `If-Match: <sha256 last seen>`. If the Cloud copy changed: 409 conflict with both stamps; Program keeps both and asks the user.
- Limit 50 MB per file for now (bingo videos are 25 to 35 MB). Chunked upload later.
- Never backed up: karaoke videos (yt-dlp). Only venue images are needed by karaoke.

## First link
- `GET /api/program/snapshot` returns the full setup as a .bighat of type `setup`.
- Program previews it against local data with its existing plan_apply, applies only what the host chose, saves a backup first. Nothing is deleted.
- Offline route: Cloud Settings has a "Download setup file" button; Program can open that file instead.

## .bighat additions (version 3, additive)
- item_id (permanent), revision (+1 per save), sha256 (payload and assets), updated_at, updated_by, source (`program:<pc code>` or `cloud`).
- v2 files must still open (older readers should ignore unknown keys; NOT tested yet). New type `setup`; lib.rs route_for_bighat gets one case for it.

## Identity and storage
- Venues match by normalized name; people by lowercase email (existing rules). The Cloud assigns item_id.
- Program keeps AppData/secure/cloud_sync.json: last_seq, file stamps, id map, outbox. Atomic writes; damaged file kept as .bad.
- Never synced: passwords or hashes, access keys, license keys, master admin credentials, karaoke videos.
- Rhythm: pull every 5 minutes and at login, backoff on errors.

## Owner decisions (2026-10-21)
1. LINKING: one flow, two entry points, whichever the person uses first. The link is always confirmed by a person on both sides; never silent.
   - Program first: after the master admin logs in online and the PC is not linked, the Program offers "Link to BIG Hat Cloud". It shows this PC's code and opens the Cloud in the browser with the code pre-filled; the owner signs in THERE. The Program never sees a Cloud password.
   - Cloud first: the first-run setup (it already has an online check) announces the PC and shows the code; the owner types it in Cloud Settings, as today.
   - Only an owner whose Cloud account holds the matching license key can link a PC. Hosts do not link PCs.
   - People who arrive from the Cloud get a Program login with a temporary password (changed at first login). Passwords never sync.
2. SCHEDULE: read-only in the Program except claims/unclaims/results, and only when the PC is linked. Program-only users are never locked out of anything.
3. LAPSED SUBSCRIPTION: sync and backup pause; Program keeps working locally. No blocking.

## Not yet pinned (Phase 1 must settle)
- Exact fields inside `data` for each kind (mirror the Cloud models).
- Whether the Cloud license-key setter (Settings) is deployed. Linking depends on it.
- Whether older .bighat readers ignore unknown manifest keys.

## Organization login (added 2026-10-21, v0.2)
Goal: anyone in a Cloud organization can sign in on ANY Program linked to that organization. Checked against the Cloud EVERY time; no offline Cloud login.
- Endpoint (Cloud, NEW): `POST /api/program/auth/login`, header `Authorization: Bearer <program access key>`, body `{email, password}`.
  - The Cloud takes account_id from the key (never from the body), finds the user by lowercase email WITH THAT account_id, checks is_active and the password with the same hash and the same rate limits as /api/auth/login (per email + per client ip, plus the program-key throttle). Same work for unknown email and wrong password (no account enumeration).
  - 200: `{ok: true, user: {email, name, role, is_admin, phone}}`. role is the Cloud role: `account_owner` or `host` (the only roles a hosting company has). NOTHING else: no id, no hash, no account_id, no license key.
  - 401 `{error: "invalid_credentials"}` for wrong email/password/not in this organization (one message for all three). 403 `{error: "deactivated"}`. 429 `rate_limited`. 401 `unlinked`, 402 `subscription_lapsed` as in require_program.
  - Platform admin: the Cloud's `master_admin` is BIG Hat's own platform account (admin@bighat.live, the only account with two-factor). It belongs to no organization, so the account-scoped lookup can never match it; it can NEVER sign in through this route. No two-factor step exists here. Only `account_owner` and `host` can use it.
  - Never sets a cookie, never returns a Cloud token. A new audit_log row per success: action `program_login`, actor_email, program_id.
- Program (NEW): the existing /api/auth/login tries the LOCAL login first (unchanged). Only when there is no local match and the PC is linked does it call the Cloud. A local user with a wrong password is NEVER sent to the Cloud (no bypass, no extra guessing surface).
- After a Cloud success the person is signed in with a session for this PC only. Cloud role -> local role: `account_owner` -> `admin` (never the local master admin, which is whoever set the PC up); `host` -> `host`.
- Then the Program asks "Copy my account to this computer?" Yes: a local user is created (hashed password, role as above, auth_method "cloud"); that person then logs in locally AND still gets re-checked against the Cloud while linked. Later: signed in for this visit only; asked again next time. A person created by the Cloud pull (temporary password) that signs in with a Cloud password gets the local password updated to match.
- Cloud checks every time: a cloud-origin local user who signs in while the PC is linked is verified with the Cloud first; the Cloud saying invalid_credentials/deactivated refuses the login even if the local copy would accept it. Cloud unreachable: a local-only user logs in as always; a copied Cloud user is refused with "can't reach the Cloud" (owner decision 2026-10-21: no offline Cloud login). The local master admin is never affected by any of this.
- A PC's venue assignment still limits what that person sees and claims there.

## Organization login: design discussion and decision (2026-10-23, for revisiting later)
The owner asked how to handle people who have a Cloud account AND a program account with DIFFERENT passwords, and proposed three rules:
1. On a person's next Cloud login, check for program logins; if none, save their credentials in a table the programs recall so both match; if some, ask which to keep.
2. Keep each person's credentials securely on the Cloud (a later Cloud task).
3. If the Cloud password changes, an Update button in Admin overwrites the saved local credentials.

DECISION (owner, 2026-10-23): keep the design already built: the Cloud is asked EVERY time (no offline Cloud login, chosen 2026-10-22); the Cloud answers
only yes/no + {email, name, role, is_admin, phone} and NEVER sends a password or a hash to a PC. So rules 1-3 are NOT built. They are kept here in case they are revisited.

Why they were set aside (the trade-off, in case it is reopened):
- A saved copy on the PC is a stale copy: a fired host would keep signing in on that PC until the next sync, an old password would keep working after a Cloud change
  (that is what rule 3's Update button would patch), and a stolen PC would carry a password hash. Every-time checking has none of these, at the cost of needing the
  internet to sign in with a Cloud account. A local program account, and the local master admin, still sign in offline.
- If it is ever revisited, the safer shape is: check once online, keep a short-lived "may sign in" stamp (e.g. 14 days) instead of the credentials, and a
  "refresh my login now" button in Admin. The Cloud would need a "password last changed" stamp on the person. Both people must prove both passwords before any merge.

How the "different passwords" case works today (built in v32.4.0):
- A person with a HAND-MADE program account keeps that account and password. Their Cloud password is NOT tried for it (a wrong program password is never sent to the Cloud:
  no extra guessing surface). They sign in with their program password.
- A person the Cloud pull created here (temporary password) signs in with their Cloud password; the local password then follows it ("same credentials in both").
- A person with no account here signs in with their Cloud password and is asked "Copy my account to this computer?". If yes, a local account is created
  (auth_method "cloud") and from then on the Cloud is asked every time for it.
- BUG FOUND AND FIXED while building this: the data pull used to give EVERY person it created a new temporary password, which silently replaced the program password of
  anyone who already had a login with the same email (since v32.1.6). It now leaves an existing login's password alone (test_the_pull_never_replaces_a_program_accounts_password).


## Kind `round_lock` + actions `lock` / `release` (Program side built, round-locks-sync-v1)
Program push: POST /api/program/actions {actions:[{action_id,type:"lock"|"release",payload}]}; action ids `lock:<record id>` and `rel:<item_id>:<time>`.
Program pull: kind `round_lock` in /api/program/changes, applied by native/cloud_locks.apply_item. item_id = sha1(cloud venue id|round key|presentation id).
`not_admin` on a release keeps it queued and blocked (never dropped). `released` / `unknown_venue` / `not_found` are final answers and are dropped from the outbox.


## Trivia show bundles (Program side built, cloud-show-import-v1)
Cloud: GET /api/program/trivia-plans -> {plans:[{id,name,venue_id,venue_name,host_name,round_count,updated_at,size,complete}]} (only status "ready", only this PC's venues);
GET /api/program/trivia-plans/{id}/bighat (409 = a round is gone from the Cloud library, 404 = not yours, 402 = lapsed); POST .../imported (informational).
Bundle = ZIP: manifest.json (type "trivia-show-bundle", version 1), payload.json (host.email, location.name, rounds[{order,type,name,file}]), rounds/<TYPE>/<file>.bighat.
Program matches host by EMAIL and venue by NAME; the lock starts at import, never at plan time.


## round_uid (Program side built, round-uid-program-v1; Cloud task: docs/CLOUD_TASK_round_uid.md)
`round_uid` = lowercase UUID in a round file's manifest.json, stamped once by the Cloud library, never changed. Locks/releases carry an optional `round_uid`;
change-feed items carry `data.round_uid`. item_id is unchanged. A lock matches by uid OR by name; a release by uid frees the round under any file name.
