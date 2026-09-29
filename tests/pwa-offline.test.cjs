const {test}=require('node:test');const assert=require('node:assert/strict');
const {create,KEY,WEEK}=require('../garden/static/garden/offline-core.js');
function harness(){
 let raw=null,clock=1000,serial=0,tail=Promise.resolve(),offline=false,drop=false,marker='one',csrf='csrf',serverCsrf='csrf',logoutHook=null;
 let context={protocol:1,account:'a',garden:'g',membership:1,token:'signed',csrf:'csrf',boundary:'one'};
 let beforeCommit=null;let beforeReceipt=null;
 let task={id:'task',garden_id:'g',title:'Vattna',version:1,status:'pending',note:'Bevara'};
 const receipts=new Map(),calls=[];
 const extra=new Map();const storage={getItem:k=>k===KEY?raw:extra.get(k)||null,setItem:(k,v)=>{if(k===KEY)raw=v;else extra.set(k,v);},removeItem:k=>extra.delete(k)};
 const locks={request:(name,fn)=>{const next=tail.then(fn);tail=next.catch(()=>{});return next;}};
 const response=(data,status=200)=>({ok:status===200,status,json:async()=>structuredClone(data)});
 const fetch=async(path,opts)=>{
  calls.push({path,opts});if(offline)throw Error('offline');
  if(path==='/api/pwa/context/')return response(context);
  if(path==='/accounts/login/'){csrf=serverCsrf;return {ok:true};}
  if(path==='/accounts/logout/'){if(logoutHook)logoutHook();return {ok:opts.headers['X-CSRFToken']===serverCsrf,status:opts.headers['X-CSRFToken']===serverCsrf?200:403};}
  if(opts.headers['X-Garden-Context']!==context.token)return response({code:'context_changed'},409);
  if(path==='/api/pwa/snapshot/')return response({protocol:1,tasks:[task]});
  const body=JSON.parse(opts.body);
  if(path==='/api/pwa/reconcile/'){if(beforeReceipt)await beforeReceipt();return response(receipts.has(body.key)?{state:'confirmed',result:receipts.get(body.key)}:{state:'unknown'});}
  assert.ok(JSON.parse(raw).scopes['a:g:1'].queue[0].sent,'persist attempted before network');
  if(beforeCommit)await beforeCommit();
  const key=opts.headers['Idempotency-Key'];
  if(receipts.has(key))return response(receipts.get(key));
  if(body.expected_version!==task.version)return response({error:{code:'version_conflict'}},409);
  task={...task,status:'completed',version:task.version+1,note:body.note??task.note};receipts.set(key,task);
  if(drop){drop=false;throw Error('lost after commit');}return response(task);
 };
 const client=()=>create({storage,locks,fetch,now:()=>clock,uuid:()=>`key-${++serial}`,origin:'test',boundary:()=>marker,csrf:()=>csrf});
 return {client,storage,calls,receipts,set csrf(v){csrf=v},set serverCsrf(v){serverCsrf=v},set logoutHook(v){logoutHook=v},set beforeCommit(v){beforeCommit=v},set beforeReceipt(v){beforeReceipt=v},get raw(){return JSON.parse(raw)},set offline(v){offline=v},set drop(v){drop=v},set time(v){clock=v},set task(v){task={...task,...v}},set marker(v){marker=v},set context(v){context={...context,...v}}};
}
async function form(e,note){const t=(await e.view()).data.snapshot.tasks[0];return {task:t,...(note===undefined?{}:{note})};}
async function ready(h){const e=h.client();const id=await e.activate();await e.refresh(id);return [e,id];}
test('offline queue and untouched note survive engine restart; confirmed history only after sync',async()=>{
 const h=harness();let[e,id]=await ready(h);h.offline=true;await e.enqueue(id,await form(e));assert.equal((await e.view()).data.snapshot.tasks[0].status,'pending');
 assert.equal(h.raw.scopes[id].queue[0].body,'{"expected_version":1}');e=h.client();assert.equal((await e.view()).data.queue.length,1);h.offline=false;await e.sync(id);assert.equal((await e.view()).data.snapshot.tasks[0].note,'Bevara');assert.equal(h.receipts.size,1);
});
test('explicit empty queued note preserved across engine restart',async()=>{const h=harness();const[e,id]=await ready(h);await e.enqueue(id,await form(e,''));await h.client().sync(id);assert.equal((await e.view()).data.snapshot.tasks[0].note,'');});
test('lost response after commit reconciles with original key and no second mutation',async()=>{const h=harness();let[e,id]=await ready(h);const key=await e.enqueue(id,await form(e));h.drop=true;await assert.rejects(e.sync(id));const frozen=h.raw.scopes[id].queue[0].body;e=h.client();await e.sync(id);assert.equal(h.receipts.size,1);assert.equal(h.calls.filter(c=>c.path.endsWith('/complete/')).length,1);assert.equal(h.raw.scopes[id].archive[0].key,key);assert.equal(h.raw.scopes[id].archive[0].body,frozen);});
test('two independent clients cannot overwrite journal or duplicate same task',async()=>{const h=harness();const[a,id]=await ready(h);const b=h.client();const r=await Promise.allSettled([a.enqueue(id,await form(a)),b.enqueue(id,await form(b))]);assert.equal(r.filter(x=>x.status==='fulfilled').length,1);await Promise.all([a.sync(id),b.sync(id)]);assert.equal(h.receipts.size,1);});
test('seven day unknown is read-only on every retry, even after restart',async()=>{const h=harness();const[e,id]=await ready(h);await e.enqueue(id,await form(e));h.time=WEEK+1000;await e.sync(id);await h.client().sync(id);assert.equal(h.calls.filter(c=>c.path.endsWith('/complete/')).length,0);assert.equal((await e.view()).data.queue[0].state,'uncertain');});
test('conflict fetches current state; explicit rebase creates one new key retaining edited note',async()=>{const h=harness();const[e,id]=await ready(h);const old=await e.enqueue(id,await form(e,'Lokal'));h.task={version:2,note:'Ny serveranteckning'};await e.sync(id);const q=(await e.view()).data.queue[0];assert.equal(q.current.note,'Ny serveranteckning');assert.equal(h.receipts.size,0);await e.resolve(id,old,true);await e.sync(id);assert.equal(h.receipts.size,1);assert.equal((await e.view()).data.snapshot.tasks[0].note,'Lokal');});
test('untouched note on explicit conflict retry keeps new server note',async()=>{const h=harness();const[e,id]=await ready(h);const k=await e.enqueue(id,await form(e));h.task={version:2,note:'Ny'};await e.sync(id);await e.resolve(id,k,true);await e.sync(id);assert.equal((await e.view()).data.snapshot.tasks[0].note,'Ny');});
test('offline logout hides snapshot, retains intent, and blocks activation until server logout completes',async()=>{const h=harness();const[e,id]=await ready(h);const k=await e.enqueue(id,await form(e));h.offline=true;await assert.rejects(e.logout());assert.equal((await e.view()).data,null);assert.equal(h.raw.scopes[id].queue[0].key,k);assert.equal(h.raw.scopes[id].snapshot,null);await assert.rejects(e.activate());h.offline=false;await assert.rejects(e.activate(),/Logga in/);assert.equal((await e.view()).logout,false);});
test('old page login boundary invalidates offline display and mutation',async()=>{const h=harness();const[e,id]=await ready(h);await e.enqueue(id,await form(e));h.marker='two';assert.equal((await e.view()).data,null);await assert.rejects(e.sync(id));assert.equal(h.receipts.size,0);});
test('account, garden and recreated membership cannot adopt old queue',async()=>{const h=harness();const[e,id]=await ready(h);await e.enqueue(id,await form(e));h.context={account:'b',garden:'other',membership:2,token:'new'};const b=await e.activate();assert.notEqual(id,b);assert.equal((await e.view()).data.queue.length,0);await assert.rejects(e.sync(id));h.context={account:'a',garden:'g',membership:3,token:'recreated'};await e.activate();assert.equal((await e.view()).data.queue.length,0);assert.equal((await e.view()).held.length,1);assert.equal(h.raw.scopes[id].queue.length,1);});
test('unwritable journal or missing locks never sends mutation',async()=>{const h=harness();const[e,id]=await ready(h);h.storage.setItem=()=>{throw Error('quota');};await assert.rejects(e.enqueue(id,await form(e)),/quota/);assert.equal(h.receipts.size,0);await assert.rejects(create({storage:h.storage,fetch:()=>{throw Error('must not fetch')}}).activate(),/lagring/);});
test('corrupt storage does not silently reset intentions',async()=>{const h=harness();h.storage.setItem(KEY,'{');await assert.rejects(h.client().activate());assert.equal(h.calls.length,0);});
test('logout in another client fences the rest of a batch while first request finishes',async()=>{
 const h=harness(),[e,id]=await ready(h);await e.enqueue(id,await form(e));
 const d=h.raw;d.scopes[id].queue.push({...d.scopes[id].queue[0],key:'second',task:{...d.scopes[id].queue[0].task,id:'second'}});h.storage.setItem(KEY,JSON.stringify(d));
 let started,release;const entered=new Promise(r=>started=r),blocked=new Promise(r=>release=r);h.beforeCommit=async()=>{started();await blocked;};
 const sync=e.sync(id);await entered;const logout=h.client().logout();release();await Promise.all([sync,logout]);
 assert.equal(h.calls.filter(c=>c.path.endsWith('/complete/')).length,1);assert.equal(h.raw.scopes[id].queue.length,1);assert.equal((await e.view()).data,null);
});
test('seven-day boundary is checked again after a slow reconciliation',async()=>{
 const h=harness(),[e,id]=await ready(h);await e.enqueue(id,await form(e));h.offline=true;await assert.rejects(e.sync(id));h.offline=false;
 const before=h.calls.filter(c=>c.path.endsWith('/complete/')).length;h.beforeReceipt=()=>{h.time=WEEK+1000;};await e.sync(id);
 assert.equal(h.calls.filter(c=>c.path.endsWith('/complete/')).length,before);
});
test('revocation clears display but preserves the frozen uncertain request',async()=>{
 const h=harness(),[e,id]=await ready(h);const key=await e.enqueue(id,await form(e));h.context={token:'revoked'};await assert.rejects(e.sync(id));assert.equal((await e.view()).data,null);assert.equal(h.raw.scopes[id].snapshot,null);assert.equal(h.raw.scopes[id].queue[0].key,key);
});

