import {test} from 'node:test';
import assert from 'node:assert/strict';
import { soil,inMonth,editBody } from '../src/workspace/domain';
import {Edit,Task} from '../src/workspace/types';
test('soil calculation supports bed and round pot; rejects zero/nonfinite dimensions',()=>{
 assert.deepEqual(soil('bed',120,80,0,20,40),{liters:192,bags:5});
 assert.ok(Math.abs(soil('pot',0,0,40,20,40)!.liters-25.132741)<0.0001);
 assert.equal(soil('bed',0,80,0,20,40),null);assert.equal(soil('pot',0,0,40,Infinity,40),null);
});
test('year view includes windows crossing month and year boundaries',()=>{
 const task={start:'2026-12-15',end:'2027-02-03'} as Task;
 assert.equal(inMonth(task,2027,1),true);assert.equal(inMonth(task,2027,3),false);assert.equal(inMonth(task,2026,12),true);
});
test('editor freezes original context/revision and preserves explicitly emptied values',()=>{
 const e:Edit={title:'Växt',command:'plant.update',target:'3',values:{notes:''},context:'original-grant',revision:'original',fields:[]};
 assert.deepEqual(editBody(e),{command:'plant.update',target:'3',values:{notes:''},context:'original-grant',revision:'original'});
});
test('rule edit derives conditional from explicit advice classification',()=>{
 const e:Edit={title:'Råd',command:'rule.update',target:'1',values:{advice_kind:'on_demand'},context:'grant',revision:'v',fields:[]};
 assert.equal(editBody(e).values.conditional,true);assert.equal(Object.hasOwn(e.values,'conditional'),false);
});
test('calendar places completed work by actual completion and hides excluded pending work',()=>{
 const task={start:'2026-01-01',end:'2026-01-31',status:'completed',happened_on:'2026-02-03'} as Task;
 assert.equal(inMonth(task,2026,1),false);assert.equal(inMonth(task,2026,2),true);
 assert.equal(inMonth({...task,status:'pending',calendar_visible:false},2026,1),false);
});
