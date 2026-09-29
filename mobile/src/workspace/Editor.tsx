import { Switch, Text, View } from 'react-native';
import { Button, Field, styles } from '../ui/common';
import { statusLabel } from './domain';
import { Edit, Field as EditField } from './types';
export function Editor({edit,change,save,close,locked,busy,error,review,rebase,reconcile}:{edit:Edit;change:(e:Edit)=>void;save:()=>void;close:()=>void;locked:boolean;busy:boolean;error?:string;review:boolean;rebase:()=>void;reconcile:()=>void}){
 const latestFields:EditField[]=edit.command==='task.update'
  ? [{key:'title',label:'Uppgift'},{key:'instructions',label:'Instruktion'},{key:'start',label:'Från'},{key:'end',label:'Till'},{key:'category',label:'Arbetskategori'},{key:'note',label:'Anteckning'}]
  : edit.fields;
 function set(key:string,value:unknown){change({...edit,values:{...edit.values,[key]:value}});}
 return <View style={styles.card}>
  <Text style={styles.title}>{edit.title}</Text>
  {!!edit.summary&&<Text style={styles.text}>{edit.summary}</Text>}
  {edit.latest&&<View style={styles.card}><Text style={styles.label}>Senast sparat på servern</Text>{typeof edit.latest.status==='string'&&<Text style={styles.text}>Status: {statusLabel[edit.latest.status]??edit.latest.status}</Text>}{latestFields.filter(f=>Object.hasOwn(edit.latest!,f.key)).map(f=><Text key={f.key} style={styles.muted}>{f.label}: {f.options?.find(o=>o.value===String(edit.latest![f.key]))?.label??String(edit.latest![f.key]??'')}</Text>)}</View>}
  {edit.fields.map(field=><View key={field.key} style={{gap:8}}>
   {field.type==='boolean'?<View style={styles.row}><Text style={styles.text}>{field.label}</Text><Switch accessibilityLabel={field.label} disabled={locked||busy} value={edit.values[field.key]===true} onValueChange={v=>set(field.key,v)}/></View>:
   field.options?<><Text style={styles.label}>{field.label}</Text><View style={styles.row}>{field.options.map(option=><Button key={option.value} title={option.label} secondary={String(edit.values[field.key]??'')!==option.value} disabled={locked||busy} onPress={()=>set(field.key,option.value)}/>)}</View></>:
   <Field label={field.label} multiline={field.multiline||field.type==='lines'} disabled={locked||busy} value={field.type==='lines'?(edit.values[field.key] as string[]??[]).join('\n'):String(edit.values[field.key]??'')} onChange={value=>set(field.key,field.type==='number'?(value===''?'':Number(value)):field.type==='lines'?value.split('\n').filter(Boolean):value)}/>}
  </View>)}
  {!!error&&<Text accessibilityRole="alert" style={styles.text}>{error}</Text>}
  {review?<><Text style={styles.text}>Underlaget har ändrats. Dina ändringar finns kvar.</Text><Button title="Granska mot senaste underlaget" onPress={rebase}/></>:
  <Button title={busy?'Sparar…':locked?'Skicka samma sparning igen':'Bekräfta och spara'} disabled={busy} onPress={save}/>}
  {locked&&<Button title="Kontrollera om sparningen är klar" secondary disabled={busy} onPress={reconcile}/>}
  <Button title="Tillbaka" secondary disabled={busy} onPress={close}/>
 </View>;
}
