function readPreference(key, fallback) {
  try { return JSON.parse(window.localStorage.getItem(key)) ?? fallback; }
  catch { return fallback; }
}

function savePreference(key, value) {
  try { window.localStorage.setItem(key, JSON.stringify(value)); return true; }
  catch { return false; }
}

function savedGrouping() {
  try { return window.localStorage.getItem("garden-task-view"); }
  catch { return "work"; }
}

const savedTaskView = savedGrouping();
const viewNames = {month: "Överblick", plants: "Min trädgård", year: "Årshjulet", shopping: "Inköpslista", settings: "Inställningar"};
const storedShopping = readPreference("garden-shopping-v1", []);
const state = {
  data: null, view: Object.hasOwn(viewNames, location.hash.slice(1)) ? location.hash.slice(1) : "month",
  taskView: ["work", "area"].includes(savedTaskView) ? savedTaskView : "work", taskPeriod: "current",
  searchTimer: null, searchRequest: 0, toastTimer: null, openItem: null,
  selectedMonth: new Date().getMonth() + 1, selectedYear: new Date().getFullYear(),
  rules: new Map(), settingsDirty: false, reviewDrafts: new Map(), loaded: false, scroll: {},
  plantFilter: "", plantQuery: "", soilShape: "bed",
  shopping: Array.isArray(storedShopping) ? storedShopping.filter(row => row && typeof row.id === "string" && typeof row.name === "string").map(row => ({id: row.id, name: row.name.slice(0, 180), detail: typeof row.detail === "string" ? row.detail.slice(0, 240) : "", done: row.done === true})) : [],
};
const $ = selector => document.querySelector(selector);
const $$ = selector => [...document.querySelectorAll(selector)];
const icon = (name, small = false) => `<svg class="icon${small ? ' small' : ''}" aria-hidden="true"><use href="#i-${name}"/></svg>`;
const capitalize = value => value.charAt(0).toUpperCase() + value.slice(1);

function plantArt(item) {
  const kind = ["apple", "plum", "berry", "rose", "hedge", "tomato"].includes(item.icon) ? item.icon : "leaf";
  return `<span class="plant-art ${kind}"><svg class="botanical" aria-hidden="true"><use href="#plant-${kind}"/></svg><span class="plant-tag">${escapeHtml(item.category || "Växt")}</span></span>`;
}

function emptyState(title, copy, action = "", symbol = "sprout") {
  return `<div class="empty-inline">${icon(symbol)}<h3>${title}</h3><p>${copy}</p>${action}</div>`;
}

function seasonFor(month) {
  if ([12, 1, 2].includes(month)) return {name: "Vinter", icon: "snow"};
  if (month <= 5) return {name: "Vår", icon: "sprout"};
  if (month <= 8) return {name: "Sommar", icon: "sun"};
  return {name: "Höst", icon: "leaf"};
}

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

function showDialog(dialog) {
  dialog.showModal();
  const message = $("#toast");
  if (message.classList.contains("show")) dialog.append(message);
}

function toast(message, undo = null) {
  const el = $("#toast");
  clearTimeout(state.toastTimer);
  ($$("dialog[open]").at(-1) || document.body).append(el);
  el.textContent = message;
  if (undo) {
    const button = document.createElement("button");
    button.className = "text-button";
    button.textContent = "Ångra";
    button.onclick = async () => { button.disabled = true; try { await undo(); } catch (error) { toast(error.message); } };
    el.append(button);
  }
  el.classList.add("show");
  if (!undo) state.toastTimer = window.setTimeout(() => el.classList.remove("show"), 4200);
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>'"]/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[char]));
}

function setView(view, updateHistory = true) {
  if (!Object.hasOwn(viewNames, view)) view = "month";
  state.scroll[state.view] = window.scrollY;
  state.view = view;
  $$(".view").forEach(el => el.classList.toggle("hidden", el.id !== `view-${view}`));
  $$(".nav-link").forEach(el => {
    const active = el.dataset.view === view;
    el.classList.toggle("active", active);
    if (active) el.setAttribute("aria-current", "page"); else el.removeAttribute("aria-current");
  });
  $("#view-title").textContent = viewNames[view];
  document.title = `${viewNames[view]} · Trädgårdsrytmen`;
  if (updateHistory && location.hash !== `#${view}`) history.pushState(null, "", `#${view}`);
  window.scrollTo({top: state.scroll[view] || 0, behavior: "instant"});
  if (view === "year") loadMonth().catch(e=>toast(e.message));
  if (view === "shopping") { renderShopping(); calculateSoil(); }
}

function formatShortDate(value) {
  return new Date(`${value}T12:00:00`).toLocaleDateString("sv-SE", {day:"numeric", month:"short", ...(value.slice(0,4) !== state.data?.today.slice(0,4) ? {year:"numeric"} : {})});
}

function taskWindow(task) {
  return task.start === task.end ? formatShortDate(task.start) : `${formatShortDate(task.start)}–${formatShortDate(task.end)}`;
}

function taskRow(task) {
  const place = [task.area?.name || "Inte placerat", task.location_detail].filter(Boolean).join(" · ");
  const overdue = task.status === "pending" && task.end < state.data.today;
  return `<div class="task-row" data-task="${task.id}">
    ${task.status === "pending" ? `<button class="task-check" data-status="completed" aria-label="Markera ${escapeHtml(task.title)} som klar">${icon('check')}</button>` : `<span class="task-state">${escapeHtml(statusName(task.status))}</span>`}
    <button class="task-copy task-open" data-open-task="${task.id}" aria-label="Visa detaljer för ${escapeHtml(task.title)}"><span class="task-row-top"><strong class="task-title">${escapeHtml(task.title)}</strong><span class="${overdue ? 'overdue' : ''}">${overdue ? 'Tidigare · ' : ''}${escapeHtml(taskWindow(task))}</span></span><span class="task-plant-name">${escapeHtml(task.item.name)} <span class="task-place">· ${escapeHtml(place)}</span></span>${task.relevance_reason ? `<span class="task-instruction">${escapeHtml(task.relevance_reason)}</span>` : ''}</button>
    <button class="task-plant-link" data-open-item="${task.item.id}" aria-label="Visa växten ${escapeHtml(task.item.name)}">${icon('leaf')}</button>
  </div>`;
}

