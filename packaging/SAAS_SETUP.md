# BIG Hat Standalone — Cloud Licensing & Squarespace Setup

This guide walks you through turning the **Phase 10.0 license server** into a
production SaaS storefront on **bighat.live** (Squarespace) + **api.bighat.live**
(license authority deployed on Emergent).

## Architecture recap

```
   bighat.live  (Squarespace)                 api.bighat.live  (Emergent deploy)
   ┌──────────────────────┐                  ┌──────────────────────────────┐
   │ Marketing pages      │                  │ FastAPI license server       │
   │ Pricing & checkout   │                  │  - mint license keys         │
   │ Customer accounts    │   webhooks  →    │  - email keys via Resend     │
   │ Digital downloads    │                  │  - activate / validate keys  │
   │ Subscriptions        │                  │  - admin dashboard           │
   └──────────────────────┘                  └──────────────────────────────┘
                                                    ↑
                                                    │ HTTPS
                                                    │
                                       ┌────────────┴────────────┐
                                       │ Desktop app (Win/macOS) │
                                       │ on customer's machine   │
                                       └─────────────────────────┘
```

## ⚠️ Security: API keys & secrets

**Never commit, ship, or paste the following into the desktop installer or
any client-facing artifact:**
- `SQUARESPACE_API_KEY` / `SQUARESPACE_WEBHOOK_SECRET`
- `RESEND_API_KEY`
- `JWT_SECRET` / `LICENSE_ADMIN_SECRET`
- `ADMIN_PASSWORD`
- Any `AZURE_*` / `ROUNDMAKER_*` OAuth client secrets

These keys live ONLY in:
1. **`/app/backend/.env`** on the dev box (git-ignored, never committed).
2. **The Emergent deployment env vars dashboard** for `api.bighat.live`.

The build pipeline (`scripts/build_installer.py` and `scripts/build_dmg.py`)
explicitly **strips every `.env*` file** from the installer payload and
ships `packaging/.env.standalone` (a desktop-safe template — no secrets,
just `BIGHAT_NATIVE_MODE=1` and similar) in its place. On first run, the
launcher copies it to `backend/.env` and substitutes a unique per-install
`JWT_SECRET`. Regression test: `test_phase10_1_no_secret_leakage.py`.

If you ever need to rotate a key:
1. Update `/app/backend/.env` (server side).
2. Update the matching env var on the Emergent deploy dashboard.
3. Restart the deploy.
4. **No installer rebuild required** — keys are not bundled into the desktop app.

## One-time setup (do these in order)

### 1. Sign up for Resend (5 minutes)

1. Visit <https://resend.com/signup>, free tier (3,000 emails/month — way more than you need).
2. Verify your sending domain (`bighat.live`):
   - Settings → Domains → Add Domain
   - Add the DNS records Resend gives you to your Squarespace DNS panel
     (Settings → Domains → Advanced → Custom Records)
   - Resend will verify automatically within ~10 minutes
3. Settings → API Keys → Create API Key (full access). Save the value.
4. The key already has a placeholder in `/app/backend/.env`:
   ```
   RESEND_API_KEY=re_…
   SENDER_EMAIL=info@bighat.live
   ```

### 2. Configure Squarespace products

You need TWO products on Squarespace.

#### Product A — BIG Hat Entertainment ($24.99 one-time)

Bundles the activation download for: the **Main Hub**, the **Trivia App**,
the **Schedule Tool**, the **Story Generator**, the **Scoreboard Tool**,
and the **Answer Sheets**.

1. **Squarespace admin → Commerce → Products → Add Product → Digital**
2. Fill in:
   - Name: `BIG Hat Entertainment`
   - Price: `$24.99`
   - **SKU: `BHE-STANDALONE-2499`**  ← MUST match exactly (or set
     `LICENSE_SKU_STANDALONE` env var on the license server to whatever you choose)
   - Upload the file:
     `dist/BIGHatStandalone-Setup-31.0.0.exe` (Windows) and
     `dist/BIGHatStandalone-31.0.0.dmg` (macOS) — Squarespace allows
     multiple files per digital product.