test('revoked access during explicit conflict resolution hides cached data and retains intent',async()=>{
 const h=harness(),[e,id]=await ready(h);const key=await e.enqueue(id,await form(e));h.task={version:2};await e.sync(id);h.context={token:'revoked'};await assert.rejects(e.resolve(id,key,true));assert.equal((await e.view()).data,null);assert.equal(h.raw.scopes[id].queue[0].key,key);
});

test('other tab refresh cannot upgrade the version of the displayed form',async()=>{
 const h=harness(),[a,id]=await ready(h),b=h.client();
 const shown=await form(a,'Text A');
 h.task={version:2,note:'Ny serveranteckning'};await b.refresh(id);
 await a.enqueue(id,shown);assert.deepEqual(JSON.parse(h.raw.scopes[id].queue[0].body),{expected_version:1,note:'Text A'});
 await a.sync(id);assert.equal(h.receipts.size,0);assert.equal(h.raw.scopes[id].queue[0].state,'conflict');
 assert.equal(h.raw.scopes[id].queue[0].current.note,'Ny serveranteckning');
});
test('another tab note and caller edits while waiting for lock cannot replace submitted intent',async()=>{
 const h=harness(),[a,id]=await ready(h),b=h.client();
 const fa=await form(a,'Text A'),fb=await form(b,'Text B');
 const submitting=a.enqueue(id,fa);fa.note=fb.note;fa.task.version=42;
 await submitting;assert.deepEqual(JSON.parse(h.raw.scopes[id].queue[0].body),{expected_version:1,note:'Text A'});
 await assert.rejects(b.enqueue(id,fb),/redan/);await a.sync(id);
 assert.equal(h.raw.scopes[id].archive[0].result.note,'Text A');
});
test('missing form context is rejected instead of adopting shared snapshot or drafts',async()=>{
 const h=harness(),[e,id]=await ready(h);await assert.rejects(e.enqueue(id,'task'),/Hämta/);
 await assert.rejects(e.enqueue(id,{task:{...(await form(e)).task,garden_id:'other'}}),/Hämta/);
 assert.equal(h.raw.scopes[id].queue.length,0);assert.equal(h.receipts.size,0);
});
test('anonymous logout with no CSRF bootstraps token and clears local fence',async()=>{
 const h=harness(),e=h.client();h.csrf='';await e.logout();
 assert.deepEqual(h.calls.map(c=>c.path),['/accounts/login/','/accounts/logout/']);
 assert.equal(h.calls[1].opts.headers['X-CSRFToken'],'csrf');assert.equal((await e.view()).logout,false);
});
for(const initial of ['', 'old-token']) test(`pending logout recovers current CSRF after restart (${initial||'missing'})`,async()=>{
 const h=harness(),[e,id]=await ready(h);await e.enqueue(id,await form(e,'Keep'));
 const frozen=structuredClone(h.raw.scopes[id]);h.csrf=initial;h.offline=true;await assert.rejects(e.logout());
 h.csrf='rotated';h.serverCsrf='rotated';h.offline=false;
 await assert.rejects(h.client().activate(),/Logga in/);
 assert.equal((await e.view()).logout,false);assert.equal(h.calls.at(-1).opts.headers['X-CSRFToken'],'rotated');
 assert.deepEqual(h.raw.scopes[id].queue,frozen.queue);assert.deepEqual(h.raw.scopes[id].context,frozen.context);
});
test('403 token rotation during logout has one bounded retry with fresh cookie',async()=>{
 const h=harness(),[e]=await ready(h);
 h.logoutHook=()=>{h.serverCsrf='new';h.logoutHook=null;};await e.logout();
 const posts=h.calls.filter(c=>c.path==='/accounts/logout/');
 assert.deepEqual(posts.map(c=>c.opts.headers['X-CSRFToken']),['csrf','new']);assert.equal((await e.view()).logout,false);
});
test('persistent logout 403 retains fence and queue; later retry can recover',async()=>{
 const h=harness(),[e,id]=await ready(h);await e.enqueue(id,await form(e));
 let serial=0;h.logoutHook=()=>{h.serverCsrf=`rotation-${++serial}`;};await assert.rejects(e.logout());
 assert.equal(serial,2);assert.equal((await e.view()).logout,true);assert.equal(h.raw.scopes[id].queue.length,1);
 h.logoutHook=null;h.csrf='valid';h.serverCsrf='valid';await h.client().logout();assert.equal((await e.view()).logout,false);
});
test('seven day fence survives clock adjustment and restart; later confirmed receipt still resolves',async()=>{
 const h=harness(),[e,id]=await ready(h),key=await e.enqueue(id,await form(e));
 const body=h.raw.scopes[id].queue[0].body;h.time=WEEK+1000;await e.sync(id);
 assert.equal(h.raw.scopes[id].queue[0].readOnlyReason,'age_limit');h.time=WEEK;await h.client().sync(id);
 assert.equal(h.calls.filter(c=>c.path.endsWith('/complete/')).length,0);
 assert.equal(h.calls.filter(c=>c.path==='/api/pwa/reconcile/').length,2);
 assert.equal(h.raw.scopes[id].queue[0].key,key);assert.equal(h.raw.scopes[id].queue[0].body,body);
 h.receipts.set(key,{id:'task',garden_id:'g',status:'completed',version:2,note:'Bevara'});
 await h.client().sync(id);assert.equal(h.raw.scopes[id].queue.length,0);assert.equal(h.raw.scopes[id].archive[0].key,key);
});
test('time fence is durable even when first receipt lookup fails',async()=>{
 const h=harness(),[e,id]=await ready(h);await e.enqueue(id,await form(e));h.time=WEEK+1000;h.offline=true;
 await assert.rejects(e.sync(id));h.offline=false;h.time=2000;await h.client().sync(id);
 assert.equal(h.calls.filter(c=>c.path.endsWith('/complete/')).length,0);assert.equal(h.raw.scopes[id].queue[0].readOnlyReason,'age_limit');
});
test('backwards clock fence survives time recovery and restart',async()=>{
 const h=harness(),[e,id]=await ready(h);await e.enqueue(id,await form(e));h.time=999;await e.sync(id);
 h.time=2000;await h.client().sync(id);assert.equal(h.raw.scopes[id].queue[0].readOnlyReason,'clock_rollback');
 assert.equal(h.calls.filter(c=>c.path.endsWith('/complete/')).length,0);
});
test('rollback above creation time is detected from persisted last observed time',async()=>{
 const h=harness(),[e,id]=await ready(h);await e.enqueue(id,await form(e));h.time=3000;h.offline=true;await assert.rejects(e.sync(id));
 const attempts=h.calls.filter(c=>c.path.endsWith('/complete/')).length;
 h.offline=false;h.time=2000;await h.client().sync(id);h.time=4000;await h.client().sync(id);
 assert.equal(h.raw.scopes[id].queue[0].readOnlyReason,'clock_rollback');assert.equal(h.calls.filter(c=>c.path.endsWith('/complete/')).length,attempts);
});

