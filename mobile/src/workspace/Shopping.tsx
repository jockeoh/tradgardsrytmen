import { useEffect, useRef, useState } from 'react';
import { Text, View } from 'react-native';
import { randomUUID } from 'expo-crypto';
import { Button, Field, styles } from '../ui/common';
import { journalStore } from '../core/storage';
import { ShoppingRow } from './types';
import { undoShopping } from './local';
import { soil } from './domain';
export function Shopping({storageKey}:{storageKey:string}){
 const [rows,setRows]=useState<ShoppingRow[]>([]),[loaded,setLoaded]=useState(false),[error,setError]=useState(''),[name,setName]=useState('');
 const [undo,setUndo]=useState<{before:ShoppingRow[];after:ShoppingRow[]}|null>(null),[busy,setBusy]=useState(false);
 const [shape,setShape]=useState<'bed'|'pot'>('bed'),[length,setLength]=useState('120'),[width,setWidth]=useState('80'),[diameter,setDiameter]=useState('40'),[depth,setDepth]=useState('20'),[bag,setBag]=useState('40');
 const alive=useRef(true),writing=useRef(false);
 useEffect(()=>{alive.current=true;journalStore.getItem(storageKey).then(raw=>{if(alive.current){setRows(raw?JSON.parse(raw):[]);setLoaded(true);}}).catch(()=>{if(alive.current)setError('Listan kunde inte läsas. Befintliga data behålls.');});return()=>{alive.current=false;};},[storageKey]);
 async function change(update:(old:ShoppingRow[])=>ShoppingRow[],isUndo=false){
  if(!loaded||writing.current)return false;writing.current=true;setBusy(true);setError('');
  try{
   const work=async()=>{const raw=await journalStore.getItem(storageKey),before:ShoppingRow[]=raw?JSON.parse(raw):[],next=update(before);await journalStore.setItem(storageKey,JSON.stringify(next));if(alive.current){setRows(next);setUndo(isUndo?null:{before,after:next});}};
   if(journalStore.withLock)await journalStore.withLock(storageKey,work);else await work();
   return true;
  }catch(e){if(alive.current)setError(e instanceof Error?e.message:'Listan kunde inte sparas. Försök igen.');return false;}finally{writing.current=false;if(alive.current)setBusy(false);}
 }
 const result=soil(shape,Number(length),Number(width),Number(diameter),Number(depth),Number(bag));
 return <View style={{gap:18}}>
  <Text style={styles.title}>Inköpslista</Text><Text style={styles.muted}>Sparas på den här enheten för din trädgård.</Text>
  <Field label="Lägg till" value={name} onChange={setName}/><Button title="Lägg till i listan" disabled={!loaded||busy||!name.trim()} onPress={()=>{const value=name.trim();void change(old=>[...old,{id:randomUUID(),name:value,detail:'',done:false}]).then(saved=>{if(saved&&alive.current)setName(current=>current.trim()===value?'':current);});}}/>
  {rows.map(row=><View key={row.id} style={styles.card}><Text style={styles.text}>{row.done?'✓ ':''}{row.name}</Text>{!!row.detail&&<Text style={styles.muted}>{row.detail}</Text>}<View style={styles.row}><Button title={row.done?'Återställ':'Inköpt'} secondary disabled={busy} onPress={()=>void change(old=>old.map(r=>r.id===row.id?{...r,done:!r.done}:r))}/><Button title="Ta bort" secondary disabled={busy} onPress={()=>void change(old=>old.filter(r=>r.id!==row.id))}/></View></View>)}
  {!!undo&&<Button title="Ångra senaste ändringen" secondary disabled={busy} onPress={()=>void change(old=>undoShopping(old,undo.before,undo.after),true)}/>}
  {!!error&&<Text accessibilityRole="alert" style={styles.text}>{error}</Text>}
  <View style={styles.card}><Text style={styles.label}>Beräkna jord</Text><View style={styles.row}><Button title="Rabatt eller pallkrage" secondary={shape!=='bed'} onPress={()=>setShape('bed')}/><Button title="Rund kruka" secondary={shape!=='pot'} onPress={()=>setShape('pot')}/></View>
  {shape==='bed'?<><Field label="Längd (cm)" value={length} onChange={setLength}/><Field label="Bredd (cm)" value={width} onChange={setWidth}/></>:<Field label="Diameter (cm)" value={diameter} onChange={setDiameter}/>}
  <Field label="Djup (cm)" value={depth} onChange={setDepth}/><Field label="Säckstorlek (liter)" value={bag} onChange={setBag}/>
  {result?<><Text style={styles.text}>{result.liters.toLocaleString('sv-SE',{maximumFractionDigits:1})} liter · {result.bags} säckar à {bag} liter</Text><Button title="Lägg jord i inköpslistan" disabled={busy||!loaded} onPress={()=>void change(old=>[...old,{id:randomUUID(),name:'Jord',detail:`${result.bags} säckar à ${bag} liter`,done:false}])}/></>:<Text style={styles.muted}>Ange positiva mått.</Text>}</View>
 </View>;
}
