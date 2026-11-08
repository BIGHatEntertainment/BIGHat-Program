# Investigation: Cloud-pulled rounds "always stopped on step 2"; after loading rounds from PC files the venue overlays did not load (2026-11-04) — OPEN, needs the PC's backend.log

## Report
A PC that always worked: rounds pulled from the Cloud (the same rounds that ran fine the night before at another venue) started loading and stopped on "step 2"; nothing worked.
Choosing different rounds from the files on the PC worked, but the venue's overlays did not load although they are on the PC. Owner rule: no guessing, no changes that are not needed;
when a PC is linked to a Cloud account there should be ONE source of truth.

## Ruled out with real tests (nothing was changed in the code)
1. The Cloud's round stamping (`routes/file_routes.stamp_zip`) breaking a file: all 5 fixtures stamped with the Cloud's own function open in the Program's own reader (`native_slides._read_bighat_round`);
   the only difference is the `_manifest.round_uid` field; every other member is byte-identical.
2. A show pulled from the Cloud losing the venue's overlays (`Files/Locations/<slug>`): `load_location_overlays` finds both overlays for a Cloud-pulled show.
3. A different file with the same name already on the PC: the import keeps it, writes the new round as `name-<8hex>.bighat`, the show points at the right file and all 5 rounds load.
4. The Cloud's automatic file pull (`native/cloud_files.py`) hiding the owner's own overlays: the owner's overlay record + file survive Cloud pulls and the Cloud's are added beside them (records, files on disk and
   what the Presenter loads all agree after each pull).
5. "Step 2": no screen in the Program shows numbered loading steps (searched the Trivia screens). The words may come from a different tool or a message I have not seen.

## What is known
- When a round fails to load the Program writes ONE of these lines to `backend.log` (in the data folder `logs/` next to `launcher_crash.log`):
  `round not found for ref ...` (the show points at a file that is not where it says), `no disk data for round ref ...` (file found, no usable data), `.bighat unzip failed for ...` (damaged / not a round).
- Overlays appear only when the show names a venue that maps to a `Files/Locations/<slug>/` folder AND that folder's `location.json` lists the overlay AND the image file is on disk
  (`native_slides.load_location_overlays`). If any one of the three is off, the overlays silently disappear.

## Needed from the PC (nothing else)
1. `backend.log` (data folder > logs), the part from the moment of the failure, and the exact words on the screen at "step 2" (a photo is fine). Which screen was it (Trivia presenter, lobby import, Presentations list)?
2. For the overlays: the venue's `Files/Locations/<venue folder>/location.json` (the `overlay_images` list) and a listing of that folder's `overlays/` files.
3. Was the show built from the Cloud wizard (Cloud shows card) or pulled by the automatic file sync? Which Program version?

## Not changed on purpose
No code was edited. Every path above works in tests; the failure must come from the actual files on that PC, which only its logs can show.