// Execute shipped UI scripts with a deliberately small DOM adapter. These are
// wiring/regression tests, not claims of real browser or installed PWA coverage.
const vm=require('node:vm'),fs=require('node:fs');
const worklistSource=fs.readFileSync(require.resolve('../garden/static/garden/worklist.js'),'utf8');
const sessionSource=fs.readFileSync(require.resolve('../garden/static/garden/offline-session.js'),'utf8');
function tabStorage(){const entries=new Map();return {getItem:k=>entries.get(k)||null,setItem:(k,v)=>entries.set(k,v),removeItem:k=>entries.delete(k)};}
function ui(h,e,sessionStorage=tabStorage()){
 const events={},windowEvents={},elements={};
 const node=()=>({innerHTML:'',textContent:'',hidden:false,querySelector(){return this.child??=node();}});
 for(const id of ['open','refresh','signin','held','identity','fetched','pending','tasks','history','status','logout'])elements[id]=node();
 const document={getElementById:id=>elements[id],addEventListener:(name,fn)=>events[name]=fn,activeElement:null,querySelector:()=>null};
 const context=vm.createContext({GardenOffline:{create:()=>e,KEY,WEEK},localStorage:h.storage,sessionStorage,document,
  navigator:{onLine:false,locks:{}},location:{origin:'test'},window:{fetch:()=>{},addEventListener:(name,fn)=>windowEvents[name]=fn}});
 vm.runInContext(worklistSource,context);
 const done=()=>vm.runInContext('operations',context);
 const input=value=>{document.activeElement={tagName:'TEXTAREA'};events.input({target:{matches:()=>true,dataset:{note:'task'},value}});};
 const submit=value=>{events.submit({preventDefault(){},target:{matches:()=>true,dataset:{task:'task'},querySelector:()=>({value})}});return done();};
 return {done,input,submit,sessionStorage,elements,render:()=>vm.runInContext('render()',context),async storageChanged(){windowEvents.storage({key:KEY});await new Promise(r=>setImmediate(r));await done();}};
}
test('shipped UI submits displayed version after another tab refresh while textarea has focus',async()=>{
 const h=harness(),[a,id]=await ready(h),ua=ui(h,a),ub=ui(h,h.client());await Promise.all([ua.done(),ub.done()]);
 ua.input('Text A');h.task={version:2,note:'Ny serveranteckning'};await h.client().refresh(id);await ub.render();await ua.storageChanged();
 assert.match(ua.elements.tasks.innerHTML,/Bevara/);assert.match(ub.elements.tasks.innerHTML,/Ny serveranteckning/);
 await ua.submit('Text A');assert.deepEqual(JSON.parse(h.raw.scopes[id].queue[0].body),{expected_version:1,note:'Text A'});
 await a.sync(id);assert.equal(h.raw.scopes[id].queue[0].state,'conflict');assert.equal(h.receipts.size,0);
});
test('shipped UI uses own field when two tabs edit the same task',async()=>{
 const h=harness(),[a,id]=await ready(h),ua=ui(h,a),ub=ui(h,h.client());await Promise.all([ua.done(),ub.done()]);
 ua.input('Text A');ub.input('Text B');await ua.storageChanged();await ua.submit('Text A');
 assert.deepEqual(JSON.parse(h.raw.scopes[id].queue[0].body),{expected_version:1,note:'Text A'});
 await ub.submit('Text B');assert.equal(h.raw.scopes[id].queue.length,1);assert.match(ub.elements.status.textContent,/redan/);
});
for(const edited of [false,true])test(`shipped UI preserves ${edited?'explicit empty':'untouched'} note across rerender and tab reload`,async()=>{
 const h=harness(),[e,id]=await ready(h),first=ui(h,e);await first.done();if(edited)first.input('');
 await first.render();const reloaded=ui(h,h.client(),first.sessionStorage);await reloaded.done();
 await reloaded.submit(edited?'':'Bevara');const body=JSON.parse(h.raw.scopes[id].queue[0].body);
 assert.equal(Object.hasOwn(body,'note'),edited);if(edited)assert.equal(body.note,'');
});
test('shipped UI keeps draft and its original version through refresh and reload',async()=>{
 const h=harness(),[e,id]=await ready(h),first=ui(h,e);await first.done();first.input('Original draft');
 h.task={version:2,note:'Server version 2'};await e.refresh(id);await first.render();
 const reloaded=ui(h,h.client(),first.sessionStorage);await reloaded.done();await reloaded.submit('Original draft');
 assert.deepEqual(JSON.parse(h.raw.scopes[id].queue[0].body),{expected_version:1,note:'Original draft'});
});
test('shipped UI clears tab drafts at logout and cannot restore them across session boundary',async()=>{
 const h=harness(),[e]=await ready(h),first=ui(h,e);await first.done();first.input('Private');
 h.offline=true;await assert.rejects(e.logout());await first.render();assert.equal(first.sessionStorage.getItem('garden.m2.forms.v1'),null);
 assert.equal(first.elements.tasks.innerHTML,'');
});
test('shipped login gate retries failed pending logout before submitting login',async()=>{
 const h=harness(),[e,id]=await ready(h);await e.enqueue(id,await form(e));h.offline=true;await assert.rejects(e.logout());
 let submit,submissions=0;
 const document={cookie:'csrftoken=rotated',body:{dataset:{}},addEventListener:(name,fn)=>{if(name==='submit')submit=fn;},getElementById:()=>null,createElement:()=>({setAttribute(){}})};
 const context=vm.createContext({GardenOffline:{create:()=>h.client(),KEY},localStorage:h.storage,navigator:{locks:{request(){}}},
  document,window:{fetch(){}},location:{origin:'test',pathname:'/accounts/login/',href:'https://test/accounts/login/'},URL,
  HTMLFormElement:{prototype:{submit(){assert.equal(h.raw.logout,false);assert.equal(h.storage.getItem('garden.m2.stop'),null);submissions++;}}}});
 vm.runInContext(sessionSource,context);await new Promise(r=>setImmediate(r));
 const csrfField={value:'old'};const target={action:'https://test/accounts/login/',append(){},querySelector:()=>csrfField};
 submit({preventDefault(){},target});await new Promise(r=>setImmediate(r));assert.equal(submissions,0);
 h.offline=false;h.csrf='rotated';h.serverCsrf='rotated';submit({preventDefault(){},target});await new Promise(r=>setImmediate(r));
 assert.equal(submissions,1);assert.equal(csrfField.value,'rotated');assert.equal(h.raw.scopes[id].queue.length,1);assert.equal(h.raw.active,null);
});

