#!/usr/bin/env python3
"""临时公网链接：Cloudflare 反向隧道 + 自动过期保险。

    python3 临时链接.py                 # 默认 30 分钟后自动断开
    python3 临时链接.py --minutes 15
    python3 临时链接.py --stop          # 立刻断开

为什么这样设计：
  - 隧道是**从本机往外连**（反向隧道），家里不开放任何入站端口，也没有可被扫描的监听；
  - 到期由系统层 `timeout` 兜底强杀：**即使本脚本自己挂了，时间一到隧道也一定会断**；
  - 启动时先清掉上一次残留的隧道，避免旧链接还在外面活着；
  - 每次链接的域名都是随机的，断开即失效。
"""

import argparse
import json
import os
import re
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

CLOUDFLARED_CANDIDATES = [
    '/usr/local/bin/cloudflared',
    '/usr/bin/cloudflared',
    '/opt/homebrew/bin/cloudflared',
]
LOG = ROOT / 'cache' / 'tunnel.log'
STATUS = ROOT / 'cache' / 'tunnel.json'

# 注意：报错信息里会出现 api.trycloudflare.com（"failed to request quick Tunnel:
# Post https://api.trycloudflare.com/tunnel"），必须排除，否则会把接口域名当隧道地址发出去。
TUNNEL_URL_RE = re.compile(r'https://(?!api\.)[a-z0-9-]{4,}\.trycloudflare\.com')


def find_cloudflared():
    env = os.environ.get('CLOUDFLARED_PATH')
    if env and Path(env).exists():
        return env
    found = shutil.which('cloudflared')
    if found:
        return found
    local = Path(__file__).resolve().parent / 'cloudflared'
    if local.exists():
        return str(local)
    for cand in CLOUDFLARED_CANDIDATES:
        if Path(cand).exists():
            return cand
    return None


def kill_tunnels(quiet=False):
    """清掉残留的隧道进程（-x 精确匹配进程名，不会误杀别的命令）。"""
    def alive():
        return subprocess.run(['pgrep', '-x', 'cloudflared'], capture_output=True).returncode == 0

    had = alive()
    if had:
        subprocess.run(['pkill', '-x', '-TERM', 'cloudflared'], capture_output=True)
        for _ in range(12):
            time.sleep(0.4)
            if not alive():
                break
        if alive():
            subprocess.run(['pkill', '-x', '-KILL', 'cloudflared'], capture_output=True)
            time.sleep(0.5)
    if not quiet:
        print('已清理残留隧道' if had else '没有残留隧道')
    return not alive()


def service_alive(port):
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=3):
            return True
    except OSError:
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--minutes', type=float, default=30, help='多少分钟后自动断开（默认 30）')
    ap.add_argument('--port', type=int, default=None)
    ap.add_argument('--stop', action='store_true', help='立刻断开所有临时链接')
    ap.add_argument('--json', action='store_true', help='只输出结果 JSON')
    args = ap.parse_args()

    if args.stop:
        ok = kill_tunnels()
        try:
            STATUS.write_text(json.dumps({'url': None, 'token': None,
                                          'closedAt': datetime.now().isoformat(timespec='seconds')},
                                         ensure_ascii=False, indent=1), encoding='utf-8')
        except OSError:
            pass
        print('已断开（链接和钥匙同时作废）' if ok else '没能断开，请人工检查 cloudflared 进程')
        return 0 if ok else 1

    cfg = json.loads((ROOT / 'config.json').read_text(encoding='utf-8'))
    port = args.port or cfg['server']['port']
    if not service_alive(port):
        print('本机服务没在跑（127.0.0.1:%d 连不上），先启动服务再开链接。' % port)
        return 2

    cf = find_cloudflared()
    if not cf:
        print('找不到 cloudflared，先安装它（见 README）。')
        return 3

    kill_tunnels(quiet=True)

    seconds = int(args.minutes * 60)
    LOG.parent.mkdir(parents=True, exist_ok=True)

    def spawn():
        log = open(LOG, 'w', encoding='utf-8')
        # timeout 是保险：本脚本被杀，隧道也会在到期时断
        proc = subprocess.Popen(
            ['timeout', '-s', 'TERM', '-k', '10', str(seconds), cf,
             'tunnel', '--no-autoupdate', '--url', 'http://127.0.0.1:%d' % port],
            stdout=log, stderr=subprocess.STDOUT)
        url = None
        deadline = time.time() + 60
        while time.time() < deadline and proc.poll() is None:
            time.sleep(1)
            text = LOG.read_text(encoding='utf-8', errors='ignore') if LOG.exists() else ''
            m = TUNNEL_URL_RE.search(text)
            if m:
                url = m.group(0)
                break
        return proc, url, log

    proc, url, log = spawn()
    tries = 0
    while not url and tries < 3:
        tries += 1
        proc.terminate()
        time.sleep(2)
        kill_tunnels(quiet=True)
        print('第 %d 次没连上，重试…' % tries)
        proc, url, log = spawn()

    if not url:
        proc.terminate()
        print('没能拿到公网地址（网络到 Cloudflare 不稳），日志：%s' % LOG)
        return 4

    token = secrets.token_hex(16)      # 跟这条链接同生共死的钥匙
    expires = datetime.now() + timedelta(seconds=seconds)
    STATUS.write_text(json.dumps({
        'url': url, 'token': token,
        'startedAt': datetime.now().isoformat(timespec='seconds'),
        'expiresAt': expires.isoformat(timespec='seconds'), 'minutes': args.minutes,
        'pid': proc.pid,
    }, ensure_ascii=False, indent=1), encoding='utf-8')

    link = '%s/?k=%s' % (url, token)
    if args.json:
        print(json.dumps({'ok': True, 'url': url, 'link': link,
                          'expiresAt': expires.isoformat(timespec='seconds')}, ensure_ascii=False))
    else:
        print('临时链接（带钥匙，直接点开就行）：%s' % link)
        print('到期时间：%s（%g 分钟后自动断开，钥匙同时作废）'
              % (expires.strftime('%H:%M:%S'), args.minutes))
        print('提前断开：python3 临时链接.py --stop')

    rc = proc.wait()          # 等到期（或被打断）
    try:
        log.close()
    except Exception:  # noqa: BLE001
        pass
    # 只有"当前这条"才有资格写关闭记录，别覆盖掉新开的那条
    try:
        cur = json.loads(STATUS.read_text(encoding='utf-8')) if STATUS.exists() else {}
        if cur.get('token') == token:
            STATUS.write_text(json.dumps({'url': None, 'token': None,
                                          'closedAt': datetime.now().isoformat(timespec='seconds')},
                                         ensure_ascii=False, indent=1), encoding='utf-8')
    except Exception:  # noqa: BLE001
        pass
    print('临时链接已自动断开（%s）' % datetime.now().strftime('%H:%M:%S'))
    return 0 if rc in (0, 124, -15, 143) else rc


if __name__ == '__main__':
    sys.exit(main())
