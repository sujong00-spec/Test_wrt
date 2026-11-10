#!/usr/bin/env python3
"""默写档案自测：记录 → 上传批改 → 复核 → 错题本 → 能力评估。

    python3 test/test_records.py          # 会真的调识别接口（需要联网）
    python3 test/test_records.py --local  # 只测对齐/判定/统计，不联网
"""

import argparse
import json
import subprocess
import sys
import time
import urllib.request as ur
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))   # 同目录的 test_api 也要能导入

PORT = 8798
BASE = 'http://127.0.0.1:%d' % PORT
ANSWER = Path(__file__).resolve().parent / 'sample_answer.jpg'
FAILS = []


def check(name, cond, detail=''):
    print(('通过  ' if cond else '不通过') + ' ' + name + (('  ' + str(detail)) if detail else ''))
    if not cond:
        FAILS.append(name)


def make_answer():
    from core.tts import find_ffmpeg
    from test_api import first_font   # noqa: E402
    ff = find_ffmpeg()
    font = first_font()
    if not ff or not font or ANSWER.exists():
        return
    # 孩子写的：第一条对、第二条错、第三条没写、第四条对
    lines = """1. 春天
2. 花杂
4. 我们一起去公园。"""
    txt = Path('/tmp/_answer_lines.txt')
    txt.write_text(lines, encoding='utf-8')
    subprocess.run([ff, '-y', '-f', 'lavfi', '-i', 'color=c=white:s=900x700',
                    '-vf', ("drawtext=fontfile=%s:textfile=%s:fontcolor=black:fontsize=44:x=60:y=60:line_spacing=40"
                            % (font, txt)), '-frames:v', '1', str(ANSWER)], capture_output=True)


def post_json(path, obj):
    req = ur.Request(BASE + path, data=json.dumps(obj).encode(),
                     headers={'Content-Type': 'application/json'})
    with ur.urlopen(req, timeout=300) as r:
        return json.loads(r.read())


def get_json(path):
    with ur.urlopen(BASE + path, timeout=60) as r:
        return json.loads(r.read())


def post_image(path, data):
    req = ur.Request(BASE + path, data=data, headers={'Content-Type': 'image/jpeg'})
    with ur.urlopen(req, timeout=300) as r:
        return json.loads(r.read())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--local', action='store_true', help='不调识别接口，只测判定与统计')
    args = ap.parse_args()

    from core import grading as G
    from core.webapp import serve
    from legacy_runtime import build

    # 0. 纯逻辑：对齐与判定
    items = [{'text': '春天'}, {'text': '花朵'}, {'text': '小鸟在树上唱歌。'}, {'text': '我们一起去公园。'}]
    lines = ['1. 春天', '2. 花杂', '4. 我们一起去公园。']
    got = G.grade_session(items, lines, 'zh')
    check('对错判定', [g['verdict'] for g in got] == ['correct', 'wrong', 'missing', 'correct'], got)
    check('差异提示', bool(got[1]['hint']), got[1])
    check('统计汇总', G.summarize(got) == {'correct': 2, 'wrong': 1, 'missing': 1, 'unknown': 0,
                                        'graded': 4, 'accuracy': 50.0}, G.summarize(got))
    en = G.grade_session([{'text': 'apple'}, {'text': 'I like apples.'}],
                         ['apple', 'i like apple'], 'en')
    check('英文判定', [g['verdict'] for g in en] == ['correct', 'wrong'], en)
    check('字数统计（中）', G.count_chars('小鸟在树上唱歌。'), (7, 0))
    check('字数统计（英）', G.count_chars('I like apples.'), (12, 3))

    app, cfg = build(PORT)
    rt = app.runtime
    serve(app, '127.0.0.1', PORT)
    time.sleep(0.4)

    # 1. 记一轮默写
    started = post_json('/api/session/start', {
        'subject': 'zh', 'mode': 'manual', 'speed': 'normal', 'items': items})
    sid = started['session']['id']
    check('轮次能建', bool(sid))
    check('轮次统计字数', started['session']['char_count'] == 2 + 2 + 7 + 7,
          started['session']['char_count'])
    post_json('/api/session/finish', {'id': sid, 'durationSec': 132, 'completed': 1})
    rec = get_json('/api/records')['records'][0]
    check('记录里有日期/条数/字数/时长',
          rec['item_count'] == 4 and rec['char_count'] == 18 and rec['duration_sec'] == 132,
          {k: rec[k] for k in ('item_count', 'char_count', 'duration_sec', 'started_at')})

    # 2. 上传孩子写的纸 → 自动批改
    if not args.local:
        make_answer()
        if ANSWER.exists():
            res = post_image('/api/result?session=%d' % sid, ANSWER.read_bytes())
            verdicts = [g['verdict'] for g in res['gradings']]
            check('上传后自动批改', verdicts.count('correct') >= 2 and 'wrong' in verdicts, verdicts)
            check('批改结果带识别原文', any(g['written'] for g in res['gradings']),
                  [g['written'] for g in res['gradings']])
            check('批改统计', res['summary']['graded'] == 4, res['summary'])

            # 3. 家长复核：把判错的那条改回「对」
            patches = {}
            for g in res['gradings']:
                if g['verdict'] == 'wrong':
                    patches[str(g['id'])] = {'verdict': 'correct', 'written': g['expected']}
            out = post_json('/api/gradings/reflect',
                            {'resultId': res['resultId'], 'session': sid, 'patches': patches})
            check('复核修订生效', out['summary']['wrong'] == 0 and out['summary']['correct'] >= 3,
                  out['summary'])
            wb2 = get_json('/api/wrongbook')['items']
            check('改对的那条不再算错题',
                  not any(w['expected'] == '花朵' and w['session_id'] == sid for w in wb2),
                  [w['expected'] for w in wb2])
        else:
            check('测试答案图生成', False, '没有字体或 ffmpeg')

    # 4. 错题本
    post_json('/api/session/start', {'subject': 'en', 'items': [{'text': 'apple'}, {'text': 'banana'}]})
    wb = get_json('/api/wrongbook')['items']
    check('错题本能取到', isinstance(wb, list))

    # 5. 能力评估
    s = get_json('/api/stats?days=14')
    check('统计总量', s['totals']['sessions'] >= 2 and s['totals']['chars'] > 0, s['totals'])
    check('按天序列', len(s['daily']) == 14 and s['daily'][-1]['date'] == time.strftime('%Y-%m-%d'),
          s['daily'][-1])
    check('分类对比', set(s['by_subject'].keys()) == {'zh', 'en'}, s['by_subject'])

    print()
    if FAILS:
        print('有 %d 项没通过：%s' % (len(FAILS), '、'.join(FAILS)))
        sys.exit(1)
    print('默写档案自测全部通过')


if __name__ == '__main__':
    main()
