# Cloud task: Trivia round locks (sync + verify)  (spec v0.1, 2026-10-22, DRAFT for owner approval)

Read memory/SYNC_CONTRACT.md first. This adds ONE kind to the existing contract. Nothing here is built yet on either side.

## Why
The 180-day round lock is stored on each PC (`Files/Trivia/round_usage.json`). A venue served by two PCs (or a host on a second PC) cannot see the
other PC's locks, so the same round can be offered twice. The Cloud becomes the shared record; the PC stays authoritative for its own show builds.

## Rules (owner wording, kept)
1. A round is locked for a venue for 180 days after use, or until an ADMIN releases it. Nothing else unlocks it.
2. The PC always works from its own copy. If the Cloud is unreachable or the subscription lapsed, the PC keeps its local locks and builds normally.
3. Merging only ADDS locks and APPLIES releases. A lock is never dropped because the other side does not have it.
4. A release is permanent and travels as a release (tombstone), so an old copy of a lock cannot bring it back.

## Data (new `kind: round_lock`, same `changes` lane)
`data`: `{venue_id, venue_name, round_file_name, round_type, used_at, expires_at, presentation_id, presentation_name, used_by, released: bool, released_at, released_by}`
- `item_id` = sha1(venue key + round key + presentation_id). venue key = the Cloud venue item_id; round key = lowercase file stem with the TYPE__ prefix and a trailing -<8 hex> stamp removed
  (the Program already does this: round_usage.same_round_keys).
- The PC maps its venue (id, slug OR name; the Program treats these as one place) to the Cloud venue by the existing normalized-name rule.

## Endpoints (Program key auth, scoped by account_id, as the rest of the contract)
- `GET /api/program/changes?since=N` already carries them once `round_lock` is a kind. A PC receives only the venues assigned to it.
- `POST /api/program/actions` new type `lock`: `{action_id, type:"lock", payload:{...data above}}` and `release`: `{type:"release", payload:{item_id | venue+round, released_by}}`.
  Release only from a role with admin rights (account_owner / local admin). Result: applied | duplicate | rejected(reason).
- `GET /api/trivia/round-locks?venue=<id>` (Cloud web session): what is locked per venue, with who/when/expiry, for the Cloud Trivia tab.

## Cloud Trivia tab (web)
- A "Round locks" panel: pick a venue, see locked rounds with date used, expiry date, show name, host. Admin button "Release" (confirm, audit_log row).
- A "Verify" action: compares the Cloud list with the last list each linked PC reported and shows differences (lock on a PC the Cloud lacks; lock on the Cloud a PC lacks).

## Program side (the Program agent / assistant builds this; NOT the Cloud agent)
- Push: every new lock and every admin release is queued in the outbox, same as claims.
- Pull: apply locks and releases for assigned venues into round_usage.json. A release received wins over a local lock with the same item_id and an older used_at.
- Build wizard / Roulette / Special / lobby import: unchanged; they already read round_usage.json.

## Acceptance (Cloud)
1. PC A builds a show at venue V; within one sync the Cloud lists the 6 locks. 2. PC B (same venue) pulls and its Wizard no longer offers those rounds.
3. Admin releases one round in the Cloud; both PCs offer it again after their next pull, and a stale PC cannot re-lock it from an old copy.
4. A PC that was offline for days syncs without losing or duplicating locks (idempotent on item_id).
5. A user without admin rights cannot release. 6. Account A never sees Account B's locks.
