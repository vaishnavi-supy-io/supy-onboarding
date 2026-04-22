# supy-onboarding

Customer onboarding form for Supy — collects company setup, branch configuration, contacts, and file uploads. On submission it fans out to HubSpot, Slack, Gmail, and Google Sheets automatically.

## Architecture

```
User fills index.html
        │
        ├─ File selected ──→ POST /upload (CF Worker)
        │                         │
        │                    R2 Bucket (supy-onboarding-uploads)
        │                    returns download URL
        │
        └─ Submit ──→ POST /webhook (CF Worker  or  Flask/PythonAnywhere)
                              │
                 ┌────────────┼────────────┬──────────────┐
                 ▼            ▼            ▼              ▼
            HubSpot        Slack        Gmail        Google Sheets
         (contact +       (blocks     (summary      (append row)
          note +          message +    email)
          file links)     file btns)
```

Two deployable backends exist — use whichever is active:

| Backend | Path | URL |
|---|---|---|
| Cloudflare Worker | `worker/` | `https://supy-onboarding.vaishnavi-5d1.workers.dev` |
| Flask (PythonAnywhere) | `app.py` | configured in `index.html` as `RENDER_URL` |

## File Upload Flow

1. User clicks **Choose file** → browser calls `POST /upload` on the CF Worker
2. Worker stores the file in **Cloudflare R2** under `submissions/{date}_{company}/{uid}_{filename}`
3. Worker returns a download URL (`/files/{key}`)
4. URL is stored in a hidden form field (`invoices_link` / `suppliers_link`)
5. On form submit, those URLs land in:
   - **HubSpot note** — clickable ⬇ Download links on the contact record
   - **Slack notification** — 📎 Invoices / 📋 Suppliers buttons in the message

CSMs never need to leave HubSpot or Slack to access uploaded files.

## Setup

### 1 — Create the R2 bucket (one-time)
```bash
cd worker
npx wrangler r2 bucket create supy-onboarding-uploads
```

### 2 — Deploy the Worker
```bash
cd worker
npm install
npx wrangler deploy
```

### 3 — Set secrets
```bash
npx wrangler secret put CLIENT_ID
npx wrangler secret put CLIENT_SECRET
npx wrangler secret put REFRESH_TOKEN
npx wrangler secret put GMAIL_CLIENT_ID
npx wrangler secret put GMAIL_CLIENT_SECRET
npx wrangler secret put GMAIL_REFRESH_TOKEN
npx wrangler secret put SLACK_WEBHOOK_URL
npx wrangler secret put GOOGLE_SCRIPT_URL
```

### 4 — Serve `index.html`
Host `index.html` on any static host (Cloudflare Pages, S3, etc.) or open locally. The `RENDER_URL` and `WORKER_BASE` variables at the top of the `<script>` block point to the Worker.

## Project Structure

```
supy-onboarding/
├── index.html          # Onboarding form (single-file frontend)
├── app.py              # Flask backend (PythonAnywhere — legacy / backup)
├── requirements.txt    # Flask dependencies
└── worker/
    ├── wrangler.toml   # CF Worker + R2 bucket config
    └── src/
        └── index.js    # CF Worker (webhook + upload + file-serve)
```

## Integrations

| Service | What it does |
|---|---|
| **HubSpot** | Upserts contact, creates HTML note, links to deal + company |
| **Slack** | Posts blocks message with HubSpot button + file download buttons |
| **Gmail** | Sends summary email to the CSM team |
| **Google Sheets** | Appends a row via Apps Script for lightweight tracking |
| **Cloudflare R2** | Stores uploaded files; Worker serves them on `/files/{key}` |

## Environment Variables

| Variable | Description |
|---|---|
| `CLIENT_ID` | HubSpot OAuth client ID |
| `CLIENT_SECRET` | HubSpot OAuth client secret |
| `REFRESH_TOKEN` | HubSpot OAuth refresh token |
| `GMAIL_CLIENT_ID` | Gmail OAuth client ID |
| `GMAIL_CLIENT_SECRET` | Gmail OAuth client secret |
| `GMAIL_REFRESH_TOKEN` | Gmail OAuth refresh token |
| `SLACK_WEBHOOK_URL` | Slack incoming webhook URL |
| `GOOGLE_SCRIPT_URL` | Google Apps Script web app URL |