test('age limit crossed during failed receipt lookup persists before a later clock rollback',async()=>{
 const h=harness(),[e,id]=await ready(h);await e.enqueue(id,await form(e));h.offline=true;await assert.rejects(e.sync(id));h.offline=false;
 const attempts=h.calls.filter(c=>c.path.endsWith('/complete/')).length;
 h.beforeReceipt=()=>{h.time=WEEK+1000;throw Error('receipt lost');};await assert.rejects(e.sync(id));
 assert.equal(h.raw.scopes[id].queue[0].readOnlyReason,'age_limit');h.time=2000;h.beforeReceipt=null;await h.client().sync(id);
 assert.equal(h.calls.filter(c=>c.path.endsWith('/complete/')).length,attempts);
});
test('failure to persist a time fence prevents transport',async()=>{
 const h=harness(),[e,id]=await ready(h);await e.enqueue(id,await form(e));h.time=WEEK+1000;
 const calls=h.calls.length;h.storage.setItem=()=>{throw Error('quota');};await assert.rejects(e.sync(id),/quota/);assert.equal(h.calls.length,calls);
});

test('shipped UI captures actual field value even without a delivered input event',async()=>{
 const h=harness(),[e,id]=await ready(h),tab=ui(h,e);await tab.done();await tab.submit('Visible field');
 assert.deepEqual(JSON.parse(h.raw.scopes[id].queue[0].body),{expected_version:1,note:'Visible field'});
});
test('failure to remove session drafts cannot leave private DOM visible after logout',async()=>{
 const h=harness(),[e]=await ready(h),tab=ui(h,e);await tab.done();tab.input('Private');
 tab.sessionStorage.removeItem=()=>{throw Error('storage unavailable');};h.offline=true;await assert.rejects(e.logout());await tab.render();
 assert.equal(tab.elements.tasks.innerHTML,'');assert.equal(tab.elements.pending.innerHTML,'');assert.equal(tab.elements.history.hidden,true);
});
test('legacy pending logout with frozen CSRF recovers without changing journal scope',async()=>{
 const h=harness(),[e,id]=await ready(h);await e.enqueue(id,await form(e));h.offline=true;await assert.rejects(e.logout());
 const old=h.raw;old.logout={csrf:''};h.storage.setItem(KEY,JSON.stringify(old));
 h.csrf='new';h.serverCsrf='new';h.offline=false;await h.client().logout();
 assert.equal(h.calls.at(-1).opts.headers['X-CSRFToken'],'new');assert.equal(h.raw.scopes[id].context.membership,1);
 assert.equal(h.raw.scopes[id].queue[0].key,old.scopes[id].queue[0].key);assert.equal((await e.view()).logout,false);
});
