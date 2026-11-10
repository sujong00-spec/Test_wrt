#!/usr/bin/env python3
"""脚手架生成器：把「平台启动脚本 / 示例配置」这类结构固定的产物用代码生成，
模型只给参数（端口、发行版名、应用名），不再整篇手写。

用法：
  python3 tools/scaffold.py shims --port 8770 --distro Ubuntu --name 小学生默写助手
  python3 tools/scaffold.py shims --check       # 只比对，不改文件（CI/回归用）
  python3 tools/scaffold.py examples --check    # 校验 data/*.example 是否可直接重生成
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ---------------- 模板（LF 写，落盘时统一转 CRLF） ----------------

START_BAT = """@echo off
chcp 65001 >nul
title {name}服务
set "DISTRO={distro}"

echo ============================================
echo   {name} · 正在启动服务
echo   这个窗口不要关，关了浏览器就打不开了
echo ============================================
echo.

for /f "usebackq delims=" %%i in (`wsl.exe -d %DISTRO% -e wslpath -a "%CD%"`) do set "WSLDIR=%%i"
if "%WSLDIR%"=="" (
  echo 没能定位到 WSL 里的项目路径：请确认已装 WSL 与 %DISTRO% 发行版，
  echo 并把本文件放在项目目录下双击。
  pause
  exit /b 1
)

wsl.exe -d %DISTRO% -e bash -lc "cd '%WSLDIR%' && exec python3 server.py"
echo.
echo 服务已停止。
pause
"""

ALLOW_LAN_BAT = """@echo off
chcp 65001 >nul
title 开放局域网访问（需要管理员）
set "PORT={port}"

net session >nul 2>&1
if %errorlevel% neq 0 (
  echo 需要管理员权限，正在弹出授权窗口，请点「是」...
  powershell -NoProfile -Command "Start-Process -Verb RunAs -FilePath '%~f0'"
  exit /b
)

echo 正在设置端口转发与防火墙（端口 %PORT%）...
netsh interface portproxy delete v4tov4 listenport=%PORT% listenaddress=0.0.0.0 >nul 2>&1
netsh interface portproxy add v4tov4 listenport=%PORT% listenaddress=0.0.0.0 connectport=%PORT% connectaddress=127.0.0.1
netsh advfirewall firewall delete rule name="{name} %PORT%" >nul 2>&1
netsh advfirewall firewall add rule name="{name} %PORT%" dir=in action=allow protocol=TCP localport=%PORT%

echo.
echo 设置完成。同一 Wi-Fi 下的手机 / 平板用浏览器打开：
for /f "tokens=2 delims=:" %%i in ('ipconfig ^| findstr /c:"IPv4" ^| findstr /r /c:"192\\.168\\." /c:"10\\." /c:"172\\."') do echo    http://%%i:%PORT%/
echo.
echo 打不开时依次检查：服务窗口有没有在跑、两台设备是不是同一个 Wi-Fi、电脑有没有开代理/VPN。
echo.
pause
"""

SHOW_ACCESS_BAT = """@echo off
chcp 65001 >nul
title 查看访问口令
set "DISTRO={distro}"

echo 下面是打开本服务需要的口令与链接（不要把口令发给别人）。
echo.

for /f "usebackq delims=" %%i in (`wsl.exe -d %DISTRO% -e wslpath -a "%CD%"`) do set "WSLDIR=%%i"
if "%WSLDIR%"=="" (
  echo 没能定位到 WSL 里的项目路径。
  pause
  exit /b 1
)

wsl.exe -d %DISTRO% -e bash -lc "cd '%WSLDIR%' && python3 server.py --show-access"
echo.
pause
"""

INSTALL_TS_BAT = """@echo off
chcp 65001 >nul
title 远程访问（Tailscale 私有网络，装一次就够）
set "PORT={port}"

net session >nul 2>&1
if %errorlevel% neq 0 (
  echo 需要管理员权限，正在弹出授权窗口，请点「是」...
  powershell -NoProfile -Command "Start-Process -Verb RunAs -FilePath '%~f0'"
  exit /b
)

set "TS=C:\\Program Files\\Tailscale\\tailscale.exe"

if not exist "%TS%" (
  echo [1/3] 正在安装 Tailscale...
  powershell -NoProfile -Command "Invoke-WebRequest -Uri 'https://pkgs.tailscale.com/stable/tailscale-setup-latest-amd64.msi' -OutFile $env:TEMP\\tailscale.msi; Start-Process msiexec -ArgumentList '/i',$env:TEMP\\tailscale.msi,'/qn','/norestart' -Wait"
  timeout /t 8 /nobreak >nul
)

