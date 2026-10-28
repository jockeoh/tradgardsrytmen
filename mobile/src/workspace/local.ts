import { Scope } from '../core/session';
import { KeyValueStore } from '../core/journal';
import { ShoppingRow } from './types';

// A list's read/modify/write operation outlives the screen that started it.
// Native SQLite calls are asynchronous; queue the whole operation, not just its
// final write. Browser locks additionally coordinate other tabs.
const shoppingQueues=new WeakMap<KeyValueStore,Map<string,Promise<void>>>();
function withShoppingLock<T>(store:KeyValueStore,key:string,work:()=>Promise<T>):Promise<T>{
 let queues=shoppingQueues.get(store);
 if(!queues){queues=new Map();shoppingQueues.set(store,queues);}
 const result=(queues.get(key)??Promise.resolve()).then(()=>store.withLock?store.withLock(key,work):work());
 const tail=result.then(()=>{},()=>{});
 queues.set(key,tail);
 void tail.then(()=>{if(queues.get(key)===tail)queues.delete(key);});
 return result;
}
export function readShopping(store:KeyValueStore,key:string):Promise<ShoppingRow[]>{
 return withShoppingLock(store,key,async()=>{
  const raw=await store.getItem(key);
  return raw?JSON.parse(raw):[];
 });
}
export function updateShopping(store:KeyValueStore,key:string,update:(rows:ShoppingRow[])=>ShoppingRow[]){
 return withShoppingLock(store,key,async()=>{
  const raw=await store.getItem(key),before:ShoppingRow[]=raw?JSON.parse(raw):[],after=update(before);
  await store.setItem(key,JSON.stringify(after));
  return {before,after};
 });
}

export function localScopeKey(scope: Scope) {
  const origin = 'origin' in scope.transport ? scope.transport.origin : 'synthetic';
  return JSON.stringify([origin, scope.account, scope.garden]);
}

export function undoShopping(current: ShoppingRow[], before: ShoppingRow[], after: ShoppingRow[]) {
  if (JSON.stringify(current) !== JSON.stringify(after))
    throw new Error('Listan har ändrats sedan dess. Uppdatera listan innan du ändrar den igen.');
  return before;
}
