import os
import json
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime, timezone
from google.oauth2 import service_account
from googleapiclient.discovery import build

app = Flask(__name__)
# This fixes the CORS errors in the browser allowing the frontend to talk to the backend
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)

# ── CONFIGURATION ───────────────────────────────────────────────
SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID", "1ZmPjLk2qWuIzIL5gKltXFVqvyYpPu5kYuw7-KrU6d58")

# Your NEW HubSpot Credentials
CLIENT_ID     = os.environ.get("CLIENT_ID", "d5f491d5-9206-422b-97b1-e037b4f06c45")
CLIENT_SECRET = os.environ.get("CLIENT_SECRET", "ce5b4a8c-3d53-4579-bbf6-783f9a149ab1")
REFRESH_TOKEN = os.environ.get("REFRESH_TOKEN", "na1-ddcd-e6ae-4cf6-82b3-439b1efaa389")

SERVICE_ACCOUNT_INFO = {
    "type": "service_account",
    "project_id": "hale-equator-456508-p0",
    "private_key_id": "5f2f79b0eece4260afc83291eb476cbee1a9f6ff",
    "private_key": "-----BEGIN PRIVATE KEY-----\nMIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQCq36ODSPzIY2US\nfB1ZO3s8DYw/T0wxa6CTKscOW0OiQG9q+JZsc42JWZcn3QSnVX6orFQnXXAXixAM\n8Iojg6OQlYqPqQzJeFk2yUSwONZuHrPOGOxCQ19doOvnOXLaTAylcVFlnCrIwdTp\nzW25ORQSqxWNoV2tovLEy3B7KgcLzem6eqfS2Q+P5xfotxSY+8ya40Y5koiBydFw\nMkrJhsChmc5xGe8wJIsal8m1Ms/E9otN+iOzywr86QSiXr59xREmBv/ADiTN3fjt\nHO0T1C7TNUn4chHoGEi0Uy3EfgXm+/RPYfntH+X1wzAyslTqAFQQeRmfwKBE0XYB\nb/eScPVhAgMBAAECggEABIK2zEZm9ds51c0U8UAStrkc1KcBOeS/bmMYshZSqLvO\ntSIuxloeiFunE9RPxSMKnuU9q3RZ+yUenVjULK/S54QrDjPGNKNKp5mUiJpXfrys\nvmoGApHIuK4AzC/GCmErjEp7fZUrw/Tp6+oSVWteTkfZ3808rdK5WdyM8ZNgcD1K\nNDs+xqMTh+auGf0kRqnkA/AipjKu+MtIfr3jlAUiRJ342jQ+9G6dwkHAIiZyc82v\n/1zLrmiiRNgIyJRK7YaiIGDui+iA6W39pHIb7QBnbRPWi5M2aE1+mhUJFJp4zTr0\n8G0Er9V3MEaT0CTAob1pAtpLi9LqFuWSIUJJ26IqKQKBgQDisySqnFhqEZyycLpI\nRUlIBUWCcr8BIfleCYSJd1TvVwS6utUoG9QrggEY2NUWwP/IFWyPNVO6vKKkzfNn\njl/Pjym0QCE+PO6Q2yXQAhgaanQIrJ5wexANaZxEIE9n8pNacPTipWshvRp4Y3bG\nv7agGDyTvdWE48/k8s72RYIsiwKBgQDA9V09KAXNAamxbgl8JvvQX7r6Ls4HTbks\n9d0Pd2EgpNAM4QT54hC3EbTSBba3M+NCU14SsCPBFjRgVLQ3l0QpK95Xgm7/u2tA\npMuNqc5dliUMHIKKtY4qMG2j2YUfoGS6g97eVLSdfVreeQbCxahMDQ5Lj978VOwb\nJQ87BeaHQwKBgQCFW+8w8mJMm2m7yva6tw+h73/xekEEkJDakezG1U1AsscUdf4Y\n5y4MHiE5Fa1dAlI1yOyg3jUQQBHJs2IBxE52knhtEeC8dSm+SzzWPbUiLQdvZuSZ\ntLs/uKX1qbAsrRWj+ZkFj1wTb+QXeCOSTYtIaJmSK/VkhINy4qd/Vmp6ewKBgQCr\nfeaeIeH179JnVQqtAuCus0Y0cEDAEP3QzbrosgrqvlACAkMv6xE8A0qXlmhrrnv+\nSKXFKjK8uwVV0DJTbecwSELVt6D7PBD4ZP5cK1yzpGvMtdH3gaCWMnBfPUWpdB3R\n/r2nD9VuWyjVrO6rUIxg+wGHepiN3tPw1CETLg1SjQKBgFMXTdjOu2/wWZ0bLWwO\nUMfNx3pH1sJXJTkGLZ61AT3/d2BBqhqz++MWEiPYM/4ho/deRrbQoWCeCvd9tDhr\n9HWYByqoFWiNVAP/dmiSNBChS6SUDNx3rQ3OxqbHyrYpMzLBG8r5PS3TJOW5Abnx\nV2Oy1gUsHe4VfJz6YhMuL/+P\n-----END PRIVATE KEY-----\n",
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
    """Appends form data as a new row in Google Sheets"""
    try:
        service = get_google_service('sheets', 'v4', ['https://www.googleapis.com/auth/spreadsheets'])
        branch_text = " | ".join([f"{b.get('name','')} ({b.get('address','')}) CC:{b.get('cost_center','')} {b.get('open','')}-{b.get('close','')}" for b in branches]) if branches else ""

        row = [
            submitted_at, d.get("company_name", ""),
            d.get("champion_name", ""), d.get("champion_title", ""), d.get("champion_email", ""), d.get("champion_phone", ""),
            d.get("accounting_external", ""), d.get("finance_name", ""), d.get("finance_title", ""), d.get("finance_email", ""), d.get("finance_phone", ""),
            d.get("it_same_as_champion", ""), d.get("it_name", ""), d.get("it_title", ""), d.get("it_email", ""), d.get("it_phone", ""), d.get("pos_system", ""), d.get("accounting_software", ""),
            branch_text, str(len(branches)),
            d.get("invoices_link", ""), d.get("suppliers_link", ""), d.get("recipes_link", ""),
            d.get("ordering_method", ""), d.get("po_approver", ""), d.get("ordering_structure", ""), d.get("stock_counts", ""), d.get("stock_count_duration", ""), d.get("inventory_system", ""),
            d.get("food_cost_current", ""), d.get("food_cost_target", ""), d.get("cogs_method", ""), d.get("invoice_delivery", ""), d.get("finance_complications", ""),
            d.get("top_problem", ""), d.get("extra_notes", ""), d.get("blockers", ""), d.get("golive_date", "")
        ]

        # Add Headers if sheet is empty
        result = service.spreadsheets().values().get(spreadsheetId=SPREADSHEET_ID, range="Sheet1!A1:A2").execute()
        if not result.get("values"):
            headers = ["Submitted At", "Company Name", "Champion Name", "Champion Title", "Champion Email", "Champion Phone", "External Accounting?", "Finance Name", "Finance Title", "Finance Email", "Finance Phone", "IT Same as Champion?", "IT Name", "IT Title", "IT Email", "IT Phone", "POS System", "Accounting Software", "Branches Summary", "Branch Count", "Invoices Link", "Suppliers Link", "Recipes Link", "Ordering Method", "PO Approver", "Ordering Structure", "Stock Counts", "Stock Count Duration", "Inventory System", "Food Cost Current", "Food Cost Target", "COGS Method", "Invoice Delivery", "Finance Complications", "Top Problem", "Extra Notes", "Blockers", "Go-Live Date"]
            service.spreadsheets().values().append(spreadsheetId=SPREADSHEET_ID, range="Sheet1!A1", valueInputOption="RAW", body={"values": [headers]}).execute()

        # Append Data
        service.spreadsheets().values().append(spreadsheetId=SPREADSHEET_ID, range="Sheet1!A1", valueInputOption="RAW", insertDataOption="INSERT_ROWS", body={"values": [row]}).execute()
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
    search_r = requests.post("https://api.hubapi.com/crm/v3/objects/contacts/search", headers=headers, json={"filterGroups": [{"filters": [{"propertyName": "email", "operator": "EQ", "value": email}]}]})
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
        branch_rows += f"<tr><td style='padding:5px 8px;border-bottom:1px solid #eee'>{i}</td><td style='padding:5px 8px;border-bottom:1px solid #eee'><b>{b.get('name','')}</b></td><td style='padding:5px 8px;border-bottom:1px solid #eee'>{b.get('address','')}</td><td style='padding:5px 8px;border-bottom:1px solid #eee'>{b.get('cost_center','')}</td><td style='padding:5px 8px;border-bottom:1px solid #eee'>{hours}</td><td style='padding:5px 8px;border-bottom:1px solid #eee'>{b.get('details','')}</td></tr>"
    branch_section = f"<table style='border-collapse:collapse;width:100%;font-size:12px'><tr style='background:#321e57;color:#fff'><th style='padding:6px 8px'>#</th><th style='padding:6px 8px'>Branch Name</th><th style='padding:6px 8px'>Address</th><th style='padding:6px 8px'>Cost Center</th><th style='padding:6px 8px'>Hours</th><th style='padding:6px 8px'>Details</th></tr>{branch_rows}</table>" if branch_rows else "<i>No branch data provided.</i>"

    def link_cell(label, link):
        if link and link.strip(): return f"{label}: <a href='{link.strip()}' target='_blank'>{link.strip()}</a>"
        return f"{label}: —"

    files_block = link_cell("Invoices", d.get("invoices_link", "")) + "<br>" + link_cell("Supplier Details", d.get("suppliers_link", "")) + "<br>" + link_cell("Recipes", d.get("recipes_link", ""))

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

@app.route("/webhook", methods=["POST", "OPTIONS"])
def webhook():
    # CORS PRE-FLIGHT CHECK
    if request.method == "OPTIONS":
        resp = app.make_default_options_response()
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        resp.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        return resp

    # GET DATA SAFELY
    d = request.values.to_dict()
    email = (d.get("champion_email") or "").strip()
    
    print(f"\n--- NEW SUBMISSION RECEIVED ---")
    print(f"Fields received: {list(d.keys())}")

    if not email:
        return jsonify({"error": "No email provided"}), 400

    submitted_at = datetime.now(timezone.utc).strftime("%d %b %Y at %H:%M UTC")

    # PARSE BRANCHES
    branches = []
    if d.get("branches_json"):
        try: branches = json.loads(d.get("branches_json"))
        except Exception as e: print(f"Branch Parse Error: {e}")

    # LOG TO SHEETS
    try: log_to_sheets(d, branches, submitted_at)
    except Exception as e: print(f"Sheets Logging Failed: {e}")

    # HUBSPOT TOKEN
    token = get_hubspot_token()
    if not token: return jsonify({"error": "HubSpot auth failed"}), 500

    # UPSERT CONTACT
    name_parts = (d.get("champion_name") or "Client").split()
    contact_id = upsert_contact(token, email, name_parts[0], " ".join(name_parts[1:]) if len(name_parts)>1 else "", d.get("champion_phone", ""), d.get("champion_title", ""))

    if not contact_id: return jsonify({"error": "Contact upsert failed"}), 400

    # BUILD AND POST NOTE
    note_body = build_note(d, branches, submitted_at)
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    note_payload = {"properties": {"hs_timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "hs_note_body": note_body}}
    
    note_r = requests.post("https://api.hubapi.com/crm/v3/objects/notes", headers=headers, json=note_payload)
    
    # ASSOCIATE NOTE
    if note_r.status_code == 201:
        note_id = note_r.json().get("id")
        requests.post("https://api.hubapi.com/crm/v3/associations/Notes/Contacts/batch/create", headers=headers, json={"inputs": [{"from": {"id": note_id}, "to": {"id": contact_id}, "type": "note_to_contact"}]})
        print("✅ Submission Successful!")
        return jsonify({"status": "ok"}), 200
    
    print(f"⚠️ Note Error: {note_r.text}")
    return jsonify({"status": "partial"}), 200

@app.route("/")
def index():
    return "Supy Onboarding Server is running.", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
