export const VERSION='1.2.0';
export const SEED=['아침에 일어나 이를 닦아요.','학교에 가는 길에 꽃을 보았어요.','친구와 사이좋게 놀아요.','책을 읽으면 마음이 자라요.','비가 오면 우산을 써요.','엄마와 함께 시장에 갔어요.','동생에게 장난감을 나누어 주었어요.','하늘에 하얀 구름이 떠 있어요.','밥을 먹기 전에 손을 씻어요.','오늘도 즐거운 하루를 보냈어요.'];
export const FAMILY_ID='family';
export function initialData(){return {students:[],prompts:SEED.map((text,i)=>({id:i+1,text})),records:[],packs:[]};}
export class InputError extends Error {}
function requireValue(condition,message){if(!condition)throw new InputError(message);}
function text(value,max,label){requireValue(typeof value==='string'&&value.trim().length>0&&value.trim().length<=max,`${label}은 1자부터 ${max}자까지 입력해 주세요.`);return value.trim();}
function id(value){requireValue((typeof value==='string'||Number.isSafeInteger(value))&&String(value).length>0&&String(value).length<=80,'자료 번호를 확인해 주세요.');return String(value);}
function promptList(prompts){
 requireValue(Array.isArray(prompts)&&prompts.length===10,'문장 10개가 필요합니다.');
 const cleaned=prompts.map(p=>{requireValue(Number.isInteger(p?.id)&&p.id>=1&&p.id<=10,'문장 번호를 확인해 주세요.');return {id:p.id,text:text(p.text,200,'문장')};}).sort((a,b)=>a.id-b.id);
 requireValue(new Set(cleaned.map(p=>p.id)).size===10,'문장 번호가 중복되어 있어요.');return cleaned;
}
export function validateData(input){
 requireValue(input&&typeof input==='object'&&!Array.isArray(input),'백업 자료 형식을 확인해 주세요.');
 const {students,prompts,records}=input;
 requireValue(Array.isArray(students)&&students.length<=30,'학생은 최대 30명까지 보관할 수 있어요.');
 requireValue(Array.isArray(prompts)&&prompts.length===10,'문장 10개가 필요합니다.');
 requireValue(Array.isArray(records)&&records.length<=1000,'학습 기록은 최대 1,000회까지 보관할 수 있어요. 먼저 백업 후 오래된 기록을 삭제해 주세요.');
 const cleanStudents=students.map(s=>({id:id(s?.id),name:text(s?.name,30,'별명')}));
 requireValue(new Set(cleanStudents.map(s=>s.id)).size===students.length,'학생 번호가 중복되어 있어요.');
 const cleanPrompts=promptList(prompts);
 const cleanRecords=records.map(r=>{
  requireValue(r&&Array.isArray(r.items)&&r.items.length>0&&r.items.length<=10,'기록에는 1~10개의 문장이 필요해요.');
  requireValue(Array.isArray(r.outcomes)&&r.outcomes.length===r.items.length&&r.outcomes.every(x=>['unchecked','correct','wrong'].includes(x)),'부모 확인 결과를 확인해 주세요.');
  const student_id=id(r.student_id);requireValue(cleanStudents.some(s=>s.id===student_id),'기록의 학생을 찾을 수 없어요.');
  requireValue(typeof r.created_at==='string'&&Number.isFinite(Date.parse(r.created_at)),'기록 날짜를 확인해 주세요.');
  requireValue(r.completed===undefined||typeof r.completed==='boolean','완료 표시를 확인해 주세요.');
  requireValue(r.kind===undefined||['practice','review'].includes(r.kind),'연습 종류를 확인해 주세요.');
  const completed=r.completed===true;const completedAt=completed?(r.completed_at||r.created_at):null;
  requireValue(!completed||(typeof completedAt==='string'&&Number.isFinite(Date.parse(completedAt))),'완료 날짜를 확인해 주세요.');
  return {completed,completed_at:completed?new Date(completedAt).toISOString():null,kind:r.kind||'practice',id:id(r.id),student_id,created_at:new Date(r.created_at).toISOString(),items:r.items.map(i=>({text:text(i?.text,200,'문장')})),outcomes:[...r.outcomes],source:'parent'};
 });
 requireValue(new Set(cleanRecords.map(r=>r.id)).size===records.length,'기록 번호가 중복되어 있어요.');
 const packs=input.packs??[];requireValue(Array.isArray(packs)&&packs.length<=50,'문제 묶음은 최대 50개까지 저장할 수 있어요.');
 const cleanPacks=packs.map(p=>({id:id(p?.id),name:text(p?.name,40,'묶음 이름'),items:promptList(p?.items)}));
 requireValue(new Set(cleanPacks.map(p=>p.id)).size===packs.length,'문제 묶음 번호가 중복되어 있어요.');
 const result={students:cleanStudents,prompts:cleanPrompts,records:cleanRecords,packs:cleanPacks};
 requireValue(new TextEncoder().encode(JSON.stringify(result)).length<=900000,'저장 공간 한도에 도달했어요. 백업 후 오래된 기록을 삭제해 주세요.');
 return result;
}
export function backupData(input){
 if(input?.format==='ttobak-backup'){requireValue(input.version===1,'지원하지 않는 백업 버전입니다.');return validateData(input.data);}
 return validateData(input); // 이전 체험판 데이터도 명시적으로 가져올 수 있습니다.
}
export function changeData(input,action,uuid=()=>crypto.randomUUID()){
 const data=validateData(input);requireValue(action&&typeof action==='object','요청 내용을 확인해 주세요.');
 let resultId;
 if(action.type==='student.add'){resultId=uuid();data.students.push({id:resultId,name:text(action.name,30,'별명')});}
 else if(action.type==='student.rename'){const student=data.students.find(s=>s.id===String(action.id));requireValue(student,'학생을 다시 선택해 주세요.');student.name=text(action.name,30,'별명');}
 else if(action.type==='student.delete'){requireValue(data.students.some(s=>s.id===String(action.id)),'학생을 다시 선택해 주세요.');data.students=data.students.filter(s=>s.id!==String(action.id));data.records=data.records.filter(r=>r.student_id!==String(action.id));}
 else if(action.type==='prompts.save'){data.prompts=action.items;}
 else if(action.type==='pack.save'){
  const pack={id:id(action.id),name:text(action.name,40,'묶음 이름'),items:promptList(action.items)};
  const index=data.packs.findIndex(p=>p.id===pack.id);if(index<0)data.packs.push(pack);else data.packs[index]=pack;data.prompts=pack.items;resultId=pack.id;
 }
 else if(action.type==='pack.load'){const pack=data.packs.find(p=>p.id===String(action.id));requireValue(pack,'문제 묶음을 선택해 주세요.');data.prompts=pack.items;}
 else if(action.type==='pack.delete'){requireValue(data.packs.some(p=>p.id===String(action.id)),'문제 묶음을 선택해 주세요.');data.packs=data.packs.filter(p=>p.id!==String(action.id));}
 else if(action.type==='record.add'){
  // 동일 요청을 재시도해도 중복 기록을 만들지 않습니다.
  resultId=id(action.id);const existing=data.records.find(r=>r.id===resultId);
  if(existing){requireValue(existing.student_id===String(action.student_id),'기록 번호를 확인해 주세요.');return {data,resultId};}
  if(action.student_id===FAMILY_ID&&!data.students.some(s=>s.id===FAMILY_ID))data.students.push({id:FAMILY_ID,name:'우리집'});
  data.records.push({completed:action.completed??false,completed_at:action.completed?new Date().toISOString():null,kind:action.kind||'practice',id:resultId,student_id:action.student_id,items:action.items,outcomes:action.outcomes,source:'parent',created_at:new Date().toISOString()});
 }
 else if(action.type==='record.complete'){const record=data.records.find(r=>r.id===String(action.id));requireValue(record,'학습 기록을 찾지 못했어요.');if(!record.completed){record.completed=true;record.completed_at=new Date().toISOString();}}
 else if(action.type==='record.review'){const record=data.records.find(r=>r.id===String(action.id));requireValue(record,'학습 기록을 찾지 못했어요.');record.outcomes=action.outcomes;}
 else if(action.type==='record.delete'){requireValue(data.records.some(r=>r.id===String(action.id)),'학습 기록을 찾지 못했어요.');data.records=data.records.filter(r=>r.id!==String(action.id));}
 else if(action.type==='backup.import'){
  const imported=backupData(action.backup);const map=new Map();
  for(const s of imported.students){const next=uuid();map.set(s.id,next);data.students.push({id:next,name:s.name});}
  for(const r of imported.records)data.records.push({...r,id:uuid(),student_id:map.get(r.student_id)});
  for(const pack of imported.packs)data.packs.push({...pack,id:uuid()});
  data.prompts=imported.prompts;
 }
 else if(action.type==='account.clear'){return {data:initialData()};}
 else throw new InputError('지원하지 않는 요청입니다.');
 return {data:validateData(data),resultId};
}
export function makeBackup(data){return {format:'ttobak-backup',version:1,exportedAt:new Date().toISOString(),data:validateData(data)};}
export function wrongbook(data,student){
 const latest=new Map();
 for(const record of data.records.filter(r=>student===undefined||r.student_id===student).sort((a,b)=>a.created_at.localeCompare(b.created_at))){
  record.items.forEach((item,i)=>{if(record.outcomes[i]!=='unchecked')latest.set(record.student_id+'\0'+item.text,{student_id:record.student_id,text:item.text,outcome:record.outcomes[i],created_at:record.created_at});});
 }
 return [...latest.values()].filter(x=>x.outcome==='wrong');
}

export function reviewWarmup(data,limit=3){
 const items=wrongbook(data).sort((a,b)=>b.created_at.localeCompare(a.created_at));
 const student=items.some(i=>i.student_id===FAMILY_ID)?FAMILY_ID:items[0]?.student_id;
 return items.filter(i=>i.student_id===student).slice(0,limit).map((item,index)=>({...item,number:index+1}));
}
export function stickerDays(data){
 const localDay=date=>{const d=new Date(date);return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;};
 return [...new Set(data.records.filter(r=>r.completed===true).map(r=>localDay(r.completed_at||r.created_at)))].sort().reverse();
}
