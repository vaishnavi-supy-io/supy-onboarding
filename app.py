import os
import json
import requests
import logging
from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime, timezone

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)

# ── CONFIGURATION ───────────────────────────────────────────────
SPREADSHEET_ID  = os.environ.get("SPREADSHEET_ID", "1ZmPjLk2qWuIzIL5gKltXFVqvyYpPu5kYuw7-KrU6d58")
CLIENT_ID       = os.environ.get("CLIENT_ID",     "d5f491d5-9206-422b-97b1-e037b4f06c45")
CLIENT_SECRET   = os.environ.get("CLIENT_SECRET", "ce5b4a8c-3d53-4579-bbf6-783f9a149ab1")
REFRESH_TOKEN   = os.environ.get("REFRESH_TOKEN", "na1-ddcd-e6ae-4cf6-82b3-439b1efaa389")

# Gmail OAuth — set these as environment variables on PythonAnywhere
GMAIL_CLIENT_ID     = os.environ.get("GMAIL_CLIENT_ID", "")
GMAIL_CLIENT_SECRET = os.environ.get("GMAIL_CLIENT_SECRET", "")
GMAIL_REFRESH_TOKEN = os.environ.get("GMAIL_REFRESH_TOKEN", "")

# Slack Webhook URL — set as environment variable
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL", "")

# Google Sheets API key or service account JSON path — set as env var
GOOGLE_SERVICE_ACCOUNT_JSON = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")

# Email recipients
EMAIL_FROM       = "vaishnavi@supy.io"
EMAIL_RECIPIENTS = ["vaishnavi@supy.io", "randhir@supy.io", "kenneth@supy.io"]

# Submission log file
LOG_FILE = os.path.join(os.path.dirname(__file__), "submissions.log")

# ── LOGGING ─────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def log_submission(email, company, submitted_at, status):
    """Append a one-line record to submissions.log"""
    try:
        with open(LOG_FILE, "a") as f:
            f.write(f"{submitted_at} | {email} | {company} | {status}\n")
        logger.info(f"Logged submission: {email} | {company} | {status}")
    except Exception as e:
        logger.error(f"Log write error: {e}")

# ── GOOGLE SHEETS (via service account JSON env var) ────────────
def log_to_sheets(d, branches, submitted_at):
    """Appends form data as a new row in Google Sheets"""
    if not GOOGLE_SERVICE_ACCOUNT_JSON:
        logger.warning("[Sheets] GOOGLE_SERVICE_ACCOUNT_JSON not set — skipping.")
        return
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        sa_info = json.loads(GOOGLE_SERVICE_ACCOUNT_JSON)
        creds = service_account.Credentials.from_service_account_info(
            sa_info, scopes=["https://www.googleapis.com/auth/spreadsheets"]
        )
        service = build("sheets", "v4", credentials=creds)

        branch_text = " | ".join([
            f"{b.get('name','')} ({b.get('address','')}) CC:{b.get('cost_center','')} {b.get('open','')}-{b.get('close','')}"
            for b in branches
        ]) if branches else ""

        row = [
            submitted_at,
            d.get("company_name", ""),
            d.get("champion_name", ""), d.get("champion_title", ""), d.get("champion_email", ""), d.get("champion_phone", ""),
            d.get("accounting_external", ""),
            d.get("finance_name", ""), d.get("finance_title", ""), d.get("finance_email", ""), d.get("finance_phone", ""),
            d.get("it_same_as_champion", ""),
            d.get("it_name", ""), d.get("it_title", ""), d.get("it_email", ""), d.get("it_phone", ""),
            d.get("pos_system", ""), d.get("accounting_software", ""),
            branch_text, str(len(branches)),
            d.get("invoices_link", ""), d.get("suppliers_link", ""),
            d.get("ordering_method", ""), d.get("po_approver", ""), d.get("ordering_structure", ""),
            d.get("stock_counts", ""), d.get("stock_count_duration", ""), d.get("inventory_system", ""),
            d.get("food_cost_current", ""), d.get("food_cost_target", ""),
            d.get("cogs_method", ""), d.get("invoice_delivery", ""), d.get("finance_complications", ""),
            d.get("top_problem", ""), d.get("extra_notes", ""), d.get("blockers", ""), d.get("golive_date", "")
        ]

        result = service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID, range="Sheet1!A1:A2"
        ).execute()
        if not result.get("values"):
            headers = [
                "Submitted At", "Company Name",
                "Champion Name", "Champion Title", "Champion Email", "Champion Phone",
                "External Accounting?",
                "Finance Name", "Finance Title", "Finance Email", "Finance Phone",
                "IT Same as Champion?",
                "IT Name", "IT Title", "IT Email", "IT Phone",
                "POS System", "Accounting Software",
                "Branches Summary", "Branch Count",
                "Invoices Link", "Suppliers Link",
                "Ordering Method", "PO Approver", "Ordering Structure",
                "Stock Counts", "Stock Count Duration", "Inventory System",
                "Food Cost Current", "Food Cost Target",
                "COGS Method", "Invoice Delivery", "Finance Complications",
                "Top Problem", "Extra Notes", "Blockers", "Go-Live Date"
            ]
            service.spreadsheets().values().append(
                spreadsheetId=SPREADSHEET_ID, range="Sheet1!A1",
                valueInputOption="RAW", body={"values": [headers]}
            ).execute()

        service.spreadsheets().values().append(
            spreadsheetId=SPREADSHEET_ID, range="Sheet1!A1",
            valueInputOption="RAW", insertDataOption="INSERT_ROWS",
            body={"values": [row]}
        ).execute()
        logger.info("[Sheets] Row appended successfully.")
    except Exception as e:
        logger.error(f"[Sheets Error]: {e}")

