import { useEffect, useRef, useState } from 'react';
import { Linking, Text, View } from 'react-native';
import { router } from 'expo-router';
import { Button, ErrorPanel, Field, Loading, Screen, styles, useResource } from '../ui/common';
import { useSession } from '../core/runtime';
import { gardenPath } from '../api/contract';
import { Edit, Plan, Plant, Rule, Task, Workspace } from './types';
import { editBody, editFor, inMonth, months, plantEdit, ruleEdit, statusLabel, taskEdit } from './domain';
import { Editor } from './Editor';
import { Shopping } from './Shopping';
import { notificationToken } from './notifications';
import { localScopeKey } from './local';

type Page='home'|'plants'|'year'|'shopping'|'settings'|'review'|'history';
const names:Record<Page,string>={home:'Överblick',plants:'Min trädgård',year:'Årshjulet',shopping:'Inköp',settings:'Inställningar',review:'Skötselförslag',history:'Historik'};
const FORM='workspace';
function groupTasks(tasks:Task[],key:(task:Task)=>string){return tasks.reduce<Record<string,Task[]>>((groups,task)=>{(groups[key(task)]??=[]).push(task);return groups;},{});}
function message(e:unknown){return e instanceof Error?e.message:'Kunde inte spara. Försök igen.';}
function RuleTiming({rule}:{rule:Rule}){
 const kind:Record<string,string>={planned:'Planerat arbete',on_demand:'Vid behov',general:'Allmänt råd',review:'Kräver klassificering'};
 const cadence:Record<string,string>={seasonal:'En gång per säsong',monthly:'Varje månad i fönstret',one_off:'Engångsarbete'};
 const window=rule.cadence==='one_off'?`${rule.one_off_date}–${rule.one_off_end}`:`${months[rule.start_month-1]}–${months[rule.end_month-1]}`;
 return <><Text style={styles.muted}>{kind[rule.advice_kind]??rule.advice_kind} · {cadence[rule.cadence]??rule.cadence} · {window}</Text>{!!rule.need_condition&&<Text style={styles.text}>När: {rule.need_condition}</Text>}</>;
}
function Sources({urls}:{urls:string[]}){return <>{urls.filter(url=>/^https?:\/\//.test(url)).map((url,i)=><Button key={`${url}:${i}`} title={`Källa: ${url.replace(/^https?:\/\//,'').split('/')[0]}`} secondary onPress={()=>void Linking.openURL(url).catch(()=>{})}/>)}</>;}

export function WorkspaceScreen(){
 const session=useSession(),scope=session.scope(),path=gardenPath(session.garden!)+'workspace/';
 const resource=useResource<Workspace>(path),data=resource.data;
 const [page,setPage]=useState<Page>('home'),[plantId,setPlantId]=useState<string|null>(null),[taskId,setTaskId]=useState<string|null>(null);
 const [query,setQuery]=useState(''),[grouping,setGrouping]=useState<'work'|'area'>('work');
 const [year,setYear]=useState(new Date().getFullYear()),[month,setMonth]=useState(new Date().getMonth()+1);
 const [editor,setEditor]=useState<Edit|null>(()=>{try{const raw=session.draft(scope,FORM).editor;return raw&&!session.outcome(scope,FORM)?.result?JSON.parse(raw):null;}catch{return null;}});
 const [error,setError]=useState(''),[notice,setNotice]=useState(''),[busy,setBusy]=useState(false);
 const mounted=useRef(true),saving=useRef(false);
 useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;};},[]);
 const confirmed=session.outcome(scope,FORM)?.result;
 const current=()=>mounted.current&&session.current(scope);
 function change(next:Edit){session.setDraft(scope,FORM,{editor:JSON.stringify(next)});setEditor(next);}
 async function begin(next:Edit){
  if(!current())return;setError('');setNotice('');
  try{await session.startNew(scope,FORM);if(current()){change(next);setPlantId(null);setTaskId(null);}}
  catch(e){if(current()){setError(message(e));const raw=session.draft(scope,FORM).editor;if(raw)setEditor(JSON.parse(raw));}}
 }
 async function save(){
  if(!editor||saving.current||!current())return;saving.current=true;setBusy(true);setError('');
  try{await session.submit(scope,FORM,path,editBody(editor));if(current()){setEditor(null);setNotice('Sparat.');resource.reload();}}
  catch(e){if(current())setError(message(e));}finally{saving.current=false;if(current())setBusy(false);}
 }
 async function reconcile(){
  setBusy(true);setError('');try{await session.reconcile(scope,FORM);if(current()){setEditor(null);setNotice('Sparningen är bekräftad.');resource.reload();}}catch(e){if(current())setError(message(e));}finally{if(current())setBusy(false);}
 }
 async function rebase(){
  if(!editor||!current())return;setBusy(true);setError('');
  try{const fresh=await session.read<Workspace>(scope,path);if(!current())return;
   if(fresh.membership!==data?.membership)throw new Error('Åtkomsten har ändrats. Öppna trädgården igen.');
   if(editor.command.startsWith('proposal.'))throw new Error('Öppna skötselförslaget igen och granska den nya jämförelsen innan du väljer råd.');
   let latest:Record<string,unknown>={};
   if(editor.command==='plant.update'){
    const row=fresh.items.find(p=>p.id===editor.target);if(!row)throw new Error('Växten finns inte längre.');latest=plantEdit(fresh,row).values;
   }else if(editor.command==='task.update'){
    const row=fresh.occurrences.find(t=>t.id===editor.target);if(!row)throw new Error('Uppgiften finns inte längre.');latest={...taskEdit(fresh,row).values,status:row.status,start:row.start,end:row.end};
   }else if(editor.command==='profile.update')latest={...fresh.profile};
   else if(editor.command==='rule.update'){
    const row=fresh.proposals.flatMap(p=>p.rules).find(r=>r.id===editor.target);if(!row)throw new Error('Förslaget finns inte längre.');latest=ruleEdit(fresh,row).values;
   }else if(editor.command==='area.update'){
    const row=fresh.areas.find(a=>a.id===editor.target);if(!row)throw new Error('Området finns inte längre.');latest={name:row.name};
   }
   session.acknowledgeReview(scope,FORM);
   change({...editor,context:fresh.context,revision:fresh.revision,latest,summary:'Jämför dina ändringar med senast sparade uppgifter och bekräfta igen.'});resource.reload();
  }catch(e){if(current())setError(message(e));}finally{if(current())setBusy(false);}
 }
 function go(next:Page){setPage(next);setPlantId(null);setTaskId(null);setEditor(null);setError('');setNotice('');}
 if(!data)return <Screen title="Din trädgård" back={()=>{session.selectGarden(null);router.replace('/');}}>{resource.loading&&<Loading/>}<ErrorPanel error={resource.error} retry={resource.reload}/></Screen>;
 if(data.protocol!=='workspace-1')return <Screen title="Din trädgård"><Text style={styles.text}>Servern behöver uppdateras för den nya appen.</Text></Screen>;
 const tasks=data.occurrences;
 const plant=plantId?data.items.find(p=>p.id===plantId):null,task=taskId?tasks.find(t=>t.id===taskId):null;
 const match=(...parts:string[])=>parts.join(' ').toLocaleLowerCase('sv-SE').includes(query.toLocaleLowerCase('sv-SE'));
 function action(command:string,target:string|null,values:Record<string,unknown>,title:string,summary?:string){void begin(editFor(data!,command,target,values,title,[],summary));}
 function taskCard(t:Task){return <View key={t.id} style={styles.card}><Text style={styles.label}>{t.title}</Text><Text style={styles.muted}>{t.item.name} · {t.area?.name||'Inte placerad'} · {t.start}–{t.end}</Text><Text style={styles.muted}>{statusLabel[t.status]??t.status}</Text><Button title="Visa uppgift" secondary onPress={()=>{setTaskId(t.id);setPlantId(null);}}/></View>;}
 function ruleCard(rule:Rule,actionable=true){return <View key={rule.id} style={styles.card}><Text style={styles.label}>{rule.title}</Text><Text style={styles.text}>{rule.instructions}</Text>{!!rule.need_condition&&<Text style={styles.muted}>{rule.need_condition}</Text>}<Sources urls={rule.source_urls}/>{actionable&&rule.advice_kind==='on_demand'&&<Button title="Det behövs nu" onPress={()=>action('work.need',rule.work_id,{},'Starta arbete vid behov',rule.title)}/>}{actionable&&<Button title="Inte relevant här" secondary onPress={()=>action('work.update',rule.work_id,{excluded:true},'Välj bort arbete',`${rule.title}. Historiken bevaras.`)}/>}</View>;}
 function plantDetails(p:Plant){return <><Text style={styles.title}>{p.name}</Text><Text style={styles.text}>{[p.cultivar,p.category,`${p.quantity} st`,p.age_stage,data!.areas.find(a=>a.id===p.area_id)?.name,p.location_detail].filter(Boolean).join(' · ')}</Text><Text style={styles.text}>{p.notes}</Text><View style={styles.row}><Button title="Redigera växt" secondary onPress={()=>void begin(plantEdit(data!,p))}/><Button title="Egen uppgift" secondary onPress={()=>void begin(taskEdit(data!,undefined,p.id))}/></View>
 <Text style={styles.label}>Skötselplan</Text>{p.plan?<><Text style={styles.text}>{p.plan.summary}</Text>{p.plan.status!=='active'&&<Button title="Granska väntande förslag" secondary onPress={()=>go('review')}/>} {(p.plan.status==='active'?p.current_rules:p.plan.rules).map(rule=>ruleCard(rule,p.plan?.status==='active'))}<Sources urls={p.plan.sources.map(s=>s.url)}/></>:<Text style={styles.muted}>Ingen skötselplan ännu.</Text>}
 <Button title="Hämta nya skötselråd" disabled={!data!.capabilities.research} onPress={()=>void begin(editFor(data!,'research.start',p.id,{consent:false},'Hämta skötselråd',[{key:'consent',label:'Jag godkänner att uppgifterna skickas för analys',type:'boolean'}],'Växtens uppgifter, trädgårdsprofil och skötselunderlag skickas till AI-tjänsten. Förslaget väntar på din granskning innan det aktiveras.'))}/>
 {!data!.capabilities.research&&<Text style={styles.muted}>Analys är inte aktiverad på servern.</Text>}
 {data!.jobs.filter(j=>j.item_id===p.id).slice(0,1).map(j=><View key={j.id} style={styles.card}><Text style={styles.text}>{({queued:'Analysen väntar',running:'Analysen förbereds',sending:'Analys pågår',succeeded:'Förslaget är klart',failed:'Analysen misslyckades',uncertain:'Analysens utfall behöver kontrolleras',cancelled:'Analysen avbröts'} as Record<string,string>)[j.state]||j.state}</Text>{!!j.reason&&<Text style={styles.muted}>{j.reason}</Text>}<Button title="Uppdatera status" secondary onPress={resource.reload}/><Button title="Granska förslag" secondary onPress={()=>go('review')}/></View>)}
 <Text style={styles.label}>Nästa uppgifter</Text>{p.next_tasks.map(taskCard)}<Text style={styles.label}>Historik</Text>{p.history.map(taskCard)}
 {p.excluded.length>0&&<Text style={styles.label}>Bortvalda arbeten</Text>}{p.excluded.map(w=><View key={w.id} style={styles.card}><Text style={styles.text}>{w.title} · {w.scope}</Text><Button title="Ta med igen" secondary onPress={()=>action('work.update',w.id,{excluded:false},'Ta med arbete igen',w.title)}/></View>)}</>;}
 function profileEditor(){const fields=[{key:'garden_name',label:'Trädgårdens namn'},{key:'city',label:'Plats'},{key:'cultivation_zone',label:'Odlingszon'},{key:'exposure',label:'Läge'},{key:'monthly_digest_day',label:'Månadssammanfattning, dag 1–28',type:'number' as const},{key:'reminder_weekday',label:'Påminnelsedag, måndag 0–söndag 6',type:'number' as const},{key:'reminder_hour',label:'Påminnelsetid, timme 0–23',type:'number' as const}];void begin(editFor(data!,'profile.update',null,{...data!.profile},'Trädgårdsprofil',fields));}
 async function notifications(active:boolean){
  setBusy(true);setError('');
  try{const token=await notificationToken(localScopeKey(scope),active);if(!current())return;
   await begin(editFor(data!,'notifications.save',null,{token,active,monthly_digest:active,task_reminders:active},active?'Påminnelser på den här enheten':'Stäng av påminnelser',active?[{key:'monthly_digest',label:'Månadssammanfattning',type:'boolean'},{key:'task_reminders',label:'Uppgiftspåminnelser',type:'boolean'}]:[]));
  }catch(e){if(current())setError(message(e));}finally{if(current())setBusy(false);}
 }
 const pending=Object.values(data.tasks).flat();
 const yearPending=tasks.filter(t=>t.status==='pending');
 return <Screen title={data.profile.garden_name||'Min trädgård'} back={()=>{session.selectGarden(null);router.replace('/');}}>
 <View style={styles.row}>{(['home','plants','year','shopping','settings'] as Page[]).map(value=><Button key={value} title={names[value]} secondary={page!==value} onPress={()=>go(value)}/>)}</View>
 <ErrorPanel error={resource.error} retry={resource.reload}/>{!!notice&&<Text accessibilityLiveRegion="polite" style={styles.text}>{notice}</Text>}
 {!editor&&!confirmed&&!!session.draft(scope,FORM).editor&&<Button title="Fortsätt med utkastet" secondary onPress={()=>setEditor(JSON.parse(session.draft(scope,FORM).editor))}/>}
 {!editor&&!!error&&<Text accessibilityRole="alert" style={styles.text}>{error}</Text>}
 {editor&&!confirmed?<Editor edit={editor} change={change} save={()=>void save()} close={()=>setEditor(null)} locked={session.locked(scope,FORM)} busy={busy} error={error} review={!!session.outcome(scope,FORM)?.reviewRequired} rebase={()=>void rebase()} reconcile={()=>void reconcile()}/>:
 task?<><Button title="Tillbaka till listan" secondary onPress={()=>setTaskId(null)}/><Text style={styles.title}>{task.title}</Text><Text style={styles.muted}>{task.item.name} · {task.start}–{task.end} · {statusLabel[task.status]}</Text><Text style={styles.text}>{task.instructions}</Text><Text style={styles.text}>{task.note}</Text><Sources urls={task.sources}/><Button title="Redigera uppgift" secondary onPress={()=>void begin(taskEdit(data,task))}/>{task.status!=='archived'&&<View style={styles.row}>{task.status==='pending'?<><Button title="Markera klar" onPress={()=>action('task.update',task.id,{status:'completed'},'Markera uppgiften klar',task.title)}/><Button title="Hoppa över" secondary onPress={()=>action('task.update',task.id,{status:'skipped'},'Hoppa över uppgiften',task.title)}/></>:<Button title="Återöppna" secondary onPress={()=>action('task.update',task.id,{status:'pending'},'Återöppna uppgift',task.title)}/>}</View>}{!!task.archive_reason&&<Text style={styles.muted}>{task.archive_reason}</Text>}</>:
 plant?<><Button title="Tillbaka till växterna" secondary onPress={()=>setPlantId(null)}/>{plantDetails(plant)}</>:
 <>
 {page==='home'&&<><Text style={styles.eyebrow}>{data.month_name} i trädgården</Text><Text style={styles.title}>En sak i taget.</Text><Text style={styles.text}>{data.completed} av {data.total} uppgifter utförda</Text><View style={styles.row}><Button title="Egen uppgift" disabled={!data.items.length} onPress={()=>void begin(taskEdit(data))}/><Button title={`Skötselförslag (${data.proposals.length})`} secondary onPress={()=>go('review')}/><Button title="Historik" secondary onPress={()=>go('history')}/></View>
 {session.unresolved().length>0&&<Button title="Kontrollera väntande sparningar" secondary onPress={()=>router.push({pathname:'/recovery',params:{form:FORM}})}/>}
 <Field label="Sök i växter, uppgifter och råd" value={query} onChange={setQuery}/>
 {query.length>=2?<>{data.items.filter(p=>match(p.name,p.cultivar,p.notes,...p.aliases,p.plan?.summary??'')).map(p=><Button key={p.id} title={p.name} secondary onPress={()=>setPlantId(p.id)}/>)}{tasks.filter(t=>match(t.title,t.instructions)).map(taskCard)}{data.items.flatMap(p=>p.current_rules).filter(r=>match(r.title,r.instructions)).map(rule=>ruleCard(rule,false))}</>:
 <><View style={styles.row}><Button title="Efter jobb" secondary={grouping!=='work'} onPress={()=>setGrouping('work')}/><Button title="Efter plats" secondary={grouping!=='area'} onPress={()=>setGrouping('area')}/></View>
 {pending.length?Object.entries(groupTasks(pending,t=>grouping==='area'?t.area?.name||'Inte placerad':t.category)).map(([label,rows])=><View key={label} style={{gap:12}}><Text style={styles.label}>{label}</Text>{rows?.map(taskCard)}</View>):<Text style={styles.text}>Inga väntande uppgifter i den hämtade listan.</Text>}
 {!!data.items.filter(p=>!p.has_care_plan).length&&<Text style={styles.muted}>{data.items.filter(p=>!p.has_care_plan).length} växter saknar skötselplan.</Text>}
 {data.advice.length>0&&<Text style={styles.label}>Vid behov</Text>}{data.advice.map(rule=>ruleCard(rule))}</>}</>}
 {page==='plants'&&<><Text style={styles.title}>Det som växer hos dig</Text><Button title="Lägg till växt" onPress={()=>void begin(plantEdit(data))}/><Field label="Filtrera växter" value={query} onChange={setQuery}/>{data.items.filter(p=>match(p.name,p.cultivar,p.category,data.areas.find(a=>a.id===p.area_id)?.name||'')).map(p=><View key={p.id} style={styles.card}><Text style={styles.label}>{p.name}</Text><Text style={styles.muted}>{p.cultivar} · {p.has_care_plan?'Skötselplan finns':'Saknar skötselplan'}</Text><Button title="Visa växt" secondary onPress={()=>setPlantId(p.id)}/></View>)}<Text style={styles.label}>Platser i trädgården</Text><Button title="Nytt område" secondary onPress={()=>void begin(editFor(data,'area.create',null,{name:''},'Nytt område',[{key:'name',label:'Namn'}]))}/>{data.areas.map(a=><View key={a.id} style={styles.card}><Text style={styles.text}>{a.name} · {a.item_count} växter</Text><View style={styles.row}><Button title="Byt namn" secondary onPress={()=>void begin(editFor(data,'area.update',a.id,{name:a.name},'Byt områdets namn',[{key:'name',label:'Namn'}]))}/><Button title="Ta bort område" secondary onPress={()=>action('area.delete',a.id,{},'Ta bort område',`${a.name}. Växterna bevaras och blir utan område.`)}/></View></View>)}</>}
 {page==='year'&&<><Text style={styles.title}>Årshjulet</Text><View style={styles.row}><Button title="Föregående år" secondary disabled={year<=1900} onPress={()=>setYear(y=>y-1)}/><Text style={styles.label}>{year}</Text><Button title="Nästa år" secondary disabled={year>=9999} onPress={()=>setYear(y=>y+1)}/></View><View style={styles.row}>{months.map((name,i)=><Button key={name} title={`${name} · ${yearPending.filter(t=>inMonth(t,year,i+1)).length}`} secondary={month!==i+1} onPress={()=>setMonth(i+1)}/>)}</View><Text style={styles.label}>{months[month-1]} {year}</Text>{tasks.filter(t=>inMonth(t,year,month)).map(taskCard)}{!tasks.some(t=>inMonth(t,year,month))&&<Text style={styles.muted}>Inga hämtade uppgifter för den här månaden.</Text>}</>}
 {page==='history'&&<><Text style={styles.title}>Historik</Text>{data.history.map(taskCard)}{!data.history.length&&<Text style={styles.muted}>Ingen historik ännu.</Text>}</>}
 {page==='shopping'&&<Shopping key={localScopeKey(scope)} storageKey={`garden-shopping:${localScopeKey(scope)}`}/>}
 {page==='review'&&<><Text style={styles.title}>Skötselförslag</Text>{data.proposals.length?data.proposals.map(plan=><Review key={`${plan.id}:${data.revision}`} plan={plan} editRule={rule=>void begin(ruleEdit(data,rule))} approve={(rule_ids,resolutions)=>action('proposal.approve',plan.proposal_id,{rule_ids,comparison_token:plan.comparison?.token,resolutions},'Godkänn valda råd',`${rule_ids.length} råd blir din nya plan. Tidigare historik bevaras.`)} reject={()=>action('proposal.reject',plan.proposal_id,{},'Avvisa skötselförslaget',plan.summary)}/>):<Text style={styles.muted}>Inga förslag väntar på granskning.</Text>}</>}
 {page==='settings'&&<><Text style={styles.title}>På dina villkor</Text><View style={styles.card}><Text style={styles.label}>{data.profile.garden_name}</Text><Text style={styles.text}>{[data.profile.city,data.profile.cultivation_zone,data.profile.exposure].filter(Boolean).join(' · ')}</Text><Button title="Redigera profil och tider" secondary onPress={profileEditor}/></View><View style={styles.card}><Text style={styles.label}>Påminnelser</Text><Text style={styles.muted}>Notiser innehåller en allmän påminnelse. Öppna appen för detaljer.</Text><Button title="Aktivera eller ändra påminnelser" disabled={busy||!data.capabilities.native_push} onPress={()=>void notifications(true)}/><Button title="Stäng av på den här enheten" secondary disabled={busy} onPress={()=>void notifications(false)}/>{!data.capabilities.native_push&&<Text style={styles.muted}>Mobilnotiser blir tillgängliga när servern och installationen är aktiverade.</Text>}</View><Button title="Granska skötselförslag" secondary onPress={()=>go('review')}/><Button title="Kontrollera väntande sparningar" secondary onPress={()=>router.push({pathname:'/recovery',params:{form:FORM}})}/><Button title="Konto och utloggning" secondary onPress={()=>{session.selectGarden(null);router.replace('/');}}/></>}
 <Button title="Uppdatera från trädgården" secondary onPress={resource.reload}/>
 </>}
 </Screen>;
}

