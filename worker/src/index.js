/**
 * Supy Onboarding — Cloudflare Worker
 *
 * Drop-in replacement for the PythonAnywhere Flask server.
 * Env vars (set as Worker Secrets via wrangler or the dashboard):
 *   CLIENT_ID, CLIENT_SECRET, REFRESH_TOKEN          — HubSpot OAuth
 *   GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET,
 *   GMAIL_REFRESH_TOKEN                              — Gmail OAuth
 *   SLACK_WEBHOOK_URL                                — Slack incoming webhook
 *   GOOGLE_SCRIPT_URL                                — Google Apps Script URL
 *
 * KV binding (optional — for /logs endpoint):
 *   LOGS  →  bound in wrangler.toml as [[kv_namespaces]]
 *
 * File uploads:
 *   Files are uploaded to HubSpot File Manager (Files v3 API).
 *   No extra secrets needed — uses the same HubSpot OAuth credentials.
 *   Files are stored under supy-onboarding/{date}_{company}/ and are publicly accessible.
 *
 * Routes:
 *   POST /webhook      — main form handler
 *   POST /upload       — receive a file, store to Supabase, return public URL
 *   GET  /logs         — recent submission log
 *   GET  /             — health check
 */

const HUBSPOT_PORTAL_ID = "9423176";
const EMAIL_FROM        = "vaishnavi@supy.io";
const EMAIL_RECIPIENTS  = ["vaishnavi@supy.io", "randhir@supy.io", "kenneth@supy.io"];

// ─────────────────────────────────────────────────────────────
// CORS helpers
// ─────────────────────────────────────────────────────────────
const CORS_HEADERS = {
  "Access-Control-Allow-Origin":  "*",
  "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};

function withCors(response) {
  const r = new Response(response.body, response);
  for (const [k, v] of Object.entries(CORS_HEADERS)) r.headers.set(k, v);
  return r;
}

function json(data, status = 200) {
  return withCors(new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  }));
}

// ─────────────────────────────────────────────────────────────
// Main entry
// ─────────────────────────────────────────────────────────────
export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: CORS_HEADERS });
    }

    if (url.pathname === "/webhook" && request.method === "POST") {
      return handleWebhook(request, env);
    }

    if (url.pathname === "/draft/save" && request.method === "POST") {
      return handleDraftSave(request, env);
    }

    if (url.pathname === "/draft/load" && request.method === "GET") {
      return handleDraftLoad(request, env);
    }

    if (url.pathname === "/upload" && request.method === "POST") {
      return handleUpload(request, env);
    }

    if (url.pathname === "/download" && request.method === "GET") {
      return handleDownload(request, env);
    }

    if (url.pathname === "/logs" && request.method === "GET") {
      return handleLogs(env);
    }





    if (url.pathname === "/cloudinary-audit" && request.method === "GET") {
      // List all resources grouped by type — helps find image-type files needing conversion
      const prefix = url.searchParams.get("prefix") || "supy-onboarding";
      const auth   = btoa(`${env.CLOUDINARY_API_KEY}:${env.CLOUDINARY_API_SECRET}`);
      const results = { raw: [], image: [], private_raw: [], private_image: [] };
      for (const rt of ["raw", "image"]) {
        for (const tp of ["upload", "private"]) {
          const r = await fetch(
            `https://api.cloudinary.com/v1_1/${env.CLOUDINARY_CLOUD_NAME}/resources/${rt}?type=${tp}&prefix=${encodeURIComponent(prefix)}&max_results=100`,
            { headers: { Authorization: `Basic ${auth}` } }
          );
          if (r.ok) {
            const body = await r.json();
            const key = `${tp === "private" ? "private_" : ""}${rt}`;
            results[key] = (body.resources || []).map(x => ({ id: x.public_id, bytes: x.bytes, format: x.format }));
          }
        }
      }
      return json(results);
    }

    if (url.pathname === "/cloudinary-batch-fix" && request.method === "POST") {
      try {
      // Convert all image-type/upload resources to type=private so image/download API works.
      // POST body: { prefix: "supy-onboarding" }  (optional, defaults to supy-onboarding)
      const body    = await request.json().catch(() => ({}));
      const prefix  = body.prefix || "supy-onboarding";
      const auth    = btoa(`${env.CLOUDINARY_API_KEY}:${env.CLOUDINARY_API_SECRET}`);
      const ts      = Math.floor(Date.now() / 1000).toString();

      // Workers allow ~50 subrequests/invocation; we use 1 for list + up to 45 renames.
      const next_cursor = body.next_cursor || null;
      let listUrl = `https://api.cloudinary.com/v1_1/${env.CLOUDINARY_CLOUD_NAME}/resources/image?type=upload&prefix=${encodeURIComponent(prefix)}&max_results=45`;
      if (next_cursor) listUrl += `&next_cursor=${encodeURIComponent(next_cursor)}`;

      const listRes = await fetch(listUrl, { headers: { Authorization: `Basic ${auth}` } });
      if (!listRes.ok) return json({ error: `List failed: ${listRes.status}` }, 500);
      const listBody = await listRes.json();
      const resources = listBody.resources || [];

      async function convertOne(pid) {
        const sigParts = [`from_public_id=${pid}`, `timestamp=${ts}`, `to_public_id=${pid}`, `to_type=private`, `type=upload`];
        sigParts.sort();
        const sigBuf = await crypto.subtle.digest("SHA-1", new TextEncoder().encode(sigParts.join("&") + env.CLOUDINARY_API_SECRET));
        const signature = Array.from(new Uint8Array(sigBuf)).map(b => b.toString(16).padStart(2, "0")).join("");
        const form = new URLSearchParams({ from_public_id: pid, to_public_id: pid, to_type: "private", type: "upload", timestamp: ts, api_key: env.CLOUDINARY_API_KEY, signature });
        const r = await fetch(`https://api.cloudinary.com/v1_1/${env.CLOUDINARY_CLOUD_NAME}/image/rename`,
          { method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" }, body: form.toString() });
        if (r.ok) return { ok: true, pid };
        const err = await r.text().catch(() => String(r.status));
        return { ok: false, pid, error: err };
      }

      const converted = [], failed = [];
      const outcomes = await Promise.all(resources.map(res => convertOne(res.public_id)));
      for (const o of outcomes) {
        if (o.ok) converted.push(o.pid); else failed.push({ pid: o.pid, error: o.error });
      }
      return json({
        converted: converted.length, failed: failed.length, failures: failed,
        next_cursor: listBody.next_cursor || null,
        done: !listBody.next_cursor,
      });
      } catch (err) {
        return json({ error: err.message, stack: err.stack }, 500);
      }
    }

    if (url.pathname === "/debug" && request.method === "GET") {
      // Test Cloudinary connectivity
      let cloudinaryReachable = false;
      let cloudinaryError = null;
      if (env.CLOUDINARY_CLOUD_NAME && env.CLOUDINARY_API_KEY) {
        try {
          const r = await fetch(`https://api.cloudinary.com/v1_1/${env.CLOUDINARY_CLOUD_NAME}/resources/image?max_results=1`, {
            headers: { Authorization: "Basic " + btoa(`${env.CLOUDINARY_API_KEY}:${env.CLOUDINARY_API_SECRET}`) },
          });
          cloudinaryReachable = r.ok;
          if (!cloudinaryReachable) cloudinaryError = `HTTP ${r.status}`;
        } catch (e) {
          cloudinaryError = e.message;
        }
      }
      return json({
        CLIENT_ID:            Boolean(env.CLIENT_ID),
        CLIENT_SECRET:        Boolean(env.CLIENT_SECRET),
        REFRESH_TOKEN:        Boolean(env.REFRESH_TOKEN),
        GMAIL_CLIENT_ID:      Boolean(env.GMAIL_CLIENT_ID),
        GMAIL_CLIENT_SECRET:  Boolean(env.GMAIL_CLIENT_SECRET),
        GMAIL_REFRESH_TOKEN:  Boolean(env.GMAIL_REFRESH_TOKEN),
        SLACK_WEBHOOK_URL:    Boolean(env.SLACK_WEBHOOK_URL),
        GOOGLE_SCRIPT_URL:    Boolean(env.GOOGLE_SCRIPT_URL),
        CLOUDINARY_CLOUD_NAME: Boolean(env.CLOUDINARY_CLOUD_NAME),
        CLOUDINARY_API_KEY:    Boolean(env.CLOUDINARY_API_KEY),
        CLOUDINARY_API_SECRET: Boolean(env.CLOUDINARY_API_SECRET),
        SLACK_TEST_WEBHOOK:   Boolean(env.SLACK_TEST_WEBHOOK_URL),
        cloudinary_reachable: cloudinaryReachable,
        cloudinary_error:     cloudinaryError,
      });
    }


    if (url.pathname === "/") {
      return withCors(new Response("Supy Automation Server: Online", { status: 200 }));
    }

    return withCors(new Response("Not Found", { status: 404 }));
  },
};

