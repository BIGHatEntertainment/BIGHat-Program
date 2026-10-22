# Task for the BIGHat-Cloud build agent: organization login for linked Programs (cloud)

Read README.md, memory/RULES.md, memory/PRD.md, memory/SYNC_CONTRACT.md (section "Organization login") first. Work only on a new branch `feature/program-org-login` in BIGHat-Cloud. Say which files you will touch before touching them. Do not change /api/program/announce or /claim-token response shapes. Do not touch /api/auth/login behaviour.

Build `POST /api/program/auth/login` exactly as the contract section describes.
- Auth the Program with the existing `program_auth.require_program` (Bearer key). account_id comes from the key only.
- Look up the user with `{email: lowercase, account_id: <from key>}`. Not found, wrong password, or other organization all return the SAME 401 `invalid_credentials`, after the same amount of work (use the existing dummy-hash pattern in routes/auth_routes.py).
- Reuse the existing helpers in routes/auth_routes.py (check_rate_limit, record_failed_attempt, clear_failed_attempts, verify_password). Use an identifier prefix `prog|` so program attempts and web attempts do not lock each other out by mistake, but keep the per-email ceiling.
- is_active false -> 403 `deactivated`.
- NO two-factor here. The Cloud's `master_admin` is BIG Hat's platform account (admin@bighat.live) and belongs to no organization; the account-scoped lookup must never match it and you must not add a special case for it. Do not add any totp_code, totp_required or setup_required behaviour. Only `account_owner` and `host` users of the key's account can sign in through this route; any other role in that account gets the same 401 `invalid_credentials`.
- Success returns only `{ok:true, user:{email,name,role,is_admin,phone}}`. No cookie, no token, no ids, no hash.
- Add an audit_log row per success (action `program_login`).
- Tests: right password in org; same email+password with a key from ANOTHER organization is refused; wrong password; unknown email returns the identical body and status as wrong password; deactivated; rate limit locks after the limit; response has none of: password_hash, _id, account_id, license_key; a platform master_admin (no account) cannot log in through the route with the right password; unlinked and lapsed keys. Prove at least two tests can fail by breaking the code on purpose.
- Then update README.md, memory/PRD.md and CHANGELOG with TESTED and NOT VERIFIED lines, and report the branch name.
