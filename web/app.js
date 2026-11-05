/* IAmStrata CRM browser client — only displays data actually returned by backend. */
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const state = {csrf: null, user: null, agencies: [], agency: null, page: 'overview', contacts: []};
const icon = (v) => `<span class="empty-icon">${v}</span>`;
const pill = (name, cls='') => `<span class="pill ${cls}">${esc(name)}</span>`;
const sub = (name, text, actions='') => `<div class="page-top"><div><div class="eyebrow top">YOUR WORKSPACE / ${esc(name.toUpperCase())}</div><h1>${esc(name)}</h1><p>${esc(text)}</p></div><div class="toolbar">${actions}</div></div>`;
const blank = (name, text, mark='◇') => `<div class="empty"><div class="empty-icon">${mark}</div><h3>${esc(name)}</h3><p>${esc(text)}</p></div>`;
const formValue = (form, key) => new FormData(form).get(key)?.toString().trim() ?? '';
function notice(message, error=false) { $('notice').innerHTML = `<div class="notice ${error?'errornotice':''}">${esc(message)}</div>`; setTimeout(() => {if($('notice')) $('notice').innerHTML='';}, 8000); }
async function api(path, init={}) {
  const headers = {...init.headers};
  if (state.csrf) headers['x-csrf-token'] = state.csrf;
  if (init.body && !(init.body instanceof FormData)) headers['Content-Type'] = 'application/json';
  let res; try { res=await fetch('/api'+path, {...init,headers,credentials:'same-origin'}); }
  catch { throw new Error('Network error. Verify the server is online.'); }
  const json=await res.json().catch(()=>({detail:'Unexpected server response'}));
  if (res.status===401 && path!='/auth/login') { showLogin(); throw new Error('Session expired. Sign in again.'); }
  if (!res.ok) throw new Error(typeof json.detail==='string'?json.detail:`Request failed (${res.status})`);
  return json;
}
function showLogin(){state.csrf=null; $('login').classList.remove('hidden'); $('shell').classList.add('hidden');}
async function boot() {
  try { state.user=await api('/me'); state.csrf=state.user.csrf; await initApp(); }
  catch { showLogin(); }
}
async function initApp() {
  $('login').classList.add('hidden'); $('shell').classList.remove('hidden');
  await loadAgencies(); await render();
}
async function loadAgencies() {
  state.agencies=await api('/agencies');
  const preferred=localStorage.getItem('strata_agency');
  if (!state.agencies.some(a=>a.id===state.agency)) state.agency=state.agencies.find(a=>a.id===preferred)?.id||state.agencies[0]?.id;
  $('agency').innerHTML=state.agencies.map(a=>`<option value="${esc(a.id)}" ${a.id===state.agency?'selected':''}>${esc(a.name)}</option>`).join('');
}
function activeAgency(){return state.agencies.find(a=>a.id===state.agency);}
async function render(){
  $('crumb').textContent=state.page[0].toUpperCase()+state.page.slice(1);
  document.querySelectorAll('#nav .nav-link').forEach(e=>e.classList.toggle('active',e.dataset.page===state.page));
  if(!state.agency) { $('page').innerHTML=blank('No workspace yet','Run the owner bootstrap to create the first agency.');return; }
  $('page').innerHTML=`<div class="panel">Loading workspace…</div>`;
  try {
    if(state.page==='overview') await overview();
    else if(state.page==='contacts') await contacts();
    else if(state.page==='inbox') await inbox();
    else if(state.page==='campaigns') await campaigns();
    else if(state.page==='workflows') await workflows();
    else if(state.page==='settings') await settings();
  } catch(e) { $('page').innerHTML=blank('Unable to load',e.message,'⚠'); }
}
const aid = () => '/agencies/'+encodeURIComponent(state.agency);
async function overview(){
  const [counts,agencies]=await Promise.all([api(aid()+'/dashboard'), api('/agencies')]);
  state.agencies=agencies;
  $('page').innerHTML=sub('Command overview',`A single view of your ${activeAgency()?.name||'agency'} pipeline and communication activity.`,`<button class="secondary" id="add-agency">+ Add sub-agency</button>`)+
  `<div class="grid-stats">${[['Total contacts',counts.contacts,'♧'],['SMS opted-in',counts.consented,'◈'],['Messages logged',counts.messages,'▤'],['Active workflows',counts.workflows,'◇']].map(([label,val,symbol])=>`<div class="stat"><div class="statname">${label}</div><div class="stat-icon">${symbol}</div><div class="value">${Number(val).toLocaleString()}</div><div class="mini">Live from your database</div></div>`).join('')}</div>`+
  `<div class="two"><div class="panel"><div class="panel-head"><h2>Operating essentials</h2>${pill('LIVE DATABASE')}</div><p>Everything here is connected to the workspace you select. No simulated leads, messages or conversion metrics are shown.</p><div class="data-row"><span>Agency</span><strong>${esc(activeAgency()?.name)}</strong></div><div class="data-row"><span>Twilio credentials</span>${pill(activeAgency()?.twilio_configured?'Configured':'Not configured',activeAgency()?.twilio_configured?'':'gray')}</div><div class="data-row"><span>A2P approval verification</span>${pill(activeAgency()?.a2p_verified?'Recorded':'Required',activeAgency()?.a2p_verified?'':'red')}</div><div style="padding-top:20px"><button class="secondary" data-go="settings">Manage integrations →</button></div></div><div class="panel"><h2>Built for what comes next</h2><div class="feature"><div class="mark">✦</div><h3>One platform. Multiple agencies.</h3><p>Secure workspace separation, permission-aware messaging, real conversation history and explicit workflow rules.</p></div></div></div>`;
  $('add-agency').addEventListener('click',async()=>{
    const name=prompt('Sub-agency display name (maximum 3 sub-agencies)'); if(!name?.trim())return;
    try{const result=await api('/agencies',{method:'POST',body:JSON.stringify({name:name.trim()})});state.agency=result.id;localStorage.setItem('strata_agency',result.id);await loadAgencies();await render();notice('New agency created.');}catch(e){notice(e.message,true);}
  });
  wireGoto();
}
function wireGoto(){document.querySelectorAll('[data-go]').forEach(el=>el.addEventListener('click',async()=>{state.page=el.dataset.go;await render();}));}
async function contacts(){
  const list=await api(aid()+'/contacts'); state.contacts=list;
  $('page').innerHTML=sub('Contacts','Organize your leads, capture consent evidence, and enrich records with custom fields.',`<button class="secondary" id="import-toggle">↑ Import CSV</button><button class="primary" id="contact-toggle">+ New contact</button>`)+
  `<section id="contact-form" class="panel form-panel hidden"><h2>Add contact</h2><form id="new-contact"><div class="field-grid"><label>Name<input name="name" required maxlength="160" placeholder="Full name"></label><label>Phone (E.164)<input name="phone" required placeholder="+12055550199"></label><label>Email<input name="email" type="email" placeholder="name@example.com"></label><label>Tags (semicolon separated)<input name="tags" placeholder="seller; Birmingham"></label></div><label>Custom fields (JSON object)<textarea name="fields" placeholder='{"property_city":"Birmingham"}'>{}</textarea></label><label class="checkline"><input type="checkbox" name="consent"> Contact has given documented consent to receive SMS</label><label>Consent source (required if opted in)<input name="consent_source" placeholder="Example: online form submitted 2026-11-06"></label><button class="primary">Save contact</button></form></section>`+
  `<section id="import-form" class="panel form-panel hidden"><h2>Import CSV</h2><p>Columns: name, phone, email, tags, sms_consent, consent_source, plus custom columns prefixed cf_. Missing consent evidence means SMS is not enabled.</p><form id="upload-csv"><label>Choose CSV file (max 2 MB, 5,000 rows)<input type="file" name="file" accept=".csv,text/csv" required></label><button class="primary">Import contacts</button></form></section>`+
  `<div class="panel"><div class="panel-head"><h2>Contact directory <small style="color:#90a3bc;font-size:12px">${list.length} shown</small></h2><input class="search" type="search" id="search" placeholder="Filter contacts..."></div><div class="table-wrap" id="contact-table">${contactTable(list)}</div></div>`;
  $('contact-toggle').onclick=()=>$('contact-form').classList.toggle('hidden');
  $('import-toggle').onclick=()=>$('import-form').classList.toggle('hidden');
  $('search').oninput=e=>$('contact-table').innerHTML=contactTable(list.filter(c=>(c.name+' '+c.phone).toLowerCase().includes(e.target.value.toLowerCase())));
  $('new-contact').onsubmit=async e=>{e.preventDefault();const f=e.target;let fields;try{fields=JSON.parse(formValue(f,'fields')||'{}');if(!fields||typeof fields!=='object'||Array.isArray(fields))throw 0;}catch{notice('Custom fields must be a JSON object.',true);return;}
    try{await api(aid()+'/contacts',{method:'POST',body:JSON.stringify({name:formValue(f,'name'),phone:formValue(f,'phone'),email:formValue(f,'email'),tags:formValue(f,'tags').split(';').map(x=>x.trim()).filter(Boolean),fields,sms_consent:f.elements.consent.checked,consent_source:formValue(f,'consent_source')})});await render();notice('Contact saved.');}catch(err){notice(err.message,true);}};
  $('upload-csv').onsubmit=async e=>{e.preventDefault();const data=new FormData(e.target);try{const result=await api(aid()+'/contacts/import',{method:'POST',body:data});await render();notice(`Import finished: ${result.created} created, ${result.duplicates} duplicates, ${result.invalid} invalid.`);}catch(err){notice(err.message,true);}};
}
function contactTable(list){return list.length?`<table class="table"><thead><tr><th>Name</th><th>Phone</th><th>Tags</th><th>SMS permission</th><th>Actions</th></tr></thead><tbody>${list.map(c=>`<tr><td><div class="name">${esc(c.name)}</div><small>${esc(c.email||'')}</small></td><td>${esc(c.phone)}</td><td>${(c.tags||[]).map(t=>`<span class="tag">${esc(t)}</span>`).join('')||'—'}</td><td>${pill(c.opted_out?'Opted out':c.sms_consent?'Consented':'Not opted in',c.opted_out?'red':c.sms_consent?'':'gray')}</td><td><button class="ghost" data-message="${esc(c.id)}">Message</button></td></tr>`).join('')}</tbody></table>`:blank('No matching contacts','Import a CSV or add your first contact.','♧')}
async function inbox(){
  const [messages,contacts]=await Promise.all([api(aid()+'/messages'),api(aid()+'/contacts')]);state.contacts=contacts;
  $('page').innerHTML=sub('Conversations','One-to-one conversations and AI-assisted drafts, under human control.')+
   `<div class="two"><section class="panel"><div class="panel-head"><h2>Message history</h2>${pill('Provider tracked','gray')}</div>${messages.length?messages.map(m=>`<div class="message-card"><strong>${esc(m.name)}</strong><span>${esc(m.direction)} · ${esc(m.status)}</span><p>${esc(m.body)}</p></div>`).join(''):blank('No messages','Inbound and outbound conversations appear when Twilio is connected.','▤')}</section>`+
   `<section class="panel"><h2>Compose</h2><p>Sending requires documented SMS consent and an approved Twilio A2P campaign.</p><form id="send-form"><label>Contact<select name="contact_id" required><option value="">Select contact</option>${contacts.map(c=>`<option value="${esc(c.id)}">${esc(c.name)} — ${esc(c.phone)}</option>`).join('')}</select></label><label>Message<textarea name="body" required maxlength="1600" placeholder="Write a message..."></textarea></label><div class="form-actions"><button type="button" class="secondary" id="ai-draft">✦ AI draft</button><button type="button" class="secondary" id="make-call">Call contact</button><button class="primary" type="submit">Send SMS</button></div></form><div class="hint">AI drafting is optional and never auto-sends. Calls bridge through a verified Twilio number to your phone.</div></section></div>`;
   $('send-form').onsubmit=async e=>{e.preventDefault();if(!confirm('Send this SMS through Twilio? Confirm consent and campaign approval first.'))return;try{await api(aid()+'/messages/send',{method:'POST',body:JSON.stringify({contact_id:formValue(e.target,'contact_id'),body:formValue(e.target,'body')})});await render();notice('Message submitted to Twilio.');}catch(err){notice(err.message,true);}};
   $('ai-draft').onclick=async()=>{const f=$('send-form');if(!formValue(f,'contact_id'))return notice('Select a contact first.',true);try{const result=await api(aid()+'/ai/draft',{method:'POST',body:JSON.stringify({contact_id:formValue(f,'contact_id'),body:formValue(f,'body')||'Write a polite, concise reply'})});f.elements.body.value=result.draft;notice('Draft generated. Review carefully before sending.');}catch(err){notice(err.message,true);}};
   $('make-call').onclick=async()=>{const f=$('send-form');if(!formValue(f,'contact_id'))return notice('Select a contact first.',true);const operator_phone=prompt('Your phone number (Twilio calls this number first, in E.164 format)');if(!operator_phone)return;try{await api(aid()+'/calls',{method:'POST',body:JSON.stringify({contact_id:formValue(f,'contact_id'),operator_phone})});notice('Twilio call initiated. Answer your phone to connect.');}catch(err){notice(err.message,true);}};
}
async function campaigns(){
 const items=await api(aid()+'/campaigns');
 $('page').innerHTML=sub('Campaign studio','Compose and queue permission-based SMS broadcasts. Dispatch requires carrier approval.',`<button class="primary" id="show-campaign">+ Create campaign</button>`)+
 `<div class="panel form-panel hidden" id="campaign-box"><h2>Draft an SMS campaign</h2><form id="campaign-form"><label>Campaign name<input name="name" required placeholder="Spring acquisitions follow-up"></label><label>SMS body<textarea name="body" required maxlength="1600" placeholder="Write an approved, relevant message with opt-out instructions"></textarea></label><button class="primary">Save draft</button></form></div>`+
 `<div class="panel"><h2>Campaigns</h2><div class="table-wrap">${items.length?`<table class="table"><thead><tr><th>Campaign</th><th>Message</th><th>Status</th><th>Actions</th></tr></thead><tbody>${items.map(c=>`<tr><td class="name">${esc(c.name)}</td><td>${esc(c.body.slice(0,110))}</td><td>${pill(c.state,'gray')}</td><td>${c.state==='draft'?`<button class="secondary" data-queue="${esc(c.id)}">Queue approved contacts</button>`:'—'}</td></tr>`).join('')}</tbody></table>`:blank('No campaigns','Create your first draft. Messages never go out before an explicit send authorization.','◉')}</div></div>`;
 $('show-campaign').onclick=()=>$('campaign-box').classList.toggle('hidden');
 $('campaign-form').onsubmit=async e=>{e.preventDefault();try{await api(aid()+'/campaigns',{method:'POST',body:JSON.stringify({name:formValue(e.target,'name'),body:formValue(e.target,'body')})});await render();notice('Campaign saved as draft.');}catch(err){notice(err.message,true);}};
 document.querySelectorAll('[data-queue]').forEach(b=>b.onclick=async()=>{if(!confirm('Queue this campaign to ALL SMS-consented contacts in this agency? Check campaign, sender identity and legal compliance.'))return;try{const r=await api(aid()+'/campaigns/'+encodeURIComponent(b.dataset.queue)+'/queue',{method:'POST'});await render();notice(`${r.queued} approved contacts queued. Worker dispatch required.`);}catch(err){notice(err.message,true);}});
}
async function workflows(){
 const list=await api(aid()+'/workflows');
 $('page').innerHTML=sub('Automations','Rule-based branching for incoming SMS. The first safe action tags matching contacts.',`<button class="primary" id="show-workflow">+ New rule</button>`)+
 `<div class="panel form-panel hidden" id="workflow-box"><h2>Create keyword branch</h2><form id="workflow-form"><label>Rule name<input name="name" required placeholder="Motivated seller inquiry"></label><div class="field-grid"><label>Incoming message contains<input name="keyword" required placeholder="sell my house"></label><label>Then add tag<input name="add_tag" required placeholder="seller-intent"></label></div><button class="primary">Activate rule</button></form></div>`+
 `<div class="panel"><h2>Active logic</h2>${list.length?list.map(w=>`<div class="data-row"><div><strong>${esc(w.name)}</strong><br><small>IF incoming message contains <span class="code">${esc(w.keyword)}</span> THEN add tag <span class="code">${esc(w.add_tag)}</span></small></div>${pill(w.enabled?'Active':'Paused',w.enabled?'':'gray')}</div>`).join(''):blank('No rules configured','Create a keyword rule to classify incoming leads automatically.','◇')}</div>`;
 $('show-workflow').onclick=()=>$('workflow-box').classList.toggle('hidden');
 $('workflow-form').onsubmit=async e=>{e.preventDefault();try{await api(aid()+'/workflows',{method:'POST',body:JSON.stringify({name:formValue(e.target,'name'),keyword:formValue(e.target,'keyword'),add_tag:formValue(e.target,'add_tag')})});await render();notice('Keyword branch activated.');}catch(err){notice(err.message,true);}};
}
async function settings(){
 const s=await api(aid()+'/settings');
 $('page').innerHTML=sub('Integrations','Manage the dedicated communications setup for this agency. Credentials remain server-side.')+
 `<div class="two"><section class="panel"><h2>Twilio communications</h2><p>Configure the account and number for ${esc(activeAgency()?.name)}. Each agency can have separate credentials.</p><form id="twilio-form"><label>Twilio phone number (E.164)<input name="phone" placeholder="+12055550199" value="${esc(s.phone||'')}" required></label><label>Account SID<input name="account_sid" placeholder="AC..." value="${esc(s.twilio_account_sid||'')}" required></label><label>Auth token (encrypted on server)<input name="auth_token" type="password" autocomplete="off" required placeholder="Enter token to save or rotate"></label><label>Messaging Service SID (optional)<input name="messaging_service_sid" value="${esc(s.twilio_messaging_service_sid||'')}" placeholder="MG..."></label><label>Forward inbound calls to (E.164; optional)<input name="forward_phone" value="${esc(s.forward_phone||'')}" placeholder="+12055550199"></label><button class="primary">Save credentials</button></form></section><section class="panel"><h2>Readiness checklist</h2><div class="data-row"><span>Twilio configured</span>${pill(s.twilio_configured?'Yes':'No',s.twilio_configured?'':'red')}</div><div class="data-row"><span>A2P verified for agency</span>${pill(s.a2p_verified?'Yes':'Pending',s.a2p_verified?'':'red')}</div><div class="data-row"><span>Sending gate enabled</span>${pill(s.global_sending_enabled?'Yes':'Disabled',s.global_sending_enabled?'':'red')}</div><p class="hint">An administrator must independently verify the approved campaign and enable the production sending gate. Updating credentials resets the agency approval flag. There is no A2P bypass.</p><p class="hint">Inbound SMS webhook:<br><span class="code">/api/twilio/sms</span><br>Inbound voice webhook:<br><span class="code">/api/twilio/voice/inbound</span></p><p class="hint">Google Play: uses server-side Twilio instead of requesting restricted Android SMS/Call Log permissions.</p></section></div>`;
 $('twilio-form').onsubmit=async e=>{e.preventDefault();try{await api(aid()+'/settings/twilio',{method:'POST',body:JSON.stringify({phone:formValue(e.target,'phone'),account_sid:formValue(e.target,'account_sid'),auth_token:formValue(e.target,'auth_token'),messaging_service_sid:formValue(e.target,'messaging_service_sid'),forward_phone:formValue(e.target,'forward_phone')})});await render();notice('Credentials encrypted and saved; A2P status requires fresh verification.');}catch(err){notice(err.message,true);}};
}
$('login-form').addEventListener('submit',async e=>{e.preventDefault();$('login-error').textContent='';try{await api('/auth/login',{method:'POST',body:JSON.stringify({email:formValue(e.target,'email'),password:formValue(e.target,'password')})});state.user=await api('/me');state.csrf=state.user.csrf;await initApp();}catch(err){$('login-error').textContent=err.message;}});
$('logout').onclick=async()=>{try{await api('/auth/logout',{method:'POST'});}catch{}showLogin();};
$('agency').onchange=async e=>{state.agency=e.target.value;localStorage.setItem('strata_agency',state.agency);await render();};
document.querySelectorAll('#nav .nav-link').forEach(el=>el.onclick=async()=>{state.page=el.dataset.page;$('shell').classList.remove('menu-open');await render();});
$('mobile-menu').onclick=()=>$('shell').classList.toggle('menu-open');
$('mobile-backdrop').onclick=()=>$('shell').classList.remove('menu-open');
document.addEventListener('click',e=>{const b=e.target.closest('[data-message]');if(b){state.page='inbox';render().then(()=>{const select=$('send-form')?.elements.contact_id;if(select)select.value=b.dataset.message;});}});
boot();
