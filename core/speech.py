"""朗读稿生成：把清单条目变成「念出来的话」。

规则（与旧版一致）：
  - 不读序号，只读内容
  - 词语：「请默写：春天」「春天」
  - 句子：「请默写：春天来了，花儿开了。」「请再听一遍：春天来了，花儿开了。」
  - 数字用中文读法；易读错的词换成同音字（只影响朗读，不影响显示）
"""

# 多音字 / 易读错词纠正：from = 原文，to = 送给语音引擎的同音写法
PRONUNCIATION = [
    ('重新', '虫新'), ('长城', '常城'), ('长袍', '常袍'), ('教书', '交书'),
    ('好奇', '号奇'), ('处理', '楚理'), ('当作', '荡作'), ('差不多', '岔不多'),
    ('弹琴', '谈琴'), ('薄弱', '脖弱'),
]

CN_DIGITS = ['零', '一', '二', '三', '四', '五', '六', '七', '八', '九']
CN_UNITS = ['', '十', '百', '千']
NUM_RE = None  # 见 digits_to_chinese


def read_integer(s, digit_by_digit=False):
    raw = str(s or '')
    t = raw.lstrip('0')
    if not t:
        return ''.join(CN_DIGITS[int(c)] for c in raw if c.isdigit())
    if digit_by_digit or len(t) > 4:
        return ''.join(CN_DIGITS[int(c)] for c in t)
    n = len(t)
    out = ''
    pending_zero = False
    for i, ch in enumerate(t):
        d = int(ch)
        unit = CN_UNITS[n - 1 - i]
        if d == 0:
            if out:
                pending_zero = True
            continue
        if pending_zero and out:
            out += '零'
        pending_zero = False
        if i == 0 and d == 1 and n == 2:
            out += unit
        else:
            out += CN_DIGITS[d] + unit
    return out


def read_number_token(token):
    t = str(token)
    if '.' in t:
        a, b = t.split('.', 1)
        return read_integer(a) + '点' + ''.join(CN_DIGITS[int(c)] for c in b if c.isdigit())
    return read_integer(t)


def digits_to_chinese(text):
    import re

    def repl(m):
        num, nxt = m.group(1), m.group(2) or ''
        if re.search(r'[年月日号时分秒]', nxt):
            return read_integer(num, True) + nxt
        return read_number_token(num) + nxt

    return re.sub(r'(\d+(?:\.\d+)?)(.)?', repl, '' if text is None else str(text))


def apply_pronunciation(text):
    out = '' if text is None else str(text)
    for frm, to in PRONUNCIATION:
        if frm in out:
            out = out.replace(frm, to)
    return out


def to_spoken(text):
    return digits_to_chinese(apply_pronunciation(text))


def split_clips(text, limit=60):
    """长文本按标点切成若干片，每片 <= limit 字（缩短单次合成时长，韵律更稳）。"""
    import re

    t = ('' if text is None else str(text)).strip()
    if not t:
        return []
    if len(t) <= limit:
        return [t]
    parts = re.findall(r'[^，。！？；：、…!?,;:]+[，。！？；：、…!?,;:]*', t) or [t]
    out, buf = [], ''
    for p in parts:
        if len(p) > limit:
            if buf:
                out.append(buf)
                buf = ''
            for i in range(0, len(p), limit):
                out.append(p[i:i + limit])
            continue
        if len(buf + p) > limit:
            out.append(buf)
            buf = p
        else:
            buf += p
    if buf:
        out.append(buf)
    return out


def build_segments(entry, phrase, gap_ms=700, lead_gap_ms=400, limit=60):
    """一条内容 -> 播放段列表。

    返回 [{'text': 要念的话, 'gapAfterMs': 这之后停多久}]，段内可能被切成多片。
    """
    body = to_spoken((entry or {}).get('text', ''))
    if not body:
        return []
    is_sentence = (entry or {}).get('kind') == 'sentence'
    lead = phrase.get('lead', '请默写：')
    again = phrase.get('again', '请再听一遍：')
    if is_sentence:
        segs = [{'text': lead + body, 'gapAfterMs': max(gap_ms, lead_gap_ms)},
                {'text': again + body, 'gapAfterMs': 0}]
    else:
        segs = [{'text': lead + body, 'gapAfterMs': max(gap_ms, lead_gap_ms)},
                {'text': body, 'gapAfterMs': 0}]
    out = []
    for s in segs:
        clips = split_clips(s['text'], limit)
        for i, c in enumerate(clips):
            out.append({'text': c, 'gapAfterMs': s['gapAfterMs'] if i == len(clips) - 1 else 120})
    return out


def preview(entry):
    """给家长看的预览文案（不是念出来的）。"""
    body = (entry or {}).get('text', '')
    if not body:
        return ''
    if (entry or {}).get('kind') == 'sentence':
        return '请默写：' + body + '　请再听一遍：' + body
    return '请默写：' + body + '　' + body
