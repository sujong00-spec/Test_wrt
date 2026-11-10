#!/usr/bin/env python3
"""文字整理与朗读稿的自测（不联网、不依赖服务）。

    python3 test/test_text.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import speech, textclean  # noqa: E402

FAILS = []


def check(name, got, want):
    if got != want:
        FAILS.append('%s\n  期望：%r\n  实际：%r' % (name, want, got))


# ---------- 序号 / 拼音 / 表头 ----------

raw = """默写内容  姓名：小明
1. 春天
2、花朵
(3) 小鸟
（4）大树
④ 太阳
一、月亮
二、星星
"""
got = [i['text'] for i in textclean.parse(raw)]
check('去序号去表头', got, ['春天', '花朵', '小鸟', '大树', '太阳', '月亮', '星星'])

got = [i['text'] for i in textclean.parse('春天  chun tian\n花朵')]
check('去拼音', got, ['春天', '花朵'])

got = [i['text'] for i in textclean.parse('春天（chun tian）\n花朵【注释】')]
check('去括号注释', got, ['春天', '花朵'])

# ---------- 词语 / 句子切分 ----------

got = [i['text'] for i in textclean.parse('春天 花朵 太阳')]
check('空格分词', got, ['春天 花朵 太阳'])

got = [i['text'] for i in textclean.parse('苹果、香蕉、葡萄')]
check('顿号分词', got, ['苹果', '香蕉', '葡萄'])

got = [i['text'] for i in textclean.parse('春天来了，花儿开了。小鸟在唱歌。')]
check('句子切分', got, ['春天来了，花儿开了。', '小鸟在唱歌。'])

got = [i['kind'] for i in textclean.parse('春天\n我们一起去公园。\n花朵')]
check('词语句子判定', got, ['word', 'sentence', 'word'])

got = [i['text'] for i in textclean.parse('1.春天 2.花朵 3.太阳')]
check('行内序号', got, ['春天', '花朵', '太阳'])

# ---------- 朗读稿 ----------

check('数字读法-年份', speech.digits_to_chinese('1937年'), '一九三七年')
check('数字读法-数值', speech.digits_to_chinese('第15课'), '第一十五课'.replace('一十五', '十五'))
check('数字读法-小数', speech.digits_to_chinese('3.5米'), '三点五米')
check('多音字纠音', speech.to_spoken('重新开始'), '虫新开始')

phrase = {'lead': '请默写：', 'again': '请再听一遍：'}
segs = speech.build_segments({'text': '春天', 'kind': 'word'}, phrase)
check('词语念两遍', [s['text'] for s in segs], ['请默写：春天', '春天'])

segs = speech.build_segments({'text': '小鸟在唱歌。', 'kind': 'sentence'}, phrase)
check('句子念两遍', [s['text'] for s in segs], ['请默写：小鸟在唱歌。', '请再听一遍：小鸟在唱歌。'])

long_text = '这是一个很长的句子，' * 6 + '结束。'
segs = speech.build_segments({'text': long_text, 'kind': 'sentence'}, phrase, limit=20)
check('长句切片', all(len(s['text']) <= 20 for s in segs), True)

# ---------- 英文 ----------

def texts(raw):
    return [i['text'] for i in textclean.parse(raw)]

got = [i['text'] for i in textclean.parse('apple\nbanana\norange')]
check('英文单词不丢', got, ['apple', 'banana', 'orange'])
check('英文条目标了语言', [i['lang'] for i in textclean.parse('apple\nbanana')], ['en', 'en'])

check('英文带序号', texts('1. apple\n2. banana\n3) orange'), ['apple', 'banana', 'orange'])
check('英文句子算句子',
      [i['kind'] for i in textclean.parse('I like apples.\nThank you.')], ['sentence', 'sentence'])
check('英文表头丢掉', texts('English Dictation  Name: Tom\n1. apple'), ['apple'])
check('英文句子不被切开', texts('I like apples.'), ['I like apples.'])
check('英文句中逗号不切', texts('Hello, Tom. How are you?'), ['Hello, Tom.', 'How are you?'])
check('英文逗号词表切开', texts('apple, banana, orange, pear'), ['apple', 'banana', 'orange', 'pear'])
check('中英对照保留两边', texts('apple 苹果\nbanana 香蕉'), ['apple 苹果', 'banana 香蕉'])
check('中文材料仍删拼音', texts('春天 chun tian\n花朵'), ['春天', '花朵'])
check('带声调拼音一律删', texts('chūn tiān\n春天'), ['春天'])
check('中文默写不受影响', texts('默写内容  姓名：小明\n1. 春天\n2、花朵'), ['春天', '花朵'])
check('英文朗读稿',
      [s['text'] for s in speech.build_segments({'text': 'apple', 'kind': 'word'}, phrase)],
      ['请默写：apple', 'apple'])
check('英文句子朗读稿',
      [s['text'] for s in speech.build_segments({'text': 'I like apples.', 'kind': 'sentence'}, phrase)],
      ['请默写：I like apples.', '请再听一遍：I like apples.'])

# ---------- 输出 ----------

if FAILS:
    print('有 %d 项没通过：' % len(FAILS))
    for f in FAILS:
        print('- ' + f)
    sys.exit(1)
print('文字整理与朗读稿：全部通过')
