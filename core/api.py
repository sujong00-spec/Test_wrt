"""所有学习功能共用的接口：设置、识别、清单存档、语音素材。"""

from pathlib import Path

from .webapp import Response, json_response, text_response

DEFAULT_SETTINGS = {'mode': 'manual', 'speed': 'normal', 'subject': 'zh'}


def build_routes(rt):
    """rt：运行环境对象，带 cfg / root / store / tts / recognizer / app"""

    def current_subject(req):
        return (req.q('lang')
                or rt.store.settings(DEFAULT_SETTINGS).get('subject')
                or 'zh')

    def features(req):
        items = [{'id': f.get('id'), 'name': f.get('name'), 'desc': f.get('desc'),
                  'icon': f.get('icon'), 'entry': f.get('entry')}
                 for f in rt.app.features]
        return json_response({'ok': True, 'features': items,
                              'default': rt.app.default_feature})

    def post_access(req):
        gate = rt.access
        payload = req.json() or {}
        token = (payload.get('token') or '').strip()
        if not gate.allow_attempt(req.client):
            return json_response({'ok': False, 'error': '试太多次了，等十分钟再试'}, 429)
        if gate.verify(token):
            gate.note_success(req.client)
            return json_response({'ok': True}).with_header('Set-Cookie', gate.cookie_header())
        return json_response({'ok': False, 'error': '口令不对'}, 401)

    def get_settings(req):
        s = rt.store.settings(DEFAULT_SETTINGS)
        s.update({'voiceName': rt.cfg['voice'].get('name', ''),
                  'voiceReady': rt.tts.available(),
                  'recognizeProvider': rt.cfg['recognize'].get('provider', 'auto'),
                  'paceFast': rt.cfg['play'].get('paceFast', 10),
                  'paceSlow': rt.cfg['play'].get('paceSlow', 20)})
        return json_response({'ok': True, 'settings': s})

    def post_settings(req):
        patch = req.json()
        s = rt.store.save_settings(patch, DEFAULT_SETTINGS)
        return json_response({'ok': True, 'settings': s})

    def recognize(req):
        ctype = req.headers.get('content-type', '')
        lang = current_subject(req)
        if ctype.startswith('image/'):
            data = req.body
            limit = int(rt.cfg['recognize'].get('max_upload_mb', 12)) * 1024 * 1024
            if len(data) > limit:
                return json_response({'ok': False, 'error': '图片太大了，请重新拍一张或压缩后再传'}, 413)
            if not data:
                return json_response({'ok': False, 'error': '没有收到图片'}, 400)
            try:
                items = rt.recognizer.recognize(data, lang=lang)
            except Exception as exc:  # noqa: BLE001
                return json_response({'ok': False, 'error': str(exc)}, 502)
            return json_response({'ok': True, 'items': items, 'note': rt.recognizer.last_note,
                                  'lang': lang})
        payload = req.json()
        text = payload.get('text', '')
        lang = payload.get('lang') or lang
        if not text.strip():
            return json_response({'ok': False, 'error': '没有内容'}, 400)
        items = rt.recognizer.recognize_text(text, force_sentence=bool(payload.get('forceSentence')),
                                             lang=lang)
        if not items:
            return json_response({'ok': False, 'error': '没整理出条目，检查一下是不是只有序号或拼音'}, 400)
        return json_response({'ok': True, 'items': items, 'note': '手动输入', 'lang': lang})

    def get_list(req):
        cur = rt.store.current()
        data = {'ok': True, 'list': cur}
        # 外部（公网链接）来访：不返回历史清单，只给当前这一份
        data['history'] = [] if rt.access.is_external(req) else rt.store.history()
        if rt.access.is_external(req):
            data['list'] = {'name': cur.get('name', ''), 'items': cur.get('items', [])}
        return json_response(data)

    def post_list(req):
        payload = req.json()
        name = (payload.get('name') or '').strip()
        items = payload.get('items') or []
        cur = rt.store.save_current(name, items)
        if payload.get('snapshot'):
            rt.store.add_history(name or '未命名', items)
        return json_response({'ok': True, 'list': cur})

    def audio_ensure(req):
        payload = req.json()
        texts = [t for t in (payload.get('texts') or []) if t]
        speed = payload.get('speed') or 'normal'
        ready, pending = rt.tts.ensure(texts, speed)
        return json_response({'ok': True, 'ready': ready, 'pending': pending,
                              'total': len(texts)})

    def audio_status(req):
        payload = req.json()
        texts = [t for t in (payload.get('texts') or []) if t]
        speed = payload.get('speed') or 'normal'
        st = rt.tts.status(texts, speed)
        ready = sum(1 for v in st.values() if v == 'ready')
        return json_response({'ok': True, 'status': st, 'ready': ready, 'total': len(st),
                              'error': rt.tts.failure_note()})

    def audio_get(req):
        key = req.q('key', '')
        if not key or any(c not in '0123456789abcdef' for c in key):
            return json_response({'ok': False, 'error': 'key 不对'}, 400)
        for suffix, ctype in (('.mp3', 'audio/mpeg'), ('.wav', 'audio/wav')):
            f = rt.tts.cache_dir / (key + suffix)
            if f.exists() and f.stat().st_size:
                return Response(200, f.read_bytes(), ctype,
                                {'Cache-Control': 'public, max-age=86400'})
        return json_response({'ok': False, 'error': '还没合成好'}, 404)

    return {
        ('GET', '/api/features'): features,
        ('POST', '/api/access'): post_access,
        ('GET', '/api/settings'): get_settings,
        ('POST', '/api/settings'): post_settings,
        ('POST', '/api/recognize'): recognize,
        ('GET', '/api/list'): get_list,
        ('POST', '/api/list'): post_list,
        ('POST', '/api/audio/ensure'): audio_ensure,
        ('POST', '/api/audio/status'): audio_status,
        ('GET', '/api/audio'): audio_get,
    }
