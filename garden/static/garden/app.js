const state = { data: null, view: "month", searchTimer: null, openItem: null };
const $ = selector => document.querySelector(selector);
const $$ = selector => [...document.querySelectorAll(selector)];

function csrfToken() {
  return document.cookie.split("; ").find(row => row.startsWith("csrftoken="))?.split("=")[1] || "";
}

async function api(url, options = {}) {
  const headers = {"Content-Type": "application/json", ...(options.headers || {})};
  if (options.method && options.method !== "GET") headers["X-CSRFToken"] = csrfToken();
  const response = await fetch(url, {...options, headers});
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || "Något gick fel.");
  return data;
}

function toast(message) {
  const el = $("#toast"); el.textContent = message; el.classList.add("show");
  window.setTimeout(() => el.classList.remove("show"), 2600);
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>'"]/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[char]));
}

function setView(view) {
  state.view = view;
  const titles = {month:"Den här månaden", year:"Året", plants:"Växter", settings:"Inställningar"};
  $$(".view").forEach(el => el.classList.toggle("hidden", el.id !== `view-${view}`));
  $$(".nav-link").forEach(el => el.classList.toggle("active", el.dataset.view === view));
  $("#view-title").textContent = titles[view];
  window.scrollTo({top:0, behavior:"smooth"});
}

function taskRow(task) {
  return `<div class="task-row" data-task="${task.id}">
    <button class="task-check" data-status="completed" aria-label="Markera ${escapeHtml(task.title)} som klar">✓</button>
    <button class="task-copy task-open" data-open-task="${task.id}" aria-label="Visa detaljer för ${escapeHtml(task.title)}"><strong>${escapeHtml(task.title)}</strong><span>${escapeHtml(task.item.name)} · ${new Date(task.end + "T12:00:00").toLocaleDateString("sv-SE",{day:"numeric",month:"short"})}</span></button>
    <button class="task-plant-link" data-open-item="${task.item.id}" aria-label="Visa växten ${escapeHtml(task.item.name)}">Växt</button>
  </div>`;
}

function renderTasks(groups) {
  const labels = {due:"Dags nu", overdue:"Kvar sedan tidigare", later:"Senare denna månad"};
  $("#task-groups").innerHTML = ["due","overdue","later"].map(key => `<section class="task-section"><h3>${labels[key]}</h3>${groups[key].length ? groups[key].map(taskRow).join("") : `<div class="empty-inline">${key === "due" ? "Inget akut – trädgården är i fas." : "Inga uppgifter här."}</div>`}</section>`).join("");
}

function plantRow(item) {
  const glyphs = {apple:"●",plum:"●",berry:"✣",rose:"✿",hedge:"▥",tomato:"◉",leaf:"♧"};
  const meta = [item.cultivar ? `Sort: ${item.cultivar}` : "Sort ej angiven", item.category, item.quantity > 1 ? `${item.quantity} st` : ""].filter(Boolean).join(" · ");
  return `<button class="plant-row" data-open-item="${item.id}"><span class="plant-icon">${glyphs[item.icon] || "♧"}</span><span><strong>${escapeHtml(item.name)}</strong><span>${escapeHtml(meta || "Lägg till detaljer")}</span></span></button>`;
}

function render(data) {
  state.data = data;
  $("#hero-date").textContent = new Date(data.today + "T12:00:00").toLocaleDateString("sv-SE", {weekday:"long", day:"numeric", month:"long"});
  $("#hero-month").textContent = data.month_name[0].toUpperCase() + data.month_name.slice(1);
  $("#progress-value").textContent = `${data.progress}%`;
  const first = data.tasks.due[0] || data.tasks.overdue[0] || data.tasks.later[0];
  $("#hero-next").textContent = first ? `Nästa steg: ${first.title.toLowerCase()} för ${first.item.name.toLowerCase()}.` : "Allt är i fas. Njut av trädgården en stund.";
  renderTasks(data.tasks);
  $("#year-grid").innerHTML = data.year.map(row => `<button class="year-month ${row.month === new Date(data.today).getMonth()+1 ? "current" : ""}" data-view="month"><strong>${row.name[0].toUpperCase()+row.name.slice(1)}</strong><span>${row.open ? `${row.open} öppna uppgifter` : "Lugn månad"}</span></button>`).join("");
  $("#plant-list").innerHTML = data.items.map(plantRow).join("");
  const suggestions = ["Päron","Vinbär","Björnbär","Krusbär","Valnöt","Kinesisk toon","Grönsaker"];
  $("#quick-adds").innerHTML = suggestions.map(name => `<button class="quick-chip" data-quick-add="${name}">+ ${name}</button>`).join("");
  for (const field of ["city","cultivation_zone","exposure"]) $("#settings-form").elements[field].value = data.settings[field] || "";
  $("#proposal-count").textContent = data.pending_proposals;
}