3. Description: include "License key delivered separately by email."

#### Product B — Cloud Library ($5/month)

1. **Squarespace admin → Commerce → Products → Add Product → Subscription**
   (requires Advanced Commerce plan)
2. Fill in:
   - Name: `BIG Hat Cloud Library`
   - Price: `$5/month`
   - Recurring: monthly
   - **SKU: `BHE-CLOUD-LIBRARY-5MO`**
   - Description: "Adds shared trivia library, Music Bingo catalog, and
     SharePoint sync to your BIG Hat Standalone install."

### 3. Configure the Squarespace webhook

1. **Squarespace admin → Settings → Developer → Webhook Subscriptions** →
   **Add Webhook Subscription**
2. URL: `https://api.bighat.live/api/squarespace/webhook`
3. Topics to subscribe (tick all):
   - `order.create`
   - `order.update`
   - `subscription.cancel`
4. Save → Squarespace shows you the **secret** for HMAC signing. Copy it.
5. Add to your `api.bighat.live` deployment env:
   ```
   SQUARESPACE_WEBHOOK_SECRET=<the secret you just copied>
   ```

### 4. (Optional) Squarespace API key for order enrichment

If you want the license server to fetch full order details (e.g. for
support lookups), you also need a Commerce API key:
1. Settings → Developer → API Keys → Create API Key
2. Permissions: Orders (Read) + Inventory (Read)
3. Save the key as `SQUARESPACE_API_KEY` env var.

## Deploy the license server

### 1. Deploy on Emergent platform

From the Emergent chat:
> Deploy this app to native deploy. It needs `BIGHAT_CLOUD_MODE=1`, not native mode.

Required env vars in the deployment dashboard:
| Variable | Value |
|----------|-------|
| `BIGHAT_CLOUD_MODE` | `1` |
| `BIGHAT_NATIVE_MODE` | `0` (or unset) |
| `MONGO_URL` | (provided by platform) |
| `DB_NAME` | `bighat_licenses` |
| `JWT_SECRET` | (random ≥32 chars; generate with `openssl rand -hex 32`) |
| `LICENSE_ADMIN_SECRET` | (same — random 32+ chars) |
| `ADMIN_EMAIL` | your-admin@bighat.live |
| `ADMIN_PASSWORD` | (bcrypt hash; `htpasswd -bnBC 12 "" 'yourpassword' \| tr -d ':\n'`) |
| `RESEND_API_KEY` | (from step 1) |
| `SENDER_EMAIL` | `info@bighat.live` |
| `SUPPORT_EMAIL` | `support@bighat.live` |
| `SQUARESPACE_WEBHOOK_SECRET` | (from step 3) |
| `SQUARESPACE_API_KEY` | (optional, from step 4) |
| `BRAND_BASE_URL` | `https://bighat.live` |
| `LICENSE_API_BASE_URL` | `https://api.bighat.live` |
| `DOWNLOAD_URL_WINDOWS` | (Squarespace digital download URL for the .exe) |
| `DOWNLOAD_URL_MACOS` | (Squarespace digital download URL for the .dmg) |
| `CURRENT_RELEASE_VERSION` | `31.0.0` |
| `LICENSE_SKU_STANDALONE` | `BHE-STANDALONE-2499` (override only if SKU differs) |
| `LICENSE_SKU_CLOUD_LIBRARY` | `BHE-CLOUD-LIBRARY-5MO` |

### 2. Point DNS

In Squarespace **Settings → Domains → bighat.live → Advanced → Custom Records**:
- Add a CNAME record: `api` → `<your-emergent-app>.preview.emergentagent.com`
- (Or a custom domain Emergent provides for native deploys.)

### 3. Smoke test