// ─────────────────────────────────────────────────────────────
// Webhook handler
// ─────────────────────────────────────────────────────────────
async function handleWebhook(request, env) {
  let d = {};
  const contentType = request.headers.get("content-type") || "";

  if (contentType.includes("application/json")) {
    d = await request.json();
  } else {
    const form = await request.formData();
    for (const [k, v] of form.entries()) d[k] = v;
  }

  // Strictly require POS + Accounting
  if (!d.pos_system || !d.accounting_software) {
    return json({ status: "error", message: "POS System and Accounting Software are strictly required." }, 400);
  }

  const email       = (d.champion_email || "Unknown").trim();
  const company     = (d.company_name   || "Unknown").trim();
  const submittedAt = new Date().toUTCString().replace(/GMT/, "UTC").replace(/:\d\d /, " ");

  let branches = [];
  if (d.branches_json) {
    try { branches = JSON.parse(d.branches_json); } catch {}
  }

  const results = [];

  // 1. HubSpot
  const token = await getHubspotToken(env);
  let cid = null;
  if (token) {
    const { id: contactId, action } = await upsertContact(token, d);
    cid = contactId;
    if (cid) {
      const noteBody = buildNote(d, branches, submittedAt);
      const noteRes = await fetch("https://api.hubapi.com/crm/v3/objects/notes", {
        method: "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({ properties: { hs_note_body: noteBody, hs_timestamp: new Date().toISOString() } }),
      });
      if (noteRes.status === 201) {
        const noteJson = await noteRes.json();
        await linkEverything(token, noteJson.id, cid, company);
        results.push(`hubspot:${action}:note-ok`);
      } else {
        const noteErr = await noteRes.text();
        console.error("HubSpot note create failed", noteRes.status, noteErr);
        results.push(`hubspot:${action}:note-fail`);
      }
    } else {
      results.push("hubspot:contact-fail");
    }
  } else {
    results.push("hubspot:auth-fail");
  }

  // 2. Slack (main channel)
  const slackOk = await sendSlack(env, d, branches, submittedAt, cid);
  results.push(slackOk ? "slack:ok" : "slack:fail");

  // 2b. Slack test channel — fires only when champion_email is vaishnavi@supy.io
  if ((d.champion_email || "").toLowerCase().trim() === "vaishnavi@supy.io") {
    const testOk = await sendSlackTestChannel(env, d, branches, submittedAt, cid);
    results.push(testOk ? "slack-test:ok" : "slack-test:fail");
  }

  // 3. Gmail — internal notification + customer confirmation
  // Confirmation only sent when HubSpot recognised the contact (limits relay abuse)
  const emailOk = await sendEmail(env, d, branches, submittedAt, cid);
  results.push(emailOk ? "email:ok" : "email:fail");
  if (cid) {
    const confirmOk = await sendCustomerConfirmation(env, d, branches, submittedAt);
    results.push(confirmOk ? "confirm:ok" : "confirm:fail");
  }

  // 4. Google Sheets
  const sheetsOk = await logToSheets(env, d, branches, submittedAt);
  results.push(sheetsOk ? "sheets:ok" : "sheets:fail");

  // 5. KV log (best-effort)
  await appendLog(env, email, company, submittedAt, results.join("|"));

  return json({ status: "ok", details: results });
}

