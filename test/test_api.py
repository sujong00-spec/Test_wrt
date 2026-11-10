#!/usr/bin/env python3
"""接口自测：真的起一个服务，真的认图、真的合成语音。

    python3 test/test_api.py            # 需要能上网（识别 + 语音都走外部服务）
    python3 test/test_api.py --no-voice # 只测接口和识别，跳过语音合成

顺带产出一张「测试作业纸」图片（test/sample_page.jpg），方便手工比对识别效果。
"""

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request as ur
from http.cookiejar import CookieJar
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PORT = 8791
BASE = 'http://127.0.0.1:%d' % PORT
SAMPLE = Path(__file__).resolve().parent / 'sample_page.jpg'
SAMPLE_EN = Path(__file__).resolve().parent / 'sample_page_en.jpg'

SAMPLE_LINES = """默写内容  姓名：小明
1. 春天
2. 花朵
3、小鸟在树上唱歌。
4. 我们一起去公园。
"""

SAMPLE_LINES_EN = """English Dictation  Name: Tom
1. apple
2. banana
3. I like apples.
4. How are you?
"""

FAILS = []
OPENER = None


def check(name, cond, detail=''):
    print(('通过  ' if cond else '不通过') + ' ' + name + (('  ' + str(detail)) if detail else ''))
    if not cond:
        FAILS.append(name)


FONT_CANDIDATES = [
    '/mnt/c/Windows/Fonts/simkai.ttf',
    '/System/Library/Fonts/Supplemental/Songti.ttc',
    '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
    '/usr/share/fonts/truetype/arphic/uming.ttc',
]


def first_font():
    for f in FONT_CANDIDATES:
        if Path(f).exists():
            return f
    return ''


def make_sample(path=SAMPLE, lines=SAMPLE_LINES, size='900x700'):
    from core.tts import find_ffmpeg
    ff = find_ffmpeg()
    font = first_font()
    if not ff or not font or Path(path).exists():
        return
    txt = Path('/tmp/_sample_lines_%s.txt' % Path(path).stem)
    txt.write_text(lines, encoding='utf-8')
    cmd = [ff, '-y', '-f', 'lavfi', '-i', 'color=c=white:s=%s' % size,
           '-vf', ("drawtext=fontfile=%s:textfile=%s:fontcolor=black:fontsize=44:x=60:y=60:line_spacing=38"
                   % (font, txt)), '-frames:v', '1', str(path)]
    subprocess.run(cmd, capture_output=True)


def post_json(path, obj):
    req = ur.Request(BASE + path, data=json.dumps(obj).encode(),
                     headers={'Content-Type': 'application/json'})
    with OPENER.open(req, timeout=300) as r:
        return json.loads(r.read())


