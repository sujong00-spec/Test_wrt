import test from 'node:test';
import assert from 'node:assert/strict';
import {initialData,validateData,changeData,makeBackup,backupData,wrongbook} from '../web/data.js';
let next=0;const uuid=()=>`fake-${++next}`;
function add(data,name='가상 학생'){return changeData(data,{type:'student.add',name},uuid).data;}
test('기본 10문장과 부모 확인 전 미확인 상태',()=>{
 let data=add(initialData());assert.equal(data.prompts.length,10);
 data=changeData(data,{type:'record.add',id:'r1',student_id:data.students[0].id,items:[{text:'종이에 써요.'}],outcomes:['unchecked']},uuid).data;
 assert.equal(data.records[0].source,'parent');assert.equal(wrongbook(data,data.students[0].id).length,0);
});
test('학생 분리, 과거 문장 사본, 재확인 시 오답 해결',()=>{
 let data=add(add(initialData()));const a=data.students[0].id,b=data.students[1].id;
 data=changeData(data,{type:'record.add',id:'r2',student_id:a,items:[{text:'같은 문장'}],outcomes:['wrong']},uuid).data;
 assert.equal(wrongbook(data,a).length,1);assert.equal(wrongbook(data,b).length,0);
 data=changeData(data,{type:'prompts.save',items:data.prompts.map(p=>({...p,text:'새 문장'}))},uuid).data;
 assert.equal(data.records[0].items[0].text,'같은 문장');
 data=changeData(data,{type:'record.review',id:'r2',outcomes:['correct']},uuid).data;
 assert.equal(wrongbook(data,a).length,0);
});
test('학생 이름 수정 및 삭제는 해당 학생 기록만 삭제',()=>{
 let data=add(add(initialData()));const a=data.students[0].id;
 data=changeData(data,{type:'student.rename',id:a,name:'새 별명'},uuid).data;assert.equal(data.students[0].name,'새 별명');
 data=changeData(data,{type:'record.add',id:'delete-r',student_id:a,items:[{text:'가'}],outcomes:['wrong']},uuid).data;
 data=changeData(data,{type:'student.delete',id:a},uuid).data;assert.equal(data.students.length,1);assert.equal(data.records.length,0);
});
test('동일 요청 재시도는 중복 기록 없음',()=>{
 let data=add(initialData());const action={type:'record.add',id:'same-r',student_id:data.students[0].id,items:[{text:'가'}],outcomes:['correct']};
 data=changeData(data,action,uuid).data;data=changeData(data,action,uuid).data;assert.equal(data.records.length,1);
});
test('백업 왕복·기존 자료 유지·기존 숫자 ID 가져오기',()=>{
 const legacy={students:[{id:1,name:'가상 별명'}],prompts:initialData().prompts,records:[{id:2,student_id:1,created_at:'2026-01-01T00:00:00Z',items:[{text:'연습'}],outcomes:['wrong']}]};
 const imported=backupData(legacy);assert.equal(imported.students[0].id,'1');assert.deepEqual(backupData(makeBackup(imported)),imported);
 const data=changeData(add(initialData()),{type:'backup.import',backup:makeBackup(imported)},uuid).data;
 assert.equal(data.students.length,2);assert.equal(data.records.length,1);assert.equal(data.records[0].student_id,data.students[1].id);
 assert.throws(()=>backupData({format:'ttobak-backup',version:99,data:legacy}),/버전/);
});
test('오류·외부 ID·잘못된 확인 결과·용량 제한',()=>{
 let data=add(initialData());assert.throws(()=>changeData(data,{type:'student.add',name:' '},uuid),/별명/);
 assert.throws(()=>changeData(data,{type:'record.add',id:'bad',student_id:'missing',items:[{text:'가'}],outcomes:['correct']},uuid),/학생/);
 assert.throws(()=>changeData(data,{type:'record.add',id:'bad',student_id:data.students[0].id,items:[{text:'가'}],outcomes:['AI-correct']},uuid),/확인/);
 const duplicate=initialData();duplicate.prompts[1].id=1;assert.throws(()=>validateData(duplicate),/중복/);
 const tooMany=initialData();tooMany.students=Array.from({length:31},(_,i)=>({id:String(i),name:'가'}));assert.throws(()=>validateData(tooMany),/30/);
 const snapshot=JSON.stringify(data);assert.throws(()=>changeData(data,{type:'prompts.save',items:[]},uuid));assert.equal(JSON.stringify(data),snapshot);
});