async function load() {
  try {
    render(await api("/api/bootstrap/"));
    $("#loading").classList.add("hidden");
    setView(state.view);
  } catch (error) {
    $("#loading").classList.add("hidden"); $("#error-state").classList.remove("hidden"); $("#error-message").textContent = error.message;
  }
}

async function updateTask(id, status) {
  await api(`/api/tasks/${id}/`, {method:"PATCH", body:JSON.stringify({status})});
  toast(status === "completed" ? "Klart – fint jobbat" : status === "skipped" ? "Hoppad över för den här gången" : "Uppgiften är öppen igen");
  await load();
  if (status !== "pending") {
    const undo = document.createElement("button"); undo.className = "text-button"; undo.textContent = "Ångra";
    undo.onclick = () => updateTask(id, "pending"); $("#toast").append(" ", undo); $("#toast").classList.add("show");
  }
}

function formatTaskDate(value) {
  return new Date(`${value}T12:00:00`).toLocaleDateString("sv-SE", {day:"numeric", month:"long"});
}

async function openTask(id) {
  const dialog = $("#detail-dialog"), content = $("#detail-content");
  content.innerHTML = `<div class="loading-state"><span class="spinner"></span></div>`;
  dialog.showModal();
  try {
    const {task} = await api(`/api/tasks/${id}/`);
    const timing = task.start === task.end ? formatTaskDate(task.start) : `${formatTaskDate(task.start)}–${formatTaskDate(task.end)}`;
    const sources = task.sources?.length ? `<section class="detail-section"><h3>Källor</h3>${task.sources.map(url => `<a class="source-link" href="${escapeHtml(url)}" target="_blank" rel="noopener">${escapeHtml(url)} ↗</a>`).join("")}</section>` : "";
    content.innerHTML = `<div class="task-detail" data-task="${task.id}"><p class="eyebrow">Uppgift</p><h2>${escapeHtml(task.title)}</h2>
      <div class="detail-meta"><span class="pill">${escapeHtml(task.item.name)}</span><span class="pill">${timing}</span>${task.manual ? '<span class="pill">Egen uppgift</span>' : ""}${task.conditional ? '<span class="pill">Bedöm efter läget</span>' : ""}</div>
      <section class="detail-section"><h3>Så gör du</h3><p>${escapeHtml(task.instructions || "Inga ytterligare instruktioner har lagts till.")}</p></section>
      <section class="detail-section"><h3>När</h3><p>Gör uppgiften någon gång ${task.start === task.end ? "den" : "mellan"} ${timing}. Den ligger kvar tills du markerar den som klar eller väljer att hoppa över den.</p></section>
      <div class="task-detail-actions"><button class="button secondary" data-open-item="${task.item.id}">Visa växt</button><button class="button" data-status="completed">Markera som klar</button></div>
      <button class="skip-task-button" data-skip-task="${task.id}">Hoppa över uppgiften</button>${sources}</div>`;
  } catch (error) {
    content.innerHTML = `<h2>Kunde inte öppna uppgiften</h2><p>${escapeHtml(error.message)}</p>`;
  }
}

