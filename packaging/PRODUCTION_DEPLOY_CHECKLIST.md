# BIG Hat Entertainment — Production Cloud Deploy Checklist

> **TL;DR — if Squarespace buyers aren't receiving license-key emails,
> 95% of the time `BIGHAT_CLOUD_MODE` is unset on `api.bighat.live`.**

This doc is the single source of truth for what `api.bighat.live` needs
configured to run as the cloud licensing authority. The same codebase
runs in two modes:

| Mode                  | Env flag                  | Purpose                                       |
|-----------------------|---------------------------|-----------------------------------------------|
| **Desktop installer** | `BIGHAT_NATIVE_MODE=1`    | Customer's machine; offline-first MontyDB/SQLite |
| **Cloud authority**   | `BIGHAT_CLOUD_MODE=1`     | `api.bighat.live`; mints + emails license keys |

The two MUST NOT both be set. If `BIGHAT_NATIVE_MODE=1` is on, the
`/api/license/*` and `/api/squarespace/webhook` routes are **not
registered at all** and every customer purchase silently fails.

---

## 1. Validate prod state in <30 seconds (no shell required)

```bash
curl -s https://api.bighat.live/api/license/health | jq
```

Expected when the pipeline is healthy:

```json
{
  "ok": true,
  "ready": true,
  "blockers": [],
  "modes": {"cloud_mode_enabled": true, "native_mode_enabled": false},
  "integrations": {
    "resend_configured": true,
    "resend_api_key_prefix": "re_j***",
    "squarespace_webhook_secret_configured": true
  },
  "routing": {"license_routes_mounted": true, ...}
}
```

If `ready: false`, the `blockers` array spells out exactly which env
var to set.

---

## 2. Required env vars on `api.bighat.live`

Set these on the Emergent Kubernetes pod (Profile → Deployments →
Environment Variables):

### Mode gate (mandatory)

```
BIGHAT_CLOUD_MODE=1
# DO NOT set BIGHAT_NATIVE_MODE on the cloud pod.
```

### Webhook signature verification (mandatory in prod)

```
SQUARESPACE_WEBHOOK_SECRET=<from Squarespace admin → Settings → Developer Tools → Webhooks>
```

Without this, the webhook endpoint will accept unsigned requests
(dev-only behaviour) and log a loud warning at every POST.

### Resend (mandatory — license emails)

```
RESEND_API_KEY=re_<your-prod-key>
SENDER_EMAIL=info@bighat.live          # default; must be a verified Resend domain
SUPPORT_EMAIL=support@bighat.live      # shown in the license email footer
```

The Resend domain `bighat.live` must be verified in your Resend
dashboard (Resend → Domains → bighat.live → SPF + DKIM green).

### License admin auth (mandatory)

```
JWT_SECRET=<256-bit hex; shared with webapp auth>
ADMIN_EMAIL=sellards@bighat.live
ADMIN_PASSWORD=<strong; rotate every 90 days>
```

### SKU mapping (optional — defaults match Squarespace setup)

```
LICENSE_SKU_STANDALONE=BHE-STANDALONE
LICENSE_SKU_CLOUD_LIBRARY=BHE-CLOUD-LIBRARY
LICENSE_SKU_MUSIC_BINGO=BHE-MUSIC-BINGO
LICENSE_SKU_KARAOKE=BHE-KARAOKE
```

### Branding + download URLs (optional)

```
BRAND_BASE_URL=https://bighat.live
LICENSE_API_BASE_URL=https://api.bighat.live
GITHUB_OWNER=<your-github-org>          # used by /api/downloads/auto resolver
GITHUB_REPO=<your-repo-name>
CURRENT_RELEASE_VERSION=32.0.0          # override; auto-detected from GitHub if unset
```

### MongoDB (mandatory)

```
MONGO_URL=mongodb+srv://...             # set by Emergent; do not touch
DB_NAME=test_database                   # set by Emergent; do not touch
```

---

## 3. Squarespace dashboard configuration

In Squarespace admin:

1. **Settings → Developer Tools → Webhook Subscriptions**
   - Create subscription with these topics:
     `order.create`, `order.update`, `extensions.order.update`,
     `subscription.cancel`
   - Endpoint URL: `https://api.bighat.live/api/squarespace/webhook`
   - Copy the displayed **secret** into `SQUARESPACE_WEBHOOK_SECRET`.

