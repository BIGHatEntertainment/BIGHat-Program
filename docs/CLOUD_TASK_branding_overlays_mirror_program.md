# CLOUD TASK: make Branding images and Overlays work exactly like the Program, and tell a linked Program about them (BIGHat-Cloud)

Paste this to the Cloud build agent. The owner's words (2026-11-05): "I will make the cloud app mimic the exact behavior of the program."
Program side (a separate PR, BIGHat-Program): a linked PC mirrors the Cloud's branding images and overlays. A PC with no Cloud account is unchanged.
Everything below depends on the Program being LINKED to an account. Nothing here may change how an unlinked Program behaves.

## 1. What the Program does today (copy this behavior exactly)

Per LOCATION (the Cloud's equivalent is the venue) the Program keeps two ordered lists of pictures:

| Program list | Cloud category today | Meaning |
|---|---|---|
| `branding_images` ("Branding images") | `image` | Plays right after the host slide. Drag to reorder. |
| `overlay_images` ("Round overlays") | `overlay` | Composited on top of a round's slides. Drag to reorder. Tagged per round. |

Each picture record in the Program: `id`, `filename`, `mime`, `size`, `order` (0..N-1, no gaps), `ext`, `uploaded_at`, `uploaded_by`.
An overlay record also has `applies_to_round_types`.

### Allowed files (same limits as the Program)
- Branding: `.png .jpg .jpeg .gif .webp`, up to 100 MB each.
- Overlays: the same plus `.mp4 .webm`, up to 100 MB each.

### Order
- `order` is the position in the list the host sees. Dragging rewrites it. Deleting a picture renumbers the rest 0..N-1.
- A new upload goes to the END (order = current count).
- The Program plays/composites strictly by ascending `order`.

### Round tags on overlays (`applies_to_round_types`)  <- the part that is easy to get wrong
Allowed values: `MC`, `REG`, `MISC`, `MYS`, `BIG`, `ANS`, plus numbered `REG1..REG10` and `MISC1..MISC10`. Anything else is rejected (400).
Meaning, exactly as the Program applies it (`presentation_builder.overlays_for_round_type`):
- Field MISSING / null = "untagged legacy": the overlay appears on the QUESTION slides of EVERY round type.
- Field is `[]` (empty list) = DORMANT: appears nowhere. This is different from missing. Keep the difference.
- `MC`, `REG`, `MISC`, `MYS`, `BIG`: the overlay appears on that round type's question slides. A bare `REG`/`MISC` matches every round of that type.
- `REG2`, `MISC4` etc.: matches only that round number.
- `ANS`: the overlay appears on ANSWER slides of every round type. Answer slides get ONLY `ANS`-tagged overlays; question slides never get ANS-only overlays.
- Tags are de-duplicated and upper-cased.
The Program's screen: each overlay card has round-type chips; clicking toggles a tag. A new overlay the host uploads starts UNTAGGED (field missing).

### Delete
Removing a picture deletes the file AND the record, renumbers the order, and it must not come back. (The Program had a bug where it did; fixed in BIGHat-Program PR 77.)
On the Cloud: soft-delete as today is fine, but the manifest (below) must stop listing it so a linked Program can tell it was removed.

## 2. What to build in the Cloud

### 2.1 Data (extend `stored_files` rows for `category in ("image","overlay")`)
- `sort_order` (int): position within (account, venue, category). New files get max+1. Reorder and delete keep it 0..N-1.
- `applies_to_round_types` (list of strings or ABSENT): overlays only. Absent = untagged. `[]` = dormant. Validate against the allowed list above.
- Backfill existing rows once: `sort_order` by `created_at` ascending; leave `applies_to_round_types` ABSENT (that is "untagged", what the Program does with an old upload).

### 2.2 Cloud Files page (the Trivia > Files screen, Images and Overlays tabs)
Same behavior as the Program's Trivia Setup screen: drag to reorder; overlay cards show the round-type chips (MC REG MISC MYS BIG ANS and the numbered REG1..10 / MISC1..10) and toggle them; delete removes and renumbers. Same wording where it helps ("Branding images: plays right after the host slide", "Round overlays: composited on top of every round's slides").

### 2.3 Routes (browser session, account owner/manager only, same checks as `/api/files/upload`)
- `PATCH /api/files/venues/{venue_id}/{category}/order`  body `{"file_ids": [...]}`: new order top-to-bottom; unknown ids ignored; missing ids keep relative order at the end. category is `image` or `overlay`.
- `PATCH /api/files/{file_id}/tags`  body `{"applies_to_round_types": [...]}`: overlays only; 400 on an invalid tag; `[]` is allowed (dormant).
- Delete: existing `DELETE /api/files/{file_id}`; after it, renumber the siblings' `sort_order`.
- Upload: existing; set `sort_order` = end of list; accept the extensions/sizes above for the category (the Program accepts mp4/webm for overlays only).

### 2.4 Tell the Program (this is what the Program-side PR reads)
In `GET /api/program/manifest` (program_sync_routes.py), for entries with category `image` or `overlay` add:
- `sort_order` (int),
- `applies_to_round_types` (list) ONLY when the field exists on the row; omit the key when it does not (the Program treats a missing key as untagged).
- The manifest `sha256` must also change when the TAGS or ORDER change, or the Program cannot notice. Simplest: add a `meta_version` (int, +1 on every reorder/tag change of that file) and include it. Do not change `sha256` itself (it is the file's bytes).
Also make the manifest COMPLETE and honest, because the Program will treat "not listed" as "removed in the Cloud" for pictures it previously received from the Cloud:
- list every non-deleted picture for the venues this Program is assigned to (same venue filter as today),
- add top-level `complete: true` and `venues: [venue ids this answer covers]` so the Program can tell "the Cloud listed everything for venue X" from a partial or failed answer. Never return a truncated list with `complete: true` (the current `to_list(5000)` cap must set `complete: false` if it is hit).

## 3. Rules (the owner has zero tolerance for silent data loss)
1. Nothing in this task changes browser-session behavior for accounts that have no linked Program.
2. Reorder/tag/delete never touch the stored FILE bytes; only `sort_order`, tags and `is_deleted`.
3. A reorder or tag change is atomic per venue+category (no half-renumbered list if two requests race).
4. Sponsor images and `other` files are out of scope.

## 4. Tests (real database)
- Upload three overlays: `sort_order` 0,1,2. Reorder; manifest shows the new order. Delete the middle one: remaining are 0,1 and the deleted one is no longer in the manifest.
- Tag an overlay `["MC","ANS"]`, `["REG2"]`, `[]`: manifest carries exactly that; an untouched overlay has NO `applies_to_round_types` key. An invalid tag is a 400 and changes nothing.
- A tag-only change bumps `meta_version` and leaves `sha256` the same.
- `complete` is true normally and false when the row cap is reached; `venues` lists only the venues this Program may see.
- A Program assigned to venue A never sees venue B's pictures, tags or order.
- Existing upload/download/manifest tests still pass.

## 5. Report back
Routes added, the manifest fields (`sort_order`, `applies_to_round_types`, `meta_version`, `complete`, `venues`), the backfill result, and test results. The Program PR is written against exactly those field names; if you must rename one, say so.