# ── GMAIL (OAuth2 access token) ──────────────────────────────────
def get_gmail_access_token():
    if not GMAIL_REFRESH_TOKEN:
        return None
    r = requests.post("https://oauth2.googleapis.com/token", data={
        "grant_type": "refresh_token",
        "client_id": GMAIL_CLIENT_ID,
        "client_secret": GMAIL_CLIENT_SECRET,
        "refresh_token": GMAIL_REFRESH_TOKEN,
    })
    if r.status_code != 200:
        logger.error(f"[Gmail Token Error]: {r.text}")
        return None
    return r.json().get("access_token")

def send_email_notification(d, branches, submitted_at):
    """Send a rich HTML email to all recipients via Gmail API"""
    token = get_gmail_access_token()
    if not token:
        logger.warning("[Email] Gmail token unavailable — skipping email.")
        return

    company   = d.get("company_name", "Unknown Company")
    champ     = d.get("champion_name", "")
    champ_email = d.get("champion_email", "")

    # Build branch rows
    branch_rows_html = ""
    for i, b in enumerate(branches, 1):
        hours = f"{b.get('open','')}-{b.get('close','')}"
        branch_rows_html += f"""
        <tr>
          <td style="padding:8px 10px;border-bottom:1px solid #f0ebf8">{i}</td>
          <td style="padding:8px 10px;border-bottom:1px solid #f0ebf8"><b>{b.get('name','')}</b></td>
          <td style="padding:8px 10px;border-bottom:1px solid #f0ebf8">{b.get('address','')}</td>
          <td style="padding:8px 10px;border-bottom:1px solid #f0ebf8">{b.get('cost_center','')}</td>
          <td style="padding:8px 10px;border-bottom:1px solid #f0ebf8">{hours}</td>
        </tr>"""

    def row(label, val):
        if not val or not val.strip(): return ""
        return f'<tr><td style="padding:5px 10px;color:#666;font-size:12px;white-space:nowrap">{label}</td><td style="padding:5px 10px;font-size:12px;font-weight:600;color:#1a1a2e">{val}</td></tr>'

    html_body = f"""
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"/></head>
<body style="font-family:Inter,-apple-system,sans-serif;background:#f4f1fa;margin:0;padding:24px">
<div style="max-width:680px;margin:0 auto">

  <!-- Header -->
  <div style="background:linear-gradient(135deg,#1a0d33,#503390);border-radius:12px 12px 0 0;padding:24px 32px;text-align:center">
    <div style="display:inline-block;background:rgba(255,255,255,.1);border:1px solid rgba(255,255,255,.2);border-radius:20px;padding:4px 14px;font-size:10px;font-weight:700;letter-spacing:1px;text-transform:uppercase;color:rgba(255,255,255,.7);margin-bottom:12px">New Onboarding Submission</div>
    <h1 style="color:#fff;font-size:22px;margin:0 0 6px">🎉 {company}</h1>
    <p style="color:rgba(255,255,255,.65);font-size:12px;margin:0">Submitted on {submitted_at}</p>
  </div>

  <!-- Body -->
  <div style="background:#fff;padding:28px 32px;border-radius:0 0 12px 12px;box-shadow:0 4px 16px rgba(80,51,144,.1)">

    <!-- Internal Champion -->
    <h3 style="color:#321e57;font-size:13px;border-left:3px solid #503390;padding-left:10px;margin:0 0 10px">Internal Champion</h3>
    <table style="width:100%;border-collapse:collapse;margin-bottom:20px;background:#f9f7fe;border-radius:8px;overflow:hidden">
      {row("Name", d.get("champion_name",""))}
      {row("Title", d.get("champion_title",""))}
      {row("Email", champ_email)}
      {row("Phone", d.get("champion_phone",""))}
    </table>

    <!-- Finance POC -->
    <h3 style="color:#321e57;font-size:13px;border-left:3px solid #f59e0b;padding-left:10px;margin:0 0 10px">Finance POC</h3>
    <table style="width:100%;border-collapse:collapse;margin-bottom:20px;background:#fffbf0;border-radius:8px;overflow:hidden">
      {row("External Firm?", d.get("accounting_external",""))}
      {row("Name", d.get("finance_name",""))}
      {row("Title", d.get("finance_title",""))}
      {row("Email", d.get("finance_email",""))}
      {row("Phone", d.get("finance_phone",""))}
    </table>

    <!-- IT Contact -->
    <h3 style="color:#321e57;font-size:13px;border-left:3px solid #3b82f6;padding-left:10px;margin:0 0 10px">IT Contact</h3>
    <table style="width:100%;border-collapse:collapse;margin-bottom:20px;background:#f0f7ff;border-radius:8px;overflow:hidden">
      {row("Same as Champion?", d.get("it_same_as_champion",""))}
      {row("Name", d.get("it_name",""))}
      {row("Email", d.get("it_email",""))}
      {row("POS System", d.get("pos_system",""))}
      {row("Accounting SW", d.get("accounting_software",""))}
    </table>

    <!-- Branches -->
    <h3 style="color:#321e57;font-size:13px;border-left:3px solid #10b981;padding-left:10px;margin:0 0 10px">Branches ({len(branches)})</h3>
    <table style="width:100%;border-collapse:collapse;margin-bottom:20px;font-size:12px">
      <tr style="background:#321e57;color:#fff">
        <th style="padding:8px 10px;text-align:left">#</th>
        <th style="padding:8px 10px;text-align:left">Name</th>
        <th style="padding:8px 10px;text-align:left">Address</th>
        <th style="padding:8px 10px;text-align:left">Cost Center</th>
        <th style="padding:8px 10px;text-align:left">Hours</th>
      </tr>
      {branch_rows_html if branch_rows_html else '<tr><td colspan="5" style="padding:10px;color:#888;text-align:center">No branches</td></tr>'}
    </table>

    <!-- Operations -->
    <h3 style="color:#321e57;font-size:13px;border-left:3px solid #8b5cf6;padding-left:10px;margin:0 0 10px">Operations & Food Cost</h3>
    <table style="width:100%;border-collapse:collapse;margin-bottom:20px;background:#f9f7fe;border-radius:8px;overflow:hidden">
      {row("Order Method", d.get("ordering_method",""))}
      {row("PO Approver", d.get("po_approver",""))}
      {row("Ordering Structure", d.get("ordering_structure",""))}
      {row("Stock Counts", d.get("stock_counts",""))}
      {row("Inventory System", d.get("inventory_system",""))}
      {row("Current Food Cost %", d.get("food_cost_current",""))}
      {row("Target Food Cost %", d.get("food_cost_target",""))}
      {row("COGS Method", d.get("cogs_method",""))}
      {row("Invoice Delivery", d.get("invoice_delivery",""))}
    </table>

    <!-- Goals & Blockers -->
    <h3 style="color:#321e57;font-size:13px;border-left:3px solid #ef4444;padding-left:10px;margin:0 0 10px">Goals & Blockers</h3>
    <table style="width:100%;border-collapse:collapse;margin-bottom:20px;background:#fff5f5;border-radius:8px;overflow:hidden">
      {row("Top Problem", d.get("top_problem",""))}
      {row("CSM Notes", d.get("extra_notes",""))}
      {row("Blockers", d.get("blockers",""))}
      {row("Target Go-Live", d.get("golive_date",""))}
    </table>

    <!-- File Links -->
    <h3 style="color:#321e57;font-size:13px;border-left:3px solid #06b6d4;padding-left:10px;margin:0 0 10px">File Links</h3>
    <table style="width:100%;border-collapse:collapse;margin-bottom:20px;background:#f0fdff;border-radius:8px;overflow:hidden">
      {row("Invoices", d.get("invoices_link",""))}
      {row("Supplier Details", d.get("suppliers_link",""))}
    </table>

  </div>

  <p style="text-align:center;font-size:10px;color:#aaa;margin-top:16px">supy.io · Onboarding Automation</p>
</div>
</body>
</html>
"""

    import base64
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"[Supy Onboarding] New submission — {company} ({champ_email})"
    msg["From"]    = EMAIL_FROM
    msg["To"]      = ", ".join(EMAIL_RECIPIENTS)
    msg.attach(MIMEText(html_body, "html"))

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()

    send_r = requests.post(
        "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"raw": raw}
    )
    if send_r.status_code == 200:
        logger.info(f"[Email] Sent to {EMAIL_RECIPIENTS}")
    else:
        logger.error(f"[Email Error]: {send_r.text}")

