"""실제 server.py와 모바일 Chromium 검증. TTS는 제어 검증용 대역 사용."""
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

ROOT=Path(__file__).resolve().parent.parent
VOICE_STUB='''
window.spoken=[];
window.SpeechSynthesisUtterance=class {constructor(text){this.text=text;}};
Object.defineProperty(window,'speechSynthesis',{value:{
 getVoices(){return [{lang:'ko-KR',name:'테스트용 한국어'}]},
 addEventListener(){},pause(){window.voicePaused=true},resume(){window.voicePaused=false},cancel(){},
 speak(u){window.spoken.push({text:u.text,lang:u.lang,rate:u.rate});window.lastUtterance=u}
}});
'''

def main():
    with tempfile.TemporaryDirectory() as data:
        env={**os.environ,'DICTATION_DATA_DIR':data,'PYTHONUNBUFFERED':'1'}
        server=subprocess.Popen([sys.executable,'server.py','--port','8877'],cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        try:
            for _ in range(60):
                try:
                    with urllib.request.urlopen('http://127.0.0.1:8877/api/practice',timeout=1) as r:
                        assert len(json.load(r)['prompts'])==10
                    break
                except OSError:time.sleep(.1)
            else:raise AssertionError('서버 시작 실패')
            with sync_playwright() as p:
                browser=p.chromium.launch(executable_path='/usr/bin/chromium' if Path('/usr/bin/chromium').exists() else None,headless=True,args=['--no-sandbox'])
                page=browser.new_page(viewport={'width':390,'height':844},is_mobile=True,has_touch=True)
                errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                page.add_init_script(VOICE_STUB)
                page.goto('http://127.0.0.1:8877/')
                expect(page.locator('.prompt')).to_have_count(10)
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                page.locator('#nickname').fill('테스트 학생 가');page.locator('#student-form button').click()
                expect(page.locator('#message')).to_contain_text('등록했어요')
                first_student=page.locator('#student').input_value()
                page.locator('.prompt textarea').first.fill('한국어 문장을 또박또박 써요.')
                page.locator('#save-prompts').click();expect(page.locator('#message')).to_contain_text('저장했어요')
                page.reload();expect(page.locator('.prompt textarea').first).to_have_value('한국어 문장을 또박또박 써요.')
                page.locator('#student').select_option(first_student)
                page.locator('#select-none').click();page.locator('.prompt input').first.check()
                page.locator('#speed').select_option('0.7');page.locator('#start').click()
                expect(page.locator('#stop')).to_be_enabled();expect(page.locator('#prompts')).to_be_hidden()
                assert page.evaluate('spoken[0].lang')=='ko-KR'
                assert page.evaluate('spoken[0].rate')==.7
                page.evaluate('lastUtterance.onend()')
                page.locator('#pause').click();expect(page.locator('#pause')).to_have_text('계속 읽기')
                page.wait_for_timeout(1300);assert page.evaluate('spoken.length')==1
                page.locator('#pause').click();page.wait_for_function('spoken.length === 2')
                page.evaluate('lastUtterance.onend()');expect(page.locator('#review')).to_be_visible()
                page.locator('#review-items select').select_option('wrong');page.locator('#save-record').click()
                expect(page.locator('#message')).to_contain_text('학습 기록을 저장했어요')
                page.locator('[data-tab=history]').click();expect(page.locator('#records')).to_contain_text('다시 연습')
                page.locator('[data-tab=wrong]').click();expect(page.locator('#wrong-items .card')).to_have_count(1)
                page.locator('#wrong-items button').click();page.locator('#start').click()
                expect(page.locator('#stop')).to_be_enabled();page.locator('#stop').click()
                page.locator('#nickname').fill('테스트 학생 나');page.locator('#student-form button').click()
                expect(page.locator('#message')).to_contain_text('등록했어요')
                page.locator('[data-tab=history]').click();expect(page.locator('#records')).to_contain_text('아직 학습 기록이 없어요')
                page.locator('[data-tab=wrong]').click();expect(page.locator('#wrong-items .card')).to_have_count(0)
                # 한국어 음성 없음: 결과/진행 화면을 꾸며내지 않습니다.
                page.locator('[data-tab=practice]').click()
                page.evaluate('speechSynthesis.getVoices=()=>[]')
                page.locator('#start').click();expect(page.locator('#message')).to_contain_text('한국어 읽기 음성이 없습니다')
                expect(page.locator('#stop')).to_be_disabled()
                page.screenshot(path='/tmp/dictation-mobile.png',full_page=True)
                page.set_viewport_size({'width':820,'height':1180});assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                page.set_viewport_size({'width':1280,'height':900});assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                assert not errors,errors
                browser.close()
            # 서버를 다시 시작해도 같은 저장소를 읽습니다.
            server.terminate();server.wait(timeout=5)
            server=subprocess.Popen([sys.executable,'server.py','--port','8877'],cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
            for _ in range(60):
                try:
                    with urllib.request.urlopen('http://127.0.0.1:8877/api/practice?student='+first_student,timeout=1) as r:
                        assert len(json.load(r)['records'])==1
                    break
                except OSError:time.sleep(.1)
            else:raise AssertionError('서버 재시작 실패')
            print('실제 서버 시작/재시작·390/820/1280px·문장 수정·학생 분리·부모 확인·오답 재연습·TTS 제어 대역·음성 없음·브라우저 오류 없음: 통과')
        finally:
            server.terminate();server.wait(timeout=5)

if __name__=='__main__':main()
