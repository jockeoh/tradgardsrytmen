import './register.mjs';
import {test} from 'node:test';
import assert from 'node:assert/strict';
import React, {useState} from 'react';
import {act,create,ReactTestRenderer} from 'react-test-renderer';
import {Shopping} from '../src/workspace/Shopping';
import {Editor} from '../src/workspace/Editor';
import {journalStore} from '../src/core/storage';
import {KeyValueStore} from '../src/core/journal';
import {Edit,ShoppingRow} from '../src/workspace/types';
import {decimalNumber,editBody,soil} from '../src/workspace/domain';
import {readShopping,updateShopping} from '../src/workspace/local';

const input=(root:ReactTestRenderer,label:string)=>root.root.findAll(n=>n.type==='input').find(n=>n.props.accessibilityLabel===label)!;
const button=(root:ReactTestRenderer,label:string)=>root.root.findAll(n=>n.type==='button').find(n=>n.props.accessibilityLabel===label)!;
const visibleText=(root:ReactTestRenderer)=>root.root.findAll(n=>String(n.type)==='Text').map(n=>n.children.join('')).join('\n');
async function field(root:ReactTestRenderer,label:string,value:string){await act(async()=>{input(root,label).props.onChangeText(value);});}
async function press(root:ReactTestRenderer,label:string){await act(async()=>{const b=button(root,label);assert.ok(b,label);assert.notEqual(b.props.disabled,true);b.props.onPress();});}
async function mount(key:string){let root!:ReactTestRenderer;await act(async()=>{root=create(React.createElement(Shopping,{storageKey:key}));});return root;}
const row=(name:string):ShoppingRow=>({id:name,name,detail:'',done:false});

for(const [key,label,text] of [
 ['aliases','Andra namn, ett per rad','Provnamn A\nProvnamn B'],
 ['source_urls','Källor, en länk per rad','https://example.org/ett\nhttps://example.org/tva'],
])test(`F05: ${key} preserves each typed newline until submission`,async()=>{
 let current:Edit={command:key==='aliases'?'plant.update':'rule.update',target:'1',title:'Redigera',context:'grant',revision:'v1',values:{[key]:[]},fields:[{key,label,type:'lines'}]};
 function Harness(){const [edit,setEdit]=useState(current);current=edit;return React.createElement(Editor,{edit,change:setEdit,save:()=>{},close:()=>{},locked:false,busy:false,review:false,rebase:()=>{},reconcile:()=>{}});}
 let root!:ReactTestRenderer;await act(async()=>{root=create(React.createElement(Harness));});
 try{
  for(let i=1;i<=text.length;i++){
   await field(root,label,text.slice(0,i));
   assert.equal(input(root,label).props.value,text.slice(0,i));
  }
  await field(root,label,`${text}\n\n`);
  assert.equal(input(root,label).props.value,`${text}\n\n`);
  assert.deepEqual(editBody(current).values[key],text.split('\n'));
  assert.deepEqual(current.values[key],[...text.split('\n'),'',''],'saving must not trim the draft');
 }finally{await act(async()=>root.unmount());}
});

test('F06: Swedish decimals work for soil dimensions and bag sizes, with invalid input rejected',async()=>{
 for(const value of ['2,5','2.5',' 2,5 '])assert.equal(decimalNumber(value),2.5);
 for(const value of ['',' ','2,5.0','2,5,0','Infinity','0x20','1e3'])assert.ok(Number.isNaN(decimalNumber(value)),value);
 assert.equal(soil('bed',120,80,0,decimalNumber('-2,5'),40),null);
 const root=await mount('decimal-regression');
 try{
  for(const depth of ['2,5','2.5']){await field(root,'Djup (cm)',depth);assert.match(visibleText(root),/24 liter/);}
  await field(root,'Längd (cm)','120,5');await field(root,'Bredd (cm)','80,5');await field(root,'Säckstorlek (liter)','2,5');
  assert.match(visibleText(root),/24,3 liter · 10 säckar à 2,5 liter/);
  await press(root,'Rund kruka');await field(root,'Diameter (cm)','40,5');
  assert.match(visibleText(root),/3,2 liter · 2 säckar à 2,5 liter/);
  await field(root,'Säckstorlek (liter)','0');assert.match(visibleText(root),/Ange positiva mått/);
 }finally{await act(async()=>root.unmount());}
});

