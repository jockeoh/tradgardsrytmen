import { Edit, Field, Plant, Rule, Task, Workspace } from './types';
export const months=['Januari','Februari','Mars','April','Maj','Juni','Juli','Augusti','September','Oktober','November','December'];
export const statusLabel:Record<string,string>={pending:'Planerat',completed:'Utfört',skipped:'Överhoppat',archived:'Arkiverat'};
const choices=(values:string[])=>values.map(value=>({value,label:value}));
export function editFor(data:Workspace,command:string,target:string|null,values:Record<string,unknown>,title:string,fields:Field[],summary?:string):Edit {
 return {command,target,values,fields,title,context:data.context,revision:data.revision,summary};
}
export function plantEdit(data:Workspace,plant?:Plant):Edit {
 const fields:Field[]=[{key:'name',label:'Namn'},{key:'kind',label:'Typ',options:[{value:'individual',label:'Enskild växt'},{value:'group',label:'Grupp'},{value:'bed',label:'Odlingsbädd'}]},
 {key:'category',label:'Växttyp'},{key:'cultivar',label:'Sort'},{key:'quantity',label:'Antal',type:'number'},{key:'age_stage',label:'Ålder eller stadium'},
 {key:'canonical_name',label:'Botaniskt namn'},{key:'aliases',label:'Andra namn, ett per rad',type:'lines'},
 {key:'area_id',label:'Område',options:[{value:'',label:'Inte placerad'},...data.areas.map(a=>({value:a.id,label:a.name}))]},
 {key:'location_detail',label:'Platsdetalj'},{key:'notes',label:'Anteckningar',multiline:true}];
 const values:Record<string,unknown>={name:'',kind:'individual',category:'',cultivar:'',quantity:1,age_stage:'',canonical_name:'',aliases:[],area_id:'',location_detail:'',notes:''};
 if(plant)for(const f of fields)values[f.key]=(plant as unknown as Record<string,unknown>)[f.key]??'';
 return editFor(data,plant?'plant.update':'plant.create',plant?.id??null,values,plant?'Redigera växt':'Lägg till växt',fields);
}
export function taskEdit(data:Workspace,task?:Task,plant?:string):Edit {
 const fields:Field[]=[{key:'title',label:'Uppgift'},{key:'category',label:'Arbetskategori',options:choices(data.work_categories)},{key:'instructions',label:'Instruktion',multiline:true}];
 if(!task)fields.push({key:'item_id',label:'Växt',options:data.items.map(p=>({value:p.id,label:p.name}))},{key:'window_start',label:'Från (ÅÅÅÅ-MM-DD)'},{key:'window_end',label:'Till (ÅÅÅÅ-MM-DD)'});
 else fields.push({key:'note',label:'Anteckning',multiline:true});
 return editFor(data,task?'task.update':'task.create',task?.id??null,task?{title:task.title,category:task.category,instructions:task.instructions,note:task.note}:
 {title:'',category:data.work_categories[0]??'Övrigt',instructions:'',item_id:plant??data.items[0]?.id??'',window_start:data.today,window_end:data.today},task?'Redigera uppgift':'Egen uppgift',fields);
}
export function ruleEdit(data:Workspace,rule:Rule):Edit {
 const fields:Field[]=[{key:'title',label:'Råd'},{key:'category',label:'Arbetskategori',options:choices(data.work_categories)},
 {key:'advice_kind',label:'Rådstyp',options:[{value:'planned',label:'Planerat'},{value:'on_demand',label:'Vid behov'},{value:'general',label:'Allmänt råd'}]},
 {key:'instructions',label:'Instruktion',multiline:true},{key:'relevance_reason',label:'Varför rådet behövs',multiline:true},{key:'need_condition',label:'När behovet uppstår'},
 {key:'cadence',label:'Återkomst',options:[{value:'seasonal',label:'En gång per säsong'},{value:'monthly',label:'Varje månad'},{value:'one_off',label:'På angivna datum'}]},
 {key:'start_month',label:'Från månad (1–12)',type:'number'},{key:'end_month',label:'Till månad (1–12)',type:'number'},
 {key:'one_off_date',label:'Engångsarbete från (ÅÅÅÅ-MM-DD)'},{key:'one_off_end',label:'Engångsarbete till (ÅÅÅÅ-MM-DD)'},
 {key:'identity_mode',label:'Koppling till tidigare arbete',options:[{value:'existing',label:'Samma arbete'},{value:'refine',label:'Förtydliga undergruppen'},{value:'merge',label:'Slå ihop med valt arbete'},{value:'new',label:'Nytt arbete'}]},
 {key:'work_id',label:'Tidigare arbete',options:rule.works.map(w=>({value:w.id,label:`${w.title} · ${w.scope}`}))},
 {key:'scope',label:'Undergrupp'},{key:'source_urls',label:'Källor, en länk per rad',type:'lines'},{key:'evidence_conflict',label:'Källorna säger olika',type:'boolean'}];
 const values:Record<string,unknown>={};for(const field of fields)values[field.key]=(rule as unknown as Record<string,unknown>)[field.key]??'';
 values.identity_mode=rule.identity_change_kind||'existing';values.work_id=rule.identity_change_kind==='refine'?(rule.identity_source_id||rule.work_id):rule.work_id;
 return editFor(data,'rule.update',rule.id,values,'Redigera skötselförslag',fields);
}
export function editBody(edit:Edit) {
 const values={...edit.values};
 if(edit.command==='rule.update'){values.conditional=values.advice_kind==='on_demand';if(values.identity_mode==='new')delete values.work_id;}
 return {command:edit.command,target:edit.target,values,context:edit.context,revision:edit.revision};
}
export function soil(shape:'bed'|'pot',length:number,width:number,diameter:number,depth:number,bag:number){
 const dims=shape==='pot'?[diameter,depth,bag]:[length,width,depth,bag];
 if(dims.some(v=>!Number.isFinite(v)||v<=0))return null;
 const liters=(shape==='pot'?Math.PI*(diameter/2)**2*depth:length*width*depth)/1000;
 return Number.isFinite(liters)?{liters,bags:Math.ceil(liters/bag)}:null;
}
export function inMonth(task:Task,year:number,month:number){
 if(task.calendar_visible===false)return false;
 if(task.status&&task.status!=='pending')return !!task.happened_on&&task.happened_on.startsWith(`${year}-${String(month).padStart(2,'0')}-`);
 const first=`${year}-${String(month).padStart(2,'0')}-01`;
 const last=`${year}-${String(month).padStart(2,'0')}-${new Date(year,month,0).getDate()}`;
 return task.start<=last&&task.end>=first;
}
