import os
import json
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime

app = Flask(__name__)
CORS(app)

# ── HubSpot credentials ───────────────────────────────────────────
CLIENT_ID     = os.environ.get("CLIENT_ID",     "d5f491d5-9206-422b-97b1-e037b4f06c45")
CLIENT_SECRET = os.environ.get("CLIENT_SECRET", "ce5b4a8c-72ee-4ccc-91b6-25a40a7815c0")
REFRESH_TOKEN = os.environ.get("REFRESH_TOKEN", "na1-ddcd-e6ae-4cf6-82b3-439b1efaa389")
NETLIFY_SITE  = "wonderful-pothos-f912a1"


def get_access_token():
    r = requests.post("https://api.hubapi.com/oauth/v1/token", data={
        "grant_type":    "refresh_token",
        "client_id":     CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": REFRESH_TOKEN,
    })
    data = r.json()
    token = data.get("access_token")
    if not token:
        print(f"   Token error: {data}")
    return token


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
        requests.patch(
            f"https://api.hubapi.com/crm/v3/objects/contacts/{contact_id}",
            headers=headers,
            json={"properties": props}
        )
        print(f"   Updated existing contact {contact_id}")
        return contact_id
    else:
        create_r = requests.post(
            "https://api.hubapi.com/crm/v3/objects/contacts",
            headers=headers,
            json={"properties": props}
        )
        rj = create_r.json()
        contact_id = rj.get("id")
        if not contact_id:
            print(f"   Create contact error: {rj}")
        else:
            print(f"   Created new contact {contact_id}")
        return contact_id


def create_note(token, contact_id, note_body):
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    now_ms = int(datetime.utcnow().timestamp() * 1000)
    eng_r = requests.post(
        "https://api.hubapi.com/engagements/v1/engagements",
        headers=headers,
        json={
            "engagement": {"active": True, "type": "NOTE", "timestamp": now_ms},
            "associations": {"contactIds": [int(contact_id)]},
            "metadata": {"body": note_body}
        }
    )
    print(f"   Note status: {eng_r.status_code}")
    if eng_r.status_code not in (200, 201):
        print(f"   Note error: {eng_r.text}")


