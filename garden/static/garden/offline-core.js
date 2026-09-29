/* Durable M2 journal. One origin-wide Web Lock covers read/change/write AND transport.
   Never silently recover malformed/unwritable storage: no persistence => no mutation. */
(function(root) {
  'use strict';
  const KEY = 'garden.m2.v1', LOCK = 'garden.m2.v1', STOP = 'garden.m2.stop', WEEK = 604800000;
  const scope = c => [c.account, c.garden, c.membership].join(':');
  function create({storage, locks, fetch: transport, now = Date.now, uuid = () => crypto.randomUUID(), origin, csrf = () => typeof document === 'undefined' ? '' : decodeURIComponent((document.cookie.match(/(?:^|; )csrftoken=([^;]*)/)||[])[1]||''), boundary = () => typeof document === 'undefined' ? null : (document.cookie.match(/(?:^|; )garden_session_boundary=([^;]*)/)||[])[1]}) {
    const read = () => {
      const raw = storage.getItem(KEY);
      if (!raw) return {version:1, epoch:0, active:null, logout:false, scopes:{}};
      const d = JSON.parse(raw);
      if (d.version !== 1 || !d.scopes || !Number.isInteger(d.epoch)) throw Error('Lokal lagring kan inte läsas. Behåll webbläsardata och be om hjälp.');
      if(d.active && d.scopes[d.active]?.context.boundary !== boundary()) {d.active=null;d.epoch++;storage.setItem(KEY,JSON.stringify(d));}
      return d;
    };
    const write = d => storage.setItem(KEY, JSON.stringify(d));
    const lock = fn => {
      if (!locks?.request) return Promise.reject(Error('Säker lokal lagring saknas i webbläsaren. Öppna den vanliga trädgårdsvyn.'));
      return locks.request(LOCK, fn);
    };
    const active = (d, expected) => {
      if (!d.active || d.logout || storage.getItem(STOP) || (expected && d.active !== expected)) throw Error('Öppna rätt konto och trädgård igen.');
      return d.scopes[d.active];
    };
    async function http(path, c, body, key) {
      const controller = new AbortController(), timer = setTimeout(() => controller.abort(), 12000);
      try {
        const r = await transport(path, {method:body === undefined ? 'GET':'POST', credentials:'same-origin', cache:'no-store', redirect:'error', signal:controller.signal,
          headers:{'Content-Type':'application/json', ...(c ? {'X-Garden-Context':c.token,'X-CSRFToken':c.csrf}:{}), ...(key ? {'Idempotency-Key':key}: {})},
          ...(body === undefined ? {} : {body: typeof body === 'string' ? body : JSON.stringify(body)})});
        let data;
        try {data = await r.json();} catch (_) {throw Error("Ingen kontakt med servern. Dina handlingar finns kvar här. Synka igen när nätet återkommer.");}
        if (!r.ok) {const e = Error(data.error?.message || data.error || 'Kontrollera inloggningen och försök igen.'); e.code = data.error?.code || data.code; e.status=r.status; const wait=r.headers?.get('Retry-After');e.retryAt=wait?(Number.isFinite(Number(wait))?now()+Number(wait)*1000:Date.parse(wait)):0;throw e;}
        return data;
      } catch(e) {if(e.name==="TypeError" || e.name==="AbortError") throw Error("Ingen kontakt med servern. Dina handlingar finns kvar här. Synka igen när nätet återkommer."); throw e;} finally {clearTimeout(timer);}
    }
    function snapshotValid(p, c) {
      if (p.protocol !== 1 || !Array.isArray(p.tasks) || p.tasks.some(t=>t.garden_id!==c.garden || !t.id || !Number.isInteger(t.version))) throw Error('Serverns arbetslista kunde inte läsas.');
      return p;
    }
    async function refreshScope(s) {
      const p=snapshotValid(await http('/api/pwa/snapshot/',s.context), s.context);
      s.snapshot={tasks:p.tasks, fetched:now()};
      for(const q of s.queue) if(q.state==='conflict') q.current=p.tasks.find(t=>t.id===q.task.id)||null;
    }
    function invalidate(d,s,e) {
      if([401,403,404].includes(e.status)||e.code==='context_changed') {d.active=null;s.snapshot=null;write(d);}
    }
    function prepareLogout(d) {
      d.logout=d.logout || {scope:d.active};
      d.active=null;d.epoch++;for(const saved of Object.values(d.scopes)){saved.snapshot=null;saved.drafts={};}write(d);
    }
    async function finishLogout(d) {
      const options={credentials:'same-origin',cache:'no-store',signal:AbortSignal.timeout(12000)};
      const refreshCsrf=async()=>{
        const r=await transport('/accounts/login/',{...options,method:'GET'});
        if(!r.ok || !csrf()) throw Error('CSRF saknas.');
      };
      try {
        // The cookie belongs to the current session. Never reuse a journal token
        // or change any queued intent's signed account/garden/grant context.
        if(!csrf()) await refreshCsrf();
        const post=()=>transport('/accounts/logout/',{...options,method:'POST',headers:{'X-CSRFToken':csrf()}});
        let r=await post();
        if(r.status===403){await refreshCsrf();r=await post();}
        if(!r.ok) throw Error('Utloggningen avvisades.');
      } catch (_) {throw Error('Utloggad lokalt. Anslut för att avsluta serversessionen.');}
      d.logout=false; write(d); storage.removeItem(STOP);
    }
    return {
      scope,
      view: () => lock(() => {
        const d=read(), paused=!!storage.getItem(STOP), s=d.active&&!d.logout&&!paused?d.scopes[d.active]:null;
        const held=s?Object.entries(d.scopes).filter(([id,other])=>id!==d.active&&other.context.account===s.context.account).flatMap(([,other])=>other.queue.map(q=>({key:q.key,created:q.created}))):[];
        return JSON.parse(JSON.stringify({active:paused?null:d.active,logout:!!d.logout||paused,data:s,held}));
      }),
      activate: () => lock(async () => {
        const d=read();
        if (d.logout || storage.getItem(STOP)) {prepareLogout(d);await finishLogout(d); throw Error('Utloggningen är klar. Logga in igen.');}
        // Hide the old identity before a request; a failed online authentication is
        // never permission to display a different account's offline cache.
        d.active=null; d.epoch++; write(d);
        const c=await http('/api/pwa/context/');
        if(c.boundary!==boundary()) throw Error('Inloggningen ändrades. Öppna trädgården igen.');
        if(c.protocol!==1 || !c.account || !c.garden || !c.membership || !c.token || !c.csrf) throw Error('Servern behöver uppdateras.');
        c.origin=origin;
        const id=scope(c); let s=d.scopes[id];
        if(!s) s=d.scopes[id]={context:c, snapshot:null, queue:[], archive:[], drafts:{}};
        s.context=c; d.active=id; write(d);
        return id;
      }),
      refresh: expected => lock(async () => {
        const d=read(), s=active(d,expected);
        try {await refreshScope(s); write(d);} catch(e) {
          if([401,403,404,409].includes(e.status)){d.active=null;s.snapshot=null;write(d);} throw e;
        }
      }),
      enqueue: (expected,form) => {
        // Capture before waiting for the cross-tab lock. The visible form owns
        // both version and note; shared snapshots/drafts cannot rebase it.
        const intent=JSON.parse(JSON.stringify(form||null));
        return lock(() => {
          const d=read(),s=active(d,expected),t=intent?.task;
          if(!t || t.garden_id!==s.context.garden || !t.id || t.status!=='pending' || !Number.isInteger(t.version) || t.version<1) throw Error('Hämta uppgiften igen.');
          if(s.queue.some(q=>q.task.id===t.id)) throw Error('Uppgiften väntar redan på synkning.');
          const body={expected_version:t.version};
          if(Object.hasOwn(intent,'note')) {
            if(typeof intent.note!=='string') throw Error('Anteckningen kunde inte läsas.');
            body.note=intent.note;
          }
          const q={key:uuid(),path:`/api/v1/gardens/${s.context.garden}/tasks/${t.id}/complete/`,body:JSON.stringify(body),created:now(),state:'queued',task:t};
          s.queue.push(q);write(d);return q.key;
        });
      },
      sync: expected => lock(async () => {
        const d=read(),s=active(d,expected);
        // One observed clock applies to the whole queue, even when the first
        // receipt fails and aborts the batch before later rows are visited.
        const observeQueue=()=>{
          const time=now();
          for(const row of s.queue) {
            if(!row.readOnlyReason) {
              if(time<Math.max(row.created,row.lastObserved||row.created)) row.readOnlyReason='clock_rollback';
              else if(time-row.created>=WEEK) row.readOnlyReason='age_limit';
            }
            row.lastObserved=Math.max(time,row.lastObserved||row.created);
            if(row.readOnlyReason && !['conflict','rejected'].includes(row.state)) row.state='uncertain';
          }
          write(d);
        };
        for(const q of [...s.queue]) {
          if(storage.getItem(STOP)) return;
          const readOnly=()=>{observeQueue();return !!q.readOnlyReason;};
          const fenced=readOnly();
          if(q.state==='conflict' || q.state==='rejected' || now()<(q.retryAt||0)) continue;
          try {
            let result;
            if(q.sent || fenced) {
              const receipt=await http('/api/pwa/reconcile/',s.context,{path:q.path,key:q.key,body:JSON.parse(q.body)});
              if(receipt.state==='confirmed') result=receipt.result;
              else if(receipt.state!=='unknown') throw Error('Avstämningen kunde inte läsas.');
              else if(readOnly()) continue;
            }
            if(!result) {
              if(storage.getItem(STOP)) return;
              if(readOnly()) continue;
              // Durable attempted marker BEFORE crossing the network boundary.
              q.sent=true;q.state='sending';write(d);
              result=await http(`/api/pwa/tasks/${q.task.id}/complete/`,s.context,q.body,q.key);
            }
            observeQueue();
            if(result.id!==q.task.id || result.garden_id!==s.context.garden || result.status!=='completed') throw Error('Svaret kunde inte bekräftas.');
            q.state='confirmed';q.result=result;s.archive.push(q);s.queue=s.queue.filter(x=>x.key!==q.key);
            if(s.snapshot) s.snapshot.tasks=s.snapshot.tasks.map(t=>t.id===result.id?{...t,...result}:t);
            write(d);
          } catch(e) {
            readOnly();
            if(e.status===409 && ['version_conflict','invalid_transition'].includes(e.code)) {
              q.state='conflict';write(d);
              try {await refreshScope(s);q.current=s.snapshot.tasks.find(t=>t.id===q.task.id)||null;write(d);}catch(readError){invalidate(d,s,readError);throw readError;}
            } else {
              q.state=e.status===400?'rejected':'uncertain';if([429,503].includes(e.status))q.retryAt=Math.max(e.retryAt||0,now()+1000);write(d);
              invalidate(d,s,e);
              throw e;
            }
          }
        }
      }),
      resolve: (expected,key,retry) => lock(async () => {
        const d=read(),s=active(d,expected),q=s.queue.find(q=>q.key===key);
        if(!q || q.state!=='conflict') throw Error('Avstäm först handlingen.');
        try {await refreshScope(s);} catch(e) {invalidate(d,s,e);throw e;}
        const t=s.snapshot.tasks.find(t=>t.id===q.task.id);
        if(retry && (!t || t.status!=='pending')) {write(d);throw Error('Uppgiften är inte längre planerad. Behåll serverns status.');}
        // Only a definitive rejected attempt can be superseded by explicit choice.
        if(retry){const body=JSON.parse(q.body);body.expected_version=t.version;s.queue.push({...q,key:uuid(),body:JSON.stringify(body),created:now(),lastObserved:now(),readOnlyReason:null,sent:false,state:'queued',task:t,current:null});}
        s.archive.push({...q,state:'resolved'});s.queue=s.queue.filter(x=>x.key!==key);write(d);
      }),
      logout: () => {
        // Synchronous cross-tab fence, before waiting for an in-flight request's lock.
        // That request may already have committed; retain it, but send no next row.
        try {storage.setItem(STOP, '1');} catch (_) {return Promise.reject(Error('Lokal lagring kunde inte låsas. Utloggningen är inte klar.'));}
        return lock(async () => {const d=read();prepareLogout(d);await finishLogout(d);});
      },
      deactivate: () => lock(()=>{const d=read();d.active=null;d.epoch++;write(d);}),
    };
  }
  const api={create,scope,KEY,WEEK};
  if(typeof module!=='undefined') module.exports=api; else root.GardenOffline=api;
})(typeof window==='undefined'?this:window);
