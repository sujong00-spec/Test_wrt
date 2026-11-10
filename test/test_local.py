"""本地部署自测：本机 OCR 服务 + OpenAI 兼容语音 + 命令行语音（都不联网、不需要任何密钥）。

    python3 test/test_local.py
"""
import json
import struct
import sys
import threading
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.recognize import Recognizer          # noqa: E402
from core.tts import VoiceEngine               # noqa: E402

OK = []
FAIL = []


def check(name, cond, extra=''):
    (OK if cond else FAIL).append(name)
    print(('通过   ' if cond else '不通过 ') + name + (('  ' + str(extra)) if extra else ''))


def wav_bytes(seconds=0.5, rate=24000):
    """一段可播放的静音 wav（不依赖 ffmpeg）。"""
    buf = BytesIO()
    with wave.open(buf, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b'\x00\x00' * int(rate * seconds))
    return buf.getvalue()


class MockOCR(BaseHTTPRequestHandler):
    """假的本机 OCR 服务：接口与 tools/ocr_server.py 一致。"""
    lines = ['春天', '花朵', '小鸟在树上唱歌。']

    def log_message(self, *a):
        pass

    def do_POST(self):
        self.rfile.read(int(self.headers.get('Content-Length') or 0))
        body = json.dumps({'lines': self.lines, 'engine': 'mock'}).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class MockTTS(BaseHTTPRequestHandler):
    """假的 OpenAI 兼容语音服务：POST /v1/audio/speech。"""
    seen = []

    def log_message(self, *a):
        pass

    def do_POST(self):
        n = int(self.headers.get('Content-Length') or 0)
        MockTTS.seen.append(json.loads(self.rfile.read(n)))
        data = wav_bytes(0.4)
        self.send_response(200)
        self.send_header('Content-Type', 'audio/wav')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def serve(handler):
    srv = ThreadingHTTPServer(('127.0.0.1', 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]


def main():
    # ---------- 1. 本机 OCR 服务 ----------
    ocr_srv, ocr_port = serve(MockOCR)
    cfg = {'provider': 'auto', 'chain': ['local', 'baidu', 'vision'],
           'local': {'url': 'http://127.0.0.1:%d/ocr' % ocr_port}}
    rec = Recognizer(cfg, ROOT)
    check('只配本机 OCR 时通道为 local', rec.chain() == ['local'], rec.chain())
    items = rec.recognize(b'\xff\xd8fake-jpeg')
    check('本机 OCR 识别出条目', [i['text'] for i in items] == MockOCR.lines, [i['text'] for i in items])
    check('来源标记为 local', all(i['source'] == 'local' for i in items))
    check('英文分类也走本机通道', rec.recognize(b'x', lang='en')[0]['source'] == 'local')
    lines, used = rec.read_lines(b'x')
    check('批改用 read_lines 走本机通道', used == 'local' and lines == MockOCR.lines)
    rows, method = rec.vision_grading(b'x', items)
    check('没配视觉模型时批改退回本机 OCR', method == 'local' and len(rows) == len(items))
    ocr_srv.shutdown()

    # ---------- 2. 本机 OpenAI 兼容语音 ----------
    tts_srv, tts_port = serve(MockTTS)
    voice_cfg = {'engine': 'openai', 'workers': 2, 'speeds': {'fast': 1.15, 'normal': 1.0, 'slow': 0.82},
                 'openai': {'base_url': 'http://127.0.0.1:%d/v1' % tts_port, 'model': 'mock',
                            'voice': 'zf_xiaobei', 'format': 'wav'}}
    eng = VoiceEngine(voice_cfg, ROOT)
    check('openai 引擎不需要参考音频也能建起来', eng.engine == 'openai' and not eng.token)
    p = eng.synthesize('测试一句')
    check('openai 引擎合成出音频文件', bool(p) and p.exists() and p.stat().st_size > 1000, p)
    check('请求体符合 OpenAI 语音接口', MockTTS.seen and MockTTS.seen[0]['input'] == '测试一句',
          MockTTS.seen[:1])
    check('同一句不会重复合成', eng.synthesize('测试一句').name == p.name)
    tts_srv.shutdown()

    # ---------- 3. 本机命令行语音（piper 这类从 stdin 读文字的工具） ----------
    writer = ('import sys, wave; '
              'w = wave.open(sys.argv[1], "wb"); w.setnchannels(1); w.setsampwidth(2); '
              'w.setframerate(24000); w.writeframes(b"\\x00\\x00" * 24000); w.close()')
    cmd_cfg = {'engine': 'command', 'workers': 1, 'speeds': {'normal': 1.0},
               'command': {'argv': [sys.executable, '-c', writer, '{out}'], 'stdin': True, 'ext': '.wav'}}
    eng2 = VoiceEngine(cmd_cfg, ROOT)
    p2 = eng2.synthesize('命令行引擎')
    check('命令行引擎合成出音频文件', bool(p2) and p2.exists() and p2.stat().st_size > 1000, p2)
    check('不同引擎的音色指纹不同', eng2.voice_tag != eng.voice_tag)

    # ---------- 4. 系统自带语音（默认引擎，零配置） ----------
    from core.tts import system_tts_available
    sys_cfg = {'engine': 'system', 'workers': 1, 'speeds': {'normal': 1.0},
               'system': {'voice': '', 'rate': 0}}
    eng3 = VoiceEngine(sys_cfg, ROOT)
    if system_tts_available():
        check('系统语音引擎报告可用', eng3.available())
        p3 = eng3.synthesize('请默写，春天。')
        check('系统语音合成出音频文件', bool(p3) and p3.exists() and p3.stat().st_size > 1000, p3)
    else:
        print('跳过   系统自带语音（这台机器没装 say/powershell/espeak-ng）')

    print('\n本地部署自测：%d 项通过，%d 项失败' % (len(OK), len(FAIL)))
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