2. **Products → Edit each product → Stock & Variants → SKU**
   - `BIG Hat Entertainment` (base, $49.99 one-time) → SKU `BHE-STANDALONE`
   - `Music Bingo Add-on` ($24.99 one-time) → SKU `BHE-MUSIC-BINGO`
   - `Karaoke Add-on` ($24.99 one-time) → SKU `BHE-KARAOKE`
   - `Cloud Library` ($5/mo subscription) → SKU `BHE-CLOUD-LIBRARY`

   SKU strings must match exactly. Override via the `LICENSE_SKU_*` env
   vars above if you need different strings.

3. **Commerce → Email Notifications → Order Confirmation**
   - Squarespace's own confirmation email does NOT contain the license
     key. The Resend email from `api.bighat.live` arrives in parallel
     (usually within 30 seconds of purchase). Consider adding "Your
     license key arrives in a separate email — check spam if you don't
     see it within 5 minutes" to your Squarespace confirmation template.

---

## 4. Post-deploy smoke test

After flipping `BIGHAT_CLOUD_MODE=1` and redeploying, run:

```bash
# 1. Health check — must show ready: true
curl -s https://api.bighat.live/api/license/health | jq .ready
# → true

# 2. Activate endpoint must accept POST (was returning 405 when broken)
curl -s -o /dev/null -w "%{http_code}\n" -X POST \
  https://api.bighat.live/api/license/activate \
  -H "Content-Type: application/json" -d '{}'
# → 422 (validation rejects empty body — route IS mounted)

# 3. Webhook endpoint must accept POST
curl -s -o /dev/null -w "%{http_code}\n" -X POST \
  https://api.bighat.live/api/squarespace/webhook \
  -H "Content-Type: application/json" -d '{}'
# → 401 (rejected unsigned in prod with SQUARESPACE_WEBHOOK_SECRET set)

# 4. Manual mint via admin → confirms Resend works
TOKEN=$(curl -s -X POST https://api.bighat.live/api/license/admin/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@bighat.live","password":"<your-admin-pwd>"}' \
  | jq -r .access_token)
curl -s -X POST https://api.bighat.live/api/license/admin/keys/mint \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"email":"you@yourdomain.com","owns_standalone":true,"cloud_library_months":0,"note":"smoke test"}'
# Check your inbox — license key email should arrive within 30 seconds.
```

---

## 5. Common failure modes

| Symptom on prod                                  | Root cause                          | Fix                                    |
|--------------------------------------------------|-------------------------------------|----------------------------------------|
| `POST /api/license/activate → 405`               | `BIGHAT_CLOUD_MODE` unset           | Set to `1` and redeploy                |
| `/api/license/health → ready:false`              | Read `blockers` array               | Set each missing env var               |
| Customer didn't get email; admin sees minted key | `RESEND_API_KEY` unset OR domain unverified | Verify Resend domain, set key  |
| `/api/squarespace/webhook → 401` from real Squarespace | Wrong webhook secret              | Re-copy from Squarespace dashboard     |
| `/api/license/health` shows `native_mode_enabled: true` | Wrong env file mounted             | Unset `BIGHAT_NATIVE_MODE` on cloud pod|

---

## 6. Troubleshooting the live pipeline

Backend logs at startup print a single banner:

```
======================================================================
CLOUD LICENSING SERVICE: ONLINE
  Routes:               /api/license/* + /api/squarespace/webhook
  Resend (emails):      ENABLED
  Webhook signature:    SET
  Sender:               info@bighat.live
  ...
======================================================================
```

If you see `CLOUD LICENSING SERVICE: OFFLINE` instead, `BIGHAT_CLOUD_MODE`
is not `1`.

Per-purchase telemetry: every webhook POST logs:

```
[webhook] received topic=order.create event_id=evt_...
[license] minted standalone key for buyer@example.com
sent email id=<resend-id> to=buyer@example.com subject='Your BIG Hat Entertainment license'
```

If the third line is missing, `RESEND_API_KEY` is unset OR the Resend
domain is not verified.
