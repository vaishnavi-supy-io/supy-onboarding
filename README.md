# supy-onboarding

Customer onboarding form for Supy — collects company setup, branch configuration, contacts, and file uploads. On submission it fans out to HubSpot, Slack, Gmail, and Google Sheets automatically.

---

## Architecture

```
User fills index.html
        │
        ├─ File selected ──→ POST /upload (CF Worker)
        │                         │
        │                    Cloudinary raw/upload
        │                    returns /download?key=...&name=... URL
        │
        ├─ Save draft ─────→ POST /draft/save (CF Worker → KV DRAFTS)
        │                         returns { key, draft_url }
        │
        ├─ Load draft ─────→ GET  /draft/load?key=... (CF Worker → KV DRAFTS)
        │
        └─ Submit ──────────→ POST /webhook (CF Worker)
                                      │
                         ┌────────────┼──────────────┬──────────────┐
                         ▼            ▼              ▼              ▼
                    HubSpot        Slack           Gmail        Google Sheets
               (contact upsert  (blocks msg    (internal +      (append row
                + HTML note      + file btns    customer         via Apps
                + associations)  + HS button)   confirmation)    Script)
```

---

## Features

### Form & Submission
- Multi-branch configuration — dynamic branch rows (name, address, cost center, hours)
- Multi-file upload per field — multiple invoices and supplier files supported
- Submit guard — prevents submission while files are still uploading
- POS system and accounting software are strictly required fields

### Draft Save & Shareable Link
- **Auto-save** — form progress saved to Cloudflare KV on every change
- **Shareable draft URL** — clicking "Save & Share Link" generates a unique URL the CSM can send back to the customer to resume where they left off
- Draft key stored in the URL as `?draft=<key>`, loaded automatically on page open
- Drafts expire after 30 days
- Endpoint: `POST /draft/save` → returns `{ key, draft_url }` | `GET /draft/load?key=`

### File Upload & Download
- Files uploaded to **Cloudinary** via `raw/upload` — all file types (PDF, ZIP, XLSX, etc.) stored in the raw bucket with no auto-classification
- Each file gets a stable worker download URL: `/download?key=...&name=...`
- Download handler has a **4-method fallback chain** (see below)
- Max file size: 50 MB
- Files stored under: `supy-onboarding/{date}_{slug}/{uid}_{filename_no_ext}`
- Extension stripped from Cloudinary `public_id` to avoid CDN blocking of `.zip`/`.exe` — original filename preserved in the `?name=` parameter

#### Download fallback chain

The `/download` endpoint tries four methods in order:

| # | Method | Works for |
|---|---|---|
| 1 | Signed CDN URL via `raw/upload` | Excel, plain files — public raw uploads (most files) |
| 2 | Signed CDN URL via `image/upload` | Legacy files auto-classified as image type |
| 3 | Private API `raw/download` | Raw files converted to `type=private` (e.g. ZIPs) |
| 4 | Private API `image/download` + `format` | PDFs stored as `resource_type=image, type=private` |

### HubSpot Integration
- **Contact upsert** — searches by email; updates if found, creates if not; handles 409 duplicates
- **HTML note** — rich formatted note with all form data: company, champion, finance POC, IT contact, branches table, operations, food cost, goals, file download links
- **Auto-associations** — note linked to contact, deal (by company name), and company; company created in HubSpot if it doesn't exist
- Phone number validated before sending (must start with `+`)
- `champion_middle_name` stored as a custom HubSpot property

### Slack Notifications
- **Main channel** — rich blocks message on every submission: company, champion, branches, go-live date, POS, accounting, HubSpot button, file download buttons
- **Test channel** — separate webhook fires only when `champion_email === vaishnavi@supy.io`, labelled "🧪 Test Submission" (requires `SLACK_TEST_WEBHOOK_URL` secret)
- Up to 5 file buttons per message (📎 Invoice, 📋 Supplier)

### Email — Internal Notification
- Full HTML summary email sent to `vaishnavi@supy.io`, `randhir@supy.io`, `kenneth@supy.io` on every submission
- Same content as the HubSpot note