function openForm(title, body, submitLabel, onSubmit) {
  const dialog = $("#form-dialog"), form = $("#dynamic-form");
  $("#form-content").innerHTML = `<h2>${title}</h2><div class="form-stack">${body}<div class="form-actions"><button class="button secondary" type="button" data-close>Avbryt</button><button class="button" type="submit">${submitLabel}</button></div></div>`;
  form.onsubmit = async event => { event.preventDefault(); const button = form.querySelector("[type=submit]"); button.disabled = true; button.textContent = "Sparar …"; try { await onSubmit(new FormData(form)); dialog.close(); await load(); } catch(e) { toast(e.message); button.disabled=false; button.textContent=submitLabel; } };
  dialog.showModal();
}

function newItem(prefill = "") {
  openForm("Lägg till i trädgården", `<p class="muted">När växten sparas hämtas också ett källbelagt skötselförslag för din granskning.</p><label>Namn<input name="name" required value="${escapeHtml(prefill)}"></label><label>Typ<select name="kind"><option value="individual">Enskild växt</option><option value="group">Grupp</option><option value="bed">Odlingsbädd</option></select></label><label>Kategori<input name="category" placeholder="Fruktträd, bär, häck …"></label><label>Sort<input name="cultivar"></label><label>Antal<input name="quantity" type="number" min="1" value="1"></label><label>Placering<input name="location"></label><label>Egna anteckningar<textarea name="notes"></textarea></label>`, "Lägg till och sök råd", async fd => {
    const result = await api("/api/items/", {method:"POST", body:JSON.stringify(Object.fromEntries(fd))}); toast(result.research_error ? `Växten lades till. ${result.research_error}` : "Växten och skötselförslaget är tillagda"); openItem(result.item.id);
  });
}

function newTask() {
  const items = state.data.items.map(i => `<option value="${i.id}">${escapeHtml(i.name)}</option>`).join("");
  openForm("Egen uppgift", `<label>Uppgift<input name="title" required></label><label>Växt eller odling<select name="item_id">${items}</select></label><label>Från<input name="window_start" type="date" required value="${state.data.today}"></label><label>Till<input name="window_end" type="date" value="${state.data.today}"></label><label>Anteckning<textarea name="instructions"></textarea></label>`, "Skapa uppgift", async fd => { await api("/api/tasks/", {method:"POST", body:JSON.stringify(Object.fromEntries(fd))}); toast("Uppgiften är tillagd"); });
}

async function openItem(id) {
  const dialog = $("#detail-dialog"), content = $("#detail-content");
  content.innerHTML = `<div class="loading-state"><span class="spinner"></span></div>`; dialog.showModal();
  try {
    const data = await api(`/api/items/${id}/`), item = data.item, proposal = data.proposals?.[0], plan = proposal || item.plan;
    state.openItem = item;
    const kindName = item.kind === "bed" ? "Odlingsbädd" : item.kind === "group" ? "Grupp" : "Enskild växt";
    content.innerHTML = `<div class="detail-heading"><div><p class="eyebrow">${escapeHtml(kindName)}</p><h2>${escapeHtml(item.name)}</h2></div><button class="button secondary" data-edit-item="${item.id}">Redigera växt</button></div>
      <dl class="plant-facts"><div><dt>Sort</dt><dd>${escapeHtml(item.cultivar || "Ej angiven")}</dd></div><div><dt>Antal</dt><dd>${item.quantity}</dd></div><div><dt>Kategori</dt><dd>${escapeHtml(item.category || "Ej angiven")}</dd></div><div><dt>Placering</dt><dd>${escapeHtml(item.location || "Ej angiven")}</dd></div>${item.age_stage?`<div><dt>Ålder/stadium</dt><dd>${escapeHtml(item.age_stage)}</dd></div>`:""}</dl>
      ${item.notes?`<p>${escapeHtml(item.notes)}</p>`:""}
      <section class="detail-section"><h3>Nästa uppgifter</h3>${item.next_tasks?.length?item.next_tasks.map(taskRow).join(""):'<p class="muted">Inga aktiva uppgifter ännu.</p>'}</section>
      <section class="detail-section"><h3>Skötselråd</h3>${plan?`<p>${escapeHtml(plan.summary)}</p>${plan.warnings?.map(w=>`<p>⚠ ${escapeHtml(w)}</p>`).join("")||""}`:'<p class="muted">Hämta ett källbelagt förslag och granska det innan något läggs i årshjulet.</p>'}<button class="button secondary" data-research="${item.id}">${plan?"Uppdatera skötselråd":"Hämta skötselråd"}</button></section>
      ${proposal?proposalMarkup(proposal):planSources(plan)}`;
  } catch(e) { content.innerHTML = `<h2>Kunde inte öppna växten</h2><p>${escapeHtml(e.message)}</p>`; }
}

