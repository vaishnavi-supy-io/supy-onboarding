import { createRequire } from 'module';
const require = createRequire(import.meta.url);
const puppeteer = require('./node_modules/puppeteer/lib/puppeteer/puppeteer.js');
import path from 'path';
import { fileURLToPath } from 'url';
const __dirname = path.dirname(fileURLToPath(import.meta.url));

const browser = await puppeteer.launch({ headless: true, args: ['--no-sandbox','--disable-setuid-sandbox'] });
const page = await browser.newPage();
await page.setViewport({ width: 1280, height: 900, deviceScaleFactor: 1.5 });
page.on('dialog', async d => await d.accept());

await page.goto('file://' + path.resolve(__dirname, 'index.html'), { waitUntil: 'domcontentloaded' });
await new Promise(r => setTimeout(r, 800));

// ── Fill every field ──
await page.evaluate(() => {
  function set(name, val) {
    var el = document.querySelector('[name="'+name+'"]');
    if (!el) return;
    el.value = val;
    el.dispatchEvent(new Event('input',{bubbles:true}));
    el.dispatchEvent(new Event('change',{bubbles:true}));
  }
  function sel(name, val) {
    var el = document.querySelector('[name="'+name+'"]');
    if (!el) return;
    el.value = val;
    el.dispatchEvent(new Event('change',{bubbles:true}));
  }

  set('company_name', 'Test Restaurant Group');
  set('champion_first_name', 'Jane');
  set('champion_middle_name', 'Marie');
  set('champion_last_name',  'Doe');
  set('champion_title', 'Operations Manager');
  set('champion_phone', '+971 50 123 4567');
  set('champion_email', 'jane.doe@testgroup.com');

  sel('accounting_external', 'No — all done in-house');
  set('finance_name',  'John Smith');
  set('finance_title', 'Finance Manager');
  set('finance_email', 'john.smith@testgroup.com');
  set('finance_phone', '+971 50 987 6543');

  var itSel = document.querySelector('[name="it_same_as_champion"]');
  itSel.value = 'yes';
  itSel.dispatchEvent(new Event('change',{bubbles:true}));
  toggleSameAs(itSel, 'it-details');

  set('pos_system', 'Foodics');
  set('accounting_software', 'Xero');

  sel('ordering_method',    'WhatsApp / phone calls to suppliers');
  sel('po_approver',        'One central approver for all locations');
  sel('ordering_structure', 'Central team orders for all');
  sel('stock_counts',       'Yes — weekly');
  sel('stock_count_duration','1–3 hours');
  set('inventory_system',   'Excel spreadsheet');

  set('food_cost_current', '31%');
  set('food_cost_target',  '27%');
  sel('cogs_method',       'Excel model we maintain');
  sel('invoice_delivery',  'Email (PDF)');
  set('finance_complications', 'None');

  set('top_problem', 'Reduce waste and track supplier performance');
  set('extra_notes', 'TEST SUBMISSION — do not action');
  set('blockers',    'None');
  set('golive_date', '2026-07-15');

  // Fill both branch rows
  var branchData = [
    ['Downtown Dubai', 'Sheikh Zayed Rd, Dubai, UAE', 'B-001', '9:00', 'AM', '11:00', 'PM', 'Ground floor'],
    ['Dubai Marina',   'Marina Walk, Dubai, UAE',     'B-002', '10:00','AM', '11:00', 'PM', 'Level 2']
  ];
  document.querySelectorAll('#branchRows .branch-row').forEach(function(row, i) {
    var d = branchData[i] || branchData[0];
    var texts = row.querySelectorAll('input[type="text"]');
    var ampms = row.querySelectorAll('select.ampm-sel');
    [d[0],d[1],d[2],d[3],d[7]].forEach(function(v,j){ if(texts[j]){ texts[j].value=v; texts[j].dispatchEvent(new Event('input',{bubbles:true})); }});
    if(texts[3]){ texts[3].value=d[3]; texts[3].dispatchEvent(new Event('input',{bubbles:true})); }
    if(texts[4]){ texts[4].value=d[5]; texts[4].dispatchEvent(new Event('input',{bubbles:true})); }
    if(ampms[0]){ ampms[0].value=d[4]; ampms[0].dispatchEvent(new Event('change',{bubbles:true})); }
    if(ampms[1]){ ampms[1].value=d[6]; ampms[1].dispatchEvent(new Event('change',{bubbles:true})); }
  });
});
console.log('✅ All fields filled');
await new Promise(r => setTimeout(r, 500));

// ── Upload invoices xlsx ──
console.log('📤 Uploading dummy_invoices.xlsx...');
const invInput = await page.$('#invFile');
await invInput.uploadFile('/tmp/dummy_invoices.xlsx');
await new Promise(r => setTimeout(r, 7000));
const invStatus = await page.$eval('#invStatus', el => el.innerText.trim());
console.log('   Invoice status:', invStatus || '(no status)');

// ── Upload suppliers xlsx ──
console.log('📤 Uploading dummy_suppliers.xlsx...');
const supInput = await page.$('#supFile');
await supInput.uploadFile('/tmp/dummy_suppliers.xlsx');
await new Promise(r => setTimeout(r, 7000));
const supStatus = await page.$eval('#supStatus', el => el.innerText.trim());
console.log('   Supplier status:', supStatus || '(no status)');

// ── Screenshots ──
await page.evaluate(() => window.scrollTo(0,0));
await new Promise(r => setTimeout(r, 300));
await page.screenshot({ path: '/tmp/t_01_top.png' });
console.log('📸 1: Top / banner');

await page.evaluate(() => document.querySelector('[name="champion_first_name"]').scrollIntoView({block:'center'}));
await new Promise(r => setTimeout(r, 200));
await page.screenshot({ path: '/tmp/t_02_champion.png' });
console.log('📸 2: Champion name (First/Middle/Last)');

await page.evaluate(() => document.getElementById('branchRows').scrollIntoView({block:'center'}));
await new Promise(r => setTimeout(r, 200));
await page.screenshot({ path: '/tmp/t_03_branches.png' });
console.log('📸 3: Branch rows');

await page.evaluate(() => document.getElementById('invStatus').scrollIntoView({block:'center'}));
await new Promise(r => setTimeout(r, 200));
await page.screenshot({ path: '/tmp/t_04_uploads.png' });
console.log('📸 4: File uploads');

// ── Validation check ──
const errors = await page.evaluate(() =>
  Array.from(document.querySelectorAll('[required]'))
    .filter(el => el.offsetParent !== null && !(el.value||'').trim())
    .map(el => ({ name: el.name||'(no name)', placeholder: el.placeholder }))
);
console.log('\nEmpty required fields:', errors.length ? JSON.stringify(errors) : 'NONE ✅');

// ── Submit ──
await page.evaluate(() => document.getElementById('submitBtn').scrollIntoView({block:'center'}));
await new Promise(r => setTimeout(r, 200));
await page.screenshot({ path: '/tmp/t_05_presubmit.png' });
console.log('📸 5: Pre-submit');

await page.evaluate(() => document.getElementById('submitBtn').click());
console.log('🚀 Submitted — waiting for response...');
await new Promise(r => setTimeout(r, 1500));
await page.screenshot({ path: '/tmp/t_06_loading.png' });
console.log('📸 6: Loading state');
await new Promise(r => setTimeout(r, 5000));
await page.screenshot({ path: '/tmp/t_07_result.png' });
console.log('📸 7: Result screen');

await browser.close();
console.log('\n✅ Test complete!');
