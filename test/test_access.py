#!/usr/bin/env python3
"""访问口令自测：没口令必须什么都拿不到。

    python3 test/test_access.py
"""

import json
import sys
import time
import urllib.error
import urllib.request as ur
from http.cookiejar import CookieJar
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PORT = 8796
BASE = 'http://127.0.0.1:%d' % PORT
FAILS = []


def check(name, cond, detail=''):
    print(('通过  ' if cond else '不通过') + ' ' + name + (('  ' + str(detail)) if detail else ''))
    if not cond:
        FAILS.append(name)


def raw_get(path, opener=None, headers=None):
    req = ur.Request(BASE + path, headers=headers or {})
    op = opener or ur.build_opener()
    try:
        with op.open(req, timeout=20) as r:
            return r.status, r.read(), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read(), dict(e.headers)


def main():
    from server import build
    from core.webapp import serve

    app, cfg = build(PORT)
    if not app.runtime.access.enabled:
        app.runtime.access.enabled = True      # 口令默认关闭，这里强制打开来验证机制
    serve(app, '127.0.0.1', PORT)
    time.sleep(0.4)
    token = app.runtime.access.token
    check('口令已生成（32 位）', len(token) == 32 and all(c in '0123456789abcdef' for c in token))

    # 1. 没口令：页面给口令页，接口给 401
    code, body, _ = raw_get('/', headers={'Accept': 'text/html'})
    check('无口令首页=口令页', code == 200 and '접근 암호가 필요합니다'.encode() in body, code)
    code, body, _ = raw_get('/api/practice')
    check('无口令接口=401', code == 401, code)
    code, body, _ = raw_get('/f/dictation/app.css')
    check('无口令样式=401', code == 401, code)
    code, body, _ = raw_get('/api/practice')
    check('无口令清单=401', code == 401, code)

    # 2. 带 ?k=口令：放行并下发 cookie（跟随后能拿到页面）
    jar = CookieJar()
    op = ur.build_opener(ur.HTTPCookieProcessor(jar))
    code, body, headers = raw_get('/?k=' + token, opener=op)
    check('带口令链接放行', code == 200 and '오늘의 문장'.encode() in body, code)
    names = [c.name for c in jar]
    check('记住口令的 cookie', 'moxie_key' in names, names)

    # 3. cookie 之后接口可用
    code, body, _ = raw_get('/api/practice', opener=op)
    check('cookie 后接口可用', code == 200 and json.loads(body)['ok'], code)
    code, body, _ = raw_get('/f/dictation/app.js', opener=op)
    check('cookie 后静态文件可用', code == 200 and b'DictationPlayer' in body, code)

    # 4. 口令页提交
    def post_access(t):
        req = ur.Request(BASE + '/api/access', data=json.dumps({'token': t}).encode(),
                         headers={'Content-Type': 'application/json'})
        try:
            with ur.urlopen(req, timeout=20) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    app.runtime.access.clear()
    code, data = post_access('wrong-token')
    check('错口令被拒', code == 401 and not data.get('ok'), code)
    code, data = post_access(token)
    check('对口令通过', code == 200 and data.get('ok'), code)

    # 5. 连错会被挡
    app.runtime.access.clear()
    for _ in range(21):
        code, _ = post_access('nope')
    check('连续输错被限速', code == 429, code)

    # 6. 接口不再泄露本机路径
    code, body, _ = raw_get('/api/practice', opener=op)
    data = json.loads(body)
    check('功能列表不含本机路径', 'students' in data, list(data.keys()))

    # 8. 公网来访（模拟隧道注入的头）：必须有临时链接钥匙，且随隧道到期
    import secrets as _secrets
    from datetime import datetime, timedelta

    tmp = Path(ROOT) / 'cache' / '_test_tunnel.json'
    app.runtime.access.tunnel_file = tmp
    app.runtime.access._tunnel_cache = (0.0, {})
    cf = {'Cf-Connecting-Ip': '203.0.113.9', 'Cf-Ray': 'test'}

    code, body, _ = raw_get('/api/practice', headers=cf)
    check('外部无钥匙=401', code == 401, code)
    code, body, _ = raw_get('/', headers=dict(cf, Accept='text/html'))
    check('外部无钥匙只看到失效页', code == 200 and '만료'.encode() in body, code)

    tkey = _secrets.token_hex(16)
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(json.dumps({'url': 'https://x.trycloudflare.com', 'token': tkey,
                               'expiresAt': (datetime.now() + timedelta(minutes=30)).isoformat(
                                   timespec='seconds')}), encoding='utf-8')
    app.runtime.access._tunnel_cache = (0.0, {})
    code, body, _ = raw_get('/api/practice', headers=dict(cf, Cookie='moxie_key=' + tkey))
    check('外部带钥匙可用', code == 200, code)
    jar2 = CookieJar()
    op2 = ur.build_opener(ur.HTTPCookieProcessor(jar2))
    code, body, _ = raw_get('/?k=' + tkey, opener=op2, headers=cf)
    check('外部用带钥匙链接进得来', code == 200 and '오늘의 문장'.encode() in body, code)
    check('外部链接会记住钥匙', 'moxie_key' in [c.name for c in jar2], [c.name for c in jar2])
    code, body, _ = raw_get('/api/practice', headers=dict(cf, Cookie='moxie_key=' + tkey))
    check('外部不返回历史清单', json.loads(body)['records'] == [], json.loads(body).get('records'))

    # 钥匙过期后立刻作废
    tmp.write_text(json.dumps({'url': 'https://x.trycloudflare.com', 'token': tkey,
                               'expiresAt': (datetime.now() - timedelta(seconds=1)).isoformat(
                                   timespec='seconds')}), encoding='utf-8')
    app.runtime.access._tunnel_cache = (0.0, {})
    code, body, _ = raw_get('/api/practice', headers=dict(cf, Cookie='moxie_key=' + tkey))
    check('钥匙过期后不可用', code == 401, code)
    tmp.unlink(missing_ok=True)

    # 本机/局域网直连不受影响（口令关闭时）
    app.runtime.access.enabled = False
    code, body, _ = raw_get('/api/practice')
    check('局域网直连仍然直接可用', code == 200, code)

    # 9. 敏感文件取不到
    app.runtime.access.clear()
    for path in ('/config.json', '/data/secrets.env', '/data/baidu.json', '/voice/reference.wav',
                 '/f/dictation/../../config.json'):
        code, body, _ = raw_get(path, opener=op)
        leaked = token.encode() in body or b'api_key' in body.lower()
        check('取不到 %s' % path, code in (401, 403, 404) and not leaked, code)

    print()
    if FAILS:
        print('有 %d 项没通过：%s' % (len(FAILS), '、'.join(FAILS)))
        sys.exit(1)
    print('访问口令自测全部通过')


if __name__ == '__main__':
    main()