function editItem(item) {
  $("#detail-dialog").close();
  openForm("Redigera växt", `<label>Namn<input name="name" required value="${escapeHtml(item.name)}"></label><label>Sort<input name="cultivar" value="${escapeHtml(item.cultivar)}" placeholder="Till exempel Glen Ample"></label><div id="reanalyze-choice" class="reanalyze-choice hidden"><p><strong>Sorten eller egna anteckningar kan påverka skötselråden.</strong></p><label class="check-row"><input type="checkbox" name="refresh_research" checked><span>Hämta ett nytt källbelagt förslag efter att växten sparats</span></label><small>Anteckningar behandlas som observationer. Det äldre ogranskade förslaget ersätts; godkända uppgifter och historik lämnas kvar.</small></div><label>Typ<select name="kind"><option value="individual">Enskild växt</option><option value="group">Grupp</option><option value="bed">Odlingsbädd</option></select></label><label>Kategori<input name="category" value="${escapeHtml(item.category)}"></label><label>Antal<input name="quantity" type="number" min="1" value="${item.quantity}"></label><label>Ålder eller stadium<input name="age_stage" value="${escapeHtml(item.age_stage)}"></label><label>Placering<input name="location" value="${escapeHtml(item.location)}"></label><label>Egna anteckningar<textarea name="notes">${escapeHtml(item.notes)}</textarea></label>`, "Spara växt", async fd => {
    const values = Object.fromEntries(fd);
    const refresh = values.refresh_research === "on" && (values.cultivar.trim() !== item.cultivar.trim() || values.notes.trim() !== item.notes.trim());
    delete values.refresh_research;
    values.quantity = Number(values.quantity);
    await api(`/api/items/${item.id}/`, {method:"PATCH", body:JSON.stringify(values)});
    let message = "Växten är uppdaterad";
    if (refresh) {
      try {
        await api(`/api/items/${item.id}/research/`, {method:"POST", body:"{}"});
        message = "Växten är uppdaterad och ett nytt förslag väntar på granskning";
      } catch (error) {
        message = `Växten sparades, men råden kunde inte uppdateras: ${error.message}`;
      }
    }
    toast(message);
  });
  const form = $("#dynamic-form");
  form.elements.kind.value = item.kind;
  const cultivar = form.elements.cultivar, notes = form.elements.notes;
  const updateChoice = () => $("#reanalyze-choice").classList.toggle("hidden", cultivar.value.trim() === item.cultivar.trim() && notes.value.trim() === item.notes.trim());
  cultivar.addEventListener("input", updateChoice);
  notes.addEventListener("input", updateChoice);
  updateChoice();
}

function planSources(plan) {
  if (!plan?.sources?.length) return "";
  return `<section class="detail-section"><h3>Källor</h3>${plan.sources.map(s=>`<a class="source-link" href="${escapeHtml(s.url)}" target="_blank" rel="noopener">${escapeHtml(s.title)} ↗</a>`).join("")}</section>`;
}

