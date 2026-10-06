# QR Relay (alpha.82): notes for deploying api.bighat.live

**What it is.** A small addition to the existing `api.bighat.live` service (same code base, `BIGHAT_CLOUD_MODE=1`). It lets a phone reach things that live on a host's PC:
1. **File drop:** Story Generator and Scoreboard upload a finished video/PNG, get a public link, show it as a QR. Files expire.
2. **Karaoke song requests:** the phone opens a page on the relay and sends a request; the PC pulls it every 3 s over outbound HTTPS. No router or firewall changes at the venue.

## Before you redeploy (order matters)
1. The relay code is in the repo as of alpha.82 (`backend/cloud/relay_router.py`, mounted in `backend/server.py`). Redeploy api.bighat.live from that version of `main`.
2. Set the proxy items in "Things you must do" below (upload size, real client IP) BEFORE testing, or big uploads and phone limits will misbehave.
3. Nothing else changes: same env vars as today (`BIGHAT_CLOUD_MODE=1`, your Mongo settings). The new settings are all optional.
4. Existing license, download and update routes are untouched.

**Code:** `backend/cloud/relay_router.py` (mounted in `backend/server.py` next to the other cloud routers, inside the `BIGHAT_CLOUD_MODE` block, after `cloud_download_landing_router`). No new packages (uses `fastapi`, already installed).

## Routes (all on api.bighat.live)
| Route | Who calls it | Needs |
|---|---|---|
| `POST /api/relay/files` | the PC | license key + machine id (form fields) |
| `GET /api/relay/d/{id}` (also `/d/{id}`) | a phone (the QR) | nothing, id is a 128-bit random token |
| `DELETE /api/relay/files/{id}` | the PC | license key + machine id |
| `POST /api/relay/karaoke/sessions` (+ `/{id}/close`, `/{id}/pull`) | the PC | license key + machine id |
| `GET /api/relay/k/{id}` (also `/k/{id}`) | a phone (the QR) | nothing (random token) |
| `POST /api/relay/karaoke/{id}/request`, `GET .../status/{rid}` | a phone | nothing (random token) |

Every PC call is checked with the existing `LicenseService.validate(key, hwid)`: unknown, revoked or un-activated copies get `401`.

## Things you must do when deploying
1. **Persistent disk for uploads.** Files are written to `RELAY_FILES_DIR` (default `/tmp/bighat_relay_files`). `/tmp` is wiped on redeploy, which only means open QR links die early. Point it at a mounted volume if you want links to survive redeploys.
2. **Request body size.** The PC uploads up to `RELAY_MAX_FILE_MB` (default 150 MB). Make sure the proxy/ingress in front of the service allows bodies that large (many default to 1 to 10 MB) and does not time out a ~1 minute upload.
3. **Real client IP.** Phone rate limiting uses `X-Forwarded-For`. Make sure your proxy sets it, otherwise all guests look like one phone and share the 20-second cooldown.
4. **MongoDB collections created automatically:** `relay_files`, `relay_sessions`, `relay_requests`. No migration.
5. **Cleanup** happens on each upload and each new night (expired files and nights are deleted). If you want it on a timer too, add a cron that calls the purge; not required.

## Settings (all optional environment variables)
(alpha.84 adds `RELAY_AUTH_CACHE_SECONDS` (300; a revoked license can keep using the relay for up to this long) and `RELAY_MAX_MB_PER_LICENSE` (600; total stored files per license).)

`RELAY_FILE_TTL_HOURS` (48) | `RELAY_MAX_FILE_MB` (150) | `RELAY_MAX_FILES_PER_LICENSE` (20) | `RELAY_SESSION_TTL_HOURS` (14) | `RELAY_MAX_REQUESTS_PER_SESSION` (300) | `RELAY_MAX_SESSIONS_PER_LICENSE` (5) | `RELAY_PHONE_COOLDOWN_SECONDS` (20) | `RELAY_FILES_DIR`

## Link paths (alpha.83)
On api.bighat.live only `/api/...` paths reach the backend; anything else shows the website. So the relay now hands out `/api/relay/d/{id}` and `/api/relay/k/{id}`, and the desktop program rewrites the short `/d/` and `/k/` forms the same way. The short routes still exist but are not used in QRs.

## Differences between this repo and the deployed copy
The deployed relay (branch `QR-Integration`) swaps the upload loop for a helper `local_disk.stream_to_disk` that exists only in that codebase. This repo keeps its own loop. Both behave the same (150 MB cap, `file_too_big` 413). Do not copy either file over the other.

## Quick check after deploying
1. `GET https://api.bighat.live/api/relay/d/aaaaaaaaaaaaaaaaaaaaaa` should return a small "link has expired" page (404), not a server error.
2. In the desktop program (alpha.82), start a Karaoke night, scan the QR with a phone on mobile data (not the venue Wi-Fi), send a song, and watch it appear in the host's request list within a few seconds.
3. Export a Scoreboard PNG, click the QR button, scan it on mobile data: the image should open.

## What the relay stores
A singer's first name and song title for the length of the night, and exported files for 48 hours. No logins, passwords, emails or payment data. Phones are identified only by a one-way hash of IP + night id (for the cooldown).

## Not included yet (planned)
- Rewards sign-up QR for Trivia and Bingo (waiting for the Rewards app README).
- Bingo player-join QR still uses the PC address (unchanged).

## Scaling notes (alpha.84)
- **What changed for growth:** MongoDB indexes are created at startup (`ensure_indexes`, called from the app lifespan); license checks are cached for 5 minutes (`validate()` writes to the license record on every call, so a polling PC would otherwise write every 3 s); a PC polls every 3 s while busy and every 10 s after a quiet minute; a per-license storage cap; and the desktop can point at a separate relay address (`relay_base_url` in system_config.json, or `BIGHAT_RELAY_BASE_URL`) without a new release.
- **Measured (local, one small machine, real MongoDB, load from several client processes):** 10 venues is trivial; 100 venues is fine (median 5 ms, 95th percentile under 1 s, no errors). At 300 venues one server process starts timing out. These are LOCAL numbers, not production: run it with 2 or more workers behind your proxy for headroom. The expected size (10 venues, about 300 rewards members by end of 2027) is far below this.
- **Not measured:** real uploads at scale, production proxy limits, multi-worker behavior.
- **Load test scripts:** `backend/scripts/load_relay_multi.sh` (local only; refuses the live address). Never run against api.bighat.live.
- **When to split the relay into its own service:** if licensing and update checks slow down on busy nights, or you pass roughly 100 active venues. Then set `relay_base_url` and move `cloud/relay_router.py` to its own deployment.