// ─────────────────────────────────────────────────────────────
// Logs endpoint
// ─────────────────────────────────────────────────────────────
async function handleLogs(env) {
  if (!env.LOGS) {
    return withCors(new Response("KV binding LOGS not configured.", { status: 200 }));
  }
  const log = (await env.LOGS.get("submissions")) || "No logs yet.";
  return withCors(new Response(`<pre>${log}</pre>`, {
    status: 200,
    headers: { "Content-Type": "text/html" },
  }));
}

// ─────────────────────────────────────────────────────────────
// File upload  (POST /upload)
// Accepts multipart/form-data: file + company.
// Stores to Cloudinary and returns the secure public URL.
// Requires: CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET secrets.
// ─────────────────────────────────────────────────────────────
async function handleUpload(request, env) {
  if (!env.CLOUDINARY_CLOUD_NAME || !env.CLOUDINARY_API_KEY || !env.CLOUDINARY_API_SECRET) {
    return json({ error: "Cloudinary not configured — set CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET secrets" }, 500);
  }

  let form;
  try {
    form = await request.formData();
  } catch {
    return json({ error: "Invalid multipart body" }, 400);
  }

  const file    = form.get("file");
  const company = (form.get("company") || "unknown").trim();

  if (!file || typeof file === "string") {
    return json({ error: "No file provided" }, 400);
  }
  if (file.size > 50 * 1024 * 1024) {
    return json({ error: "File too large (max 50 MB)" }, 413);
  }

  const slug      = company.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 40) || "unknown";
  const date      = new Date().toISOString().slice(0, 10);
  const uid       = crypto.randomUUID().slice(0, 8);
  const baseName  = file.name.replace(/\.[^.]+$/, "").replace(/[^a-zA-Z0-9_-]/g, "_").slice(0, 80);
  // Strip extension from public_id — Cloudinary blocks zip/rar/tar CDN delivery by extension.
  // The real filename is preserved in the download URL ?name= parameter.
  const publicId  = `supy-onboarding/${date}_${slug}/${uid}_${baseName}`;
  const timestamp = Math.floor(Date.now() / 1000).toString();

  // Cloudinary signed upload: signature = SHA1(sorted_params + api_secret)
  // Params sent: public_id, timestamp (alphabetical order)
  const sigInput  = `public_id=${publicId}&timestamp=${timestamp}${env.CLOUDINARY_API_SECRET}`;
  const sigBuffer = await crypto.subtle.digest("SHA-1", new TextEncoder().encode(sigInput));
  const signature = Array.from(new Uint8Array(sigBuffer)).map(b => b.toString(16).padStart(2, "0")).join("");

  const clForm = new FormData();
  clForm.append("file",      new Blob([await file.arrayBuffer()], { type: file.type || "application/octet-stream" }), file.name);
  clForm.append("api_key",   env.CLOUDINARY_API_KEY);
  clForm.append("timestamp", timestamp);
  clForm.append("signature", signature);
  clForm.append("public_id", publicId);

  // Force raw resource_type so all files (PDFs, ZIPs, etc.) land in the raw bucket.
  // auto/upload would reclassify PDFs as image type, breaking the raw/upload download path.
  const uploadRes  = await fetch(
    `https://api.cloudinary.com/v1_1/${env.CLOUDINARY_CLOUD_NAME}/raw/upload`,
    { method: "POST", body: clForm }
  );
  const uploadJson = await uploadRes.json();

  if (!uploadRes.ok) {
    console.error("Cloudinary upload failed", uploadRes.status, JSON.stringify(uploadJson));
    return json({ error: `File upload failed: ${uploadJson.error?.message || uploadRes.status}` }, 500);
  }

  return json({
    url:  `https://supy-onboarding.vaishnavi-5d1.workers.dev/download?key=${encodeURIComponent(uploadJson.public_id)}&name=${encodeURIComponent(file.name)}`,
    key:  uploadJson.public_id,
    name: file.name,
    size: file.size,
  });
}

async function appendLog(env, email, company, submittedAt, status) {
  if (!env.LOGS) return;
  try {
    const existing = (await env.LOGS.get("submissions")) || "";
    const line = `${submittedAt} | ${email} | ${company} | ${status}\n`;
    // Keep last ~200 lines to stay within KV value limits
    const lines = (existing + line).split("\n").filter(Boolean);
    const trimmed = lines.slice(-200).join("\n") + "\n";
    await env.LOGS.put("submissions", trimmed);
  } catch {}
}

// ─────────────────────────────────────────────────────────────
// HubSpot
// ─────────────────────────────────────────────────────────────
async function getHubspotToken(env) {
  const r = await fetch("https://api.hubapi.com/oauth/v1/token", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      grant_type:    "refresh_token",
      client_id:     env.CLIENT_ID,
      client_secret: env.CLIENT_SECRET,
      refresh_token: env.REFRESH_TOKEN,
    }),
  });
  if (r.status !== 200) return null;
  return (await r.json()).access_token || null;
}