# ── SLACK NOTIFICATION ───────────────────────────────────────────
def send_slack_notification(d, branches, submitted_at):
    if not SLACK_WEBHOOK_URL:
        logger.warning("[Slack] SLACK_WEBHOOK_URL not set — skipping.")
        return
    try:
        company   = d.get("company_name", "Unknown")
        champ     = d.get("champion_name", "—")
        email     = d.get("champion_email", "—")
        phone     = d.get("champion_phone", "—")
        golive    = d.get("golive_date", "—")
        n_branches = len(branches)

        payload = {
            "blocks": [
                {
                    "type": "header",
                    "text": {"type": "plain_text", "text": f"🎉 New Onboarding Submission", "emoji": True}
                },
                {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": f"*Company:*\n{company}"},
                        {"type": "mrkdwn", "text": f"*Submitted:*\n{submitted_at}"},
                        {"type": "mrkdwn", "text": f"*Champion:*\n{champ}"},
                        {"type": "mrkdwn", "text": f"*Email:*\n{email}"},
                        {"type": "mrkdwn", "text": f"*Phone:*\n{phone}"},
                        {"type": "mrkdwn", "text": f"*Branches:*\n{n_branches}"},
                        {"type": "mrkdwn", "text": f"*Target Go-Live:*\n{golive}"},
                        {"type": "mrkdwn", "text": f"*Order Method:*\n{d.get('ordering_method','—')}"},
                    ]
                },
                {
                    "type": "context",
                    "elements": [{"type": "mrkdwn", "text": "Supy Onboarding Form · supy.io"}]
                }
            ]
        }

        r = requests.post(SLACK_WEBHOOK_URL, json=payload)
        if r.status_code == 200:
            logger.info("[Slack] Notification sent.")
        else:
            logger.error(f"[Slack Error]: {r.status_code} {r.text}")
    except Exception as e:
        logger.error(f"[Slack Exception]: {e}")

