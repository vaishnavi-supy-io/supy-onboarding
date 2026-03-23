import os
from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
from datetime import datetime

app = Flask(__name__)
CORS(app)

CLIENT_ID     = os.environ.get("CLIENT_ID", "d5f491d5-9206-422b-97b1-e037b4f06c45")
CLIENT_SECRET = os.environ.get("CLIENT_SECRET", "ce5b4a8c-3d53-4579-bbf6-783f9a149ab1")
REFRESH_TOKEN = os.environ.get("REFRESH_TOKEN", "na1-ddcd-e6ae-4cf6-82b3-439b1efaa389")
NETLIFY_FORMS_URL = "https://app.netlify.com/sites/wonderful-pothos-f912a1/forms"

def get_token():
    r = requests.post("https://api.hubapi.com/oauth/v1/token", data={
        "grant_type":    "refresh_token",
        "client_id":     CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": REFRESH_TOKEN
    })
    return r.json().get("access_token")

def row(label, value):
    v = str(value).strip() if value else ''
    if not v or v.lower() == 'none':
        return ''
    return '<b>' + label + ':</b> ' + v + '<br>'

@app.route('/', methods=['GET'])
def health():
    return 'Supy Onboarding Server is running.', 200

@app.route('/webhook', methods=['POST', 'OPTIONS'])
def handle():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    try:
        d = request.form.to_dict()
        email = d.get('champion_email', '').strip()

        if not email:
            return jsonify({"error": "No email"}), 400

        print("NEW SUBMISSION from: " + email)

        # Collect uploaded filenames
        file_names = {}
        for field in ['invoices', 'supplier_details', 'recipe_list']:
            files = request.files.getlist(field)
            names = [f.filename for f in files if f and f.filename]
            file_names[field] = ', '.join(names) if names else None

        token = get_token()
        headers = {'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'}

        # Search for existing contact
        search = requests.post(
            'https://api.hubapi.com/crm/v3/objects/contacts/search',
            headers=headers,
            json={"filterGroups": [{"filters": [{"propertyName": "email", "operator": "EQ", "value": email}]}]}
        ).json()

        name  = d.get('champion_name', 'New User').strip()
        parts = name.split()
        phone = d.get('champion_phone', '')

        props = {
            "email":     email,
            "firstname": parts[0],
            "lastname":  ' '.join(parts[1:]) if len(parts) > 1 else 'User',
            "jobtitle":  d.get('champion_title', '')
        }
        if phone.startswith('+'):
            props["phone"] = phone

        cid = None
        if search.get('total', 0) > 0:
            cid = search['results'][0]['id']
            requests.patch('https://api.hubapi.com/crm/v3/objects/contacts/' + cid,
                           headers=headers, json={"properties": props})
            print("Contact updated: " + cid)
        else:
            r = requests.post('https://api.hubapi.com/crm/v3/objects/contacts',
                              headers=headers, json={"properties": props})
            cid = r.json().get('id')
            print("Contact created: " + str(cid))

        if not cid:
            return jsonify({"error": "no contact id"}), 500

        def file_row(label, field):
            names = file_names.get(field)
            link  = d.get(field + '_link', '').strip()
            out = ''
            if names:
                out += '<b>' + label + ':</b> ' + names + '<br>'
            if link:
                out += '<b>' + label + ' Link:</b> <a href="' + link + '">' + link + '</a><br>'
            if not names and not link:
                out += '<b>' + label + ':</b> Not provided<br>'
            return out

        it_same = d.get('it_same_as_champion', '').lower()
        if it_same == 'yes':
            it_section = (
                '<h3>IT CONTACT</h3>'
                '<b>Same as Internal Champion</b> — '
                + d.get('champion_name','') + ' (' + d.get('champion_email','') + ')<br>'
                + row('POS System', d.get('pos_system'))
                + row('Accounting Software', d.get('accounting_software'))
                + '<br>'
            )
        else:
            it_section = (
                '<h3>IT CONTACT</h3>'
                + row('Name', d.get('it_name'))
                + row('Title', d.get('it_title'))
                + row('Email', d.get('it_email'))
                + row('Phone', d.get('it_phone'))
                + row('POS System', d.get('pos_system'))
                + row('Accounting Software', d.get('accounting_software'))
                + '<br>'
            )

        submitted = datetime.now().strftime('%d %b %Y at %H:%M')

        note = (
            '<h2>SUPY ONBOARDING</h2>'
            '<p><b>Submitted:</b> ' + submitted + '</p><br>'
            '<h3>INTERNAL CHAMPION</h3>'
            + row('Name', d.get('champion_name'))
            + row('Title', d.get('champion_title'))
            + row('Email', d.get('champion_email'))
            + row('Phone', d.get('champion_phone'))
            + '<br>'
            '<h3>FINANCE POC</h3>'
            + row('External Accounting Firm', d.get('accounting_external'))
            + row('Name', d.get('finance_name'))
            + row('Title', d.get('finance_title'))
            + row('Email', d.get('finance_email'))
            + row('Phone', d.get('finance_phone'))
            + '<br>'
            + it_section
            + '<h3>OPERATIONS</h3>'
            + row('Order Method', d.get('order_method'))
            + row('PO Approver', d.get('po_approver'))
            + row('Ordering Structure', d.get('ordering_structure'))
            + row('Stock Counts', d.get('stock_count_freq'))
            + row('Stock Count Duration', d.get('stock_count_duration'))
            + row('Inventory System', d.get('inventory_system'))
            + '<br>'
            '<h3>FOOD COST</h3>'
            + row('Current Food Cost %', d.get('current_food_cost'))
            + row('Target Food Cost %', d.get('target_food_cost'))
            + row('COGS Method', d.get('cogs_method'))
            + row('Invoice Delivery', d.get('invoice_delivery'))
            + row('Finance Complications', d.get('accounting_complications'))
            + '<br>'
            '<h3>GOALS AND BLOCKERS</h3>'
            + row('Top Problem to Solve', d.get('top_problem'))
            + row('CSM Notes', d.get('csm_notes'))
            + row('Known Blockers', d.get('known_blockers'))
            + row('Target Go-Live', d.get('target_golive_date'))
            + '<br>'
            '<h3>UPLOADED FILES</h3>'
            + file_row('Invoices', 'invoices')
            + file_row('Supplier Details', 'supplier_details')
            + file_row('Recipe List', 'recipe_list')
            + '<br>'
            + '<p><b>Download files:</b> <a href="' + NETLIFY_FORMS_URL + '">Netlify Forms Dashboard</a></p>'
        )

        note_r = requests.post(
            'https://api.hubapi.com/crm/v3/objects/notes',
            headers=headers,
            json={
                "properties": {
                    "hs_note_body": note,
                    "hs_timestamp": str(int(datetime.now().timestamp() * 1000))
                },
                "associations": [{"to": {"id": cid}, "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 202}]}]
            }
        )
        print("Note status: " + str(note_r.status_code))
        return jsonify({"status": "success"}), 200

    except Exception as e:
        print("ERROR: " + str(e))
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