function renderTasks(groups) {
  $$("[data-task-view]").forEach(button => {button.classList.toggle("active", button.dataset.taskView === state.taskView);button.setAttribute("aria-pressed", String(button.dataset.taskView === state.taskView));});
  $$("[data-task-period]").forEach(button => {button.classList.toggle("active", button.dataset.taskPeriod === state.taskPeriod);button.setAttribute("aria-pressed", String(button.dataset.taskPeriod === state.taskPeriod));});
  const advice = state.taskPeriod === "advice";
  $("#on-demand").classList.toggle("hidden", !advice);
  $("#task-groups").classList.toggle("hidden", advice);
  $("#task-toolbar").classList.toggle("hidden", advice);
  const tasks = state.taskPeriod === "upcoming" ? groups.later : [...groups.overdue, ...groups.due];
  $("#task-summary").textContent = `${tasks.length} ${tasks.length === 1 ? 'uppgift' : 'uppgifter'} · ${state.taskPeriod === 'upcoming' ? 'framåt i tiden' : 'i din trädgård'}`;
  if (!tasks.length) {
    let title = "Inga planerade uppgifter just nu.", copy = "Listan visar din plan, inte en bedömning av alla växters skötselbehov.", action = '<button class="button secondary" data-view="plants">Besök din trädgård</button>';
    if (!state.data.items.length) {
      title = "Allt börjar med en växt."; copy = "Lägg till din första växt, så kan vi börja bygga din trädgårdsrytm tillsammans.";
      action = `<button class="button" data-new-item>${icon('plus', true)}Lägg till din första växt</button>`;
    } else if (state.taskPeriod === "upcoming") {
      title = "Luft i kalendern."; copy = "Här samlas dina kommande uppgifter när det finns en plan. Årshjulet visar också det du redan har gjort.";
      action = '<button class="button secondary" data-view="year">Utforska årshjulet</button>';
    }
    $("#task-groups").innerHTML = emptyState(title, copy, action);
    return;
  }
  const categoryIcons = {"Vattna":"water", "Beskära och binda upp":"scissors", "Kontrollera":"search", "Gödsla":"sprout", "Jord och ogräs":"bed", "Skörda":"bag", "Övrigt":"leaf"};
  const key = t => state.taskView === "work" ? t.category : t.area?.name || "Inte placerat";
  const sorted = [...tasks].sort((a,b) => a.end.localeCompare(b.end) || a.title.localeCompare(b.title, "sv"));
  const keys = [...new Set(sorted.map(key))];
  $("#task-groups").innerHTML = keys.map(k => {
    const rows = sorted.filter(t => key(t) === k);
    return `<section class="work-group"><div class="round-heading">${icon(state.taskView === 'area' ? 'pin' : categoryIcons[k] || 'leaf')}<h4>${escapeHtml(k)}</h4><span>${rows.length} ${rows.length === 1 ? 'uppgift' : 'uppgifter'}</span></div>${rows.map(taskRow).join('')}</section>`;
  }).join('');
}

function statusName(status) {return {pending:"Planerat", completed:"Utfört", skipped:"Överhoppat", archived:"Arkiverat"}[status] || status;}
function adviceMarkup(r) {
  return `<article class="advice-row"><strong>${escapeHtml(r.title)}</strong><p>${escapeHtml(r.item.name)} · ${escapeHtml(r.scope)}</p><p>${escapeHtml(r.need_condition || r.relevance_reason)}</p><details><summary>Instruktion och källor</summary><p>${escapeHtml(r.instructions)}</p>${r.source_urls.map(u=>`<a class="source-link" href="${escapeHtml(u)}" target="_blank" rel="noopener">${escapeHtml(u)}</a>`).join('')}</details><div class="form-actions">${r.advice_kind === 'on_demand' ? `<button class="button secondary" data-need="${r.work_id}">Behövs nu</button>` : ''}<button class="text-button" data-exclude="${r.work_id}">Inte relevant här</button></div></article>`;
}

async function loadMonth() {
  const year = state.selectedYear, month = state.selectedMonth;
  $("#month-detail").setAttribute("aria-busy", "true");
  let data;
  try { data = await api(`/api/month/?year=${year}&month=${month}`); }
  catch (error) {
    if (year === state.selectedYear && month === state.selectedMonth) {
      $("#month-detail").removeAttribute("aria-busy");
      $("#month-detail").innerHTML = emptyState("Kalendern kunde inte hämtas.", escapeHtml(error.message), '<button class="button secondary" data-retry-month>Försök igen</button>', 'calendar');
    }
    return;
  }
  if (year !== state.selectedYear || month !== state.selectedMonth) return;
  $("#month-detail").removeAttribute("aria-busy");
  if (document.activeElement !== $("#selected-year")) $("#selected-year").value = year;
  $("#selected-month").value = month;
  $$("[data-month]").forEach(b=>b.setAttribute('aria-pressed',String(Number(b.dataset.month)===month)));
  data.counts.forEach(row => {
    const button = $(`[data-month="${row.month}"]`);
    if (button) {
      button.querySelector(".month-count").textContent = row.open ? `${row.open} ${row.open === 1 ? "planerad uppgift" : "planerade uppgifter"}` : "Inget planerat ännu";
      button.classList.toggle("current", year === Number(state.data.today.slice(0,4)) && row.month === Number(state.data.today.slice(5,7)));
    }
  });
  const name = state.data.year.find(row => row.month === month).name;
  $("#month-detail").innerHTML = `<div class="month-detail-heading"><div><p class="eyebrow">DIN PLAN & HISTORIK</p><h3>${escapeHtml(name)} ${year}</h3></div>${icon(seasonFor(month).icon)}</div><h4>Planerade uppgifter</h4>${data.planned.length ? data.planned.map(taskRow).join('') : '<p class="muted">Inga planerade uppgifter den här månaden.</p>'}<h4>Det du har gjort</h4>${data.history.length ? data.history.map(taskRow).join('') : '<p class="muted">När du avslutar en uppgift hittar du den här.</p>'}`;
}

