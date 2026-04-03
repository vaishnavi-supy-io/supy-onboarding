import os
import json
import requests
import logging
from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime, timezone

app = Flask(__name__)
# Fixes CORS errors for your frontend
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)

# ── CONFIGURATION (Values are pulled from the WSGI Vault) ────────
CLIENT_ID           = os.environ.get("CLIENT_ID", "")
CLIENT_SECRET       = os.environ.get("CLIENT_SECRET", "")
REFRESH_TOKEN       = os.environ.get("REFRESH_TOKEN", "")

GMAIL_CLIENT_ID     = os.environ.get("GMAIL_CLIENT_ID", "")
GMAIL_CLIENT_SECRET = os.environ.get("GMAIL_CLIENT_SECRET", "")
GMAIL_REFRESH_TOKEN = os.environ.get("GMAIL_REFRESH_TOKEN", "")

SLACK_WEBHOOK_URL   = os.environ.get("SLACK_WEBHOOK_URL", "")
GOOGLE_SCRIPT_URL   = os.environ.get("GOOGLE_SCRIPT_URL", "")

EMAIL_FROM       = "vaishnavi@supy.io"
EMAIL_RECIPIENTS = ["vaishnavi@supy.io", "randhir@supy.io", "kenneth@supy.io"]

LOG_FILE = os.path.join(os.path.dirname(__file__), "submissions.log")

# ── LOGGING SETUP ────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def log_submission(email, company, submitted_at, status):
    try:
        with open(LOG_FILE, "a") as f:
            f.write(f"{submitted_at} | {email} | {company} | {status}\n")
    except Exception as e:
        logger.error(f"Log write error: {e}")

# ── 1. GOOGLE SHEETS (Via Apps Script Bridge) ─────────────────────
def log_to_sheets(d, branches, submitted_at):
    if not GOOGLE_SCRIPT_URL:
        logger.error("[Sheets] Magic URL missing from Vault")
        return False
    
    payload = d.copy()
    payload["submitted_at"] = submitted_at
    payload["branch_count"] = len(branches)
    
    try:
        r = requests.post(GOOGLE_SCRIPT_URL, json=payload, timeout=10)
        logger.info(f"[Sheets] Bridge Response: {r.text}")
        return True
    except Exception as e:
        logger.error(f"[Sheets Error]: {e}")
        return False

# ── 2. GMAIL (OAuth 2.0) ──────────────────────────────────────────
def get_gmail_access_token():
    r = requests.post("https://oauth2.googleapis.com/token", data={
        "grant_type":    "refresh_token",
        "client_id":     GMAIL_CLIENT_ID,
        "client_secret": GMAIL_CLIENT_SECRET,
        "refresh_token": GMAIL_REFRESH_TOKEN,
    })
    return r.json().get("access_token") if r.status_code == 200 else None

def send_email_notification(d, branches, submitted_at):
    token = get_gmail_access_token()
    if not token: return False

    import base64
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    company = d.get("company_name", "Unknown Company")
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🚀 New Onboarding: {company}"
    msg["From"] = EMAIL_FROM
    msg["To"] = ", ".join(EMAIL_RECIPIENTS)

    # Simple Email Body
    body = f"New onboarding submission received for {company} on {submitted_at}.\nCheck HubSpot for details."
    msg.attach(MIMEText(body, "plain"))

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    r = requests.post("https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
                  headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                  json={"raw": raw})
    return True if r.status_code == 200 else False

# ── 3. SLACK ──────────────────────────────────────────────────────
def send_slack_notification(d):
    if not SLACK_WEBHOOK_URL: return False
    payload = {
        "text": f"🎉 *New Onboarding Submission*\n*Company:* {d.get('company_name')}\n*Champion:* {d.get('champion_name')}"
    }
    r = requests.post(SLACK_WEBHOOK_URL, json=payload)
    return True if r.status_code == 200 else False

# ── 4. HUBSPOT ───────────────────────────────────────────────────
def get_hubspot_token():
    r = requests.post("https://api.hubapi.com/oauth/v1/token", data={
        "grant_type":    "refresh_token",
        "client_id":     CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": REFRESH_TOKEN,
    })
    return r.json().get("access_token") if r.status_code == 200 else None