```bash
# Should respond "ok": false (key not found) — proves routing & cloud mode works
curl -X POST https://api.bighat.live/api/license/validate \
  -H "Content-Type: application/json" \
  -d '{"key":"BHE-FAKE-FAKE-FAKE-FAKE","hwid":"test"}'

# Should return your Windows download URL
curl https://api.bighat.live/api/downloads/windows
```

### 4. Test purchase end-to-end

1. Log in as a *different* customer (not your admin email).
2. Buy the Standalone product on bighat.live for $24.99.
3. Watch the license server logs:
   ```
   [license] minted standalone key for alice@example.com
   sent email id=… to=alice@example.com subject='Your BIG Hat Standalone license'
   ```
4. Check the inbox for the email with the BHE-XXXX-XXXX-XXXX-XXXX key.
5. Run the desktop installer, paste the key in the Setup Wizard.
6. Verify in admin dashboard:
   ```bash
   # Get an admin token
   curl -X POST https://api.bighat.live/api/license/admin/login \
     -H "Content-Type: application/json" \
     -d '{"email":"your-admin@bighat.live","password":"…"}'
   # List all license keys
   curl https://api.bighat.live/api/license/admin/keys \
     -H "Authorization: Bearer <token>"
   ```

## What the customer experiences

1. **Visits bighat.live** → sees the product page → clicks "Buy".
2. **Squarespace checkout** → enters card → pays $24.99.
3. **Squarespace post-purchase email** → "Thanks for your order. Download your files: BIGHatStandalone-Setup-31.0.0.exe / .dmg"
4. **A second email from you (via Resend)** → "Your BIG Hat Standalone license key: `BHE-XXXX-XXXX-XXXX-XXXX`. Paste it into the Setup Wizard."
5. **Customer runs the installer**, opens the app, sees the Setup Wizard.
6. **Customer pastes the key + their email** → app calls
   `POST https://api.bighat.live/api/license/activate` → server binds HWID,
   returns `owns_standalone=True, cloud_library_active=False`.
7. **App unlocks** all standalone features. Cloud-library-gated features
   (SharePoint sync, shared library) remain disabled until they buy the
   $5/mo subscription separately.
8. **App re-validates every 7 days online**. If offline, last-known status
   is honoured for 30 days, then the subscription tier degrades to "free".

## Operations

### Manually mint a comp / gift key
```bash
TOKEN=$(curl -s -X POST https://api.bighat.live/api/license/admin/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@…","password":"…"}' | jq -r .access_token)

curl -X POST https://api.bighat.live/api/license/admin/keys/mint \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"email":"vip@example.com","owns_standalone":true,"cloud_library_months":12,"note":"VIP comp"}'
```

### Revoke a key (chargeback / abuse)
```bash
curl -X POST "https://api.bighat.live/api/license/admin/keys/BHE-XXXX-XXXX-XXXX-XXXX/revoke?reason=chargeback" \
  -H "Authorization: Bearer $TOKEN"
```

### Help a customer move to a new computer
The desktop app has a built-in "Deactivate this machine" button under
**Settings → License**. If they can't access the old machine, they can
also call:
```bash
curl -X POST https://api.bighat.live/api/license/deactivate \
  -H "Content-Type: application/json" \
  -d '{"key":"BHE-XXXX…","hwid":"<old-hwid-from-support-email>"}'
```

## Future improvements (Phase 10.1 +)

- **Phase 10.1**: Wire the desktop app's existing Setup Wizard to call
  `https://api.bighat.live/api/license/activate` in production. The
  endpoints + payloads already line up — this is just config + a 7-day
  re-validation timer.
- **Phase 10.2**: Move installer hosting from Squarespace to S3+CloudFront
  with signed URLs (better analytics, no 300 MB Squarespace limit).
- **Phase 10.3**: Customer Portal — let customers self-serve "deactivate
  a seat", "view receipts", "cancel subscription", "redownload installer"
  directly on bighat.live (Squarespace Member Areas + a small React
  widget that talks to `/api/license/status/{key}`).
