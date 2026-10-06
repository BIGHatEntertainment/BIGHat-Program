# QR Relay (alpha.82): notes for deploying api.bighat.live

**What it is.** A small addition to the existing `api.bighat.live` service (same code base, `BIGHAT_CLOUD_MODE=1`). It lets a phone reach things that live on a host's PC:
1. **File drop:** Story Generator and Scoreboard upload a finished video/PNG, get a public link, show it as a QR. Files expire.
2. **Karaoke song requests:** the phone opens a page on the relay and sends a request; the PC pulls it every 3 s over outbound HTTPS. No router or firewall changes at the venue.

**Code:** `backend/cloud/relay_router.py` (mounted in `backend/server.py` next to the other cloud routers, inside the `BIGHAT_CLOUD_MODE` block, after `cloud_download_landing_router`). No new packages (uses `fastapi`, already installed).

## Routes (all on api.bighat.live)
| Route | Who calls it | Needs |
|---|---|---|
| `POST /api/relay/files` | the PC | license key + machine id (form fields) |
| `GET /d/{id}` | a phone (the QR) | nothing, id is a 128-bit random token |
| `DELETE /api/relay/files/{id}` | the PC | license key + machine id |
| `POST /api/relay/karaoke/sessions` (+ `/{id}/close`, `/{id}/pull`) | the PC | license key + machine id |
| `GET /k/{id}` | a phone (the QR) | nothing (random token) |
| `POST /api/relay/karaoke/{id}/request`, `GET .../status/{rid}` | a phone | nothing (random token) |

Every PC call is checked with the existing `LicenseService.validate(key, hwid)`: unknown, revoked or un-activated copies get `401`.

## Things you must do when deploying
1. **Persistent disk for uploads.** Files are written to `RELAY_FILES_DIR` (default `/tmp/bighat_relay_files`). `/tmp` is wiped on redeploy, which only means open QR links die early. Point it at a mounted volume if you want links to survive redeploys.
2. **Request body size.** The PC uploads up to `RELAY_MAX_FILE_MB` (default 150 MB). Make sure the proxy/ingress in front of the service allows bodies that large (many default to 1 to 10 MB) and does not time out a ~1 minute upload.
3. **Real client IP.** Phone rate limiting uses `X-Forwarded-For`. Make sure your proxy sets it, otherwise all guests look like one phone and share the 20-second cooldown.
4. **MongoDB collections created automatically:** `relay_files`, `relay_sessions`, `relay_requests`. No migration.
5. **Cleanup** happens on each upload and each new night (expired files and nights are deleted). If you want it on a timer too, add a cron that calls the purge; not required.

## Settings (all optional environment variables)
`RELAY_FILE_TTL_HOURS` (48) | `RELAY_MAX_FILE_MB` (150) | `RELAY_MAX_FILES_PER_LICENSE` (20) | `RELAY_SESSION_TTL_HOURS` (14) | `RELAY_MAX_REQUESTS_PER_SESSION` (300) | `RELAY_MAX_SESSIONS_PER_LICENSE` (5) | `RELAY_PHONE_COOLDOWN_SECONDS` (20) | `RELAY_FILES_DIR`

## Quick check after deploying
1. `GET https://api.bighat.live/d/aaaaaaaaaaaaaaaaaaaaaa` should return a small "link has expired" page (404), not a server error.
2. In the desktop program (alpha.82), start a Karaoke night, scan the QR with a phone on mobile data (not the venue Wi-Fi), send a song, and watch it appear in the host's request list within a few seconds.
3. Export a Scoreboard PNG, click the QR button, scan it on mobile data: the image should open.

## What the relay stores
A singer's first name and song title for the length of the night, and exported files for 48 hours. No logins, passwords, emails or payment data. Phones are identified only by a one-way hash of IP + night id (for the cooldown).

## Not included yet (planned)
- Rewards sign-up QR for Trivia and Bingo (waiting for the Rewards app README).
- Bingo player-join QR still uses the PC address (unchanged).
