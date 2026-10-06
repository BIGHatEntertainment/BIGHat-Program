# BIG Hat WebApp -> Standalone Program: Data Export Spec

**For:** the build agent of the BIG Hat web app (the Emergent prototype).
**From:** Monty, builder of the BIG Hat standalone desktop program (repo `BIGHatEntertainment/BIGHat-Program`).
**Goal:** add ONE export feature to the web app so an owner can download a single file, and the desktop program can import it. Employees then move to the new program without re-entering anything.

---

## 1. Why this is built to be re-run

The first export will not be perfect (a field will be missing, a file will not open, a date will be in the wrong format). So the design is:

1. **Nothing is lost on the web app side.** Export only READS. It never changes or deletes web app data.
2. **The export file is self-describing.** A `manifest.json` lists every item with a count, so the desktop can show a preview and a report of what did and did not come across.
3. **One bad item never stops the rest.** If a user or file is broken, the export skips it, writes the reason to `export_report.json`, and keeps going.
4. **Importing is repeatable.** The desktop skips what it already has, so the owner can export again after a fix and import again, with no duplicates.
5. **Everything has a stable id** (`source_id`) from the web app, so a second export matches the first.

Please keep to the file format below exactly. If something in the web app does not fit, **do not change the format**: put the item in `export_report.json` as "skipped" with a reason, and tell Monty what was different.

---

## 2. What to build in the web app

**A "Export for the standalone program" button** in the Admin area (master admin and admin only).

- Click it, the server builds one file, the browser downloads it.
- File name: `bighat-export-YYYY-MM-DD.zip`.
- Show a short summary when done: "12 users, 340 files, 95 rounds played. 3 items skipped (see report)."
- Add a second, optional checkbox per section so the owner can export only users, only files, or only rounds played (all ticked by default). Smaller exports make fixing easier.
- It must be **read-only** and must not require stopping the web app.
- It must work for large data: build the zip as a stream and do not load every file into memory.

---

## 3. The export file (ZIP)

```
bighat-export-2026-10-06.zip
├── manifest.json            REQUIRED  what is inside, counts, version
├── export_report.json       REQUIRED  what was skipped and why
├── users.json               users (no passwords, see 4.1)
├── locations.json           locations / venues (names, addresses)
├── rounds_played.json       trivia round history (see 4.3)
└── files/
    ├── trivia/              .bighat trivia round files
    ├── bingo/               .bighat bingo pack files
    └── karaoke/             .bighat karaoke playlist files
```

If a section was not selected or has no data, leave that file out and set its count to 0 in the manifest. Never leave an empty or half-written file.

### 3.1 manifest.json

```json
{
  "format": "bighat-webapp-export",
  "format_version": 1,
  "exported_at": "2026-10-06T16:30:00Z",
  "source": {
    "app": "BIG Hat WebApp",
    "app_version": "x.y.z (whatever the web app calls itself)",
    "base_url": "https://the-web-app-address"
  },
  "counts": {
    "users": 12,
    "locations": 6,
    "files_trivia": 300,
    "files_bingo": 25,
    "files_karaoke": 15,
    "rounds_played": 95
  },
  "skipped_total": 3,
  "notes": "free text, optional"
}
```

### 3.2 export_report.json

```json
{
  "skipped": [
    { "section": "files", "source_id": "abc123", "name": "Round 14.bighat",
      "reason": "file content missing in storage" },
    { "section": "users", "source_id": "u-77", "name": "(no name)",
      "reason": "no email address" }
  ],
  "warnings": [
    { "section": "rounds_played", "message": "12 records had a date without a time zone; treated as UTC" }
  ]
}
```
Every item that is NOT exported must appear here with a plain-English reason. A manifest count plus the report should always add up to what the web app has.

---

## 4. The data, field by field

All dates are **ISO 8601 in UTC**, for example `2026-10-06T16:30:00Z`. All text is UTF-8. Do not invent values: if the web app does not have a field, **omit it** (do not send `null` strings like `"None"`).

### 4.1 users.json

```json
{ "users": [
  {
    "source_id": "the web app's own id for this user",
    "email": "person@example.com",
    "first_name": "Sam",
    "last_name": "Host",
    "display_name": "Sam Host",
    "phone": "555-0100",
    "role": "master_admin | admin | host",
    "is_admin": true,
    "enabled": true,
    "created_at": "2025-03-01T12:00:00Z"
  }
]}
```

**Rules**
- **NEVER export passwords or password hashes or tokens.** The desktop program creates its own login for each person (see section 6). This is a security requirement, not a preference.
- `email` is required and must be unique. Lower-case and trim it. Users without an email go in the report.
- `role` must be one of `master_admin`, `admin`, `host`. If the web app has other role names, send the closest one and put the original in `source_role` (a plain string).
- Include the schedule employees (name, email, phone, admin flag) as users too, so the Schedule's employee list can be built. If the web app keeps employees and users in separate collections, export both into this one list and merge by email (one entry per email).
- Include everyone, even if disabled (`enabled: false`).

### 4.2 files (the .bighat files)

- Put each file in `files/trivia/`, `files/bingo/` or `files/karaoke/` as **the original bytes, unchanged**. Do not re-save, re-zip, re-encode, or "clean up" a `.bighat` file. They are ZIP archives made by the BIG Hat File Creator tool; keep the exact original file name (the name matters, the desktop locks rounds by file name).
- Add `files/index.json` next to them:

