import test from 'node:test';
import assert from 'node:assert/strict';
import {DatabaseSync} from 'node:sqlite';
import {readFileSync} from 'node:fs';
import worker from '../dist/server/index.js';
class LocalD1 {
 constructor(){this.db=new DatabaseSync(':memory:');this.db.exec(readFileSync(new URL('../drizzle/0000_family.sql',import.meta.url),'utf8'));}
 prepare(sql){const db=this.db;return {bind(...values){const s=db.prepare(sql);return {async first(){return s.get(...values)||null;},async run(){const r=s.run(...values);return {success:true,meta:{changes:Number(r.changes)}};}};}};}
}
function context(){const env={DB:new LocalD1()};const call=async(path,owner,body,extra={})=>{
 const headers={'Content-Type':'application/json',...(owner?{'oai-authenticated-user-id':owner}:{}),...extra};
 const req=new Request('https://test.example'+path,{method:body===undefined?'GET':'POST',headers,...(body===undefined?{}:{body:typeof body==='string'?body:JSON.stringify(body)})});
 const response=await worker.fetch(req,env);return {status:response.status,data:await response.json()};
 };return {env,call};}
test('공개 페이지·설치 manifest·개인자료는 인증 필수',async()=>{
 const {env,call}=context();const response=await worker.fetch(new Request('https://test.example/'),env);
 assert.equal(response.status,200);assert.match(await response.text(),/또박또박/);assert.ok(response.headers.get('Content-Security-Policy'));
 assert.equal((await worker.fetch(new Request('https://test.example/manifest.webmanifest'),env)).status,200);
 assert.equal((await call('/api/data')).status,401);assert.equal((await call('/api/account')).data.loggedIn,false);
 assert.equal((await call('/api/account','owner-a')).data.loggedIn,true);
 for(const path of ['/api/result','/api/recognize'])assert.equal((await call(path,'owner-a',{})).status,404);
});
test('실제 SQLite에서 계정별 조회·저장 분리 및 클라이언트 소유자 위조 무시',async()=>{
 const {call}=context();const a=await call('/api/data','owner-a');assert.equal(a.data.revision,0);
 const saved=await call('/api/data','owner-a',{revision:0,owner_id:'owner-b',action:{type:'student.add',name:'가상 별명'}});
 assert.equal(saved.status,200);assert.equal(saved.data.data.students.length,1);
 const b=await call('/api/data?owner_id=owner-a','owner-b');assert.equal(b.data.data.students.length,0);
 const again=await call('/api/data','owner-a');assert.equal(again.data.data.students.length,1);
});
test('동시 저장과 오래된 버전은 409, 최신 데이터 보존',async()=>{
 const {call}=context();
 const [a,b]=await Promise.all([call('/api/data','owner',{revision:0,action:{type:'student.add',name:'첫째'}}),call('/api/data','owner',{revision:0,action:{type:'student.add',name:'둘째'}})]);
 assert.deepEqual([a.status,b.status].sort(),[200,409]);assert.equal((await call('/api/data','owner')).data.data.students.length,1);
 assert.equal((await call('/api/data','owner',{revision:0,action:{type:'account.clear'}})).status,409);
});
test('교차 사이트 요청·잘못된 JSON·과대 요청·잘못된 자료 거부',async()=>{
 const {call}=context();assert.equal((await call('/api/data','a',{revision:0,action:{type:'student.add',name:'가'}},{Origin:'https://other.example'})).status,403);
 assert.equal((await call('/api/data','a','not json')).status,400);
 assert.equal((await call('/api/data','a','x'.repeat(1000001))).status,413);
 assert.equal((await call('/api/data','a',{revision:0,action:{type:'student.add',name:' '}})).status,400);
 assert.equal((await call('/api/data','a',{revision:0,action:{type:'student.add',name:'가'}},{'Content-Type':'text/plain'})).status,415);
});
test('전체 학습 자료 삭제는 다른 계정에 영향 없음, 버전 단조 증가',async()=>{
 const {call}=context();await call('/api/data','a',{revision:0,action:{type:'student.add',name:'가'}});await call('/api/data','b',{revision:0,action:{type:'student.add',name:'나'}});
 const clear=await call('/api/data','a',{revision:1,action:{type:'account.clear'}});assert.equal(clear.status,200);assert.equal(clear.data.data.students.length,0);assert.equal(clear.data.revision,2);
 assert.equal((await call('/api/data','b')).data.data.students.length,1);
});
test('부모 확인 저장·백업 가져오기·기록 수정의 전체 API 흐름',async()=>{
 const {call}=context();let r=await call('/api/data','a',{revision:0,action:{type:'student.add',name:'가상 학생'}});const student=r.data.resultId;
 r=await call('/api/data','a',{revision:r.data.revision,action:{type:'record.add',id:'record-1',student_id:student,items:[{text:'안녕하세요.'}],outcomes:['wrong']}});assert.equal(r.status,200);
 r=await call('/api/data','a',{revision:r.data.revision,action:{type:'record.review',id:'record-1',outcomes:['correct']}});assert.equal(r.data.data.records[0].outcomes[0],'correct');
 const backup={format:'ttobak-backup',version:1,data:r.data.data};r=await call('/api/data','b',{revision:0,action:{type:'backup.import',backup}});assert.equal(r.status,200);assert.equal(r.data.data.records.length,1);
 assert.notEqual(r.data.data.students[0].id,student);
});

