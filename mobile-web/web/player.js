// 기기의 설치 상태와 브라우저의 API 지원 여부를 구분해 안내합니다.
export function voiceEnvironment(synth,Utterance,userAgent='') {
  const embedded=/KAKAOTALK|FBAN|FBAV|Instagram|NAVER|Line\//i.test(userAgent);
  const supported=typeof Utterance==='function'&&['getVoices','speak','cancel','pause','resume'].every(key=>typeof synth?.[key]==='function');
  let voices=[];try{voices=supported?synth.getVoices().filter(v=>/^ko(?:-|_|$)/i.test(v.lang)):[];}catch{}
  let message;
  if(voices.length)message='한국어 음성이 준비되었어요.';
  else if(embedded)message='카카오톡 등 앱 안의 브라우저에서는 한국어 음성 읽기가 제한될 수 있어요. Chrome 또는 Safari로 열어 주세요.';
  else if(!supported)message='이 브라우저는 음성 읽기를 지원하지 않아요. 최신 Chrome 또는 Safari로 열어 주세요.';
  else message='한국어 음성 목록이 아직 준비되지 않았어요. 잠시 후 ‘음성 다시 확인’을 누르세요. 계속 같으면 기기 설정에서 한국어 읽기 음성을 확인해 주세요.';
  return {embedded,supported,voices,message,android:/Android/i.test(userAgent)};
}
export class DictationPlayer {
  constructor(synth, Utterance, notify, done) {
    Object.assign(this, {synth, Utterance, notify, done});
    this.generation = 0; this.active = false; this.paused = false;
  }
  environment() { return voiceEnvironment(this.synth,this.Utterance,globalThis.navigator?.userAgent||''); }
  voices() { return this.environment().voices; }
  start(items, rate, repeat, gap, mode='auto') {
    this.stop();
    const voice = this.voices()[0];
    if (!voice || !this.Utterance) throw new Error(this.environment().message);
    Object.assign(this, {items, rate, repeat, gap, mode, voice, index:0, turn:0, active:true, paused:false, awaitingNext:false});
    this.speak();
  }
  readingState(phase='speaking') {
    return {text:this.items[this.index].text,number:this.items[this.index].number||this.index+1,index:this.index,total:this.items.length,turn:Math.min(this.turn+1,this.repeat),repeat:this.repeat,awaitingNext:this.awaitingNext,last:this.index+1===this.items.length,phase};
  }
  speak() { this.playUtterance(()=>this.advance()); }
  advance() {
    this.turn++;
    if(this.turn<this.repeat)this.wait(1200,()=>this.speak(),'repeat');
    else if(this.mode==='manual'){this.awaitingNext=true;this.announceNext();}
    else if(this.index+1<this.items.length){
      this.notify(`${this.items[this.index].number||this.index+1}번 문장을 종이에 써 주세요. 잠시 후 다음 문장을 읽어요.`,this.readingState('writing'));
      this.wait(this.gap*1000,()=>{this.index++;this.turn=0;this.speak();},'writing');
    } else {this.active=false;this.paused=false;this.done();}
  }
  announceNext(){
    this.notify(this.index+1===this.items.length?'마지막 문장을 다 썼으면 ‘다 썼어요 · 연습 완료’를 눌러 주세요.':'다 썼으면 ‘다 썼어요 · 다음 문장’을 눌러 주세요.',this.readingState('ready-next'));
  }
  canNext(){return this.active&&this.awaitingNext&&!this.paused&&!this.replaying;}
  nextSentence(){
    if(!this.canNext())return false;this.awaitingNext=false;
    if(this.index+1===this.items.length){this.active=false;this.paused=false;this.done({completed:true});}
    else {this.index++;this.turn=0;this.speak();}return true;
  }
  playUtterance(onEnd,replay=false) {
    const generation=this.generation;
    const utterance=new this.Utterance(this.items[this.index].text);
    utterance.lang='ko-KR';utterance.voice=this.voice;utterance.rate=this.rate;
    const state=this.readingState(replay?'replaying':'speaking');
    this.notify(replay?`${state.number}번 문장 · 다시 읽기`:`${state.number}번 문장 · ${this.turn+1} / ${this.repeat}회 읽기`,state);
    utterance.onend=()=>{if(generation!==this.generation||!this.active)return;onEnd();};
    utterance.onerror=()=>{
      if(generation!==this.generation)return;
      this.stop();this.done('음성을 읽지 못했어요. 한국어 음성 설정을 확인한 뒤 다시 시도해 주세요.');
    };
    this.utterance=utterance;
    this.synth.speak(utterance);
  }
  repeatCurrent() {
    if(this.replaying||!this.items?.[this.index])return false;
    const voice=this.voices()[0];
    if(!voice||!this.Utterance)throw new Error(this.environment().message);
    const wasActive=this.active,wasPaused=this.paused,next=this.next,waitKind=this.waitKind,wasAwaitingNext=this.awaitingNext;
    const remaining=this.timer?Math.max(0,this.deadline-Date.now()):this.remaining;
    this.generation++;
    clearTimeout(this.timer);this.timer=null;this.next=null;
    this.synth.cancel();this.synth.resume();
    this.voice=voice;this.active=true;this.paused=false;this.replaying=true;this.awaitingNext=false;
    this.playUtterance(()=>{
      this.replaying=false;
      if(!wasActive){
        this.active=false;this.paused=false;
        this.notify('다시 읽기가 끝났어요. 종이에 이어서 써 주세요.',this.readingState('replay-finished'));
        return;
      }
      this.paused=wasPaused||this.paused;
      if(wasAwaitingNext){this.awaitingNext=true;this.announceNext();}
      else if(next){
        this.wait(waitKind==='writing'?this.gap*1000:remaining,next,waitKind);
        this.notify(this.paused?'일시정지 상태예요. 계속 읽기를 누르면 연습을 이어갑니다.':'다시 들은 문장을 써 주세요. 원래 순서대로 이어갑니다.',this.readingState('replay-finished'));
      }else {
        this.advance();
        if(this.active&&!this.awaitingNext)this.notify(this.paused?'일시정지 상태예요. 계속 읽기를 누르면 연습을 이어갑니다.':'원래 순서대로 이어갑니다.',this.readingState('replay-finished'));
      }
      if(this.active&&this.paused)this.synth.pause();
    },true);
    return true;
  }
  wait(ms,next,kind='repeat'){this.remaining=ms;this.next=next;this.waitKind=kind;if(!this.paused)this.schedule();}
  schedule() {
    this.deadline=Date.now()+this.remaining;
    this.timer=setTimeout(() => {this.timer=null; const next=this.next; this.next=null; next();},this.remaining);
  }
  toggle() {
    if (!this.active) return;
    this.paused=!this.paused;
    if (this.paused) {
      this.synth.pause();
      if (this.timer) {clearTimeout(this.timer); this.timer=null; this.remaining=Math.max(0,this.deadline-Date.now());}
    } else {this.synth.resume(); if (this.next) this.schedule();}
  }
  stop() {this.generation++; clearTimeout(this.timer); this.timer=null; this.next=null; this.active=false; this.paused=false; this.replaying=false; this.awaitingNext=false; this.synth?.cancel?.();}
}