```json
{ "files": [
  {
    "source_id": "web app id",
    "kind": "trivia | bingo | karaoke",
    "path": "files/trivia/MC-01-A.bighat",
    "file_name": "MC-01-A.bighat",
    "size_bytes": 1048576,
    "sha256": "hex of the file bytes",
    "round_type": "MC | REG | MISC | MYS | BIG",
    "uploaded_at": "2025-04-01T09:00:00Z"
  }
]}
```
- `sha256` is **required**. It lets the desktop prove each file arrived intact and skip duplicates.
- `round_type` for trivia: `MC` (multiple choice), `REG` (regular/general), `MISC` (miscellaneous), `MYS` (mystery), `BIG` (the big final round). Use exactly these five codes. On the desktop the files are stored in one folder per code (`Trivia\MC`, `Trivia\REG`, and so on), so a wrong or missing `round_type` puts a file in the wrong folder. If the web app only knows the type from the file name (for example `MC-01-A` starts with `MC`), fill it in from the name. If the type truly cannot be told, leave `round_type` out and add the file to the report as a warning; the desktop will put it in a fallback folder for review.
- If two files have the same name but different content, keep both: add the web app's id to the stored name (`MC-01-A__abc123.bighat`) and list both in the index.
- If the web app stores a file's content inside the database (GridFS or similar) rather than on disk, read the bytes out and write them into the zip. If that is not possible for an item, report it as skipped.
- Also export **presentations** if the web app has built ones, as `presentations.json`. A presentation is: `{ source_id, name, location (name), created_at, created_by (email), rounds: [{order, file_name, round_type}] }`. This is optional for the first version.

### 4.3 rounds_played.json (trivia round history)

This is what the desktop's **180-day round lock** uses, so a round already played at a location stays hidden from that location until it expires. One record per round played.

```json
{ "rounds_played": [
  {
    "source_id": "web app's id for this record",
    "location": "Monkey Pants",
    "round_file": "MC-01-A.bighat",
    "round_type": "MC",
    "round_number": 1,
    "used_date": "2026-08-14T01:30:00Z",
    "used_by": "sam@example.com",
    "presentation_name": "Tuesday Night Trivia"
  }
]}
```

**Rules**
- `location` is the location **name as the web app shows it** (the desktop matches names ignoring case, spaces and punctuation).
- `round_file` is the exact file name of the round (with `.bighat`). It must match a file in `files/` where possible.
- `used_date` is when it was played (or built, if that is all the web app knows).
- **Do NOT calculate an expiry date.** The desktop works out "180 days after `used_date`" itself. If the web app has its own expiry field, send it as `source_expires_date` for reference only.
- Include **released** records the same way (the 180-day lock released early by an admin) with `"released": true`, so they do NOT lock the round again.
- Export the full history, not only the active locks. The desktop ignores expired ones.

### 4.4 locations.json

```json
{ "locations": [
  { "source_id": "...", "name": "Monkey Pants", "address": "1 Main St",
    "city": "Phoenix", "state": "AZ", "zip": "85001", "timezone": "America/Phoenix" }
]}
```
Names must match the names used in `rounds_played.json` and `users.json` (if users have a home location). Skip fields the web app does not have.

---

## 5. What the web app must NOT do

- Do not include passwords, password hashes, tokens, API keys, secrets, or session data.
- Do not modify, lock, or delete anything in the web app.
- Do not change a `.bighat` file's bytes or name.
- Do not rename fields or change types. If the web app's data does not fit, report it and tell Monty.

---

## 6. What the desktop program does with it (so you know the other side)

The desktop will get an **Import from Web App** screen (master admin only). It works in four steps, and every step can be repeated:

1. **Choose the zip.** The program checks `manifest.json` and `format_version`, and shows a **preview** with counts and the report's skipped items. Nothing is written yet.
2. **Backup.** The program takes a backup snapshot first.
3. **Import** (each part is separate, the owner ticks what they want):
   - **Users:** matched by email. New people get a login with a **temporary password shown once** (to give to the employee). Existing people are left as they are. **The master admin is never changed.** People are also added to the Schedule's employee list.
   - **Locations:** added to the Schedule's venue list (the program's single list of places); matched by name, never duplicated.
   - **Files:** each file's `sha256` is checked; copied into `Documents\BIG Hat Entertainment\Files\...`. Files already present (same name and same hash) are skipped; same name with different content is kept as a second copy and flagged.
   - **Rounds played:** added to the 180-day lock list with the original `used_date`. Already-imported records (by `source_id`) are skipped.
4. **Import report.** A plain list of what came across, what was skipped, and why, saved as a file the owner can send to Monty.

Because of step 4, a partial first import is fine: the report tells us what to fix in the export, and a re-run only adds what is missing.

---

## 7. Acceptance checklist (please confirm each when done)

- [ ] Button in Admin (admin and master admin only) that downloads `bighat-export-YYYY-MM-DD.zip`.
- [ ] `manifest.json` and `export_report.json` are always present.
- [ ] `users.json` has no passwords or hashes (please grep the finished zip for `password`).
- [ ] Every `.bighat` file in `files/` is byte-identical to the original (compare `sha256`).
- [ ] `files/index.json` lists every file with `sha256`.
- [ ] `rounds_played.json` has full history, including released ones, with no expiry calculation.
- [ ] Counts in `manifest.json` match what is in the zip.
- [ ] Anything skipped appears in `export_report.json` with a plain reason.
- [ ] Export is read-only and works with large data (streamed).
- [ ] Reply to Monty with: how the web app names roles, where it stores files (disk or database), what the round history collection is called, and anything that did not fit this spec.

---

## 8. Questions to answer in your reply (please include real examples)

1. Paste **one real example** (with private details changed) of a user, a round history record and a file entry exactly as the web app stores them.
2. What are the web app's role names?
3. Are the `.bighat` files stored on disk, or inside the database?
4. Does the web app keep **employees** and **users** as the same thing or separate?
5. Does the web app keep a list of locations, or only a text field on each record?
