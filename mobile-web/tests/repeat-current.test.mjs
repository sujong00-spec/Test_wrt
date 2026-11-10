import test from 'node:test';
import assert from 'node:assert/strict';
import {DictationPlayer} from '../web/player.js';
function setup(repeat=2){
 const spoken=[],notices=[];let done=0;
 const synth={getVoices:()=>[{lang:'ko-KR'}],speak:u=>spoken.push(u),cancel(){},resume(){},pause(){}};
 class Utterance {constructor(text){this.text=text;}}
 const player=new DictationPlayer(synth,Utterance,(text,state)=>notices.push({text,state}),()=>done++);
 player.start([{text:'선택한 오 번 문장',number:5},{text:'선택한 칠 번 문장',number:7}],.7,repeat,20);
 return {player,spoken,notices,done:()=>done};
}
test('읽는 도중 현재 문장만 재시작하고 오래된 onend 무시',()=>{
 const {player,spoken,notices}=setup();const old=spoken[0];
 assert.equal(player.repeatCurrent(),true);assert.equal(spoken.length,2);assert.equal(spoken[1].text,old.text);assert.equal(spoken[1].rate,.7);assert.match(notices.at(-1).text,/5번 문장.*다시 읽기/);
 old.onend();assert.equal(player.turn,0);assert.equal(player.replaying,true);
 assert.equal(player.repeatCurrent(),false);assert.equal(spoken.length,2);
 spoken[1].onend();assert.equal(player.turn,1);assert.equal(player.index,0);assert.equal(player.replaying,false);assert.equal(player.remaining,1200);
 player.stop();
});
test('쓰기 대기 중 다시 읽으면 같은 문장을 읽고 쓰는 시간 20초를 다시 제공',()=>{
 const {player,spoken}=setup(1);spoken[0].onend();assert.equal(player.waitKind,'writing');
 player.repeatCurrent();spoken[1].onend();assert.equal(player.index,0);assert.equal(player.remaining,20000);assert.equal(player.waitKind,'writing');assert.equal(player.active,true);player.stop();
});
test('일시정지 중 다시 읽기는 재생 후 일시정지 상태 보존',()=>{
 const {player,spoken}=setup(1);spoken[0].onend();player.toggle();assert.equal(player.paused,true);
 player.repeatCurrent();assert.equal(player.paused,false);spoken[1].onend();assert.equal(player.paused,true);assert.equal(player.timer,null);assert.equal(typeof player.next,'function');
 player.toggle();assert.equal(player.paused,false);assert.ok(player.timer);player.stop();
});
test('완료 뒤 마지막 문장만 다시 읽어도 완료 이벤트나 기록 생성 반복 없음',()=>{
 const {player,spoken,done}=setup(1);player.items=player.items.slice(0,1);spoken[0].onend();assert.equal(done(),1);assert.equal(player.active,false);
 player.repeatCurrent();assert.equal(spoken[1].text,'선택한 오 번 문장');spoken[1].onend();assert.equal(done(),1);assert.equal(player.active,false);player.stop();
});
test('다시 읽기 도중 종료하면 취소한 이벤트가 진행을 재개하지 않음',()=>{
 const {player,spoken,done}=setup();player.repeatCurrent();const repeated=spoken[1];player.stop();repeated.onend();assert.equal(done(),0);assert.equal(player.next,null);assert.equal(player.active,false);assert.equal(player.replaying,false);
});