echo [2/3] 放行本机端口 %PORT%
netsh interface portproxy delete v4tov4 listenport=%PORT% listenaddress=0.0.0.0 >nul 2>&1
netsh interface portproxy add v4tov4 listenport=%PORT% listenaddress=0.0.0.0 connectport=%PORT% connectaddress=127.0.0.1
netsh advfirewall firewall delete rule name="{name} %PORT%" >nul 2>&1
netsh advfirewall firewall add rule name="{name} %PORT%" dir=in action=allow protocol=TCP localport=%PORT%

echo [3/3] 加入你的私有网络（会弹出浏览器，用你自己的账号登录一次）
"%TS%" up

echo.
echo ==========================================================
echo  这台电脑在私有网络里的地址：
"%TS%" ip -4
echo ==========================================================
echo.
echo 接着在 iPad / 手机上装 Tailscale 并用同一个账号登录，
echo 然后用浏览器打开  http://上面那个地址:%PORT%/
echo 装完之后在任何网络都能用，公网上没有任何入口。
echo.
pause
"""

START_SH = """#!/usr/bin/env bash
# {name}：在 Linux / macOS 上启动服务（Windows 用 start.bat）
set -e
cd "$(dirname "$0")"
exec python3 server.py "$@"
"""

SHIMS = {
    'start.bat': START_BAT,
    'allow-lan.bat': ALLOW_LAN_BAT,
    'show-access.bat': SHOW_ACCESS_BAT,
    'install-tailscale.bat': INSTALL_TS_BAT,
    'start.sh': START_SH,
}


def render(template: str, **kw) -> str:
    text = template.format(**kw)
    if text.endswith('\n'):
        text = text[:-1]
    return text


def write_text(path: Path, text: str, crlf: bool) -> None:
    data = text.replace('\r\n', '\n').replace('\n', '\r\n') if crlf else text
    path.write_bytes(data.encode('utf-8'))


def cmd_shims(args) -> int:
    params = dict(port=args.port, distro=args.distro, name=args.name)
    bad = 0
    for fname, tpl in SHIMS.items():
        want = render(tpl, **params)
        path = ROOT / fname
        crlf = fname.endswith('.bat')
        if args.check:
            have = path.read_bytes().decode('utf-8', 'ignore') if path.exists() else ''
            have = have.replace('\r\n', '\n')
            ok = have == want
            print(('一致   ' if ok else '不一致 ') + fname + ('' if ok else '  ← 需要重新生成'))
            bad += 0 if ok else 1
        else:
            write_text(path, want, crlf)
            if fname.endswith('.sh'):
                path.chmod(0o755)
            print('生成   ' + fname)
    if args.check:
        print('\n%s：%d 个文件，%d 个不一致' % ('校验', len(SHIMS), bad))
    return 1 if (args.check and bad) else 0


def cmd_examples(args) -> int:
    """示例配置：内容固定，直接写；--check 只比对。"""
    files = {
        'data/baidu.json.example': json.dumps({
            'api_key': '在这里填百度开放平台的 API Key',
            'secret_key': '在这里填百度开放平台的 Secret Key',
            'note': '百度 AI 开放平台 → 文字识别 → 手写文字识别 / 通用文字识别。个人实名有免费额度。'
                    '也可以改用环境变量 BAIDU_OCR_AK / BAIDU_OCR_SK。'},
            ensure_ascii=False, indent=2) + '\n',
        'data/secrets.env.example': (
            '# 本机凭据：一行一个 KEY=VALUE，不要提交到仓库。\n'
            '# 语音克隆服务（3 秒极速复刻）的访问令牌\n'
            'MODELSCOPE_API_KEY=\n\n'
            '# 视觉兜底识别（任意 OpenAI 兼容的多模态接口）的令牌\n'
            '# 服务地址与模型名在 config.json 的 recognize.vision 里配\n'
            'INTERN_DISCOVERY_API_KEY=\n'),
    }
    bad = 0
    for rel, want in files.items():
        path = ROOT / rel
        if args.check:
            have = path.read_bytes().decode('utf-8', 'ignore') if path.exists() else ''
            ok = have.replace('\r\n', '\n') == want
            print(('一致   ' if ok else '不一致 ') + rel)
            bad += 0 if ok else 1
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            write_text(path, want, crlf=False)
            print('生成   ' + rel)
    return 1 if (args.check and bad) else 0


def main() -> int:
    ap = argparse.ArgumentParser(description='脚手架生成器（模型只给参数，产物由代码渲染）')
    sub = ap.add_subparsers(dest='what', required=True)
    for name in ('shims', 'examples'):
        sp = sub.add_parser(name)
        sp.add_argument('--check', action='store_true', help='只比对，不写文件')
        sp.add_argument('--port', default=8770)
        sp.add_argument('--distro', default='Ubuntu', help='WSL 发行版名（shims 用）')
        sp.add_argument('--name', default='小学生默写助手')
    a = ap.parse_args()
    return cmd_shims(a) if a.what == 'shims' else cmd_examples(a)


if __name__ == '__main__':
    sys.exit(main())
