"""한국어 받아쓰기: 로컬 SQLite 저장소와 1단계 API."""
import json
from contextlib import contextmanager
import sqlite3
from pathlib import Path
from .webapp import json_response

SENTENCES = ['아침에 일어나 이를 닦아요.', '학교에 가는 길에 꽃을 보았어요.', '친구와 사이좋게 놀아요.', '책을 읽으면 마음이 자라요.', '비가 오면 우산을 써요.', '엄마와 함께 시장에 갔어요.', '동생에게 장난감을 나누어 주었어요.', '하늘에 하얀 구름이 떠 있어요.', '밥을 먹기 전에 손을 씻어요.', '오늘도 즐거운 하루를 보냈어요.']

class PracticeStore:
    def __init__(self, root):
        self.path = Path(root) / 'data' / 'dictation.sqlite3'
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS students(id INTEGER PRIMARY KEY, name TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS prompts(id INTEGER PRIMARY KEY, text TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS sessions(id INTEGER PRIMARY KEY, student_id INTEGER NOT NULL REFERENCES students(id), created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')), items TEXT NOT NULL, outcomes TEXT NOT NULL, source TEXT NOT NULL DEFAULT 'parent');
            ''')
            db.executemany('INSERT OR IGNORE INTO prompts(id,text) VALUES(?,?)', enumerate(SENTENCES, 1))

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            with db:
                yield db
        finally:
            db.close()

    def state(self, student=None):
        with self.connect() as db:
            students = [dict(r) for r in db.execute('SELECT * FROM students ORDER BY id')]
            prompts = [dict(r) for r in db.execute('SELECT * FROM prompts ORDER BY id')]
            records = []
            wrong = []
            if student:
                if not db.execute('SELECT 1 FROM students WHERE id=?', (student,)).fetchone():
                    raise ValueError('학생을 다시 선택해 주세요.')
                for r in db.execute('SELECT * FROM sessions WHERE student_id=? ORDER BY id DESC', (student,)):
                    row = dict(r)
                    row['items'] = json.loads(row['items'])
                    row['outcomes'] = json.loads(row['outcomes'])
                    records.append(row)
                    for item, outcome in zip(row['items'], row['outcomes']):
                        if outcome == 'wrong':
                            wrong.append({**item, 'session_id': row['id'], 'created_at': row['created_at']})
            return {'students': students, 'prompts': prompts, 'records': records, 'wrongbook': wrong}

    def add_student(self, name):
        name = clean_text(name, 30, '학생 별명')
        with self.connect() as db:
            return db.execute('INSERT INTO students(name) VALUES(?)', (name,)).lastrowid

    def save_prompts(self, items):
        if not isinstance(items, list) or len(items) != 10:
            raise ValueError('문제는 10개를 모두 보내 주세요.')
        if any(not isinstance(i, dict) for i in items):
            raise ValueError('문제 형식을 확인해 주세요.')
        if {i.get('id') for i in items if type(i.get('id')) is int} != set(range(1, 11)):
            raise ValueError('문제 번호는 1번부터 10번까지여야 합니다.')
        rows = [(clean_text(i.get('text'), 200, '문장'), i['id']) for i in items]
        with self.connect() as db:
            db.executemany('UPDATE prompts SET text=? WHERE id=?', rows)

    def record(self, payload):
        student = payload.get('student_id')
        items, outcomes = payload.get('items'), payload.get('outcomes')
        if type(student) is not int:
            raise ValueError('학생을 선택해 주세요.')
        if not isinstance(items, list) or not 1 <= len(items) <= 10 or any(not isinstance(i, dict) for i in items):
            raise ValueError('연습 문장은 1개부터 10개까지 저장할 수 있습니다.')
        if not isinstance(outcomes, list) or len(items) != len(outcomes) or any(x not in ('unchecked', 'correct', 'wrong') for x in outcomes):
            raise ValueError('부모 확인 결과를 확인해 주세요.')
        snapshot = [{'text': clean_text(i.get('text'), 200, '문장')} for i in items]
        with self.connect() as db:
            if not db.execute('SELECT 1 FROM students WHERE id=?', (student,)).fetchone():
                raise ValueError('학생을 다시 선택해 주세요.')
            return db.execute('INSERT INTO sessions(student_id,items,outcomes) VALUES(?,?,?)',
                (student, json.dumps(snapshot, ensure_ascii=False), json.dumps(outcomes))).lastrowid


def clean_text(value, limit, label):
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > limit:
        raise ValueError(f'{label}: 1자부터 {limit}자까지 입력해 주세요.')
    return value.strip()


def build_routes(rt):
    store = rt.practice
    def endpoint(fn):
        def run(req):
            try:
                return json_response({'ok': True, **fn(req)})
            except (ValueError, TypeError, KeyError):
                return json_response({'ok': False, 'error': '입력 내용을 확인해 주세요. 학생 별명은 30자, 문장은 200자까지 입력할 수 있습니다.'}, 400)
        return run
    def payload(req):
        obj = json.loads(req.body.decode('utf-8'))
        if not isinstance(obj, dict):
            raise ValueError('잘못된 요청')
        return obj
    def access(req):
        try:
            token = payload(req).get('token', '')
            if not isinstance(token, str):
                raise ValueError
        except (ValueError, TypeError):
            return json_response({'ok': False, 'error': '접근 암호를 입력해 주세요.'}, 400)
        if not rt.access.allow_attempt(req.client):
            return json_response({'ok': False, 'error': '시도가 너무 많습니다. 10분 후 다시 시도해 주세요.'}, 429)
        if rt.access.verify(token):
            rt.access.note_success(req.client)
            return json_response({'ok': True}).with_header('Set-Cookie', rt.access.cookie_header())
        return json_response({'ok': False, 'error': '접근 암호를 확인해 주세요.'}, 401)
    return {
        ('GET', '/api/practice'): endpoint(lambda r: store.state(int(r.q('student')) if r.q('student') else None)),
        ('POST', '/api/students'): endpoint(lambda r: {'id': store.add_student(payload(r).get('name'))}),
        ('POST', '/api/prompts'): endpoint(lambda r: (store.save_prompts(payload(r).get('items')) or {})),
        ('POST', '/api/practice/record'): endpoint(lambda r: {'id': store.record(payload(r))}),
        ('POST', '/api/access'): access,
    }
