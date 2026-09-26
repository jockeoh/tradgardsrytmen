const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const vm = require('node:vm');
const source = readFileSync('garden/static/garden/app.js', 'utf8');
const worker = readFileSync('garden/static/garden/sw.js', 'utf8');
// Load the shipped functions, with only browser startup/event wiring omitted.
function runtime(extra = {}) {
  const context = vm.createContext({location: {hash:''}, window: {localStorage: {getItem:()=>null}}, document: {}, ...extra});
  vm.runInContext(source.slice(0, source.indexOf('document.addEventListener("click"')), context);
  return context;
}

test('empty current list stays neutral after completing a manual task', () => {
  const elements = new Map();
  const get = key => {if(!elements.has(key)) elements.set(key,{classList:{toggle(){}},textContent:'',innerHTML:''}); return elements.get(key);};
  const c = runtime({document:{querySelector:get,querySelectorAll:()=>[]}});
  vm.runInContext('state.data = {items: [{}, {}, {}, {}, {}, {}], completed: 1}; renderTasks({due: [], overdue: [], later: []});',c);
  assert.match(get('#task-groups').innerHTML,/Inga planerade uppgifter just nu/);
  assert.doesNotMatch(get('#task-groups').innerHTML,/Du är i fas/);
});

test('focus restoration follows identity, not old row position', () => {
  const old = {hasAttribute:n=>n==='data-shopping-toggle',getAttribute:()=> 'second'};
  let focused;
  const replacement = {getAttribute:()=> 'second',focus:()=>{focused='second';}};
  const other = {getAttribute:()=> 'first',focus:()=>{focused='first';}};
  const container = {contains:()=>true,querySelectorAll:()=>[other,replacement]};
  const c=runtime({document:{activeElement:old},container});
  vm.runInContext('preserveFocus(container, null)()',c);
  assert.equal(focused,'second');
  container.querySelectorAll=()=>[];
  c.fallback={focus:()=>{focused='input';}};
  vm.runInContext('preserveFocus(container, fallback)()',c);
  assert.equal(focused,'input');
});

for (const kind of ['item','task']) test(`complete and undo refresh the open ${kind} view`, async () => {
  const calls=[];
  const dialog={open:true,scrollTop:240};
  const detail={querySelector:()=>null};
  const c=runtime({document:{activeElement:{isConnected:true},querySelector:s=>s==='#detail-dialog'?dialog:detail,querySelectorAll:()=>[]},calls});
  vm.runInContext(`state.data={tasks:{due:[{id:42}],overdue:[],later:[]}}; state.detail={kind:'${kind}',id:17};
    api=async(url,options)=>calls.push(JSON.parse(options.body).status);
    renderTasks=()=>{}; load=async()=>calls.push('load');
    openItem=async id=>calls.push('item:'+id); openTask=async id=>calls.push('task:'+id);
    toast=(message,undo)=>{state.testUndo=undo;};`,c);
  await vm.runInContext('updateTask(42,"completed")',c);
  assert.deepEqual(calls,['completed','load',`${kind}:17`]);
  assert.equal(dialog.scrollTop,240);
  await vm.runInContext('state.testUndo()',c);
  assert.deepEqual(calls.slice(3),['pending','load',`${kind}:17`]);
});

test('undo feedback belongs to the modal top layer and does not expire', () => {
  let parent, timeout=false;
  const el={textContent:'',append(){},classList:{add(){}}};
  const dialog={append:value=>{parent=value;}};
  const c=runtime({clearTimeout(){},window:{localStorage:{getItem:()=>null},setTimeout:()=>{timeout=true;}},document:{querySelector:()=>el,querySelectorAll:()=>[dialog],createElement:()=>({})}});
  vm.runInContext('toast("Klar",()=>{})',c);
  assert.equal(parent,el);
  assert.equal(timeout,false);
});

test('opening another dialog carries existing undo into that modal', () => {
  let attached=false, opened=false;
  const message={classList:{contains:()=>true}};
  const dialog={showModal:()=>{opened=true;},append:el=>{attached=el===message;}};
  const c=runtime({document:{querySelector:()=>message},dialog});
  vm.runInContext('showDialog(dialog)',c);
  assert.ok(opened && attached);
});

