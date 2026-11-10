"""本地数据：设置与清单的保存/读取（一个 JSON 文件，随时可以手工看）。"""

import json
import threading
import time
from pathlib import Path


class Store:
    def __init__(self, root):
        self.path = Path(root) / 'data' / 'state.json'
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._data = self._load()

    def _load(self):
        if self.path.exists():
            try:
                return json.loads(self.path.read_text(encoding='utf-8'))
            except Exception:  # noqa: BLE001
                pass
        return {'settings': {}, 'current': {'name': '', 'items': []}, 'history': []}

    def _flush(self):
        tmp = self.path.with_suffix('.tmp')
        tmp.write_text(json.dumps(self._data, ensure_ascii=False, indent=1), encoding='utf-8')
        tmp.replace(self.path)

    def get(self, key, default=None):
        with self._lock:
            return self._data.get(key, default)

    def set(self, key, value):
        with self._lock:
            self._data[key] = value
            self._flush()
        return value

    # ---------- 常用快捷方法 ----------

    def settings(self, defaults):
        with self._lock:
            cur = dict(defaults)
            cur.update(self._data.get('settings') or {})
            return cur

    def save_settings(self, patch, defaults):
        with self._lock:
            cur = dict(defaults)
            cur.update(self._data.get('settings') or {})
            cur.update({k: v for k, v in (patch or {}).items() if k in defaults})
            self._data['settings'] = cur
            self._flush()
            return cur

    def current(self):
        with self._lock:
            return self._data.get('current') or {'name': '', 'items': []}

    def save_current(self, name, items):
        with self._lock:
            self._data['current'] = {'name': name or '', 'items': items or [],
                                     'savedAt': int(time.time())}
            self._flush()
            return self._data['current']

    def add_history(self, name, items):
        with self._lock:
            hist = self._data.get('history') or []
            hist = [h for h in hist if h.get('name') != name]
            hist.insert(0, {'name': name, 'items': items, 'savedAt': int(time.time())})
            self._data['history'] = hist[:30]
            self._flush()
            return self._data['history']

    def history(self):
        with self._lock:
            return self._data.get('history') or []
