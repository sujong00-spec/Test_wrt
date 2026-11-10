import test from 'node:test';
import assert from 'node:assert/strict';
import {initialData,changeData,FAMILY_ID,wrongbook} from '../web/data.js';
import {DictationPlayer} from '../web/player.js';
test('학생 등록 없이 가족 공용 기록 저장, 반복해도 공용 항목은 한 개',()=>{
 let data=initialData();
 for(let i=0;i<2;i++)data=changeData(data,{type:'record.add',id:'family-'+i,student_id:FAMILY_ID,items:[{text:'우리집 문장'}],outcomes:['unchecked']}).data;
 assert.equal(data.students.length,1);assert.equal(data.students[0].id,FAMILY_ID);assert.equal(data.records.length,2);
});
test('이전 학생 기록 보존, 오답은 이전 학생별 확인을 유지',()=>{
 let data=changeData(initialData(),{type:'student.add',name:'이전 별명'},()=> 'old-student').data;
 data=changeData(data,{type:'record.add',id:'old',student_id:'old-student',items:[{text:'같은 문장'}],outcomes:['wrong']}).data;
 const original=JSON.stringify(data.records[0]);
 data=changeData(data,{type:'record.add',id:'new',student_id:FAMILY_ID,items:[{text:'같은 문장'}],outcomes:['correct']}).data;
 assert.equal(JSON.stringify(data.records[0]),original);assert.equal(wrongbook(data).length,1);assert.equal(wrongbook(data)[0].student_id,'old-student');
});
test('선택한 원래 번호와 읽는 문장을 화면 알림으로 전달',()=>{
 let current;const speech={getVoices:()=>[{lang:'ko-KR'}],speak(u){this.utterance=u;},cancel(){},pause(){},resume(){}};
 class Utterance {constructor(text){this.text=text;}}
 const player=new DictationPlayer(speech,Utterance,(text,state)=>current={text,state},()=>{});
 player.start([{text:'오 번 문장',number:5}],1,2,10);
 assert.match(current.text,/5번 문장/);assert.equal(current.state.text,'오 번 문장');assert.equal(current.state.number,5);assert.equal(current.state.turn,1);
 player.stop();
});
