import os
import json
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime, timezone
from google.oauth2 import service_account
from googleapiclient.discovery import build

app = Flask(__name__)
CORS(app)

# ── CONFIGURATION ───────────────────────────────────────────────
SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID", "1ZmPjLk2qWuIzIL5gKltXFVqvyYpPu5kYuw7-KrU6d58")

CLIENT_ID     = os.environ.get("CLIENT_ID", "d5f491d5-9206-422b-97b1-e037b4f06c45")
CLIENT_SECRET = os.environ.get("CLIENT_SECRET", "ce5b4a8c-72ee-4ccc-91b6-25a40a7815c0")
REFRESH_TOKEN = os.environ.get("REFRESH_TOKEN", "na1-ddcd-e6ae-4cf6-82b3-439b1efaa389")

SERVICE_ACCOUNT_INFO = {
    "type": "service_account",
    "project_id": "hale-equator-456508-p0",
    "private_key_id": "afbecd82e12a3b1bc6d988cc8db7974c2b085ad7",
    "private_key": "-----BEGIN PRIVATE KEY-----\nMIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQDh9FDL8PCl2PaH\noKhCXf8QK7MJeEsbyMGhsNslcX1omDDF6sWpc7aN9oZIkLJIbA2fIU2K34a41vOE\nE+GvJ75ZN6k6EqJ1meMbFVOlW3yhAJffkdScM+qrGslBSvoHesxc+b1KWQydLDi2\nYhTrjnnRvR1NwbAiGNltbM3vJCPAHwp8Y6rgRIQODTCoQ4TNL5x6QytnE29LW66/\nKgN19nl0vBr/B+6T743D5XXKDSbNnKFqRVnRHpfObdR/ZRTJzgVGR3uzOx4ORErg\nEQt1COqAXFHevbKUB9Fv1k90d0HcnM/Q6PsRKu98z8Amhf2RngkwpIIgKfCPuMGu\nc3VVw983AgMBAAECggEALwaBcEhnVSTn/gcmLZXReUSXAOALxa8M+YFMwqixgHy4\nHeDEHYWrFzWY8e5HZII0fYtZT49AwyRdTv4ySJldaMUIT8FEFXSfCupv26jEMd/l\nO87mcFHvw4eSHigkDD123dzOE/SfhvCGpxKXpwSifs+8kwu+BAKm8bqky2H6nMeU\n81qzZoAlum4tqSPc53K38RVRSZnzFe4wSienWJv+6NHD891DeWoccnFqWkG5ju4X\navB805e9n6iz0O/++x/t7HDAVlCR4P6Tf81Y0uhUpr3JBuJmVJaA0foDZTscWUUC\nTMpXvq+Vjzy4+oVPsP9NjhsLkQe5K5YkAeZbyZ1GmQKBgQDwna7xYe4BjRYLRQsC\nVpRqMGjWZmBmKug9aHx4mzrgAvj3UXFWXw157jMlwl9PQlbO5LmS6CtORZk68m+1\nMamn4c65IcRz1rKJpvWojAgqPkoleOPHSO7K625+wJQt0vBwti8Pgj7O9/tj5VJD\n0dIctnbBi6n+S/3tLocA3O4o2QKBgQDwZqgPYtmM/oNbt8i6272jwDvK5t5l4Eiu\nypF5K0hzfM32x7hVu5Y00f4DC69PNl5H/xFZ4RW5bYjBMpIH0Zh/SElo9E2MORTD\nO9AGwkeQvjN5WP7v3SSBIrTftDS7PAO2OXxp1fAqyfNVpx8rZjGCkyYlx/y1qblk\ned+Ha3q+jwKBgQDwjMPr//qAxHroU2MZOFNyAemdhoYTPgwl8EKYFKB8eZxLLLnB\nHpALeQ7bTgIY6/p7JoE8FC3PN5dkLiFtpTO2afJQdSjAokCliywHD8/N464e3kfh\n4NESPuKdh4vccAj+tbRArfZ61cIWcZmXwblsCSKahjUxzOkUaLKBM15JqQKBgD7h\nOxg7LNg6QjWdTr3BeEr6nyklVgqjrZ86kO52qc67WEwyVT7ngBR00NIPHl3DxMlk\nKC+wNjR4OAsApT2yTwcL61eufxIsZAfk/zalXn63oVMeOiCXYVL9tv3Ebv6CZh4l\nzysHsHggtqsyuW5qnoye3J2JP8psiHeFgTg0nrh1AoGACqsNAsIymeq48CpGZT+F\nMJthTd5351qooi9146/t9rwPQXX5QtU+MCfsUe+apubP82dY/NMSG7uy9ezF1XMM\nYxy2vVuCIp+Y6dFCeVEHZfS9OI/A6zShK5b764GW/lNDjJfvNZUWIiPSwMmVOa/I\nWZPR4GE/cdyvjBJkPUAwRTM=\n-----END PRIVATE KEY-----\n",
    "client_email": "supy-uploader@hale-equator-456508-p0.iam.gserviceaccount.com",
    "client_id": "104517190572916185488",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/supy-uploader%40hale-equator-456508-p0.iam.gserviceaccount.com",
    "universe_domain": "googleapis.com"
}
# ────────────────────────────────────────────────────────────────