async function upsertContact(token, d) {
  const headers = { Authorization: `Bearer ${token}`, "Content-Type": "application/json" };
  const email   = d.champion_email;

  const firstname = (d.champion_first_name || "").trim();
  const lastname  = (d.champion_last_name  || "").trim();

  const props   = {
    email,
    firstname,
    lastname,
    champion_middle_name: (d.champion_middle_name || "").trim(),
    jobtitle:  d.champion_title,
  };
  // Only include phone if it looks valid (must start with + and country code)
  const rawPhone = (d.champion_phone || "").trim();
  if (rawPhone.startsWith("+")) props.phone = rawPhone;

  // Search for existing contact by email
  const searchRes = await fetch("https://api.hubapi.com/crm/v3/objects/contacts/search", {
    method: "POST", headers,
    body: JSON.stringify({ filterGroups: [{ filters: [{ propertyName: "email", operator: "EQ", value: email }] }] }),
  });
  const searchJson = await searchRes.json();
  const existing   = (searchJson.results || [])[0];

  if (existing) {
    // Contact found — update it
    const patchRes = await fetch(`https://api.hubapi.com/crm/v3/objects/contacts/${existing.id}`, {
      method: "PATCH", headers, body: JSON.stringify({ properties: props }),
    });
    if (!patchRes.ok) {
      const patchErr = await patchRes.json().catch(() => ({}));
      console.error("HubSpot PATCH failed", patchRes.status, JSON.stringify(patchErr));
    }
    return { id: existing.id, action: "updated" };
  }

  // Contact not found — create a new one
  const createRes  = await fetch("https://api.hubapi.com/crm/v3/objects/contacts", {
    method: "POST", headers, body: JSON.stringify({ properties: props }),
  });
  const createJson = await createRes.json();

  if (createRes.status === 201 && createJson.id) {
    return { id: createJson.id, action: "created" };
  }

  // Edge case: HubSpot returned 409 (duplicate detected on their side) — re-search to get the id
  if (createRes.status === 409) {
    const retryRes  = await fetch("https://api.hubapi.com/crm/v3/objects/contacts/search", {
      method: "POST", headers,
      body: JSON.stringify({ filterGroups: [{ filters: [{ propertyName: "email", operator: "EQ", value: email }] }] }),
    });
    const retryJson = await retryRes.json();
    const found     = (retryJson.results || [])[0];
    if (found) return { id: found.id, action: "updated" };
  }

  // Log the error detail so it surfaces in Cloudflare logs
  console.error("HubSpot contact create failed", createRes.status, JSON.stringify(createJson));
  return { id: null, action: "failed" };
}

async function linkEverything(token, noteId, contactId, companyName) {
  const headers = { Authorization: `Bearer ${token}`, "Content-Type": "application/json" };

  const assoc = (from, fromId, to, toId, type) =>
    fetch(`https://api.hubapi.com/crm/v3/associations/${from}/${to}/batch/create`, {
      method: "POST", headers,
      body: JSON.stringify({ inputs: [{ from: { id: fromId }, to: { id: toId }, type }] }),
    });

  // Note → Contact
  await assoc("Notes", noteId, "Contacts", contactId, "note_to_contact");

  // Note → any Deals already on the Contact
  try {
    const r = await fetch(`https://api.hubapi.com/crm/v3/objects/contacts/${contactId}/associations/deals`, { headers });
    if (r.status === 200) {
      for (const deal of (await r.json()).results || []) {
        await assoc("Notes", noteId, "Deals", deal.id, "note_to_deal");
      }
    }
  } catch {}

  if (!companyName || companyName.toLowerCase() === "unknown") return;

  // Deals by name
  try {
    const deals = await fetch("https://api.hubapi.com/crm/v3/objects/deals/search", {
      method: "POST", headers,
      body: JSON.stringify({ filterGroups: [{ filters: [{ propertyName: "dealname", operator: "CONTAINS_TOKEN", value: companyName }] }] }),
    });
    for (const deal of (await deals.json()).results || []) {
      await assoc("Notes",    noteId,    "Deals", deal.id, "note_to_deal");
      await assoc("Contacts", contactId, "Deals", deal.id, "contact_to_deal");
    }
  } catch {}

  // Company — search first, create if missing, then link contact + note
  try {
    const comps = await fetch("https://api.hubapi.com/crm/v3/objects/companies/search", {
      method: "POST", headers,
      body: JSON.stringify({ filterGroups: [{ filters: [{ propertyName: "name", operator: "CONTAINS_TOKEN", value: companyName }] }] }),
    });
    const compResults = (await comps.json()).results || [];

    let compId;
    if (compResults.length > 0) {
      compId = compResults[0].id;
    } else {
      // No company found — create one
      const createComp = await fetch("https://api.hubapi.com/crm/v3/objects/companies", {
        method: "POST", headers,
        body: JSON.stringify({ properties: { name: companyName } }),
      });
      if (createComp.status === 201) {
        const created = await createComp.json();
        compId = created.id;
      } else {
        console.error("HubSpot company create failed", createComp.status, await createComp.text());
      }
    }

    if (compId) {
      await assoc("Contacts", contactId, "Companies", compId, "contact_to_company");
      await assoc("Notes",    noteId,    "Companies", compId, "note_to_company");
      const compDeals = await fetch(`https://api.hubapi.com/crm/v3/objects/companies/${compId}/associations/deals`, { headers });
      if (compDeals.status === 200) {
        for (const deal of (await compDeals.json()).results || []) {
          await assoc("Notes", noteId, "Deals", deal.id, "note_to_deal");
        }
      }
    }
  } catch {}
}

