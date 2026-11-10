"""원본 OCR/TTS 테스트용 구성. 제품 서버에서 사용하지 않습니다."""
import json
from pathlib import Path
from types import SimpleNamespace
from core.access import AccessGate
from core.api import build_routes
from core.records_api import build_records_routes
from core.history import History
from core.store import Store
from core.recognize import Recognizer
from core.tts import VoiceEngine
from core.webapp import App
from features import moxie
ROOT = Path(__file__).resolve().parent.parent

def build(port=None):
    cfg = json.loads((ROOT / 'config.json').read_text())
    cfg['server']['default_feature'] = 'moxie'
    if port: cfg['server']['port'] = port
    rt = SimpleNamespace(root=ROOT, cfg=cfg, access=AccessGate(ROOT, enabled=False), store=Store(ROOT), history=History(ROOT), tts=VoiceEngine(cfg['voice'], ROOT), recognizer=Recognizer(cfg['recognize'], ROOT))
    app = App(cfg, ROOT, rt)
    rt.app = app
    app.routes.update(build_routes(rt))
    app.routes.update(build_records_routes(rt))
    app.add_feature(moxie)
    return app, cfg