def get_json(path):
    with OPENER.open(BASE + path, timeout=60) as r:
        return json.loads(r.read())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--no-voice', action='store_true')
    args = ap.parse_args()

    from legacy_runtime import build
    from core.webapp import serve

    app, cfg = build(PORT)
    serve(app, '127.0.0.1', PORT)
    time.sleep(0.4)

    # 没有访问口令时一律拒绝，然后带上口令换取 cookie
    global OPENER
    OPENER = ur.build_opener(ur.HTTPCookieProcessor(CookieJar()))
    gate_on = app.runtime.access.enabled
    try:
        ur.urlopen(BASE + '/api/settings', timeout=10)
        gate_code = 200
    except urllib.error.HTTPError as exc:
        gate_code = exc.code
    check('没有口令时接口被拒' if gate_on else '口令关闭时直接可用',
          gate_code == (401 if gate_on else 200), gate_code)
    OPENER.open(BASE + '/?k=' + app.runtime.access.token, timeout=10).read()

    # 页面
    with OPENER.open(BASE + '/', timeout=20) as r:
        html = r.read().decode('utf-8')
        final_url = r.geturl()
    check('首页能打开', '小学默写' in html and len(html) > 1000)
    check('首页跳到了功能页', final_url.endswith('/f/moxie/'), final_url)
    with OPENER.open(BASE + '/f/moxie/app.css', timeout=20) as r:
        css = r.read().decode('utf-8')
    check('样式能打开', '--accent' in css)
    with OPENER.open(BASE + '/f/moxie/app.js', timeout=20) as r:
        js = r.read().decode('utf-8')
    check('脚本能打开', 'function playItem' in js)

    feats = get_json('/api/features')
    check('功能列表接口', any(f['id'] == 'moxie' for f in feats['features']), feats['features'])

    st = get_json('/api/settings')
    check('设置接口', st['ok'] and 'mode' in st['settings'], st['settings'])

    # 手动输入
    data = post_json('/api/recognize', {'text': '1.春天\n2.花朵\n3、小鸟在树上唱歌。'})
    check('手工文字整理', [i['text'] for i in data['items']] == ['春天', '花朵', '小鸟在树上唱歌。'],
          data['items'])

    # 图片识别（中文）
    make_sample()
    if SAMPLE.exists():
        img = SAMPLE.read_bytes()
        req = ur.Request(BASE + '/api/recognize', data=img, headers={'Content-Type': 'image/jpeg'})
        with OPENER.open(req, timeout=300) as r:
            rec = json.loads(r.read())
        texts = [i['text'] for i in rec['items']]
        check('图片识别出 4 条', len(texts) >= 4, texts)
        check('图片识别内容对', '春天' in texts and any('小鸟' in t for t in texts), texts)
        items = rec['items']
    else:
        items = data['items']

    # 图片识别（英文分类）
    make_sample(SAMPLE_EN, SAMPLE_LINES_EN)
    if SAMPLE_EN.exists():
        img = SAMPLE_EN.read_bytes()
        req = ur.Request(BASE + '/api/recognize?lang=en', data=img,
                         headers={'Content-Type': 'image/jpeg'})
        with OPENER.open(req, timeout=300) as r:
            rec_en = json.loads(r.read())
        texts_en = [i['text'] for i in rec_en['items']]
        check('英文图片识别出 4 条', len(texts_en) >= 4, texts_en)
        check('英文单词没被当拼音删掉', 'apple' in texts_en and 'banana' in texts_en, texts_en)
        check('英文句子识别对', any('I like apples' in t for t in texts_en), texts_en)
        check('英文条目分类标记', all(i['lang'] == 'en' for i in rec_en['items']), rec_en['items'][0])
        check('英文句子判为句子',
              [i['kind'] for i in rec_en['items'] if 'apple' in i['text'] and 'like' in i['text']]
              == ['sentence'],
              [i['kind'] for i in rec_en['items']])

    # 英文手动输入 + 朗读方案
    en = post_json('/api/recognize', {'text': 'apple\nI like apples.', 'lang': 'en'})
    check('英文手动输入', [i['text'] for i in en['items']] == ['apple', 'I like apples.'], en['items'])
    plan_en = post_json('/api/plan', {'items': en['items'], 'speed': 'normal', 'mode': 'manual'})
    check('英文朗读方案两段',
          [s['text'] for s in plan_en['items'][0]['steps']] == ['请默写：apple', 'apple'],
          plan_en['items'][0]['steps'])

    # 清单存档
    post_json('/api/list', {'name': '自测', 'items': items, 'snapshot': True})
    cur = get_json('/api/list')
    check('清单能存能取', len(cur['list']['items']) == len(items))

    # 朗读方案
    plan = post_json('/api/plan', {'items': items, 'speed': 'normal', 'mode': 'manual'})
    check('朗读方案-每条两段', all(len(it['steps']) == 2 for it in plan['items']), plan['items'][0]['steps'])
    check('朗读方案-有话术', plan['items'][0]['steps'][0]['text'].startswith('请默写：'))
    check('朗读方案-有关键字', all(s['key'] for it in plan['items'] for s in it['steps']))
    check('朗读方案-有结束语', bool(plan['phrases'].get('end')))

    if args.no_voice:
        print('\n跳过语音合成自测')
    else:
        one = {'item': {'text': '春天', 'kind': 'word'}}
        p = post_json('/api/plan', {'items': [one['item']], 'speed': 'normal'})
        texts = p['texts']
        post_json('/api/audio/ensure', {'texts': texts, 'speed': 'normal'})
        ok = False
        deadline = time.time() + 240
        while time.time() < deadline:
            s = post_json('/api/audio/status', {'texts': texts, 'speed': 'normal'})
            if s['ready'] >= s['total']:
                ok = True
                break
            if s.get('error'):
                print('  语音服务报错：', s['error'])
                break
            time.sleep(3)
        check('语音合成完成', ok)
        if ok:
            key = p['items'][0]['steps'][0]['key']
            with OPENER.open(BASE + '/api/audio?key=' + key, timeout=60) as r:
                audio = r.read()
                ctype = r.headers.get_content_type()
            check('语音能下载', len(audio) > 5000 and ctype in ('audio/mpeg', 'audio/wav'),
                  '%d 字节 %s' % (len(audio), ctype))

    print()
    if FAILS:
        print('有 %d 项没通过：%s' % (len(FAILS), '、'.join(FAILS)))
        sys.exit(1)
    print('接口自测全部通过')


if __name__ == '__main__':
    main()
