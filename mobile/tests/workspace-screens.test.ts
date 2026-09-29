import './register.mjs';
import {test} from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import {act,create,ReactTestRenderer} from 'react-test-renderer';
import {randomUUID} from 'node:crypto';
import {Session} from '../src/core/session';
import {SessionProvider} from '../src/core/runtime';
import {WorkspaceScreen} from '../src/workspace/WorkspaceScreen';
import {Workspace,ShoppingRow,Rule,Task} from '../src/workspace/types';
import {Request,ApiError} from '../src/api/contract';
import {localScopeKey,undoShopping} from '../src/workspace/local';

const base=()=>({protocol:'workspace-1',garden_id:'garden',membership:1,context:'grant',revision:'v1',today:'2026-09-29',month_name:'September',progress:0,completed:0,total:1,tasks:{due:[]},items:[{id:'1',name:'Ros',aliases:[],notes:'',cultivar:'',kind:'individual',category:'',quantity:1,age_stage:'',area_id:null,location_detail:'',canonical_name:'',has_care_plan:false,current_rules:[],next_tasks:[],history:[],advice:[],excluded:[]}],areas:[],advice:[],history:[],occurrences:[],proposals:[],work_categories:['Övrigt'],profile:{garden_name:'Hem',city:'Lund',cultivation_zone:'1',exposure:'Sol',monthly_digest_day:1,reminder_weekday:1,reminder_hour:9},capabilities:{research:false,native_push:false},jobs:[]} as Workspace);
let root:ReactTestRenderer;
const text=()=>JSON.stringify(root.toJSON());
async function settle(){await act(async()=>{await new Promise(r=>setTimeout(r,20));});}
async function press(label:string){await act(async()=>{const b=root.root.findAll(n=>n.type==='button').find(n=>n.props.accessibilityLabel===label);assert.ok(b,label);assert.notEqual(b.props.disabled,true);b.props.onPress();});await settle();}
async function field(label:string,value:string){await act(async()=>{root.root.findAll(n=>n.type==='input').find(n=>n.props.accessibilityLabel===label)!.props.onChangeText(value);});}
async function mount(data:Workspace,write:(r:Request)=>unknown){const session=new Session(randomUUID,async()=>{});session.login({id:'account',display_name:'Kim'},{request:async<T>(r:Request)=>structuredClone(r.method==='GET'?data:await write(r)) as T});session.selectGarden('garden');await act(async()=>{root=create(React.createElement(SessionProvider,{value:session},React.createElement(WorkspaceScreen)));});await settle();return session;}

test('full workspace navigation and plant edit use frozen server context',async()=>{
 const data=base(),calls:Request[]=[];
 await mount(data,r=>{calls.push(r);data.items[0].name=String(r.body!.values && (r.body!.values as any).name);return {protocol:'workspace-1',garden_id:'garden',membership:1,result:{ok:true}};});
 await press('Min trädgård');await press('Visa växt');await press('Redigera växt');await field('Namn','Röd ros');await press('Bekräfta och spara');
 assert.equal(calls.length,1);assert.equal(calls[0].body!.revision,'v1');assert.equal((calls[0].body!.values as any).name,'Röd ros');assert.match(text(),/Röd ros/);
 await press('Årshjulet');assert.match(text(),/Nästa år/);await press('Inköp');assert.match(text(),/Beräkna jord/);await press('Inställningar');assert.match(text(),/Redigera profil och tider/);
 await act(async()=>root.unmount());
});
test('conflict retains draft and requires visible fresh review before a new mutation',async()=>{
 const data=base(),calls:Request[]=[];
 await mount(data,r=>{calls.push(r);if(calls.length===1){data.revision='v2';data.items[0].name='Annan ändring';throw new ApiError(409,{error:{code:'version_conflict',message:'Ändrad',fields:{},request_id:'test'}});}return {ok:true};});
 await press('Min trädgård');await press('Visa växt');await press('Redigera växt');await field('Namn','Mitt utkast');await press('Bekräfta och spara');assert.equal(calls.length,1);
 await press('Granska mot senaste underlaget');assert.match(text(),/Annan ändring/);assert.match(text(),/Mitt utkast/);assert.equal(calls.length,1);
 await press('Bekräfta och spara');assert.equal(calls[1].body!.revision,'v2');assert.notEqual(calls[1].key,calls[0].key);
 await act(async()=>root.unmount());
});
test('shopping undo refuses concurrent edits and local storage separates servers',()=>{
 const before:ShoppingRow[]=[],after=[{id:'1',name:'Jord',done:false,detail:''}];
 assert.deepEqual(undoShopping(after,before,after),[]);
 assert.throws(()=>undoShopping([...after,{...after[0],id:'2'}],before,after));
 const scope={account:'a',garden:'g',transport:{origin:'https://one.example'}} as any;
 assert.notEqual(localScopeKey(scope),localScopeKey({...scope,transport:{origin:'https://two.example'}}));
});