# ── HUBSPOT ──────────────────────────────────────────────────────
def get_hubspot_token():
    r = requests.post("https://api.hubapi.com/oauth/v1/token", data={
        "grant_type": "refresh_token",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": REFRESH_TOKEN,
    })
    if r.status_code != 200:
        logger.error(f"[HubSpot Token Error]: {r.text}")
        return None
    return r.json().get("access_token")

def upsert_contact(token, email, firstname, lastname, phone, jobtitle):
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    search_r = requests.post(
        "https://api.hubapi.com/crm/v3/objects/contacts/search", headers=headers,
        json={"filterGroups": [{"filters": [{"propertyName": "email", "operator": "EQ", "value": email}]}]}
    )
    results = search_r.json().get("results", [])
    props = {"email": email, "firstname": firstname, "lastname": lastname, "jobtitle": jobtitle}
    if phone and phone.strip().startswith("+"):
        props["phone"] = phone.strip()

    if results:
        contact_id = results[0]["id"]
        requests.patch(f"https://api.hubapi.com/crm/v3/objects/contacts/{contact_id}", headers=headers, json={"properties": props})
        return contact_id
    else:
        create_r = requests.post("https://api.hubapi.com/crm/v3/objects/contacts", headers=headers, json={"properties": props})
        return create_r.json().get("id")

