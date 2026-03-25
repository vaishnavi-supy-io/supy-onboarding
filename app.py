import os
import json
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime, timezone
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

app = Flask(__name__)
CORS(app)

# ── CONFIGURATION ───────────────────────────────────────────────
PARENT_FOLDER_ID = "1JZ1Rmyx0cyTcEf1gE74-qwzS3qWE8S_Z"

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

def get_access_token():
    r = requests.post("https://api.hubapi.com/oauth/v1/token", data={
        "grant_type": "refresh_token",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": REFRESH_TOKEN,
    })
    if r.status_code != 200:
        print(f"   [HubSpot Token Error]: {r.text}")
    return r.json().get("access_token")

def upload_to_drive(file_obj, subfolder_id, drive_service):
    """ Uploads a single file to Drive and returns the public link """
    if not file_obj or not file_obj.filename:
        return None
    try:
        file_metadata = {'name': file_obj.filename, 'parents': [subfolder_id]}
        media = MediaIoBaseUpload(file_obj, mimetype=file_obj.content_type or 'application/octet-stream', resumable=True)
        uploaded_file = drive_service.files().create(
            body=file_metadata, media_body=media, fields='id, webViewLink'
        ).execute()

        drive_service.permissions().create(
            fileId=uploaded_file.get('id'),
            body={'type': 'anyone', 'role': 'reader'}
        ).execute()
        return uploaded_file.get('webViewLink')
    except Exception as e:
        print(f"   [Drive Upload Error]: {e}")
        return None

def upsert_contact(token, email, firstname, lastname, phone, jobtitle):
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    search_r = requests.post(
        "https://api.hubapi.com/crm/v3/objects/contacts/search",
        headers=headers,
        json={"filterGroups": [{"filters": [{"propertyName": "email", "operator": "EQ", "value": email}]}]}
    )
    results = search_r.json().get("results", [])

    props = {"email": email, "firstname": firstname, "lastname": lastname, "jobtitle": jobtitle}
    if phone and phone.strip().startswith("+"):
        props["phone"] = phone.strip()

    if results:
        contact_id = results[0]["id"]
        patch_r = requests.patch(f"https://api.hubapi.com/crm/v3/objects/contacts/{contact_id}", headers=headers, json={"properties": props})
        if patch_r.status_code not in (200, 201):
            print(f"   [HubSpot Update Error]: {patch_r.text}")
        return contact_id
    else:
        create_r = requests.post("https://api.hubapi.com/crm/v3/objects/contacts", headers=headers, json={"properties": props})
        if create_r.status_code not in (200, 201):
            print(f"   [HubSpot Create Error]: {create_r.text}")
        return create_r.json().get("id")

