"""文字整理：把识别结果或手输文字整理成默写清单。

纯函数模块，不依赖任何网络与框架，可以直接跑单测。
规则：
  1. 去掉行首序号：1. / 1、 / （1） / 一、 / ① ...
  2. 去掉拼音：（chun tian）/ 行内 chun tian / 整行拼音（**只在中英混排以中文为主时才删，纯英文内容是正事**）
  3. 去掉括号注释：（ ）( ) 【 】[ ]（可嵌套）
  4. 词语按词语分条，句子按句子分条（中英文都支持）
  5. 姓名 / 日期 / 得分 / Name / Date / Unit 这类表头丢弃
"""

import re

CJK_RE = re.compile(r'[\u4e00-\u9fa5\u3400-\u4dbf]')
LATIN_RE = re.compile(r'[A-Za-z]')

PINYIN_LETTERS = ('a-zA-Z\u0101\u00e1\u01ce\u00e0\u0113\u00e9\u011b\u00e8'
                  '\u012b\u00ed\u01d0\u00ec\u014d\u00f3\u01d2\u00f2'
                  '\u016b\u00fa\u01d4\u00f9\u01d6\u01d8\u01da\u01dc\u00fc\u00ea')
PINYIN_RUN_RE = re.compile('[' + PINYIN_LETTERS + r']+[0-9]?')
# 带声调符号的字母串：一定是拼音，任何语言环境下都删（整串一起删，别只剩声母）
TONED_RUN_RE = re.compile('(?:[A-Za-z\u0101\u00e1\u01ce\u00e0\u0113\u00e9\u011b\u00e8'
                          '\u012b\u00ed\u01d0\u00ec\u014d\u00f3\u01d2\u00f2'
                          '\u016b\u00fa\u01d4\u00f9\u01d6\u01d8\u01da\u01dc\u00fc\u00ea]*'
                          '[\u0101\u00e1\u01ce\u00e0\u0113\u00e9\u011b\u00e8'
                          '\u012b\u00ed\u01d0\u00ec\u014d\u00f3\u01d2\u00f2'
                          '\u016b\u00fa\u01d4\u00f9\u01d6\u01d8\u01da\u01dc\u00fc\u00ea]'
                          '[A-Za-z\u0101\u00e1\u01ce\u00e0\u0113\u00e9\u011b\u00e8'
                          '\u012b\u00ed\u01d0\u00ec\u014d\u00f3\u01d2\u00f2'
                          '\u016b\u00fa\u01d4\u00f9\u01d6\u01d8\u01da\u01dc\u00fc\u00ea]*[0-9]?)')
BRACKET_RE = re.compile(r'[（(【\[][^（()）【\[\]】]*[）)】\]]')

LEADING_INDEX_RES = [
    re.compile(r'^[\s]*[\u2460-\u24ff\u3220-\u3229\u3251-\u325f\uff10-\uff19]{1,2}[\s]*[.、．)）]?'),
    re.compile(r'^[\s]*[（(【\[][一二三四五六七八九十百\d]{1,3}[）)】\]][\s]*'),
    re.compile(r'^[\s]*\d{1,3}[\s]*[.、，,：:。．·)）][\s]*'),
    re.compile(r'^[\s]*[一二三四五六七八九十百]{1,3}[\s]*[、，,.．:：)）][\s]*'),
]

INLINE_CIRCLED_RE = re.compile(r'(^|[\s。！？；;、，,])([\u2460-\u24ff\u3220-\u3229])[\s]*(?=[\u4e00-\u9fa5])')
INLINE_NUM_RE = re.compile(
    r'(^|[\s。！？；;、，,])([（(【\[]?(?:\d{1,3}|[一二三四五六七八九十百]{1,3})[）)】\]]?[\s]*[.、．)）])[\s]*(?=[\u4e00-\u9fa5A-Za-z])')

