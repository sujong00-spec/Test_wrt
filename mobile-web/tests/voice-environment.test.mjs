import test from 'node:test';
import assert from 'node:assert/strict';
import {voiceEnvironment,DictationPlayer} from '../web/player.js';
const browser=(voices)=>({getVoices:()=>voices,speak(){},cancel(){},pause(){},resume(){}});
class Utterance {constructor(text){this.text=text;}}
test('카카오톡 웹뷰의 API 미지원은 기기 음성 미설치로 단정하지 않음',()=>{
 const info=voiceEnvironment(undefined,undefined,'Mozilla Android KAKAOTALK/26 INAPP');
 assert.equal(info.supported,false);assert.equal(info.embedded,true);assert.equal(info.android,true);assert.match(info.message,/Chrome/);assert.doesNotMatch(info.message,/기기에.*없/);
 const p=new DictationPlayer(undefined,undefined,()=>{},()=>{});assert.doesNotThrow(()=>p.stop());assert.throws(()=>p.start([{text:'한글'}],1,2,10),/브라우저/);
});
test('음성 목록 지연과 한국어 음성 준비를 구분',()=>{
 const synth=browser([]);assert.match(voiceEnvironment(synth,Utterance,'Chrome Android').message,/아직 준비/);
 synth.getVoices=()=>[{lang:'ko-KR'}];assert.equal(voiceEnvironment(synth,Utterance,'Chrome Android').voices.length,1);
});
test('카카오톡이라도 한국어 음성을 지원하면 사용 가능',()=>{
 const info=voiceEnvironment(browser([{lang:'ko_KR'}]),Utterance,'Android KAKAOTALK');assert.equal(info.embedded,true);assert.equal(info.supported,true);assert.match(info.message,/준비되었/);
});
