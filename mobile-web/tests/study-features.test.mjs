import test from 'node:test';
import assert from 'node:assert/strict';
import {initialData,changeData,validateData,makeBackup,backupData,reviewWarmup,stickerDays,FAMILY_ID} from '../web/data.js';
let i=0;const uuid=()=>`study-${++i}`;
function record(data,recordId,outcomes=['unchecked'],completed=false){return changeData(data,{type:'record.add',id:recordId,student_id:FAMILY_ID,items:outcomes.map((_,index)=>({text:`문장 ${index}`})),outcomes,completed}).data;}
test('주차별 문제 묶음 저장·수정·불러오기·삭제는 과거 기록 사본 보존',()=>{
 let data=record(initialData(),'history');const snapshot=JSON.stringify(data.records);
 const first=data.prompts.map(p=>({...p,text:`1주차 ${p.id}번`})),second=data.prompts.map(p=>({...p,text:`2주차 ${p.id}번`}));
 data=changeData(data,{type:'pack.save',id:'week1',name:'학교 1주차',items:first}).data;assert.deepEqual(data.prompts,first);
 data=changeData(data,{type:'pack.save',id:'week2',name:'학교 2주차',items:second}).data;assert.equal(data.packs.length,2);
 data=changeData(data,{type:'pack.save',id:'week1',name:'1주차 수정',items:first}).data;assert.equal(data.packs.length,2);
 data=changeData(data,{type:'pack.load',id:'week2'}).data;assert.deepEqual(data.prompts,second);assert.equal(JSON.stringify(data.records),snapshot);
 data=changeData(data,{type:'pack.delete',id:'week2'}).data;assert.equal(data.packs.length,1);assert.deepEqual(data.prompts,second);
});
test('묶음은 10문장 형식·이름·개수 제한, 실패 시 기존 자료 유지',()=>{
 const data=initialData(),before=JSON.stringify(data);
 assert.throws(()=>changeData(data,{type:'pack.save',id:'a',name:'',items:data.prompts}),/묶음 이름/);
 assert.throws(()=>changeData(data,{type:'pack.save',id:'a',name:'가',items:[]}),/10/);
 assert.throws(()=>changeData(data,{type:'pack.load',id:'missing'}),/묶음/);assert.equal(JSON.stringify(data),before);
 const tooMany={...data,packs:Array.from({length:51},(_,n)=>({id:String(n),name:'가',items:data.prompts}))};assert.throws(()=>validateData(tooMany),/50/);
});
test('새 묶음 포함 백업 왕복과 구버전 자료 호환',()=>{
 let data=changeData(initialData(),{type:'pack.save',id:'week1',name:'1주차',items:initialData().prompts}).data;
 assert.deepEqual(backupData(makeBackup(data)),data);
 const old=JSON.parse(JSON.stringify(data));delete old.packs;assert.deepEqual(validateData(old).packs,[]);
 const imported=changeData(data,{type:'backup.import',backup:makeBackup(data)},uuid).data;assert.equal(imported.packs.length,2);assert.notEqual(imported.packs[0].id,imported.packs[1].id);
});
test('오답 복습은 부모 확인한 오답 중 최대 3개만, 오늘 문제 보존',()=>{
 let data=record(initialData(),'wrong',['wrong','wrong','wrong','wrong','correct','unchecked']);const prompts=JSON.stringify(data.prompts);
 const items=reviewWarmup(data);assert.equal(items.length,3);assert.ok(items.every(x=>x.student_id===FAMILY_ID));assert.equal(JSON.stringify(data.prompts),prompts);
 data=changeData(data,{type:'record.review',id:'wrong',outcomes:['correct','correct','correct','correct','correct','unchecked']}).data;assert.equal(reviewWarmup(data).length,0);
});
test('완료 스티커는 정답 여부가 아닌 실제 완료 표시로 하루 한 개',()=>{
 let data=record(initialData(),'unfinished',['correct'],false);assert.equal(stickerDays(data).length,0);
 data=record(data,'finished',['unchecked'],true);assert.equal(stickerDays(data).length,1);assert.deepEqual(data.records[1].outcomes,['unchecked']);
 data=record(data,'finished-again',['wrong'],true);assert.equal(stickerDays(data).length,1);
 const old={...data,records:[{...data.records[0]}]};delete old.records[0].completed;delete old.records[0].completed_at;assert.equal(stickerDays(validateData(old)).length,0);
 assert.throws(()=>record(initialData(),'invalid',['unchecked'],'yes'),/완료/);
});
test('기록 저장 후 완료를 표시해도 기록과 스티커가 중복 생성되지 않음',()=>{
 let data=record(initialData(),'later');data=changeData(data,{type:'record.complete',id:'later'}).data;const at=data.records[0].completed_at;
 data=changeData(data,{type:'record.complete',id:'later'}).data;assert.equal(data.records.length,1);assert.equal(data.records[0].completed_at,at);assert.equal(stickerDays(data).length,1);
});