function careRule(id:string,title:string):Rule{return {id,title,instructions:'En tydlig instruktion för växten.',category:'Övrigt',cadence:'monthly',start_month:3,end_month:7,scope:'hela-växten',advice_kind:'on_demand',relevance_reason:'För växtens behov.',need_condition:'När jorden är torr',source_urls:[],work_id:id,conditional:true,evidence_conflict:false,identity_change_kind:'',identity_source_id:null,one_off_date:'',one_off_end:'',works:[],item:{id:'1',name:'Ros'}};}

test('active care excludes unselected advice and includes restored older rules',async()=>{
 const data=base(),chosen=careRule('1','Godkänt råd'),rejected=careRule('2','Ej godkänt råd'),restored=careRule('3','Återställt äldre råd');
 data.items[0].plan={id:'1',proposal_id:'1',version:1,status:'active',summary:'Plan',warnings:[],uncertainties:[],sources:[],rules:[chosen,rejected],comparison:null};
 data.items[0].current_rules=[chosen,restored];
 await mount(data,()=>({ok:true}));await press('Min trädgård');await press('Visa växt');
 assert.match(text(),/Godkänt råd/);assert.match(text(),/Återställt äldre råd/);assert.doesNotMatch(text(),/Ej godkänt råd/);
 assert.equal(root.root.findAll(n=>n.type==='button'&&n.props.accessibilityLabel==='Det behövs nu').length,2);
 await press('Överblick');await field('Sök i växter, uppgifter och råd','Ej godkänt');assert.doesNotMatch(text(),/En tydlig instruktion/);
 await act(async()=>root.unmount());
});

test('approval displays recurrence dates classification and need condition',async()=>{
 const data=base(),monthly=careRule('1','Månadsråd'),once={...careRule('2','Engångsråd'),advice_kind:'planned',cadence:'one_off',one_off_date:'2031-04-17',one_off_end:'2031-04-19',need_condition:''};
 data.proposals=[{id:'1',proposal_id:'1',version:1,status:'pending',summary:'Förslag',warnings:[],uncertainties:[],sources:[],rules:[monthly,once],comparison:{token:'comparison',context_changed:false,rows:[],removed:[]}}];
 const calls:Request[]=[];await mount(data,r=>{calls.push(r);return {ok:true};});await press('Skötselförslag (1)');
 for(const value of ['Vid behov','Varje månad i fönstret','Mars','Juli','När jorden är torr','Planerat arbete','Engångsarbete','2031-04-17','2031-04-19'])assert.ok(text().includes(value),value);
 assert.equal(calls.length,0);await act(async()=>root.unmount());
});

for(const action of ['Markera klar','Hoppa över','Återöppna'])test(`${action}: fresh task content is visible before conflict retry`,async()=>{
 const data=base(),calls:Request[]=[];
 const task:Task={id:'1',title:'Gammal rubrik',instructions:'Gammal instruktion',status:action==='Återöppna'?'completed':'pending',note:'',category:'Övrigt',start:data.today,end:data.today,item:{id:'1',name:'Ros'},area:null,sources:[],work_id:null,manual:true,archive_reason:'',completed_at:null,month:9};
 data.occurrences=[task];data.tasks={due:[task]};
 await mount(data,r=>{calls.push(r);if(calls.length===1){Object.assign(task,{title:'Ändrad rubrik',instructions:'Ny instruktion att granska',note:'Ny anteckning',start:'2031-03-04',end:'2031-03-07'});data.revision='v2';throw new ApiError(409,{error:{code:'version_conflict',message:'Ändrad',fields:{},request_id:'test'}});}return {ok:true};});
 await press('Visa uppgift');await press(action);await press('Bekräfta och spara');await press('Granska mot senaste underlaget');
 for(const value of ['Ändrad rubrik','Ny instruktion att granska','Ny anteckning','2031-03-04','2031-03-07'])assert.ok(text().includes(value),value);
 assert.equal(calls.length,1);await press('Bekräfta och spara');assert.equal(calls.length,2);assert.equal(calls[1].body!.revision,'v2');assert.notEqual(calls[0].key,calls[1].key);
 assert.deepEqual(calls[1].body!.values,{status:action==='Markera klar'?'completed':action==='Hoppa över'?'skipped':'pending'});
 await act(async()=>root.unmount());
});
