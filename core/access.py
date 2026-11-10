"""访问口令 / 外部访问防护。

两层，互相独立：

1. 外部来访（经公网隧道进来的请求）**一律**需要「临时链接密钥」。密钥由 `临时链接.py` 每次现生成，
   只写在 cache/tunnel.json 里，并且**随隧道一起到期**（隧道断 = 密钥失效）。
   你在 iPad 上只需点一次我发的链接，不用输任何东西；别人拿到裸地址只会看到 401。
2. 可选的固定口令（config.json → access.enabled）：家里纯局域网也想拦一道时才打开，默认关闭。

判定"外部"看隧道注入的请求头（Cf-Connecting-Ip / Cf-Ray / X-Forwarded-For）；局域网直连没有这些头，
所以家里用不受影响。
"""

import hmac
import json
import secrets
import threading
import time
from pathlib import Path

from .webapp import Response, json_response

COOKIE = 'moxie_key'
COOKIE_DAYS = 60
MAX_FAILS = 20
FAIL_WINDOW = 600

EXTERNAL_HEADERS = ('cf-connecting-ip', 'cf-ray', 'x-forwarded-for', 'x-real-ip')


GATE_PAGE = """<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="robots" content="noindex, nofollow">
<title>접근 암호가 필요합니다</title>
<style>
 :root { --ink:#1f2437; --soft:#6a7590; --accent:#f0761f; }
 * { box-sizing:border-box; -webkit-tap-highlight-color:transparent; }
 body { margin:0; min-height:100dvh; display:grid; place-items:center;
        background:#f3f7ff; color:var(--ink);
        font-family:"Yuanti SC","PingFang SC","Hiragino Sans GB","Microsoft YaHei",system-ui,sans-serif; }
 .card { width:min(92vw,420px); background:#fff; border-radius:28px; padding:28px 24px;
         box-shadow:0 12px 28px rgba(31,36,55,.09); }
 h1 { margin:0 0 8px; font-size:23px; }
 p { margin:0 0 18px; color:var(--soft); font-size:15px; line-height:1.6; }
 input { width:100%; font:inherit; font-size:17px; padding:15px 16px; border-radius:16px;
         border:1.5px solid #e2eaf8; background:#fbfcff; color:var(--ink); }
 button { width:100%; margin-top:14px; padding:17px; border:0; border-radius:16px;
          background:var(--accent); color:#fff; font:inherit; font-size:18px; font-weight:700; }
 .err { color:#d9483b; font-size:14px; min-height:20px; margin-top:12px; }
 .note { color:var(--soft); font-size:13px; margin-top:14px; line-height:1.6; }
</style></head><body>
<div class="card">
  <h1>접근 암호가 필요합니다</h1>
  <p>가족용 학습 도구입니다. 서버 실행 창이나 data/access.json에서 접근 암호를 확인해 주세요.</p>
  <input id="k" type="password" inputmode="latin" autocapitalize="off" autocomplete="off" placeholder="접근 암호">
  <button id="go">입장하기</button>
  <div class="err" id="err"></div>
  <div class="note">이 기기에서 암호를 60일 동안 기억합니다.</div>
</div>
<script>
 document.getElementById('go').onclick = async () => {
   const k = document.getElementById('k').value.trim();
   const err = document.getElementById('err');
   err.textContent = '';
   try {
     const r = await fetch('/api/access', { method:'POST', headers:{'Content-Type':'application/json'},
                                             body: JSON.stringify({ token: k }) });
     const d = await r.json().catch(() => ({}));
     if (r.ok && d.ok) { location.replace('/'); return; }
     err.textContent = d.error || '접근 암호를 확인해 주세요.';
   } catch (e) { err.textContent = '연결하지 못했어요. 네트워크를 확인해 주세요.'; }
 };
 document.getElementById('k').addEventListener('keydown', (e) => {
   if (e.key === 'Enter') document.getElementById('go').click();
 });
</script>
</body></html>
"""


EXTERNAL_PAGE = """<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="robots" content="noindex, nofollow">
<title>링크가 만료되었습니다</title>
<style>
 body { margin:0; min-height:100dvh; display:grid; place-items:center; background:#f3f7ff; color:#1f2437;
        font-family:"Yuanti SC","PingFang SC","Hiragino Sans GB","Microsoft YaHei",system-ui,sans-serif; }
 .card { width:min(92vw,430px); background:#fff; border-radius:28px; padding:28px 24px;
         box-shadow:0 12px 28px rgba(31,36,55,.09); }
 h1 { margin:0 0 10px; font-size:22px; }
 p { margin:0 0 10px; color:#6a7590; font-size:15px; line-height:1.65; }
</style></head><body>
<div class="card">
  <h1>이 링크는 만료되었습니다</h1>
  <p>임시 링크의 사용 기간이 끝났습니다.</p>
  <p>서버를 실행한 컴퓨터에서 새 링크를 받아 접속해 주세요.</p>
</div>
</body></html>
"""


