# Squarespace Delivery — Quickstart (Option B: Digital Products)

This is the short, click-by-click guide for **attaching the installers
directly to the product** in Squarespace Commerce. No hidden `/download`
page. No buttons. No file blocks.

When a customer pays, Squarespace **automatically** emails them a download
link for every file attached to the product. Your separate license-key
email (sent from `api.bighat.live` via Resend) is delivered in parallel.

---

## What you have on disk right now

```
/app/dist/BIGHatStandalone-Setup-31.0.0.exe                       (34 MB)  ← Windows
/app/dist/BIGHatEntertainment-31.0.0-macOS-AppleSilicon.zip       (60 MB)  ← M1/M2/M3 Mac
/app/dist/BIGHatEntertainment-31.0.0-macOS-Intel.zip              (61 MB)  ← Intel Mac
```

All three are well under the 300 MB Squarespace limit.

> If Squarespace's UI ever blocks the `.exe`, a pre-zipped fallback is at
> `/app/frontend/public/downloads/BIGHatEntertainment-31.0.0-Windows.zip`
> (34 MB). Upload the `.zip` instead. **Note:** Squarespace Commerce
> Digital Products *does* accept `.exe` — only the generic Page → Button
> → File upload rejects it. Make sure you are inside
> `Commerce → Products → Digital`, not editing a button.

---

## Step-by-step (≈ 4 minutes)

### 1. Open the product
- Squarespace admin → **Commerce** → **Products**
- Click your existing **BIG Hat Entertainment** product (or **+ Add Product → Digital** if it doesn't exist yet)

### 2. Set the basics
- Name: `BIG Hat Entertainment`
- Price: `$49.99`
- **SKU: `BHE-STANDALONE`** ← must match exactly. The license server
  reads this SKU off the webhook to know which key to mint.

### 3. Attach the files
Inside the product editor, find the **Digital Files** section
(sometimes labelled **Downloadable Files** depending on Squarespace's
current UI).

- Click **Upload File** → choose `BIGHatStandalone-Setup-31.0.0.exe`
- Click **Upload File** → choose `BIGHatEntertainment-31.0.0-macOS-AppleSilicon.zip`
- Click **Upload File** → choose `BIGHatEntertainment-31.0.0-macOS-Intel.zip`

You'll see all three listed. Squarespace will send a single email after
purchase containing **one download link per file**, each link signed and
time-limited.

### 4. Description (recommended)
Paste this so customers know what to download:

```
Includes installers for Windows and macOS (both Apple Silicon and Intel).
Download the file that matches your computer.

After purchase you will receive TWO emails:
  1. From Squarespace — your download links.
  2. From info@bighat.live — your license key (BHE-XXXX-XXXX-XXXX-XXXX).

Paste the key into the Setup Wizard the first time you open the app.
Need help? Email support@bighat.live.
```

### 5. Save & publish

That's it. No `/download` page. No unlinked navigation. No button hacks.

---

## Repeat for the add-on products

For **Music Bingo** (`BHE-MUSIC-BINGO`) and **Karaoke** (`BHE-KARAOKE`):
- Follow the same steps **but skip the file upload entirely**.
- These products deliver value purely through the license key — they
  unlock features inside the already-installed app. Squarespace will
  send a tiny "thanks for your order" email; the unlock email comes
  from your license server.
- Description should explicitly say: *"This is an add-on. You must
  already own BIG Hat Entertainment ($49.99) for it to do anything."*

---

## How a customer experiences this

```
1. bighat.live → "Buy" → checkout → pays $49.99
2. ~5 seconds later, two emails land:
     ✉  Squarespace:  "Download your files" → 3 links (Windows / Apple Silicon / Intel)
     ✉  info@bighat.live (Resend): "Your BIG Hat license key"  → BHE-XXXX-XXXX-XXXX-XXXX
3. Customer downloads the installer that matches their machine, runs it.
4. Setup Wizard pops up → paste the key + email → app activates → done.
```

---

## When you ship a new version

You only need to update the files inside the Squarespace product:

1. Run the build pipeline: `python /app/scripts/build_installer.py` and
   `python /app/scripts/build_dmg.py` → fresh files appear in `/app/dist/`.
2. Squarespace admin → **Commerce → Products → BIG Hat Entertainment**
3. **Remove** the old files, **Upload File** for the new ones.
4. Bump `CURRENT_RELEASE_VERSION` env var on the `api.bighat.live` deploy
   so existing customers see the in-app update prompt.

The license keys on existing customer machines keep working — keys are
not tied to a specific build.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Squarespace says ".exe is not a supported file type." | You're editing a **button / file block**, not a Digital Product. Open the product from `Commerce → Products` and look for the **Digital Files** field. |
| Customer says they didn't get a download email. | Check the order in `Commerce → Orders`. There's a "Resend Receipt" / "Resend Download Link" action. |
| Customer got the download email but no license key email. | Check the `api.bighat.live` deployment logs for `[license] minted standalone key for <email>` — if it's missing, the webhook didn't fire. Verify Settings → Developer → Webhook Subscriptions. |
| Customer says the file is corrupted. | They probably double-clicked while the download was still in progress. Have them clear and re-download — Squarespace links stay valid for 24 hours and 5 attempts. |
| The `.zip` Mac file won't unzip. | macOS Gatekeeper sometimes flags unsigned `.app` bundles. Tell the customer to right-click → Open the first time, or run `xattr -dr com.apple.quarantine /path/to/BIGHat.app`. (Long-term fix: code-sign + notarize the `.app`.) |

---

## Why this is better than the old `/download` page approach

- **No bypass risk.** Squarespace's Digital Product links are signed and
  customer-specific. A non-paying visitor can't guess them.
- **No navigation pollution.** No hidden page floating in your site map.
- **No button hacks.** The download link arrives in the customer's
  inbox automatically — they never even touch your site after checkout.
- **Built-in resend.** If a customer loses the email, you can resend
  the download link from the Order page in two clicks.