function proposalMarkup(plan) {
  return `<section class="detail-section proposal" data-proposal="${plan.proposal_id}"><p class="eyebrow">Väntar på din granskning</p><h3>Föreslagna uppgifter</h3>${plan.rules.map(r=>`<div class="rule-choice"><input aria-label="Välj ${escapeHtml(r.title)}" type="checkbox" value="${r.id}" ${r.source_validated?"checked":"disabled"}><span><strong>${escapeHtml(r.title)}</strong><small>${monthName(r.start_month)}–${monthName(r.end_month)} · ${r.confidence === "high"?"hög":r.confidence === "medium"?"medel":"låg"} säkerhet${!r.source_validated?" · saknar verifierad källa":""}</small><small>${escapeHtml(r.instructions)}</small><button class="text-button" data-edit-rule="${r.id}" data-title="${escapeHtml(r.title)}" data-instructions="${escapeHtml(r.instructions)}" data-cadence="${r.cadence}" data-start="${r.start_month}" data-end="${r.end_month}">Redigera</button></span></div>`).join("")}<div class="form-actions"><button class="text-button" data-reject="${plan.proposal_id}">Avvisa</button><button class="button" data-approve="${plan.proposal_id}">Godkänn valda</button></div></section>${planSources(plan)}`;
}

function monthName(month){return ["jan","feb","mar","apr","maj","jun","jul","aug","sep","okt","nov","dec"][month-1]}

async function research(itemId, button) {
  button.disabled=true; const original=button.textContent; button.textContent="Söker hos betrodda källor …";
  try { await api(`/api/items/${itemId}/research/`, {method:"POST", body:"{}"}); toast("Förslaget är redo att granskas"); await openItem(itemId); }
  catch(e){toast(e.message); button.disabled=false; button.textContent=original;}
}

async function approve(id) {
  const rules = $$(`.proposal[data-proposal="${id}"] input:checked`).map(el=>Number(el.value));
  await api(`/api/proposals/${id}/approve/`, {method:"POST", body:JSON.stringify({rule_ids:rules})}); toast(`${rules.length} uppgifter godkända`); $("#detail-dialog").close(); await load();
}

function editRule(button) {
  $("#detail-dialog").close();
  openForm("Redigera förslag", `<label>Uppgift<input name="title" required value="${escapeHtml(button.dataset.title)}"></label><label>Instruktion<textarea name="instructions">${escapeHtml(button.dataset.instructions)}</textarea></label><label>Återkomst<select name="cadence"><option value="one_off">En gång</option><option value="seasonal">En gång per säsong</option><option value="monthly">Varje månad i fönstret</option></select></label><div class="field-grid"><label>Från månad<input name="start_month" type="number" min="1" max="12" value="${button.dataset.start}"></label><label>Till månad<input name="end_month" type="number" min="1" max="12" value="${button.dataset.end}"></label></div>`, "Spara ändring", async fd => { const data=Object.fromEntries(fd); data.start_month=Number(data.start_month); data.end_month=Number(data.end_month); await api(`/api/rules/${button.dataset.editRule}/`,{method:"PATCH",body:JSON.stringify(data)}); toast("Förslaget är uppdaterat"); $("#detail-dialog").close(); await load(); });
  $("#dynamic-form").elements.cadence.value=button.dataset.cadence;
}

async function saveSettings(event) {
  event.preventDefault(); const data=Object.fromEntries(new FormData(event.target)); await api("/api/settings/",{method:"PATCH",body:JSON.stringify(data)}); toast("Trädgårdsprofilen är sparad"); await load();
}

function urlBase64ToUint8Array(base64String) { const padding="=".repeat((4-base64String.length%4)%4), base64=(base64String+padding).replace(/-/g,"+").replace(/_/g,"/"), raw=atob(base64); return Uint8Array.from([...raw].map(c=>c.charCodeAt(0))); }
async function saveNotifications() {
  if (!("serviceWorker" in navigator) || !("PushManager" in window)) throw new Error("Push stöds inte i den här webbläsaren.");
  const permission=await Notification.requestPermission(); if(permission!=="granted") throw new Error("Notisbehörighet gavs inte.");
  const registration=await navigator.serviceWorker.ready, key=(await api("/api/push/public-key/")).public_key;
  let sub=await registration.pushManager.getSubscription(); if(!sub) sub=await registration.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:urlBase64ToUint8Array(key)});
  await api("/api/push/subscriptions/",{method:"POST",body:JSON.stringify({subscription:sub.toJSON(),device_name:navigator.platform||"PWA",monthly_digest:$("#notify-monthly").checked,task_reminders:$("#notify-tasks").checked})}); toast("Notisinställningarna är sparade");
}

