#!/usr/bin/env python3
"""本机 OCR 服务：给「小学生默写助手」提供一个完全离线的手写/印刷体识别接口。

装依赖（二选一，CPU 就能跑）：
    pip install rapidocr-onnxruntime     # 约 100MB 模型，装完即用（推荐）
    pip install paddleocr paddlepaddle   # 备选，中文印刷体更好，装起来重一些

起服务：
    python3 tools/ocr_server.py --port 8788

接到应用里（config.json）：
    "recognize": { "local": { "url": "http://127.0.0.1:8788/ocr" } }

接口：
    GET  /health            -> {"ok": true, "engine": "rapidocr"}
    POST /ocr  (图片字节)    -> {"lines": ["春天", "花朵", ...], "engine": "rapidocr"}

调用方（core/recognize.py 的 local 通道）只认 {"lines": [...]} 或 {"text": "..."}，
返回的行按从上到下、从左到右排序——默写顺序就是孩子本子上的顺序。

说明：本机 OCR 对工整印刷体很准，对手写体弱于云上的手写识别接口。
孩子写的字潦草时，可以另配视觉大模型（本机 Ollama 也行）做兜底，见 README。
"""

import argparse
import json
import os
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MAX_BODY = 32 * 1024 * 1024
_engine = None
_engine_name = ''
_lock = threading.Lock()


def load_engine():
    """优先 rapidocr，其次 paddleocr。"""
    global _engine, _engine_name
    if _engine is not None:
        return _engine, _engine_name
    try:
        from rapidocr_onnxruntime import RapidOCR
        _engine = RapidOCR()
        _engine_name = 'rapidocr'
        return _engine, _engine_name
    except ImportError:
        pass
    try:
        from paddleocr import PaddleOCR
        _engine = PaddleOCR(use_angle_cls=True, lang='ch', show_log=False)
        _engine_name = 'paddleocr'
        return _engine, _engine_name
    except ImportError:
        pass
    raise SystemExit(
        '没有可用的 OCR 引擎。请先装一个：\n'
        '    pip install rapidocr-onnxruntime\n'
        '或\n'
        '    pip install paddleocr paddlepaddle'
    )


def ocr_image(image_bytes):
    """图片字节 -> [(y, x, 文本)] 列表（用于排序）。"""
    from PIL import Image  # rapidocr/paddleocr 都会带 Pillow
    with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as f:
        f.write(image_bytes)
        path = f.name
    try:
        if _engine_name == 'rapidocr':
            result, _ = _engine(path)
            rows = []
            for box, text, score in (result or []):
                ys = [p[1] for p in box]
                xs = [p[0] for p in box]
                if text and str(text).strip():
                    rows.append((min(ys), min(xs), str(text).strip()))
            return rows
        # paddleocr
        if hasattr(_engine, 'predict'):
            out = _engine.predict(path)
            rows = []
            for page in (out or []):
                texts = page.get('rec_texts') or []
                boxes = page.get('rec_polys') or page.get('dt_polys') or []
                for i, text in enumerate(texts):
                    box = boxes[i] if i < len(boxes) else None
                    y = min(p[1] for p in box) if box is not None else i
                    x = min(p[0] for p in box) if box is not None else 0
                    rows.append((y, x, str(text)))
            return rows
        out = _engine.ocr(path, cls=True)
        rows = []
        for page in (out or []):
            for item in (page or []):
                box, (text, _score) = item[0], item[1]
                ys = [p[1] for p in box]
                xs = [p[0] for p in box]
                rows.append((min(ys), min(xs), str(text)))
        return rows
    finally:
        os.unlink(path)


def lines_of(image_bytes):
    """按阅读顺序合并成行文本。"""
    rows = ocr_image(image_bytes)
    rows.sort(key=lambda r: (round(r[0] / 18), r[1]))   # 同一行内按 x 排序
    lines, cur_y, cur = [], None, []
    for y, x, text in rows:
        if cur_y is None or abs(y - cur_y) <= 18:
            cur.append(text)
            cur_y = y if cur_y is None else cur_y
        else:
            lines.append(''.join(cur))
            cur, cur_y = [text], y
    if cur:
        lines.append(''.join(cur))
    return [l for l in (s.strip() for s in lines) if l]


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, fmt, *args):    # 安静一点
        print('  %s - %s' % (self.address_string(), fmt % args))

    def _send(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith('/health'):
            self._send(200, {'ok': True, 'engine': _engine_name})
        else:
            self._send(404, {'ok': False, 'error': 'only /ocr and /health'})

    def do_POST(self):
        if not self.path.startswith('/ocr'):
            self._send(404, {'ok': False, 'error': 'only /ocr and /health'})
            return
        try:
            length = int(self.headers.get('Content-Length') or 0)
        except ValueError:
            length = 0
        if length <= 0 or length > MAX_BODY:
            self._send(400, {'ok': False, 'error': '图片为空或过大'})
            return
        image = self.rfile.read(length)
        try:
            with _lock:
                lines = lines_of(image)
        except Exception as exc:  # noqa: BLE001
            self._send(500, {'ok': False, 'error': str(exc)[:200]})
            return
        self._send(200, {'lines': lines, 'engine': _engine_name})


def main():
    ap = argparse.ArgumentParser(description='本机 OCR 服务')
    ap.add_argument('--host', default='127.0.0.1', help='监听地址（默认只给本机用）')
    ap.add_argument('--port', type=int, default=8788)
    args = ap.parse_args()
    load_engine()
    print('OCR 引擎：%s' % _engine_name)
    print('服务已启动：http://%s:%d/ocr   （把地址填进 config.json 的 recognize.local.url）'
          % (args.host, args.port))
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()


if __name__ == '__main__':
    main()