def build_note(d, branches, submitted_at):
    it_same = (d.get("it_same_as_champion") or "").lower()
    if it_same == "yes":
        it_block = f"<b>Same as Internal Champion</b> — {d.get('champion_name', '')} ({d.get('champion_email', '')})"
    else:
        it_block = f"Name: {d.get('it_name', '')}<br>Title: {d.get('it_title', '')}<br>Email: {d.get('it_email', '')}<br>Phone: {d.get('it_phone', '')}<br>POS System: {d.get('pos_system', '')}<br>Accounting SW: {d.get('accounting_software', '')}"

    branch_rows = ""
    for i, b in enumerate(branches, 1):
        hours = f"{b.get('open', '')} – {b.get('close', '')}".strip(" –")
        branch_rows += f"<tr><td style='padding:5px 8px;border-bottom:1px solid #eee'>{i}</td><td style='padding:5px 8px;border-bottom:1px solid #eee'><b>{b.get('name','')}</b></td><td style='padding:5px 8px;border-bottom:1px solid #eee'>{b.get('address','')}</td><td style='padding:5px 8px;border-bottom:1px solid #eee'>{b.get('cost_center','')}</td><td style='padding:5px 8px;border-bottom:1px solid #eee'>{hours}</td></tr>"
    branch_section = f"<table style='border-collapse:collapse;width:100%;font-size:12px'><tr style='background:#321e57;color:#fff'><th style='padding:6px 8px'>#</th><th style='padding:6px 8px'>Branch Name</th><th style='padding:6px 8px'>Address</th><th style='padding:6px 8px'>Cost Center</th><th style='padding:6px 8px'>Hours</th></tr>{branch_rows}</table>" if branch_rows else "<i>No branch data provided.</i>"

    def link_cell(label, link):
        if link and link.strip(): return f"{label}: <a href='{link.strip()}' target='_blank'>{link.strip()}</a>"
        return f"{label}: —"

    files_block = link_cell("Invoices", d.get("invoices_link", "")) + "<br>" + link_cell("Supplier Details", d.get("suppliers_link", ""))

    return (
        f"<h3 style='color:#321e57;margin:0 0 4px'>SUPY ONBOARDING</h3><p style='color:#888;font-size:11px;margin:0 0 16px'>Submitted: {submitted_at}</p>"
        f"<h4 style='color:#503390;border-bottom:1px solid #e0d8f0;padding-bottom:4px;margin:14px 0 8px'>COMPANY INFO</h4>Company Name: {d.get('company_name', '')}"
        f"<h4 style='color:#503390;border-bottom:1px solid #e0d8f0;padding-bottom:4px;margin:14px 0 8px'>INTERNAL CHAMPION</h4>Name: {d.get('champion_name', '')}<br>Title: {d.get('champion_title', '')}<br>Email: {d.get('champion_email', '')}<br>Phone: {d.get('champion_phone', '')}"
        f"<h4 style='color:#503390;border-bottom:1px solid #e0d8f0;padding-bottom:4px;margin:14px 0 8px'>FINANCE POC</h4>External Accounting Firm: {d.get('accounting_external', '')}<br>Name: {d.get('finance_name', '')}<br>Title: {d.get('finance_title', '')}<br>Email: {d.get('finance_email', '')}<br>Phone: {d.get('finance_phone', '')}"
        f"<h4 style='color:#503390;border-bottom:1px solid #e0d8f0;padding-bottom:4px;margin:14px 0 8px'>IT CONTACT</h4>{it_block}"
        f"<h4 style='color:#503390;border-bottom:1px solid #e0d8f0;padding-bottom:4px;margin:14px 0 8px'>BRANCH CONFIGURATION</h4>{branch_section}"
        f"<h4 style='color:#503390;border-bottom:1px solid #e0d8f0;padding-bottom:4px;margin:14px 0 8px'>OPERATIONS</h4>Order Method: {d.get('ordering_method', '')}<br>PO Approver: {d.get('po_approver', '')}<br>Ordering Structure: {d.get('ordering_structure', '')}<br>Stock Counts: {d.get('stock_counts', '')}<br>Stock Count Duration: {d.get('stock_count_duration', '')}<br>Inventory System: {d.get('inventory_system', '')}"
        f"<h4 style='color:#503390;border-bottom:1px solid #e0d8f0;padding-bottom:4px;margin:14px 0 8px'>FOOD COST</h4>Current Food Cost %: {d.get('food_cost_current', '')}<br>Target Food Cost %: {d.get('food_cost_target', '')}<br>COGS Method: {d.get('cogs_method', '')}<br>Invoice Delivery: {d.get('invoice_delivery', '')}<br>Finance Complications: {d.get('finance_complications', '')}"
        f"<h4 style='color:#503390;border-bottom:1px solid #e0d8f0;padding-bottom:4px;margin:14px 0 8px'>GOALS &amp; BLOCKERS</h4>Top Problem to Solve: {d.get('top_problem', '')}<br>CSM Notes: {d.get('extra_notes', '')}<br>Known Blockers: {d.get('blockers', '')}<br>Target Go-Live: {d.get('golive_date', '')}"
        f"<h4 style='color:#503390;border-bottom:1px solid #e0d8f0;padding-bottom:4px;margin:14px 0 8px'>FILE LINKS</h4>{files_block}"
    )