function Review({plan,editRule,approve,reject}:{plan:Plan;editRule:(r:Rule)=>void;approve:(ids:string[],resolutions:Record<string,string>)=>void;reject:()=>void}){
 const [selected,setSelected]=useState(()=>plan.comparison?.rows.filter(r=>r.preselected&&!r.error).map(r=>r.rule_id)??[]);
 const [resolutions,setResolutions]=useState<Record<string,string>>({});
 return <View style={styles.card}><Text style={styles.label}>{plan.rules[0]?.item.name||'Skötselplan'}</Text><Text style={styles.text}>{plan.summary}</Text>{[...plan.warnings,...plan.uncertainties].map((text,i)=><Text key={i} style={styles.muted}>{text}</Text>)}{plan.comparison?.context_changed&&<Text style={styles.text}>Underlaget har ändrats sedan analysen. Jämförelsen använder dagens uppgifter.</Text>}
 {plan.rules.map(rule=>{const row=plan.comparison?.rows.find(r=>r.rule_id===rule.id);return <View key={rule.id} style={styles.card}><Text style={styles.label}>{rule.title} · {rule.scope}</Text><Text style={styles.muted}>{({new:'Nytt',changed:'Ändrat',unchanged:'Oförändrat',removed:'Tas bort'} as Record<string,string>)[row?.change??'']||''}</Text><RuleTiming rule={rule}/><Text style={styles.text}>{rule.instructions}</Text><Text style={styles.muted}>{rule.relevance_reason}</Text><Sources urls={rule.source_urls}/>{!!row?.error&&<Text style={styles.text}>{row.error}</Text>}{!!row?.history_count&&<Text style={styles.muted}>{row.history_count} historiska tillfällen bevaras.</Text>}{(!!row?.conflicts.length||!!rule.identity_source_id)&&<><Text style={styles.text}>Möjligt överlapp: {row?.conflicts.map(c=>`${c.title} · ${c.scope}`).join(', ')}</Text><Field label="Förklara överlapp eller koppling till tidigare arbete" multiline value={resolutions[rule.id]||''} onChange={value=>setResolutions({...resolutions,[rule.id]:value})}/></>}<View style={styles.row}><Button title={selected.includes(rule.id)?'✓ Valt råd':'Välj råd'} secondary={!selected.includes(rule.id)} disabled={!!row?.error} onPress={()=>setSelected(old=>old.includes(rule.id)?old.filter(id=>id!==rule.id):[...old,rule.id])}/><Button title="Redigera" secondary onPress={()=>editRule(rule)}/></View></View>;})}
 {plan.comparison?.removed.map((r,i)=><Text key={i} style={styles.muted}>Tas bort: {r.title} · {r.scope}. Historiken bevaras.</Text>)}<Sources urls={plan.sources.map(s=>s.url)}/><Button title="Godkänn valda råd" onPress={()=>approve(selected,resolutions)}/><Button title="Avvisa förslaget" secondary onPress={reject}/></View>;
}