def build_note(d, branches, file_links):
    submitted = datetime.now(timezone.utc).strftime("%d %b %Y at %H:%M UTC")

    it_same = d.get("it_same_as_champion", "").lower()
    if it_same == "yes":
        it_block = f"<b>Same as Internal Champion</b> — {d.get('champion_name', '')} ({d.get('champion_email', '')})"
    else:
        it_block = f"Name: {d.get('it_name', '')}<br>Title: {d.get('it_title', '')}<br>Email: {d.get('it_email', '')}<br>Phone: {d.get('it_phone', '')}<br>POS System: {d.get('pos_system', '')}<br>Accounting SW: {d.get('accounting_software', '')}"

    branch_rows = ""
    for i, b in enumerate(branches, 1):
        hours = (b.get("open", "") + " – " + b.get("close", "")).strip(" –")
        branch_rows += f"<tr><td style='padding:5px 8px;border-bottom:1px solid #eee'>{i}</td><td style='padding:5px 8px;border-bottom:1px solid #eee'><b>{b.get('name','')}</b></td><td style='padding:5px 8px;border-bottom:1px solid #eee'>{b.get('address','')}</td><td style='padding:5px 8px;border-bottom:1px solid #eee'>{b.get('cost_center','')}</td><td style='padding:5px 8px;border-bottom:1px solid #eee'>{hours}</td><td style='padding:5px 8px;border-bottom:1px solid #eee'>{b.get('details','')}</td></tr>"

    branch_section = f"<table style='border-collapse:collapse;width:100%;font-size:12px'><tr style='background:#321e57;color:#fff'><th style='padding:6px 8px'>#</th><th style='padding:6px 8px'>Branch Name</th><th style='padding:6px 8px'>Address</th><th style='padding:6px 8px'>Cost Center</th><th style='padding:6px 8px'>Hours</th><th style='padding:6px 8px'>Details</th></tr>{branch_rows}</table>" if branch_rows else "<i>No branch data provided.</i>"

    def file_line(label, urls, manual_link):
        parts = [f'<a href="{u}" target="_blank">View File</a>' for u in urls if u]
        if manual_link: parts.append(f'<a href="{manual_link}" target="_blank">{manual_link}</a>')
        return f"{label}: " + (" | ".join(parts) if parts else "—")

    files_block = (
        file_line("Invoices", file_links["invoices"], d.get("invoices_link", "")) + "<br>" +
        file_line("Supplier Details", file_links["suppliers"], d.get("suppliers_link", "")) + "<br>" +
        file_line("Recipes", file_links["recipes"], d.get("recipes_link", ""))
    )

    note = (
        f"<h3 style='color:#321e57;margin:0 0 4px'>SUPY ONBOARDING</h3>"
        f"<p style='color:#888;font-size:11px;margin:0 0 16px'>Submitted: {submitted}</p>"
        f"<h4 style='color:#503390;border-bottom:1px solid #e0d8f0;padding-bottom:4px;margin:14px 0 8px'>COMPANY INFO</h4>Company Name: {d.get('company_name', '')}"
        f"<h4 style='color:#503390;border-bottom:1px solid #e0d8f0;padding-bottom:4px;margin:14px 0 8px'>INTERNAL CHAMPION</h4>Name: {d.get('champion_name', '')}<br>Title: {d.get('champion_title', '')}<br>Email: {d.get('champion_email', '')}<br>Phone: {d.get('champion_phone', '')}"
        f"<h4 style='color:#503390;border-bottom:1px solid #e0d8f0;padding-bottom:4px;margin:14px 0 8px'>FINANCE POC</h4>External Accounting Firm: {d.get('accounting_external', '')}<br>Name: {d.get('finance_name', '')}<br>Title: {d.get('finance_title', '')}<br>Email: {d.get('finance_email', '')}<br>Phone: {d.get('finance_phone', '')}"
        f"<h4 style='color:#503390;border-bottom:1px solid #e0d8f0;padding-bottom:4px;margin:14px 0 8px'>IT CONTACT</h4>{it_block}"
        f"<h4 style='color:#503390;border-bottom:1px solid #e0d8f0;padding-bottom:4px;margin:14px 0 8px'>BRANCH CONFIGURATION</h4>{branch_section}"
        f"<h4 style='color:#503390;border-bottom:1px solid #e0d8f0;padding-bottom:4px;margin:14px 0 8px'>OPERATIONS</h4>Order Method: {d.get('ordering_method', '')}<br>PO Approver: {d.get('po_approver', '')}<br>Ordering Structure: {d.get('ordering_structure', '')}<br>Stock Counts: {d.get('stock_counts', '')}<br>Stock Count Duration: {d.get('stock_count_duration', '')}<br>Inventory System: {d.get('inventory_system', '')}"
        f"<h4 style='color:#503390;border-bottom:1px solid #e0d8f0;padding-bottom:4px;margin:14px 0 8px'>FOOD COST</h4>Current Food Cost %: {d.get('food_cost_current', '')}<br>Target Food Cost %: {d.get('food_cost_target', '')}<br>COGS Method: {d.get('cogs_method', '')}<br>Invoice Delivery: {d.get('invoice_delivery', '')}<br>Finance Complications: {d.get('finance_complications', '')}"
        f"<h4 style='color:#503390;border-bottom:1px solid #e0d8f0;padding-bottom:4px;margin:14px 0 8px'>GOALS &amp; BLOCKERS</h4>Top Problem to Solve: {d.get('top_problem', '')}<br>CSM Notes: {d.get('extra_notes', '')}<br>Known Blockers: {d.get('blockers', '')}<br>Target Go-Live: {d.get('golive_date', '')}"
        f"<h4 style='color:#503390;border-bottom:1px solid #e0d8f0;padding-bottom:4px;margin:14px 0 8px'>UPLOADED FILES</h4>{files_block}"
    )
    return note

