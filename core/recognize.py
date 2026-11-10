"""识别：把照片里的默写内容变成文字。

三条通道，可自动择优（`chain` 里按顺序试，认出来的条目够多就停）：

  - local ：**本机 OCR 服务**（离线、不联网；`tools/ocr_server.py`，见 README）
  - baidu ：百度手写文字识别（快，1~2 秒，认手写体好，需要联网与密钥）
  - vision：任意 OpenAI 兼容的视觉大模型（慢几十秒，但更懂版面，可指向本机 Ollama / vLLM）

默认顺序 local → baidu → vision，没配的自动跳过；只配了本机服务时就是**完全离线**。
"""

import base64
import json
import os
import re
import urllib.parse as up
import urllib.request as ur
from pathlib import Path

from . import textclean

BAIDU_TOKEN_URL = 'https://aip.baidubce.com/oauth/2.0/token'
BAIDU_OCR_URL = 'https://aip.baidubce.com/rest/2.0/ocr/v1/%s'

LOCAL_HOSTS = ('127.0.0.1', 'localhost', '0.0.0.0', '::1', 'host.docker.internal')

VISION_PROMPT = (
    '这是一页小学作业本或默写纸的照片。请只输出上面需要默写的词语和句子：'
    '一行一条，去掉题号、姓名、日期、得分等表头和说明文字，不要改写文字，不要解释，不要编号。'
    '如果某一行看不清，就跳过它。'
)

VISION_PROMPT_EN = (
    'This is a photo of a primary-school dictation page. Output only the English words and sentences '
    'that need to be dictated: one item per line, keep the original spelling and punctuation, '
    'drop numbering, names, dates, scores and other headers. No explanations, no numbering. '
    'Skip any line you cannot read clearly.'
)


class RecognizeError(Exception):
    pass


def _load_baidu_keys(cfg, root):
    ak = os_getenv('BAIDU_OCR_AK')
    sk = os_getenv('BAIDU_OCR_SK')
    if ak and sk:
        return ak, sk
    kf = root / cfg.get('key_file', 'data/baidu.json')
    if kf.exists():
        try:
            d = json.loads(kf.read_text(encoding='utf-8'))
            return d.get('api_key', ''), d.get('secret_key', '')
        except Exception:  # noqa: BLE001
            return '', ''
    return '', ''


def os_getenv(name):
    return os.environ.get(name, '')


def is_local_url(url):
    """本机地址不需要令牌（本机 Ollama / OCR 服务都没有鉴权）。"""
    m = re.match(r'^https?://([^/:]+)', url or '')
    return bool(m) and m.group(1).lower() in LOCAL_HOSTS