# ── WEBHOOK ──────────────────────────────────────────────────────
@app.route("/webhook", methods=["POST", "OPTIONS"])
def webhook():
    if request.method == "OPTIONS":
        resp = app.make_default_options_response()
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        resp.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        return resp

    d     = request.values.to_dict()
    email = (d.get("champion_email") or "").strip()
    company = (d.get("company_name") or "Unknown").strip()

    logger.info(f"\n{'='*50}\nNEW SUBMISSION from: {email} | {company}\n{'='*50}")
    logger.info(f"Fields received: {list(d.keys())}")

    if not email:
        return jsonify({"error": "No email provided"}), 400

    submitted_at = datetime.now(timezone.utc).strftime("%d %b %Y at %H:%M UTC")

    # PARSE BRANCHES
    branches = []
    if d.get("branches_json"):
        try:
            branches = json.loads(d.get("branches_json"))
        except Exception as e:
            logger.error(f"Branch Parse Error: {e}")

    status_parts = []

    # LOG TO SHEETS
    try:
        log_to_sheets(d, branches, submitted_at)
        status_parts.append("sheets:ok")
    except Exception as e:
        logger.error(f"Sheets Logging Failed: {e}")
        status_parts.append("sheets:fail")

    # SEND EMAIL
    try:
        send_email_notification(d, branches, submitted_at)
        status_parts.append("email:ok")
    except Exception as e:
        logger.error(f"Email Failed: {e}")
        status_parts.append("email:fail")

    # SEND SLACK
    try:
        send_slack_notification(d, branches, submitted_at)
        status_parts.append("slack:ok")
    except Exception as e:
        logger.error(f"Slack Failed: {e}")
        status_parts.append("slack:fail")

    # HUBSPOT TOKEN
    token = get_hubspot_token()
    if not token:
        log_submission(email, company, submitted_at, "hubspot_auth_failed|" + "|".join(status_parts))
        return jsonify({"error": "HubSpot auth failed"}), 500

    # UPSERT CONTACT
    name_parts = (d.get("champion_name") or "Client").split()
    contact_id = upsert_contact(
        token, email,
        name_parts[0], " ".join(name_parts[1:]) if len(name_parts) > 1 else "",
        d.get("champion_phone", ""), d.get("champion_title", "")
    )

    if not contact_id:
        log_submission(email, company, submitted_at, "contact_upsert_failed|" + "|".join(status_parts))
        return jsonify({"error": "Contact upsert failed"}), 400

    # BUILD AND POST NOTE
    note_body    = build_note(d, branches, submitted_at)
    hs_headers   = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    note_payload = {
        "properties": {
            "hs_timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "hs_note_body": note_body
        }
    }

    note_r = requests.post("https://api.hubapi.com/crm/v3/objects/notes", headers=hs_headers, json=note_payload)

    if note_r.status_code == 201:
        note_id = note_r.json().get("id")
        requests.post(
            "https://api.hubapi.com/crm/v3/associations/Notes/Contacts/batch/create",
            headers=hs_headers,
            json={"inputs": [{"from": {"id": note_id}, "to": {"id": contact_id}, "type": "note_to_contact"}]}
        )
        status_parts.append("hubspot:ok")
        log_submission(email, company, submitted_at, "SUCCESS|" + "|".join(status_parts))
        logger.info("✅ Submission Successful!")
        return jsonify({"status": "ok"}), 200

    status_parts.append("hubspot_note:fail")
    log_submission(email, company, submitted_at, "PARTIAL|" + "|".join(status_parts))
    logger.warning(f"⚠️ Note Error: {note_r.text}")
    return jsonify({"status": "partial"}), 200


@app.route("/logs", methods=["GET"])
def view_logs():
    """Simple log viewer — restrict in production"""
    try:
        with open(LOG_FILE, "r") as f:
            lines = f.readlines()
        return "<pre style='font-family:monospace;padding:20px'>" + "".join(lines[-200:]) + "</pre>", 200
    except FileNotFoundError:
        return "No submissions logged yet.", 200


@app.route("/")
def index():
    return "Supy Onboarding Server is running.", 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