def get_google_service(api_name, api_version, scopes):
    creds = service_account.Credentials.from_service_account_info(
        SERVICE_ACCOUNT_INFO, scopes=scopes
    )
    return build(api_name, api_version, credentials=creds)


def log_to_sheets(d, branches, submitted_at):
    """Append a full row to the Google Sheet backup log."""
    try:
        service = get_google_service(
            'sheets', 'v4',
            ['https://www.googleapis.com/auth/spreadsheets']
        )

        # Flatten branch data into readable string
        branch_text = " | ".join([
            f"{b.get('name','')} ({b.get('address','')}) CC:{b.get('cost_center','')} {b.get('open','')}-{b.get('close','')}"
            for b in branches
        ]) if branches else ""

        row = [
            submitted_at,
            d.get("company_name", ""),
            # Internal Champion
            d.get("champion_name", ""),
            d.get("champion_title", ""),
            d.get("champion_email", ""),
            d.get("champion_phone", ""),
            # Finance
            d.get("accounting_external", ""),
            d.get("finance_name", ""),
            d.get("finance_title", ""),
            d.get("finance_email", ""),
            d.get("finance_phone", ""),
            # IT
            d.get("it_same_as_champion", ""),
            d.get("it_name", ""),
            d.get("it_title", ""),
            d.get("it_email", ""),
            d.get("it_phone", ""),
            d.get("pos_system", ""),
            d.get("accounting_software", ""),
            # Branches
            branch_text,
            str(len(branches)),
            # File links
            d.get("invoices_link", ""),
            d.get("suppliers_link", ""),
            d.get("recipes_link", ""),
            # Operations
            d.get("ordering_method", ""),
            d.get("po_approver", ""),
            d.get("ordering_structure", ""),
            d.get("stock_counts", ""),
            d.get("stock_count_duration", ""),
            d.get("inventory_system", ""),
            # Food cost
            d.get("food_cost_current", ""),
            d.get("food_cost_target", ""),
            d.get("cogs_method", ""),
            d.get("invoice_delivery", ""),
            d.get("finance_complications", ""),
            # Goals
            d.get("top_problem", ""),
            d.get("extra_notes", ""),
            d.get("blockers", ""),
            d.get("golive_date", ""),
        ]

        # Check if header row exists; if sheet is empty, add headers first
        result = service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID,
            range="Sheet1!A1:A2"
        ).execute()

        if not result.get("values"):
            headers = [
                "Submitted At", "Company Name",
                "Champion Name", "Champion Title", "Champion Email", "Champion Phone",
                "External Accounting?", "Finance Name", "Finance Title", "Finance Email", "Finance Phone",
                "IT Same as Champion?", "IT Name", "IT Title", "IT Email", "IT Phone",
                "POS System", "Accounting Software",
                "Branches Summary", "Branch Count",
                "Invoices Link", "Suppliers Link", "Recipes Link",
                "Ordering Method", "PO Approver", "Ordering Structure",
                "Stock Counts", "Stock Count Duration", "Inventory System",
                "Food Cost Current", "Food Cost Target", "COGS Method",
                "Invoice Delivery", "Finance Complications",
                "Top Problem", "Extra Notes", "Blockers", "Go-Live Date",
            ]
            service.spreadsheets().values().append(
                spreadsheetId=SPREADSHEET_ID,
                range="Sheet1!A1",
                valueInputOption="RAW",
                body={"values": [headers]}
            ).execute()

        service.spreadsheets().values().append(
            spreadsheetId=SPREADSHEET_ID,
            range="Sheet1!A1",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": [row]}
        ).execute()

        print("   [Sheets] Row appended successfully.")
    except Exception as e:
        print(f"   [Sheets Error]: {e}")


