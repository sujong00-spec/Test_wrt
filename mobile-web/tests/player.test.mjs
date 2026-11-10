import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
// package.json 없이 브라우저 ES 모듈을 읽습니다.
const code = await readFile(new URL('../web/player.js',import.meta.url),'utf8');
const {DictationPlayer} = await import('data:text/javascript;base64,'+Buffer.from(code).toString('base64'));
let utterances=[], completed=0, notices=[];
const synth={getVoices:()=>[{lang:'en-US'},{lang:'ko-KR'}],speak:u=>utterances.push(u),cancel(){},pause(){},resume(){}};
class Utterance {constructor(text){this.text=text;}}
const player=new DictationPlayer(synth,Utterance,t=>notices.push(t),()=>completed++);
player.start([{text:'한글 문장'}],.7,2,10);
assert.equal(utterances[0].lang,'ko-KR');assert.equal(utterances[0].rate,.7);assert.equal(utterances[0].voice.lang,'ko-KR');
utterances[0].onend();
player.toggle();assert.equal(player.paused,true);assert.equal(player.timer,null);
await new Promise(r=>setTimeout(r,30));assert.equal(utterances.length,1);
player.toggle();assert.equal(player.paused,false);
await new Promise(r=>setTimeout(r,1250));assert.equal(utterances.length,2);
utterances[1].onend();assert.equal(completed,1);assert.equal(player.active,false);
player.start([{text:'첫 문장'},{text:'다음 문장'}],1,1,.01);
const stale=utterances.at(-1);stale.onend();player.stop();
await new Promise(r=>setTimeout(r,30));assert.equal(completed,1);assert.equal(player.active,false);
stale.onend();assert.equal(player.next,null);
player.start([{text:'오류 문장'}],1,2,1);utterances.at(-1).onerror({error:'synthesis-failed'});assert.equal(completed,2);
synth.getVoices=()=>[];
assert.throws(()=>player.start([{text:'문장'}],1,2,1),/한국어/);
console.log('음성 선택·속도·기본 두 번 읽기·대기 중 일시정지/재개·종료·오류·한국어 음성 없음: 통과');
