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