def get_hubspot_token():
    r = requests.post("https://api.hubapi.com/oauth/v1/token", data={
        "grant_type": "refresh_token",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": REFRESH_TOKEN,
    })
    if r.status_code != 200:
        print(f"   [HubSpot Token Error]: {r.text}")
        return None
    return r.json().get("access_token")


def upsert_contact(token, email, firstname, lastname, phone, jobtitle):
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    search_r = requests.post(
        "https://api.hubapi.com/crm/v3/objects/contacts/search",
        headers=headers,
        json={"filterGroups": [{"filters": [{"propertyName": "email", "operator": "EQ", "value": email}]}]}
    )
    results = search_r.json().get("results", [])

    props = {
        "email": email,
        "firstname": firstname,
        "lastname": lastname,
        "jobtitle": jobtitle
    }
    if phone and phone.strip().startswith("+"):
        props["phone"] = phone.strip()

    if results:
        contact_id = results[0]["id"]
        patch_r = requests.patch(
            f"https://api.hubapi.com/crm/v3/objects/contacts/{contact_id}",
            headers=headers,
            json={"properties": props}
        )
        if patch_r.status_code not in (200, 201):
            print(f"   [HubSpot Update Error]: {patch_r.text}")
        return contact_id
    else:
        create_r = requests.post(
            "https://api.hubapi.com/crm/v3/objects/contacts",
            headers=headers,
            json={"properties": props}
        )
        if create_r.status_code not in (200, 201):
            print(f"   [HubSpot Create Error]: {create_r.text}")
        return create_r.json().get("id")