def upsert_contact(token, d):
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    email = d.get("champion_email")
    props = {
        "email": email, 
        "firstname": d.get("champion_name"), 
        "jobtitle": d.get("champion_title"),
        "phone": d.get("champion_phone")
    }
    # Search for existing
    search = requests.post("https://api.hubapi.com/crm/v3/objects/contacts/search", headers=headers,
                           json={"filterGroups": [{"filters": [{"propertyName": "email", "operator": "EQ", "value": email}]}]})
    results = search.json().get("results", [])
    
    if results:
        cid = results[0]["id"]
        requests.patch(f"https://api.hubapi.com/crm/v3/objects/contacts/{cid}", headers=headers, json={"properties": props})
        return cid
    else:
        create = requests.post("https://api.hubapi.com/crm/v3/objects/contacts", headers=headers, json={"properties": props})
        return create.json().get("id")

# --- THIS IS THE CORRECTED, FULL HTML NOTE FOR HUBSPOT ---
def build_note(d, branches, submitted_at):
    it_same = (d.get("it_same_as_champion") or "").lower()
    if it_same == "yes":
        it_block = f"<b>Same as Internal Champion</b> — {d.get('champion_name','')} ({d.get('champion_email','')})"
    else:
        it_block = f"Name: {d.get('it_name','')}<br>Title: {d.get('it_title','')}<br>Email: {d.get('it_email','')}<br>Phone: {d.get('it_phone','')}<br>POS System: {d.get('pos_system','')}<br>Accounting SW: {d.get('accounting_software','')}"

    branch_rows = ""
    for i, b in enumerate(branches, 1):
        hours = f"{b.get('open','')} – {b.get('close','')}".strip(" –")
        branch_rows += f"<tr><td style='padding:5px 8px;border-bottom:1px solid #eee'>{i}</td><td style='padding:5px 8px;border-bottom:1px solid #eee'><b>{b.get('name','')}</b></td><td style='padding:5px 8px;border-bottom:1px solid #eee'>{b.get('address','')}</td><td style='padding:5px 8px;border-bottom:1px solid #eee'>{b.get('cost_center','')}</td><td style='padding:5px 8px;border-bottom:1px solid #eee'>{hours}</td></tr>"
    branch_section = f"<table style='border-collapse:collapse;width:100%;font-size:12px'><tr style='background:#321e57;color:#fff'><th style='padding:6px 8px'>#</th><th style='padding:6px 8px'>Branch Name</th><th style='padding:6px 8px'>Address</th><th style='padding:6px 8px'>Cost Center</th><th style='padding:6px 8px'>Hours</th></tr>{branch_rows}</table>" if branch_rows else "<i>No branch data provided.</i>"

    def link_cell(label, link):
        if link and link.strip(): return f"{label}: <a href='{link.strip()}' target='_blank'>{link.strip()}</a>"
        return f"{label}: —"

    files_block = link_cell("Invoices", d.get("invoices_link","")) + "<br>" + link_cell("Supplier Details", d.get("suppliers_link",""))

    return (
        f"<h3 style='color:#321e57;margin:0 0 4px'>SUPY ONBOARDING</h3><p style='color:#888;font-size:11px;margin:0 0 16px'>Submitted: {submitted_at}</p>"
        f"<h4 style='color:#503390;border-bottom:1px solid #e0d8f0;padding-bottom:4px;margin:14px 0 8px'>COMPANY INFO</h4>Company Name: {d.get('company_name','')}"
        f"<h4 style='color:#503390;border-bottom:1px solid #e0d8f0;padding-bottom:4px;margin:14px 0 8px'>INTERNAL CHAMPION</h4>Name: {d.get('champion_name','')}<br>Title: {d.get('champion_title','')}<br>Email: {d.get('champion_email','')}<br>Phone: {d.get('champion_phone','')}"
        f"<h4 style='color:#503390;border-bottom:1px solid #e0d8f0;padding-bottom:4px;margin:14px 0 8px'>FINANCE POC</h4>External Accounting Firm: {d.get('accounting_external','')}<br>Name: {d.get('finance_name','')}<br>Title: {d.get('finance_title','')}<br>Email: {d.get('finance_email','')}<br>Phone: {d.get('finance_phone','')}"
        f"<h4 style='color:#503390;border-bottom:1px solid #e0d8f0;padding-bottom:4px;margin:14px 0 8px'>IT CONTACT</h4>{it_block}"
        f"<h4 style='color:#503390;border-bottom:1px solid #e0d8f0;padding-bottom:4px;margin:14px 0 8px'>BRANCH CONFIGURATION</h4>{branch_section}"
        f"<h4 style='color:#503390;border-bottom:1px solid #e0d8f0;padding-bottom:4px;margin:14px 0 8px'>OPERATIONS</h4>Order Method: {d.get('ordering_method','')}<br>PO Approver: {d.get('po_approver','')}<br>Ordering Structure: {d.get('ordering_structure','')}<br>Stock Counts: {d.get('stock_counts','')}<br>Stock Count Duration: {d.get('stock_count_duration','')}<br>Inventory System: {d.get('inventory_system','')}"
        f"<h4 style='color:#503390;border-bottom:1px solid #e0d8f0;padding-bottom:4px;margin:14px 0 8px'>FOOD COST</h4>Current Food Cost %: {d.get('food_cost_current','')}<br>Target Food Cost %: {d.get('food_cost_target','')}<br>COGS Method: {d.get('cogs_method','')}<br>Invoice Delivery: {d.get('invoice_delivery','')}<br>Finance Complications: {d.get('finance_complications','')}"
        f"<h4 style='color:#503390;border-bottom:1px solid #e0d8f0;padding-bottom:4px;margin:14px 0 8px'>GOALS &amp; BLOCKERS</h4>Top Problem to Solve: {d.get('top_problem','')}<br>CSM Notes: {d.get('extra_notes','')}<br>Known Blockers: {d.get('blockers','')}<br>Target Go-Live: {d.get('golive_date','')}"
        f"<h4 style='color:#503390;border-bottom:1px solid #e0d8f0;padding-bottom:4px;margin:14px 0 8px'>FILE LINKS</h4>{files_block}"
    )

