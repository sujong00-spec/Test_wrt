#!/usr/bin/env python3
"""小学生默写助手 · 本机服务

启动后在同一个 Wi-Fi 下的 iPad / 手机浏览器打开即可用（地址见启动时打印的提示）。
只用 Python 标准库，不需要装任何依赖。

    python3 server.py            # 前台启动
    python3 server.py --port 8770
"""

import argparse
import json
import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from core.access import AccessGate              # noqa: E402
from core.env import load_local_env          # noqa: E402
from core.webapp import App, serve           # noqa: E402
import features                              # noqa: E402


class Runtime:
    pass


def lan_ip():
    """猜一个同网段能访问到的本机地址。

    在 WSL 里必须报 Windows 主机的局域网地址，iPad 才连得上（WSL 自己的内网 IP 外面看不到）。
    """
    try:
        if 'microsoft' in Path('/proc/version').read_text(errors='ignore').lower():
            for cmd in (['ipconfig.exe'], ['/mnt/c/Windows/System32/ipconfig.exe']):
                try:
                    out = subprocess.run(cmd, capture_output=True, timeout=15).stdout
                except Exception:  # noqa: BLE001
                    continue
                text = out.decode('gbk', 'ignore') if out else ''
                found = re.findall(r'192\.168\.\d{1,3}\.\d{1,3}', text)
                if found:
                    return found[0]
    except Exception:  # noqa: BLE001
        pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:  # noqa: BLE001
        return '127.0.0.1'


def build(port=None):
    cfg = json.loads((ROOT / 'config.json').read_text(encoding='utf-8'))
    load_local_env(ROOT)
    if port:
        cfg['server']['port'] = port
    rt = Runtime()
    rt.cfg = cfg
    rt.root = ROOT
    data_root = Path(os.environ.get('DICTATION_DATA_DIR', ROOT)).expanduser()
    rt.access = AccessGate(data_root, enabled=cfg.get('access', {}).get('enabled', True))
    from core.dictation import PracticeStore, build_routes as practice_routes
    rt.practice = PracticeStore(data_root)
    app = App(cfg, ROOT, rt)
    rt.app = app
    app.routes.update(practice_routes(rt))
    features.load(app)
    return app, cfg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, default=None)
    ap.add_argument('--host', default=None)
    ap.add_argument('--show-access', action='store_true', help='접근 암호와 주소 표시')
    args = ap.parse_args()

    if args.show_access:
        app, cfg = build(args.port)
        port = cfg['server']['port']
        gate = app.runtime.access
        print('접근 암호: %s' % gate.token)
        print('이 컴퓨터: %s' % gate.token_url('http://127.0.0.1:%d' % port))
        print('같은 Wi-Fi:%s' % gate.token_url('http://%s:%d' % (lan_ip(), port)))
        print('암호는 data/access.json에 저장됩니다.')
        return

    app, cfg = build(args.port)
    host = args.host or cfg['server'].get('host', '0.0.0.0')
    port = cfg['server']['port']
    try:
        serve(app, host, port)
    except OSError as exc:
        print('포트 %d를 사용할 수 없습니다: %s' % (port, exc))
        print('서버가 이미 실행 중인지 확인하세요: http://127.0.0.1:%d/' % port)
        print('기존 서버를 Ctrl+C로 종료한 뒤 다시 실행하세요.')
        sys.exit(1)

    ip = lan_ip()
    print('한글 받아쓰기 서버가 시작되었습니다.')
    print('  접근 암호: %s' % app.runtime.access.token)
    print('  이 컴퓨터: %s' % app.runtime.access.token_url('http://127.0.0.1:%d' % port))
    if host == '0.0.0.0':
        print('  태블릿 접속:%s (같은 Wi-Fi에 연결하세요.)' % app.runtime.access.token_url('http://%s:%d' % (ip, port)))
    else:
        print('태블릿 접속은 --host 0.0.0.0 옵션으로 실행하세요.')
    print('  기능: %s' % ', '.join(f.get('name', '?') for f in app.features))
    print('음성: 모바일 브라우저의 한국어 음성을 사용합니다.')
    print('Ctrl+C로 종료합니다.')
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        print('\n종료되었습니다.')


if __name__ == '__main__':
    main()
