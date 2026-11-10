"""极简 Web 应用骨架（只用标准库）：路由、静态文件、功能注册。

「加一个新学习功能」的做法见 README：在 features/ 下新建一个包，
在 feature.json 里写清名字和入口，再实现 register(app) 即可。
"""

import json
import mimetypes
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse


class Response:
    def __init__(self, status=200, body=b'', content_type='text/plain; charset=utf-8', headers=None):
        self.status = status
        if isinstance(body, str):
            body = body.encode('utf-8')
        self.body = body
        self.content_type = content_type
        self.headers = headers or {}

    def with_header(self, key, value):
        self.headers[key] = value
        return self


def json_response(obj, status=200):
    return Response(status, json.dumps(obj, ensure_ascii=False),
                    'application/json; charset=utf-8', {'Cache-Control': 'no-store'})


def text_response(text, status=200):
    return Response(status, text, 'text/plain; charset=utf-8')


class Request:
    def __init__(self, method, path, query, headers, body, client):
        self.method = method
        self.path = path
        self.query = query
        self.headers = headers
        self.body = body
        self.client = client

    def q(self, name, default=None):
        v = self.query.get(name)
        return v[0] if v else default

    def json(self):
        if not self.body:
            return {}
        try:
            return json.loads(self.body.decode('utf-8'))
        except Exception:  # noqa: BLE001
            return {}


class App:
    def __init__(self, cfg, root, runtime):
        self.cfg = cfg
        self.root = Path(root)
        self.runtime = runtime          # 共享对象（语音、识别、存档…）
        self.routes = {}                # (method, path) -> handler
        self.statics = []               # (prefix, directory)
        self.features = []              # 已注册功能
        self.default_feature = cfg.get('server', {}).get('default_feature', 'moxie')

    # ---------- 注册 ----------

    def route(self, method, path, handler=None):
        def deco(fn):
            self.routes[(method.upper(), path)] = fn
            return fn
        return deco(handler) if handler else deco

    def get(self, path, handler=None):
        return self.route('GET', path, handler)

    def post(self, path, handler=None):
        return self.route('POST', path, handler)

    def static(self, prefix, directory):
        self.statics.append((prefix.rstrip('/') + '/', Path(directory)))

    def add_feature(self, module):
        routes = getattr(module, 'ROUTES', None)
        if callable(routes):
            routes = routes(self.runtime)
        self.routes.update(routes or {})
        for prefix, directory in getattr(module, 'STATICS', []):
            self.static(prefix, directory)
        meta = getattr(module, 'META', None)
        if meta:
            self.features.append(meta)
        hooks = getattr(module, 'on_start', None)
        if hooks:
            hooks(self)
        return module

    # ---------- 请求处理 ----------

    def handle(self, req):
        # 外部来访一律要临时链接密钥；可选的固定口令按 config 决定是否拦局域网
        gate = getattr(self.runtime, 'access', None)
        cookie_value = ''
        if gate is not None and req.path not in ('/api/access',):
            ok, cookie_value = gate.check(req)
            if not ok:
                return gate.challenge(req)
        resp = self._dispatch(req)
        if cookie_value and gate is not None:
            resp.with_header('Set-Cookie', gate.cookie_header(cookie_value))
            resp.with_header('Cache-Control', 'no-store')
        return resp

    def _dispatch(self, req):
        # 静态文件
        for prefix, directory in self.statics:
            if req.path.startswith(prefix):
                return self._serve_file(directory, req.path[len(prefix):])
        if req.path == '/':
            return Response(302, '', 'text/plain; charset=utf-8',
                            {'Location': '/f/%s/' % self.default_feature})
        if req.path.endswith('/') and req.path.strip('/').startswith('f/'):
            rest = req.path.strip('/')[2:].strip('/')
            if rest in [f.get('id') for f in self.features]:
                return self._serve_feature_root(rest)
        handler = self.routes.get((req.method, req.path))
        if handler:
            try:
                return handler(req)
            except Exception as exc:  # noqa: BLE001
                traceback.print_exc()
                return json_response({'ok': False, 'error': '요청을 처리하지 못했습니다. 서버 실행 창을 확인해 주세요.'}, 500)
        return json_response({'ok': False, 'error': '요청한 기능이 없습니다: %s' % req.path}, 404)

    def _serve_feature_root(self, feature_id=None):
        fid = feature_id or self.default_feature
        for f in self.features:
            if f.get('id') == fid:
                page = f.get('page')
                if page and Path(page).exists():
                    return Response(200, Path(page).read_bytes(), 'text/html; charset=utf-8',
                                    {'Cache-Control': 'no-store'})
        return Response(404, '요청한 화면이 없습니다', 'text/plain; charset=utf-8')

    def _serve_file(self, directory, rel):
        rel = unquote(rel).lstrip('/')
        target = (directory / rel).resolve()
        try:
            target.relative_to(directory.resolve())
        except ValueError:
            return Response(403, '접근할 수 없습니다.')
        if target.is_dir():
            target = target / 'index.html'
        if not target.exists():
            return Response(404, '파일이 없습니다.')
        ctype = mimetypes.guess_type(str(target))[0] or 'application/octet-stream'
        if ctype.startswith('text/') or ctype in ('application/javascript',):
            ctype += '; charset=utf-8'
        return Response(200, target.read_bytes(), ctype, {'Cache-Control': 'no-cache'})


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    app = None

    def log_message(self, fmt, *args):
        pass

    def _run(self, method):
        parsed = urlparse(self.path)
        try:
            length = int(self.headers.get('Content-Length') or 0)
            if not 0 <= length <= 65536:
                raise ValueError
        except ValueError:
            self.send_error(413, 'Request body too large or invalid')
            self.close_connection = True
            return
        body = self.rfile.read(length) if length else b''
        req = Request(method, unquote(parsed.path), parse_qs(parsed.query),
                      {k.lower(): v for k, v in self.headers.items()}, body, self.client_address[0])
        try:
            resp = self.app.handle(req)
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            resp = json_response({'ok': False, 'error': '요청을 처리하지 못했습니다. 서버 실행 창을 확인해 주세요.'}, 500)
        try:
            self.send_response(resp.status)
            self.send_header('Content-Type', resp.content_type)
            self.send_header('Content-Length', str(len(resp.body)))
            self.send_header('X-Robots-Tag', 'noindex, nofollow')
            for k, v in resp.headers.items():
                self.send_header(k, v)
            self.end_headers()
            if method != 'HEAD':
                self.wfile.write(resp.body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        self._run('GET')

    def do_POST(self):
        self._run('POST')

    def do_HEAD(self):
        self._run('HEAD')


def serve(app, host, port):
    Handler.app = app
    httpd = ThreadingHTTPServer((host, port), Handler)
    httpd.daemon_threads = True
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return httpd