async function runSearch(value) {
  const box=$("#search-results"); if(value.trim().length<2){box.innerHTML='<p class="muted">Skriv minst två tecken.</p>';return;}
  const {results}=await api(`/api/search/?q=${encodeURIComponent(value)}`); box.innerHTML=results.length?results.map(r=>`<button class="search-result" data-open-item="${r.type==='task'?'':r.id}" data-open-task="${r.type==='task'?r.id:''}"><strong>${escapeHtml(r.title)}</strong><span>${escapeHtml(r.subtitle)}</span></button>`).join(""):'<p class="muted">Inga träffar ännu.</p>';
}

document.addEventListener("click", async event => {
  const nav=event.target.closest("[data-view]"); if(nav){setView(nav.dataset.view);return;}
  const status=event.target.closest("[data-status]"); if(status){const taskRow=status.closest("[data-task]"); await updateTask(Number(taskRow.dataset.task),status.dataset.status); if(taskRow.classList.contains("task-detail")) $("#detail-dialog").close(); return;}
  const skip=event.target.closest("[data-skip-task]"); if(skip){if(window.confirm("Hoppa över uppgiften den här gången? Du kan ångra direkt efteråt.")){ $("#detail-dialog").close(); await updateTask(Number(skip.dataset.skipTask),"skipped"); } return;}
  const task=event.target.closest("[data-open-task]"); if(task?.dataset.openTask){$("#search-dialog").close();openTask(Number(task.dataset.openTask));return;}
  const item=event.target.closest("[data-open-item]"); if(item?.dataset.openItem){$("#search-dialog").close(); if ($("#detail-dialog").open) $("#detail-dialog").close(); openItem(Number(item.dataset.openItem));return;}
  const quick=event.target.closest("[data-quick-add]"); if(quick){newItem(quick.dataset.quickAdd);return;}
  const researchButton=event.target.closest("[data-research]"); if(researchButton){research(researchButton.dataset.research,researchButton);return;}
  const editItemButton=event.target.closest("[data-edit-item]"); if(editItemButton && state.openItem){editItem(state.openItem);return;}
  const approveButton=event.target.closest("[data-approve]"); if(approveButton){approve(approveButton.dataset.approve);return;}
  const editButton=event.target.closest("[data-edit-rule]"); if(editButton){editRule(editButton);return;}
  const reject=event.target.closest("[data-reject]"); if(reject){await api(`/api/proposals/${reject.dataset.reject}/`,{method:"DELETE"});toast("Förslaget avvisades");$("#detail-dialog").close();await load();return;}
  if(event.target.closest("[data-close]")) $("#form-dialog").close();
  if(event.target.closest("[data-close-detail]")) $("#detail-dialog").close();
});

$("#search-trigger").onclick=()=>{$("#search-dialog").showModal();setTimeout(()=>$("#global-search").focus(),50)};
$("#global-search").addEventListener("input",event=>{clearTimeout(state.searchTimer);state.searchTimer=setTimeout(()=>runSearch(event.target.value),180)});
$("#new-item").onclick=()=>newItem(); $("#new-task").onclick=newTask; $("#settings-form").onsubmit=saveSettings;
$("#save-notifications").onclick=()=>saveNotifications().catch(e=>toast(e.message));
$("#test-notification").onclick=()=>api("/api/push/test/",{method:"POST",body:"{}"}).then(r=>toast(r.sent?"Testnotisen skickades":"Ingen aktiv enhet hittades")).catch(e=>toast(e.message));
document.addEventListener("keydown",event=>{if((event.metaKey||event.ctrlKey)&&event.key.toLowerCase()==="k"){event.preventDefault();$("#search-trigger").click()}if(event.key==="Escape")$$('dialog[open]').forEach(d=>d.close())});
if("serviceWorker" in navigator) window.addEventListener("load",()=>navigator.serviceWorker.register("/sw.js"));
load();
