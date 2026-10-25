# Cloud task 3 of 4: Cloud Build Wizard + saved show plans (spec v0.1, 2026-10-25, DRAFT for owner approval)
Needs task 1 (library). Task 2 makes it richer ("last used here") but is not required. Copy the PROTOTYPE wizard: BIGHat-Program `_reference/standalone_v30/frontend/src/components/trivia/TriviaBuilderWizard.jsx` (743 lines) and its SlotMachineRandomizer.jsx. Keep its screens, step order and look. Only the data calls change. Do not redesign it.

## Rules copied from the Program (backend/presentation_builder.py, ROUND_ORDER_SPEC)
- Round count 5 or 6. 5: MC, REG, MISC, MYS, BIG. 6: MC, REG, (REG or MISC), MISC, MYS, BIG (slot 3 is the host's choice).
- A round locked at the chosen venue is HIDDEN (round_locks, same venue rule). The same round cannot be picked twice in one plan.
- The wizard NEVER creates a lock. A lock starts only when the Program imports/builds the show (owner decision 2026-10-25: same as the prototype, even if the plan is made days early).

## Data: collection `trivia_plans`
`{id, account_id, name, host_id (Cloud employee), venue_id, round_count, slots:[{order,type,library_id,round_key,name}], created_by, created_at, updated_at, status: draft|ready}` indexed by account_id and venue_id.

## Endpoints (Cloud web session; ANY host may create/edit/delete THEIR plans; admin/owner may see and edit all)
- `GET /api/trivia/wizard/options` hosts (employees), venues, per-venue availability for each slot type (library rows with locked flag).
- `POST/GET/PUT/DELETE /api/trivia/plans`. Validate on SAVE and again on DOWNLOAD: slot order, count, all library ids exist and belong to the account, host and venue exist. Answer with reasons, never a 500.
- The random "slot machine" picks from unlocked rounds only.

## UI
Trivia page gets "Build a show" (the wizard) and "My plans" (list: name, venue, host, date made, status; Open, Edit, Download .bighat (task 4), Delete with confirm). Mobile friendly. A plan whose round was LOCKED after it was saved shows a warning badge (not an error).

## Acceptance
1. A host builds a 6-round plan end to end and sees it in My plans. 2. Locked rounds never appear for that venue and appear for another. 3. Wrong slot order / duplicate round / foreign account id is rejected with a reason. 4. A host cannot see another host's plan; an admin can. 5. Saving a plan creates NO lock. 6. Delete asks first.
