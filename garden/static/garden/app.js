const savedTaskView = window.localStorage.getItem("garden-task-view");
const state = { data: null, view: "month", taskView: ["work", "area"].includes(savedTaskView) ? savedTaskView : "work", searchTimer: null, toastTimer: null, openItem: null, selectedMonth: new Date().getMonth()+1, selectedYear: new Date().getFullYear(), rules: new Map(), settingsDirty: false, reviewDrafts: new Map(), loaded: false, scroll: {} };
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
  state.scroll[state.view] = window.scrollY;
  state.view = view;
  const titles = {month:"Nu", year:"Året", plants:"Trädgården", settings:"Inställningar"};
  $$(".view").forEach(el => el.classList.toggle("hidden", el.id !== `view-${view}`));
  $$(".nav-link").forEach(el => el.classList.toggle("active", el.dataset.view === view));
  $("#view-title").textContent = titles[view];
  window.scrollTo({top:state.scroll[view] || 0});
  if (view === "year") loadMonth().catch(e=>toast(e.message));
}

function formatShortDate(value) {
  return new Date(`${value}T12:00:00`).toLocaleDateString("sv-SE", {day:"numeric", month:"short", ...(value.slice(0,4) !== state.data?.today.slice(0,4) ? {year:"numeric"} : {})});
}

function taskWindow(task) {
  return task.start === task.end ? formatShortDate(task.start) : `${formatShortDate(task.start)}–${formatShortDate(task.end)}`;
}

function taskRow(task) {
  const place = [task.area?.name || "Inte placerat", task.location_detail].filter(Boolean).join(" · ");
  return `<div class="task-row" data-task="${task.id}">
    ${task.status === "pending" ? `<button class="task-check" data-status="completed" aria-label="Markera ${escapeHtml(task.title)} som klar">✓</button>` : `<span class="task-state">${escapeHtml(statusName(task.status))}</span>`}
    <button class="task-copy task-open" data-open-task="${task.id}" aria-label="Visa detaljer för ${escapeHtml(task.title)}"><span class="task-row-top"><strong>${escapeHtml(task.item.name)}</strong><span>${escapeHtml(taskWindow(task))}</span></span><span class="task-title">${escapeHtml(task.title)}</span><span class="task-instruction">${escapeHtml(task.relevance_reason || "Öppna för instruktioner.")}</span><span class="task-place">${escapeHtml(place)}</span></button>
    <button class="task-plant-link" data-open-item="${task.item.id}" aria-label="Visa växten ${escapeHtml(task.item.name)}">Växt</button>
  </div>`;
}

function renderTasks(groups) {
  $$("[data-task-view]").forEach(button => {button.classList.toggle("active", button.dataset.taskView === state.taskView);button.setAttribute("aria-pressed", String(button.dataset.taskView === state.taskView));});
  const sections = [["Aktuellt", [...groups.overdue, ...groups.due]], ["Kommande", groups.later]];
  $("#task-groups").innerHTML = sections.map(([label, tasks]) => {
    if (!tasks.length) return label === "Aktuellt" ? '<p class="empty-inline">Inga aktuella arbeten. Nästa säsongsarbete visas under Kommande.</p>' : '';
    const key = t => state.taskView === "work" ? t.category : t.area?.name || "Inte placerat";
    const sorted = [...tasks].sort((a,b)=>a.end.localeCompare(b.end) || a.title.localeCompare(b.title,"sv"));
    const keys = [...new Set(sorted.map(key))];
    return `<section><h3 class="period-heading">${label}</h3>${keys.map(k=>`<section class="work-group"><div class="round-heading"><h4>${escapeHtml(k)}</h4></div>${sorted.filter(t=>key(t)===k).map(taskRow).join('')}</section>`).join('')}</section>`;
  }).join('');
}

function statusName(status) {return {pending:"Planerat", completed:"Utfört", skipped:"Överhoppat", archived:"Arkiverat"}[status] || status;}
function adviceMarkup(r) {
  return `<article class="advice-row"><strong>${escapeHtml(r.title)}</strong><p>${escapeHtml(r.item.name)} · ${escapeHtml(r.scope)}</p><p>${escapeHtml(r.need_condition || r.relevance_reason)}</p><details><summary>Instruktion och källor</summary><p>${escapeHtml(r.instructions)}</p>${r.source_urls.map(u=>`<a class="source-link" href="${escapeHtml(u)}" target="_blank" rel="noopener">${escapeHtml(u)}</a>`).join('')}</details><div class="form-actions">${r.advice_kind === 'on_demand' ? `<button class="button secondary" data-need="${r.work_id}">Behövs nu</button>` : ''}<button class="text-button" data-exclude="${r.work_id}">Inte relevant här</button></div></article>`;
}

