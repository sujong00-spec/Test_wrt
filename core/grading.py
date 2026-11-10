"""批改：把「该写的」和「孩子写的（识别结果）」对齐并判对错。

设计原则：
  - 判错要保守，宁可疑（待定）也不错判——家长一定要能复核修订；
  - 对齐用相似度做，孩子跳着写、漏写一条也能对上；
  - 判定只看「归一化后是否完全一致」，不留模糊地带。
"""

import difflib
import re

CJK_RE = re.compile(r'[\u4e00-\u9fa5]')
LATIN_RE = re.compile(r'[A-Za-z]')
PUNCT_RE = re.compile(r'[\s，。！？；：、“”‘’（）()《》〈〉,\.!\?;:\'"\[\]【】…—\-·]')

VERDICT_LABEL = {
    'correct': '对',
    'wrong': '错',
    'missing': '没写',
    'unknown': '待定',
}


def normalize(text, lang='zh'):
    """去掉标点、空格、大小写差异，只留要看的字。"""
    t = '' if text is None else str(text)
    t = PUNCT_RE.sub('', t)
    t = t.replace('，', '').replace('。', '')
    if lang == 'en':
        t = t.lower()
    return t


def count_chars(text):
    """返回 (字数, 英文单词数)：中文数字符，英文数字母。"""
    t = '' if text is None else str(text)
    if LATIN_RE.search(t) and not CJK_RE.search(t):
        return len(LATIN_RE.findall(t)), len([w for w in re.split(r'\s+', t.strip()) if w])
    return len(CJK_RE.findall(t)), 0


def lines_to_candidates(raw_lines):
    """识别出来的原始行 -> 干净的候选答案（去序号、去控件符号）。"""
    out = []
    for line in raw_lines or []:
        s = '' if line is None else str(line)
        s = re.sub(r'^\s*[\d一二三四五六七八九十]{1,3}\s*[.、．)）:：]?\s*', '', s)
        s = re.sub(r'^\s*[（(【\[]\s*[\d一二三四五六七八九十]{1,3}\s*[）)】\]]\s*', '', s)
        s = s.strip(' 　\t.。，,;；:：')
        if s:
            out.append(s)
    return out


def align(expected_items, written_lines, lang='zh'):
    """把期望条目和识别行配对。

    期望：[(index, text), ...]；written_lines：识别出的行（已清洗）。
    返回 {index: written_text or None}
    """
    pairs = {}
    used = set()
    # 先按位置粗略配对，再用相似度把错位的拉回来
    for pos, (idx, text) in enumerate(expected_items):
        want = normalize(text, lang)
        best, best_ratio = None, 0.0
        for j in range(len(written_lines)):
            if j in used:
                continue
            if j > pos + 3:                      # 只看附近，避免整篇乱配
                break
            cand = normalize(written_lines[j], lang)
            if not cand:
                continue
            ratio = difflib.SequenceMatcher(None, want, cand).ratio()
            if want and cand == want:
                best, best_ratio = j, 2.0
                break
            if ratio > best_ratio:
                best, best_ratio = j, ratio
        if best is not None and best_ratio >= 0.34:
            pairs[idx] = written_lines[best]
            used.add(best)
        else:
            pairs[idx] = None
    return pairs


def grade_item(expected, written, lang='zh'):
    """单条判定。"""
    if written is None or str(written).strip() == '':
        return 'missing'
    if normalize(written, lang) == normalize(expected, lang):
        return 'correct'
    return 'wrong'


def diff_hint(expected, written, lang='zh'):
    """给家长看的差异说明（哪个字不对）。"""
    a, b = normalize(expected, lang), normalize(written, lang)
    if not b:
        return '没有写到'
    if not a:
        return '多写了内容'
    if a == b:
        return ''
    sm = difflib.SequenceMatcher(None, a, b)
    extra, lost = [], []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag in ('replace', 'delete'):
            lost.append(a[i1:i2])
        if tag in ('replace', 'insert'):
            extra.append(b[j1:j2])
    parts = []
    if lost:
        parts.append('少了「%s」' % '」「'.join(x for x in lost if x))
    if extra:
        parts.append('多/错了「%s」' % '」「'.join(x for x in extra if x))
    return '，'.join(parts)


def grade_session(items, raw_lines, lang='zh'):
    """整轮批改：items=[{'text','kind','lang'}...]，raw_lines=识别出的行。

    返回 [{'index','expected','written','verdict','hint'}]
    """
    lines = lines_to_candidates(raw_lines)
    expected = [(i, it.get('text', '')) for i, it in enumerate(items)]
    pairs = align(expected, lines, lang)
    out = []
    for i, text in expected:
        written = pairs.get(i)
        verdict = grade_item(text, written, lang)
        out.append({'index': i, 'expected': text, 'written': written or '',
                    'verdict': verdict,
                    'hint': diff_hint(text, written, lang) if verdict == 'wrong' else ''})
    return out


def merge_vision(items, rows, lang='zh'):
    """视觉模型的判定结果补齐成整轮：没给到的条目记为待定。"""
    by_index = {}
    for r in rows or []:
        try:
            by_index[int(r.get('index', -1))] = r
        except (TypeError, ValueError):
            continue
    out = []
    for i, it in enumerate(items):
        text = it.get('text', '')
        row = by_index.get(i)
        if row is None:
            out.append({'index': i, 'expected': text, 'written': '', 'verdict': 'unknown', 'hint': ''})
            continue
        written = str(row.get('written', ''))
        verdict = row.get('verdict') or 'unknown'
        out.append({'index': i, 'expected': text, 'written': written, 'verdict': verdict,
                    'hint': diff_hint(text, written, lang) if verdict == 'wrong' else ''})
    return out


def summarize(gradings):
    """一次批改的统计：对 / 错 / 没写 / 待定 / 正确率。"""
    counts = {'correct': 0, 'wrong': 0, 'missing': 0, 'unknown': 0}
    for g in gradings or []:
        v = g.get('verdict') or 'unknown'
        counts[v] = counts.get(v, 0) + 1
    graded = counts['correct'] + counts['wrong'] + counts['missing']
    accuracy = round(counts['correct'] / graded * 100, 1) if graded else None
    return {'correct': counts['correct'], 'wrong': counts['wrong'],
            'missing': counts['missing'], 'unknown': counts['unknown'],
            'graded': graded, 'accuracy': accuracy}
