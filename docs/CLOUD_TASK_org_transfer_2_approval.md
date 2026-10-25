# Task 2 of 2 for the BIGHat-Cloud build agent: BIG Hat Admin approval and the transfer itself. Needs task 1 merged.

Read README.md, memory/RULES.md, memory/PRD.md and memory/SYNC_CONTRACT.md first. New branch `feature/org-transfer-approval`. List files touched and not touched. Additive only.

## Owner decisions (2026-10-25)
- Only the BIG Hat Admin (platform `master_admin`, already two-factor) can approve or decline. Every transfer, every time.
- On approval the person MOVES from Org A to their new Org B and becomes its `account_owner`. They are fully out of Org A. There is no link back and no second membership.
  (If they host for Org A later, Org A's owner adds them with a DIFFERENT email.)
- Org A's records of them are KEPT, not deleted: their past events and claims stay readable. They are not carried to Org B.
- Org A's owner is told by EMAIL and by a NOTICE in the Cloud dashboard. Email must never block or undo the transfer.

## Backend
1. Admin routes (all behind `require_admin`, i.e. master_admin, same file as the other admin routes):
   - `GET /api/admin/transfers?status=pending|approved|declined|cancelled&skip=&limit=` paginated (limit <= 50), newest first. Each row: request id, requested_at, person name + email, from org (name/owner email, role), to org (license masked), status, who decided and when.
   - `GET /api/admin/transfers/{id}` the same plus what WOULD move: counts only (the person's employee row in Org A, their upcoming claimed events in Org A, programs linked to Org A) so the admin sees the impact before approving. Never lists other people's data.
   - `POST /api/admin/transfers/{id}/approve` body `{confirm: true}`
   - `POST /api/admin/transfers/{id}/decline` body `{reason: str (required, 3-500 chars)}`
2. APPROVE does these steps IN THIS ORDER, each guarded so a failure undoes ONLY what this call did and leaves the request `pending` with a clear error (nothing half-moved):
   a. Re-check at the moment of approval (do not trust the request): the request is `pending`; the person still exists, is active, is not master_admin, is still in `from_account_id` and is NOT the owner of any account; the parked account still exists with `status: "pending_transfer"` and its license key is still valid on the license server (fails closed: license server down -> refuse, stays pending).
   b. Compare-and-set the user row: set `account_id` = Org B, `role` = `account_owner`, only if it still equals the values read in (a). Bump `password_changed_at` NOT (their password stays); instead set `sessions_valid_after` (or reuse `password_changed_at`'s check) so every token issued before the move stops working. They sign in again and land in Org B.
   c. Activate the parked account: remove `status: "pending_transfer"`, set `owner_user_id`/`owner_email` to the person, `created_at` kept.
   d. In Org A: set the person's `employees` row `active: false` and `left_at`, `left_reason: "transferred"`. DO NOT delete it and DO NOT touch claims, events or files. Org A's `claimed_by` keeps pointing at the old employee id so history still reads. Their host pictures/profile in Org A stay with Org A.
   e. In Org B: create the person's `employees` row (admin flag true, active) so they appear in their own schedule and in the Program person list.
   f. Programs: any Program linked to Org A stays linked to Org A (it belongs to Org A's key). The person simply stops being accepted there because the Program login asks the Cloud every time and the Cloud no longer finds them in Org A. Add a regression test for exactly that.
   g. Mark the request `approved` with `decided_at`, `decided_by` (the admin id). Write audit_log rows: `transfer_approved` (actor admin, target user, from/to account ids) in the platform log, and one in each org's visible log.
   h. THEN, outside the transfer: notify Org A's owner(s): an email via `email_service.send_email` (plain text, link only to the site's own domain; the anti-phishing check in email_service must pass) saying "<person> has left your organization and now owns their own. Their past events stay in your records. Their Program sign-in on your PCs no longer works." AND a dashboard notice. A failed or paused email (503/502) is logged and `from_org_notified: false` is kept for a retry; it NEVER fails the approval. Also email the person ("Your Owners account is approved. Sign in and link your Program with the 6-character code.").
3. DECLINE: only from `pending`. Set `declined`, store the reason, delete the parked account (frees the license key), set the person's `next_allowed_at` = now + 24 h, audit `transfer_declined`. The person stays exactly as they were. Email the person with the reason (failure never blocks).
4. A notice for Org A's owner: new collection `org_notices` `{id, account_id, kind: "member_left", text, created_at, read_at}` indexed `(account_id, read_at, created_at)`. `GET /api/account/notices` (owner/admin of that account only, their own account only, paginated) and `POST /api/account/notices/{id}/read`. Show the unread count and the list in the owner dashboard (a small bell/card, no popups).
5. Idempotency and races: approving twice, or approve while the person cancels, must end in exactly one outcome (use compare-and-set on the request status). Two admins approving at once: one wins.
6. Admin front end: a "Transfer requests" section in the BIG Hat Admin area: the pending list with the impact counts, Approve (confirm dialog that names both orgs and the person) and Decline (reason box). History tab for the rest.

## Scale and safety rules
- Everything indexed and bounded; no loops over all users/accounts; no operation touches any org other than Org A and Org B.
- A transfer never deletes a person, an event, a claim, a file or an audit row. The only destructive action is deleting the PARKED (empty) account on decline/cancel.
- The platform master_admin can never be transferred; an account_owner can never be transferred.

## Tests (required, real MongoDB)
- approve: the user row moves to Org B as account_owner; their old token stops working; the new account is active; Org A's employee row is inactive but still exists; Org A's events/claims/files are byte-for-byte unchanged; Org B has the employee row; one audit row per side.
- approve re-checks: license key now invalid, license server down, person deactivated, person became an owner, person already moved, parked account missing -> refused, request stays pending, NOTHING changed (compare the whole user and account rows before/after).
- failure injected at each step b..g: only that call's own changes are undone; the request stays pending.
- decline: reason required; parked account deleted and key free; person unchanged; cooldown set and enforced by task 1's register; double decline / decline after approve refused.
- race: approve vs cancel, approve vs approve -> one outcome.
- email: success sets notified; a 503 from email does not fail the approval and leaves `from_org_notified: false`; the message contains no password, no full key, and passes the email anti-phishing guard.
- notices: Org A's owner sees one notice; another org's owner sees none; an org cannot read another org's notices.
- Program regression (important): after approval, `POST /api/program/auth/login` for that person on a Program linked to Org A answers `invalid_credentials` (the same neutral 401 as an unknown person), and on a Program linked to Org B (once linked) answers as account_owner.
- only master_admin can use every /api/admin/transfers route (403 for an owner, 401 signed out). Every existing test passes unchanged.
Then update README.md, memory/PRD.md and CHANGELOG with TESTED and NOT VERIFIED lines and report the branch name.

## After this task (not part of it)
The Program side needs nothing new: its organization login already asks the Cloud every time. The Program assistant will re-test that a person who moved out of Org A is refused on Org A's PCs and accepted on Org B's.
