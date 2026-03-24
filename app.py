import os
import json
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime, timezone

app = Flask(__name__)
CORS(app)

# ── HubSpot Credentials ───────────────────────────────────────────
CLIENT_ID     = os.environ.get("CLIENT_ID",     "d5f491d5-9206-422b-97b1-e037b4f06c45")
CLIENT_SECRET = os.environ.get("CLIENT_SECRET", "ce5b4a8c-72ee-4ccc-91b6-25a40a7815c0")
REFRESH_TOKEN = os.environ.get("REFRESH_TOKEN", "na1-ddcd-e6ae-4cf6-82b3-439b1efaa389")

# ── Supabase Credentials ──────────────────────────────────────────
SUPABASE_URL         = "https://zwswlfugdzlxroqzwpfv.supabase.co"
SUPABASE_BUCKET      = "onboarding-files"
SUPABASE_SERVICE_KEY = "sb_secret_MN4pUJDnwapwBkZsXyYiGw_IAtX-fsU" 

def get_access_token():
    r = requests.post("https://api.hubapi.com/oauth/v1/token", data={
        "grant_type":    "refresh_token",
        "client_id":     CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": REFRESH_TOKEN,
    })
    if r.status_code != 200:
        print(f"   [HubSpot Token Error]: {r.text}")
    return r.json().get("access_token")

def upload_to_supabase(file_obj, category, email):
    if not file_obj or not file_obj.filename:
        return None
    
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    safe_name = "".join([c if c.isalnum() or c in "._-" else "_" for c in file_obj.filename])
    path = f"{category}/{timestamp}_{safe_name}"
    
    upload_url = f"{SUPABASE_URL}/storage/v1/object/{SUPABASE_BUCKET}/{path}"
    
    headers = {
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": file_obj.content_type or "application/octet-stream",
        "x-upsert": "true"
    }
    
    file_data = file_obj.read()
    r = requests.post(upload_url, headers=headers, data=file_data)
    
    if r.status_code == 200:
        return f"{SUPABASE_URL}/storage/v1/object/public/{SUPABASE_BUCKET}/{path}"
    else:
        print(f"   [Supabase Upload Error]: {r.status_code} - {r.text}")
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
    # HubSpot requires phone numbers to start with +
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
        parts = [f'<a href="{u}" target="_blank">View File</a>' for u in urls]
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

    # ── Upload Files to Supabase from the Server ──
    file_links = {"invoices": [], "suppliers": [], "recipes": []}
    for field_name, category in [("invoices_files", "invoices"), ("suppliers_files", "suppliers"), ("recipes_files", "recipes")]:
        for f in request.files.getlist(field_name):
            url = upload_to_supabase(f, category, email)
            if url: 
                file_links[category].append(url)
                print(f"   Uploaded file: {f.filename}")

    branches = []
    try:
        branches = json.loads(d.get("branches_json", "[]"))
    except Exception:
        pass

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

    # --- THE CRITICAL FIX IS HERE ---
    if not contact_id:
        print("   ERROR: HubSpot refused to create or update the contact. Check the logs above for the specific error.")
        return jsonify({"error": "Contact upsert failed"}), 400

    note_body = build_note(d, branches, file_links)
    
    # Create Note in HubSpot
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    note_r = requests.post("https://api.hubapi.com/engagements/v1/engagements", headers=headers, json={
        "engagement": {"active": True, "type": "NOTE", "timestamp": int(datetime.now(timezone.utc).timestamp() * 1000)},
        "associations": {"contactIds": [int(contact_id)]},
        "metadata": {"body": note_body}
    })
    
    if note_r.status_code not in (200, 201):
        print(f"   [HubSpot Note Error]: {note_r.text}")

    print(f"   Done — contact {contact_id} updated with note.")
    return jsonify({"status": "ok"}), 200

@app.route("/")
def index():
    return "Supy Onboarding Server is running.", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