# ── THE MAIN WEBHOOK ──────────────────────────────────────────────
@app.route("/webhook", methods=["POST", "OPTIONS"])
def webhook():
    if request.method == "OPTIONS":
        return jsonify({"status": "ok"}), 200
    
    d = request.values.to_dict()
    email = d.get("champion_email", "Unknown").strip()
    company = d.get("company_name", "Unknown").strip()
    submitted_at = datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC")
    
    branches = []
    if d.get("branches_json"):
        try: branches = json.loads(d["branches_json"])
        except: pass

    # Execution tracking
    results = []

    # 1. Sheets
    if log_to_sheets(d, branches, submitted_at): results.append("sheets:ok")
    else: results.append("sheets:fail")

    # 2. Gmail
    if send_email_notification(d, branches, submitted_at): results.append("email:ok")
    else: results.append("email:fail")

    # 3. Slack
    if send_slack_notification(d): results.append("slack:ok")
    else: results.append("slack:fail")

    # 4. HubSpot
    token = get_hubspot_token()
    if token:
        cid = upsert_contact(token, d)
        if cid:
            note_body = build_note(d, branches, submitted_at)
            # Create Note
            note_r = requests.post("https://api.hubapi.com/crm/v3/objects/notes", 
                                   headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                                   json={"properties": {"hs_note_body": note_body, "hs_timestamp": datetime.now(timezone.utc).isoformat()}})
            if note_r.status_code == 201:
                nid = note_r.json().get("id")
                # Associate Note to Contact
                requests.post("https://api.hubapi.com/crm/v3/associations/Notes/Contacts/batch/create",
                              headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                              json={"inputs": [{"from": {"id": nid}, "to": {"id": cid}, "type": "note_to_contact"}]})
                results.append("hubspot:ok")
    
    log_submission(email, company, submitted_at, "|".join(results))
    return jsonify({"status": "ok", "details": results}), 200

@app.route("/logs", methods=["GET"])
def view_logs():
    try:
        with open(LOG_FILE, "r") as f:
            return f"<pre>{f.read()}</pre>"
    except: return "No logs found.", 200

@app.route("/")
def index():
    return "Supy Automation Server: Online", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