function buildNote(d, branches, submittedAt) {
  const itSame    = (d.it_same_as_champion || "").toLowerCase();
  const itContact = itSame === "yes"
    ? `<b>Same as Internal Champion</b> — ${[d.champion_first_name, d.champion_middle_name, d.champion_last_name].filter(Boolean).map(s=>s.trim()).join(" ")}`
    : `Name: ${d.it_name || ""}<br>Email: ${d.it_email || ""}`;
  const itBlock   = `${itContact}<br><br><b>POS System:</b> ${d.pos_system || ""}<br><b>Accounting SW:</b> ${d.accounting_software || ""}`;

  let branchRows = "";
  for (let i = 0; i < branches.length; i++) {
    const b     = branches[i];
    const hours = `${b.open || ""} – ${b.close || ""}`.replace(/^\s*–\s*$/, "");
    branchRows += `<tr><td style='padding:5px 8px;border-bottom:1px solid #eee'>${i + 1}</td><td style='padding:5px 8px;border-bottom:1px solid #eee'><b>${b.name || ""}</b></td><td style='padding:5px 8px;border-bottom:1px solid #eee'>${b.address || ""}</td><td style='padding:5px 8px;border-bottom:1px solid #eee'>${b.cost_center || ""}</td><td style='padding:5px 8px;border-bottom:1px solid #eee'>${hours}</td></tr>`;
  }
  const branchSection = branchRows
    ? `<table style='border-collapse:collapse;width:100%;font-size:12px'><tr style='background:#321e57;color:#fff'><th style='padding:6px 8px'>#</th><th style='padding:6px 8px'>Branch Name</th><th style='padding:6px 8px'>Address</th><th style='padding:6px 8px'>Cost Center</th><th style='padding:6px 8px'>Hours</th></tr>${branchRows}</table>`
    : "<i>No branch data provided.</i>";

  const linkCells = (label, raw) => {
    if (!raw || !raw.trim()) return `${label}: <span style='color:#aaa'>—</span>`;
    const links = raw.split(",").map(u => u.trim()).filter(Boolean);
    const anchors = links.map((u, i) =>
      `<a href='${u}' target='_blank' style='color:#503390;font-weight:600;text-decoration:none'>⬇ File ${i + 1}</a>`
    ).join(" &nbsp; ");
    return `${label}: ${anchors}`;
  };
  const filesBlock = linkCells("Invoices / Product List", d.invoices_link) + "<br>" + linkCells("Supplier Details", d.suppliers_link);

  return [
    `<h3 style='color:#321e57;margin:0 0 4px'>SUPY ONBOARDING</h3><p style='color:#888;font-size:11px;margin:0 0 16px'>Submitted: ${submittedAt}</p>`,
    `<h4 style='color:#503390;border-bottom:1px solid #e0d8f0;padding-bottom:4px;margin:14px 0 8px'>COMPANY INFO</h4>Company Name: ${d.company_name || ""}`,
    `<h4 style='color:#503390;border-bottom:1px solid #e0d8f0;padding-bottom:4px;margin:14px 0 8px'>INTERNAL CHAMPION</h4>Name: ${[d.champion_first_name, d.champion_middle_name, d.champion_last_name].filter(Boolean).map(s=>s.trim()).join(" ") || ""}<br>Title: ${d.champion_title || ""}<br>Email: ${d.champion_email || ""}<br>Phone: ${d.champion_phone || ""}`,
    `<h4 style='color:#503390;border-bottom:1px solid #e0d8f0;padding-bottom:4px;margin:14px 0 8px'>FINANCE POC</h4>External Accounting Firm: ${d.accounting_external || ""}<br>Name: ${d.finance_name || ""}<br>Title: ${d.finance_title || ""}<br>Email: ${d.finance_email || ""}<br>Phone: ${d.finance_phone || ""}`,
    `<h4 style='color:#503390;border-bottom:1px solid #e0d8f0;padding-bottom:4px;margin:14px 0 8px'>IT &amp; SYSTEMS</h4>${itBlock}`,
    `<h4 style='color:#503390;border-bottom:1px solid #e0d8f0;padding-bottom:4px;margin:14px 0 8px'>BRANCH CONFIGURATION</h4>${branchSection}`,
    `<h4 style='color:#503390;border-bottom:1px solid #e0d8f0;padding-bottom:4px;margin:14px 0 8px'>OPERATIONS</h4>Order Method: ${d.ordering_method || ""}<br>PO Approver: ${d.po_approver || ""}<br>Ordering Structure: ${d.ordering_structure || ""}<br>Stock Counts: ${d.stock_counts || ""}<br>Stock Count Duration: ${d.stock_count_duration || ""}<br>Inventory System: ${d.inventory_system || ""}`,
    `<h4 style='color:#503390;border-bottom:1px solid #e0d8f0;padding-bottom:4px;margin:14px 0 8px'>FOOD COST</h4>Current Food Cost %: ${d.food_cost_current || ""}<br>Target Food Cost %: ${d.food_cost_target || ""}<br>COGS Method: ${d.cogs_method || ""}<br>Invoice Delivery: ${d.invoice_delivery || ""}<br>Finance Complications: ${d.finance_complications || ""}`,
    `<h4 style='color:#503390;border-bottom:1px solid #e0d8f0;padding-bottom:4px;margin:14px 0 8px'>GOALS &amp; BLOCKERS</h4>Top Problem to Solve: ${d.top_problem || ""}<br>CSM Notes: ${d.extra_notes || ""}<br>Known Blockers: ${d.blockers || ""}<br>Target Go-Live: ${d.golive_date || ""}`,
    `<h4 style='color:#503390;border-bottom:1px solid #e0d8f0;padding-bottom:4px;margin:14px 0 8px'>FILE LINKS</h4>${filesBlock}`,
  ].join("");
}