INSTRUCTION_PREFIX_RE = re.compile(
    '^(姓名|班级|学号|日期|时间|得分|分数|成绩|默写内容|听写内容|默写|听写|抄写|看拼音写词语|看拼音|写词语|写句子|'
    '组词|造句|填空|选择|判断|连线|古诗|课文|词语|句子|生字|拼音|要求|提示|注意|练习|作业|复习|'
    '近义词|反义词|近义|反义|多音字|形近字|同音字|'
    '第一|第二|第三|第四|第五|第六|第七|第八|第九|第十|第[一二三四五六七八九十百\\d]{1,3}(课|单元|组|部分|题))')

INFO_LINE_RE = re.compile(r'(日期|开始时间|结束时间|实际用时|用时|得分|评价|评语|签名)')

# 英文作业纸表头：Name / Date / Class / Unit / Lesson / Dictation / English ...
EN_HEADER_RE = re.compile(
    r'^\s*(name|date|class|grade|no\.?|number|score|mark|marks|unit|lesson|dictation|spelling|'
    r'english|chinese|maths?|page|time|total|school|student|teacher|word|words|sentence|sentences)\b',
    re.I)


def has_cjk(text):
    return bool(CJK_RE.search(text or ''))


def has_latin(text):
    return bool(LATIN_RE.search(text or ''))


def dominant_lang(text):
    """整份内容是中文为主还是英文为主。"""
    cjk = len(CJK_RE.findall(text or ''))
    latin = len(LATIN_RE.findall(text or ''))
    return 'en' if latin > cjk else 'zh'


def strip_leading_index(line):
    """剥掉行首序号，可反复：\"1.（2）一、春天\" -> \"春天\"。"""
    s = '' if line is None else str(line)
    for _ in range(4):
        before = s
        for rx in LEADING_INDEX_RES:
            nxt = rx.sub('', s, count=1)
            if nxt != s and nxt.strip():
                s = nxt
        if s == before:
            break
    return s


def strip_brackets(text):
    s = '' if text is None else str(text)
    for _ in range(4):
        nxt = BRACKET_RE.sub(' ', s)
        if nxt == s:
            break
        s = nxt
    return s


def strip_inline_pinyin(text, aggressive=True):
    """去掉拼音。先删带声调的（一定是拼音）；无声调的字母串要不要删看上下文：
    中文行里字母串数量 ≥ 汉字数量（"春天 chun tian"）才当拼音删；
    "apple 苹果" 这种一个英文词配中文释义的保留（英语默写要念这个英文词）。"""
    s = '' if text is None else str(text)
    s = TONED_RUN_RE.sub(' ', s)
    if aggressive:
        s = PINYIN_RUN_RE.sub(' ', s)
    return s


def pinyin_aggressive(line):
    """这一行的无声调字母串算不算拼音。"""
    runs = PINYIN_RUN_RE.findall(line)
    cjk = len(CJK_RE.findall(line))
    if not runs:
        return False
    if not cjk:
        return False                      # 纯英文行，绝不当拼音删
    return len(runs) >= cjk


def squash(text):
    s = '' if text is None else str(text)
    s = re.sub(r'\s+', ' ', s)
    s = re.sub(r'\s*([，。！？；：、])\s*', r'\1', s)     # 只收全角标点周围，英文逗号后的空格保留
    return s.strip()


def is_instruction(line, lang='zh'):
    has_cjk_ch = has_cjk(line)
    has_latin_ch = has_latin(line)
    if not has_cjk_ch and not has_latin_ch:
        return True                                  # 纯数字/符号行
    if not has_cjk_ch:                               # 纯英文行：只有表头才丢
        if EN_HEADER_RE.match(line) and (len(line) <= 32 or ':' in line):
            return True
        return False
    # 有中文的行：按中文规则
    if INSTRUCTION_PREFIX_RE.match(line) and (len(line) <= 12 or line.endswith(('：', ':'))):
        return True
    if len(line) <= 20 and INFO_LINE_RE.search(line) and (re.search(r'[：:]', line) or re.search(r'\d', line)):
        return True
    return False


