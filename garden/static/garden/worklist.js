'use strict';
const engine=GardenOffline.create({storage:localStorage,locks:navigator.locks,fetch:window.fetch.bind(window),origin:location.origin});
const el=id=>document.getElementById(id);
const escape=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let tabScope=null,busy=false,operations=Promise.resolve();
// sessionStorage is separate per tab (including after a duplicated tab diverges).
// Persist the displayed task version together with that tab's own edited note.
const FORM_KEY='garden.m2.forms.v1';
let forms=null;
function saveForms(){sessionStorage.setItem(FORM_KEY,JSON.stringify(forms));}
function clearForms(){
 forms=null;
 // A storage error must never prevent hiding private DOM after logout.
 try{sessionStorage.removeItem(FORM_KEY);}catch(_){}
}
function loadForms(s){
 const saved=forms || JSON.parse(sessionStorage.getItem(FORM_KEY)||'null');
 const next=saved && saved.scope===tabScope && saved.boundary===s.context.boundary
  ? JSON.parse(JSON.stringify(saved)) : {scope:tabScope,boundary:s.context.boundary,tasks:{}};
 for(const q of s.queue) delete next.tasks[q.task.id];
 for(const t of s.snapshot?.tasks||[]) {
  if(t.status!=='pending') delete next.tasks[t.id];
  else if((!next.tasks[t.id]||!Object.hasOwn(next.tasks[t.id],'note'))&&!s.queue.some(q=>q.task.id===t.id)) next.tasks[t.id]={task:t};
 }
 // Commit the new form model only after persistence succeeds. On failure,
 // the still-visible DOM and its version must remain paired.
 sessionStorage.setItem(FORM_KEY,JSON.stringify(next));
 forms=next;
}
const title=t=>`<h3>${escape(t.title)}</h3><small>${escape(t.plant_name)} · ${escape(t.due_date)}</small>`;
async function render(){
 const v=await engine.view(),s=v.active===tabScope?v.data:null;
 el('open').hidden=!!s;el('refresh').hidden=!s;el('signin').hidden=!!s||v.logout;el('open').textContent=v.logout?'Slutför utloggning':'Öppna inloggad trädgård';
 el('held').hidden=!s||!v.held.length;el('held').querySelector('ul').innerHTML=s?v.held.map(q=>`<li>${escape(q.key)}</li>`).join(''):'';
 el('identity').textContent=s?`${s.context.name} · ${s.context.account_name}`:'';
 el('fetched').textContent=s?.snapshot?`Senast hämtad ${new Date(s.snapshot.fetched).toLocaleString('sv-SE')}`:'';
 if(!s){clearForms();el('pending').innerHTML='';el('tasks').innerHTML='';el('history').hidden=true;el('status').textContent=v.logout?'Utloggad lokalt. Anslut för att avsluta utloggningen.':'Öppna din inloggade trädgård med nätanslutning.';return;}
 loadForms(s);
 el('history').hidden=false;
 el('status').textContent=navigator.onLine?'Synkas när appen är öppen.':'Utan nät · sparas på enheten.';
 el('pending').innerHTML=s.queue.length?'<h2>Väntar på synkning</h2>'+s.queue.map(q=>`<article class="pending">${title(q.task)}<p>${escape(({queued:'Sparad på enheten',sending:'Inväntar bekräftelse',uncertain:'Utfallet behöver stämmas av. Synka igen med nät.',conflict:'Uppgiften har ändrats.',rejected:'Handlingen avvisades. Behåll begäransnyckeln och be om hjälp.'})[q.state])}</p>${Object.hasOwn(JSON.parse(q.body),'note')?`<p>Din anteckning: ${escape(JSON.parse(q.body).note)||'(tömd)'}</p>`:''}${q.state==='conflict'?`<p>Servern: ${escape(({pending:'Planerat',completed:'Utfört',skipped:'Överhoppat',archived:'Arkiverat'})[q.current?.status]||'hämta aktuell status')} · ${escape(q.current?.note||'Ingen anteckning')}</p><div class="actions">${q.current?.status==='pending'?`<button data-retry="${q.key}">Klarmarkera senaste versionen</button>`:''}<button data-keep="${q.key}">Behåll serverns status</button></div>`:''}<details><summary>Begäransnyckel</summary>${escape(q.key)}${q.readOnlyReason || Date.now()-q.created>=GardenOffline.WEEK?'<p>Tidsgräns eller ändrad klocka. Endast läsande avstämning; be administratören kontrollera utfallet om kvitto saknas.</p>':''}</details></article>`).join(''):'';
 const tasks=s.snapshot?.tasks||[],pending=tasks.filter(t=>t.status==='pending'&&!s.queue.some(q=>q.task.id===t.id));
 el('tasks').innerHTML='<h2>Att göra</h2>'+ (pending.length?pending.map(current=>{const f=forms.tasks[current.id],t=f.task;return `<article>${title(t)}<p>${escape(t.instructions)}</p><form data-task="${t.id}"><label>Anteckning (valfri)<textarea maxlength="10000" data-note="${t.id}">${escape(Object.hasOwn(f,'note')?f.note:t.note)}</textarea></label><button type="submit">Markera som klar</button></form></article>`;}).join(''): '<p>Inga fler uppgifter i den hämtade listan.</p>');
 el('history').querySelector('div').innerHTML=tasks.filter(t=>t.status!=='pending').map(t=>`<article>${title(t)}<p>${escape({completed:'Utfört',skipped:'Överhoppat',archived:'Arkiverat'}[t.status])}${t.completed_at?' · '+escape(new Date(t.completed_at).toLocaleString('sv-SE')):''}</p><p>${escape(t.note)}</p></article>`).join('')||'<p>Ingen hämtad historik.</p>';
}
function run(fn){operations=operations.then(async()=>{busy=true;try{await fn();await render();}catch(e){await render().catch(()=>{});el('status').textContent=typeof e.message==='string'?e.message:'Kunde inte synka. Försök igen.';}finally{busy=false;}});return operations;}