def build_note(d, branches, submitted_at):
    """Build a clean HTML note for HubSpot with all form data."""

    # IT block
    it_same = (d.get("it_same_as_champion") or "").lower()
    if it_same == "yes":
        it_block = (
            f"<b>Same as Internal Champion</b> — "
            f"{d.get('champion_name', '')} ({d.get('champion_email', '')})"
        )
    else:
        it_block = (
            f"Name: {d.get('it_name', '')}<br>"
            f"Title: {d.get('it_title', '')}<br>"
            f"Email: {d.get('it_email', '')}<br>"
            f"Phone: {d.get('it_phone', '')}<br>"
            f"POS System: {d.get('pos_system', '')}<br>"
            f"Accounting SW: {d.get('accounting_software', '')}"
        )

    # Branch rows
    branch_rows = ""
    for i, b in enumerate(branches, 1):
        hours = f"{b.get('open', '')} – {b.get('close', '')}".strip(" –")
        branch_rows += (
            f"<tr>"
            f"<td style='padding:5px 8px;border-bottom:1px solid #eee'>{i}</td>"
            f"<td style='padding:5px 8px;border-bottom:1px solid #eee'><b>{b.get('name','')}</b></td>"
            f"<td style='padding:5px 8px;border-bottom:1px solid #eee'>{b.get('address','')}</td>"
            f"<td style='padding:5px 8px;border-bottom:1px solid #eee'>{b.get('cost_center','')}</td>"
            f"<td style='padding:5px 8px;border-bottom:1px solid #eee'>{hours}</td>"
            f"<td style='padding:5px 8px;border-bottom:1px solid #eee'>{b.get('details','')}</td>"
            f"</tr>"
        )
    branch_section = (
        f"<table style='border-collapse:collapse;width:100%;font-size:12px'>"
        f"<tr style='background:#321e57;color:#fff'>"
        f"<th style='padding:6px 8px'>#</th>"
        f"<th style='padding:6px 8px'>Branch Name</th>"
        f"<th style='padding:6px 8px'>Address</th>"
        f"<th style='padding:6px 8px'>Cost Center</th>"
        f"<th style='padding:6px 8px'>Hours</th>"
        f"<th style='padding:6px 8px'>Details</th>"
        f"</tr>{branch_rows}</table>"
    ) if branch_rows else "<i>No branch data provided.</i>"

    # File links block (links only, no uploads)
    def link_cell(label, link):
        if link and link.strip():
            return f"{label}: <a href='{link.strip()}' target='_blank'>{link.strip()}</a>"
        return f"{label}: —"

    files_block = (
        link_cell("Invoices", d.get("invoices_link", "")) + "<br>" +
        link_cell("Supplier Details", d.get("suppliers_link", "")) + "<br>" +
        link_cell("Recipes", d.get("recipes_link", ""))
    )

    note = (
        f"<h3 style='color:#321e57;margin:0 0 4px'>SUPY ONBOARDING</h3>"
        f"<p style='color:#888;font-size:11px;margin:0 0 16px'>Submitted: {submitted_at}</p>"

        f"<h4 style='color:#503390;border-bottom:1px solid #e0d8f0;padding-bottom:4px;margin:14px 0 8px'>COMPANY INFO</h4>"
        f"Company Name: {d.get('company_name', '')}"

        f"<h4 style='color:#503390;border-bottom:1px solid #e0d8f0;padding-bottom:4px;margin:14px 0 8px'>INTERNAL CHAMPION</h4>"
        f"Name: {d.get('champion_name', '')}<br>"
        f"Title: {d.get('champion_title', '')}<br>"
        f"Email: {d.get('champion_email', '')}<br>"
        f"Phone: {d.get('champion_phone', '')}"

        f"<h4 style='color:#503390;border-bottom:1px solid #e0d8f0;padding-bottom:4px;margin:14px 0 8px'>FINANCE POC</h4>"
        f"External Accounting Firm: {d.get('accounting_external', '')}<br>"
        f"Name: {d.get('finance_name', '')}<br>"
        f"Title: {d.get('finance_title', '')}<br>"
        f"Email: {d.get('finance_email', '')}<br>"
        f"Phone: {d.get('finance_phone', '')}"

        f"<h4 style='color:#503390;border-bottom:1px solid #e0d8f0;padding-bottom:4px;margin:14px 0 8px'>IT CONTACT</h4>"
        f"{it_block}"

        f"<h4 style='color:#503390;border-bottom:1px solid #e0d8f0;padding-bottom:4px;margin:14px 0 8px'>BRANCH CONFIGURATION</h4>"
        f"{branch_section}"

        f"<h4 style='color:#503390;border-bottom:1px solid #e0d8f0;padding-bottom:4px;margin:14px 0 8px'>OPERATIONS</h4>"
        f"Order Method: {d.get('ordering_method', '')}<br>"
        f"PO Approver: {d.get('po_approver', '')}<br>"
        f"Ordering Structure: {d.get('ordering_structure', '')}<br>"
        f"Stock Counts: {d.get('stock_counts', '')}<br>"
        f"Stock Count Duration: {d.get('stock_count_duration', '')}<br>"
        f"Inventory System: {d.get('inventory_system', '')}"

        f"<h4 style='color:#503390;border-bottom:1px solid #e0d8f0;padding-bottom:4px;margin:14px 0 8px'>FOOD COST</h4>"
        f"Current Food Cost %: {d.get('food_cost_current', '')}<br>"
        f"Target Food Cost %: {d.get('food_cost_target', '')}<br>"
        f"COGS Method: {d.get('cogs_method', '')}<br>"
        f"Invoice Delivery: {d.get('invoice_delivery', '')}<br>"
        f"Finance Complications: {d.get('finance_complications', '')}"

        f"<h4 style='color:#503390;border-bottom:1px solid #e0d8f0;padding-bottom:4px;margin:14px 0 8px'>GOALS &amp; BLOCKERS</h4>"
        f"Top Problem to Solve: {d.get('top_problem', '')}<br>"
        f"CSM Notes: {d.get('extra_notes', '')}<br>"
        f"Known Blockers: {d.get('blockers', '')}<br>"
        f"Target Go-Live: {d.get('golive_date', '')}"

        f"<h4 style='color:#503390;border-bottom:1px solid #e0d8f0;padding-bottom:4px;margin:14px 0 8px'>FILE LINKS</h4>"
        f"{files_block}"
    )
    return note