async function loadMonth() {
  const year = state.selectedYear, month = state.selectedMonth;
  const data = await api(`/api/month/?year=${year}&month=${month}`);
  if (year !== state.selectedYear || month !== state.selectedMonth) return;
  $$("[data-month]").forEach(b=>b.setAttribute('aria-pressed',String(Number(b.dataset.month)===month)));
  data.counts.forEach(row=>{const button=$(`[data-month="${row.month}"]`);if(button)button.querySelector("span").textContent=row.open ? `${row.open} ${row.open === 1 ? "planerat arbete" : "planerade arbeten"}` : "Inga planerade arbeten";});
  $("#month-detail").innerHTML = `<h3>${monthName(month)} ${year}</h3><h4>Planerade arbeten</h4>${data.planned.length ? data.planned.map(taskRow).join('') : '<p class="muted">Inga planerade arbeten.</p>'}<h4>Historik</h4>${data.history.length ? data.history.map(taskRow).join('') : '<p class="muted">Ingen registrerad historik under månaden.</p>'}`;
}

async function openReview() {
  const dialog = $("#detail-dialog");
  $("#detail-content").innerHTML = '<p>Hämtar granskningskön …</p>';
  dialog.showModal();
  const {proposals} = await api('/api/proposals/');
  $("#detail-content").innerHTML = `<h2>Granska skötsel</h2>${proposals.length ? proposals.map(p=>`<h3><button class="text-button" data-open-item="${p.item.id}">${escapeHtml(p.item.name)}</button></h3>${proposalMarkup(p.plan)}`).join('') : '<p>Inga förslag väntar på granskning.</p>'}`;
}

function plantRow(item) {
  const glyphs = {apple:"●",plum:"●",berry:"✣",rose:"✿",hedge:"▥",tomato:"◉",leaf:"♧"};
  const meta = [item.cultivar ? `Sort: ${item.cultivar}` : "Sort ej angiven", item.category, item.quantity > 1 ? `${item.quantity} st` : ""].filter(Boolean).join(" · ");
  return `<button class="plant-row" data-open-item="${item.id}"><span class="plant-icon">${glyphs[item.icon] || "♧"}</span><span><strong>${escapeHtml(item.name)}</strong><span>${escapeHtml(meta || "Lägg till detaljer")}</span></span></button>`;
}

function areaOptions(selected = "") {
  const options = state.data.areas.map(area => `<option value="${area.id}" ${Number(selected) === area.id ? "selected" : ""}>${escapeHtml(area.name)}</option>`).join("");
  return `<option value="">Inte placerat</option>${options}`;
}

function renderAreas(data) {
  const list = $("#area-list"), review = $("#placement-review");
  if (!list || !review) return;
  list.innerHTML = data.areas.length ? data.areas.map(area => `<div class="area-manage-row"><span><strong>${escapeHtml(area.name)}</strong><small>${area.item_count} ${area.item_count === 1 ? "växt" : "växter"}</small></span><span><button class="text-button" type="button" data-rename-area="${area.id}" data-area-name="${escapeHtml(area.name)}">Byt namn</button><button class="text-button danger-text" type="button" data-delete-area="${area.id}" data-area-name="${escapeHtml(area.name)}">Ta bort</button></span></div>`).join("") : '<p class="muted">Skapa ditt första område. Appen gissar aldrig placering åt dig.</p>';
  review.innerHTML = data.items.map(item => `<label class="placement-row"><span><strong>${escapeHtml(item.name)}</strong><small>${escapeHtml(item.location_detail || "Ingen platsdetalj angiven")}</small></span><select data-item-area="${item.id}" aria-label="Område för ${escapeHtml(item.name)}">${areaOptions(item.area_id)}</select></label>`).join("");
}

