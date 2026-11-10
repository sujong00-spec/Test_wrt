import test from 'node:test';
import assert from 'node:assert/strict';
import {DataClient} from '../web/client.js';
import {initialData} from '../web/data.js';
function storage(){const data=new Map();return {getItem:k=>data.get(k)||null,setItem:(k,v)=>data.set(k,v)};}
test('비로그인은 브라우저 저장, 저장 실패 시 메모리의 기존 자료 유지',async()=>{
 const local=storage();const client=new DataClient(async()=>new Response(JSON.stringify({loggedIn:false})),local);await client.init();await client.change({type:'student.add',name:'기기 별명'});assert.equal(client.data.students.length,1);
 local.setItem=()=>{throw Error('full');};await assert.rejects(()=>client.change({type:'student.add',name:'실패'}),/저장하지 못/);assert.equal(client.data.students.length,1);
});
test('로그인 시 로컬 학생을 자동 업로드하지 않음',async()=>{
 const local=storage();const legacy=initialData();legacy.students=[{id:'local',name:'기기 학생'}];local.setItem('ttobak-mobile-v1',JSON.stringify(legacy));let writes=0;
 const client=new DataClient(async(path,opts)=>{if(opts.method==='POST')writes++;return new Response(JSON.stringify(path==='/api/account'?{loggedIn:true}:{data:initialData(),revision:0}));},local);
 await client.init();assert.equal(client.cloud,true);assert.equal(client.data.students.length,0);assert.equal(client.legacy().students.length,1);assert.equal(writes,0);
});
test('클라우드 409 실패가 화면의 기존 자료를 덮어쓰지 않음',async()=>{
 let initial=true;const client=new DataClient(async path=>path==='/api/account'?new Response('{"loggedIn":true}'):initial?new Response(JSON.stringify({data:initialData(),revision:0})):new Response('{"error":"새로고침 후 저장해 주세요."}',{status:409}),storage());await client.init();initial=false;
 await assert.rejects(()=>client.change({type:'student.add',name:'가'}),/새로고침/);assert.equal(client.data.students.length,0);assert.equal(client.revision,0);
});

test('브라우저 fetch는 전역 객체에 연결하여 Illegal invocation 방지',async()=>{
 const calls=[];
 function browserFetch(path,options){
  if(this!==globalThis)throw new TypeError('Illegal invocation');
  calls.push(path);
  if(path==='/api/account')return Promise.resolve(new Response('{"loggedIn":true}'));
  const data=initialData();
  if(options.method==='POST')data.students.push({id:'browser-student',name:'가상 학생'});
  return Promise.resolve(new Response(JSON.stringify({data,revision:options.method==='POST'?1:0,resultId:'browser-student'})));
 }
 const client=new DataClient(browserFetch,storage());
 await client.init();await client.change({type:'student.add',name:'가상 학생'});
 assert.deepEqual(calls,['/api/account','/api/data','/api/data']);assert.equal(client.data.students.length,1);
});
test('연결 예외는 기존 자료를 유지하고 인터넷 장애로 단정하지 않음',async()=>{
 const client=new DataClient(()=>{throw new TypeError('Failed to fetch');},storage());
 await assert.rejects(()=>client.init(),/서버 요청을 보내지 못/);assert.equal(client.data.students.length,0);
});