def build_note(d, branches, uploaded_files):
    submitted = datetime.utcnow().strftime("%-d %b %Y at %H:%M UTC")

    it_same = d.get("it_same_as_champion", "").lower()
    if it_same == "yes":
        it_block = (
            "<b>Same as Internal Champion</b> — "
            + d.get("champion_name", "") + " (" + d.get("champion_email", "") + ")"
        )
    else:
        it_block = (
            "Name: " + d.get("it_name", "") + "<br>"
            + "Title: " + d.get("it_title", "") + "<br>"
            + "Email: " + d.get("it_email", "") + "<br>"
            + "Phone: " + d.get("it_phone", "") + "<br>"
            + "POS System: " + d.get("pos_system", "") + "<br>"
            + "Accounting SW: " + d.get("accounting_software", "")
        )

    branch_rows = ""
    for i, b in enumerate(branches, 1):
        hours = (b.get("open", "") + " – " + b.get("close", "")).strip(" –")
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

    if branch_rows:
        branch_section = (
            "<table style='border-collapse:collapse;width:100%;font-size:12px'>"
            "<tr style='background:#321e57;color:#fff'>"
            "<th style='padding:6px 8px'>#</th>"
            "<th style='padding:6px 8px'>Branch Name</th>"
            "<th style='padding:6px 8px'>Address</th>"
            "<th style='padding:6px 8px'>Cost Center</th>"
            "<th style='padding:6px 8px'>Hours</th>"
            "<th style='padding:6px 8px'>Details</th>"
            "</tr>"
            + branch_rows + "</table>"
        )
    else:
        branch_section = "<i>No branch data provided.</i>"

    def file_line(label, category_key, manual_link):
        parts = []
        for f in uploaded_files.get(category_key, []):
            name = f.get("name", "File")
            url  = f.get("url", "#")
            parts.append(f'<a href="{url}" target="_blank">{name}</a>')
        if manual_link:
            parts.append(f'<a href="{manual_link}" target="_blank">{manual_link}</a>')
        return label + ": " + (" / ".join(parts) if parts else "—")

    files_block = (
        file_line("Invoices",         "invoices",  d.get("invoices_link",  "")) + "<br>"
        + file_line("Supplier Details", "suppliers", d.get("suppliers_link", "")) + "<br>"
        + file_line("Recipes",          "recipes",   d.get("recipes_link",   ""))
    )

    note = (
        "<h3 style='color:#321e57;margin:0 0 4px'>SUPY ONBOARDING</h3>"
        "<p style='color:#888;font-size:11px;margin:0 0 16px'>Submitted: " + submitted + "</p>"

        "<h4 style='color:#503390;border-bottom:1px solid #e0d8f0;padding-bottom:4px;margin:14px 0 8px'>INTERNAL CHAMPION</h4>"
        "Name: " + d.get("champion_name", "") + "<br>"
        "Title: " + d.get("champion_title", "") + "<br>"
        "Email: " + d.get("champion_email", "") + "<br>"
        "Phone: " + d.get("champion_phone", "")

        + "<h4 style='color:#503390;border-bottom:1px solid #e0d8f0;padding-bottom:4px;margin:14px 0 8px'>FINANCE POC</h4>"
        "External Accounting Firm: " + d.get("accounting_external", "") + "<br>"
        "Name: " + d.get("finance_name", "") + "<br>"
        "Title: " + d.get("finance_title", "") + "<br>"
        "Email: " + d.get("finance_email", "") + "<br>"
        "Phone: " + d.get("finance_phone", "")

        + "<h4 style='color:#503390;border-bottom:1px solid #e0d8f0;padding-bottom:4px;margin:14px 0 8px'>IT CONTACT</h4>"
        + it_block

        + "<h4 style='color:#503390;border-bottom:1px solid #e0d8f0;padding-bottom:4px;margin:14px 0 8px'>BRANCH CONFIGURATION</h4>"
        + branch_section

        + "<h4 style='color:#503390;border-bottom:1px solid #e0d8f0;padding-bottom:4px;margin:14px 0 8px'>OPERATIONS</h4>"
        "Order Method: " + d.get("ordering_method", "") + "<br>"
        "PO Approver: " + d.get("po_approver", "") + "<br>"
        "Ordering Structure: " + d.get("ordering_structure", "") + "<br>"
        "Stock Counts: " + d.get("stock_counts", "") + "<br>"
        "Stock Count Duration: " + d.get("stock_count_duration", "") + "<br>"
        "Inventory System: " + d.get("inventory_system", "")

        + "<h4 style='color:#503390;border-bottom:1px solid #e0d8f0;padding-bottom:4px;margin:14px 0 8px'>FOOD COST</h4>"
        "Current Food Cost %: " + d.get("food_cost_current", "") + "<br>"
        "Target Food Cost %: " + d.get("food_cost_target", "") + "<br>"
        "COGS Method: " + d.get("cogs_method", "") + "<br>"
        "Invoice Delivery: " + d.get("invoice_delivery", "") + "<br>"
        "Finance Complications: " + d.get("finance_complications", "")

        + "<h4 style='color:#503390;border-bottom:1px solid #e0d8f0;padding-bottom:4px;margin:14px 0 8px'>GOALS &amp; BLOCKERS</h4>"
        "Top Problem to Solve: " + d.get("top_problem", "") + "<br>"
        "CSM Notes: " + d.get("extra_notes", "") + "<br>"
        "Known Blockers: " + d.get("blockers", "") + "<br>"
        "Target Go-Live: " + d.get("golive_date", "")

        + "<h4 style='color:#503390;border-bottom:1px solid #e0d8f0;padding-bottom:4px;margin:14px 0 8px'>UPLOADED FILES</h4>"
        + files_block

        + "<p style='margin-top:14px;font-size:10px;color:#aaa'>"
        "Download files: <a href='https://app.netlify.com/sites/" + NETLIFY_SITE + "/forms'>Netlify Forms Dashboard</a></p>"
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

    print(f"\n{'='*55}")
    print(f"NEW SUBMISSION from: {email}")
    print(f"{'='*55}")

    # Parse Supabase uploaded files JSON
    uploaded_files = {"invoices": [], "suppliers": [], "recipes": []}
    raw = d.get("uploaded_files_json", "{}")
    print(f"   uploaded_files_json: {raw[:300]}")
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            uploaded_files = parsed
            total = sum(len(v) for v in uploaded_files.values())
            print(f"   Files parsed OK — {total} total files")
    except Exception as e:
        print(f"   Error parsing uploaded_files_json: {e}")

    # Parse branches JSON
    branches = []
    try:
        branches = json.loads(d.get("branches_json", "[]"))
    except Exception as e:
        print(f"   Error parsing branches_json: {e}")
    print(f"   Branches: {len(branches)}")

    # Get token
    token = get_access_token()
    if not token:
        return jsonify({"error": "HubSpot auth failed"}), 500

    full_name  = d.get("champion_name", "").strip()
    name_parts = full_name.split() if full_name else ["Client"]
    firstname  = name_parts[0]
    lastname   = " ".join(name_parts[1:]) if len(name_parts) > 1 else ""

    contact_id = upsert_contact(
        token, email, firstname, lastname,
        d.get("champion_phone", ""),
        d.get("champion_title", "")
    )

    if not contact_id:
        return jsonify({"error": "Contact upsert failed"}), 500

    note_body = build_note(d, branches, uploaded_files)
    create_note(token, contact_id, note_body)

    print(f"   Done — contact {contact_id} updated with note.")
    return jsonify({"status": "ok", "contact_id": contact_id}), 200


@app.route("/")
def index():
    return "Supy Onboarding Server is running.", 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