function render(data) {
  state.data = data;
  $("#garden-name").textContent = data.settings.garden_name;
  $("#garden-city").textContent = data.settings.city;
  $("#garden-exposure").textContent = `Zon ${data.settings.cultivation_zone} · ${data.settings.exposure}`;
  $("#hero-date").textContent = new Date(data.today + "T12:00:00").toLocaleDateString("sv-SE", {weekday:"long", day:"numeric", month:"long"});
  $("#hero-month").textContent = data.month_name[0].toUpperCase() + data.month_name.slice(1);
  $("#progress-value").textContent = `${data.tasks.due.length + data.tasks.overdue.length} aktuella · ${data.completed} utförda denna månad`;
  $("#need-list").innerHTML = data.advice.length ? data.advice.map(adviceMarkup).join("") : '<p class="muted">Inga godkända behovsråd.</p>';
  $("#review-count").textContent = `(${data.pending_proposals})`;
  const first = data.tasks.overdue[0] || data.tasks.due[0] || data.tasks.later[0];
  $("#hero-next").textContent = first ? `Nästa steg: ${first.title.toLowerCase()} för ${first.item.name.toLowerCase()}.` : "Allt är i fas. Njut av trädgården en stund.";
  renderTasks(data.tasks);
  $("#year-grid").innerHTML = data.year.map(row => `<button class="year-month ${row.month === new Date(data.today).getMonth()+1 ? "current" : ""}" data-month="${row.month}" aria-pressed="${row.month === state.selectedMonth}"><strong>${row.name[0].toUpperCase()+row.name.slice(1)}</strong><span>${row.open ? `${row.open} öppna uppgifter` : "Lugn månad"}</span></button>`).join("");
  const areas = [...new Set(data.items.map(i=>i.area?.name || "Inte placerat"))];
  $("#plant-list").innerHTML = areas.map(area=>`<section><h3>${escapeHtml(area)}</h3>${data.items.filter(i=>(i.area?.name || "Inte placerat")===area).map(plantRow).join('')}</section>`).join('');
  $("#selected-year").value = state.selectedYear;
  const suggestions = ["Päron","Vinbär","Björnbär","Krusbär","Valnöt","Kinesisk toon","Grönsaker"];
  $("#quick-adds").innerHTML = suggestions.map(name => `<button class="quick-chip" data-quick-add="${name}">+ ${name}</button>`).join("");
  if (!state.settingsDirty) for (const field of ["city","cultivation_zone","exposure"]) $("#settings-form").elements[field].value = data.settings[field] || "";
  $("#proposal-count").textContent = data.pending_proposals;
  renderAreas(data);
}

async function load() {
  const scroll = window.scrollY;
  try {
    render(await api("/api/bootstrap/"));
    $("#loading").classList.add("hidden");
    if (!state.loaded) {setView(state.view); state.loaded = true;}
    if (state.view === 'year') await loadMonth();
    $("#error-state").classList.add("hidden");
    window.scrollTo({top:scroll});
  } catch (error) {
    $("#loading").classList.add("hidden"); $("#error-state").classList.remove("hidden"); $("#error-message").textContent = error.message;
  }
}

async function updateTask(id, status) {
  await api(`/api/tasks/${id}/`, {method:"PATCH", body:JSON.stringify({status})});
  if (status !== "pending" && state.data) {
    for (const key of ["overdue", "due", "later"]) state.data.tasks[key] = state.data.tasks[key].filter(task => task.id !== id);
    renderTasks(state.data.tasks);
  }
  toast(status === "completed" ? "Klart – fint jobbat" : status === "skipped" ? "Hoppad över för den här gången" : "Uppgiften är öppen igen");
  await load();
  if (status !== "pending") {
    const undo = document.createElement("button"); undo.className = "text-button"; undo.textContent = "Ångra";
    undo.onclick = event => {event.stopPropagation();updateTask(id, "pending").catch(e=>toast(e.message));}; $("#toast").append(" ", undo); $("#toast").classList.add("show");
  }
}

function formatTaskDate(value) {
  return new Date(`${value}T12:00:00`).toLocaleDateString("sv-SE", {day:"numeric", month:"long", ...(value.slice(0,4) !== state.data?.today.slice(0,4) ? {year:"numeric"} : {})});
}