async function openReview() {
  state.detail = null;
  const dialog = $("#detail-dialog");
  $("#detail-content").innerHTML = '<p>Hämtar granskningskön …</p>';
  showDialog(dialog);
  try {
    const {proposals} = await api('/api/proposals/');
    $("#detail-content").innerHTML = `<h2>Granska skötsel</h2>${proposals.length ? proposals.map(p=>`<h3><button class="text-button" data-open-item="${p.item.id}">${escapeHtml(p.item.name)}</button></h3>${proposalMarkup(p.plan)}`).join('') : emptyState('Inget att ta ställning till just nu.', 'När du hämtar nya skötselråd för en växt kan du granska dem här.', '', 'check')}`;
  } catch (error) {
    $("#detail-content").innerHTML = `<h2>Råden kunde inte hämtas</h2><p>${escapeHtml(error.message)}</p><button class="button secondary" data-review>Försök igen</button>`;
  }
}

function plantRow(item) {
  const meta = [item.cultivar || item.category || "Din växt", item.quantity > 1 ? `${item.quantity} st` : ""].filter(Boolean).join(" · ");
  return `<button class="plant-row" data-open-item="${item.id}" aria-label="Öppna ${escapeHtml(item.name)}">${plantArt(item)}<span class="plant-card-copy"><strong>${escapeHtml(item.name)}</strong><span class="plant-meta">${escapeHtml(meta)}</span><span class="plant-card-location">${icon('pin', true)}<span>${escapeHtml(item.area?.name || item.location_detail || 'Välj en plats')}</span>${icon('arrow-up-right', true)}</span></span></button>`;
}

function renderPlants() {
  const restoreFilter = preserveFocus($("#plant-filters"), $("#plant-search"));
  const restorePlant = preserveFocus($("#plant-list"), $("#plant-search"));
  const items = state.data.items;
  const categories = [...new Set(items.map(item => item.category).filter(Boolean))];
  if (!categories.includes(state.plantFilter)) state.plantFilter = "";
  $("#plant-filters").innerHTML = ["", ...categories].map(category => `<button class="filter-chip ${state.plantFilter === category ? 'active' : ''}" data-plant-filter="${escapeHtml(category)}" aria-pressed="${state.plantFilter === category}">${escapeHtml(category || 'Alla växter')}<span>${category ? items.filter(item => item.category === category).length : items.length}</span></button>`).join('');
  const query = state.plantQuery.trim().toLocaleLowerCase("sv");
  const shown = items.filter(item => (!state.plantFilter || item.category === state.plantFilter) && [item.name, item.category, item.cultivar, item.area?.name, item.location_detail, ...(item.aliases || [])].filter(Boolean).join(' ').toLocaleLowerCase("sv").includes(query));
  $("#plant-result-count").textContent = `${shown.length} av ${items.length} växter visas.`;
  $("#plant-list").innerHTML = shown.length ? shown.map(plantRow).join('') : items.length ? emptyState("Ingen växt hittades.", "Prova ett annat namn, en sort eller ett område.", '<button class="button secondary" data-reset-plants>Visa alla växter</button>', 'search') : emptyState("Ett grönt rum att fylla.", "Ett äppelträd, en kruka eller en hel odlingsbädd. Lägg till det som växer hos dig.", '<button class="button" data-new-item>Lägg till din första växt</button>');
  restoreFilter(); restorePlant();
}