test('browser-only data is scoped by account and garden', () => {
  assert.match(source, /garden-shopping-v2:\$\{accountStorageScope\}/);
  assert.match(source, /garden-task-view:\$\{accountStorageScope\}/);
  assert.match(source, /garden-form-draft:\$\{accountStorageScope\}:\$\{title\}/);
  assert.doesNotMatch(source, /readPreference\("garden-shopping-v1"/);
  assert.doesNotMatch(source, /removeItem\("garden-shopping-v1"/);
});

test('service worker never caches authenticated html or api data', () => {
  assert.doesNotMatch(worker, /const ASSETS = \["\/"/);
  assert.match(worker, /pathname\.startsWith\("\/static\/"\)/);
  assert.doesNotMatch(worker, /caches\.match\("\/"\)/);
});

test('research network retry keeps intent key and does not resend automatically', async () => {
  let serial=0;
  const calls=[];
  const c=runtime({crypto:{randomUUID:()=>`intent-${++serial}`}, calls});
  vm.runInContext(`api=async(url,options)=>{calls.push(options.headers['Idempotency-Key']);if(calls.length===1)throw new Error('network lost');return {job:{state:'queued'}};};`, c);
  await assert.rejects(vm.runInContext('requestResearch(17)', c));
  assert.deepEqual(calls,['intent-1']);
  await vm.runInContext('requestResearch(17)', c);
  assert.deepEqual(calls,['intent-1','intent-1']);
  await vm.runInContext('requestResearch(17)', c);
  assert.deepEqual(calls,['intent-1','intent-1','intent-2']);
});

test('queued research does not claim proposal is ready', async () => {
  const messages=[];
  const c=runtime({messages,button:{textContent:'Hämta råd'}});
  vm.runInContext(`requestResearch=async()=>({job:{state:'queued'}});toast=message=>messages.push(message);openItem=async()=>{};`, c);
  await vm.runInContext('research(17,button)', c);
  assert.match(messages[0],/köad/);
  assert.doesNotMatch(messages[0],/redo att granskas/);
});

test('uncertain research clearly requires manual reconciliation', () => {
  const c=runtime();
  const markup=vm.runInContext(`researchJobMarkup({state:'uncertain'})`, c);
  assert.match(markup,/körs inte igen automatiskt/);
  assert.match(markup,/administratören/);
});

test('all API reads and writes use immutable page context despite a shared-cookie switch', async () => {
  const calls=[];
  const dataset={accountId:'alice', gardenId:'A', webContext:'signed-A'};
  const c=runtime({document:{body:{dataset},cookie:'csrftoken=fresh-shared-cookie'},fetch:async(url,options)=>{
    calls.push({url,options});return {ok:false,status:409,json:async()=>({code:'context_changed',error:'Kontexten har ändrats'})};
  }});
  dataset.webContext='signed-B'; // Neither DOM changes nor caller headers may rebind this page.
  for(const options of [{}, {method:'POST',body:'{"notes":"Privat A"}',headers:{'X-Garden-Context':'signed-B'}}]) {
    c.options=options;
    await assert.rejects(vm.runInContext('api("/api/items/", options)',c),/Kontexten har ändrats/);
  }
  assert.equal(calls.length,2);
  for(const {options} of calls) {
    assert.equal(options.headers['X-Garden-Context'],'signed-A');
    assert.equal(options.cache,'no-store');
  }
  assert.equal(calls[1].options.headers['X-CSRFToken'],'fresh-shared-cookie');
});

for(const status of [401,409]) test(`failed form submission (${status}) retains original scoped draft and stays open`,async()=>{
  const storage=new Map();
  let redirected=false, closed=false, alert, sent;
  const button={};
  const fields=[{name:'name',value:'Ros'}, {name:'notes',value:'Privat A'}];
  const form={dataset:{},elements:fields,querySelector:s=>s==='[type=submit]'?button:s==='.form-actions'?{before:el=>{alert=el;}}:null};
  const dialog={showModal(){},close(){closed=true;}};
  const toast={classList:{contains:()=>false}};
  const nodes={'#dynamic-form':form,'#form-dialog':dialog,'#form-content':{},'#toast':toast};
  const c=runtime({location:{hash:'',href:'https://example.test/',pathname:'/',search:'',assign:()=>{redirected=true;}},
    window:{localStorage:{getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)},sessionStorage:{setItem(){}}},
    document:{body:{dataset:{accountId:'alice',gardenId:'A',webContext:'signed-A'}},cookie:'csrftoken=valid',querySelector:s=>nodes[s],createElement:()=>({setAttribute(){},focus(){}})},
    FormData:class {constructor(form){return form.elements.map(f=>[f.name,f.value]);}},
    fetch:async(url,options)=>{sent=options;return {ok:false,status,json:async()=>({error:'Kontexten har ändrats',code:'context_changed'})};}
  });
  vm.runInContext('openForm("Ny växt", "", "Spara", async fd => api("/api/items/",{method:"POST",body:JSON.stringify(Object.fromEntries(fd))}))',c);
  await form.onsubmit({preventDefault(){}});
  assert.equal(closed,false);
  assert.equal(redirected,false);
  assert.equal(button.disabled,false);
  assert.ok(alert.textContent);
  assert.equal(sent.headers['X-Garden-Context'],'signed-A');
  assert.equal(JSON.parse(storage.get('garden-form-draft:alice:A:Ny växt')).notes,'Privat A');
  assert.equal(storage.size,1);
  assert.equal(fields[1].value,'Privat A');
});

test('a newly loaded different account or garden cannot restore the original form draft',()=>{
  const storage=new Map([['garden-form-draft:alice:A:Ny växt',JSON.stringify({notes:'Privat A'})]]);
  function openPage(accountId,gardenId) {
    const field={name:'notes',value:''};
    const form={dataset:{},elements:[field]};
    const nodes={'#dynamic-form':form,'#form-dialog':{showModal(){}},'#form-content':{},'#toast':{classList:{contains:()=>false}}};
    const c=runtime({window:{localStorage:{getItem:k=>storage.get(k)||null}},document:{body:{dataset:{accountId,gardenId}},querySelector:s=>nodes[s]}});
    vm.runInContext('openForm("Ny växt", "", "Spara", async()=>{})',c);
    return field.value;
  }
  assert.equal(openPage('alice','B'),'');
  assert.equal(openPage('bob','A'),'');
  assert.equal(openPage('alice','A'),'Privat A');
  assert.equal(storage.size,1);
});

test('reconciled research reports no new transmission and requires a new explicit action', () => {
  const c = runtime();
  const markup = vm.runInContext(`researchJobMarkup({state:'reconciled'})`, c);
  assert.match(markup,/Ingen ny analys har skickats/);
  assert.match(markup,/uttryckligen begära/);
  assert.doesNotMatch(markup,/Okänd analysstatus/);
});