async function openTask(id) {
  const dialog = $("#detail-dialog"), content = $("#detail-content");
  content.innerHTML = `<div class="loading-state"><span class="spinner"></span></div>`;
  dialog.showModal();
  try {
    const {task} = await api(`/api/tasks/${id}/`);
    const timing = task.start === task.end ? formatTaskDate(task.start) : `${formatTaskDate(task.start)}–${formatTaskDate(task.end)}`;
    const sources = task.sources?.length ? `<section class="detail-section"><h3>Källor</h3>${task.sources.map(url => `<a class="source-link" href="${escapeHtml(url)}" target="_blank" rel="noopener">${escapeHtml(url)} ↗</a>`).join("")}</section>` : "";
    const place = [task.area?.name || "Inte placerat", task.location_detail].filter(Boolean).join(" · ");
    content.innerHTML = `<div class="task-detail" data-task="${task.id}"><p class="eyebrow">${escapeHtml(task.category)}</p><h2>${escapeHtml(task.title)}</h2>
      <div class="detail-meta"><span class="pill">${escapeHtml(task.item.name)}</span><span class="pill">${escapeHtml(place)}</span><span class="pill">${timing}</span>${task.manual ? '<span class="pill">Egen uppgift</span>' : ""}${task.conditional ? '<span class="pill">Bedöm efter läget</span>' : ""}</div>
      <p>${escapeHtml(task.relevance_reason)} ${task.scope ? `Gäller: ${escapeHtml(task.scope)}.` : ""}</p>
      <section class="detail-section"><h3>Så gör du</h3><p>${escapeHtml(task.instructions || "Inga ytterligare instruktioner har lagts till.")}</p></section>
      <section class="detail-section"><h3>När</h3><p>Gör uppgiften någon gång ${task.start === task.end ? "den" : "mellan"} ${timing}. ${task.manual ? "Din egen uppgift ligger kvar tills du avslutar den." : "Automatiska tillfällen arkiveras när tidsfönstret passerat."}</p></section>
      <div class="task-detail-actions"><button class="button secondary" data-open-item="${task.item.id}">Visa växt</button>${task.status === "pending" ? '<button class="button" data-status="completed">Markera som klar</button>' : `<span>${escapeHtml(statusName(task.status))}</span>`}</div>
      ${task.status === "pending" ? `<button class="skip-task-button" data-skip-task="${task.id}">Hoppa över denna gång</button>` : ""}${task.work_id ? `<button class="text-button" data-exclude="${task.work_id}">Inte relevant här</button>` : ""}${task.note ? `<p>Anteckning: ${escapeHtml(task.note)}</p>` : ""}${task.archive_reason ? `<p>${escapeHtml(task.archive_reason)}</p>` : ""}${sources}</div>`;
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
  openForm("Lägg till i trädgården", `<p class="muted">När växten sparas hämtas också ett källbelagt skötselförslag för din granskning.</p><label>Namn<input name="name" required value="${escapeHtml(prefill)}"></label><label>Typ<select name="kind"><option value="individual">Enskild växt</option><option value="group">Grupp</option><option value="bed">Odlingsbädd</option></select></label><label>Växttyp<input name="category" placeholder="Fruktträd, bär, häck …"></label><label>Sort<input name="cultivar"></label><label>Antal<input name="quantity" type="number" min="1" value="1"></label><label>Område<select name="area_id">${areaOptions()}</select></label><label>Platsdetalj<input name="location_detail" placeholder="Till exempel vid lilla altanrabatten"></label><label>Egna anteckningar<textarea name="notes"></textarea></label>`, "Lägg till och sök råd", async fd => {
    const result = await api("/api/items/", {method:"POST", body:JSON.stringify(Object.fromEntries(fd))}); toast(result.research_error ? `Växten lades till. ${result.research_error}` : "Växten och skötselförslaget är tillagda"); openItem(result.item.id);
  });
}

function newTask() {
  const items = state.data.items.map(i => `<option value="${i.id}">${escapeHtml(i.name)}</option>`).join("");
  const categories = state.data.work_categories.map(category => `<option value="${escapeHtml(category)}">${escapeHtml(category)}</option>`).join("");
  openForm("Egen uppgift", `<label>Uppgift<input name="title" required></label><label>Arbetskategori<select name="category">${categories}</select></label><label>Växt eller odling<select name="item_id">${items}</select></label><label>Från<input name="window_start" type="date" required value="${state.data.today}"></label><label>Till<input name="window_end" type="date" value="${state.data.today}"></label><label>Instruktion<textarea name="instructions"></textarea></label>`, "Skapa uppgift", async fd => { await api("/api/tasks/", {method:"POST", body:JSON.stringify(Object.fromEntries(fd))}); toast("Uppgiften är tillagd"); });
}

async function openItem(id) {
  const dialog = $("#detail-dialog"), content = $("#detail-content");
  content.innerHTML = `<div class="loading-state"><span class="spinner"></span></div>`; dialog.showModal();
  try {
    const data = await api(`/api/items/${id}/`), item = data.item, proposal = data.proposals?.[0], plan = proposal || item.plan;
    state.openItem = item;
    const kindName = item.kind === "bed" ? "Odlingsbädd" : item.kind === "group" ? "Grupp" : "Enskild växt";
    content.innerHTML = `<div class="detail-heading"><div><p class="eyebrow">${escapeHtml(kindName)}</p><h2>${escapeHtml(item.name)}</h2></div><button class="button secondary" data-edit-item="${item.id}">Redigera växt</button></div>
      <dl class="plant-facts"><div><dt>Sort</dt><dd>${escapeHtml(item.cultivar || "Ej angiven")}</dd></div><div><dt>Antal</dt><dd>${item.quantity}</dd></div><div><dt>Växttyp</dt><dd>${escapeHtml(item.category || "Ej angiven")}</dd></div><div><dt>Område</dt><dd>${escapeHtml(item.area?.name || "Inte placerat")}</dd></div><div><dt>Platsdetalj</dt><dd>${escapeHtml(item.location_detail || "Ej angiven")}</dd></div>${item.age_stage?`<div><dt>Ålder/stadium</dt><dd>${escapeHtml(item.age_stage)}</dd></div>`:""}</dl>
      ${item.notes?`<p>${escapeHtml(item.notes)}</p>`:""}
      <section class="detail-section"><h3>Nästa uppgifter</h3>${item.next_tasks?.length?item.next_tasks.map(taskRow).join(""):'<p class="muted">Inga aktiva uppgifter ännu.</p>'}</section>
      <section class="detail-section"><h3>Skötselråd</h3>${plan?`<p>${escapeHtml(plan.summary)}</p>${plan.warnings?.map(w=>`<p>⚠ ${escapeHtml(w)}</p>`).join("")||""}`:'<p class="muted">Hämta ett källbelagt förslag och granska det innan något läggs i årshjulet.</p>'}<button class="button secondary" data-research="${item.id}">${plan?"Uppdatera skötselråd":"Hämta skötselråd"}</button></section>
      <section class="detail-section"><h3>Vid behov och allmänna råd</h3>${item.advice?.map(adviceMarkup).join('') || '<p>Inga råd ännu.</p>'}</section>
      <details class="detail-section"><summary>Historik (${item.history?.length || 0})</summary>${item.history?.map(taskRow).join('') || '<p>Ingen historik ännu.</p>'}</details>
      <details class="detail-section"><summary>Bortval (${item.excluded?.length || 0})</summary>${item.excluded?.map(w=>`<p>${escapeHtml(w.title)} · ${escapeHtml(w.scope)} <button class="text-button" data-restore="${w.id}">Återställ</button></p>`).join('') || '<p>Inga beständiga bortval.</p>'}</details>
      ${proposal?proposalMarkup(proposal):planSources(plan)}`;
  } catch(e) { content.innerHTML = `<h2>Kunde inte öppna växten</h2><p>${escapeHtml(e.message)}</p>`; }
}

function editItem(item) {
  $("#detail-dialog").close();
  openForm("Redigera växt", `<label>Namn<input name="name" required value="${escapeHtml(item.name)}"></label><label>Sort<input name="cultivar" value="${escapeHtml(item.cultivar)}" placeholder="Till exempel Glen Ample"></label><div id="reanalyze-choice" class="reanalyze-choice hidden"><p><strong>Sorten eller egna anteckningar kan påverka skötselråden.</strong></p><label class="check-row"><input type="checkbox" name="refresh_research" checked><span>Hämta ett nytt källbelagt förslag efter att växten sparats</span></label><small>Anteckningar behandlas som observationer. Det äldre ogranskade förslaget ersätts; godkända uppgifter och historik lämnas kvar.</small></div><label>Typ<select name="kind"><option value="individual">Enskild växt</option><option value="group">Grupp</option><option value="bed">Odlingsbädd</option></select></label><label>Växttyp<input name="category" value="${escapeHtml(item.category)}"></label><label>Antal<input name="quantity" type="number" min="1" value="${item.quantity}"></label><label>Ålder eller stadium<input name="age_stage" value="${escapeHtml(item.age_stage)}"></label><label>Område<select name="area_id">${areaOptions(item.area_id)}</select></label><label>Platsdetalj<input name="location_detail" value="${escapeHtml(item.location_detail)}"></label><label>Egna anteckningar<textarea name="notes">${escapeHtml(item.notes)}</textarea></label>`, "Spara växt", async fd => {
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
  const comparison = plan.comparison;
  const labels = {new:'Nytt', changed:'Ändrat', unchanged:'Oförändrat', removed:'Tas bort'};
  plan.rules.forEach(r=>state.rules.set(r.id, r));
  return `<section class="detail-section proposal" data-proposal="${plan.proposal_id}" data-token="${comparison.token}"><p class="eyebrow">Väntar på din granskning</p><h3>Förändringar i skötseln</h3><p>${escapeHtml(plan.summary)}</p>${comparison.context_changed ? '<p class="review-notice">Växtinformation eller historik har ändrats sedan analysen. Jämförelsen nedan använder dagens uppgifter.</p>' : ''}${plan.rules.map(r=>{
    const row = comparison.rows.find(x=>x.rule_id===r.id);
    const draft = state.reviewDrafts.get(r.id);
    return `<div class="rule-choice"><input aria-label="Välj ${escapeHtml(r.title)}" type="checkbox" value="${r.id}" ${(draft?.checked ?? row.preselected) ? 'checked' : ''} ${row.error ? 'disabled' : ''}><span><strong>${escapeHtml(r.title)}</strong><small>${labels[row.change]} · ${escapeHtml(r.scope)} · ${{planned:'Planerat arbete', on_demand:'Vid behov', general:'Allmänt råd', review:'Kräver klassificering'}[r.advice_kind]}</small><small>${escapeHtml(r.relevance_reason)}</small>${row.history_count ? `<small>${row.history_count} tidigare utförda eller överhoppade tillfällen respekteras.</small>` : ""}<small>${r.cadence === 'one_off' ? `${escapeHtml(r.one_off_date)}–${escapeHtml(r.one_off_end)}` : `${monthName(r.start_month)}–${monthName(r.end_month)}`}</small>${row.error ? `<p class="review-notice">${escapeHtml(row.error)}</p>` : ''}${row.conflicts.length ? `<p class="review-notice">Möjligt överlapp: ${row.conflicts.map(c=>`${escapeHtml(c.title)} (${escapeHtml(c.scope)})`).join(', ')}</p><label>Hur har överlappet lösts?<textarea data-resolution="${r.id}" placeholder="Beskriv skillnaden i moment eller tillfälle, eller välj bort dubbletten.">${escapeHtml(draft?.resolution || "")}</textarea></label>` : ''}<details><summary>Instruktion och källor</summary><p>${escapeHtml(r.instructions)}</p>${r.source_urls.map(u=>`<a class="source-link" href="${escapeHtml(u)}" target="_blank" rel="noopener">${escapeHtml(u)}</a>`).join('')}</details><button class="text-button" data-edit-rule="${r.id}">Redigera</button></span></div>`;
  }).join('')}${comparison.removed.map(r=>`<p>Tas bort: ${escapeHtml(r.title)} · ${escapeHtml(r.scope)}. Saknas i det nya förslaget; historiken bevaras.</p>`).join('')}<p class="muted">Endast valda råd behålls i den nya planen. Bortvalda gamla tillfällen arkiveras med orsak.</p><div class="form-actions"><button class="text-button" data-reject="${plan.proposal_id}">Avvisa</button><button class="button" data-approve="${plan.proposal_id}">Godkänn valda</button></div></section>${planSources(plan)}`;
}

function monthName(month){return ["jan","feb","mar","apr","maj","jun","jul","aug","sep","okt","nov","dec"][month-1]}

async function research(itemId, button) {
  button.disabled=true; const original=button.textContent; button.textContent="Söker hos betrodda källor …";
  try { await api(`/api/items/${itemId}/research/`, {method:"POST", body:"{}"}); toast("Förslaget är redo att granskas"); await openItem(itemId); }
  catch(e){toast(e.message); button.disabled=false; button.textContent=original;}
}

async function approve(id) {
  const rules = $$(`.proposal[data-proposal="${id}"] input:checked`).map(el=>Number(el.value));
  const proposal = $(`.proposal[data-proposal="${id}"]`);
  const resolutions = Object.fromEntries([...proposal.querySelectorAll('[data-resolution]')].map(e=>[e.dataset.resolution,e.value]));
  await api(`/api/proposals/${id}/approve/`, {method:"POST", body:JSON.stringify({rule_ids:rules, comparison_token:proposal.dataset.token, resolutions})}); toast(`${rules.length} råd godkända`); $("#detail-dialog").close(); await load();
}

function editRule(button) {
  const rule = state.rules.get(Number(button.dataset.editRule));
  $("#detail-dialog").close();
  const fields = [['title','Rubrik'], ['scope','Berörd del eller undergrupp'], ['relevance_reason','Varför behövs detta på växten?'], ['need_condition','Behovsvillkor (endast Vid behov)']];
  const identity = `<label>Hur ska arbetet kopplas?<select name="identity_mode"><option value="existing">Återanvänd valt arbete exakt</option><option value="refine">Förtydliga undergruppen för valt arbete</option><option value="merge">Slå ihop förslagets tidigare identitet med valt arbete</option><option value="new">Skapa ett nytt arbetsmoment</option></select></label><label>Arbete<select name="work_id">${rule.works.map(w=>`<option value="${w.id}" data-scope="${escapeHtml(w.scope)}">${escapeHtml(w.title)} · ${escapeHtml(w.scope)}</option>`).join('')}</select></label><p class="muted" data-identity-help></p>`;
  openForm("Redigera förslag", identity + fields.map(([key,label])=>`<label>${label}<input name="${key}" value="${escapeHtml(rule[key])}"></label>`).join('') + `<label>Rådstyp<select name="advice_kind"><option value="planned">Planerat arbete</option><option value="on_demand">Vid behov</option><option value="general">Allmänt råd</option></select></label><label>Arbetskategori<select name="category">${state.data.work_categories.map(c=>`<option>${escapeHtml(c)}</option>`).join('')}</select></label><label>Instruktion<textarea name="instructions">${escapeHtml(rule.instructions)}</textarea></label><label>Återkomst<select name="cadence"><option value="seasonal">En gång per säsong</option><option value="monthly">Varje månad</option><option value="one_off">En gång på angivna datum</option></select></label><div class="field-grid"><label>Från månad<input name="start_month" type="number" min="1" max="12" value="${rule.start_month}"></label><label>Till månad<input name="end_month" type="number" min="1" max="12" value="${rule.end_month}"></label><label>Engångsarbete från<input name="one_off_date" type="date" value="${rule.one_off_date}"></label><label>Engångsarbete till<input name="one_off_end" type="date" value="${rule.one_off_end}"></label></div>`, "Spara ändring", async fd=>{
    const data = Object.fromEntries(fd); data.start_month=Number(data.start_month);data.end_month=Number(data.end_month);data.conditional=data.advice_kind==='on_demand';
    await api(`/api/rules/${rule.id}/`,{method:'PATCH',body:JSON.stringify(data)});
    toast('Förslaget är uppdaterat'); await openReview();
  });
  const form = $('#dynamic-form');
  form.elements.work_id.value=String(rule.identity_change_kind==='refine' ? rule.identity_source_id : rule.work_id);
  form.elements.identity_mode.value=rule.identity_change_kind || 'existing';
  const syncIdentity = () => {
    const mode=form.elements.identity_mode.value, option=form.elements.work_id.selectedOptions[0], scope=form.elements.scope;
    scope.readOnly=mode==='existing' || mode==='merge';
    if ((mode==='existing' || mode==='merge') && option) scope.value=option.dataset.scope;
    form.querySelector('[data-identity-help]').textContent={existing:'Historik och bortval för valt arbete används. Undergruppen följer identiteten.',refine:'Ange en tydligare undergrupp. Kopplingen aktiveras först när förslaget godkänns.',merge:'Använd endast när detta uttryckligen är samma tidigare arbete.',new:'Detta skapar ett fristående arbetsmoment utan tidigare historik.'}[mode];
  };
  form.elements.identity_mode.addEventListener('change',syncIdentity);form.elements.work_id.addEventListener('change',syncIdentity);syncIdentity();
  for (const key of ['category','cadence','advice_kind']) form.elements[key].value = rule[key] === 'review' ? 'planned' : rule[key];
}

async function saveSettings(event) {
  event.preventDefault(); const data=Object.fromEntries(new FormData(event.target)); await api("/api/settings/",{method:"PATCH",body:JSON.stringify(data)}); toast("Trädgårdsprofilen är sparad"); state.settingsDirty=false; await load();
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
  try {
  const month=event.target.closest('[data-month]'); if(month){state.selectedMonth=Number(month.dataset.month);await loadMonth();return;}
  if(event.target.closest('[data-review]')) {await openReview();return;}
  const need=event.target.closest('[data-need]'); if(need){need.disabled=true;try{const result=await api(`/api/works/${need.dataset.need}/need/`,{method:'POST',body:'{}'});toast(result.created?'Arbetet är tillagt':'Arbetet är redan öppet');await load();}finally{need.disabled=false;}return;}
  const exclusion=event.target.closest('[data-exclude], [data-restore]'); if(exclusion){const id=exclusion.dataset.exclude || exclusion.dataset.restore; await api(`/api/works/${id}/`,{method:'PATCH',body:JSON.stringify({excluded:!!exclusion.dataset.exclude})});$('#detail-dialog').close();await load();toast(exclusion.dataset.exclude?'Arbetet är bortvalt tills du återställer det under växten.':'Bortvalet är återställt');return;}

  const taskView=event.target.closest("[data-task-view]"); if(taskView){state.taskView=taskView.dataset.taskView;window.localStorage.setItem("garden-task-view",state.taskView);renderTasks(state.data.tasks);return;}
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
  const renameArea=event.target.closest("[data-rename-area]"); if(renameArea){const name=window.prompt("Nytt namn på området",renameArea.dataset.areaName);if(name?.trim()){await api(`/api/areas/${renameArea.dataset.renameArea}/`,{method:"PATCH",body:JSON.stringify({name:name.trim()})});toast("Området har bytt namn");await load();}return;}
  const deleteArea=event.target.closest("[data-delete-area]"); if(deleteArea){if(window.confirm(`Ta bort området ${deleteArea.dataset.areaName}? Växterna blir inte placerade men deras platsdetaljer sparas.`)){await api(`/api/areas/${deleteArea.dataset.deleteArea}/`,{method:"DELETE"});toast("Området togs bort");await load();}return;}
  if(event.target.closest("[data-close]")) $("#form-dialog").close();
  if(event.target.closest("[data-close-detail]")) $("#detail-dialog").close();
  } catch(error) {toast(error.message);}
});

document.addEventListener("change", async event => {
  const select=event.target.closest("[data-item-area]");
  if (!select) return;
  select.disabled=true;
  try {
    await api(`/api/items/${select.dataset.itemArea}/`, {method:"PATCH", body:JSON.stringify({area_id:select.value || null})});
    toast("Placeringen är sparad");
    await load();
  } catch(error) {
    toast(error.message); select.disabled=false;
  }
});

document.addEventListener('input', event=>{
  const proposal=event.target.closest('.proposal'); if(!proposal)return;
  proposal.querySelectorAll('.rule-choice').forEach(row=>{const box=row.querySelector('input[type=checkbox]');state.reviewDrafts.set(Number(box.value),{checked:box.checked,resolution:row.querySelector('textarea')?.value || ''});});
});
$("#settings-form").addEventListener('input',()=>{state.settingsDirty=true;});
$("#selected-year").addEventListener('change',async event=>{state.selectedYear=Number(event.target.value);try{await loadMonth();}catch(e){toast(e.message);}});
$("#search-trigger").onclick=()=>{$("#search-dialog").showModal();setTimeout(()=>$("#global-search").focus(),50)};
$("#global-search").addEventListener("input",event=>{clearTimeout(state.searchTimer);state.searchTimer=setTimeout(()=>runSearch(event.target.value),180)});
$("#new-item").onclick=()=>newItem(); $("#new-task").onclick=newTask; $("#settings-form").onsubmit=saveSettings;
$("#new-area-form").onsubmit=async event=>{event.preventDefault();const input=event.target.elements.name;const name=input.value.trim();if(!name)return;try{await api("/api/areas/",{method:"POST",body:JSON.stringify({name})});input.value="";toast("Området är tillagt");await load();}catch(error){toast(error.message)}};
$("#save-notifications").onclick=()=>saveNotifications().catch(e=>toast(e.message));
$("#test-notification").onclick=()=>api("/api/push/test/",{method:"POST",body:"{}"}).then(r=>toast(r.sent?"Testnotisen skickades":"Ingen aktiv enhet hittades")).catch(e=>toast(e.message));
document.addEventListener("keydown",event=>{if((event.metaKey||event.ctrlKey)&&event.key.toLowerCase()==="k"){event.preventDefault();$("#search-trigger").click()}if(event.key==="Escape")$$('dialog[open]').forEach(d=>d.close())});
if("serviceWorker" in navigator) window.addEventListener("load",()=>navigator.serviceWorker.register("/sw.js"));
load();