function renderCalendar(today) {
  const date = new Date(`${today}T12:00:00`), year = date.getFullYear(), month = date.getMonth();
  const offset = (new Date(year, month, 1).getDay() + 6) % 7;
  const days = new Date(year, month + 1, 0).getDate();
  $("#calendar-title").textContent = date.toLocaleDateString("sv-SE", {month: 'long', year: 'numeric'});
  $("#mini-calendar").setAttribute('aria-label', `Kalender för ${date.toLocaleDateString("sv-SE", {month:'long', year:'numeric'})}. I dag är det den ${date.getDate()}.`);
  $("#mini-calendar").innerHTML = ['M','T','O','T','F','L','S'].map(day => `<span class="calendar-weekday" aria-hidden="true">${day}</span>`).join('') + '<span></span>'.repeat(offset) + Array.from({length: days}, (_,i) => `<span class="calendar-day ${i+1 === date.getDate() ? 'today' : ''} ${(i+offset)%7 >= 5 ? 'weekend' : ''}" aria-hidden="true">${i+1}</span>`).join('');
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
  $("#garden-city").textContent = data.settings.city || "Din trädgård";
  $("#garden-exposure").textContent = [data.settings.cultivation_zone ? `Odlingszon ${data.settings.cultivation_zone}` : "", data.settings.exposure].filter(Boolean).join(' · ');
  $("#garden-exposure").title = $("#garden-exposure").textContent;
  $("#hero-date").textContent = new Date(data.today + "T12:00:00").toLocaleDateString("sv-SE", {weekday:"long", day:"numeric", month:"long"});
  $("#hero-month").textContent = capitalize(data.month_name);
  const season = seasonFor(Number(data.today.slice(5,7)));
  $("#hero-season").innerHTML = `${icon(season.icon, true)}<span>${season.name} i trädgården</span>`;
  const current = data.tasks.due.length + data.tasks.overdue.length;
  $("#stat-current").textContent = current;
  $("#stat-current").nextElementSibling.textContent = current === 1 ? "aktuell uppgift" : "aktuella uppgifter";
  $("#stat-plants").textContent = data.items.length;
  $("#stat-completed").textContent = data.completed;
  $("#stat-completed").nextElementSibling.textContent = data.completed === 1 ? "utförd denna månad" : "utförda denna månad";
  $("#count-current").textContent = current;
  $("#count-upcoming").textContent = data.tasks.later.length;
  $("#count-advice").textContent = data.advice.length;
  $("#nav-task-count").textContent = current;
  $("#nav-task-count").classList.toggle('hidden', !current);
  $("#need-list").innerHTML = data.advice.length ? data.advice.map(adviceMarkup).join("") : emptyState("Omtanke när den behövs.", "Här samlas granskade råd som du själv aktiverar när behovet uppstår.", '<button class="button secondary" data-view="plants">Se dina växters skötselråd</button>', 'water');
  $(".review-link").classList.toggle('hidden', !data.pending_proposals);
  $("#review-count").textContent = `${data.pending_proposals} förslag väntar på din granskning`;
  const next = [...data.tasks.overdue, ...data.tasks.due, ...data.tasks.later].sort((a,b) => a.end.localeCompare(b.end))[0];
  state.nextTask = next?.id;
  $("#hero-next").textContent = next ? `${next.title} · ${next.item.name} · ${taskWindow(next)}` : data.items.length ? "Skapa en egen uppgift eller öppna en växt för att börja planera skötseln." : "Lägg till din första växt och börja din plan.";
  $("#hero-action").innerHTML = `${next ? 'Visa nästa uppgift' : data.items.length ? 'Planera skötsel' : 'Lägg till en växt'}${icon('arrow-right')}`;
  $("#plan-coverage").classList.toggle("hidden", !data.items.length);
  const covered = data.items.filter(item => item.has_care_plan).length;
  $("#plan-coverage").textContent = `${covered} av ${data.items.length} växter har en granskad skötselplan. Planerna garanterar inte att alla behov är täckta.`;
  renderTasks(data.tasks);
  $("#year-grid").innerHTML = data.year.map(row => `<button class="year-month ${row.month === Number(data.today.slice(5,7)) && state.selectedYear === Number(data.today.slice(0,4)) ? "current" : ""}" data-month="${row.month}" aria-pressed="${row.month === state.selectedMonth}"><span class="year-month-top"><b>${String(row.month).padStart(2,'0')} / ${seasonFor(row.month).name.toUpperCase()}</b>${icon(seasonFor(row.month).icon)}</span><strong>${capitalize(row.name)}</strong><span class="month-count">${row.open ? `${row.open} planerade uppgifter` : 'Inget planerat ännu'}</span></button>`).join("");
  $("#selected-month").innerHTML = data.year.map(row => `<option value="${row.month}">${capitalize(row.name)}</option>`).join("");
  $("#selected-month").value = state.selectedMonth;
  renderPlants();
  renderCalendar(data.today);
  $("#plant-preview").innerHTML = data.items.length ? data.items.slice(0,4).map(plantRow).join('') : emptyState("Här kommer det att grönska.", "Dina växter samlas här när du har lagt till dem.", '<button class="button secondary" data-new-item>Lägg till en växt</button>');
  if (document.activeElement !== $("#selected-year")) $("#selected-year").value = state.selectedYear;
  const suggestions = ["Päron","Vinbär","Björnbär","Krusbär","Valnöt","Kinesisk toon","Grönsaker"];
  $("#quick-adds").innerHTML = suggestions.map(name => `<button class="quick-chip" data-quick-add="${name}">+ ${name}</button>`).join("");
  if (!state.settingsDirty) for (const field of ["garden_name","city","cultivation_zone","exposure"]) $("#settings-form").elements[field].value = data.settings[field] || "";
  $("#proposal-count").textContent = data.pending_proposals;
  renderAreas(data);
}

async function load() {
  const scroll = window.scrollY;
  try {
    render(await api("/api/bootstrap/"));
    $("#loading").classList.add("hidden");
    if (!state.loaded) {setView(state.view); state.loaded = true;}
    else if (state.view === 'year') await loadMonth();
    $("#error-state").classList.add("hidden");
    window.scrollTo({top:scroll});
  } catch (error) {
    $("#loading").classList.add("hidden"); $("#error-state").classList.remove("hidden"); $("#error-message").textContent = error.message;
  }
}

async function refreshOpenDetail() {
  if ($("#detail-dialog").open && state.detail) {
    const detail = {...state.detail}, scroll = $("#detail-dialog").scrollTop;
    const expanded = $$("#detail-content details").map(el => el.open);
    if (detail.kind === "item") await openItem(detail.id); else await openTask(detail.id);
    $$("#detail-content details").forEach((el, index) => {el.open = expanded[index] || false;});
    $("#detail-dialog").scrollTop = scroll;
  }
}

async function updateTask(id, status) {
  const focused = document.activeElement;
  await api(`/api/tasks/${id}/`, {method:"PATCH", body:JSON.stringify({status})});
  if (status !== "pending" && state.data) {
    for (const key of ["overdue", "due", "later"]) state.data.tasks[key] = state.data.tasks[key].filter(task => task.id !== id);
    renderTasks(state.data.tasks);
  }
  await load();
  await refreshOpenDetail();
  toast(status === "completed" ? "Uppgiften är klar" : status === "skipped" ? "Hoppad över för den här gången" : "Uppgiften är öppen igen", status !== "pending" ? () => updateTask(id, "pending") : null);
  if (!focused.isConnected) {
    const scope = $("#detail-dialog").open ? $("#detail-content") : $(".view:not(.hidden)");
    ($("#toast button") || scope.querySelector(`[data-task="${id}"] button`) || $("#detail-dialog[open] [data-close-detail]") || $("#hero-action")).focus({preventScroll:true});
  }
}

function formatTaskDate(value) {
  return new Date(`${value}T12:00:00`).toLocaleDateString("sv-SE", {day:"numeric", month:"long", ...(value.slice(0,4) !== state.data?.today.slice(0,4) ? {year:"numeric"} : {})});
}

