import {initialData,validateData,changeData,InputError} from '../web/data.js';
export function json(data,status=200){return new Response(JSON.stringify(data),{status,headers:{'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Vary':'Cookie'}});}
export async function api(request,env){
 const url=new URL(request.url),path=url.pathname;
 const owner=request.headers.get('oai-authenticated-user-id');
 if(path==='/api/account'&&request.method==='GET')return json({loggedIn:!!owner,version:'1.2.0'});
 if(path!=='/api/data')return json({error:'요청한 기능이 없습니다.'},404);
 if(!owner)return json({error:'기록을 동기화하려면 보호자 계정으로 로그인해 주세요.'},401);
 if(!env.DB)return json({error:'저장소를 준비 중입니다. 잠시 후 다시 시도해 주세요.'},503);
 if(!['GET','POST'].includes(request.method))return json({error:'지원하지 않는 요청입니다.'},405);
 if(request.method==='POST'){
  const origin=request.headers.get('origin');
  if((origin&&origin!==url.origin)||request.headers.get('sec-fetch-site')==='cross-site')return json({error:'이 사이트에서 다시 시도해 주세요.'},403);
  if(!request.headers.get('content-type')?.startsWith('application/json'))return json({error:'JSON 형식으로 보내 주세요.'},415);
 }
 try {
  const row=await env.DB.prepare('SELECT document, revision FROM family_data WHERE owner_id = ?').bind(owner).first();
  const data=row?validateData(JSON.parse(row.document)):initialData();
  if(request.method==='GET')return json({data,revision:row?.revision??0});
  if(Number(request.headers.get('content-length'))>1000000)return json({error:'요청이 너무 큽니다. 백업 파일은 1MB 이하여야 합니다.'},413);
  const reader=request.body?.getReader();let size=0;const chunks=[];
  if(reader){while(true){const {done,value}=await reader.read();if(done)break;size+=value.byteLength;if(size>1000000){await reader.cancel();return json({error:'요청이 너무 큽니다.'},413);}chunks.push(value);}}
  const bytes=new Uint8Array(size);let offset=0;for(const chunk of chunks){bytes.set(chunk,offset);offset+=chunk.byteLength;}
  const raw=new TextDecoder().decode(bytes);
  let body;try{body=JSON.parse(raw);}catch{return json({error:'요청 내용을 확인해 주세요.'},400);}
  if(!body||!Number.isInteger(body.revision)||body.revision<0)return json({error:'저장 버전을 확인해 주세요.'},400);
  if(body.revision!==(row?.revision??0))return json({error:'다른 기기에서 기록을 바꾸었어요. 새로고침 후 다시 저장해 주세요.'},409);
  const changed=changeData(data,body.action);
  const document=JSON.stringify(changed.data);
  let result;
  if(row)result=await env.DB.prepare('UPDATE family_data SET document = ?, revision = revision + 1 WHERE owner_id = ? AND revision = ?').bind(document,owner,row.revision).run();
  else result=await env.DB.prepare('INSERT OR IGNORE INTO family_data(owner_id, document, revision) VALUES (?, ?, 1)').bind(owner,document).run();
  if(result.meta.changes!==1)return json({error:'동시에 변경된 기록이 있어요. 새로고침 후 다시 시도해 주세요.'},409);
  return json({data:changed.data,revision:(row?.revision??0)+1,resultId:changed.resultId});
 }catch(e){
  if(e instanceof InputError)return json({error:e.message},400);
  // 학생 기록이나 사용자 ID를 로그에 출력하지 않습니다.
  return json({error:'저장소에 연결하지 못했어요. 입력은 화면에 남아 있으니 잠시 후 다시 시도해 주세요.'},503);
 }
}