class AccessGate:
    def __init__(self, root, enabled=True):
        self.root = Path(root)
        self.path = self.root / 'data' / 'access.json'
        self.tunnel_file = self.root / 'cache' / 'tunnel.json'
        self.enabled = bool(enabled)
        self.token = ''
        self._fails = {}
        self._lock = threading.Lock()
        self._tunnel_cache = (0.0, {})
        self._load()

    # ---------- 临时链接密钥（跟隧道一起到期） ----------

    def tunnel_session(self):
        """读 cache/tunnel.json：{token, expiresAt}。文件改了会自动重新读。"""
        try:
            mtime = self.tunnel_file.stat().st_mtime
        except OSError:
            return {}
        cached_at, cached = self._tunnel_cache
        if cached_at == mtime and cached:
            return cached
        try:
            data = json.loads(self.tunnel_file.read_text(encoding='utf-8'))
        except Exception:  # noqa: BLE001
            data = {}
        if not data.get('token') or not data.get('expiresAt'):
            data = {}
        self._tunnel_cache = (mtime, data)
        return data

    def tunnel_token_ok(self, given):
        session = self.tunnel_session()
        if not session:
            return False
        try:
            from datetime import datetime
            if datetime.now() >= datetime.fromisoformat(session['expiresAt']):
                return False
        except Exception:  # noqa: BLE001
            return False
        return hmac.compare_digest(str(given), session['token'])

    def is_external(self, req):
        return any(h in req.headers for h in EXTERNAL_HEADERS)

    def _load(self):
        data = {}
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding='utf-8'))
            except Exception:  # noqa: BLE001
                data = {}
        if not data.get('token'):
            data['token'] = secrets.token_hex(16)
            data.setdefault('enabled', True)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding='utf-8')
            try:
                self.path.chmod(0o600)
            except OSError:
                pass
        self.token = data['token']
        self.enabled = bool(data.get('enabled', True)) and self.enabled

    # ---------- 校验 ----------

    def verify(self, given):
        return bool(given) and hmac.compare_digest(str(given), self.token)

    def check(self, req):
        """返回 (是否放行, 需要下发的 cookie 值或空串)。"""
        param = req.q('k')
        cookie = self._cookie_of(req)

        # 外部（公网隧道）来访：必须有有效且在有效期内的临时链接密钥
        if self.is_external(req):
            if self.tunnel_token_ok(cookie):
                return True, ''
            if self.tunnel_token_ok(param):
                return True, param
            if self.enabled:
                if self.verify(cookie):
                    return True, ''
                if self.verify(param):
                    return True, param
            return False, ''

        # 局域网 / 本机直连：只有固定口令打开时才拦
        if not self.enabled:
            return True, ''
        if self.verify(cookie):
            return True, ''
        if self.verify(param):
            return True, param
        return False, ''

    def _cookie_of(self, req):
        raw = req.headers.get('cookie', '') or ''
        for part in raw.split(';'):
            if '=' in part:
                name, value = part.split('=', 1)
                if name.strip() == COOKIE:
                    return value.strip()
        return ''

    def cookie_header(self, value=None):
        return '%s=%s; Path=/; Max-Age=%d; SameSite=Lax; HttpOnly' % (
            COOKIE, value or self.token, COOKIE_DAYS * 86400)

    def token_url(self, base, value=None):
        return '%s/?k=%s' % (base.rstrip('/'), value or self.token)

    # ---------- 拦截 ----------

    def challenge(self, req):
        accept = req.headers.get('accept', '') or ''
        if self.is_external(req):
            page = EXTERNAL_PAGE
        else:
            page = GATE_PAGE
        if req.method in ('GET', 'HEAD') and ('text/html' in accept or req.path in ('/', '')):
            return Response(200, page, 'text/html; charset=utf-8',
                            {'Cache-Control': 'no-store', 'X-Robots-Tag': 'noindex, nofollow'})
        return json_response({'ok': False, 'error': '这个临时링크가 만료되었습니다或无效'}, 401)

    # ---------- 输错限速 ----------

    def allow_attempt(self, ip):
        now = time.time()
        with self._lock:
            cnt, first = self._fails.get(ip, (0, now))
            if now - first > FAIL_WINDOW:
                cnt, first = 0, now
            if cnt >= MAX_FAILS:
                self._fails[ip] = (cnt, first)
                return False
            self._fails[ip] = (cnt + 1, first)
            return True

    def note_success(self, ip):
        with self._lock:
            self._fails.pop(ip, None)

    def clear(self):
        with self._lock:
            self._fails.clear()

    # ---------- 直接换口令（本地用） ----------

    def rotate(self):
        self.token = secrets.token_hex(16)
        self.path.write_text(json.dumps({'token': self.token, 'enabled': self.enabled},
                                        ensure_ascii=False, indent=1), encoding='utf-8')
        return self.token