test('가족용 첫 연습은 별도 학생 등록 API 없이 서버에 원자적으로 저장',async()=>{
 const {call}=context();const saved=await call('/api/data','family-owner',{revision:0,action:{type:'record.add',id:'first-family-record',student_id:'family',items:[{text:'우리집에서 써요.'}],outcomes:['unchecked']}});
 assert.equal(saved.status,200);assert.equal(saved.data.data.students[0].name,'우리집');assert.equal(saved.data.data.records.length,1);
 assert.equal((await call('/api/data','other-owner')).data.data.records.length,0);
});

test('주차 묶음과 완료 기록이 실제 DB 왕복 후에도 보존되고 다른 계정과 분리',async()=>{
 const {call}=context();let data=await call('/api/data','learner');
 const items=data.data.data.prompts.map(p=>({...p,text:'이번 주 '+p.id}));
 let saved=await call('/api/data','learner',{revision:0,action:{type:'pack.save',id:'school-week',name:'학교 1주차',items}});assert.equal(saved.status,200);
 saved=await call('/api/data','learner',{revision:saved.data.revision,action:{type:'record.add',id:'study-complete',student_id:'family',items:[{text:'연습 문장'}],outcomes:['unchecked'],completed:true,kind:'review'}});assert.equal(saved.status,200);
 const reloaded=await call('/api/data','learner');assert.equal(reloaded.data.data.packs[0].name,'학교 1주차');assert.equal(reloaded.data.data.records[0].completed,true);assert.equal(reloaded.data.data.records[0].kind,'review');assert.deepEqual(reloaded.data.data.records[0].outcomes,['unchecked']);
 const other=await call('/api/data','another-learner');assert.deepEqual(other.data.data.packs,[]);assert.deepEqual(other.data.data.records,[]);
});
test('구버전 JSON 자료를 지우지 않고 새 묶음과 완료 필드를 추가',async()=>{
 const {call,env}=context();const old={students:[{id:'family',name:'우리집'}],prompts:Array.from({length:10},(_,i)=>({id:i+1,text:'예전 문장'})),records:[{id:'old',student_id:'family',created_at:'2026-01-01T00:00:00Z',items:[{text:'이전 학습'}],outcomes:['correct']}]};
 env.DB.db.prepare('INSERT INTO family_data(owner_id,document,revision) VALUES(?,?,?)').run('old-user',JSON.stringify(old),1);
 let r=await call('/api/data','old-user');assert.equal(r.data.data.records[0].completed,false);assert.deepEqual(r.data.data.packs,[]);
 r=await call('/api/data','old-user',{revision:1,action:{type:'pack.save',id:'new',name:'새 묶음',items:old.prompts}});assert.equal(r.status,200);assert.equal(r.data.data.records[0].items[0].text,'이전 학습');
});
