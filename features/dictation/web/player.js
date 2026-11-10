// 브라우저 한국어 음성만 사용합니다. 음성이 없으면 연습을 시작하지 않습니다.
export class DictationPlayer {
  constructor(synth, Utterance, notify, done) {
    Object.assign(this, {synth, Utterance, notify, done});
    this.generation = 0; this.active = false; this.paused = false;
  }
  voices() { return this.synth?.getVoices().filter(v => /^ko(?:-|_|$)/i.test(v.lang)) || []; }
  start(items, rate, repeat, gap) {
    this.stop();
    const voice = this.voices()[0];
    if (!voice || !this.Utterance) throw new Error('이 기기에 한국어 읽기 음성이 없습니다. 기기 설정에서 한국어 음성을 설치하고 다시 열어 주세요.');
    Object.assign(this, {items, rate, repeat, gap, voice, index:0, turn:0, active:true, paused:false});
    this.speak();
  }
  speak() {
    const generation = this.generation;
    const utterance = new this.Utterance(this.items[this.index].text);
    utterance.lang = 'ko-KR'; utterance.voice = this.voice; utterance.rate = this.rate;
    this.notify(`${this.index + 1} / ${this.items.length}번 문장 · ${this.turn + 1} / ${this.repeat}회 읽기`);
    utterance.onend = () => {
      if (generation !== this.generation || !this.active) return;
      this.turn++;
      if (this.turn < this.repeat) this.wait(1200, () => this.speak());
      else if (this.index + 1 < this.items.length) {
        this.notify(`${this.index + 1}번 문장을 종이에 써 주세요. 잠시 후 다음 문장을 읽어요.`);
        this.wait(this.gap * 1000, () => {this.index++; this.turn=0; this.speak();});
      } else { this.active=false; this.done(); }
    };
    utterance.onerror = e => {
      if (generation !== this.generation) return;
      this.stop(); this.done('음성을 읽지 못했어요. 한국어 음성 설정을 확인한 뒤 다시 시도해 주세요.');
    };
    this.utterance = utterance; // 일부 모바일 브라우저의 가비지 수집 방지
    this.synth.speak(utterance);
  }
  wait(ms, next) { this.remaining=ms; this.next=next; if (!this.paused) this.schedule(); }
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
  stop() {this.generation++; clearTimeout(this.timer); this.timer=null; this.next=null; this.active=false; this.paused=false; this.synth?.cancel();}
}