// ─────────────────────────────────────────────────────────────
// Slack
// ─────────────────────────────────────────────────────────────
async function sendSlack(env, d, branches, submittedAt, cid) {
  if (!env.SLACK_WEBHOOK_URL) return false;
  const hsLink = cid
    ? `https://app.hubspot.com/contacts/${HUBSPOT_PORTAL_ID}/record/0-1/${cid}`
    : "https://app.hubspot.com/contacts/";
  const blocks = [
    { type: "header", text: { type: "plain_text", text: "🎉 New Onboarding Submission", emoji: true } },
    {
      type: "section",
      fields: [
        { type: "mrkdwn", text: `*Company:*\n${d.company_name || "Unknown"}` },
        { type: "mrkdwn", text: `*Champion:*\n${[d.champion_first_name, d.champion_middle_name, d.champion_last_name].filter(Boolean).map(s=>s.trim()).join(" ") || "-"} (${d.champion_email || "-"})` },
        { type: "mrkdwn", text: `*Branches:*\n${branches.length} location(s)` },
        { type: "mrkdwn", text: `*Target Go-Live:*\n${d.golive_date || "Not specified"}` },
        { type: "mrkdwn", text: `*POS System:*\n${d.pos_system || "-"}` },
        { type: "mrkdwn", text: `*Accounting:*\n${d.accounting_software || "-"}` },
      ],
    },
    {
      type: "actions",
      elements: [{ type: "button", text: { type: "plain_text", text: "View in HubSpot", emoji: true }, style: "primary", url: hsLink }],
    },
  ];

  // Append file download buttons only when files were uploaded
  const buildFileButtons = (raw, prefix) => {
    if (!raw || !raw.trim()) return [];
    return raw.split(",").map(u => u.trim()).filter(Boolean).slice(0, 5).map((u, i) => ({
      type: "button",
      text: { type: "plain_text", text: `${prefix} ${i + 1}`, emoji: true },
      url: u,
    }));
  };
  const fileButtons = [
    ...buildFileButtons(d.invoices_link, "📎 Invoice"),
    ...buildFileButtons(d.suppliers_link, "📋 Supplier"),
  ].slice(0, 5);
  if (fileButtons.length > 0) blocks.push({ type: "actions", elements: fileButtons });
  const r = await fetch(env.SLACK_WEBHOOK_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ blocks }),
  });
  return r.status === 200;
}

// ─────────────────────────────────────────────────────────────
// Slack — hubspot-test-channel
// Fires only when champion_email === vaishnavi@supy.io
// ─────────────────────────────────────────────────────────────
async function sendSlackTestChannel(env, d, branches, submittedAt, cid) {
  if (!env.SLACK_TEST_WEBHOOK_URL) return false;
  const hsLink = cid
    ? `https://app.hubspot.com/contacts/${HUBSPOT_PORTAL_ID}/record/0-1/${cid}`
    : "https://app.hubspot.com/contacts/";

  const blocks = [
    { type: "header", text: { type: "plain_text", text: "🧪 Test Submission — vaishnavi@supy.io", emoji: true } },
    {
      type: "section",
      fields: [
        { type: "mrkdwn", text: `*Company:*\n${d.company_name || "Unknown"}` },
        { type: "mrkdwn", text: `*Champion:*\n${[d.champion_first_name, d.champion_middle_name, d.champion_last_name].filter(Boolean).map(s=>s.trim()).join(" ") || "-"} (${d.champion_email || "-"})` },
        { type: "mrkdwn", text: `*Branches:*\n${branches.length} location(s)` },
        { type: "mrkdwn", text: `*Target Go-Live:*\n${d.golive_date || "Not specified"}` },
        { type: "mrkdwn", text: `*POS System:*\n${d.pos_system || "-"}` },
        { type: "mrkdwn", text: `*Accounting:*\n${d.accounting_software || "-"}` },
      ],
    },
    {
      type: "actions",
      elements: [{ type: "button", text: { type: "plain_text", text: "View in HubSpot", emoji: true }, style: "primary", url: hsLink }],
    },
  ];

  const buildFileButtons = (raw, prefix) => {
    if (!raw || !raw.trim()) return [];
    return raw.split(",").map(u => u.trim()).filter(Boolean).slice(0, 5).map((u, i) => ({
      type: "button",
      text: { type: "plain_text", text: `${prefix} ${i + 1}`, emoji: true },
      url: u,
    }));
  };
  const fileButtons = [
    ...buildFileButtons(d.invoices_link, "📎 Invoice"),
    ...buildFileButtons(d.suppliers_link, "📋 Supplier"),
  ].slice(0, 5);
  if (fileButtons.length > 0) blocks.push({ type: "actions", elements: fileButtons });

  const r = await fetch(env.SLACK_TEST_WEBHOOK_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ blocks }),
  });
  return r.status === 200;
}

// ─────────────────────────────────────────────────────────────
// Gmail (OAuth2 refresh token flow)
// ─────────────────────────────────────────────────────────────
async function getGmailToken(env) {
  const r = await fetch("https://oauth2.googleapis.com/token", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      grant_type:    "refresh_token",
      client_id:     env.GMAIL_CLIENT_ID,
      client_secret: env.GMAIL_CLIENT_SECRET,
      refresh_token: env.GMAIL_REFRESH_TOKEN,
    }),
  });
  if (r.status !== 200) return null;
  return (await r.json()).access_token || null;
}

async function sendEmail(env, d, branches, submittedAt, cid) {
  const token = await getGmailToken(env);
  if (!token) return false;

  const hsLink  = cid
    ? `https://app.hubspot.com/contacts/${HUBSPOT_PORTAL_ID}/record/0-1/${cid}`
    : "https://app.hubspot.com/contacts/";
  const company = String(d.company_name || "Unknown Company").replace(/[\r\n]+/g, " ").slice(0, 200);

  const noteBody = buildNote(d, branches, submittedAt);
  const htmlBody = [
    `<div style='font-family:Arial,sans-serif;max-width:700px;margin:auto;padding:24px;border:1px solid #e0d8f0;border-radius:8px'>`,
    noteBody,
    `</div>`,
  ].join("");

  const mime = [
    `From: ${EMAIL_FROM}`,
    `To: ${EMAIL_RECIPIENTS.join(", ")}`,
    `Subject: New Onboarding: ${company}`,
    `MIME-Version: 1.0`,
    `Content-Type: text/html; charset=UTF-8`,
    ``,
    htmlBody,
  ].join("\r\n");

  const raw = btoa(unescape(encodeURIComponent(mime)))
    .replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");

  const r = await fetch("https://gmail.googleapis.com/gmail/v1/users/me/messages/send", {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: JSON.stringify({ raw }),
  });
  return r.status === 200;
}

