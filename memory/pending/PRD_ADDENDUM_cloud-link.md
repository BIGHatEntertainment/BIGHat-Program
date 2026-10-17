PASTE THIS SECTION into memory/PRD.md (after the Setup Package section), then delete this file.

## Cloud link (v32.1.2)
- Goal: let several PCs owned by one customer link to ONE BIG Hat Cloud account (central hub for updates, files and scheduling).
- Where: Admin > Integrations > "BIG Hat Cloud" card.
- Contract (defined by BIGHat-Cloud backend/routes/program_routes.py): the program shows a permanent 6-character code; the owner types it in Cloud Settings; the program announces {code, license_key, name, app_version} to /api/program/announce and, once linked, collects its access key ONCE from /api/program/claim-token.
- Persistence rule: code and link state live in <AppData>/secure/cloud_link.json, access key encrypted with secure/ledger.key. Disk is the source of truth. Never in the database, never in the browser.
- Open: the program does not yet USE the access key (no sync calls are built). The cloud address is empty until the cloud app is deployed. A way to reset the code and unlink is not built.