async function sync(){await engine.sync(tabScope);await engine.refresh(tabScope);}
el('refresh').onclick=()=>run(sync);
el('open').onclick=()=>run(async()=>{tabScope=await engine.activate();await sync();});
el('logout').onclick=()=>{const logout=engine.logout();logout.catch(()=>{});tabScope=null;clearForms();for(const id of ['identity','fetched','pending','tasks'])el(id).textContent='';el('history').hidden=true;el('held').hidden=true;el('status').textContent='Avslutar utloggning …';run(async()=>{await logout;location.href='/accounts/login/';});};
document.addEventListener('input',e=>{
 if(!e.target.matches('[data-note]'))return;
 const f=forms?.tasks[e.target.dataset.note];if(!f)return;
 f.note=e.target.value;
 try{saveForms();}catch(err){el('status').textContent=err.message;}
});
document.addEventListener('submit',e=>{
 if(!e.target.matches('[data-task]'))return;e.preventDefault();
 // Read the actual field now, before any queued render or cross-tab update.
 const id=e.target.dataset.task,scope=tabScope,form=JSON.parse(JSON.stringify(forms.tasks[id]));
 const note=e.target.querySelector('textarea').value;
 if(Object.hasOwn(form,'note')||note!==String(form.task.note??''))form.note=note;
 run(async()=>{saveForms();await engine.enqueue(scope,form);delete forms.tasks[id];saveForms();await render();if(navigator.onLine)await sync();});
});
document.addEventListener('click',e=>{const b=e.target.closest('[data-retry],[data-keep]');if(b)run(async()=>{await engine.resolve(tabScope,b.dataset.retry||b.dataset.keep,!!b.dataset.retry);await sync();});});
window.addEventListener('storage',e=>{if(e.key===GardenOffline.KEY||e.key==='garden.m2.stop')engine.view().then(v=>{if(v.active!==tabScope)render();else if(!busy && document.activeElement?.tagName!=='TEXTAREA')render();});});
window.addEventListener('online',()=>run(sync));
window.addEventListener('pageshow',e=>{if(e.persisted)run(async()=>{if(navigator.onLine)await engine.refresh(tabScope);});});
// No background sync and no periodic surprise retries. Foreground/reconnect only.
document.addEventListener('visibilitychange',()=>{if(!document.hidden&&navigator.onLine&&!document.querySelector('textarea:focus'))run(sync);});
run(async()=>{const v=await engine.view();tabScope=v.active;if(v.data&&!v.logout){await render();if(navigator.onLine){await engine.refresh(tabScope);await sync();}}else if(!v.logout&&navigator.onLine){tabScope=await engine.activate();await sync();}});
if('serviceWorker' in navigator)navigator.serviceWorker.register('/sw.js');
