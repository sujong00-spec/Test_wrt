import {DictationPlayer} from './player.js';
import {DataClient} from './client.js';
import {makeBackup,backupData,wrongbook,FAMILY_ID,reviewWarmup,stickerDays} from './data.js';
const $=id=>document.getElementById(id);
const client=new DataClient();
let ready=false,working=false,dirty=false,draft=null,retry=null,recordLimit=20,installPrompt=null,selectedPackId='';
const labels={unchecked:'미확인',correct:'잘했어요',wrong:'다시 연습'};
function node(tag,text,className){const el=document.createElement(tag);if(text)el.textContent=text;if(className)el.className=className;return el;}
function message(text,error=false){$('message').textContent=text;$('message').className=error?'error':'';}
function controls(){
 const locked=!ready||working||player.active;
 for(const id of ['start','start-top','speed','repeat','gap','select-all','select-none','save-prompts','export','import','clear','migrate','reload','check-voice','advance-mode','pack-select','pack-name','pack-save','pack-load','pack-delete','start-warmup'])$(id).disabled=locked;
 document.querySelectorAll('[data-tab],.record button,.record select,#wrong-items button,#prompts input,#prompts textarea,#review-items select').forEach(el=>el.disabled=locked);
 $('pack-load').disabled=locked||!selectedPackId;$('pack-delete').disabled=locked||!selectedPackId;
 $('next-sentence').disabled=!player.canNext();$('next-sentence').hidden=$('advance-mode').value!=='manual';
 $('next-sentence').textContent=player.items&&player.index+1===player.items.length?'다 썼어요 · 연습 완료':'다 썼어요 · 다음 문장';
 $('gap-label').hidden=$('advance-mode').value==='manual';
 $('gap').disabled=locked||$('advance-mode').value==='manual';
 $('finish-writing').hidden=!draft?.readingFinished||draft.completed||player.active;
 $('finish-writing').disabled=working;
 $('back-to-today').hidden=draft?.kind!=='review'||player.active;
 $('back-to-today').disabled=working;
 $('save-record').disabled=locked||!draft||draft.saved;
 $('repeat-current').disabled=!ready||working||!currentReading||player.replaying;
 $('repeat-current').textContent=player.replaying?'다시 읽는 중…':'현재 문장 다시 읽기';
 $('pause').disabled=!player.active; $('stop').disabled=!player.active;
 document.body.classList.toggle('reading',player.active);
 $('pause').textContent=player.paused?'계속 읽기':'일시정지';
 $('reload').hidden=!client.cloud;
}
function selectedItems(){return [...document.querySelectorAll('.prompt')].filter(row=>row.querySelector('input').checked).map(row=>({text:row.querySelector('textarea').value.trim(),number:Number(row.dataset.id)}));}
function selection(){retry=null;$('selection-count').textContent=`${selectedItems().length} / 10개 선택`;}
function renderPrompts(){
 $('prompts').replaceChildren();
 client.data.prompts.forEach(item=>{
  const row=node('div',null,'prompt');row.dataset.id=item.id;
  const check=node('input');check.type='checkbox';check.checked=true;check.setAttribute('aria-label',`${item.id}번 문장 선택`);check.onchange=selection;
  const label=node('label',`${item.id}번 문장`),input=node('textarea');input.value=item.text;input.maxLength=200;input.rows=2;
  input.oninput=()=>{dirty=true;$('dirty-note').hidden=false;retry=null;};label.append(input);row.append(check,label);$('prompts').append(row);
 });dirty=false;$('dirty-note').hidden=true;selection();
}
function tab(id){for(const name of ['practice','history','wrong','settings'])$(name).hidden=name!==id;document.querySelectorAll('[data-tab]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.tab===id)));}
function outcomeSelect(value){const select=node('select');for(const [key,label] of Object.entries(labels))select.add(new Option(label,key));select.value=value;return select;}
function renderPacks(){
 if(!client.data.packs.some(p=>p.id===selectedPackId))selectedPackId='';
 $('pack-select').replaceChildren(new Option('새 문제 묶음',''));
 client.data.packs.forEach(pack=>$('pack-select').add(new Option(pack.name,pack.id)));
 $('pack-select').value=selectedPackId;
}
function renderStickers(){
 const days=stickerDays(client.data),today=new Date();
 const key=`${today.getFullYear()}-${String(today.getMonth()+1).padStart(2,'0')}-${String(today.getDate()).padStart(2,'0')}`;
 $('today-sticker').textContent=days.includes(key)?'⭐ 오늘의 연습 완료 스티커를 모았어요!':'한 문장씩 차근차근 시작해 보자.';
 $('sticker-note').textContent=days.length?`끝까지 연습한 날이 ${days.length}일 쌓였어요.`:'연습을 끝내고 기록을 저장하면 첫 스티커가 생겨요.';
 $('sticker-days').replaceChildren();
 days.slice(0,30).forEach(day=>$('sticker-days').append(node('span',`⭐ ${day}`,'sticker-day')));
}
function renderWarmup(){
 const items=reviewWarmup(client.data);$('warmup').hidden=!items.length;
 $('warmup-note').textContent=items.length?`지난번에 다시 연습하기로 한 ${items.length}문장부터 가볍게 시작해요.`:'';
 $('start-warmup').textContent=`오답 ${items.length||3}문장 먼저 복습`;
}
function renderRecords(){
 const records=client.data.records.slice().sort((a,b)=>b.created_at.localeCompare(a.created_at));
 $('records').replaceChildren();$('wrong-items').replaceChildren();$('record-count').textContent=`${records.length}회`;
 if(!records.length)$('records').append(node('p','아직 기록이 없어요. 오늘 첫 연습을 시작해 보세요.'));
 for(const record of records.slice(0,recordLimit)){
  const card=node('details',null,'record');
  const legacyName=record.student_id===FAMILY_ID?'':client.data.students.find(s=>s.id===record.student_id)?.name;
  if(legacyName)card.append(node('p','이전 기록 · '+legacyName,'hint'));
  const checked=record.outcomes.filter(x=>x!=='unchecked').length;
  card.append(node('summary',`${new Date(record.created_at).toLocaleString('ko-KR')} · ${record.items.length}문장 · 확인 ${checked}개${record.kind==='review'?' · 오답 복습':''}${record.completed?' · ⭐ 완료':''}`));
  const selects=[];
  record.items.forEach((item,index)=>{const label=node('label',`${index+1}. ${item.text}`),select=outcomeSelect(record.outcomes[index]);selects.push(select);label.append(select);card.append(label);});
  const actions=node('div',null,'actions'),save=node('button','확인 결과 수정 저장','secondary'),remove=node('button','이 기록 삭제','text-danger');
  save.onclick=()=>mutate({type:'record.review',id:record.id,outcomes:selects.map(s=>s.value)},'확인 결과를 수정했어요.');
  remove.onclick=()=>{if(confirm('이 학습 기록을 삭제할까요? 삭제 후에는 백업 파일로만 복원할 수 있어요.'))mutate({type:'record.delete',id:record.id},'기록을 삭제했어요.');};
  actions.append(save,remove);card.append(actions);$('records').append(card);
 }
 $('more-records').hidden=records.length<=recordLimit;
 const wrong=wrongbook(client.data);
 if(!wrong.length)$('wrong-items').append(node('p','지금 다시 연습할 문장이 없어요.'));
 for(const item of wrong){const card=node('article',null,'card'),button=node('button','이 문장 다시 연습','secondary');card.append(node('p',item.text));if(item.student_id!==FAMILY_ID){const name=client.data.students.find(s=>s.id===item.student_id)?.name;if(name)card.append(node('p','이전 기록 · '+name,'hint'));}button.onclick=()=>{if(!discardDraft())return;retry=[{text:item.text,number:1,student_id:item.student_id}];tab('practice');$('progress').textContent='오답 문장 한 개를 준비했어요. 연습 시작을 눌러 주세요.';$('listening').scrollIntoView({behavior:'smooth',block:'start'});};card.append(button);$('wrong-items').append(card);}
}
function render(){renderPacks();renderStickers();renderWarmup();renderRecords();controls();}
async function mutate(action,success,{resetPrompts=false,clearDraft=false}={}){
 if(working)return false;working=true;controls();
 try{
  const id=await client.change(action);
  if(action.type==='pack.save')selectedPackId=id;
  if(action.type==='pack.delete'){selectedPackId='';$('pack-name').value='';}
  if(clearDraft){draft=null;retry=null;$('review').hidden=true;resetReading();updateCompletion();}
  if(resetPrompts)renderPrompts();
  render();
  message(success);return true;
 }catch(e){message(e.message,true);return false;}
 finally{working=false;controls();}
}
function discardDraft(){if(draft&&!draft.saved&&!confirm('아직 저장하지 않은 연습이 있어요. 이 연습을 닫을까요?'))return false;draft=null;$('review').hidden=true;resetReading();updateCompletion();return true;}
function updateCompletion(){
 $('completion').hidden=!draft?.completed;
 if(draft?.completed)$('completion-note').textContent=`${draft.items.length}문장 연습을 끝냈어! `+(draft.saved?'오늘의 완료 스티커와 기록을 보관했어요.':'아래에서 기록을 저장하면 오늘의 스티커가 남아요. 부모 확인 전 정답은 미확인으로 보관해요.');
}
function showReview(){
 if(!draft)return;
 if(!$('review').hidden){updateCompletion();controls();return;}$('review').hidden=false;$('review-items').replaceChildren();
 draft.items.forEach((item,index)=>{const row=node('div',null,'card'),label=node('label',`${index+1}. ${item.text}`);label.append(outcomeSelect('unchecked'));row.append(label);$('review-items').append(row);});updateCompletion();controls();
}
let currentReading=null;
function resetReading(){currentReading=null;$('current-number').textContent='지금 읽는 문장';showCurrentSentence();}
function showCurrentSentence(){
 $('current-sentence').textContent=currentReading?($('hide-sentence').checked?'문장을 가렸어요. 귀 기울여 들어 보세요.':currentReading.text):'연습을 시작하면 읽는 문장이 여기에 보여요.';
}
const player=new DictationPlayer(window.speechSynthesis,window.SpeechSynthesisUtterance,(text,reading)=>{
 $('progress').textContent=text;
 if(reading){currentReading=reading;$('current-number').textContent=`${reading.number}번 문장 · ${reading.index+1} / ${reading.total}개`;showCurrentSentence();}
 controls();
},result=>{
 const error=typeof result==='string'?result:null;
 if(!error&&draft){draft.readingFinished=true;if(result?.completed)draft.completed=true;}
 $('progress').textContent=error||(draft?.completed?'기량아, 오늘도 끝까지 해냈어!':'읽기가 끝났어요. 마지막 문장을 다 쓴 뒤 연습 완료를 눌러 주세요.');
 if(error)message(error,true);showReview();controls();
});
function beginPractice(items,{student=FAMILY_ID,kind='practice'}={}){
 try{
  if(!items.length||items.some(x=>!x.text))throw new Error('빈 문장 없이 한 개 이상 선택해 주세요.');
  if(!discardDraft())return;
  draft={id:crypto.randomUUID(),student,kind,items:items.map((i,index)=>({text:i.text,number:i.number||index+1})),saved:false,completed:false,readingFinished:false};
  player.start(draft.items,Number($('speed').value),Number($('repeat').value),Number($('gap').value),$('advance-mode').value);
  message('지금 읽는 문장을 보며 종이에 써 보자!');controls();$('listening').scrollIntoView({behavior:'smooth',block:'start'});
 }catch(e){player.stop();draft=null;resetReading();updateCompletion();controls();message(e.message,true);}
}
$('start').onclick=()=>beginPractice(retry||selectedItems(),{student:retry?.[0]?.student_id||FAMILY_ID,kind:retry?'review':'practice'});
$('start-warmup').onclick=()=>{const items=reviewWarmup(client.data);beginPractice(items,{student:items[0]?.student_id||FAMILY_ID,kind:'review'});};
$('next-sentence').onclick=()=>{player.nextSentence();controls();};
$('repeat-current').onclick=()=>{try{player.repeatCurrent();controls();}catch(e){message(e.message,true);controls();}};
$('pause').onclick=()=>{player.toggle();controls();};
$('stop').onclick=()=>{player.stop();$('progress').textContent='읽기를 종료했어요. 진행한 문장을 직접 확인해 저장할 수 있어요.';showReview();controls();};
async function saveCurrentRecord(){
 if(!draft)return false;if(draft.saved)return true;const current=draft;
 const ok=await mutate({type:'record.add',id:current.id,student_id:current.student,items:current.items,outcomes:[...$('review-items').querySelectorAll('select')].map(s=>s.value),completed:current.completed,kind:current.kind},current.completed?'완료 스티커와 학습 기록을 저장했어요.':'학습 기록을 저장했어요.');
 if(ok&&draft===current){draft.saved=true;updateCompletion();controls();}return ok;
}
$('save-record').onclick=()=>saveCurrentRecord();
$('finish-writing').onclick=async()=>{
 if(!draft?.readingFinished||draft.completed)return;
 if(draft.saved){const ok=await mutate({type:'record.complete',id:draft.id},'완료 스티커를 저장했어요.');if(!ok)return;}
 draft.completed=true;updateCompletion();controls();
};
$('back-to-today').onclick=async()=>{
 if(!await saveCurrentRecord())return;
 retry=null;beginPractice(selectedItems());
};
$('start-top').onclick=()=>$('start').click();
$('hide-sentence').onchange=showCurrentSentence;
function allPrompts(){return [...document.querySelectorAll('.prompt')].map(row=>({id:Number(row.dataset.id),text:row.querySelector('textarea').value}));}
$('save-prompts').onclick=()=>mutate({type:'prompts.save',items:allPrompts()},'문장을 저장했어요.',{resetPrompts:true});
$('pack-select').onchange=()=>{selectedPackId=$('pack-select').value;$('pack-name').value=client.data.packs.find(p=>p.id===selectedPackId)?.name||'';controls();};
$('pack-save').onclick=()=>{
 if(selectedPackId&&!confirm('선택한 문제 묶음을 현재 입력한 10문장으로 바꿀까요? 과거 학습 기록은 그대로 유지돼요.'))return;
 mutate({type:'pack.save',id:selectedPackId||crypto.randomUUID(),name:$('pack-name').value,items:allPrompts()},'문제 묶음과 오늘의 문장을 저장했어요.',{resetPrompts:true});
};
$('pack-load').onclick=()=>{
 if((dirty||(draft&&!draft.saved))&&!confirm('저장하지 않은 수정·연습을 닫고 선택한 묶음을 불러올까요? 필요하면 먼저 저장해 주세요.'))return;
 mutate({type:'pack.load',id:selectedPackId},'문제 묶음을 불러왔어요.',{resetPrompts:true,clearDraft:true});
};
$('pack-delete').onclick=()=>{if(confirm('선택한 문제 묶음을 삭제할까요? 오늘의 문장과 학습 기록은 그대로 유지돼요.'))mutate({type:'pack.delete',id:selectedPackId},'문제 묶음을 삭제했어요.');};
$('select-all').onclick=()=>{document.querySelectorAll('.prompt input').forEach(c=>c.checked=true);selection();};
$('select-none').onclick=()=>{document.querySelectorAll('.prompt input').forEach(c=>c.checked=false);selection();};
$('more-records').onclick=()=>{recordLimit+=20;renderRecords();controls();};
$('reload').onclick=async()=>{
 if((dirty||(draft&&!draft.saved))&&!confirm('최신 기록을 불러오면 화면의 저장하지 않은 수정과 연습이 닫힙니다. 계속할까요?'))return;
 working=true;controls();try{await client.reload();draft=null;$('review').hidden=true;resetReading();updateCompletion();renderPrompts();render();message('최신 기록을 불러왔어요.');}catch(e){message(e.message,true);}finally{working=false;controls();}
};
function download(){const blob=new Blob([JSON.stringify(makeBackup(client.data),null,2)],{type:'application/json'}),url=URL.createObjectURL(blob),anchor=node('a');anchor.href=url;anchor.download=`받아쓰기-백업-${new Date().toISOString().slice(0,10)}.json`;document.body.append(anchor);anchor.click();anchor.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);message('백업 파일 내려받기를 요청했어요. 다운로드 폴더를 확인해 주세요.');}
$('export').onclick=()=>{try{download();}catch(e){message(e.message,true);}};
$('import').onclick=()=>$('import-file').click();
async function importBackup(backup,isMigration=false){
 const clean=backupData(backup);
 if(!confirm(`연습 기록 ${clean.records.length}개를 추가하고, 문제 묶음 ${clean.packs.length}개를 추가하고, 문제 10개를 가져온 문장으로 바꿀까요? 기존 기록은 유지되며 같은 자료를 다시 가져오면 중복됩니다.`))return;
 const ok=await mutate({type:'backup.import',backup:{format:'ttobak-backup',version:1,data:clean}},'자료를 가져왔어요.',{resetPrompts:true,clearDraft:true});
 if(ok&&isMigration){$('migration').hidden=true;try{localStorage.setItem('ttobak-migrated','yes');}catch{}}
}
$('import-file').onchange=async()=>{try{const file=$('import-file').files[0];if(!file)return;if(file.size>1000000)throw new Error('백업 파일은 1MB 이하만 가져올 수 있어요.');let backup;try{backup=JSON.parse(await file.text());}catch{throw new Error('올바른 JSON 백업 파일을 선택해 주세요.');}await importBackup(backup);}catch(e){message(e.message,true);}finally{$('import-file').value='';}};
$('migrate').onclick=async()=>{try{const legacy=client.legacy();if(!legacy)throw new Error('가져올 기기 기록을 찾지 못했어요.');await importBackup(legacy,true);}catch(e){message(e.message,true);}};
$('clear').onclick=()=>{if(confirm('현재 저장 공간의 모든 학습 자료를 삭제할까요? 먼저 백업을 내려받으세요.'))mutate({type:'account.clear'},'모든 학습 자료를 삭제했어요.',{resetPrompts:true,clearDraft:true});};
document.querySelectorAll('[data-tab]').forEach(b=>b.onclick=()=>tab(b.dataset.tab));
function voices(){
 const info=player.environment();
 $('voice-note').textContent=info.message;
 $('browser-help').hidden=!info.embedded;
 if(info.embedded&&info.android){
  const destination=location.origin+'/';
  $('open-chrome').href='intent://'+location.host+'/#Intent;scheme=https;package=com.android.chrome;S.browser_fallback_url='+encodeURIComponent(destination)+';end';
  $('open-chrome').hidden=false;
 }
}
window.speechSynthesis?.addEventListener?.('voiceschanged',voices);voices();
$('check-voice').onclick=()=>{voices();message(player.environment().message,!player.voices().length);};
window.addEventListener('focus',voices);
for(const id of ['speed','repeat','gap','advance-mode'])$(id).onchange=()=>{try{localStorage.setItem('ttobak-preferences',JSON.stringify({speed:$('speed').value,repeat:$('repeat').value,gap:$('gap').value,'advance-mode':$('advance-mode').value}));}catch{}controls();};
try{const prefs=JSON.parse(localStorage.getItem('ttobak-preferences')||'null');if(prefs)for(const id of ['speed','repeat','gap','advance-mode'])if([...$(id).options].some(o=>o.value===prefs[id]))$(id).value=prefs[id];}catch{}
window.addEventListener('beforeinstallprompt',event=>{event.preventDefault();installPrompt=event;$('install').textContent='홈 화면에 설치';});
$('install').onclick=async()=>{if(installPrompt){await installPrompt.prompt();installPrompt=null;}else{$('install-help').scrollIntoView({behavior:'smooth',block:'center'});message('Android Chrome은 메뉴 ⋮, iPhone/iPad Safari는 공유 메뉴에서 ‘홈 화면에 추가’를 선택하세요.');}};
window.addEventListener('beforeunload',event=>{if(dirty||(draft&&!draft.saved)){event.preventDefault();event.returnValue='';}});
window.addEventListener('pagehide',()=>player.stop());
$('connection-retry').onclick=()=>boot();
$('connection-retry-main').onclick=()=>boot();
async function boot(){
 $('connection-retry').disabled=true;$('connection-retry-main').disabled=true;
 try{
  await client.init();ready=true;$('connection-retry').hidden=true;$('connection-retry-main').hidden=true;$('connection-status').hidden=true;
  $('signin').hidden=client.cloud;$('signout').hidden=!client.cloud;
  $('storage-note').textContent=client.cloud?'보호자 계정으로 연결됐어요. 같은 계정으로 로그인하면 다른 기기에서도 기록을 불러올 수 있어요.':'로그인 없이 체험 중이에요. 기록은 이 브라우저에만 저장돼요. 브라우저 데이터를 지우면 사라질 수 있으니 백업해 주세요.';
  if(client.cloud){const legacy=client.legacy();let migrated=false;try{migrated=localStorage.getItem('ttobak-migrated')==='yes';}catch{}$('migration').hidden=!legacy?.students.length||migrated;}
  renderPrompts();render();
 }catch(e){message(e.message,true);$('storage-note').textContent='저장 공간에 연결하지 못했어요. 아래 ‘다시 연결’을 눌러 주세요. 기기 기록은 지우지 않습니다.';$('connection-retry').hidden=false;$('connection-retry-main').hidden=false;$('connection-status').textContent='저장 공간에 연결하지 못했어요. 다시 연결해 주세요.';$('connection-status').hidden=false;}
 $('connection-retry').disabled=false;$('connection-retry-main').disabled=false;
 controls();
}
boot();