test('F08: remounted shopping waits for an old delayed write and retains both additions',async()=>{
 const key='shopping-remount-regression',originalSet=journalStore.setItem.bind(journalStore);
 let release:(()=>void)|undefined,held=false;
 let first:ReactTestRenderer|undefined,second:ReactTestRenderer|undefined,third:ReactTestRenderer|undefined;
 journalStore.setItem=async(k,v)=>{
  if(k===key&&!held){held=true;await new Promise<void>(resolve=>{release=resolve;});}
  await originalSet(k,v);
 };
 try{
  first=await mount(key);await field(first,'Lägg till','Jord');await press(first,'Lägg till i listan');
  assert.ok(release,'old write is in flight');
  await act(async()=>first!.unmount());first=undefined;
  second=await mount(key);await field(second,'Lägg till','Frön');
  assert.equal(button(second,'Lägg till i listan').props.disabled,true,'a fresh screen must not read a stale list during the old write');
  await act(async()=>{release!();});
  assert.match(visibleText(second),/Jord/);
  await press(second,'Lägg till i listan');
  assert.deepEqual(JSON.parse((await journalStore.getItem(key))!).map((r:ShoppingRow)=>r.name),['Jord','Frön']);
  await act(async()=>second!.unmount());second=undefined;
  third=await mount(key);assert.match(visibleText(third),/Jord/);assert.match(visibleText(third),/Frön/);
 }finally{
  release?.();journalStore.setItem=originalSet;
  await act(async()=>{first?.unmount();second?.unmount();third?.unmount();});
 }
});

test('F08: queued changes reread after the prior write and failures release the shared list queue',async()=>{
 const values=new Map<string,string>();let release!:()=>void,writes=0,reads=0;
 const store:KeyValueStore={
  async getItem(key){reads++;return values.get(key)??null;},
  async setItem(key,value){if(++writes===1)await new Promise<void>(resolve=>{release=resolve;});values.set(key,value);},
  async removeItem(key){values.delete(key);},async getAllKeys(){return [...values.keys()];},
 };
 const first=updateShopping(store,'list',old=>[...old,row('Jord')]);
 await new Promise(resolve=>setImmediate(resolve));
 const second=updateShopping(store,'list',old=>[...old,row('Frön')]);
 await new Promise(resolve=>setImmediate(resolve));
 try{assert.equal(reads,1);assert.equal(writes,1);}finally{release();}
 await Promise.all([first,second]);
 assert.deepEqual((await readShopping(store,'list')).map(r=>r.name),['Jord','Frön']);
 const write=store.setItem;store.setItem=async()=>{throw new Error('storage failed');};
 await assert.rejects(updateShopping(store,'list',old=>[...old,row('Oskriven')]),/storage failed/);
 store.setItem=write;
 await updateShopping(store,'list',old=>[...old,row('Kruka')]);
 assert.deepEqual((await readShopping(store,'list')).map(r=>r.name),['Jord','Frön','Kruka']);
});

test('F08: changing garden during a delayed write keeps both lists and the new view separate',async()=>{
 const firstKey='shopping-garden-a',secondKey='shopping-garden-b';
 const originalSet=journalStore.setItem.bind(journalStore);let release:(()=>void)|undefined;
 journalStore.setItem=async(k,v)=>{if(k===firstKey)await new Promise<void>(resolve=>{release=resolve;});await originalSet(k,v);};
 const root=await mount(firstKey);
 try{
  await field(root,'Lägg till','Jord');await press(root,'Lägg till i listan');assert.ok(release);
  await act(async()=>root.update(React.createElement(Shopping,{storageKey:secondKey})));
  await field(root,'Lägg till','Frön');await press(root,'Lägg till i listan');
  await act(async()=>{release!();});
  assert.match(visibleText(root),/Frön/);assert.doesNotMatch(visibleText(root),/Jord/);
  assert.deepEqual(JSON.parse((await journalStore.getItem(firstKey))!).map((r:ShoppingRow)=>r.name),['Jord']);
  assert.deepEqual(JSON.parse((await journalStore.getItem(secondKey))!).map((r:ShoppingRow)=>r.name),['Frön']);
 }finally{release?.();journalStore.setItem=originalSet;await act(async()=>root.unmount());}
});
