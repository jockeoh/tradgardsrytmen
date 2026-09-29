(function(){
if(!navigator.locks?.request && !localStorage.getItem(GardenOffline.KEY))return;
/* Loaded on login, selection and the online app. Never adopt an old tab's intent. */
'use strict';
const offlineSession=GardenOffline.create({storage:localStorage,locks:navigator.locks,fetch:window.fetch.bind(window),origin:location.origin});
const settleSession=async()=>{
 const v=await offlineSession.view();
 const account=document.body.dataset.accountId,garden=document.body.dataset.gardenId;
 if(!account || (v.data && (v.data.context.account!==account || v.data.context.garden!==garden)))await offlineSession.deactivate();
 if(v.logout)await offlineSession.logout();
};
const offlineGate=settleSession();
offlineGate.catch(()=>{});
document.addEventListener('submit',e=>{
 const logout=new URL(e.target.action,location.href).pathname==='/accounts/logout/';
 const identity=location.pathname.startsWith('/accounts/login')||location.pathname.startsWith('/gardens/select');
 if(!logout&&!identity)return;
 e.preventDefault();const submitter=e.submitter;const pendingLogout=logout?offlineSession.logout():null;pendingLogout?.catch(()=>{});
 (async()=>{
  // A failed page-load attempt must not poison every later submit.
  await offlineGate.catch(()=>{});
  if(logout){await pendingLogout;location.href='/accounts/login/';return;}
  await settleSession();
  await offlineSession.deactivate();
  const csrf=e.target.querySelector('[name=csrfmiddlewaretoken]');
  if(csrf)csrf.value=decodeURIComponent((document.cookie.match(/(?:^|; )csrftoken=([^;]*)/)||[])[1]||csrf.value);
  if(submitter?.name){
   const f=document.createElement('input');f.type='hidden';f.name=submitter.name;f.value=submitter.value;e.target.append(f);
  }
  HTMLFormElement.prototype.submit.call(e.target);
 })().catch(()=>{
  let p=document.getElementById('offline-session-error');
  if(!p){p=document.createElement('p');p.id='offline-session-error';p.setAttribute('role','alert');e.target.append(p);}
  p.textContent='Lokalt låst. Anslut till nätet för att slutföra utloggning eller kontobyte. Väntande handlingar finns kvar.';
 });
});

})();