@app.route("/webhook", methods=["POST", "OPTIONS"])
def webhook():
    if request.method == "OPTIONS":
        resp = app.make_default_options_response()
        resp.headers["Access-Control-Allow-Origin"]  = "*"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
        resp.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        return resp

    d = request.form.to_dict()
    email = d.get("champion_email", "").strip()
    if not email:
        return jsonify({"error": "No champion email provided"}), 400

    print(f"\n{'='*55}\nNEW SUBMISSION from: {email}\n{'='*55}")

    # ── Upload Files to Google Drive ──
    file_links = {"invoices": [], "suppliers": [], "recipes": []}
    
    try:
        # Authenticate with Google Drive
        creds = service_account.Credentials.from_service_account_info(
            SERVICE_ACCOUNT_INFO, scopes=['https://www.googleapis.com/auth/drive']
        )
        drive_service = build('drive', 'v3', credentials=creds)

        # Create a unique subfolder for this client
        folder_name = f"{d.get('company_name', 'Client')} - {email} - {datetime.now().strftime('%Y-%m-%d')}"
        subfolder = drive_service.files().create(
            body={'name': folder_name, 'mimeType': 'application/vnd.google-apps.folder', 'parents': [PARENT_FOLDER_ID]}, 
            fields='id'
        ).execute()
        subfolder_id = subfolder.get('id')

        # Upload files to the new folder
        for field_name, category in [("invoices_files", "invoices"), ("suppliers_files", "suppliers"), ("recipes_files", "recipes")]:
            for f in request.files.getlist(field_name):
                url = upload_to_drive(f, subfolder_id, drive_service)
                if url: 
                    file_links[category].append(url)
                    print(f"   Uploaded file to Drive: {f.filename}")
    except Exception as e:
        print(f"   [Drive Folder Setup Error]: {e}")

    # ── Parse Branch Data ──
    branches = []
    try:
        branches = json.loads(d.get("branches_json", "[]"))
    except Exception:
        pass

    # ── HubSpot Operations ──
    token = get_access_token()
    if not token:
        print("   ERROR: Could not get HubSpot access token.")
        return jsonify({"error": "HubSpot auth failed"}), 500

    contact_id = upsert_contact(
        token, email, 
        d.get("champion_name", "").split()[0] if d.get("champion_name") else "Client", 
        " ".join(d.get("champion_name", "").split()[1:]) if len(d.get("champion_name", "").split()) > 1 else "",
        d.get("champion_phone", ""), d.get("champion_title", "")
    )

    if not contact_id:
        print("   ERROR: HubSpot refused to create or update the contact.")
        return jsonify({"error": "Contact upsert failed"}), 400

    note_body = build_note(d, branches, file_links)
    
    # Create Note in HubSpot (CRITICAL FIX: Using v3 API)
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    note_payload = {
        "properties": {
            "hs_timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "hs_note_body": note_body
        }
    }
    note_r = requests.post("https://api.hubapi.com/crm/v3/objects/notes", headers=headers, json=note_payload)
    
    if note_r.status_code == 201:
        note_id = note_r.json().get('id')
        assoc_payload = {"inputs": [{"from": {"id": note_id}, "to": {"id": contact_id}, "type": "note_to_contact"}]}
        requests.post("https://api.hubapi.com/crm/v3/associations/Notes/Contacts/batch/create", headers=headers, json=assoc_payload)
        print(f"   Done — contact {contact_id} updated with note.")
    else:
        print(f"   [HubSpot Note Error]: {note_r.text}")

    return jsonify({"status": "ok"}), 200

@app.route("/")
def index():
    return "Supy Onboarding Server is running.", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
