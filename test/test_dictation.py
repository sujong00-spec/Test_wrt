"""외부 API 없이 저장소와 실제 HTTP 경로를 검증합니다."""
import json
import tempfile
import unittest
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from core.dictation import PracticeStore, SENTENCES, build_routes
from core.access import AccessGate
from core.webapp import App, serve
from features import load

ROOT = Path(__file__).resolve().parent.parent

class PracticeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = PracticeStore(self.tmp.name)
        self.student = self.store.add_student('연습 별명')

    def record(self, student=None, outcomes=None):
        return self.store.record({'student_id': student or self.student, 'items': [{'text': '안녕하세요.'}], 'outcomes': outcomes or ['unchecked']})

    def test_seed_and_persistence(self):
        self.assertEqual([x['text'] for x in self.store.state()['prompts']], SENTENCES)
        prompts=self.store.state()['prompts']; prompts[0]['text']='새 문장이에요.'
        self.store.save_prompts(prompts)
        self.assertEqual(PracticeStore(self.tmp.name).state()['prompts'][0]['text'], '새 문장이에요.')

    def test_no_invented_results(self):
        self.record()
        data=self.store.state(self.student)
        self.assertEqual(data['records'][0]['outcomes'], ['unchecked'])
        self.assertEqual(data['wrongbook'], [])
        self.assertNotIn('accuracy', data)

    def test_student_isolation_and_wrongbook(self):
        other=self.store.add_student('다른 별명')
        self.record(outcomes=['wrong']); self.record(student=other, outcomes=['correct'])
        self.assertEqual(len(self.store.state(self.student)['wrongbook']), 1)
        self.assertEqual(self.store.state(other)['wrongbook'], [])
        self.assertEqual(len(self.store.state(other)['records']), 1)

    def test_history_snapshot(self):
        self.record()
        prompts=self.store.state()['prompts']; prompts[0]['text']='수정된 문제'
        self.store.save_prompts(prompts)
        self.assertEqual(self.store.state(self.student)['records'][0]['items'], [{'text':'안녕하세요.'}])

    def test_validation_and_atomic_update(self):
        for name in ['', ' '*3, '별'*31, None, 123]:
            with self.assertRaises(ValueError): self.store.add_student(name)
        prompts=self.store.state()['prompts']; prompts[0]['text']='';
        with self.assertRaises(ValueError): self.store.save_prompts(prompts)
        self.assertEqual(self.store.state()['prompts'][0]['text'], SENTENCES[0])
        with self.assertRaises(ValueError): self.record(student=999)
        with self.assertRaises(ValueError): self.record(outcomes=['ai-correct'])
        with self.assertRaises(ValueError): self.store.save_prompts([{'id':1,'text':'가'}]*10)

    def test_concurrent_records(self):
        with ThreadPoolExecutor(max_workers=5) as pool:
            list(pool.map(lambda _: self.record(), range(10)))
        self.assertEqual(len(self.store.state(self.student)['records']), 10)

class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory()
        rt=SimpleNamespace(practice=PracticeStore(cls.tmp.name),access=AccessGate(cls.tmp.name,enabled=False))
        cls.app=App({'server':{'default_feature':'dictation'}}, ROOT, rt)
        cls.app.routes.update(build_routes(rt)); load(cls.app)
        cls.server=serve(cls.app, '127.0.0.1', 0)
        cls.base='http://127.0.0.1:'+str(cls.server.server_port)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.tmp.cleanup()

    def request(self,path,body=None):
        req=urllib.request.Request(self.base+path, data=body, headers={'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(req) as response:return response.status,response.read()
        except urllib.error.HTTPError as e:return e.code,e.read()

    def test_actual_page_and_api(self):
        status,body=self.request('/')
        self.assertEqual(status,200);self.assertIn('오늘의 문장'.encode(),body);self.assertIn(b'lang="ko"',body)
        status,body=self.request('/api/students',json.dumps({'name':'테스트 별명'}).encode())
        self.assertEqual(status,200);student=json.loads(body)['id']
        status,body=self.request('/api/practice/record',json.dumps({'student_id':student,'items':[{'text':'종이에 써요.'}],'outcomes':['wrong']}).encode())
        self.assertEqual(status,200)
        status,body=self.request('/api/practice?student='+str(student))
        self.assertEqual(len(json.loads(body)['wrongbook']),1)

    def test_removed_ai_and_private_files(self):
        for path in ['/api/recognize','/api/result','/api/result/vision','/api/plan']:
            self.assertEqual(self.request(path,b'photo')[0],404,path)
        for path in ['/config.json','/data/dictation.sqlite3','/f/moxie/','/f/dictation/../../config.json']:
            self.assertIn(self.request(path)[0],(403,404),path)

    def test_invalid_requests(self):
        for body in [b'not json',b'[]',b'null',b'{}',b'{"items":1}']:
            self.assertEqual(self.request('/api/prompts',body)[0],400,body)
        self.assertEqual(self.request('/api/practice?student=not-a-number')[0],400)
        self.assertEqual(self.request('/api/students',b'x'*65537)[0],413)

    def test_access_gate(self):
        self.app.runtime.access.enabled=True
        try:
            status,body=self.request('/api/practice');self.assertEqual(status,401)
            token=self.app.runtime.access.token
            self.assertEqual(self.request('/api/practice?k='+token)[0],200)
        finally:self.app.runtime.access.enabled=False

if __name__=='__main__':unittest.main()
