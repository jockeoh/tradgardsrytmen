// Real HTTP + filesystem journal. Separate processes exercise crash/restart.
const fs=require('node:fs');const assert=require('node:assert/strict');const {randomUUID}=require('node:crypto');
const {create}=require('../garden/static/garden/offline-core.js');
const [fixtureFile,journal,phase]=process.argv.slice(2),f=JSON.parse(fs.readFileSync(fixtureFile));
const extras=new Map();const storage={removeItem:k=>extras.delete(k),getItem:k=>k!=='garden.m2.v1'?extras.get(k)||null:fs.existsSync(journal)?fs.readFileSync(journal,'utf8'):null,setItem:(k,v)=>{if(k!=='garden.m2.v1'){extras.set(k,v);return;}fs.writeFileSync(journal,v);const fd=fs.openSync(journal,'r');fs.fsyncSync(fd);fs.closeSync(fd);}};
const transport=async(path,opts)=>{
 const r=await fetch(f.base+path,{...opts,headers:{...opts.headers,Cookie:f.cookie,Origin:f.base}});
 if(phase==='crash'&&path.endsWith('/complete/')){assert.equal(r.status,200);await r.text();process.exit(23);}
 return r;
};
const e=create({storage,locks:{request:(_,fn)=>fn()},fetch:transport,origin:f.base,boundary:()=>f.boundary,uuid:randomUUID});
(async()=>{
 if(phase==='queue'){const id=await e.activate();await e.refresh(id);const task=(await e.view()).data.snapshot.tasks.find(t=>t.id===f.task);await e.enqueue(id,{task,note:''});assert.equal((await e.view()).data.snapshot.tasks[0].status,'pending');}
 else {const v=await e.view();await e.sync(v.active);const after=await e.view();assert.equal(after.data.queue.length,0);assert.equal(after.data.archive[0].result.note,'');assert.equal(after.data.archive[0].result.version,2);}
})().catch(e=>{console.error(e);process.exit(1)});
