# Task 1 of 2 for the BIGHat-Cloud build agent: "branch off" request (register with a license key as an existing user)

Read README.md, memory/RULES.md, memory/PRD.md and memory/SYNC_CONTRACT.md first. Work only on a new branch `feature/org-transfer-request` in BIGHat-Cloud.
List the files you touched and what you did NOT touch. Do not change the behaviour of any existing route for a person with a NEW email, and do not change any existing test. Everything is ADDITIVE.
Do NOT start task 2 (the admin approval and the move); it needs this one merged and checked.

## Why (owner decisions, 2026-10-25)
A person who already belongs to one organization ("Org A") can buy their own program license and become the OWNER of their own organization ("Org B"), branching off from Org A.
There is NO two-organization membership. One person, one account, one organization at a time. A transfer MOVES the person from Org A to Org B, and only the BIG Hat Admin (the platform master_admin) can approve it.
Until it is approved nothing about the person changes: they stay in Org A with the same role and the same sign-in.

## The flow the person sees
"Register account" (bottom of the sign-in page): license key + email + password + name.
- A NEW email: exactly today's behaviour.
- An EXISTING email: after the password is proven, a prompt: "Your account is part of <Org A name> as <role>. Do you want to keep your account there, or branch off and create your own organization?"
  - Keep: nothing happens; the page says so. (No data is created.)
  - Branch off: a short explanation ("An Owners account is for control of your own events and the hosts under you. BIG Hat approves every transfer. Until then you stay in <Org A name> exactly as now."), a Confirm button, then a "Waiting for approval" screen that also tells them to link their Program to their new account once approved.

## What to build (backend)
1. `POST /api/auth/register`: for an EXISTING email it must stop answering "Email already registered". It answers 200 `{status: "existing_account", needs_password: true}` and creates NOTHING and reveals NOTHING (no name, no org, no role). For an email that does not exist, today's flow runs unchanged. Rate-limit this path with the existing `check_rate_limit` using a `register|<email>` key so it cannot be used to probe emails. Do not let the response, status or timing tell an attacker more than the sign-up page already does.
2. `POST /api/auth/register/preview` body `{email, password, license_key}`:
   - verify the password for the existing user in constant time (dummy hash for an unknown email); wrong password -> the same generic 401 as sign-in, and it counts toward the rate limit;
   - validate the license key EXACTLY as register does (valid on the license server, fails closed if the server is unreachable, not already on another account);
   - refuse (clear message) if the person is the platform `master_admin`, is deactivated, or is already the `account_owner` of an organization (an owner cannot branch off; they can add a key to their own org);
   - on success return `{status: "can_branch_off", person: {name, email}, current: {org_name, role}, license_masked}`. `org_name` is the current organization's owner name or email, never another person's personal data.
3. `POST /api/auth/register/branch-off` body `{email, password, license_key, confirm: true}` (re-prove the password; do not trust the preview call):
   - create the NEW account document exactly as register does (new `account_id`, the license key on it, `owner_user_id` = the existing user's id, `max_programs` 5) but with `status: "pending_transfer"` and NO owner sign-in able to reach it. Nothing in it is reachable by anyone until task 2 approves it;
   - create a `transfer_requests` document: `{id (uuid), user_id, email, from_account_id, from_role, to_account_id, license_masked, status: "pending", requested_at, decided_at: null, decided_by: null, reason: null, from_org_notified: false}`;
   - the user's `account_id`, `role`, sessions and tokens are NOT touched;
   - write an audit_log row `transfer_requested` (actor = the person; details never contain the password or the full key);
   - answer `{status: "pending_admin_approval", message, next: "link_program_after_approval"}`.
   - If anything after the account insert fails, undo what THIS call created (the new account and the request) and nothing else, the same compensation register already uses for the unique license key.
4. Indexes (add in the existing index setup): `transfer_requests.status + requested_at`, unique `transfer_requests` on `(user_id, status)` restricted to `status: "pending"` (a person can have only ONE open request), `accounts.status` sparse.
5. A person can cancel their own pending request: `DELETE /api/auth/register/branch-off` (signed in, their own request only). It deletes the parked account and marks the request `cancelled`. Never anyone else's.
6. Front end `RegisterPage.js`: the prompts and screens above. Plain wording, no jargon. Never show the person another person's data.

## Scale rules (the reason this is built carefully)
- Every query added is indexed and bounded. Nothing scans a collection. No per-request loop over all users or accounts.
- A parked account holds no data and can be deleted by cancel or by decline (task 2) with no leftovers.
- Cap: a person may have 1 open request; a decline puts a 24 hour cooldown before another request from the same person (store `next_allowed_at`).
- The license key can only ever be on ONE account (the existing unique index must still hold). A key attached to a parked account is "in use" for everyone else until the request ends.

## Tests (required, real MongoDB as the existing tests do)
- existing email, no password proof: reveals nothing; wrong password: generic 401 + counted toward the rate limit; unknown email: the normal new-sign-up path.
- preview: correct password shows only the person's own current org name and role; a master_admin, a deactivated user and an account_owner are each refused with a clear message.
- branch-off: creates the parked account + one pending request + an audit row; the person's account_id, role and token are unchanged; the new account is not reachable (a sign-in cannot enter it, no program can link to it).
- a key already used / invalid / license server down: refused, nothing created; simulate a failure after the account insert and check the undo leaves no parked account and no request.
- double submit creates one request; cancel removes it and the parked account and frees the key; the cooldown blocks an immediate retry after a decline (use a fixture, task 2 builds the decline).
- a brand-new email still registers exactly as before (regression). Every existing test passes unchanged.
Then update README.md, memory/PRD.md and CHANGELOG with TESTED and NOT VERIFIED lines and report the branch name.