class Recognizer:
    def __init__(self, cfg, root):
        self.cfg = cfg
        self.root = Path(root)
        self.provider = cfg.get('provider', 'auto')
        self._token = None
        self._token_expire = 0
        self.last_note = ''

    # ---------- 通道选择 ----------

    def available(self):
        """哪些通道现在可用（配好了）。"""
        out = []
        if (self.cfg.get('local', {}) or {}).get('url'):
            out.append('local')
        if all(_load_baidu_keys(self.cfg.get('baidu', {}) or {}, self.root)):
            out.append('baidu')
        vcfg = self.cfg.get('vision', {}) or {}
        if vcfg.get('base_url') and (os_getenv(vcfg.get('token_env', '')) or is_local_url(vcfg['base_url'])):
            out.append('vision')
        return out

    def chain(self):
        """识别顺序：显式配的 provider 排最前，其余按 chain 顺序补齐。"""
        order = list(self.cfg.get('chain') or ['local', 'baidu', 'vision'])
        if self.provider and self.provider != 'auto':
            order = [self.provider] + [n for n in order if n != self.provider]
        usable = self.available()
        return [n for n in order if n in usable]

    def _fetch(self, name, image_bytes, lang='auto'):
        if name == 'local':
            return self._local(image_bytes)
        if name == 'baidu':
            return self._baidu(image_bytes)
        return self._vision(image_bytes, lang=lang)

    # ---------- 对外入口 ----------

    def recognize(self, image_bytes, hint='', lang='auto'):
        """图片 -> [{'text', 'kind', 'lang', 'source'}]"""
        names = self.chain()
        if not names:
            raise RecognizeError('没有任何可用的识别通道：本机 OCR 服务没配 URL，识别密钥也没有。'
                                 '可以先手动输入，或按 README 起一个本机 OCR 服务。')
        errors = []
        best = []
        for name in names:
            try:
                raw = self._fetch(name, image_bytes, lang=lang)
            except Exception as exc:  # noqa: BLE001
                errors.append('%s: %s' % (name, exc))
                continue
            items = textclean.parse(raw['text'] if isinstance(raw, dict) else raw, lang=lang)
            for it in items:
                it['source'] = name
            if len(items) > len(best):
                best = items
                self.last_note = raw.get('note', '') if isinstance(raw, dict) else ''
            if len(items) >= 2:
                break
        if not best:
            raise RecognizeError('没有识别到内容。' + ('；'.join(errors) if errors else '请换成更清晰的照片，或手动输入。'))
        return best

    def recognize_text(self, text, force_sentence=False, lang='auto'):
        items = textclean.parse(text, force_sentence=force_sentence, lang=lang)
        for it in items:
            it['source'] = 'manual'
        return items

    # ---------- 批改用：只取行，不做清洗 ----------

    def read_lines(self, image_bytes, lang='zh'):
        """返回识别出的原始行（批改用，孩子可能只写了一半、跳着写）。"""
        errors = []
        for name in self.chain():
            try:
                raw = self._fetch(name, image_bytes, lang=lang)
            except Exception as exc:  # noqa: BLE001
                errors.append('%s: %s' % (name, exc))
                continue
            text = raw['text'] if isinstance(raw, dict) else raw
            lines = [l.strip() for l in str(text).split('\n') if l.strip()]
            if lines:
                self.last_note = raw.get('note', '') if isinstance(raw, dict) else ''
                return lines, name
        raise RecognizeError('没认出孩子写的内容。' + ('；'.join(errors) if errors else '换张更清晰的照片，或手动标对错。'))

    def vision_grading(self, image_bytes, items, lang='zh'):
        """按题目逐条判对错，返回 [{'index','written','verdict'}]。

        **默认**一次性返回完整 JSON（实测该端点下 4 题只花 85 输出 tokens，且比两步走更准）。
        `recognize.vision.compact=true` 时改成两步走（JEV：先只要一行判定码 `1211`，
        再只对非「对」的题回头要原文）——实测输出 tokens 85→28（-67%），但多一次往返、
        判定会退步（同一张图把「没写」判成「对」），所以默认不开。
        注意：compact 路径下判定为「对」的条目，written 直接取题目原文（孩子写对即同题）。

        没配视觉模型时退回「先认字再本地比对」。
        """
        vcfg = self.cfg.get('vision', {}) or {}
        token = os_getenv(vcfg.get('token_env', 'INTERN_DISCOVERY_API_KEY'))
        if not vcfg.get('base_url') or (not token and not is_local_url(vcfg['base_url'])):
            lines, used = self.read_lines(image_bytes, lang=lang)
            return [{'index': i, 'written': lines[i] if i < len(lines) else '', 'verdict': 'unknown'}
                    for i in range(len(items))], used
        if not vcfg.get('compact'):
            # 默认走一次性完整 JSON：实测本端点下它已经很紧凑（4 题 85 输出 tokens），
            # 且比两步走更准；两步走仅在 vision.compact=true 时启用（长清单场景省输出）。
            return self._vision_grading_full(image_bytes, items, token, lang), 'vision'
        try:
            codes = self._vision_codes(image_bytes, items, token, lang)
            written = self._vision_written(image_bytes, items, codes, token, lang) if any(
                c != '1' for c in codes) else {}
        except Exception:      # noqa: BLE001 - 两步走失败就用老路径，不让批改断掉
            return self._vision_grading_full(image_bytes, items, token, lang), 'vision'
        verdict_map = {'1': 'correct', '2': 'wrong', '3': 'missing', '0': 'unknown'}
        rows = [{'index': i, 'written': written.get(i, '') if codes[i] != '1' else items[i].get('text', ''),
                 'verdict': verdict_map.get(codes[i], 'unknown')}
                for i in range(len(codes))]
        return rows, 'vision'

    def _vbody(self, image_bytes, prompt, token, vcfg, max_tokens, reasoning_off=True):
        b64 = base64.b64encode(image_bytes).decode()
        body = {'model': vcfg.get('model', ''),
                'messages': [{'role': 'user', 'content': [
                    {'type': 'text', 'text': prompt},
                    {'type': 'image_url', 'image_url': {'url': 'data:image/jpeg;base64,' + b64}}]}],
                'temperature': 0.1, 'max_tokens': max_tokens}
        if reasoning_off:
            body['reasoning_effort'] = 'none'      # 关掉思考 tokens：只判对错不需要推导过程
        url = vcfg['base_url'].rstrip('/') + '/chat/completions'
        try:
            return self._post_json(url, body, token, timeout=300)
        except RecognizeError:
            body.pop('reasoning_effort', None)     # 端点不认就去掉重试
            return self._post_json(url, body, token, timeout=300)

    def _vision_codes(self, image_bytes, items, token, lang='zh'):
        """第一步：只要一行判定码。"""
        vcfg = self.cfg.get('vision', {}) or {}
        wanted = '\n'.join('%d. %s' % (i + 1, it.get('text', '')) for i, it in enumerate(items))
        prompt = ('下面是这轮默写的题目（按顺序）：\n%s\n\n' % wanted +
                  '照片是孩子写在本子上的答案。请逐题判断，输出与题数等长的**一行数字**：'
                  '1=完全正确（忽略空格标点）2=写错 3=没写 0=看不清。'
                  '只输出 JSON：{"code":"<如 1211>"}，不要解释。')
        data = self._vbody(image_bytes, prompt, token, vcfg, max_tokens=48)
        raw = data['choices'][0]['message'].get('content') or ''
        m = re.search(r'"code"\s*:\s*"([0-9]+)"', raw) or re.search(r'([0-9]{2,})', raw)
        if not m:
            raise RecognizeError('视觉模型没有给出判定码')
        codes = m.group(1)
        if len(codes) != len(items):
            raise RecognizeError('判定码长度与题数不符（%d vs %d）' % (len(codes), len(items)))
        return codes

    def _vision_written(self, image_bytes, items, codes, token, lang='zh'):
        """第二步：只要非「对」那几条的孩子原文。"""
        vcfg = self.cfg.get('vision', {}) or {}
        need = [i for i, c in enumerate(codes) if c != '1']
        wanted = '\n'.join('%d. %s' % (i + 1, items[i].get('text', '')) for i in need)
        prompt = ('照片是孩子写在本子上的答案。下面是几道题的题目：\n%s\n\n' % wanted +
                  '只把孩子在照片里对应位置写的原文抄出来（看不出来就留空）。'
                  '只输出 JSON：{"texts":{"<题号>":"<原文>"}}，不要解释。')
        data = self._vbody(image_bytes, prompt, token, vcfg, max_tokens=256)
        raw = data['choices'][0]['message'].get('content') or ''
        m = re.search(r'\{.*\}', raw, re.S)
        if not m:
            return {}
        try:
            texts = json.loads(m.group(0)).get('texts') or {}
        except Exception:   # noqa: BLE001
            return {}
        out = {}
        for k, v in texts.items():
            try:
                out[int(k) - 1] = str(v)
            except (TypeError, ValueError):
                continue
        return out

    def _vision_grading_full(self, image_bytes, items, token, lang='zh'):
        """老路径：一次返回完整 JSON（含每条 written）。仅在两步走不可用时使用。"""
        vcfg = self.cfg.get('vision', {}) or {}
        wanted = '\n'.join('%d. %s' % (i + 1, it.get('text', '')) for i, it in enumerate(items))
        prompt = (
            ('下面是这轮默写的题目（按顺序）：\n%s\n\n' % wanted) +
            '照片是孩子写在本子上的答案。请逐题判断：孩子写的和题目是否完全一致（忽略空格和标点）。'
            '只输出一个 JSON 数组，形如 '
            '[{"index":1,"written":"孩子写的原文","verdict":"correct"}, ...]，'
            'verdict 取值只能是 correct（对）、wrong（错）、missing（没写）。'
            '看不清的按 wrong 并在 written 里写你看到的字。不要输出任何解释。'
        )
        data = self._vbody(image_bytes, prompt, token, vcfg, max_tokens=1500)
        content = data['choices'][0]['message']['content']
        m = re.search(r'\[.*\]', content, re.S)
        if not m:
            raise RecognizeError('视觉模型没给出可用的结果')
        parsed = json.loads(m.group(0))
        out = []
        for row in parsed:
            idx = int(row.get('index', 0)) - 1
            verdict = row.get('verdict', 'wrong')
            if verdict not in ('correct', 'wrong', 'missing'):
                verdict = 'wrong'
            out.append({'index': idx, 'written': str(row.get('written', '')), 'verdict': verdict})
        return out

    # ---------- 本机 OCR 服务 ----------

    def _local(self, image_bytes):
        """把图片原样 POST 给本机 OCR 服务，接受 {'lines':[...]} / {'text':'...'} / 字符串数组。"""
        lcfg = self.cfg.get('local', {}) or {}
        url = lcfg.get('url')
        if not url:
            raise RecognizeError('没有配置本机 OCR 服务地址')
        req = ur.Request(url, data=image_bytes,
                         headers={'Content-Type': lcfg.get('content_type', 'image/jpeg')})
        try:
            with ur.urlopen(req, timeout=int(lcfg.get('timeout', 180))) as r:
                data = json.loads(r.read() or b'{}')
        except ur.HTTPError as exc:
            raise RecognizeError('本机 OCR 服务返回 %s：%s' % (exc.code, exc.read()[:120].decode('utf-8', 'ignore')))
        except Exception as exc:  # noqa: BLE001
            raise RecognizeError('连不上本机 OCR 服务（%s），确认 tools/ocr_server.py 在跑' % exc)
        if isinstance(data, list):
            lines = [str(x) for x in data]
        elif isinstance(data, dict):
            lines = data.get('lines') or []
            if not lines and data.get('text'):
                lines = [l for l in str(data['text']).split('\n') if l.strip()]
        else:
            lines = []
        lines = [str(l).strip() for l in lines if str(l).strip()]
        return {'text': '\n'.join(lines), 'note': '本机 OCR %d 行' % len(lines)}

    # ---------- 手写文字识别 ----------

    def _baidu(self, image_bytes):
        ak, sk = _load_baidu_keys(self.cfg.get('baidu', {}) or {}, self.root)
        if not ak or not sk:
            raise RecognizeError('未配置识别密钥')
        token = self._baidu_token(ak, sk)
        endpoint = (self.cfg.get('baidu', {}) or {}).get('endpoint', 'handwriting')
        body = up.urlencode({'image': base64.b64encode(image_bytes).decode()}).encode()
        req = ur.Request(BAIDU_OCR_URL % endpoint + '?access_token=' + token, data=body)
        with ur.urlopen(req, timeout=60) as r:
            data = json.loads(r.read())
        if data.get('error_code'):
            raise RecognizeError('识别接口返回错误 %s' % data.get('error_code'))
        lines = [w.get('words', '') for w in data.get('words_result', [])]
        return {'text': '\n'.join(lines), 'note': '手写识别 %d 行' % len(lines)}

    def _baidu_token(self, ak, sk):
        import time
        if self._token and time.time() < self._token_expire:
            return self._token
        body = up.urlencode({'grant_type': 'client_credentials',
                             'client_id': ak, 'client_secret': sk}).encode()
        with ur.urlopen(ur.Request(BAIDU_TOKEN_URL, data=body), timeout=30) as r:
            data = json.loads(r.read())
        tok = data.get('access_token')
        if not tok:
            raise RecognizeError('识别密钥无效')
        self._token = tok
        self._token_expire = time.time() + int(data.get('expires_in', 2592000)) - 3600
        return tok

    # ---------- 视觉模型 ----------

    def _vision(self, image_bytes, lang='auto'):
        vcfg = self.cfg.get('vision', {}) or {}
        token = os_getenv(vcfg.get('token_env', 'INTERN_DISCOVERY_API_KEY'))
        if not vcfg.get('base_url'):
            raise RecognizeError('未配置视觉模型地址')
        if not token and not is_local_url(vcfg['base_url']):
            raise RecognizeError('未配置视觉模型令牌')
        b64 = base64.b64encode(image_bytes).decode()
        body = {
            'model': vcfg.get('model', ''),
            'messages': [{'role': 'user', 'content': [
                {'type': 'text', 'text': VISION_PROMPT_EN if lang == 'en' else VISION_PROMPT},
                {'type': 'image_url', 'image_url': {'url': 'data:image/jpeg;base64,' + b64}},
            ]}],
            'temperature': 0.1,
            'max_tokens': int(vcfg.get('max_tokens', 1200)),
        }
        data = self._post_json(vcfg['base_url'].rstrip('/') + '/chat/completions', body, token, timeout=300)
        content = data['choices'][0]['message']['content']
        content = re.sub(r'^```.*$|^```$', '', content, flags=re.M).strip()
        return {'text': content, 'note': '视觉识别'}

    def _post_json(self, url, body, token, timeout=300):
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['Authorization'] = 'Bearer ' + token
        req = ur.Request(url, data=json.dumps(body).encode(), headers=headers)
        try:
            with ur.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())
        except ur.HTTPError as exc:
            raise RecognizeError('模型接口返回 %s：%s' % (exc.code, exc.read()[:200].decode('utf-8', 'ignore')))
        except Exception as exc:  # noqa: BLE001
            raise RecognizeError('连不上模型接口（%s）' % exc)