async function openTask(id) {
  state.detail = {kind: "task", id};
  const dialog = $("#detail-dialog"), content = $("#detail-content");
  content.innerHTML = `<div class="loading-state"><span class="spinner"></span></div>`;
  showDialog(dialog);
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
  $("#form-content").innerHTML = `<h2 id="form-title">${title}</h2><div class="form-stack">${body}<div class="form-actions"><button class="button secondary" type="button" data-close>Avbryt</button><button class="button" type="submit">${submitLabel}</button></div></div>`;
  form.onsubmit = async event => {
    event.preventDefault();
    const button = form.querySelector("[type=submit]");
    form.querySelector('.form-error')?.remove();
    button.disabled = true; button.textContent = "Sparar …";
    try { await onSubmit(new FormData(form)); dialog.close(); await load(); }
    catch (error) {
      const message = document.createElement('p');
      message.tabIndex = -1; message.className = 'form-error'; message.setAttribute('role', 'alert'); message.textContent = error.message;
      form.querySelector('.form-actions').before(message);
      message.focus();
      button.disabled = false; button.textContent = submitLabel;
    }
  };
  showDialog(dialog);
}

function newItem(prefill = "") {
  openForm("Lägg till i trädgården", `<p class="muted">Spara växtens detaljer här. Du kan sedan välja att hämta skötselråd från OpenAI i ett separat steg.</p><label>Namn<input name="name" required value="${escapeHtml(prefill)}"></label><label>Typ<select name="kind"><option value="individual">Enskild växt</option><option value="group">Grupp</option><option value="bed">Odlingsbädd</option></select></label><label>Växttyp<input name="category" placeholder="Fruktträd, bär, häck …"></label><label>Sort<input name="cultivar"></label><label>Antal<input name="quantity" type="number" min="1" value="1"></label><label>Område<select name="area_id">${areaOptions()}</select></label><label>Platsdetalj<input name="location_detail" placeholder="Till exempel vid lilla altanrabatten"></label><label>Egna anteckningar<textarea name="notes"></textarea></label>`, "Spara växt", async fd => {
    const result = await api("/api/items/", {method:"POST", body:JSON.stringify(Object.fromEntries(fd))}); await openItem(result.item.id); toast("Växten är sparad");
  });
}

function newTask() {
  if (!state.data.items.length) {
    toast("Lägg till en växt först, så kan du ge den en uppgift.");
    newItem();
    return;
  }
  const items = state.data.items.map(i => `<option value="${i.id}">${escapeHtml(i.name)}</option>`).join("");
  const categories = state.data.work_categories.map(category => `<option value="${escapeHtml(category)}">${escapeHtml(category)}</option>`).join("");
  openForm("Egen uppgift", `<label>Uppgift<input name="title" required></label><label>Arbetskategori<select name="category">${categories}</select></label><label>Växt eller odling<select name="item_id">${items}</select></label><label>Från<input name="window_start" type="date" required value="${state.data.today}"></label><label>Till<input name="window_end" type="date" value="${state.data.today}"></label><label>Instruktion<textarea name="instructions"></textarea></label>`, "Skapa uppgift", async fd => { await api("/api/tasks/", {method:"POST", body:JSON.stringify(Object.fromEntries(fd))}); toast("Uppgiften är tillagd"); });
}

async function openItem(id) {
  state.detail = {kind: "item", id};
  const dialog = $("#detail-dialog"), content = $("#detail-content");
  content.innerHTML = `<div class="loading-state"><span class="spinner"></span></div>`; showDialog(dialog);
  try {
    const data = await api(`/api/items/${id}/`), item = data.item, proposal = data.proposals?.[0], plan = proposal || item.plan;
    state.openItem = item;
    const kindName = item.kind === "bed" ? "Odlingsbädd" : item.kind === "group" ? "Grupp" : "Enskild växt";
    content.innerHTML = `<div class="detail-heading"><div><p class="eyebrow">${escapeHtml(kindName)}</p><h2>${escapeHtml(item.name)}</h2></div><button class="button secondary" data-edit-item="${item.id}">Redigera växt</button></div>
      <div class="detail-botanical">${plantArt(item)}</div>
      <dl class="plant-facts"><div><dt>Sort</dt><dd>${escapeHtml(item.cultivar || "Ej angiven")}</dd></div><div><dt>Antal</dt><dd>${item.quantity}</dd></div><div><dt>Växttyp</dt><dd>${escapeHtml(item.category || "Ej angiven")}</dd></div><div><dt>Område</dt><dd>${escapeHtml(item.area?.name || "Inte placerat")}</dd></div><div><dt>Platsdetalj</dt><dd>${escapeHtml(item.location_detail || "Ej angiven")}</dd></div>${item.age_stage?`<div><dt>Ålder/stadium</dt><dd>${escapeHtml(item.age_stage)}</dd></div>`:""}</dl>
      ${item.notes?`<p>${escapeHtml(item.notes)}</p>`:""}
      <section class="detail-section"><h3>Nästa uppgifter</h3>${item.next_tasks?.length?item.next_tasks.map(taskRow).join(""):'<p class="muted">Inga aktiva uppgifter ännu.</p>'}</section>
      <section class="detail-section"><h3>Skötselråd</h3>${plan?`<p>${escapeHtml(plan.summary)}</p>${plan.warnings?.map(w=>`<p>⚠ ${escapeHtml(w)}</p>`).join("")||""}`:'<p class="muted">Hämta ett källbelagt förslag och granska det innan något läggs i årshjulet.</p>'}<p class="research-disclosure">När du hämtar råd skickas växtinformation, egna anteckningar, trädgårdens platsprofil och skötselhistorik till OpenAI. Därefter granskar du råden innan de läggs i planen.</p><button class="button secondary" data-research="${item.id}">${plan?"Uppdatera skötselråd":"Hämta skötselråd"}</button></section>
      <section class="detail-section"><h3>Vid behov och allmänna råd</h3>${item.advice?.map(adviceMarkup).join('') || '<p>Inga råd ännu.</p>'}</section>
      <details class="detail-section"><summary>Historik (${item.history?.length || 0})</summary>${item.history?.map(taskRow).join('') || '<p>Ingen historik ännu.</p>'}</details>
      <details class="detail-section"><summary>Bortval (${item.excluded?.length || 0})</summary>${item.excluded?.map(w=>`<p>${escapeHtml(w.title)} · ${escapeHtml(w.scope)} <button class="text-button" data-restore="${w.id}">Återställ</button></p>`).join('') || '<p>Inga beständiga bortval.</p>'}</details>
      ${proposal?proposalMarkup(proposal):planSources(plan)}`;
  } catch(e) { content.innerHTML = `<h2>Kunde inte öppna växten</h2><p>${escapeHtml(e.message)}</p>`; }
}

