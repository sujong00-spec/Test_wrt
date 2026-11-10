"""默写：把清单变成「怎么念」的方案（念两遍、词语/句子不同话术、停顿可调）。"""

from pathlib import Path

from core.speech import build_segments
from core.webapp import json_response

META = {
    'id': 'moxie',
    'name': '默写',
    'desc': '拍下作业本，逐条念出来，孩子跟着写',
    'icon': '✏️',
    'page': str(Path(__file__).parent / 'web' / 'index.html'),
    'entry': '/f/moxie/',
}

STATICS = [('/f/moxie/', Path(__file__).parent / 'web')]


def build_routes(rt):
    cfg = rt.cfg

    def plan(req):
        payload = req.json()
        items = payload.get('items') or []
        speed = payload.get('speed') or cfg['play'].get('defaultSpeed', 'normal')
        mode = payload.get('mode') or cfg['play'].get('defaultMode', 'manual')
        phrase = cfg['voice'].get('phrase', {})
        limit = int(cfg['voice'].get('max_chars_per_clip', 60))
        gap = int(cfg['play'].get('gapMs', 700))
        lead_gap = int(cfg['play'].get('leadGapMs', 400))

        plan_items = []
        texts = []
        for i, entry in enumerate(items):
            entry = entry if isinstance(entry, dict) else {'text': str(entry)}
            entry.setdefault('kind', 'word')
            segs = build_segments(entry, phrase, gap_ms=gap, lead_gap_ms=lead_gap, limit=limit)
            steps = []
            for s in segs:
                key = rt.tts.key_of(s['text'], speed)
                texts.append(s['text'])
                steps.append({'text': s['text'], 'key': key,
                              'gapAfterMs': s['gapAfterMs'],
                              'url': '/api/audio?key=' + key})
            plan_items.append({'index': i, 'text': entry.get('text', ''),
                               'kind': entry.get('kind', 'word'), 'steps': steps})
            if not steps:
                plan_items[-1]['steps'] = []

        extra = {}
        for name in ('first', 'last', 'end'):
            t = phrase.get(name, '')
            if not t:
                continue
            key = rt.tts.key_of(t, speed)
            texts.append(t)
            extra[name] = {'text': t, 'key': key, 'url': '/api/audio?key=' + key}

        all_texts = []
        for it in plan_items:
            all_texts.extend(s['text'] for s in it['steps'])
        for v in extra.values():
            all_texts.append(v['text'])
        rt.tts.ensure(all_texts, speed)

        return json_response({'ok': True, 'speed': speed, 'mode': mode,
                              'items': plan_items, 'phrases': extra,
                              'texts': all_texts,
                              'paceFast': cfg['play'].get('paceFast', 10),
                              'paceSlow': cfg['play'].get('paceSlow', 20),
                              'gapMs': gap, 'repeat': cfg['play'].get('repeat', 2)})

    return {('POST', '/api/plan'): plan}


ROUTES = build_routes