### Email — Customer Confirmation
- Sent to the customer's email after successful submission (only when HubSpot contact was recognised, to prevent relay abuse)
- Branded Supy email with the full submission summary
- `Reply-To: csms@supy.io` — customer replies land directly in the CSM inbox with full context
- Includes a prompt: "Need to make a change? Reply to this email"

### Google Sheets Logging
- Appends a row on every submission via Google Apps Script
- Deduplication logic in the Apps Script — updates existing row if same email submitted again
- Draft reminder emails sent from Apps Script for incomplete submissions

### Logs
- `GET /logs` — shows last 200 submission lines from KV (email | company | timestamp | result codes)

---

## Routes

| Method | Path | Description |
|---|---|---|
| `POST` | `/webhook` | Main form submission — triggers HubSpot, Slack, Gmail, Sheets |
| `POST` | `/upload` | Receive file, store to Cloudinary, return download URL |
| `GET` | `/download` | Proxy file download from Cloudinary (4-method fallback chain) |
| `POST` | `/draft/save` | Save form state to KV, return `{ key, draft_url }` |
| `GET` | `/draft/load` | Load form state from KV by key |
| `GET` | `/logs` | View last 200 submission log lines from KV |
| `GET` | `/cloudinary-audit` | List all Cloudinary resources by type/storage — debugging tool |
| `POST` | `/cloudinary-batch-fix` | Bulk-convert `image/upload` files to `type=private` (paginated) |
| `GET` | `/debug` | Check all secrets are set + Cloudinary connectivity |
| `GET` | `/` | Health check |

---

## Setup

### 1 — Deploy the Worker

```bash
cd worker
npm install
npx wrangler deploy
```

### 2 — Set secrets

```bash
npx wrangler secret put CLIENT_ID            # HubSpot OAuth client ID
npx wrangler secret put CLIENT_SECRET        # HubSpot OAuth client secret
npx wrangler secret put REFRESH_TOKEN        # HubSpot OAuth refresh token
npx wrangler secret put GMAIL_CLIENT_ID
npx wrangler secret put GMAIL_CLIENT_SECRET
npx wrangler secret put GMAIL_REFRESH_TOKEN
npx wrangler secret put SLACK_WEBHOOK_URL    # Main Slack channel webhook
npx wrangler secret put SLACK_TEST_WEBHOOK_URL  # Test channel (optional)
npx wrangler secret put GOOGLE_SCRIPT_URL    # Google Apps Script web app URL
npx wrangler secret put CLOUDINARY_CLOUD_NAME   # e.g. dnrhbyluy
npx wrangler secret put CLOUDINARY_API_KEY
npx wrangler secret put CLOUDINARY_API_SECRET
```

### 3 — Serve `index.html`

Host `index.html` on any static host (Cloudflare Pages, GitHub Pages, etc.) or open locally. The `WORKER_BASE` variable at the top of the `<script>` block points to the Worker URL.

---

## Project Structure

```
supy-onboarding/
├── index.html                  # Onboarding form (single-file frontend)
├── app.py                      # Flask backend (PythonAnywhere — legacy / backup)
├── requirements.txt            # Flask dependencies
├── google-apps-script/
│   └── Code.gs                 # Sheets logging, row upsert, draft reminder emails
└── worker/
    ├── wrangler.toml           # CF Worker config + KV bindings
    └── src/
        └── index.js            # CF Worker — all routes (~987 lines)
```

---

## Integrations

| Service | What it does |
|---|---|
| **HubSpot** | Upserts contact, creates rich HTML note, links to deal + company |
| **Slack** | Posts blocks message with file download buttons and HubSpot link |
| **Gmail** | Internal notification + customer confirmation with `Reply-To: csms@supy.io` |
| **Google Sheets** | Row append/upsert via Apps Script; draft reminder emails |
| **Cloudinary** | Stores all files via `raw/upload`; served via `/download` endpoint |
| **Cloudflare KV** | Draft form sessions (binding: `DRAFTS`), submission logs (binding: `LOGS`) |

---

## Environment Variables

