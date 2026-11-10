import test from 'node:test';
import assert from 'node:assert/strict';
import {DictationPlayer} from '../web/player.js';
function setup(mode='manual'){
 const spoken=[],events=[],done=[];const synth={getVoices:()=>[{lang:'ko-KR'}],speak:u=>spoken.push(u),pause(){},resume(){},cancel(){}};
 class Utterance{constructor(text){this.text=text;}}
 const player=new DictationPlayer(synth,Utterance,(text,state)=>events.push({text,state}),result=>done.push(result));
 player.start([{text:'첫 문장',number:2},{text:'끝 문장',number:9}],1,1,10,mode);return {player,spoken,events,done};
}
test('수동 진행은 읽는 중 클릭 거부, 문장 뒤 타이머 없이 대기하고 다 썼어요로만 이동',()=>{
 const {player,spoken,done}=setup();assert.equal(player.nextSentence(),false);
 spoken[0].onend();assert.equal(player.canNext(),true);assert.equal(player.timer,null);assert.equal(spoken.length,1);
 player.nextSentence();assert.equal(player.index,1);assert.equal(spoken.length,2);assert.equal(player.nextSentence(),false);
 spoken[1].onend();assert.equal(done.length,0);assert.equal(player.active,true);
 player.nextSentence();assert.deepEqual(done,[{completed:true}]);assert.equal(player.active,false);assert.equal(player.nextSentence(),false);player.stop();
});
test('수동 대기 중 다시 듣기는 현재 번호와 대기를 유지하며 자동 이동하지 않음',()=>{
 const {player,spoken,events}=setup();spoken[0].onend();player.repeatCurrent();assert.equal(player.canNext(),false);
 spoken[1].onend();assert.equal(player.awaitingNext,true);assert.equal(player.index,0);assert.equal(player.timer,null);assert.equal(events.at(-1).state.phase,'ready-next');assert.equal(events.at(-1).state.number,2);player.stop();
});
test('수동 대기 중 일시정지·다시 읽기 후에도 계속 읽기 전까지 이동 불가',()=>{
 const {player,spoken}=setup();spoken[0].onend();player.toggle();assert.equal(player.nextSentence(),false);
 player.repeatCurrent();spoken[1].onend();assert.equal(player.paused,true);assert.equal(player.awaitingNext,true);assert.equal(player.canNext(),false);
 player.toggle();assert.equal(player.canNext(),true);player.stop();
});
test('중간 종료는 완료 이벤트나 스티커 조건을 생성하지 않음',()=>{
 const {player,spoken,done}=setup();spoken[0].onend();player.stop();assert.equal(player.canNext(),false);assert.equal(done.length,0);
});
test('자동 읽기 종료 자체로 완료를 추측하지 않음',()=>{
 const {player,spoken,done}=setup('auto');player.items=player.items.slice(0,1);spoken[0].onend();assert.deepEqual(done,[undefined]);player.stop();
});