function editItem(item) {
  $("#detail-dialog").close();
  openForm("Redigera växt", `<label>Namn<input name="name" required value="${escapeHtml(item.name)}"></label><label>Sort<input name="cultivar" value="${escapeHtml(item.cultivar)}" placeholder="Till exempel Glen Ample"></label><div id="reanalyze-choice" class="reanalyze-choice hidden"><p><strong>Sorten eller egna anteckningar kan påverka skötselråden.</strong></p><label class="check-row"><input type="checkbox" name="refresh_research"><span>Skicka växtinformation, anteckningar, platsprofil och skötselhistorik till OpenAI för nya råd efter sparandet</span></label><small>Anteckningar behandlas som observationer. Det äldre ogranskade förslaget ersätts; godkända uppgifter och historik lämnas kvar.</small></div><label>Typ<select name="kind"><option value="individual">Enskild växt</option><option value="group">Grupp</option><option value="bed">Odlingsbädd</option></select></label><label>Växttyp<input name="category" value="${escapeHtml(item.category)}"></label><label>Antal<input name="quantity" type="number" min="1" value="${item.quantity}"></label><label>Ålder eller stadium<input name="age_stage" value="${escapeHtml(item.age_stage)}"></label><label>Område<select name="area_id">${areaOptions(item.area_id)}</select></label><label>Platsdetalj<input name="location_detail" value="${escapeHtml(item.location_detail)}"></label><label>Egna anteckningar<textarea name="notes">${escapeHtml(item.notes)}</textarea></label>`, "Spara växt", async fd => {
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
  event.preventDefault();
  const button = event.target.querySelector('[type=submit]');
  button.disabled = true;
  try {
    const data = Object.fromEntries(new FormData(event.target));
    await api("/api/settings/", {method:"PATCH", body:JSON.stringify(data)});
    state.settingsDirty = false; await load(); toast("Trädgårdsprofilen är sparad");
  } catch (error) { toast(error.message); }
  finally { button.disabled = false; }
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
  const box = $("#search-results"), request = ++state.searchRequest;
  if (value.trim().length < 2) {box.innerHTML='<p class="muted">Skriv minst två tecken för att söka.</p>';return;}
  box.innerHTML = '<p class="muted">Letar i din trädgård …</p>';
  try {
    const {results} = await api(`/api/search/?q=${encodeURIComponent(value)}`);
    if (request !== state.searchRequest || value !== $("#global-search").value) return;
    box.innerHTML = results.length ? results.map(r=>`<button class="search-result" data-open-item="${r.type==='task'?'':r.id}" data-open-task="${r.type==='task'?r.id:''}"><strong>${escapeHtml(r.title)}</strong><span>${escapeHtml(r.subtitle)}</span></button>`).join("") : '<p class="muted">Inga träffar. Prova en växt, en sort eller ett skötselord.</p>';
  } catch (error) {
    if (request === state.searchRequest) box.innerHTML = `<p class="muted">${escapeHtml(error.message)} Försök söka igen.</p>`;
  }
}

function showTaskPeriod(period, scroll = false) {
  state.taskPeriod = period;
  renderTasks(state.data.tasks);
  if (scroll) {
    if (state.view !== 'month') setView('month');
    $('#care-plan').scrollIntoView({behavior: 'smooth', block: 'start'});
    $('#care-heading').setAttribute('tabindex', '-1');
    $('#care-heading').focus({preventScroll: true});
  }
}

function calculateSoil() {
  const form = $('#soil-form'), values = Object.fromEntries(new FormData(form));
  const valid = [...form.querySelectorAll('input:not(:disabled), select')].every(field => field.validity.valid);
  const length = Number(values.length), width = Number(values.width), diameter = Number(values.diameter), depth = Number(values.depth), bag = Number(values.bag_size);
  const volume = (state.soilShape === 'pot' ? Math.PI * (diameter / 2) ** 2 * depth : length * width * depth) / 1000;
  const button = form.querySelector('[type=submit]');
  if (!valid || !Number.isFinite(volume) || volume <= 0 || bag <= 0) {
    $('#soil-result').innerHTML = '<span>Fyll i positiva mått för att beräkna jordåtgången.</span>';
    button.disabled = true;
    return null;
  }
  button.disabled = false;
  const bags = Math.ceil(volume / bag);
  const liters = volume < .1 ? 'mindre än 0,1' : volume.toLocaleString('sv-SE', {maximumFractionDigits: 1});
  $('#soil-result').innerHTML = `<strong>${liters}<small>liter</small></strong><span>Det motsvarar ungefär<br><b>${bags.toLocaleString('sv-SE')} ${bags === 1 ? 'säck' : 'säckar'} à ${bag} liter</b></span>`;
  return {volume, liters, bags, bag};
}

function setSoilShape(shape) {
  state.soilShape = shape;
  $$('[data-soil-shape]').forEach(button => {button.classList.toggle('active', button.dataset.soilShape === shape);button.setAttribute('aria-pressed', String(button.dataset.soilShape === shape));});
  $$('[data-bed-dimension], [data-pot-dimension]').forEach(label => {
    const hidden = label.hasAttribute('data-bed-dimension') ? shape === 'pot' : shape === 'bed';
    label.classList.toggle('hidden', hidden);
    label.querySelector('input').disabled = hidden;
  });
  calculateSoil();
}

function preserveFocus(container, fallback) {
  const active = document.activeElement;
  if (!container.contains(active)) return () => {};
  const attrs = ['data-shopping-toggle', 'data-shopping-remove', 'data-plant-filter', 'data-open-item', 'data-open-task', 'data-item-area'];
  const attr = attrs.find(name => active.hasAttribute(name));
  const value = attr && active.getAttribute(attr);
  return () => {
    const match = attr && [...container.querySelectorAll(`[${attr}]`)].find(el => el.getAttribute(attr) === value);
    (match || fallback)?.focus({preventScroll: true});
  };
}

function renderShopping() {
  const restore = preserveFocus($('#shopping-list'), $('#shopping-name'));
  $('#shopping-count').textContent = state.shopping.filter(row => !row.done).length;
  $('#shopping-list').innerHTML = state.shopping.length ? state.shopping.map(row => `<div class="shopping-row ${row.done ? 'is-done' : ''}"><label><input type="checkbox" data-shopping-toggle="${escapeHtml(row.id)}" ${row.done ? 'checked' : ''}><span><strong>${escapeHtml(row.name)}</strong>${row.detail ? `<small>${escapeHtml(row.detail)}</small>` : ''}</span></label><button class="icon-button" data-shopping-remove="${escapeHtml(row.id)}" aria-label="Ta bort ${escapeHtml(row.name)}">${icon('close')}</button></div>`).join('') : emptyState('Redo för nästa gröna idé.', 'Lägg till det du behöver, eller låt jordberäkningen hjälpa dig med mängden.', '', 'bag');
  restore();
}

function changeShopping(update) {
  const previous = state.shopping;
  const next = update(previous);
  if (!savePreference('garden-shopping-v1', next)) {
    toast('Listan kunde inte sparas. Tillåt lagring i webbläsaren och försök igen.');
    renderShopping();
    return false;
  }
  state.shopping = next;
  renderShopping();
  return true;
}

function addShopping(name, detail = '') {
  const row = {id: crypto.randomUUID(), name, detail, done: false};
  const saved = changeShopping(rows => [...rows, row]);
  if (saved) toast('Tillagt i din inköpslista', () => {if (changeShopping(rows => rows.filter(item => item.id !== row.id))) toast('Tillägget är ångrat');});
  return saved;
}

document.addEventListener("click", async event => {
  try {
  if (event.target.closest('[data-new-item]')) { if (state.data) newItem(); return; }
  if (event.target.closest('[data-retry-month]')) {await loadMonth();return;}
  const period = event.target.closest('[data-task-period], [data-show-period]'); if (period) { showTaskPeriod(period.dataset.taskPeriod || period.dataset.showPeriod, period.hasAttribute('data-show-period')); return; }
  const filter = event.target.closest('[data-plant-filter]'); if (filter) {state.plantFilter = filter.dataset.plantFilter;renderPlants();return;}
  if (event.target.closest('[data-reset-plants]')) {state.plantQuery = '';state.plantFilter = '';$('#plant-search').value = '';renderPlants();return;}
  if (event.target.closest('[data-current-year]')) {state.selectedMonth = Number(state.data.today.slice(5,7));state.selectedYear = Number(state.data.today.slice(0,4));setView('year');return;}
  const yearStep = event.target.closest('[data-year-step]'); if (yearStep) {state.selectedYear = Math.min(9999, Math.max(1900, state.selectedYear + Number(yearStep.dataset.yearStep)));await loadMonth();return;}
  const shape = event.target.closest('[data-soil-shape]'); if (shape) {setSoilShape(shape.dataset.soilShape);return;}
  const remove = event.target.closest('[data-shopping-remove]'); if (remove) {
    const row = state.shopping.find(item => item.id === remove.dataset.shoppingRemove);
    if (row && changeShopping(rows => rows.filter(item => item.id !== row.id))) toast('Borttaget från inköpslistan', () => {if (changeShopping(rows => [...rows, row])) toast('Inköpet är tillbaka i listan');});
    return;
  }
  const month=event.target.closest('[data-month]'); if(month){state.selectedMonth=Number(month.dataset.month);await loadMonth();$('#month-detail').scrollIntoView({behavior:'smooth',block:'start'});return;}
  if(event.target.closest('[data-review]')) {await openReview();return;}
  const need=event.target.closest('[data-need]'); if(need){need.disabled=true;try{const result=await api(`/api/works/${need.dataset.need}/need/`,{method:'POST',body:'{}'});await load();await refreshOpenDetail();toast(result.created?'Arbetet är tillagt':'Arbetet är redan öppet');if(!need.isConnected) document.querySelector(`dialog[open] [data-need="${need.dataset.need}"]`)?.focus({preventScroll:true});}finally{need.disabled=false;}return;}
  const exclusion=event.target.closest('[data-exclude], [data-restore]'); if(exclusion){const id=exclusion.dataset.exclude || exclusion.dataset.restore; await api(`/api/works/${id}/`,{method:'PATCH',body:JSON.stringify({excluded:!!exclusion.dataset.exclude})});$('#detail-dialog').close();await load();toast(exclusion.dataset.exclude?'Arbetet är bortvalt tills du återställer det under växten.':'Bortvalet är återställt');return;}

  const taskView=event.target.closest("[data-task-view]"); if(taskView){state.taskView=taskView.dataset.taskView;try {window.localStorage.setItem("garden-task-view",state.taskView);} catch {} renderTasks(state.data.tasks);return;}
  const nav=event.target.closest("[data-view]"); if(nav){setView(nav.dataset.view);return;}
  const status=event.target.closest("[data-status]"); if(status){const taskRow=status.closest("[data-task]"); status.disabled=true;try {await updateTask(Number(taskRow.dataset.task),status.dataset.status);} finally {status.disabled=false;} return;}
  const skip=event.target.closest("[data-skip-task]"); if(skip){if(window.confirm("Hoppa över uppgiften den här gången? Du kan ångra direkt efteråt.")){ await updateTask(Number(skip.dataset.skipTask),"skipped"); } return;}
  const task=event.target.closest("[data-open-task]"); if(task?.dataset.openTask){$("#search-dialog").close();await openTask(Number(task.dataset.openTask));return;}
  const item=event.target.closest("[data-open-item]"); if(item?.dataset.openItem){$("#search-dialog").close(); if ($("#detail-dialog").open) $("#detail-dialog").close(); openItem(Number(item.dataset.openItem));return;}
  const quick=event.target.closest("[data-quick-add]"); if(quick){newItem(quick.dataset.quickAdd);return;}
  const researchButton=event.target.closest("[data-research]"); if(researchButton){research(researchButton.dataset.research,researchButton);return;}
  const editItemButton=event.target.closest("[data-edit-item]"); if(editItemButton && state.openItem){editItem(state.openItem);return;}
  const approveButton=event.target.closest("[data-approve]"); if(approveButton){approveButton.disabled=true;try {await approve(approveButton.dataset.approve);} finally {approveButton.disabled=false;}return;}
  const editButton=event.target.closest("[data-edit-rule]"); if(editButton){editRule(editButton);return;}
  const reject=event.target.closest("[data-reject]"); if(reject){await api(`/api/proposals/${reject.dataset.reject}/`,{method:"DELETE"});toast("Förslaget avvisades");$("#detail-dialog").close();await load();return;}
  const renameArea=event.target.closest("[data-rename-area]"); if(renameArea){const name=window.prompt("Nytt namn på området",renameArea.dataset.areaName);if(name?.trim()){await api(`/api/areas/${renameArea.dataset.renameArea}/`,{method:"PATCH",body:JSON.stringify({name:name.trim()})});toast("Området har bytt namn");await load();}return;}
  const deleteArea=event.target.closest("[data-delete-area]"); if(deleteArea){if(window.confirm(`Ta bort området ${deleteArea.dataset.areaName}? Växterna blir inte placerade men deras platsdetaljer sparas.`)){await api(`/api/areas/${deleteArea.dataset.deleteArea}/`,{method:"DELETE"});toast("Området togs bort");await load();}return;}
  if(event.target.closest("[data-close]")) $("#form-dialog").close();
  if(event.target.closest("[data-close-detail]")) $("#detail-dialog").close();
  } catch(error) {toast(error.message);}
});

document.addEventListener("change", async event => {
  const shopping = event.target.closest('[data-shopping-toggle]');
  if (shopping) {changeShopping(rows => rows.map(row => row.id === shopping.dataset.shoppingToggle ? {...row, done: shopping.checked} : row));return;}
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
$("#selected-month").addEventListener("change", async event => {state.selectedMonth = Number(event.target.value); await loadMonth();});
$("#settings-form").addEventListener('input',()=>{state.settingsDirty=true;});
$("#selected-year").addEventListener('change',async event=>{if(!event.target.validity.valid || !event.target.value){event.target.value=state.selectedYear;toast('Välj ett år mellan 1900 och 9999.');return;}state.selectedYear=Number(event.target.value);try{await loadMonth();}catch(e){toast(e.message);}});
$("#search-trigger").onclick=()=>{showDialog($("#search-dialog"));setTimeout(()=>$("#global-search").focus(),50)};
$("#global-search").addEventListener("input",event=>{clearTimeout(state.searchTimer);state.searchRequest++;state.searchTimer=setTimeout(()=>runSearch(event.target.value),180)});
$("#plant-search").addEventListener('input', event => {state.plantQuery = event.target.value;renderPlants();});
$("#hero-action").onclick = () => state.nextTask ? openTask(state.nextTask) : state.data.items.length ? newTask() : newItem();
$("#manage-areas").onclick = () => {$('#area-settings').open = true;$('#area-settings').scrollIntoView({behavior:'smooth', block:'start'});$('#new-area-form input').focus({preventScroll:true});};
$("#soil-form").addEventListener('input', calculateSoil);
$("#soil-form").onsubmit = event => {
  event.preventDefault();
  const result = calculateSoil();
  if (!result) return;
  const added = addShopping(state.soilShape === 'pot' ? 'Jord till kruka' : 'Jord till rabatt eller pallkrage', `${result.bags.toLocaleString('sv-SE')} ${result.bags === 1 ? 'säck' : 'säckar'} à ${result.bag} l · beräknat ${result.liters} liter`);
  if (added) {$('#shopping-name').focus(); $('#shopping-heading').scrollIntoView({block:'start', behavior:'smooth'});}
};
$("#shopping-name").addEventListener('input', event => event.target.setCustomValidity(''));
$("#shopping-form").onsubmit = event => {event.preventDefault();const field=event.target.elements.name;if(!field.value.trim()){field.setCustomValidity('Skriv vad du vill lägga till.');field.reportValidity();return;}if(addShopping(field.value.trim())) field.value='';field.focus();};
window.addEventListener('hashchange', () => {const view=location.hash.slice(1);if(state.loaded && view !== 'main' && view !== state.view) setView(view, false);});
$("#new-item").onclick=()=>newItem(); $("#new-task").onclick=newTask; $("#settings-form").onsubmit=saveSettings;
$("#new-area-form").onsubmit=async event=>{event.preventDefault();const input=event.target.elements.name;const name=input.value.trim();if(!name)return;try{await api("/api/areas/",{method:"POST",body:JSON.stringify({name})});input.value="";toast("Området är tillagt");await load();}catch(error){toast(error.message)}};
$("#save-notifications").onclick=()=>saveNotifications().catch(e=>toast(e.message));
$("#test-notification").onclick=()=>api("/api/push/test/",{method:"POST",body:"{}"}).then(r=>toast(r.sent?"Testnotisen skickades":"Ingen aktiv enhet hittades")).catch(e=>toast(e.message));
document.addEventListener("keydown",event=>{if((event.metaKey||event.ctrlKey)&&event.key.toLowerCase()==="k"){event.preventDefault();$("#search-trigger").click()}if(event.key==="Escape")$$('dialog[open]').forEach(d=>d.close())});
if("serviceWorker" in navigator) window.addEventListener("load",()=>navigator.serviceWorker.register("/sw.js"));
load();

$$('dialog').forEach(dialog => dialog.addEventListener('close', () => {
  if (dialog.contains($('#toast'))) ($$('dialog[open]').at(-1) || document.body).append($('#toast'));
  if (document.activeElement === document.body && !document.querySelector('dialog[open]')) $('.view:not(.hidden) button')?.focus({preventScroll:true});
}));