| Variable | Description |
|---|---|
| `CLIENT_ID` | HubSpot OAuth client ID |
| `CLIENT_SECRET` | HubSpot OAuth client secret |
| `REFRESH_TOKEN` | HubSpot OAuth refresh token |
| `GMAIL_CLIENT_ID` | Gmail OAuth client ID |
| `GMAIL_CLIENT_SECRET` | Gmail OAuth client secret |
| `GMAIL_REFRESH_TOKEN` | Gmail OAuth refresh token |
| `SLACK_WEBHOOK_URL` | Slack incoming webhook — main onboarding channel |
| `SLACK_TEST_WEBHOOK_URL` | Slack incoming webhook — test channel (optional) |
| `GOOGLE_SCRIPT_URL` | Google Apps Script web app URL |
| `CLOUDINARY_CLOUD_NAME` | Cloudinary cloud name (e.g. `dnrhbyluy`) |
| `CLOUDINARY_API_KEY` | Cloudinary API key |
| `CLOUDINARY_API_SECRET` | Cloudinary API secret |

---

## Incident Log — File Download Issues (June 2026)

### What was broken and why

#### 1. PDFs uploaded via `auto/upload` → downloads broken

**Root cause:** The worker was calling `auto/upload`, which lets Cloudinary decide the resource type. Cloudinary classified PDFs as `resource_type=image`. The download handler only knew how to serve `raw` resources, so it fetched the wrong URL format and returned `ERR_INVALID_RESPONSE`.

**Fix:** Changed upload endpoint from `auto/upload` → `raw/upload`. Every file now lands in the `raw` bucket unconditionally, regardless of content type.

#### 2. ZIP files blocked by Cloudinary CDN ("Untrusted File Access")

**Root cause:** Cloudinary's CDN blocks delivery of files with `.zip`, `.exe`, and other "untrusted" extensions by default, regardless of whether they're uploaded correctly.

**Fix:** File extension stripped from the Cloudinary `public_id` on upload — the original filename is preserved in the `/download?name=` parameter. Affected ZIP files were also converted to `type=private` so they use the authenticated `raw/download` API instead of CDN.

#### 3. Worker crashing on every download — Error 1101

**Root cause:** A bug in the download fallback code. When all download methods failed, the code created a plain JS object `{ status: 404, body: "..." }` and then called `.headers.get()` on it — but plain objects don't have a `.headers` property. This threw a TypeError that crashed the entire Worker on every request.

**Fix:** Replaced the broken fallback with `return json({ error: "File not found" }, 404)`.

#### 4. 100 existing PDFs permanently broken (Capon Ltd)

**Root cause:** All Capon Ltd PDFs were uploaded before the `raw/upload` fix. They were sitting in Cloudinary as `resource_type=image, type=upload`. The `image/download` API only works for `type=private` resources — so every file was permanently undownloadable.

**Fix:** Built `/cloudinary-batch-fix` endpoint that bulk-converted all 100 files from `type=upload` → `type=private` using Cloudinary's rename API. Ran in 4 paginated batches of 45 (Cloudflare Workers cap at 50 subrequests per invocation).

#### 5. No resilience in download handler — one method, no fallbacks

**Root cause:** The original download handler only tried a single CDN URL path. If a file was stored differently (image type, private type) it failed immediately with no recovery.

**Fix:** Rewrote the download handler with a 4-method fallback chain covering all valid Cloudinary storage configurations.

### Summary

| Problem | Root Cause | Fix |
|---|---|---|
| PDFs giving ERR_INVALID_RESPONSE | `auto/upload` stored them as `resource_type=image` | Changed to `raw/upload` for all new uploads |
| ZIPs blocked by CDN | Cloudinary blocks `.zip` extension on CDN delivery | Strip extension from `public_id`; convert to `type=private` |
| All downloads crashing (Error 1101) | `.headers.get()` called on a plain JS object | Replaced with proper `json()` 404 response |
| 100 Capon Ltd PDFs broken | Legacy files stuck as `image/upload` | Batch-converted all 100 to `type=private` |
| No resilience to storage type variations | Single download path | 4-method fallback chain covers all cases |

**Going forward:** Every new upload goes through `raw/upload` → consistent storage type → first CDN path always works → no broken links.