def _push(out, s, lang='zh'):
    t = squash(s)
    t = re.sub(r'^[，,、。；;：:]+', '', t)
    t = re.sub(r'[，,、；;：:]+$', '', t)
    if t and (CJK_RE.search(t) or LATIN_RE.search(t)):
        out.append(t)


def split_line(line, lang='zh'):
    """一行拆成若干条目（中英文都支持）。"""
    out = []
    en = lang == 'en' or not has_cjk(line)

    if '、' in line:
        parts = line.split('、')
        if len(parts) > 1:
            if all(len(p) <= 8 and not re.search(r'[。！？!?；;]', p) for p in parts):
                for p in parts:
                    _push(out, p)
                return out
            if en and all(len(p) <= 24 and not re.search(r'[.!?]', p) for p in parts):
                for p in parts:
                    _push(out, p)
                return out
    if re.search(r'[，,]', line):
        parts = re.split(r'[，,]', line)
        if len(parts) >= 3 and all(len(p) <= 4 and not re.search(r'[。！？!?]', p) for p in parts):
            for p in parts:
                _push(out, p)
            return out
        if en and len(parts) >= 2 and all(len(p.strip()) <= 24 and not re.search(r'[.!?]', p) for p in parts):
            for p in parts:
                _push(out, p)
            return out
    if en:
        sentences = re.findall(r'[^.!?…]*[.!?…]+|[^.!?…]+', line)
    else:
        sentences = re.findall(r'[^。！？!?…]*[。！？!?…]+|[^。！？!?…]+', line)
    if sentences and len(sentences) > 1:
        for s in sentences:
            _push(out, s)
        return out
    _push(out, line)
    return out


def classify(text):
    t = str(text or '')
    if re.search(r'[。！？!?…]$', t):
        return 'sentence'
    if re.search(r'[，,]', t) and len(t) >= 8:
        return 'sentence'
    if len(t) >= 12:
        return 'sentence'
    if not has_cjk(t) and len(t.split()) >= 2:      # 英文多词 → 句子
        return 'sentence'
    return 'word'


def clean_line(line, lang='zh'):
    s = '' if line is None else str(line)
    s = re.sub(r'^[\s#*·•\-—]+', '', s)
    s = strip_leading_index(s)
    s = strip_brackets(s)
    s = strip_inline_pinyin(s, aggressive=pinyin_aggressive(s))
    s = squash(s)
    s = re.sub(r'[(【（\[]+$', '', s)
    s = re.sub(r'^[)\]}】）\]]+', '', s)
    return s.strip()


def parse(raw_text, force_sentence=False, lang='auto'):
    """原始文字 -> [{'text', 'kind', 'lang'}]"""
    if not raw_text:
        return []
    text = str(raw_text).replace('\r\n', '\n').replace('\r', '\n').replace('\u3000', ' ')

    def keep_prefix(prefix):
        return prefix + '\n' if re.search(r'[。！？；;、，,]', prefix) else '\n'

    text = INLINE_CIRCLED_RE.sub(lambda m: keep_prefix(m.group(1)), text)
    text = INLINE_NUM_RE.sub(lambda m: keep_prefix(m.group(1)), text)

    doc_lang = lang if lang in ('zh', 'en') else dominant_lang(text)
    result, seen = [], set()
    for raw_line in text.split('\n'):
        line = clean_line(raw_line, doc_lang)
        if not line or is_instruction(line, doc_lang):
            continue
        for item in split_line(line, doc_lang):
            if item in seen:
                continue
            seen.add(item)
            result.append({'text': item,
                           'kind': 'sentence' if force_sentence else classify(item),
                           'lang': doc_lang})
    return result


def stringify(entries):
    return '\n'.join((e.get('text') if isinstance(e, dict) else str(e)) for e in (entries or []))
