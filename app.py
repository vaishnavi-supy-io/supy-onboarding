import os
import json
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime

app = Flask(__name__)
CORS(app)

# ── HubSpot Credentials ───────────────────────────────────────────
CLIENT_ID     = os.environ.get("CLIENT_ID",     "d5f491d5-9206-422b-97b1-e037b4f06c45")
CLIENT_SECRET = os.environ.get("CLIENT_SECRET", "ce5b4a8c-72ee-4ccc-91b6-25a40a7815c0")
REFRESH_TOKEN = os.environ.get("REFRESH_TOKEN", "na1-ddcd-e6ae-4cf6-82b3-439b1efaa389")

# ── Supabase Credentials ──────────────────────────────────────────
SUPABASE_URL         = "https://zwswlfugdzlxroqzwpfv.supabase.co"
# REVEAL AND PASTE THE 'service_role' SECRET KEY FROM SUPABASE SETTINGS
SUPABASE_SERVICE_KEY = "PASTE_YOUR_SECRET_SERVICE_ROLE_KEY_HERE" 
SUPABASE_BUCKET      = "onboarding-files"

def get_access_token():
    r = requests.post("https://api.hubapi.com/oauth/v1/token", data={
        "grant_type":    "refresh_token",
        "client_id":     CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": REFRESH_TOKEN,
    })
    return r.json().get("access_token")

def upload_to_supabase(file_obj, category, email):
    """Uploads file to Supabase using the Service Key (bypasses RLS)"""
    if not file_obj or not file_obj.filename:
        return None
    
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    safe_name = "".join([c if c.isalnum() or c in "._-" else "_" for c in file_obj.filename])
    path = f"{category}/{timestamp}_{safe_name}"
    
    upload_url = f"{SUPABASE_URL}/storage/v1/object/{SUPABASE_BUCKET}/{path}"
    
    headers = {
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "apikey": SUPABASE_SERVICE_KEY,
        "Content-Type": file_obj.content_type or "application/octet-stream",
        "x-upsert": "true"
    }
    
    # Read file content and upload
    file_data = file_obj.read()
    r = requests.post(upload_url, headers=headers, data=file_data)
    
    if r.status_code == 200:
        return f"{SUPABASE_URL}/storage/v1/object/public/{SUPABASE_BUCKET}/{path}"
    else:
        print(f"   Supabase error: {r.status_code} - {r.text}")
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
        requests.patch(f"https://api.hubapi.com/crm/v3/objects/contacts/{contact_id}", headers=headers, json={"properties": props})
        return contact_id
    else:
        create_r = requests.post("https://api.hubapi.com/crm/v3/objects/contacts", headers=headers, json={"properties": props})
        return create_r.json().get("id")

def build_note(d, branches, file_links):
    submitted = datetime.utcnow().strftime("%-d %b %Y at %H:%M UTC")
    
    it_same = d.get("it_same_as_champion", "").lower()
    it_block = f"<b>Same as Internal Champion</b>" if it_same == "yes" else \
               f"Name: {d.get('it_name','')}<br>Email: {d.get('it_email','')}<br>POS: {d.get('pos_system','')}"

    def link_list(label, urls):
        if not urls: return f"{label}: —"
        links = [f'<a href="{u}" target="_blank">View File</a>' for u in urls]
        return f"{label}: " + " | ".join(links)

    note = (
        f"<h3 style='color:#321e57;'>SUPY ONBOARDING</h3>"
        f"<p>Submitted: {submitted}</p>"
        f"<h4>COMPANY INFO</h4>Company: {d.get('company_name','')}<br>"
        f"<h4>INTERNAL CHAMPION</h4>{d.get('champion_name','')} ({d.get('champion_email','')})<br>"
        f"<h4>IT CONTACT</h4>{it_block}<br>"
        f"<h4>UPLOADED FILES</h4>"
        f"{link_list('Invoices', file_links['invoices'])}<br>"
        f"{link_list('Suppliers', file_links['suppliers'])}<br>"
        f"{link_list('Recipes', file_links['recipes'])}<br>"
    )
    return note

@app.route("/webhook", methods=["POST", "OPTIONS"])
def webhook():
    if request.method == "OPTIONS":
        resp = app.make_default_options_response()
        resp.headers["Access-Control-Allow-Origin"] = "*"
        return resp

    d = request.form.to_dict()
    email = d.get("champion_email", "").strip()
    
    # ── SERVER-SIDE FILE UPLOADS ──
    file_links = {"invoices": [], "suppliers": [], "recipes": []}
    for field, cat in [("invoices_files", "invoices"), ("suppliers_files", "suppliers"), ("recipes_files", "recipes")]:
        files = request.files.getlist(field)
        for f in files:
            url = upload_to_supabase(f, cat, email)
            if url: file_links[cat].append(url)

    # Parse branches
    try: branches = json.loads(d.get("branches_json", "[]"))
    except: branches = []

    token = get_access_token()
    contact_id = upsert_contact(token, email, d.get("champion_name",""), "", d.get("champion_phone",""), d.get("champion_title",""))
    
    note_body = build_note(d, branches, file_links)
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    requests.post("https://api.hubapi.com/engagements/v1/engagements", headers=headers, json={
        "engagement": {"active": True, "type": "NOTE", "timestamp": int(datetime.utcnow().timestamp() * 1000)},
        "associations": {"contactIds": [int(contact_id)]},
        "metadata": {"body": note_body}
    })

    return jsonify({"status": "ok"}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
