"""默写档案：每一轮默写、每一次批改、错题本、能力评估的取数。

用 SQLite（Python 标准库自带），文件在 data/moxie.db，随时可以拷走备份。
"""

import json
import sqlite3
import threading
from datetime import datetime, timedelta
from pathlib import Path

from . import grading as G

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  subject TEXT, kind TEXT DEFAULT 'dictation',
  started_at TEXT, finished_at TEXT,
  item_count INTEGER, char_count INTEGER, word_count INTEGER,
  duration_sec INTEGER DEFAULT 0,
  mode TEXT, speed TEXT,
  completed INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id INTEGER, idx INTEGER, text TEXT, kind TEXT, lang TEXT, char_count INTEGER
);
CREATE TABLE IF NOT EXISTS results (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id INTEGER, created_at TEXT, method TEXT, note TEXT, image_path TEXT
);
CREATE TABLE IF NOT EXISTS gradings (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  result_id INTEGER, session_id INTEGER, item_id INTEGER,
  expected TEXT, written TEXT, verdict TEXT, method TEXT,
  confirmed INTEGER DEFAULT 0, updated_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_items_session ON items(session_id);
CREATE INDEX IF NOT EXISTS idx_gradings_session ON gradings(session_id);
CREATE INDEX IF NOT EXISTS idx_gradings_result ON gradings(result_id);
"""


def now_iso():
    return datetime.now().isoformat(timespec='seconds')


def today():
    return datetime.now().date()


class History:
    def __init__(self, root):
        self.path = Path(root) / 'data' / 'moxie.db'
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._conn.commit()

    def _exec(self, sql, args=()):
        with self._lock:
            cur = self._conn.execute(sql, args)
            self._conn.commit()
            return cur

    def _query(self, sql, args=()):
        with self._lock:
            return [dict(r) for r in self._conn.execute(sql, args).fetchall()]

    # ---------- 写入 ----------

    def start_session(self, items, subject='zh', mode='manual', speed='normal'):
        chars = words = 0
        for it in items:
            c, w = G.count_chars(it.get('text', ''))
            it['char_count'] = c
            chars += c
            words += w
        cur = self._exec(
            "INSERT INTO sessions (subject, started_at, item_count, char_count, word_count, mode, speed) "
            "VALUES (?,?,?,?,?,?,?)",
            (subject, now_iso(), len(items), chars, words, mode, speed))
        sid = cur.lastrowid
        for i, it in enumerate(items):
            self._exec("INSERT INTO items (session_id, idx, text, kind, lang, char_count) VALUES (?,?,?,?,?,?)",
                       (sid, i, it.get('text', ''), it.get('kind', 'word'),
                        it.get('lang', subject), it.get('char_count', 0)))
        return self.session(sid)

    def finish_session(self, session_id, duration_sec=0, completed=0):
        self._exec("UPDATE sessions SET finished_at=?, duration_sec=?, completed=? WHERE id=?",
                   (now_iso(), int(duration_sec or 0), 1 if completed else 0, session_id))
        return self.session(session_id)

    def save_result(self, session_id, gradings, method='ocr', note='', image_path=''):
        cur = self._exec("INSERT INTO results (session_id, created_at, method, note, image_path) "
                         "VALUES (?,?,?,?,?)",
                         (session_id, now_iso(), method, note, image_path))
        rid = cur.lastrowid
        items = {it['idx']: it for it in self.items(session_id)}
        for g in gradings:
            it = items.get(g.get('index'))
            self._exec(
                "INSERT INTO gradings (result_id, session_id, item_id, expected, written, verdict, method, confirmed, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (rid, session_id, it['id'] if it else None, g.get('expected', ''),
                 g.get('written', ''), g.get('verdict', 'unknown'), method, 0, now_iso()))
        return rid

    def update_gradings(self, result_id, patches):
        """家长复核：{grading_id: {'verdict':..., 'written':...}}"""
        n = 0
        rows = self._query("SELECT * FROM gradings WHERE result_id=?", (result_id,))
        by_id = {r['id']: r for r in rows}
        for gid, patch in (patches or {}).items():
            gid = int(gid)
            row = by_id.get(gid)
            if not row:
                continue
            verdict = patch.get('verdict') or row['verdict']
            written = patch.get('written', row['written'])
            if verdict not in ('correct', 'wrong', 'missing', 'unknown'):
                continue
            self._exec("UPDATE gradings SET verdict=?, written=?, confirmed=1, updated_at=? WHERE id=?",
                       (verdict, written, now_iso(), gid))
            n += 1
        if n:
            self._exec("UPDATE results SET note=? WHERE id=?", ('家长已复核', result_id))
        return n

    # ---------- 读取 ----------

    def session(self, session_id):
        rows = self._query("SELECT * FROM sessions WHERE id=?", (session_id,))
        return rows[0] if rows else None

    def items(self, session_id):
        return self._query("SELECT * FROM items WHERE session_id=? ORDER BY idx", (session_id,))

    def results(self, session_id):
        return self._query("SELECT * FROM results WHERE session_id=? ORDER BY id DESC", (session_id,))

    def gradings(self, result_id):
        return self._query("SELECT * FROM gradings WHERE result_id=? ORDER BY id", (result_id,))

    def latest_result(self, session_id):
        rows = self._query("SELECT * FROM results WHERE session_id=? ORDER BY id DESC LIMIT 1", (session_id,))
        return rows[0] if rows else None

    def result(self, result_id):
        rows = self._query("SELECT * FROM results WHERE id=?", (result_id,))
        return rows[0] if rows else None

    def latest_gradings(self, session_id):
        r = self.latest_result(session_id)
        return (r, self.gradings(r['id'])) if r else (None, [])

    def records(self, subject=None, limit=100, offset=0):
        args = []
        where = ''
        if subject in ('zh', 'en'):
            where = 'WHERE subject=?'
            args.append(subject)
        rows = self._query(
            "SELECT * FROM sessions %s ORDER BY id DESC LIMIT ? OFFSET ?" % where,
            tuple(args + [int(limit), int(offset)]))
        out = []
        for s in rows:
            r, gs = self.latest_gradings(s['id'])
            out.append({**s, 'result_id': r['id'] if r else None,
                        'confirmed': bool(r and r.get('note') == '家长已复核'),
                        'summary': G.summarize(gs) if gs else None})
        return out

    def detail(self, session_id):
        s = self.session(session_id)
        if not s:
            return None
        r, gs = self.latest_gradings(session_id)
        return {'session': s, 'items': self.items(session_id),
                'result': r, 'gradings': gs,
                'summary': G.summarize(gs) if gs else None}

    # ---------- 错题本 ----------

    def wrongbook(self, subject=None, limit=200):
        """错题本：只看每条题目的**最新**批改结果（家长改对了就不再算错）。"""
        args = []
        where = "WHERE g.verdict IN ('wrong','missing')"
        if subject in ('zh', 'en'):
            where += ' AND s.subject=?'
            args.append(subject)
        rows = self._query(
            "SELECT g.expected, g.written, g.verdict, g.updated_at, s.subject, s.id AS session_id "
            "FROM gradings g JOIN sessions s ON s.id = g.session_id "
            "WHERE g.id IN (SELECT MAX(id) FROM gradings GROUP BY session_id, item_id) "
            "  AND g.verdict IN ('wrong','missing') "
            + (' AND s.subject = ?' if subject in ('zh', 'en') else '') +
            " ORDER BY g.id DESC",
            tuple([subject] if subject in ('zh', 'en') else []))
        agg = {}
        for r in rows:
            key = (r['subject'], r['expected'])
            item = agg.setdefault(key, {'subject': r['subject'], 'expected': r['expected'],
                                        'times': 0, 'last_at': '', 'last_written': '',
                                        'session_id': r['session_id'],
                                        'verdicts': {'wrong': 0, 'missing': 0}})
            item['times'] += 1
            item['verdicts'][r['verdict']] = item['verdicts'].get(r['verdict'], 0) + 1
            if r['updated_at'] and r['updated_at'] > item['last_at']:
                item['last_at'] = r['updated_at']
                item['last_written'] = r['written']
                item['session_id'] = r['session_id']
        items = sorted(agg.values(), key=lambda x: (-x['times'], x['last_at']), reverse=False)
        items.sort(key=lambda x: (-x['times'], x['last_at']))
        return items[:int(limit)]

    # ---------- 能力评估 ----------

    def stats(self, days=14):
        sessions = self._query("SELECT * FROM sessions ORDER BY id")
        rows = []
        for s in sessions:
            r, gs = self.latest_gradings(s['id'])
            sm = G.summarize(gs) if gs else None
            rows.append({'date': (s['started_at'] or '')[:10], 'subject': s['subject'],
                         'items': s['item_count'] or 0, 'chars': s['char_count'] or 0,
                         'words': s['word_count'] or 0, 'duration': s['duration_sec'] or 0,
                         'completed': s['completed'] or 0, 'summary': sm})

        # 近 N 天
        span = []
        for i in range(days - 1, -1, -1):
            d = (today() - timedelta(days=i)).isoformat()
            same = [r for r in rows if r['date'] == d]
            grad = [r for r in same if r['summary'] and r['summary']['graded']]
            correct = sum(r['summary']['correct'] for r in grad)
            graded = sum(r['summary']['graded'] for r in grad)
            span.append({'date': d, 'sessions': len(same),
                         'items': sum(r['items'] for r in same),
                         'chars': sum(r['chars'] for r in same),
                         'words': sum(r['words'] for r in same),
                         'minutes': round(sum(r['duration'] for r in same) / 60.0, 1),
                         'accuracy': round(correct / graded * 100, 1) if graded else None})

        def block(subject):
            same = [r for r in rows if r['subject'] == subject]
            grad = [r for r in same if r['summary'] and r['summary']['graded']]
            correct = sum(r['summary']['correct'] for r in grad)
            graded = sum(r['summary']['graded'] for r in grad)
            return {'sessions': len(same),
                    'items': sum(r['items'] for r in same),
                    'chars': sum(r['chars'] for r in same),
                    'words': sum(r['words'] for r in same),
                    'minutes': round(sum(r['duration'] for r in same) / 60.0, 1),
                    'accuracy': round(correct / graded * 100, 1) if graded else None}

        # 连续打卡天数
        days_set = {r['date'] for r in rows if r['date']}
        streak = 0
        d = today()
        while d.isoformat() in days_set:
            streak += 1
            d -= timedelta(days=1)

        graded_all = [r for r in rows if r['summary'] and r['summary']['graded']]
        correct_all = sum(r['summary']['correct'] for r in graded_all)
        graded_n = sum(r['summary']['graded'] for r in graded_all)

        return {
            'totals': {
                'sessions': len(rows),
                'items': sum(r['items'] for r in rows),
                'chars': sum(r['chars'] for r in rows),
                'words': sum(r['words'] for r in rows),
                'minutes': round(sum(r['duration'] for r in rows) / 60.0, 1),
                'graded': graded_n,
                'correct': correct_all,
                'accuracy': round(correct_all / graded_n * 100, 1) if graded_n else None,
                'streak': streak,
                'graded_sessions': len(graded_all),
            },
            'daily': span,
            'by_subject': {'zh': block('zh'), 'en': block('en')},
            'wrong_top': self.wrongbook(limit=10),
        }