function esc(s) {
  return String(s || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

async function sendCustomerConfirmation(env, d, branches, submittedAt) {
  const token = await getGmailToken(env);
  if (!token) return false;

  const customerEmail = (d.champion_email || "").trim();
  if (!customerEmail || !/^[^\s<>@\r\n,;"]+@[^\s<>@\r\n,;"]+\.[^\s<>@\r\n,;"]+$/.test(customerEmail)) return false;

  const firstName = esc((d.champion_first_name || "").trim() || "there");
  const company   = esc(String(d.company_name || "your company").replace(/[\r\n]+/g, " ").slice(0, 200));

  const noteBody  = buildNote(d, branches, submittedAt);

  const htmlBody = `
<div style="font-family:Arial,sans-serif;max-width:680px;margin:auto;color:#1a1a2e">

  <div style="background:#321e57;padding:24px 28px;border-radius:8px 8px 0 0">
    <img src="https://cdn.prod.website-files.com/68933e53d968ca7f0c808561/690cc143814230554277cf54_supy-favicon.svg" height="28" style="vertical-align:middle;margin-right:10px">
    <span style="color:#fff;font-size:18px;font-weight:700;vertical-align:middle">Supy</span>
  </div>

  <div style="background:#fff;padding:28px;border:1px solid #e0d8f0;border-top:none;border-radius:0 0 8px 8px">

    <h2 style="color:#321e57;margin:0 0 8px">You're all set, ${firstName}!</h2>
    <p style="color:#555;margin:0 0 20px;font-size:15px">
      Thank you for completing the Supy onboarding form for <strong>${company}</strong>.
      Your Customer Success Manager has been notified and will be reaching out shortly to schedule your first session.
    </p>

    <div style="background:#f5f2ff;border-left:4px solid #503390;padding:12px 16px;border-radius:4px;margin-bottom:24px">
      <p style="margin:0;font-size:14px;color:#321e57">
        <strong>Need to make a change?</strong><br>
        If anything in your submission needs to be updated or corrected, simply <strong>reply to this email</strong> and your CSM will be notified automatically with the full context.
      </p>
    </div>

    <h3 style="color:#503390;font-size:14px;border-bottom:1px solid #e0d8f0;padding-bottom:6px;margin:0 0 16px">
      Your submission summary
    </h3>

    ${noteBody}

    <hr style="border:none;border-top:1px solid #e0d8f0;margin:24px 0">
    <p style="color:#aaa;font-size:11px;margin:0">
      This confirmation was sent to ${esc(customerEmail)}. Reply any time to update your information — your CSM will receive your message directly.
    </p>

  </div>
</div>`;

  const mime = [
    `From: Supy Onboarding <${EMAIL_FROM}>`,
    `To: ${customerEmail}`,
    `Reply-To: csms@supy.io`,
    `Subject: Your Supy onboarding has been received — ${company}`,
    `MIME-Version: 1.0`,
    `Content-Type: text/html; charset=UTF-8`,
    ``,
    htmlBody,
  ].join("\r\n");

  const raw = btoa(unescape(encodeURIComponent(mime)))
    .replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");

  const r = await fetch("https://gmail.googleapis.com/gmail/v1/users/me/messages/send", {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: JSON.stringify({ raw }),
  });
  return r.status === 200;
}

// ─────────────────────────────────────────────────────────────
// Google Sheets (Apps Script)
// ─────────────────────────────────────────────────────────────
async function logToSheets(env, d, branches, submittedAt) {
  if (!env.GOOGLE_SCRIPT_URL) return false;
  try {
    const payload = { ...d, submitted_at: submittedAt, branch_count: branches.length };
    const r = await fetch(env.GOOGLE_SCRIPT_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    return r.ok;
  } catch { return false; }
}

// ─────────────────────────────────────────────────────────────
// Universal download proxy  (GET /download?key=...&name=...)
// Detects storage backend from key prefix so old links never break:
//   "submissions/"      → Supabase Storage
//   anything else       → Cloudinary (legacy)
// New uploads always go through this same endpoint, so swapping
// the backend in the future only requires updating this function.
// ─────────────────────────────────────────────────────────────
async function handleDownload(request, env) {
  const params   = new URL(request.url).searchParams;
  const key      = params.get("key");
  const filename = params.get("name") || key?.split("/").pop() || "download";

  if (!key) return json({ error: "Missing ?key= parameter" }, 400);

  // ── Supabase ──────────────────────────────────────────────
  if (key.startsWith("submissions/")) {
    if (!env.SUPABASE_URL || !env.SUPABASE_ANON_KEY) {
      return json({ error: "Supabase not configured" }, 500);
    }
    const upstream = await fetch(
      `${env.SUPABASE_URL}/storage/v1/object/onboarding-files/${key}`,
      { headers: { "Authorization": `Bearer ${env.SUPABASE_ANON_KEY}` } }
    );
    if (!upstream.ok) return json({ error: `File not found (${upstream.status})` }, 404);
    return new Response(upstream.body, {
      status: 200,
      headers: {
        ...CORS_HEADERS,
        "Content-Type":        upstream.headers.get("Content-Type") || "application/octet-stream",
        "Content-Disposition": `attachment; filename="${filename}"`,
        "Cache-Control":       "no-store",
      },
    });
  }

  // ── Cloudinary (legacy keys) ──────────────────────────────
  if (!env.CLOUDINARY_CLOUD_NAME || !env.CLOUDINARY_API_SECRET) {
    return json({ error: "Cloudinary not configured" }, 500);
  }

  // First: try a signed CDN delivery URL (works for xlsx, pdf, etc.).
  // Signature = URL-safe base64(SHA-1(public_id + api_secret)), first 6 bytes → 8 chars.
  const sigBuf = await crypto.subtle.digest(
    "SHA-1",
    new TextEncoder().encode(key + env.CLOUDINARY_API_SECRET)
  );
  const sigBytes = new Uint8Array(sigBuf).slice(0, 6);
  const sig = btoa(String.fromCharCode(...sigBytes))
    .replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");

  const cdnUrl  = `https://res.cloudinary.com/${env.CLOUDINARY_CLOUD_NAME}/raw/upload/s--${sig}--/${key}`;
  const cdnResp = await fetch(cdnUrl, { redirect: "manual" });

  if (cdnResp.status === 301 || cdnResp.status === 302) {
    return Response.redirect(cdnResp.headers.get("location"), 302);
  }
  if (cdnResp.ok) {
    return new Response(cdnResp.body, {
      status: 200,
      headers: {
        ...CORS_HEADERS,
        "Content-Type":        cdnResp.headers.get("Content-Type") || "application/octet-stream",
        "Content-Disposition": `attachment; filename="${filename}"`,
        "Cache-Control":       "no-store",
      },
    });
  }

  // Fallback 1: might be stored as image type (e.g. PDF uploaded via auto/upload).
  // For image resources, to_sign = public_id WITHOUT format extension (format is appended in URL only).
  const ext = filename.includes(".") ? filename.split(".").pop().toLowerCase() : "";
  if (ext) {
    const imgBuf = await crypto.subtle.digest("SHA-1", new TextEncoder().encode(key + env.CLOUDINARY_API_SECRET));
    const imgBytes = new Uint8Array(imgBuf).slice(0, 6);
    const imgSig = btoa(String.fromCharCode(...imgBytes)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
    const imgUrl = `https://res.cloudinary.com/${env.CLOUDINARY_CLOUD_NAME}/image/upload/s--${imgSig}--/${key}.${ext}`;
    const imgResp = await fetch(imgUrl, { redirect: "manual" });
    if (imgResp.status === 301 || imgResp.status === 302) {
      return Response.redirect(imgResp.headers.get("location"), 302);
    }
    if (imgResp.ok) {
      return new Response(imgResp.body, {
        status: 200,
        headers: {
          ...CORS_HEADERS,
          "Content-Type":        imgResp.headers.get("Content-Type") || "application/octet-stream",
          "Content-Disposition": `attachment; filename="${filename}"`,
          "Cache-Control":       "no-store",
        },
      });
    }
  }

  // Fallback 2: private file. Try raw/download then image/download (image-type PDFs need format param).
  const timestamp = Math.floor(Date.now() / 1000).toString();
  const fileExt = filename.includes(".") ? filename.split(".").pop().toLowerCase() : "";
  async function tryPrivateDownload(resourceType) {
    const parts = [`attachment=${filename}`, `public_id=${key}`, `timestamp=${timestamp}`, `type=private`];
    if (resourceType === "image" && fileExt) parts.push(`format=${fileExt}`);
    parts.sort();
    const buf = await crypto.subtle.digest("SHA-1", new TextEncoder().encode(parts.join("&") + env.CLOUDINARY_API_SECRET));
    const signature = Array.from(new Uint8Array(buf)).map(b => b.toString(16).padStart(2, "0")).join("");
    const p = new URLSearchParams({ public_id: key, timestamp, api_key: env.CLOUDINARY_API_KEY, signature, attachment: filename, type: "private" });
    if (resourceType === "image" && fileExt) p.set("format", fileExt);
    return fetch(`https://api.cloudinary.com/v1_1/${env.CLOUDINARY_CLOUD_NAME}/${resourceType}/download?${p}`, { redirect: "manual" });
  }
  for (const rt of ["raw", "image"]) {
    const dlResp = await tryPrivateDownload(rt);
    if (dlResp.status === 302) return Response.redirect(dlResp.headers.get("location"), 302);
    if (dlResp.ok) {
      return new Response(dlResp.body, {
        status: 200,
        headers: { ...CORS_HEADERS, "Content-Type": dlResp.headers.get("Content-Type") || "application/octet-stream", "Content-Disposition": `attachment; filename="${filename}"` },
      });
    }
  }
  return json({ error: "File not found" }, 404);
}

// ── Draft save/load handlers ──────────────────────────────────

async function handleDraftSave(request, env) {
  if (!env.DRAFTS) return json({ error: "DRAFTS KV not configured" }, 500);

  const body = await request.json().catch(() => null);
  if (!body) return json({ error: "Invalid JSON" }, 400);

  // Use provided key (for updates) or generate a new one
  const key = body._draft_key || generateDraftKey();
  const payload = { ...body, _draft_key: key, _saved_at: new Date().toISOString() };

  // Store for 30 days
  await env.DRAFTS.put(key, JSON.stringify(payload), { expirationTtl: 60 * 60 * 24 * 30 });

  return json({ key, draft_url: `https://vaishnavi-supy-io.github.io/supy-onboarding/?draft=${key}` });
}

async function handleDraftLoad(request, env) {
  if (!env.DRAFTS) return json({ error: "DRAFTS KV not configured" }, 500);

  const key = new URL(request.url).searchParams.get("key");
  if (!key) return json({ error: "Missing key" }, 400);

  const data = await env.DRAFTS.get(key);
  if (!data) return json({ error: "Draft not found or expired" }, 404);

  return json({ data: JSON.parse(data) });
}

function generateDraftKey() {
  return crypto.randomUUID().replace(/-/g, "").slice(0, 24);
}
