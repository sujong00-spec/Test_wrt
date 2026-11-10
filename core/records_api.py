"""默写档案相关接口：记录、上传批改、复核、错题本、能力评估。"""

from datetime import datetime
from pathlib import Path

from . import grading as G
from .webapp import json_response


def build_records_routes(rt):
    def start(req):
        payload = req.json()
        items = payload.get('items') or []
        if not items:
            return json_response({'ok': False, 'error': '清单是空的'}, 400)
        s = rt.history.start_session(items, subject=payload.get('subject') or 'zh',
                                     mode=payload.get('mode') or 'manual',
                                     speed=payload.get('speed') or 'normal')
        return json_response({'ok': True, 'session': s})

    def finish(req):
        payload = req.json()
        sid = payload.get('id')
        if not sid:
            return json_response({'ok': False, 'error': '缺少轮次 id'}, 400)
        s = rt.history.finish_session(sid, duration_sec=payload.get('durationSec') or 0,
                                      completed=payload.get('completed'))
        return json_response({'ok': True, 'session': s})

    def records(req):
        return json_response({'ok': True, 'records': rt.history.records(
            subject=req.q('subject'), limit=int(req.q('limit', 100) or 100))})

    def record(req):
        sid = req.q('id')
        if not sid:
            return json_response({'ok': False, 'error': '缺少 id'}, 400)
        data = rt.history.detail(int(sid))
        if not data:
            return json_response({'ok': False, 'error': '没有这条记录'}, 404)
        return json_response({'ok': True, **data, 'labels': G.VERDICT_LABEL})

    def upload_result(req):
        """上传孩子写完的纸：识别 -> 逐条判对错 -> 存起来等家长复核。"""
        sid = req.q('session')
        if not sid:
            return json_response({'ok': False, 'error': '缺少轮次 id'}, 400)
        data = rt.history.detail(int(sid))
        if not data:
            return json_response({'ok': False, 'error': '没有这条记录'}, 404)
        image = req.body
        if not image:
            return json_response({'ok': False, 'error': '没有收到图片'}, 400)
        lang = data['session'].get('subject') or 'zh'
        try:
            lines, method = rt.recognizer.read_lines(image, lang=lang)
        except Exception as exc:  # noqa: BLE001
            return json_response({'ok': False, 'error': str(exc)}, 502)
        save_dir = Path(rt.root) / 'data' / 'results'
        save_dir.mkdir(parents=True, exist_ok=True)
        image_path = save_dir / ('%s_%s.jpg' % (sid, datetime.now().strftime('%Y%m%d%H%M%S')))
        try:
            image_path.write_bytes(image)
        except OSError:
            image_path = None
        graded = G.grade_session(data['items'], lines, lang)
        rid = rt.history.save_result(int(sid), graded, method=method,
                                     note=rt.recognizer.last_note,
                                     image_path=str(image_path) if image_path else '')
        new_data = rt.history.detail(int(sid))
        return json_response({'ok': True, 'resultId': rid, 'method': method,
                              'recognizedLines': lines, **new_data,
                              'labels': G.VERDICT_LABEL})

    def vision_grade(req):
        """用视觉模型逐条精批（慢，几十秒；识别对错更稳）。"""
        payload = req.json()
        sid = payload.get('session')
        data = rt.history.detail(int(sid or 0))
        if not data:
            return json_response({'ok': False, 'error': '没有这条记录'}, 404)
        rid = payload.get('resultId')
        result = rt.history.result(int(rid)) if rid else rt.history.latest_result(int(sid))
        image_path = (result or {}).get('image_path')
        if not image_path or not Path(image_path).exists():
            return json_response({'ok': False, 'error': '请先上传孩子写的照片，再用视觉模型精批'}, 400)
        lang = data['session'].get('subject') or 'zh'
        try:
            rows, method = rt.recognizer.vision_grading(Path(image_path).read_bytes(), data['items'], lang)
        except Exception as exc:  # noqa: BLE001
            return json_response({'ok': False, 'error': str(exc)}, 502)
        graded = G.merge_vision(data['items'], rows, lang)
        rt.history.save_result(int(sid), graded, method='vision', note='视觉模型精批',
                               image_path=image_path)
        return json_response({'ok': True, **rt.history.detail(int(sid)), 'labels': G.VERDICT_LABEL})

    def reflect(req):
        """家长复核修订：改判定、改孩子写的原文。"""
        payload = req.json()
        rid = payload.get('resultId')
        if not rid:
            return json_response({'ok': False, 'error': '缺少批改 id'}, 400)
        n = rt.history.update_gradings(int(rid), payload.get('patches') or {})
        sid = payload.get('session')
        return json_response({'ok': True, 'updated': n,
                              **(rt.history.detail(int(sid)) if sid else {})})

    def wrongbook(req):
        return json_response({'ok': True, 'items': rt.history.wrongbook(subject=req.q('subject')),
                              'labels': G.VERDICT_LABEL})

    def retry_items(req):
        """用错题再默一次：返回可以直接进入默写流程的清单。"""
        payload = req.json()
        subject = payload.get('subject') or 'zh'
        limit = int(payload.get('limit') or 10)
        items = rt.history.wrongbook(subject=subject)
        picked = [{'text': it['expected'], 'kind': 'sentence' if len(it['expected']) >= 12 else 'word',
                   'lang': it['subject']} for it in items[:limit]]
        return json_response({'ok': True, 'items': picked, 'total': len(items)})

    def stats(req):
        return json_response({'ok': True, **rt.history.stats(days=int(req.q('days', 14) or 14))})

    return {
        ('POST', '/api/session/start'): start,
        ('POST', '/api/session/finish'): finish,
        ('GET', '/api/records'): records,
        ('GET', '/api/record'): record,
        ('POST', '/api/result'): upload_result,
        ('POST', '/api/result/vision'): vision_grade,
        ('POST', '/api/gradings/reflect'): reflect,
        ('GET', '/api/wrongbook'): wrongbook,
        ('POST', '/api/wrongbook/retry'): retry_items,
        ('GET', '/api/stats'): stats,
    }