@app.route("/webhook", methods=["POST", "OPTIONS"])
def webhook():
    # Fix 1: Better CORS handling for the browser's "pre-check"
    if request.method == "OPTIONS":
        resp = app.make_default_options_response()
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        resp.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        return resp

    # Fix 2: Use request.values (replaces request.form for better reliability)
    d = request.values.to_dict()
    
    # This helps you see what's happening in your PythonAnywhere 'server.log'
    print(f"\n--- NEW SUBMISSION RECEIVED ---")
    print(f"Fields received: {list(d.keys())}")

    email = (d.get("champion_email") or "").strip()
    if not email:
        print("ERROR: No email found in submission")
        return jsonify({"error": "No email found"}), 400

    submitted_at = datetime.now(timezone.utc).strftime("%d %b %Y at %H:%M UTC")

    # Fix 3: Robust Branch Parsing
    branches = []
    raw_branches = d.get("branches_json")
    if raw_branches:
        try:
            branches = json.loads(raw_branches)
        except Exception as e:
            print(f"Branch Parse Error: {e}")

    # Fix 4: Try/Except wrap so one error doesn't crash the whole thing
    try:
        log_to_sheets(d, branches, submitted_at)
    except Exception as e:
        print(f"Google Sheets Error: {e}")

    token = get_hubspot_token()
    if not token:
        return jsonify({"error": "HubSpot Auth Failed"}), 500

    # HubSpot Contact Logic
    name_parts = (d.get("champion_name") or "Client").split()
    firstname = name_parts[0]
    lastname = " ".join(name_parts[1:]) if len(name_parts) > 1 else ""

    contact_id = upsert_contact(
        token, email, firstname, lastname,
        d.get("champion_phone", ""),
        d.get("champion_title", "")
    )

    if not contact_id:
        return jsonify({"error": "HubSpot Contact Logic Failed"}), 400

    # HubSpot Note Logic
    note_body = build_note(d, branches, submitted_at)
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    
    note_payload = {
        "properties": {
            "hs_timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "hs_note_body": note_body,
        }
    }

    note_r = requests.post("https://api.hubapi.com/crm/v3/objects/notes", headers=headers, json=note_payload)
    
    if note_r.status_code == 201:
        note_id = note_r.json().get("id")
        assoc_url = "https://api.hubapi.com/crm/v3/associations/Notes/Contacts/batch/create"
        assoc_payload = {
            "inputs": [{"from": {"id": note_id}, "to": {"id": contact_id}, "type": "note_to_contact"}]
        }
        requests.post(assoc_url, headers=headers, json=assoc_payload)
        print("✅ Submission Successful!")
        return jsonify({"status": "ok", "contact_id": contact_id}), 200
    
    # If Note fails but Sheet worked, we still call it a success
    print(f"⚠️ HubSpot Note Failed: {note_r.text}")
    return jsonify({"status": "partial", "contact_id": contact_id}), 200


@app.route("/")
def index():
    return "Supy Onboarding Server is running.", 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
    
