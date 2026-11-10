import {DictationPlayer} from './player.js';
const $ = id => document.getElementById(id);
let state, currentItems=[], saved=false;
const message = (text, error=false) => { $('message').textContent=text; $('message').className=error?'error':''; };
async function api(path, body) {
  const response = await fetch(path, body === undefined ? {} : {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || '요청을 처리하지 못했어요.');
  return data;
}
function element(tag, text, className) { const node=document.createElement(tag); if(text)node.textContent=text; if(className)node.className=className; return node; }
function selectedItems() {return [...document.querySelectorAll('.prompt')].filter(row=>row.querySelector('input').checked).map(row=>({id:Number(row.dataset.id),text:row.querySelector('textarea').value.trim()}));}
function selectionCount() { $('selection-count').textContent=`${selectedItems().length} / 10개 선택`; }
function prompts() {
  $('prompts').replaceChildren();
  state.prompts.forEach(item=>{
    const row=element('div',null,'prompt'); row.dataset.id=item.id;
    const check=element('input'); check.type='checkbox'; check.checked=true; check.setAttribute('aria-label',`${item.id}번 문장 선택`); check.onchange=selectionCount;
    const label=element('label',`${item.id}번 문장`), input=element('textarea'); input.value=item.text; input.maxLength=200; input.rows=2; label.append(input);
    row.append(check,label); $('prompts').append(row);
  }); selectionCount();
}
function renderHistory() {
  $('records').replaceChildren(); $('wrong-items').replaceChildren();
  if (!state.records.length) $('records').append(element('p','아직 학습 기록이 없어요. 첫 연습을 시작해 보세요.'));
  for (const record of state.records) {
    const card=element('article',null,'card');
    const date = new Date(record.created_at).toLocaleString('ko-KR');
    card.append(element('h3',`${date} · ${record.items.length}문장`));
    const labels={correct:'잘했어요',wrong:'다시 연습',unchecked:'미확인'};
    record.items.forEach((item,index)=>card.append(element('p',`${index+1}. ${item.text} — ${labels[record.outcomes[index]]}`)));
    $('records').append(card);
  }
  if (!state.wrongbook.length) $('wrong-items').append(element('p','아직 다시 연습할 문장이 없어요. 부모 확인 후 여기에 모입니다.'));
  for(const item of state.wrongbook) {
    const card=element('article',null,'card'); card.append(element('p',item.text));
    const button=element('button','이 문장 다시 연습','secondary');
    button.onclick=()=>{ tab('practice'); prepare([item]); $('review').hidden=true; $('progress').scrollIntoView({behavior:'smooth',block:'center'}); };
    card.append(button); $('wrong-items').append(card);
  }
}
async function refresh(student=$('student').value) {
  state=await api('/api/practice'+(student?'?student='+encodeURIComponent(student):''));
  $('student').replaceChildren(new Option('학생을 선택해 주세요',''));
  state.students.forEach(s=>$('student').add(new Option(s.name,s.id)));
  $('student').value=student; renderHistory();
}
function tab(id) { ['practice','history','wrong'].forEach(x=>$(x).hidden=x!==id); document.querySelectorAll('[data-tab]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.tab===id))); }
function busy(value) {
  document.body.classList.toggle('reading',value);
  ['student','nickname','start','speed','repeat','gap','select-all','select-none','save-prompts'].forEach(id=>$(id).disabled=value);
  $('student-form').querySelector('button').disabled=value;
  document.querySelectorAll('[data-tab]').forEach(b=>b.disabled=value);
  $('pause').disabled=!value; $('stop').disabled=!value; $('pause').textContent='일시정지';
}
const player=new DictationPlayer(window.speechSynthesis,window.SpeechSynthesisUtterance,text=>$('progress').textContent=text,error=>{
  busy(false); $('progress').textContent=error || '읽기가 끝났어요. 종이에 다 쓴 뒤 부모님과 확인해 주세요.';
  if(error) message(error,true); review();
});
function prepare(items) {currentItems=items.map(x=>({text:x.text})); saved=false;}
function review() {
  $('review').hidden=false; $('review-items').replaceChildren(); $('save-record').disabled=false;
  $('review-note').textContent='듣기 연습 기록이며, 모든 확인 결과는 부모님이 직접 선택합니다.';
  currentItems.forEach((item,index)=>{
    const row=element('div',null,'card'), label=element('label',`${index+1}. ${item.text}`), select=element('select');
    select.add(new Option('아직 확인하지 않았어요','unchecked')); select.add(new Option('잘했어요','correct')); select.add(new Option('다시 연습해요','wrong'));
    label.append(select); row.append(label); $('review-items').append(row);
  });
}
$('start').onclick=()=>{
  try {
    if(!$('student').value) throw new Error('먼저 학생을 선택하거나 등록해 주세요.');
    const items=currentItems.length && $('progress').dataset.retry==='true' ? currentItems : selectedItems();
    if(!items.length || items.some(i=>!i.text)) throw new Error('빈 문장 없이 한 개 이상 선택해 주세요.');
    prepare(items); $('review').hidden=true;
    player.start(currentItems,Number($('speed').value),Number($('repeat').value),Number($('gap').value)); busy(true); message('정답 문장을 가렸어요. 종이에 받아써 보세요.');
  }catch(e){player.stop();busy(false);message(e.message,true);}
};
// 오답 재연습은 일반 선택 문제와 분리된 한 문장으로 시작합니다.
$('wrong-items').addEventListener('click',e=>{if(e.target.tagName==='BUTTON') $('progress').dataset.retry='true';});
$('prompts').addEventListener('input',()=>{$('progress').dataset.retry='false';});
$('prompts').addEventListener('change',()=>{$('progress').dataset.retry='false';});
$('pause').onclick=()=>{player.toggle(); $('pause').textContent=player.paused?'계속 읽기':'일시정지';};
$('stop').onclick=()=>{player.stop();busy(false);$('progress').textContent='읽기를 종료했어요. 진행한 내용은 직접 확인하여 저장할 수 있어요.';review();};
$('student').onchange=async()=>{currentItems=[];$('progress').dataset.retry='false';$('review').hidden=true;try{await refresh();}catch(e){message(e.message,true);}};
$('student-form').onsubmit=async e=>{e.preventDefault();try{const result=await api('/api/students',{name:$('nickname').value});$('nickname').value='';await refresh(String(result.id));currentItems=[];$('review').hidden=true;message('학생을 등록했어요.');}catch(e){message(e.message,true);}};
$('save-prompts').onclick=async()=>{try{await api('/api/prompts',{items:[...document.querySelectorAll('.prompt')].map(row=>({id:Number(row.dataset.id),text:row.querySelector('textarea').value}))});message('문장을 저장했어요.');}catch(e){message(e.message,true);}};
$('select-all').onclick=()=>{document.querySelectorAll('.prompt input').forEach(x=>x.checked=true);$('progress').dataset.retry='false';selectionCount();};
$('select-none').onclick=()=>{document.querySelectorAll('.prompt input').forEach(x=>x.checked=false);$('progress').dataset.retry='false';selectionCount();};
$('save-record').onclick=async()=>{
  if(saved)return;
  $('save-record').disabled=true;
  try{await api('/api/practice/record',{student_id:Number($('student').value),items:currentItems,outcomes:[...document.querySelectorAll('#review-items select')].map(x=>x.value)});saved=true;await refresh();message('학습 기록을 저장했어요. 학습 기록과 오답노트에서 확인할 수 있어요.');}
  catch(e){message(e.message,true);$('save-record').disabled=false;}
};
document.querySelectorAll('[data-tab]').forEach(b=>b.onclick=()=>tab(b.dataset.tab));
function voices(){const available=player.voices().length>0;$('voice-note').textContent=available?'한국어 읽기 음성이 준비되었어요.':'한국어 음성을 기다리고 있어요. 계속 표시되면 기기 설정에서 한국어 읽기 음성을 설치해 주세요.';}
if(window.speechSynthesis) window.speechSynthesis.addEventListener('voiceschanged',voices);voices();
window.addEventListener('pagehide',()=>player.stop());
refresh().then(prompts).catch(e=>message('서버에 연결하지 못했어요. '+e.message,true));
